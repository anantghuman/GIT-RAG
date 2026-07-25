"""initial metadata schema

Revision ID: 202607230001
Revises:
Create Date: 2026-07-23 00:01:00
"""

from alembic import op
import sqlalchemy as sa

revision = "202607230001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "repositories",
        sa.Column("id", sa.String(length=80), primary_key=True),
        sa.Column("url", sa.Text(), nullable=False, unique=True),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("local_path", sa.Text(), nullable=False),
        sa.Column("default_branch", sa.String(length=255)),
        sa.Column("indexed_generation", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "repository_refs",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("repo_id", sa.String(length=80), sa.ForeignKey("repositories.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("ref_type", sa.String(length=40), nullable=False),
        sa.Column("sha", sa.String(length=40), nullable=False),
        sa.Column("indexed_at", sa.DateTime(timezone=True)),
        sa.UniqueConstraint("repo_id", "name", name="uq_repository_refs_repo_name"),
    )
    op.create_table(
        "commits",
        sa.Column("repo_id", sa.String(length=80), sa.ForeignKey("repositories.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("sha", sa.String(length=40), primary_key=True),
        sa.Column("author", sa.Text(), nullable=False, server_default=""),
        sa.Column("email", sa.Text(), nullable=False, server_default=""),
        sa.Column("message", sa.Text(), nullable=False, server_default=""),
        sa.Column("commit_time", sa.DateTime(timezone=True)),
        sa.Column("is_merge", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("depth", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("refs_json", sa.JSON()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_commits_repo_time", "commits", ["repo_id", "commit_time"])
    op.create_index("ix_commits_repo_depth", "commits", ["repo_id", "depth"])
    op.create_table(
        "commit_parents",
        sa.Column("repo_id", sa.String(length=80), sa.ForeignKey("repositories.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("child_sha", sa.String(length=40), primary_key=True),
        sa.Column("parent_sha", sa.String(length=40), primary_key=True),
        sa.Column("position", sa.Integer(), nullable=False, server_default="0"),
    )
    op.create_table(
        "files",
        sa.Column("id", sa.String(length=48), primary_key=True),
        sa.Column("repo_id", sa.String(length=80), sa.ForeignKey("repositories.id", ondelete="CASCADE"), nullable=False),
        sa.Column("path", sa.Text(), nullable=False),
        sa.Column("language", sa.String(length=80)),
        sa.Column("latest_sha", sa.String(length=40)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_files_repo_path", "files", ["repo_id", "path"])
    op.create_table(
        "file_versions",
        sa.Column("id", sa.String(length=48), primary_key=True),
        sa.Column("repo_id", sa.String(length=80), sa.ForeignKey("repositories.id", ondelete="CASCADE"), nullable=False),
        sa.Column("file_id", sa.String(length=48), sa.ForeignKey("files.id", ondelete="CASCADE"), nullable=False),
        sa.Column("sha", sa.String(length=40), nullable=False),
        sa.Column("path", sa.Text(), nullable=False),
        sa.Column("parent_sha", sa.String(length=40)),
        sa.Column("change_type", sa.String(length=20), nullable=False),
        sa.Column("storage_kind", sa.String(length=40), nullable=False),
        sa.Column("s3_key", sa.Text()),
        sa.Column("content_hash", sa.String(length=64)),
        sa.Column("size_bytes", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("compressed_bytes", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("repo_id", "sha", "path", name="uq_file_versions_repo_sha_path"),
    )
    op.create_index("ix_file_versions_repo_path", "file_versions", ["repo_id", "path"])
    op.create_table(
        "symbols",
        sa.Column("id", sa.String(length=48), primary_key=True),
        sa.Column("repo_id", sa.String(length=80), sa.ForeignKey("repositories.id", ondelete="CASCADE"), nullable=False),
        sa.Column("file_id", sa.String(length=48), sa.ForeignKey("files.id", ondelete="CASCADE"), nullable=False),
        sa.Column("path", sa.Text(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("kind", sa.String(length=80), nullable=False),
        sa.Column("language", sa.String(length=80)),
        sa.Column("first_sha", sa.String(length=40), nullable=False),
        sa.Column("last_sha", sa.String(length=40), nullable=False),
    )
    op.create_index("ix_symbols_repo_path_name", "symbols", ["repo_id", "path", "name"])
    op.create_table(
        "chunks",
        sa.Column("id", sa.String(length=48), primary_key=True),
        sa.Column("repo_id", sa.String(length=80), sa.ForeignKey("repositories.id", ondelete="CASCADE"), nullable=False),
        sa.Column("sha", sa.String(length=40), nullable=False),
        sa.Column("file_id", sa.String(length=48), sa.ForeignKey("files.id", ondelete="CASCADE"), nullable=False),
        sa.Column("symbol_id", sa.String(length=48), sa.ForeignKey("symbols.id", ondelete="SET NULL")),
        sa.Column("path", sa.Text(), nullable=False),
        sa.Column("language", sa.String(length=80)),
        sa.Column("chunk_type", sa.String(length=40), nullable=False),
        sa.Column("symbol_name", sa.Text()),
        sa.Column("line_start", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("line_end", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("content_hash", sa.String(length=64), nullable=False),
        sa.Column("embedding_model", sa.String(length=120), nullable=False),
        sa.Column("vector_id", sa.String(length=80), nullable=False, unique=True),
        sa.Column("commit_time", sa.DateTime(timezone=True)),
        sa.Column("metadata_json", sa.JSON()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_chunks_repo_sha", "chunks", ["repo_id", "sha"])
    op.create_index("ix_chunks_repo_path", "chunks", ["repo_id", "path"])
    op.create_index("ix_chunks_content_hash", "chunks", ["content_hash"])
    op.create_table(
        "chunk_refs",
        sa.Column("chunk_id", sa.String(length=48), sa.ForeignKey("chunks.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("repo_id", sa.String(length=80), sa.ForeignKey("repositories.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("ref_name", sa.String(length=255), primary_key=True),
    )
    op.create_index("ix_chunk_refs_repo_ref", "chunk_refs", ["repo_id", "ref_name"])
    op.create_table(
        "ingestion_jobs",
        sa.Column("id", sa.String(length=48), primary_key=True),
        sa.Column("repo_id", sa.String(length=80), sa.ForeignKey("repositories.id", ondelete="CASCADE"), nullable=False),
        sa.Column("job_type", sa.String(length=40), nullable=False),
        sa.Column("status", sa.String(length=40), nullable=False, server_default="queued"),
        sa.Column("ref", sa.String(length=255)),
        sa.Column("before_sha", sa.String(length=40)),
        sa.Column("after_sha", sa.String(length=40)),
        sa.Column("delivery_id", sa.String(length=120)),
        sa.Column("error", sa.Text()),
        sa.Column("stats_json", sa.JSON()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("repo_id", "delivery_id", name="uq_ingestion_jobs_repo_delivery"),
    )
    op.create_index("ix_ingestion_jobs_repo_status", "ingestion_jobs", ["repo_id", "status"])
    op.create_table(
        "embedding_cache",
        sa.Column("id", sa.String(length=48), primary_key=True),
        sa.Column("content_hash", sa.String(length=64), nullable=False),
        sa.Column("model", sa.String(length=120), nullable=False),
        sa.Column("vector_json", sa.JSON()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "snapshot_manifests",
        sa.Column("id", sa.String(length=48), primary_key=True),
        sa.Column("repo_id", sa.String(length=80), sa.ForeignKey("repositories.id", ondelete="CASCADE"), nullable=False),
        sa.Column("file_id", sa.String(length=48), sa.ForeignKey("files.id", ondelete="CASCADE"), nullable=False),
        sa.Column("sha", sa.String(length=40), nullable=False),
        sa.Column("parent_sha", sa.String(length=40)),
        sa.Column("path", sa.Text(), nullable=False),
        sa.Column("kind", sa.String(length=40), nullable=False),
        sa.Column("s3_key", sa.Text(), nullable=False),
        sa.Column("content_hash", sa.String(length=64)),
        sa.Column("naive_bytes", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("stored_bytes", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_snapshot_manifests_repo_path", "snapshot_manifests", ["repo_id", "path"])


def downgrade() -> None:
    op.drop_index("ix_snapshot_manifests_repo_path", table_name="snapshot_manifests")
    op.drop_table("snapshot_manifests")
    op.drop_table("embedding_cache")
    op.drop_index("ix_ingestion_jobs_repo_status", table_name="ingestion_jobs")
    op.drop_table("ingestion_jobs")
    op.drop_index("ix_chunk_refs_repo_ref", table_name="chunk_refs")
    op.drop_table("chunk_refs")
    op.drop_index("ix_chunks_content_hash", table_name="chunks")
    op.drop_index("ix_chunks_repo_path", table_name="chunks")
    op.drop_index("ix_chunks_repo_sha", table_name="chunks")
    op.drop_table("chunks")
    op.drop_index("ix_symbols_repo_path_name", table_name="symbols")
    op.drop_table("symbols")
    op.drop_index("ix_file_versions_repo_path", table_name="file_versions")
    op.drop_table("file_versions")
    op.drop_index("ix_files_repo_path", table_name="files")
    op.drop_table("files")
    op.drop_table("commit_parents")
    op.drop_index("ix_commits_repo_depth", table_name="commits")
    op.drop_index("ix_commits_repo_time", table_name="commits")
    op.drop_table("commits")
    op.drop_table("repository_refs")
    op.drop_table("repositories")
