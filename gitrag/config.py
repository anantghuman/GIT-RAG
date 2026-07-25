"""Environment-backed configuration for API, workers, and CLI commands."""

from dataclasses import dataclass, field
import os
from pathlib import Path


def _bool(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.lower() in {"1", "true", "yes", "on"}


def _int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None or raw == "":
        return default
    return int(raw)


def _float(name: str, default: float) -> float:
    raw = os.getenv(name)
    if raw is None or raw == "":
        return default
    return float(raw)


@dataclass(frozen=True)
class Settings:
    app_name: str = field(default_factory=lambda: os.getenv("APP_NAME", "git-rag"))
    environment: str = field(default_factory=lambda: os.getenv("ENVIRONMENT", "local"))
    project_dir: str = field(default_factory=lambda: os.getenv("PROJECT_DIR", str(Path.cwd())))
    clone_repo_dir: str = field(default_factory=lambda: os.getenv("CLONE_REPO_DIR", str(Path.cwd() / "repos")))
    local_object_dir: str = field(default_factory=lambda: os.getenv("LOCAL_OBJECT_DIR", str(Path.cwd() / ".gitrag-objects")))

    database_url: str = field(default_factory=lambda: os.getenv("DATABASE_URL", "sqlite:///./gitrag.db"))
    redis_url: str = field(default_factory=lambda: os.getenv("REDIS_URL", "redis://localhost:6379/0"))

    kafka_bootstrap_servers: str = field(default_factory=lambda: os.getenv("KAFKA_BOOTSTRAP_SERVERS", "localhost:9092"))
    kafka_ingestion_topic: str = field(default_factory=lambda: os.getenv("KAFKA_INGESTION_TOPIC", "gitrag.ingestion"))
    kafka_consumer_group: str = field(default_factory=lambda: os.getenv("KAFKA_CONSUMER_GROUP", "gitrag-workers"))

    aws_region: str = field(default_factory=lambda: os.getenv("AWS_REGION", os.getenv("PINECONE_REGION", "us-east-1")))
    s3_bucket: str = field(default_factory=lambda: os.getenv("S3_BUCKET", ""))
    s3_endpoint_url: str = field(default_factory=lambda: os.getenv("S3_ENDPOINT_URL", ""))

    pinecone_api_key: str = field(default_factory=lambda: os.getenv("PINECONE_API_KEY", ""))
    pinecone_index_name: str = field(default_factory=lambda: os.getenv("PINECONE_INDEX_NAME", "git-rag-index"))
    pinecone_cloud: str = field(default_factory=lambda: os.getenv("PINECONE_CLOUD", "aws"))
    pinecone_region: str = field(default_factory=lambda: os.getenv("PINECONE_REGION", "us-east-1"))
    vector_backend: str = field(default_factory=lambda: os.getenv("GITRAG_VECTOR_BACKEND", "pinecone"))

    openai_api_key: str = field(default_factory=lambda: os.getenv("OPENAI_API_KEY", ""))
    openai_embedding_model: str = field(default_factory=lambda: os.getenv("OPENAI_EMBEDDING_MODEL", "text-embedding-3-small"))
    openai_chat_model: str = field(default_factory=lambda: os.getenv("OPENAI_CHAT_MODEL", "gpt-4o-mini"))
    deterministic_embeddings: bool = field(default_factory=lambda: _bool("GITRAG_DETERMINISTIC_EMBEDDINGS", False))

    github_webhook_secret: str = field(default_factory=lambda: os.getenv("GITHUB_WEBHOOK_SECRET", ""))
    github_access_token: str = field(default_factory=lambda: os.getenv("GITHUB_ACCESS_TOKEN", ""))

    snapshot_interval: int = field(default_factory=lambda: _int("SNAPSHOT_INTERVAL", 10))
    snapshot_change_threshold: float = field(default_factory=lambda: _float("SNAPSHOT_CHANGE_THRESHOLD", 0.30))
    embedding_batch_size: int = field(default_factory=lambda: _int("EMBEDDING_BATCH_SIZE", 64))
    vector_upsert_batch_size: int = field(default_factory=lambda: _int("VECTOR_UPSERT_BATCH_SIZE", 100))
    query_cache_ttl_seconds: int = field(default_factory=lambda: _int("QUERY_CACHE_TTL_SECONDS", 300))
    default_top_k: int = field(default_factory=lambda: _int("DEFAULT_TOP_K", 8))
    index_vendor_code: bool = field(default_factory=lambda: _bool("INDEX_VENDOR_CODE", False))


def get_settings() -> Settings:
    return Settings()
