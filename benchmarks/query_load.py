"""Simple async load generator for retrieval p95 checks."""

from __future__ import annotations

import argparse
import asyncio
import statistics
from time import perf_counter

import httpx


async def one_request(client: httpx.AsyncClient, url: str, repo_id: str, idx: int) -> float:
    start = perf_counter()
    response = await client.post(
        url,
        json={
            "repo_id": repo_id,
            "question": f"Where is symbol {idx % 1000} implemented?",
            "branch": "main",
            "top_k": 8,
            "include_answer": False,
        },
    )
    response.raise_for_status()
    return (perf_counter() - start) * 1000


async def run(url: str, repo_id: str, concurrency: int, requests: int) -> None:
    latencies: list[float] = []
    sem = asyncio.Semaphore(concurrency)
    async with httpx.AsyncClient(timeout=30) as client:
        async def guarded(i: int) -> None:
            async with sem:
                latencies.append(await one_request(client, url, repo_id, i))

        await asyncio.gather(*(guarded(i) for i in range(requests)))
    p95 = statistics.quantiles(latencies, n=100)[94]
    print(f"requests={requests} concurrency={concurrency} p50={statistics.median(latencies):.2f}ms p95={p95:.2f}ms")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", default="http://localhost:8000/query")
    parser.add_argument("--repo-id", default="bench")
    parser.add_argument("--concurrency", type=int, default=50)
    parser.add_argument("--requests", type=int, default=5000)
    args = parser.parse_args()
    asyncio.run(run(args.url, args.repo_id, args.concurrency, args.requests))


if __name__ == "__main__":
    main()
