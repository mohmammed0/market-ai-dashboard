from __future__ import annotations

from backend.app.events.publisher import publish_event
from backend.app.repositories.platform_events import PlatformEventRepository
from backend.app.services.storage import session_scope


def replay_order_events(*, limit: int = 100, event_type: str | None = None) -> dict:
    with session_scope() as session:
        repo = PlatformEventRepository(session)
        job = repo.create_event_replay_job(job_name="operations.replay_order_events", event_type_filter=event_type)
        events = repo.list_order_events(limit=limit, event_type=event_type)
        replayed = 0
        for item in reversed(events):
            publish_event(
                event_type=item["event_type"],
                producer="event_replay",
                payload=item["payload"] or {},
                correlation_id=item["correlation_id"],
            )
            replayed += 1
        result = {"replayed": replayed, "requested_limit": limit, "event_type": event_type}
        repo.complete_event_replay_job(job, status="completed", result=result)
        return result

