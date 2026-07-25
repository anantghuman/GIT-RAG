"""Kafka producer/consumer helpers for ingestion jobs."""

from __future__ import annotations

import json
from typing import Callable

from gitrag.config import Settings, get_settings


class KafkaPublisher:
    def __init__(self, settings: Settings | None = None):
        self.settings = settings or get_settings()
        self._producer = None

    def _get_producer(self):
        if self._producer is not None:
            return self._producer
        from confluent_kafka import Producer

        self._producer = Producer({"bootstrap.servers": self.settings.kafka_bootstrap_servers})
        return self._producer

    def publish(self, payload: dict, *, key: str | None = None) -> None:
        producer = self._get_producer()
        producer.produce(
            self.settings.kafka_ingestion_topic,
            key=key,
            value=json.dumps(payload).encode("utf-8"),
        )
        producer.flush(10)


class KafkaConsumerLoop:
    def __init__(self, settings: Settings | None = None):
        self.settings = settings or get_settings()

    def run(self, handler: Callable[[dict], None]) -> None:
        from confluent_kafka import Consumer

        consumer = Consumer(
            {
                "bootstrap.servers": self.settings.kafka_bootstrap_servers,
                "group.id": self.settings.kafka_consumer_group,
                "auto.offset.reset": "earliest",
                "enable.auto.commit": False,
            }
        )
        consumer.subscribe([self.settings.kafka_ingestion_topic])
        try:
            while True:
                msg = consumer.poll(1.0)
                if msg is None:
                    continue
                if msg.error():
                    raise RuntimeError(msg.error())
                handler(json.loads(msg.value().decode("utf-8")))
                consumer.commit(msg)
        finally:
            consumer.close()
