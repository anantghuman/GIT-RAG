# Git-RAG Benchmarks

These scripts are opt-in and are not part of normal unit tests.

## Seed Synthetic Chunks

```bash
GITRAG_VECTOR_BACKEND=memory GITRAG_DETERMINISTIC_EMBEDDINGS=true \
python benchmarks/seed_1m_chunks.py --repo-id bench --chunks 1000000
```

## Query Load

```bash
python benchmarks/query_load.py --url http://localhost:8000/query --repo-id bench --concurrency 50 --requests 5000
```

The target for cached/filter-heavy retrieval is p95 under 100 ms. LLM synthesis is measured separately by passing `include_answer=false` for retrieval-only tests.
