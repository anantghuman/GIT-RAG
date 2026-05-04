"""Single entry point that orchestrates clone -> ingest -> query."""
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


def build_argparser():
    p = argparse.ArgumentParser(prog="git-rag", description="Git-RAG CLI")
    sub = p.add_subparsers(dest="cmd", required=True)

    sub.add_parser("clone", help="Mirror-clone the repo and build commit_graph.json")
    sub.add_parser("ingest", help="Chunk, embed, and upsert the indexed repo into Pinecone")

    q = sub.add_parser("query", help="Ask a question against the indexed repo")
    q.add_argument("question", nargs="?")
    q.add_argument("--top-k", type=int, default=8)
    q.add_argument("--path")
    q.add_argument("--sha")
    q.add_argument("--branch")
    q.add_argument("--no-llm", action="store_true")

    a = sub.add_parser("run-all", help="Clone, ingest, and (optionally) query in one go")
    a.add_argument("question", nargs="?")
    a.add_argument("--top-k", type=int, default=8)
    a.add_argument("--path")
    a.add_argument("--sha")
    a.add_argument("--branch")
    a.add_argument("--no-llm", action="store_true")

    return p


def main():
    args = build_argparser().parse_args()
    {"clone": cmd_clone, "ingest": cmd_ingest, "query": cmd_query, "run-all": cmd_run_all}[args.cmd](args)


if __name__ == "__main__":
    main()
