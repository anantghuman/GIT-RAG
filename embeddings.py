import os
from openai import OpenAI

_client = None


def _get_client():
    global _client
    if _client is None:
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            raise RuntimeError("OPENAI_API_KEY is not set")
        _client = OpenAI(api_key=api_key)
    return _client


def _model():
    return os.getenv("OPENAI_EMBEDDING_MODEL", "text-embedding-3-small")


def embed_texts(texts, batch_size=64):
    """Embed a list of strings, returning a list of embedding vectors."""
    client = _get_client()
    model = _model()
    out = []
    for i in range(0, len(texts), batch_size):
        batch = [t if t else " " for t in texts[i : i + batch_size]]
        resp = client.embeddings.create(model=model, input=batch)
        out.extend([d.embedding for d in resp.data])
    return out


def embed_query(text):
    return embed_texts([text])[0]


def generate_embeddings(chunks):
    """Attach an `embedding` field to each chunk dict."""
    texts = [c.get("content", "") for c in chunks]
    vectors = embed_texts(texts)
    for chunk, vec in zip(chunks, vectors):
        chunk["embedding"] = vec
    return chunks


def upsert_embeddings(index, embeddings_with_metadata):
    """Batch upsert embeddings to Pinecone with DAG metadata."""
    batch_size = 100
    total = len(embeddings_with_metadata)
    successful = 0

    for i in range(0, total, batch_size):
        batch = embeddings_with_metadata[i : i + batch_size]
        vectors = []
        for chunk in batch:
            if "embedding" not in chunk:
                continue
            vector_id = f"{chunk['sha'][:8]}_{chunk['path']}_{chunk.get('line_start', 0)}"
            vector_id = vector_id.replace("/", "_").replace(".", "_").replace(" ", "_")
            metadata = {
                "sha": chunk["sha"],
                "path": chunk["path"],
                "language": chunk.get("language", ""),
                "content": (chunk.get("content") or "")[:2000],
                "line_start": chunk.get("line_start", 0),
                "line_end": chunk.get("line_end", 0),
                "type": chunk.get("type", "code"),
                "branches": chunk.get("branches", []) or [],
                "timestamp": str(chunk.get("timestamp", "")),
                "commit_message": (chunk.get("commit_message", "") or "")[:500],
                "parents": chunk.get("parents", []) or [],
                "depth": chunk.get("depth", 0),
                "is_merge": bool(chunk.get("is_merge", False)),
            }
            vectors.append({"id": vector_id, "values": chunk["embedding"], "metadata": metadata})

        if not vectors:
            continue

        try:
            index.upsert(vectors=vectors)
            successful += len(vectors)
            print(f"  upserted {successful}/{total}")
        except Exception as e:
            print(f"  upsert error (batch {i // batch_size}): {e}")

    print(f"Upserted {successful} vectors total")
    return successful
