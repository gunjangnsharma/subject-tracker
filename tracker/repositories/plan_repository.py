"""Data access for PlanAssignment, scoped to one user.

Reads join Chapter -> Module -> Subject so only the current user's assignments
are ever returned.
"""

from __future__ import annotations

from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from tracker.models import Chapter, Module, PlanAssignment, Subject


class PlanRepository:
    def __init__(self, session: Session, user_id: int) -> None:
        self._session = session
        self._user_id = user_id

    def _scoped(self):
        return (
            select(PlanAssignment)
            .join(Chapter, PlanAssignment.chapter_id == Chapter.id)
            .join(Module, Chapter.module_id == Module.id)
            .join(Subject, Module.subject_id == Subject.id)
            .where(Subject.user_id == self._user_id)
        )

    def add(self, chapter_id: int, planned_date: date) -> PlanAssignment:
        assignment = PlanAssignment(chapter_id=chapter_id, planned_date=planned_date)
        self._session.add(assignment)
        self._session.flush()
        return assignment

    def on_date(self, planned_date: date) -> list[PlanAssignment]:
        stmt = self._scoped().where(PlanAssignment.planned_date == planned_date)
        return list(self._session.scalars(stmt))

    def in_range(self, start: date, end: date) -> list[PlanAssignment]:
        stmt = self._scoped().where(
            PlanAssignment.planned_date >= start,
            PlanAssignment.planned_date <= end,
        )
        return list(self._session.scalars(stmt))

    def before(self, cutoff: date) -> list[PlanAssignment]:
        """The user's assignments planned strictly before ``cutoff`` (backlog candidates)."""
        stmt = self._scoped().where(PlanAssignment.planned_date < cutoff)
        return list(self._session.scalars(stmt))
