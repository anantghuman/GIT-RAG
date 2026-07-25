"""Bootstrap and incremental ingestion orchestration."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import json
from pathlib import Path
import uuid

from sqlalchemy.orm import Session

from gitrag.config import Settings, get_settings
from gitrag.db.models import (
    Chunk,
    ChunkRef,
    Commit,
    CommitParent,
    File,
    FileVersion,
    IngestionJob,
    Repository,
    RepositoryRef,
    SnapshotManifest,
    Symbol,
)
from gitrag.git import (
    ZERO_SHA,
    build_commit_graph,
    changed_files,
    clone_or_fetch_mirror,
    diff_for_file,
    file_at_sha,
    language_for_path,
    list_refs,
    repo_display_name,
    refs_containing_commit,
    rev_list_between,
)
from gitrag.ids import (
    chunk_id,
    content_hash,
    file_id,
    file_version_id,
    normalize_repo_id,
    stable_hash,
    symbol_id,
)
from gitrag.ingest.chunker import CodeChunk, build_parsers, chunk_file_content, should_index_path
from gitrag.queue.kafka import KafkaPublisher
from gitrag.retrieval.embedding import Embedder
from gitrag.retrieval.vector import VectorStore, get_vector_store
from gitrag.storage.object_store import ObjectStore, diff_key, snapshot_key
from gitrag.storage.snapshot import choose_storage_kind, storage_reduction


@dataclass(frozen=True)
class BootstrapResult:
    repo_id: str
    job_id: str
    repo_path: str
    refs: int
    commits: int


class IngestionService:
    def __init__(
        self,
        *,
        settings: Settings | None = None,
        embedder: Embedder | None = None,
        vector_store: VectorStore | None = None,
        object_store: ObjectStore | None = None,
        publisher: KafkaPublisher | None = None,
    ):
        self.settings = settings or get_settings()
        self.embedder = embedder or Embedder(self.settings)
        self.vector_store = vector_store or get_vector_store(self.settings)
        self.object_store = object_store or ObjectStore(self.settings)
        self.publisher = publisher

    def bootstrap_repo(self, session: Session, *, repo_url: str, enqueue: bool = True) -> BootstrapResult:
        repo_id = normalize_repo_id(repo_url)
        repo_path = clone_or_fetch_mirror(repo_url, self.settings.clone_repo_dir)
        refs = list_refs(repo_path)
        graph = build_commit_graph(repo_path)

        repo = session.get(Repository, repo_id)
        if repo is None:
            repo = Repository(id=repo_id, url=repo_url, name=repo_display_name(repo_url), local_path=str(repo_path))
        repo.local_path = str(repo_path)
        repo.default_branch = _default_branch(refs)
        session.merge(repo)

        for ref in refs:
            session.merge(RepositoryRef(repo_id=repo_id, name=ref.name, ref_type=ref.ref_type, sha=ref.sha))
        self._persist_commit_graph(session, repo_id, graph)

        job_id = f"job_{stable_hash(str(uuid.uuid4()), 32)}"
        job = IngestionJob(
            id=job_id,
            repo_id=repo_id,
            job_type="bootstrap",
            status="queued" if enqueue else "running",
            after_sha="--all",
            stats_json={"commit_count": len(graph), "ref_count": len(refs)},
        )
        session.add(job)
        session.flush()

        if enqueue:
            payload = {"job_id": job_id, "repo_id": repo_id, "repo_url": repo_url, "mode": "bootstrap"}
            self._publish(payload, key=repo_id)

        return BootstrapResult(repo_id=repo_id, job_id=job_id, repo_path=str(repo_path), refs=len(refs), commits=len(graph))

    def enqueue_webhook_job(
        self,
        session: Session,
        *,
        repo_url: str,
        ref: str,
        before: str,
        after: str,
        delivery_id: str,
    ) -> IngestionJob:
        repo_id = normalize_repo_id(repo_url)
        repo = session.get(Repository, repo_id)
        if repo is None:
            repo_path = clone_or_fetch_mirror(repo_url, self.settings.clone_repo_dir)
            repo = Repository(id=repo_id, url=repo_url, name=repo_display_name(repo_url), local_path=str(repo_path))
            session.add(repo)

        existing = (
            session.query(IngestionJob)
            .filter(IngestionJob.repo_id == repo_id, IngestionJob.delivery_id == delivery_id)
            .one_or_none()
        )
        if existing:
            return existing

        job = IngestionJob(
            id=f"job_{stable_hash(delivery_id or str(uuid.uuid4()), 32)}",
            repo_id=repo_id,
            job_type="webhook",
            status="queued",
            ref=ref,
            before_sha=before,
            after_sha=after,
            delivery_id=delivery_id,
        )
        session.add(job)
        session.flush()
        self._publish(
            {
                "job_id": job.id,
                "repo_id": repo_id,
                "repo_url": repo_url,
                "mode": "webhook",
                "ref": ref,
                "before": before,
                "after": after,
                "delivery_id": delivery_id,
            },
            key=repo_id,
        )
        return job

    def process_job(self, session: Session, payload: dict) -> dict:
        job = session.get(IngestionJob, payload["job_id"])
        if job is None:
            raise ValueError(f"Unknown job_id: {payload['job_id']}")
        job.status = "running"
        session.flush()

        repo = session.get(Repository, payload["repo_id"])
        if repo is None:
            raise ValueError(f"Unknown repo_id: {payload['repo_id']}")
        repo_path = clone_or_fetch_mirror(repo.url, self.settings.clone_repo_dir)
        repo.local_path = str(repo_path)

        try:
            if payload.get("mode") == "bootstrap":
                graph = build_commit_graph(repo_path)
                shas = sorted(graph.keys(), key=lambda sha: graph[sha].get("depth", 0))
                self._persist_commit_graph(session, repo.id, graph)
            else:
                shas = rev_list_between(repo_path, payload.get("before"), payload["after"])
                graph = build_commit_graph(repo_path)
                self._persist_commit_graph(session, repo.id, graph)

            stats = self.ingest_commits(session, repo_id=repo.id, repo_path=Path(repo_path), shas=shas)
            repo.indexed_generation += 1
            job.status = "complete"
            job.stats_json = stats
            return stats
        except Exception as exc:
            job.status = "failed"
            job.error = str(exc)
            raise

    def ingest_commits(self, session: Session, *, repo_id: str, repo_path: Path, shas: list[str]) -> dict:
        parsers = build_parsers()
        stats = {"commits": 0, "files": 0, "chunks": 0, "vectors": 0, "naive_bytes": 0, "stored_bytes": 0}
        vector_batch: list[tuple[str, list[float], dict]] = []
        seen_chunk_ids: set[str] = set()
        seen_symbol_ids: set[str] = set()
        seen_files: dict[str, File] = {}

        for commit_index, sha in enumerate(shas, 1):
            commit = session.get(Commit, {"repo_id": repo_id, "sha": sha})
            commit_refs = refs_containing_commit(repo_path, sha)
            is_merge = bool(commit.is_merge) if commit else False
            commit_time = commit.commit_time if commit else None
            parent_shas = [row.parent_sha for row in session.query(CommitParent).filter_by(repo_id=repo_id, child_sha=sha).all()]
            parent_sha = parent_shas[0] if parent_shas else None

            for changed in changed_files(repo_path, sha):
                if changed.status == "D":
                    continue
                if not should_index_path(changed.path, include_vendor=self.settings.index_vendor_code):
                    continue
                language = language_for_path(changed.path)
                if language is None:
                    continue
                content = file_at_sha(repo_path, sha, changed.path)
                if content is None:
                    continue
                parent_content = file_at_sha(repo_path, parent_sha, changed.path) if parent_sha else None
                file_hash = content_hash(content)
                current_file_id = file_id(repo_id, changed.path)
                db_file = seen_files.get(current_file_id)
                if db_file is None:
                    db_file = session.get(File, current_file_id)
                if db_file is None:
                    db_file = File(
                        id=current_file_id,
                        repo_id=repo_id,
                        path=changed.path,
                        language=language,
                        latest_sha=sha,
                    )
                    session.add(db_file)
                else:
                    db_file.language = language
                    db_file.latest_sha = sha
                seen_files[current_file_id] = db_file

                decision = choose_storage_kind(
                    has_parent=parent_sha is not None,
                    is_merge=is_merge,
                    version_index=commit_index,
                    current_content=content,
                    parent_content=parent_content,
                    snapshot_interval=self.settings.snapshot_interval,
                    change_threshold=self.settings.snapshot_change_threshold,
                )
                object_text = content
                object_key = snapshot_key(repo_id, sha, changed.path)
                if decision.kind == "diff" and parent_sha:
                    object_text = diff_for_file(repo_path, sha, changed.path) or ""
                    object_key = diff_key(repo_id, parent_sha, sha, changed.path)
                stored = self.object_store.put_text(object_key, object_text, compress=True)
                stats["naive_bytes"] += len(content.encode("utf-8"))
                stats["stored_bytes"] += stored.stored_bytes

                file_version = FileVersion(
                    id=file_version_id(repo_id, sha, changed.path),
                    repo_id=repo_id,
                    file_id=current_file_id,
                    sha=sha,
                    path=changed.path,
                    parent_sha=parent_sha,
                    change_type=changed.status,
                    storage_kind=decision.kind,
                    s3_key=stored.key,
                    content_hash=file_hash,
                    size_bytes=stored.raw_bytes,
                    compressed_bytes=stored.stored_bytes,
                )
                session.merge(file_version)
                session.merge(
                    SnapshotManifest(
                        id=f"snap_{stable_hash(file_version.id + '|' + decision.kind, 32)}",
                        repo_id=repo_id,
                        file_id=current_file_id,
                        sha=sha,
                        parent_sha=parent_sha,
                        path=changed.path,
                        kind=decision.kind,
                        s3_key=stored.key,
                        content_hash=file_hash,
                        naive_bytes=len(content.encode("utf-8")),
                        stored_bytes=stored.stored_bytes,
                    )
                )

                parser = parsers.get(language)
                chunks = chunk_file_content(changed.path, content, parser, language)
                diff_text = diff_for_file(repo_path, sha, changed.path)
                if diff_text:
                    chunks.append(
                        CodeChunk(
                            content=diff_text[:12000],
                            path=changed.path,
                            language=language,
                            chunk_type="diff",
                            node_type="diff",
                            line_start=1,
                            line_end=1,
                            symbol_name=None,
                        )
                    )

                vectors_by_hash = self.embedder.embed_with_cache(session, [chunk.content for chunk in chunks])
                for code_chunk in chunks:
                    chunk_hash = content_hash(code_chunk.content)
                    symbol_pk = None
                    if code_chunk.symbol_name:
                        symbol_pk = symbol_id(repo_id, changed.path, code_chunk.symbol_name, code_chunk.node_type)
                        if symbol_pk not in seen_symbol_ids:
                            seen_symbol_ids.add(symbol_pk)
                            session.merge(
                                Symbol(
                                    id=symbol_pk,
                                    repo_id=repo_id,
                                    file_id=current_file_id,
                                    path=changed.path,
                                    name=code_chunk.symbol_name,
                                    kind=code_chunk.node_type,
                                    language=language,
                                    first_sha=sha,
                                    last_sha=sha,
                                )
                            )
                    current_chunk_id = chunk_id(
                        repo_id=repo_id,
                        sha=sha,
                        path=changed.path,
                        symbol=code_chunk.symbol_name,
                        line_start=code_chunk.line_start,
                        line_end=code_chunk.line_end,
                        chunk_type=code_chunk.chunk_type,
                        hash_value=chunk_hash,
                        embedding_model=self.embedder.model,
                    )
                    if current_chunk_id in seen_chunk_ids:
                        continue
                    seen_chunk_ids.add(current_chunk_id)
                    db_chunk = Chunk(
                        id=current_chunk_id,
                        repo_id=repo_id,
                        sha=sha,
                        file_id=current_file_id,
                        symbol_id=symbol_pk,
                        path=changed.path,
                        language=language,
                        chunk_type=code_chunk.chunk_type,
                        symbol_name=code_chunk.symbol_name,
                        line_start=code_chunk.line_start,
                        line_end=code_chunk.line_end,
                        content=code_chunk.content,
                        content_hash=chunk_hash,
                        embedding_model=self.embedder.model,
                        vector_id=current_chunk_id,
                        commit_time=commit_time,
                        metadata_json={"node_type": code_chunk.node_type, "storage_kind": decision.kind},
                    )
                    session.merge(db_chunk)
                    for ref_name in commit_refs:
                        session.merge(ChunkRef(chunk_id=current_chunk_id, repo_id=repo_id, ref_name=ref_name))
                    vector_batch.append(
                        (
                            current_chunk_id,
                            vectors_by_hash[chunk_hash],
                            {
                                "repo_id": repo_id,
                                "sha": sha,
                                "path": changed.path,
                                "branch_names": commit_refs,
                                "language": language,
                                "chunk_type": code_chunk.chunk_type,
                                "symbol_name": code_chunk.symbol_name or "",
                                "commit_time": commit_time.isoformat() if commit_time else "",
                            },
                        )
                    )
                    stats["chunks"] += 1
                stats["files"] += 1

            stats["commits"] += 1
            if len(vector_batch) >= self.settings.vector_upsert_batch_size:
                self.vector_store.upsert(vector_batch)
                stats["vectors"] += len(vector_batch)
                vector_batch.clear()
                session.flush()

        if vector_batch:
            self.vector_store.upsert(vector_batch)
            stats["vectors"] += len(vector_batch)
        session.flush()
        stats["storage_reduction"] = storage_reduction(stats["naive_bytes"], stats["stored_bytes"])
        self._write_storage_report(repo_id, stats)
        return stats

    def _persist_commit_graph(self, session: Session, repo_id: str, graph: dict[str, dict]) -> None:
        for sha, data in graph.items():
            commit_time = datetime.fromtimestamp(int(data.get("timestamp") or 0), tz=timezone.utc)
            session.merge(
                Commit(
                    repo_id=repo_id,
                    sha=sha,
                    author=data.get("author", ""),
                    email=data.get("email", ""),
                    message=data.get("message", ""),
                    commit_time=commit_time,
                    is_merge=bool(data.get("is_merge")),
                    depth=int(data.get("depth") or 0),
                    refs_json=data.get("refs", []),
                )
            )
            for position, parent_sha in enumerate(data.get("parents", [])):
                session.merge(CommitParent(repo_id=repo_id, child_sha=sha, parent_sha=parent_sha, position=position))

    def _publish(self, payload: dict, *, key: str) -> None:
        if self.publisher is not None:
            self.publisher.publish(payload, key=key)

    def _write_storage_report(self, repo_id: str, stats: dict) -> None:
        path = Path(self.settings.project_dir) / "storage_report.json"
        report = {"repo_id": repo_id, **stats}
        path.write_text(json.dumps(report, indent=2), encoding="utf-8")


def _default_branch(refs) -> str | None:
    for candidate in ("origin/main", "main", "origin/master", "master"):
        if any(ref.name == candidate for ref in refs):
            return candidate
    return refs[0].name if refs else None
