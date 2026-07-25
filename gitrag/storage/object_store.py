"""S3 object storage with a local filesystem fallback for development/tests."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import gzip
import os

from gitrag.config import Settings, get_settings


@dataclass(frozen=True)
class StoredObject:
    key: str
    raw_bytes: int
    stored_bytes: int


class ObjectStore:
    def __init__(self, settings: Settings | None = None):
        self.settings = settings or get_settings()

    def _compress(self, data: bytes) -> bytes:
        try:
            import zstandard as zstd

            return zstd.ZstdCompressor(level=6).compress(data)
        except Exception:
            return gzip.compress(data, compresslevel=6)

    def put_text(self, key: str, text: str, *, compress: bool = True) -> StoredObject:
        raw = text.encode("utf-8")
        body = self._compress(raw) if compress else raw
        if self.settings.s3_bucket:
            self._put_s3(key, body)
        else:
            target = Path(self.settings.local_object_dir) / key
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(body)
        return StoredObject(key=key, raw_bytes=len(raw), stored_bytes=len(body))

    def _put_s3(self, key: str, body: bytes) -> None:
        import boto3

        kwargs = {"region_name": self.settings.aws_region}
        if self.settings.s3_endpoint_url:
            kwargs["endpoint_url"] = self.settings.s3_endpoint_url
        client = boto3.client("s3", **kwargs)
        client.put_object(Bucket=self.settings.s3_bucket, Key=key, Body=body)


def path_hash(path: str) -> str:
    from gitrag.ids import stable_hash

    return stable_hash(path, 16)


def snapshot_key(repo_id: str, sha: str, path: str) -> str:
    return f"repos/{repo_id}/snapshots/{path_hash(path)}/{sha}.txt.zst"


def diff_key(repo_id: str, parent_sha: str, sha: str, path: str) -> str:
    return f"repos/{repo_id}/diffs/{path_hash(path)}/{parent_sha}_{sha}.patch.zst"
