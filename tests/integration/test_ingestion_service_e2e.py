import subprocess

from gitrag.db.models import Chunk, File
from gitrag.db.session import create_all, session_scope
from gitrag.ingest.service import IngestionService
from gitrag.retrieval.service import QueryService


def run(cmd, cwd):
    subprocess.run(cmd, cwd=cwd, check=True, capture_output=True, text=True)


def reset_db_session():
    import gitrag.db.session as session_module

    session_module._engine = None
    session_module._SessionLocal = None


def test_ingestion_service_skips_dependencies_and_queries_repeated_file_changes(tmp_path, monkeypatch):
    repo = tmp_path / "repo"
    repo.mkdir()
    run(["git", "init", "-b", "main"], repo)
    run(["git", "config", "user.email", "dev@example.com"], repo)
    run(["git", "config", "user.name", "Dev"], repo)

    (repo / "node_modules/pkg").mkdir(parents=True)
    (repo / "node_modules/pkg/index.js").write_text("function dependency() { return true; }\n", encoding="utf-8")
    (repo / "server.js").write_text("function start() {\n  return 'v1';\n}\n", encoding="utf-8")
    run(["git", "add", "."], repo)
    run(["git", "commit", "-m", "initial app"], repo)

    (repo / "server.js").write_text(
        "function start() {\n  return 'v2';\n}\n\nfunction route() {\n  return '/health';\n}\n",
        encoding="utf-8",
    )
    run(["git", "commit", "-am", "add route"], repo)

    (repo / "server.js").write_text(
        "function start() {\n  return 'v3';\n}\n\nfunction route() {\n  return '/ready';\n}\n",
        encoding="utf-8",
    )
    run(["git", "commit", "-am", "update route"], repo)

    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path / 'gitrag.db'}")
    monkeypatch.setenv("GITRAG_VECTOR_BACKEND", "memory")
    monkeypatch.setenv("GITRAG_DETERMINISTIC_EMBEDDINGS", "true")
    monkeypatch.setenv("CLONE_REPO_DIR", str(tmp_path / "mirrors"))
    monkeypatch.setenv("LOCAL_OBJECT_DIR", str(tmp_path / "objects"))
    monkeypatch.setenv("PROJECT_DIR", str(tmp_path))
    reset_db_session()
    create_all()

    with session_scope() as session:
        service = IngestionService()
        boot = service.bootstrap_repo(session, repo_url=str(repo), enqueue=False)
        stats = service.process_job(
            session,
            {"job_id": boot.job_id, "repo_id": boot.repo_id, "repo_url": str(repo), "mode": "bootstrap"},
        )

        indexed_paths = [row.path for row in session.query(File).all()]
        assert "server.js" in indexed_paths
        assert all(not path.startswith("node_modules/") for path in indexed_paths)
        assert stats["commits"] == 3
        assert session.query(Chunk).count() > 0

        result = QueryService().query(
            session,
            repo_id=boot.repo_id,
            question="Where is the route defined?",
            top_k=3,
            include_answer=False,
        )
        assert result["citations"]
