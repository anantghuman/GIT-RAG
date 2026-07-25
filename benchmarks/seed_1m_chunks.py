"""Seed synthetic chunk rows for retrieval-scale benchmarking."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone

from gitrag.db.models import Chunk, ChunkRef, File, Repository
from gitrag.db.session import create_all, session_scope
from gitrag.ids import chunk_id, content_hash, file_id
from gitrag.retrieval.embedding import deterministic_vector
from gitrag.retrieval.vector import get_vector_store


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-id", default="bench")
    parser.add_argument("--chunks", type=int, default=1_000_000)
    parser.add_argument("--batch-size", type=int, default=1000)
    args = parser.parse_args()

    create_all()
    vector_store = get_vector_store()
    now = datetime.now(timezone.utc)

    with session_scope() as session:
        session.merge(
            Repository(
                id=args.repo_id,
                url="https://github.com/example/bench.git",
                name="bench",
                local_path="/tmp/bench.git",
                default_branch="main",
            )
        )

        vectors = []
        for i in range(args.chunks):
            path = f"src/module_{i % 1000}.py"
            fid = file_id(args.repo_id, path)
            content = f"def symbol_{i}():\n    return {i % 97}\n"
            h = content_hash(content)
            cid = chunk_id(
                repo_id=args.repo_id,
                sha=f"{i % 100000:040x}",
                path=path,
                symbol=f"symbol_{i}",
                line_start=1,
                line_end=2,
                chunk_type="code",
                hash_value=h,
                embedding_model="text-embedding-3-small",
            )
            session.merge(File(id=fid, repo_id=args.repo_id, path=path, language="Python", latest_sha=f"{i:040x}"))
            session.merge(
                Chunk(
                    id=cid,
                    repo_id=args.repo_id,
                    sha=f"{i % 100000:040x}",
                    file_id=fid,
                    path=path,
                    language="Python",
                    chunk_type="code",
                    symbol_name=f"symbol_{i}",
                    line_start=1,
                    line_end=2,
                    content=content,
                    content_hash=h,
                    embedding_model="text-embedding-3-small",
                    vector_id=cid,
                    commit_time=now,
                    metadata_json={"synthetic": True},
                )
            )
            session.merge(ChunkRef(chunk_id=cid, repo_id=args.repo_id, ref_name="main"))
            vectors.append(
                (
                    cid,
                    deterministic_vector(content),
                    {
                        "repo_id": args.repo_id,
                        "sha": f"{i % 100000:040x}",
                        "path": path,
                        "branch_names": ["main"],
                        "language": "Python",
                        "chunk_type": "code",
                        "symbol_name": f"symbol_{i}",
                        "commit_time": now.isoformat(),
                    },
                )
            )
            if len(vectors) >= args.batch_size:
                vector_store.upsert(vectors)
                session.flush()
                vectors.clear()
                print(f"seeded {i + 1}/{args.chunks}")

        if vectors:
            vector_store.upsert(vectors)
        print(f"seeded {args.chunks} chunks")


if __name__ == "__main__":
    main()
