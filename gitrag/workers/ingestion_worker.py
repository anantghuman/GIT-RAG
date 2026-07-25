"""Kafka worker entrypoint for incremental Git ingestion."""

from __future__ import annotations

from gitrag.config import get_settings
from gitrag.db.session import create_all, session_scope
from gitrag.ingest.service import IngestionService
from gitrag.queue.kafka import KafkaConsumerLoop


def handle_payload(payload: dict) -> dict:
    settings = get_settings()
    if settings.database_url.startswith("sqlite"):
        create_all()
    with session_scope() as session:
        return IngestionService(settings=settings).process_job(session, payload)


def main() -> None:
    settings = get_settings()
    KafkaConsumerLoop(settings).run(lambda payload: handle_payload(payload))


if __name__ == "__main__":
    main()
