"""Data access for ProgressEvent (study activity log), scoped to one user."""

from __future__ import annotations

from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from tracker.models import Chapter, Module, ProgressEvent, Subject


class ActivityRepository:
    def __init__(self, session: Session, user_id: int) -> None:
        self._session = session
        self._user_id = user_id

    def _scoped(self):
        return (
            select(ProgressEvent)
            .join(Chapter, ProgressEvent.chapter_id == Chapter.id)
            .join(Module, Chapter.module_id == Module.id)
            .join(Subject, Module.subject_id == Subject.id)
            .where(Subject.user_id == self._user_id)
        )

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
        stmt = self._scoped().where(ProgressEvent.occurred_on == day)
        return list(self._session.scalars(stmt))

    def between(self, start: date, end: date) -> list[ProgressEvent]:
        stmt = self._scoped().where(
            ProgressEvent.occurred_on >= start,
            ProgressEvent.occurred_on <= end,
        )
        return list(self._session.scalars(stmt))
