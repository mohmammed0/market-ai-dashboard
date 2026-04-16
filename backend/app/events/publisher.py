from __future__ import annotations

import asyncio
import logging
from threading import Lock
from typing import Protocol

from backend.app.config import (
    EVENT_PERSIST_DEAD_LETTERS,
    EVENT_TRANSPORT,
    NATS_SUBJECT_PREFIX,
    NATS_URL,
)
from backend.app.core.logging_utils import get_logger, log_event
from backend.app.observability.metrics import emit_counter
from backend.app.repositories.platform_events import PlatformEventRepository
from backend.app.services.storage import session_scope
from packages.contracts.events import EventEnvelope

logger = get_logger(__name__)


class EventPublisher(Protocol):
    def publish_envelope(self, envelope: EventEnvelope) -> EventEnvelope: ...


def build_event_envelope(
    *,
    event_type: str,
    producer: str,
    payload: dict,
    correlation_id: str | None = None,
    event_version: str = "1",
) -> EventEnvelope:
    return EventEnvelope(
        event_type=event_type,
        event_version=event_version,
        producer=producer,
        correlation_id=correlation_id,
        payload=payload,
    )


class InMemoryEventPublisher:
    """Temporary publisher for the modular-monolith stage."""

    def __init__(self) -> None:
        self._events: list[EventEnvelope] = []

    @property
    def events(self) -> list[EventEnvelope]:
        return list(self._events)

    def publish_envelope(self, envelope: EventEnvelope) -> EventEnvelope:
        self._events.append(envelope)
        return envelope

    def publish(
        self,
        *,
        event_type: str,
        producer: str,
        payload: dict,
        correlation_id: str | None = None,
        event_version: str = "1",
    ) -> EventEnvelope:
        envelope = build_event_envelope(
            event_type=event_type,
            producer=producer,
            payload=payload,
            correlation_id=correlation_id,
            event_version=event_version,
        )
        return self.publish_envelope(envelope)


class NatsEventPublisher:
    """Best-effort NATS publisher with graceful failure semantics."""

    def __init__(self, *, servers: str, subject_prefix: str) -> None:
        self._servers = servers
        self._subject_prefix = subject_prefix.strip(".")

    def _subject_for(self, event_type: str) -> str:
        if self._subject_prefix:
            return f"{self._subject_prefix}.{event_type}"
        return event_type

    async def _publish_async(self, envelope: EventEnvelope) -> None:
        try:
            from nats.aio.client import Client as NATS  # type: ignore
        except Exception as exc:  # pragma: no cover - optional dependency
            raise RuntimeError("NATS transport requested but python 'nats-py' is not installed.") from exc

        client = NATS()
        await client.connect(servers=[self._servers], connect_timeout=2, max_reconnect_attempts=1)
        try:
            await client.publish(
                self._subject_for(envelope.event_type),
                envelope.model_dump_json().encode("utf-8"),
            )
            await client.flush(timeout=2)
        finally:
            await client.close()

    def publish_envelope(self, envelope: EventEnvelope) -> EventEnvelope:
        asyncio.run(self._publish_async(envelope))
        return envelope


_publisher_lock = Lock()
_publisher_cache: tuple[str, EventPublisher] | None = None


def _build_configured_publisher() -> EventPublisher:
    transport = EVENT_TRANSPORT
    if transport == "nats":
        try:
            return NatsEventPublisher(servers=NATS_URL, subject_prefix=NATS_SUBJECT_PREFIX)
        except Exception as exc:  # pragma: no cover - fallback path
            log_event(
                logger,
                logging.WARNING,
                "events.publisher_transport_fallback",
                requested_transport=transport,
                fallback_transport="inmemory",
                error=str(exc),
            )
    return InMemoryEventPublisher()


def get_event_publisher() -> EventPublisher:
    global _publisher_cache
    cache_key = f"{EVENT_TRANSPORT}|{NATS_URL}|{NATS_SUBJECT_PREFIX}"
    with _publisher_lock:
        if _publisher_cache is None or _publisher_cache[0] != cache_key:
            _publisher_cache = (cache_key, _build_configured_publisher())
        return _publisher_cache[1]


def publish_event(
    *,
    event_type: str,
    producer: str,
    payload: dict,
    correlation_id: str | None = None,
    event_version: str = "1",
) -> EventEnvelope:
    envelope = build_event_envelope(
        event_type=event_type,
        producer=producer,
        payload=payload,
        correlation_id=correlation_id,
        event_version=event_version,
    )
    try:
        publisher = get_event_publisher()
        publisher.publish_envelope(envelope)
        log_event(
            logger,
            logging.INFO,
            "events.published",
            event_id=envelope.event_id,
            event_type=event_type,
            producer=producer,
            correlation_id=correlation_id,
            transport=EVENT_TRANSPORT,
        )
        emit_counter(
            "events_published_total",
            event_type=event_type,
            producer=producer,
            transport=EVENT_TRANSPORT,
        )
    except Exception as exc:
        log_event(
            logger,
            logging.ERROR,
            "events.publish_failed",
            event_id=envelope.event_id,
            event_type=event_type,
            producer=producer,
            correlation_id=correlation_id,
            transport=EVENT_TRANSPORT,
            error=str(exc),
        )
        emit_counter(
            "events_publish_failures_total",
            event_type=event_type,
            producer=producer,
            transport=EVENT_TRANSPORT,
        )
        if EVENT_PERSIST_DEAD_LETTERS:
            try:
                with session_scope() as session:
                    PlatformEventRepository(session).append_dead_letter_event(
                        event_id=envelope.event_id,
                        event_type=envelope.event_type,
                        producer=envelope.producer,
                        correlation_id=envelope.correlation_id,
                        payload=envelope.payload,
                        error_message=str(exc),
                    )
            except Exception as dead_letter_exc:  # pragma: no cover - defensive logging
                log_event(
                    logger,
                    logging.ERROR,
                    "events.dead_letter_failed",
                    event_id=envelope.event_id,
                    event_type=envelope.event_type,
                    error=str(dead_letter_exc),
                )
    return envelope


__all__ = [
    "EventPublisher",
    "InMemoryEventPublisher",
    "NatsEventPublisher",
    "build_event_envelope",
    "get_event_publisher",
    "publish_event",
]
