"""Branch-aware retrieval and optional answer synthesis."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from time import perf_counter

from sqlalchemy.orm import Session

from gitrag.config import Settings, get_settings
from gitrag.db.models import Chunk, ChunkRef, Repository
from gitrag.ids import query_cache_key
from gitrag.retrieval.cache import QueryCache
from gitrag.retrieval.embedding import Embedder
from gitrag.retrieval.vector import VectorStore, get_vector_store


@dataclass(frozen=True)
class Citation:
    sha: str
    branch: str | None
    path: str
    line_start: int
    line_end: int
    github_url: str | None
    score: float
    chunk_type: str


class QueryService:
    def __init__(
        self,
        *,
        settings: Settings | None = None,
        embedder: Embedder | None = None,
        vector_store: VectorStore | None = None,
        cache: QueryCache | None = None,
    ):
        self.settings = settings or get_settings()
        self.embedder = embedder or Embedder(self.settings)
        self.vector_store = vector_store or get_vector_store(self.settings)
        self.cache = cache or QueryCache(self.settings)

    def query(
        self,
        session: Session,
        *,
        repo_id: str,
        question: str,
        branch: str | None = None,
        sha: str | None = None,
        path_prefix: str | None = None,
        top_k: int | None = None,
        include_answer: bool = True,
    ) -> dict:
        top_k = top_k or self.settings.default_top_k
        repo = session.get(Repository, repo_id)
        if repo is None:
            raise ValueError(f"Unknown repo_id: {repo_id}")

        cache_key = query_cache_key(
            model=self.embedder.model,
            repo_id=repo_id,
            question=question,
            branch=branch,
            sha=sha,
            path_prefix=path_prefix,
            top_k=top_k,
            index_generation=repo.indexed_generation,
            include_answer=include_answer,
        )
        cached = self.cache.get(cache_key)
        if cached:
            cached["cache_hit"] = True
            return cached

        timings: dict[str, float] = {}
        start = perf_counter()
        query_vector = self.embedder.embed_query(question)
        timings["embed_ms"] = (perf_counter() - start) * 1000

        pinecone_filter: dict = {"repo_id": repo_id}
        if sha:
            pinecone_filter["sha"] = sha
        if branch:
            pinecone_filter["branch_names"] = {"$in": [branch]}

        start = perf_counter()
        matches = self.vector_store.query(query_vector, top_k=top_k * 3, filters=pinecone_filter)
        timings["vector_ms"] = (perf_counter() - start) * 1000

        start = perf_counter()
        chunk_ids = [m.id for m in matches]
        chunks = {chunk.id: chunk for chunk in session.query(Chunk).filter(Chunk.id.in_(chunk_ids)).all()} if chunk_ids else {}
        ref_rows = (
            session.query(ChunkRef).filter(ChunkRef.chunk_id.in_(chunk_ids)).all() if chunk_ids else []
        )
        refs_by_chunk: dict[str, set[str]] = {}
        for ref in ref_rows:
            refs_by_chunk.setdefault(ref.chunk_id, set()).add(ref.ref_name)

        hydrated = []
        for match in matches:
            chunk = chunks.get(match.id)
            if chunk is None:
                continue
            if path_prefix and not chunk.path.startswith(path_prefix):
                continue
            if sha and chunk.sha != sha:
                continue
            branch_names = refs_by_chunk.get(chunk.id, set())
            if branch and branch not in branch_names:
                continue
            hydrated.append((match, chunk, branch_names))
            if len(hydrated) >= top_k:
                break
        timings["hydrate_ms"] = (perf_counter() - start) * 1000

        citations = [
            Citation(
                sha=chunk.sha,
                branch=branch or (sorted(refs)[0] if refs else None),
                path=chunk.path,
                line_start=chunk.line_start,
                line_end=chunk.line_end,
                github_url=_github_url(repo.url, chunk.sha, chunk.path, chunk.line_start, chunk.line_end),
                score=match.score,
                chunk_type=chunk.chunk_type,
            )
            for match, chunk, refs in hydrated
        ]

        answer = None
        if include_answer:
            start = perf_counter()
            answer = self._answer(question, [chunk for _, chunk, _ in hydrated])
            timings["answer_ms"] = (perf_counter() - start) * 1000

        response = {
            "repo_id": repo_id,
            "question": question,
            "answer": answer,
            "citations": [asdict(citation) for citation in citations],
            "matches": [
                {
                    "id": chunk.id,
                    "score": match.score,
                    "content": chunk.content,
                    "metadata": {
                        "sha": chunk.sha,
                        "path": chunk.path,
                        "language": chunk.language,
                        "chunk_type": chunk.chunk_type,
                        "symbol_name": chunk.symbol_name,
                    },
                }
                for match, chunk, _ in hydrated
            ],
            "cache_hit": False,
            "timings_ms": timings,
        }
        self.cache.set(cache_key, response)
        return response

    def _answer(self, question: str, chunks: list[Chunk]) -> str:
        if not chunks:
            return "I do not have enough indexed context to answer that."
        if not self.settings.openai_api_key or self.settings.deterministic_embeddings:
            return "Retrieved relevant code context; LLM synthesis is disabled in this environment."
        from openai import OpenAI

        context = "\n\n".join(
            f"{chunk.path}@{chunk.sha[:8]}:{chunk.line_start}-{chunk.line_end}\n{chunk.content[:4000]}"
            for chunk in chunks
        )
        client = OpenAI(api_key=self.settings.openai_api_key)
        resp = client.chat.completions.create(
            model=self.settings.openai_chat_model,
            messages=[
                {
                    "role": "system",
                    "content": "Answer using only the supplied repository snippets. Cite path, SHA, and line ranges.",
                },
                {"role": "user", "content": f"Question: {question}\n\nContext:\n{context}"},
            ],
            temperature=0.2,
        )
        return resp.choices[0].message.content or ""


def _github_url(repo_url: str, sha: str, path: str, line_start: int, line_end: int) -> str | None:
    if "github.com" not in repo_url:
        return None
    cleaned = repo_url.removesuffix(".git")
    if cleaned.startswith("git@github.com:"):
        cleaned = "https://github.com/" + cleaned.removeprefix("git@github.com:")
    return f"{cleaned}/blob/{sha}/{path}#L{line_start}-L{line_end}"
