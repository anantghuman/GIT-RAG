"""End-to-end ingestion: walk the commit graph, chunk code, embed, upsert."""
import json
import os
import sys
from datetime import datetime

from dotenv import load_dotenv

from dag_utils import get_branches_containing_commit, get_commit_depth, topological_sort
from embeddings import generate_embeddings, upsert_embeddings
from ingest_cli import build_parsers, chunk_file, get_file_language, get_language
from pinecone_setup import setup_vector_db
from sha_parser import get_changed_files, get_diff_for_file

load_dotenv()


def _normalize_languages(languages):
    if isinstance(languages, dict):
        return list(languages.keys())
    return list(languages or [])


def process_commit(sha, commit_data, branches, depth, parsers, language_names, stats):
    chunks = []
    for file_path in get_changed_files(sha):
        language = get_file_language(file_path, language_names)
        if not language or language not in parsers:
            continue

        try:
            file_chunks = chunk_file(sha, file_path, parsers[language], language)
        except Exception as e:
            print(f"   parse error in {file_path}: {e}")
            continue

        common = {
            "branches": branches,
            "parents": commit_data["parents"],
            "children": commit_data.get("children", []),
            "depth": depth,
            "is_merge": len(commit_data["parents"]) > 1,
            "refs": commit_data.get("refs", []),
            "timestamp": commit_data["timestamp"],
            "commit_message": commit_data["message"],
            "author": commit_data.get("author", ""),
        }

        for chunk in file_chunks:
            chunk.update(common)
        chunks.extend(file_chunks)
        stats["total_files"] += 1

        if commit_data["parents"]:
            diff = get_diff_for_file(sha, file_path)
            if diff:
                diff_chunk = {
                    "content": diff[:8000],
                    "sha": sha,
                    "path": file_path,
                    "type": "diff",
                    "language": language,
                    "line_start": 0,
                    "line_end": 0,
                    **common,
                }
                chunks.append(diff_chunk)

    stats["total_chunks"] += len(chunks)
    return chunks


def ingest_repository():
    print("Starting Git-RAG ingestion\n")

    if not os.path.exists("commit_graph.json"):
        print("commit_graph.json not found. Run `python script.py` first.")
        sys.exit(1)

    with open("commit_graph.json") as f:
        data = json.load(f)
    commit_graph = data["graph"]
    branch_tips = data["branch_tips"]
    repo_path = data["repo_path"]

    print(f"Repo: {repo_path}")
    print(f"Commits: {len(commit_graph)}")
    print(f"Refs: {len(branch_tips)}\n")

    languages = get_language()
    if not languages:
        languages = ["Python", "JavaScript", "TypeScript", "Java", "Go"]
        print(f"Falling back to languages: {languages}")
    else:
        print(f"Languages from GitHub: {list(languages)}")

    print("\nBuilding parsers...")
    parsers = build_parsers(languages)
    if not parsers:
        print("No parsers loaded. Install tree-sitter language packages and retry.")
        return
    language_names = _normalize_languages(languages)

    print("\nConnecting to Pinecone...")
    index = setup_vector_db()

    sorted_commits = topological_sort(commit_graph)
    sorted_commits.reverse()  # Oldest first; order does not change correctness.
    print(f"\nProcessing {len(sorted_commits)} commits...")

    stats = {
        "processed_commits": 0,
        "total_chunks": 0,
        "total_files": 0,
        "errors": 0,
        "start_time": datetime.now(),
    }

    batch_size = 10
    for batch_start in range(0, len(sorted_commits), batch_size):
        batch_chunks = []
        for sha in sorted_commits[batch_start : batch_start + batch_size]:
            try:
                commit_data = commit_graph[sha]
                branches = get_branches_containing_commit(sha, commit_graph, branch_tips)
                depth = get_commit_depth(sha, commit_graph)
                batch_chunks.extend(
                    process_commit(sha, commit_data, branches, depth, parsers, language_names, stats)
                )
                stats["processed_commits"] += 1
            except Exception as e:
                print(f"  commit {sha[:8]} failed: {e}")
                stats["errors"] += 1

        if batch_chunks:
            try:
                print(
                    f"\n[batch {batch_start // batch_size + 1}] embedding {len(batch_chunks)} chunks "
                    f"(commits processed: {stats['processed_commits']}/{len(sorted_commits)})"
                )
                generate_embeddings(batch_chunks)
                upsert_embeddings(index, batch_chunks)
            except Exception as e:
                print(f"  embed/upsert failed: {e}")
                stats["errors"] += 1

    elapsed = datetime.now() - stats["start_time"]
    print("\n" + "=" * 60)
    print("INGESTION COMPLETE")
    print("=" * 60)
    print(f"Commits processed : {stats['processed_commits']}")
    print(f"Files processed   : {stats['total_files']}")
    print(f"Chunks created    : {stats['total_chunks']}")
    print(f"Errors            : {stats['errors']}")
    print(f"Elapsed           : {elapsed}")

    try:
        idx_stats = index.describe_index_stats()
        print(f"Vectors in index  : {idx_stats.get('total_vector_count', '?')}")
    except Exception as e:
        print(f"Could not fetch index stats: {e}")


if __name__ == "__main__":
    if not os.getenv("OPENAI_API_KEY"):
        print("OPENAI_API_KEY is not set in .env; embeddings cannot be generated.")
        sys.exit(1)
    if not os.getenv("PINECONE_API_KEY"):
        print("PINECONE_API_KEY is not set in .env.")
        sys.exit(1)

    ingest_repository()
