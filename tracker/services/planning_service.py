"""Daily / weekly planning with derived backlog.

Backlog is never stored or moved between days. It is computed at read time by
comparing each assignment's ``planned_date`` against 'today'. An assignment is
backlog when it was planned in the past and its chapter is not yet done.
Finishing a chapter (completion -> 10) therefore removes it from every backlog
automatically.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from sqlalchemy.orm import Session

from tracker import domain
from tracker.models import Chapter, PlanAssignment
from tracker.repositories.chapter_repository import ChapterRepository
from tracker.repositories.plan_repository import PlanRepository


@dataclass(frozen=True)
class PlannedItem:
    """A chapter appearing in a plan, with display context."""

    assignment_id: int
    chapter: Chapter
    planned_date: date

    @property
    def title(self) -> str:
        return self.chapter.title

    @property
    def module_name(self) -> str:
        return self.chapter.module.name

    @property
    def subject_name(self) -> str:
        return self.chapter.module.subject.name

    @property
    def is_done(self) -> bool:
        return self.chapter.is_done

    @property
    def progress(self) -> domain.Progress:
        return self.chapter.progress


def _to_item(assignment: PlanAssignment) -> PlannedItem:
    return PlannedItem(
        assignment_id=assignment.id,
        chapter=assignment.chapter,
        planned_date=assignment.planned_date,
    )


@dataclass(frozen=True)
class DayPlan:
    day: date
    planned: list[PlannedItem]      # planned for this exact day
    backlog: list[PlannedItem]      # carried over from earlier, still unfinished


@dataclass(frozen=True)
class WeekPlan:
    start: date
    end: date
    planned: list[PlannedItem]      # planned within this week
    backlog: list[PlannedItem]      # from before this week, still unfinished


class PlanningService:
    def __init__(self, session: Session, user_id: int) -> None:
        self._session = session
        self._user_id = user_id
        self._plans = PlanRepository(session, user_id)
        self._chapters = ChapterRepository(session, user_id)

    def assign(self, chapter_id: int, planned_date: date) -> PlanAssignment:
        # Ownership guard: only the owner of the chapter may plan it.
        if self._chapters.get(chapter_id) is None:
            raise ValueError("Chapter not found.")
        assignment = self._plans.add(chapter_id, planned_date)
        self._session.commit()
        return assignment

    def assignments_in_range(self, start: date, end: date) -> list[PlanAssignment]:
        return self._plans.in_range(start, end)

    def today_plan(self, today: date) -> DayPlan:
        planned = [_to_item(a) for a in self._plans.on_date(today)]
        backlog = [
            _to_item(a)
            for a in self._plans.before(today)
            if not a.chapter.is_done
        ]
        backlog.sort(key=lambda item: item.planned_date)
        return DayPlan(day=today, planned=planned, backlog=backlog)

    def week_plan(self, today: date) -> WeekPlan:
        start, end = domain.week_bounds(today)
        planned = [_to_item(a) for a in self._plans.in_range(start, end)]
        backlog = [
            _to_item(a)
            for a in self._plans.before(start)
            if not a.chapter.is_done
        ]
        backlog.sort(key=lambda item: item.planned_date)
        return WeekPlan(start=start, end=end, planned=planned, backlog=backlog)
