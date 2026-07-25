"""Relational metadata schema for branch-aware Git-RAG."""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    JSON,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    pass


class Repository(Base):
    __tablename__ = "repositories"

    id: Mapped[str] = mapped_column(String(80), primary_key=True)
    url: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    local_path: Mapped[str] = mapped_column(Text, nullable=False)
    default_branch: Mapped[str | None] = mapped_column(String(255))
    indexed_generation: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False)

    refs: Mapped[list["RepositoryRef"]] = relationship(back_populates="repository", cascade="all, delete-orphan")


class RepositoryRef(Base):
    __tablename__ = "repository_refs"
    __table_args__ = (UniqueConstraint("repo_id", "name", name="uq_repository_refs_repo_name"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    repo_id: Mapped[str] = mapped_column(ForeignKey("repositories.id", ondelete="CASCADE"), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    ref_type: Mapped[str] = mapped_column(String(40), nullable=False)
    sha: Mapped[str] = mapped_column(String(40), nullable=False)
    indexed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    repository: Mapped[Repository] = relationship(back_populates="refs")


class Commit(Base):
    __tablename__ = "commits"
    __table_args__ = (
        Index("ix_commits_repo_time", "repo_id", "commit_time"),
        Index("ix_commits_repo_depth", "repo_id", "depth"),
    )

    repo_id: Mapped[str] = mapped_column(ForeignKey("repositories.id", ondelete="CASCADE"), primary_key=True)
    sha: Mapped[str] = mapped_column(String(40), primary_key=True)
    author: Mapped[str] = mapped_column(Text, default="", nullable=False)
    email: Mapped[str] = mapped_column(Text, default="", nullable=False)
    message: Mapped[str] = mapped_column(Text, default="", nullable=False)
    commit_time: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    is_merge: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    depth: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    refs_json: Mapped[dict | list | None] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)


class CommitParent(Base):
    __tablename__ = "commit_parents"

    repo_id: Mapped[str] = mapped_column(ForeignKey("repositories.id", ondelete="CASCADE"), primary_key=True)
    child_sha: Mapped[str] = mapped_column(String(40), primary_key=True)
    parent_sha: Mapped[str] = mapped_column(String(40), primary_key=True)
    position: Mapped[int] = mapped_column(Integer, default=0, nullable=False)


class File(Base):
    __tablename__ = "files"
    __table_args__ = (Index("ix_files_repo_path", "repo_id", "path"),)

    id: Mapped[str] = mapped_column(String(48), primary_key=True)
    repo_id: Mapped[str] = mapped_column(ForeignKey("repositories.id", ondelete="CASCADE"), nullable=False)
    path: Mapped[str] = mapped_column(Text, nullable=False)
    language: Mapped[str | None] = mapped_column(String(80))
    latest_sha: Mapped[str | None] = mapped_column(String(40))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False)


class FileVersion(Base):
    __tablename__ = "file_versions"
    __table_args__ = (
        UniqueConstraint("repo_id", "sha", "path", name="uq_file_versions_repo_sha_path"),
        Index("ix_file_versions_repo_path", "repo_id", "path"),
    )

    id: Mapped[str] = mapped_column(String(48), primary_key=True)
    repo_id: Mapped[str] = mapped_column(ForeignKey("repositories.id", ondelete="CASCADE"), nullable=False)
    file_id: Mapped[str] = mapped_column(ForeignKey("files.id", ondelete="CASCADE"), nullable=False)
    sha: Mapped[str] = mapped_column(String(40), nullable=False)
    path: Mapped[str] = mapped_column(Text, nullable=False)
    parent_sha: Mapped[str | None] = mapped_column(String(40))
    change_type: Mapped[str] = mapped_column(String(20), default="M", nullable=False)
    storage_kind: Mapped[str] = mapped_column(String(40), nullable=False)
    s3_key: Mapped[str | None] = mapped_column(Text)
    content_hash: Mapped[str | None] = mapped_column(String(64))
    size_bytes: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    compressed_bytes: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)


class Symbol(Base):
    __tablename__ = "symbols"
    __table_args__ = (Index("ix_symbols_repo_path_name", "repo_id", "path", "name"),)

    id: Mapped[str] = mapped_column(String(48), primary_key=True)
    repo_id: Mapped[str] = mapped_column(ForeignKey("repositories.id", ondelete="CASCADE"), nullable=False)
    file_id: Mapped[str] = mapped_column(ForeignKey("files.id", ondelete="CASCADE"), nullable=False)
    path: Mapped[str] = mapped_column(Text, nullable=False)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    kind: Mapped[str] = mapped_column(String(80), nullable=False)
    language: Mapped[str | None] = mapped_column(String(80))
    first_sha: Mapped[str] = mapped_column(String(40), nullable=False)
    last_sha: Mapped[str] = mapped_column(String(40), nullable=False)


class Chunk(Base):
    __tablename__ = "chunks"
    __table_args__ = (
        Index("ix_chunks_repo_sha", "repo_id", "sha"),
        Index("ix_chunks_repo_path", "repo_id", "path"),
        Index("ix_chunks_content_hash", "content_hash"),
    )

    id: Mapped[str] = mapped_column(String(48), primary_key=True)
    repo_id: Mapped[str] = mapped_column(ForeignKey("repositories.id", ondelete="CASCADE"), nullable=False)
    sha: Mapped[str] = mapped_column(String(40), nullable=False)
    file_id: Mapped[str] = mapped_column(ForeignKey("files.id", ondelete="CASCADE"), nullable=False)
    symbol_id: Mapped[str | None] = mapped_column(ForeignKey("symbols.id", ondelete="SET NULL"))
    path: Mapped[str] = mapped_column(Text, nullable=False)
    language: Mapped[str | None] = mapped_column(String(80))
    chunk_type: Mapped[str] = mapped_column(String(40), nullable=False)
    symbol_name: Mapped[str | None] = mapped_column(Text)
    line_start: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    line_end: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    embedding_model: Mapped[str] = mapped_column(String(120), nullable=False)
    vector_id: Mapped[str] = mapped_column(String(80), nullable=False, unique=True)
    commit_time: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    metadata_json: Mapped[dict | list | None] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)


class ChunkRef(Base):
    __tablename__ = "chunk_refs"
    __table_args__ = (Index("ix_chunk_refs_repo_ref", "repo_id", "ref_name"),)

    chunk_id: Mapped[str] = mapped_column(ForeignKey("chunks.id", ondelete="CASCADE"), primary_key=True)
    repo_id: Mapped[str] = mapped_column(ForeignKey("repositories.id", ondelete="CASCADE"), primary_key=True)
    ref_name: Mapped[str] = mapped_column(String(255), primary_key=True)


class IngestionJob(Base):
    __tablename__ = "ingestion_jobs"
    __table_args__ = (
        UniqueConstraint("repo_id", "delivery_id", name="uq_ingestion_jobs_repo_delivery"),
        Index("ix_ingestion_jobs_repo_status", "repo_id", "status"),
    )

    id: Mapped[str] = mapped_column(String(48), primary_key=True)
    repo_id: Mapped[str] = mapped_column(ForeignKey("repositories.id", ondelete="CASCADE"), nullable=False)
    job_type: Mapped[str] = mapped_column(String(40), nullable=False)
    status: Mapped[str] = mapped_column(String(40), default="queued", nullable=False)
    ref: Mapped[str | None] = mapped_column(String(255))
    before_sha: Mapped[str | None] = mapped_column(String(40))
    after_sha: Mapped[str | None] = mapped_column(String(40))
    delivery_id: Mapped[str | None] = mapped_column(String(120))
    error: Mapped[str | None] = mapped_column(Text)
    stats_json: Mapped[dict | list | None] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False)


class EmbeddingCache(Base):
    __tablename__ = "embedding_cache"

    id: Mapped[str] = mapped_column(String(48), primary_key=True)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    model: Mapped[str] = mapped_column(String(120), nullable=False)
    vector_json: Mapped[list | None] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)


class SnapshotManifest(Base):
    __tablename__ = "snapshot_manifests"
    __table_args__ = (Index("ix_snapshot_manifests_repo_path", "repo_id", "path"),)

    id: Mapped[str] = mapped_column(String(48), primary_key=True)
    repo_id: Mapped[str] = mapped_column(ForeignKey("repositories.id", ondelete="CASCADE"), nullable=False)
    file_id: Mapped[str] = mapped_column(ForeignKey("files.id", ondelete="CASCADE"), nullable=False)
    sha: Mapped[str] = mapped_column(String(40), nullable=False)
    parent_sha: Mapped[str | None] = mapped_column(String(40))
    path: Mapped[str] = mapped_column(Text, nullable=False)
    kind: Mapped[str] = mapped_column(String(40), nullable=False)
    s3_key: Mapped[str] = mapped_column(Text, nullable=False)
    content_hash: Mapped[str | None] = mapped_column(String(64))
    naive_bytes: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    stored_bytes: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
