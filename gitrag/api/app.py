"""FastAPI service for ingestion control, GitHub webhooks, and branch-aware queries."""

from __future__ import annotations

import json

from fastapi import Depends, FastAPI, Header, HTTPException, Request, Response
from sqlalchemy import text
from sqlalchemy.orm import Session

from gitrag.api.schemas import (
    BootstrapRequest,
    BootstrapResponse,
    BranchResponse,
    JobResponse,
    QueryRequest,
    WebhookAccepted,
)
from gitrag.api.security import verify_github_signature
from gitrag.config import Settings, get_settings
from gitrag.db.models import IngestionJob, RepositoryRef
from gitrag.db.session import create_all, get_session_factory
from gitrag.ingest.service import IngestionService
from gitrag.queue.kafka import KafkaPublisher
from gitrag.retrieval.service import QueryService


def get_db():
    session = get_session_factory()()
    try:
        yield session
    finally:
        session.close()


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    app = FastAPI(title="Git-RAG", version="0.1.0")

    @app.on_event("startup")
    def _startup() -> None:
        if settings.database_url.startswith("sqlite"):
            create_all()

    @app.get("/healthz")
    def healthz() -> dict:
        return {"status": "ok", "service": settings.app_name}

    @app.get("/readyz")
    def readyz(session: Session = Depends(get_db)) -> dict:
        session.execute(text("SELECT 1"))
        return {"status": "ready"}

    @app.get("/metrics")
    def metrics() -> Response:
        try:
            from prometheus_client import CONTENT_TYPE_LATEST, generate_latest

            return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)
        except Exception:
            return Response("# prometheus_client is not installed\n", media_type="text/plain")

    @app.post("/repos/bootstrap", response_model=BootstrapResponse)
    def bootstrap_repo(payload: BootstrapRequest, session: Session = Depends(get_db)) -> BootstrapResponse:
        publisher = KafkaPublisher(settings) if payload.enqueue else None
        service = IngestionService(settings=settings, publisher=publisher)
        try:
            result = service.bootstrap_repo(session, repo_url=payload.repo_url, enqueue=payload.enqueue)
            session.commit()
        except Exception as exc:
            session.rollback()
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return BootstrapResponse(**result.__dict__)

    @app.post("/webhooks/github", response_model=WebhookAccepted)
    async def github_webhook(
        request: Request,
        x_hub_signature_256: str | None = Header(default=None),
        x_github_delivery: str | None = Header(default=None),
        session: Session = Depends(get_db),
    ) -> WebhookAccepted:
        body = await request.body()
        if not verify_github_signature(settings.github_webhook_secret, body, x_hub_signature_256):
            raise HTTPException(status_code=401, detail="Invalid GitHub webhook signature")
        payload = json.loads(body.decode("utf-8"))
        repo_url = payload.get("repository", {}).get("clone_url") or payload.get("repository", {}).get("ssh_url")
        if not repo_url:
            raise HTTPException(status_code=400, detail="Webhook payload missing repository clone URL")
        try:
            job = IngestionService(settings=settings, publisher=KafkaPublisher(settings)).enqueue_webhook_job(
                session,
                repo_url=repo_url,
                ref=payload.get("ref", ""),
                before=payload.get("before", ""),
                after=payload.get("after", ""),
                delivery_id=x_github_delivery or payload.get("after", ""),
            )
            session.commit()
        except Exception as exc:
            session.rollback()
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return WebhookAccepted(job_id=job.id, repo_id=job.repo_id, status=job.status)

    @app.post("/query")
    def query(payload: QueryRequest, session: Session = Depends(get_db)) -> dict:
        try:
            return QueryService(settings=settings).query(session, **payload.model_dump())
        except ValueError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except Exception as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.get("/jobs/{job_id}", response_model=JobResponse)
    def get_job(job_id: str, session: Session = Depends(get_db)) -> JobResponse:
        job = session.get(IngestionJob, job_id)
        if job is None:
            raise HTTPException(status_code=404, detail="Job not found")
        return JobResponse(
            id=job.id,
            repo_id=job.repo_id,
            job_type=job.job_type,
            status=job.status,
            ref=job.ref,
            before_sha=job.before_sha,
            after_sha=job.after_sha,
            error=job.error,
            stats=job.stats_json,
        )

    @app.get("/repos/{repo_id}/branches", response_model=BranchResponse)
    def get_branches(repo_id: str, session: Session = Depends(get_db)) -> BranchResponse:
        refs = (
            session.query(RepositoryRef)
            .filter(RepositoryRef.repo_id == repo_id, RepositoryRef.ref_type.in_(["branch", "remote_branch"]))
            .order_by(RepositoryRef.name)
            .all()
        )
        return BranchResponse(repo_id=repo_id, branches=[{"name": ref.name, "sha": ref.sha} for ref in refs])

    return app


app = create_app()
