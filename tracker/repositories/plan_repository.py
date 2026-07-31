"""Data access for PlanAssignment (daily/weekly planning)."""

from __future__ import annotations

from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from tracker.models import PlanAssignment


class PlanRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def add(self, chapter_id: int, planned_date: date) -> PlanAssignment:
        assignment = PlanAssignment(chapter_id=chapter_id, planned_date=planned_date)
        self._session.add(assignment)
        self._session.flush()
        return assignment

    def on_date(self, planned_date: date) -> list[PlanAssignment]:
        stmt = select(PlanAssignment).where(PlanAssignment.planned_date == planned_date)
        return list(self._session.scalars(stmt))

    def in_range(self, start: date, end: date) -> list[PlanAssignment]:
        stmt = select(PlanAssignment).where(
            PlanAssignment.planned_date >= start,
            PlanAssignment.planned_date <= end,
        )
        return list(self._session.scalars(stmt))

    def before(self, cutoff: date) -> list[PlanAssignment]:
        """All assignments planned strictly before ``cutoff`` (candidates for backlog)."""
        stmt = select(PlanAssignment).where(PlanAssignment.planned_date < cutoff)
        return list(self._session.scalars(stmt))
