"""FastAPI request and response schemas."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class BootstrapRequest(BaseModel):
    repo_url: str = Field(..., examples=["https://github.com/org/repo.git"])
    enqueue: bool = True


class BootstrapResponse(BaseModel):
    repo_id: str
    job_id: str
    repo_path: str
    refs: int
    commits: int


class QueryRequest(BaseModel):
    repo_id: str
    question: str
    branch: str | None = None
    sha: str | None = None
    path_prefix: str | None = None
    top_k: int = Field(default=8, ge=1, le=50)
    include_answer: bool = True


class WebhookAccepted(BaseModel):
    job_id: str
    repo_id: str
    status: str


class JobResponse(BaseModel):
    id: str
    repo_id: str
    job_type: str
    status: str
    ref: str | None = None
    before_sha: str | None = None
    after_sha: str | None = None
    error: str | None = None
    stats: Any = None


class BranchResponse(BaseModel):
    repo_id: str
    branches: list[dict[str, str]]
