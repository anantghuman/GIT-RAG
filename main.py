"""Single entry point for legacy scripts and the production Git-RAG services."""
import argparse
import os
import sys

from dotenv import load_dotenv

load_dotenv()


def cmd_clone(_args):
    import script
    script.main()


def cmd_ingest(_args):
    from ingest_all import ingest_repository
    ingest_repository()


def cmd_query(args):
    if getattr(args, "repo_id", None):
        from gitrag.db.session import create_all, session_scope
        from gitrag.retrieval.service import QueryService

        if os.getenv("DATABASE_URL", "sqlite:///./gitrag.db").startswith("sqlite"):
            create_all()
        question = args.question or input("Question: ").strip()
        with session_scope() as session:
            result = QueryService().query(
                session,
                repo_id=args.repo_id,
                question=question,
                branch=args.branch,
                sha=args.sha,
                path_prefix=args.path_prefix or args.path,
                top_k=args.top_k,
                include_answer=not args.no_llm,
            )
        if result.get("answer"):
            print("\nAnswer:\n")
            print(result["answer"])
        print("\nCitations:")
        for citation in result["citations"]:
            print(
                f"  {citation['path']}@{citation['sha'][:8]}:"
                f"{citation['line_start']}-{citation['line_end']} score={citation['score']:.3f}"
            )
        return

    sys.argv = ["query.py"]
    if args.question:
        sys.argv.append(args.question)
    if args.top_k:
        sys.argv += ["--top-k", str(args.top_k)]
    if args.path:
        sys.argv += ["--path", args.path]
    if args.sha:
        sys.argv += ["--sha", args.sha]
    if args.branch:
        sys.argv += ["--branch", args.branch]
    if args.no_llm:
        sys.argv.append("--no-llm")
    from query import main as query_main
    query_main()


def cmd_run_all(args):
    cmd_clone(args)
    cmd_ingest(args)
    if args.question:
        cmd_query(args)


def cmd_bootstrap(args):
    from gitrag.db.session import create_all, session_scope
    from gitrag.ingest.service import IngestionService

    if os.getenv("DATABASE_URL", "sqlite:///./gitrag.db").startswith("sqlite"):
        create_all()
    with session_scope() as session:
        result = IngestionService().bootstrap_repo(session, repo_url=args.repo_url, enqueue=args.enqueue)
    print(
        f"repo_id={result.repo_id} job_id={result.job_id} "
        f"refs={result.refs} commits={result.commits} mirror={result.repo_path}"
    )


def cmd_api(args):
    import uvicorn

    uvicorn.run("gitrag.api.app:app", host=args.host, port=args.port, reload=args.reload)


def cmd_worker(_args):
    from gitrag.workers.ingestion_worker import main as worker_main

    worker_main()


def build_argparser():
    p = argparse.ArgumentParser(prog="git-rag", description="Git-RAG CLI")
    sub = p.add_subparsers(dest="cmd", required=True)

    sub.add_parser("clone", help="Mirror-clone the repo and build commit_graph.json")
    sub.add_parser("ingest", help="Chunk, embed, and upsert the indexed repo into Pinecone")

    q = sub.add_parser("query", help="Ask a question against the indexed repo")
    q.add_argument("question", nargs="?")
    q.add_argument("--top-k", type=int, default=8)
    q.add_argument("--path")
    q.add_argument("--path-prefix")
    q.add_argument("--sha")
    q.add_argument("--branch")
    q.add_argument("--repo-id", help="Use production DB/vector retrieval for this repo id.")
    q.add_argument("--no-llm", action="store_true")

    a = sub.add_parser("run-all", help="Clone, ingest, and (optionally) query in one go")
    a.add_argument("question", nargs="?")
    a.add_argument("--top-k", type=int, default=8)
    a.add_argument("--path")
    a.add_argument("--sha")
    a.add_argument("--branch")
    a.add_argument("--no-llm", action="store_true")

    b = sub.add_parser("bootstrap", help="Production bootstrap: mirror repo, persist refs/DAG, enqueue ingestion")
    b.add_argument("repo_url")
    b.add_argument("--enqueue", action=argparse.BooleanOptionalAction, default=True)

    api = sub.add_parser("api", help="Run the FastAPI service")
    api.add_argument("--host", default="0.0.0.0")
    api.add_argument("--port", type=int, default=8000)
    api.add_argument("--reload", action="store_true")

    sub.add_parser("worker", help="Run the Kafka ingestion worker")

    return p


def main():
    args = build_argparser().parse_args()
    {
        "clone": cmd_clone,
        "ingest": cmd_ingest,
        "query": cmd_query,
        "run-all": cmd_run_all,
        "bootstrap": cmd_bootstrap,
        "api": cmd_api,
        "worker": cmd_worker,
    }[args.cmd](args)


if __name__ == "__main__":
    main()
