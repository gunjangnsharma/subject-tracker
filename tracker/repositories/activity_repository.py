"""Data access for ProgressEvent (study activity log)."""

from __future__ import annotations

from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from tracker.models import ProgressEvent


class ActivityRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def add(self, chapter_id: int, occurred_on: date, minutes_delta: float) -> ProgressEvent:
        event = ProgressEvent(
            chapter_id=chapter_id,
            occurred_on=occurred_on,
            minutes_delta=minutes_delta,
        )
        self._session.add(event)
        self._session.flush()
        return event

    def on_date(self, day: date) -> list[ProgressEvent]:
        stmt = select(ProgressEvent).where(ProgressEvent.occurred_on == day)
        return list(self._session.scalars(stmt))

    def between(self, start: date, end: date) -> list[ProgressEvent]:
        stmt = select(ProgressEvent).where(
            ProgressEvent.occurred_on >= start,
            ProgressEvent.occurred_on <= end,
        )
        return list(self._session.scalars(stmt))
