"""Vector-store abstraction and Pinecone implementation."""

from __future__ import annotations

from dataclasses import dataclass
import math

from gitrag.config import Settings, get_settings
from gitrag.retrieval.embedding import EMBEDDING_DIMENSIONS


@dataclass(frozen=True)
class VectorMatch:
    id: str
    score: float
    metadata: dict


class VectorStore:
    def upsert(self, vectors: list[tuple[str, list[float], dict]]) -> None:
        raise NotImplementedError

    def query(self, vector: list[float], *, top_k: int, filters: dict | None = None) -> list[VectorMatch]:
        raise NotImplementedError


class PineconeVectorStore(VectorStore):
    def __init__(self, settings: Settings | None = None):
        self.settings = settings or get_settings()
        self._index = None

    def _get_index(self):
        if self._index is not None:
            return self._index
        if not self.settings.pinecone_api_key:
            raise RuntimeError("PINECONE_API_KEY is required for Pinecone vector search")
        from pinecone import Pinecone, ServerlessSpec

        pc = Pinecone(api_key=self.settings.pinecone_api_key)
        model = self.settings.openai_embedding_model
        dimension = EMBEDDING_DIMENSIONS.get(model, 1536)
        existing = [idx.name for idx in pc.list_indexes()]
        if self.settings.pinecone_index_name not in existing:
            pc.create_index(
                name=self.settings.pinecone_index_name,
                dimension=dimension,
                metric="cosine",
                spec=ServerlessSpec(cloud=self.settings.pinecone_cloud, region=self.settings.pinecone_region),
            )
        self._index = pc.Index(self.settings.pinecone_index_name)
        return self._index

    def upsert(self, vectors: list[tuple[str, list[float], dict]]) -> None:
        if not vectors:
            return
        index = self._get_index()
        batch_size = self.settings.vector_upsert_batch_size
        for i in range(0, len(vectors), batch_size):
            batch = [
                {"id": vector_id, "values": values, "metadata": metadata}
                for vector_id, values, metadata in vectors[i : i + batch_size]
            ]
            index.upsert(vectors=batch)

    def query(self, vector: list[float], *, top_k: int, filters: dict | None = None) -> list[VectorMatch]:
        kwargs = {"vector": vector, "top_k": top_k, "include_metadata": True}
        if filters:
            kwargs["filter"] = filters
        result = self._get_index().query(**kwargs)
        matches = result.matches if hasattr(result, "matches") else result.get("matches", [])
        return [VectorMatch(id=m.id, score=float(m.score), metadata=m.metadata or {}) for m in matches]


class MemoryVectorStore(VectorStore):
    """Small cosine-similarity vector store used for tests and local demos."""

    def __init__(self):
        self.vectors: dict[str, tuple[list[float], dict]] = {}

    def upsert(self, vectors: list[tuple[str, list[float], dict]]) -> None:
        for vector_id, values, metadata in vectors:
            self.vectors[vector_id] = (values, metadata)

    def query(self, vector: list[float], *, top_k: int, filters: dict | None = None) -> list[VectorMatch]:
        scored: list[VectorMatch] = []
        for vector_id, (values, metadata) in self.vectors.items():
            if filters and not _metadata_matches(metadata, filters):
                continue
            denom = (math.sqrt(sum(v * v for v in vector)) or 1.0) * (math.sqrt(sum(v * v for v in values)) or 1.0)
            score = sum(a * b for a, b in zip(vector, values)) / denom
            scored.append(VectorMatch(id=vector_id, score=score, metadata=metadata))
        return sorted(scored, key=lambda item: item.score, reverse=True)[:top_k]


def _metadata_matches(metadata: dict, filters: dict) -> bool:
    for key, expected in filters.items():
        actual = metadata.get(key)
        if isinstance(expected, dict) and "$in" in expected:
            candidates = expected["$in"]
            if isinstance(actual, list):
                if not set(actual) & set(candidates):
                    return False
            elif actual not in candidates:
                return False
        elif actual != expected:
            return False
    return True


_memory_store = MemoryVectorStore()


def get_vector_store(settings: Settings | None = None) -> VectorStore:
    settings = settings or get_settings()
    if settings.vector_backend == "memory":
        return _memory_store
    return PineconeVectorStore(settings)
