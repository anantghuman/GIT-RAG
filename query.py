"""Natural-language RAG query over the indexed git history."""
import argparse
import os
import sys

from dotenv import load_dotenv
from openai import OpenAI

from embeddings import embed_query
from pinecone_setup import setup_vector_db

load_dotenv()


SYSTEM_PROMPT = """You answer questions about a software repository using ONLY the provided
context snippets. Each snippet has a SHA, file path, and line range. Cite each fact
inline as [path@sha:lines]. If the context is insufficient, say so. Be concise."""


def search(index, query_text, top_k=8, sha=None, path=None, branch=None):
    vec = embed_query(query_text)
    pinecone_filter = {}
    if sha:
        pinecone_filter["sha"] = sha
    if path:
        pinecone_filter["path"] = path
    if branch:
        pinecone_filter["branches"] = {"$in": [branch]}
    kwargs = {"vector": vec, "top_k": top_k, "include_metadata": True}
    if pinecone_filter:
        kwargs["filter"] = pinecone_filter
    return index.query(**kwargs)


def format_context(matches):
    blocks = []
    for i, m in enumerate(matches, 1):
        md = m.metadata or {}
        sha = md.get("sha", "")[:8]
        path = md.get("path", "?")
        ls, le = md.get("line_start", 0), md.get("line_end", 0)
        msg = (md.get("commit_message") or "")[:120]
        kind = md.get("type", "code")
        content = md.get("content", "")
        blocks.append(
            f"[{i}] {path}@{sha}:{ls}-{le}  ({kind})  msg=\"{msg}\"\n"
            f"score={m.score:.3f}\n"
            f"---\n{content}\n"
        )
    return "\n".join(blocks)


def answer(query_text, matches, model=None):
    client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
    model = model or os.getenv("OPENAI_CHAT_MODEL", "gpt-4o-mini")
    context = format_context(matches)
    user = f"Question: {query_text}\n\nContext:\n{context}"
    resp = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user},
        ],
        temperature=0.2,
    )
    return resp.choices[0].message.content


def print_citations(matches):
    print("\nCitations:")
    for i, m in enumerate(matches, 1):
        md = m.metadata or {}
        sha = md.get("sha", "")
        path = md.get("path", "?")
        ls, le = md.get("line_start", 0), md.get("line_end", 0)
        repo_user = os.getenv("USER", "")
        repo_name = os.getenv("REPO", "")
        link = ""
        if repo_user and repo_name and sha:
            link = f"  https://github.com/{repo_user}/{repo_name}/blob/{sha}/{path}#L{ls + 1}-L{le + 1}"
        print(f"  [{i}] {path}@{sha[:8]}:{ls}-{le}  score={m.score:.3f}{link}")


def main():
    parser = argparse.ArgumentParser(description="Query the Git-RAG index.")
    parser.add_argument("question", nargs="?", help="Natural language question.")
    parser.add_argument("--top-k", type=int, default=8)
    parser.add_argument("--sha", help="Restrict to a specific commit SHA.")
    parser.add_argument("--path", help="Restrict to a specific file path.")
    parser.add_argument("--branch", help="Restrict to a specific branch.")
    parser.add_argument(
        "--no-llm",
        action="store_true",
        help="Skip LLM synthesis; just print the retrieved snippets.",
    )
    args = parser.parse_args()

    if not os.getenv("OPENAI_API_KEY"):
        print("OPENAI_API_KEY is not set in .env.", file=sys.stderr)
        sys.exit(1)
    if not os.getenv("PINECONE_API_KEY"):
        print("PINECONE_API_KEY is not set in .env.", file=sys.stderr)
        sys.exit(1)

    question = args.question or input("Question: ").strip()
    if not question:
        print("No question provided.", file=sys.stderr)
        sys.exit(1)

    index = setup_vector_db()
    results = search(index, question, top_k=args.top_k, sha=args.sha, path=args.path, branch=args.branch)
    matches = results.matches if hasattr(results, "matches") else results.get("matches", [])

    if not matches:
        print("No results found. Has the index been populated?")
        return

    if args.no_llm:
        print(format_context(matches))
        print_citations(matches)
        return

    reply = answer(question, matches)
    print("\nAnswer:\n")
    print(reply)
    print_citations(matches)


if __name__ == "__main__":
    main()
