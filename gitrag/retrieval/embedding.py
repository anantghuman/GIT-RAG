"""Embedding clients with database-backed deduplication support."""

from __future__ import annotations

import hashlib
import math
from typing import Iterable

from sqlalchemy.orm import Session

from gitrag.config import Settings, get_settings
from gitrag.db.models import EmbeddingCache
from gitrag.ids import content_hash, embedding_cache_id


EMBEDDING_DIMENSIONS = {
    "text-embedding-3-small": 1536,
    "text-embedding-3-large": 3072,
    "text-embedding-ada-002": 1536,
}


def deterministic_vector(text: str, dimensions: int = 1536) -> list[float]:
    seed = hashlib.sha256(text.encode("utf-8")).digest()
    values: list[float] = []
    counter = 0
    while len(values) < dimensions:
        digest = hashlib.sha256(seed + counter.to_bytes(4, "big")).digest()
        for idx in range(0, len(digest), 4):
            value = int.from_bytes(digest[idx : idx + 4], "big") / 2**32
            values.append((value * 2.0) - 1.0)
            if len(values) == dimensions:
                break
        counter += 1
    norm = math.sqrt(sum(v * v for v in values)) or 1.0
    return [v / norm for v in values]


class Embedder:
    def __init__(self, settings: Settings | None = None):
        self.settings = settings or get_settings()
        self.model = self.settings.openai_embedding_model
        self.dimensions = EMBEDDING_DIMENSIONS.get(self.model, 1536)
        self._client = None
        self._local_vectors: dict[tuple[str, str], list[float]] = {}

    def _openai_client(self):
        if self._client is None:
            if not self.settings.openai_api_key:
                raise RuntimeError("OPENAI_API_KEY is required unless deterministic embeddings are enabled")
            from openai import OpenAI

            self._client = OpenAI(api_key=self.settings.openai_api_key)
        return self._client

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        if self.settings.deterministic_embeddings:
            return [deterministic_vector(text or " ", self.dimensions) for text in texts]
        client = self._openai_client()
        out: list[list[float]] = []
        for i in range(0, len(texts), self.settings.embedding_batch_size):
            batch = [text if text else " " for text in texts[i : i + self.settings.embedding_batch_size]]
            resp = client.embeddings.create(model=self.model, input=batch)
            out.extend([row.embedding for row in resp.data])
        return out

    def embed_query(self, text: str) -> list[float]:
        return self.embed_texts([text])[0]

    def embed_with_cache(self, session: Session, contents: Iterable[str]) -> dict[str, list[float]]:
        unique = {content_hash(content): content for content in contents}
        vectors: dict[str, list[float]] = {}

        for hash_value in list(unique):
            cached = self._local_vectors.get((hash_value, self.model))
            if cached is not None:
                vectors[hash_value] = cached

        lookup_hashes = [hash_value for hash_value in unique if hash_value not in vectors]
        cached_rows = (
            session.query(EmbeddingCache)
            .filter(EmbeddingCache.content_hash.in_(lookup_hashes), EmbeddingCache.model == self.model)
            .all()
            if lookup_hashes
            else []
        )
        for row in cached_rows:
            if row.vector_json:
                vectors[row.content_hash] = list(row.vector_json)
                self._local_vectors[(row.content_hash, self.model)] = vectors[row.content_hash]
        missing = [(hash_value, text) for hash_value, text in unique.items() if hash_value not in vectors]
        if missing:
            generated = self.embed_texts([text for _, text in missing])
            for (hash_value, _), vector in zip(missing, generated):
                vectors[hash_value] = vector
                self._local_vectors[(hash_value, self.model)] = vector
                session.merge(
                    EmbeddingCache(
                        id=embedding_cache_id(hash_value, self.model),
                        content_hash=hash_value,
                        model=self.model,
                        vector_json=vector,
                    )
                )
        return vectors
