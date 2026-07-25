"""Redis-backed query response caching."""

from __future__ import annotations

import json

from gitrag.config import Settings, get_settings


class QueryCache:
    def __init__(self, settings: Settings | None = None):
        self.settings = settings or get_settings()
        self._client = None

    def _redis(self):
        if self._client is not None:
            return self._client
        try:
            import redis

            self._client = redis.Redis.from_url(self.settings.redis_url, decode_responses=True)
            self._client.ping()
        except Exception:
            self._client = False
        return self._client

    def get(self, key: str) -> dict | None:
        client = self._redis()
        if not client:
            return None
        raw = client.get(key)
        return json.loads(raw) if raw else None

    def set(self, key: str, value: dict, ttl_seconds: int | None = None) -> None:
        client = self._redis()
        if not client:
            return
        client.setex(key, ttl_seconds or self.settings.query_cache_ttl_seconds, json.dumps(value))
