"""Daily / weekly planning with derived backlog.

Backlog is never stored or moved between days. It is computed at read time by
comparing each assignment's ``planned_date`` against 'today'. An assignment is
backlog when it was planned in the past and its chapter is not yet done.
Finishing a chapter (completion -> 10) therefore removes it from every backlog
automatically.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta

from sqlalchemy.orm import Session

from tracker import domain
from tracker.models import Chapter, PlanAssignment
from tracker.repositories.chapter_repository import ChapterRepository
from tracker.repositories.plan_repository import PlanRepository

# The week plan shows a rolling window of this many days, starting today.
ROLLING_WINDOW_DAYS = 7


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
class DayGroup:
    """One day within the rolling week window, with its planned items."""

    day: date
    today: date
    items: list[PlannedItem]        # chapters planned for this exact day

    @property
    def is_today(self) -> bool:
        return self.day == self.today

    @property
    def weekday(self) -> str:
        return self.day.strftime("%a")   # Mon, Tue, ...

    @property
    def count(self) -> int:
        return len(self.items)


@dataclass(frozen=True)
class RollingPlan:
    """A rolling window of `len(days)` day-groups starting today, + overdue backlog."""

    start: date                     # == today
    end: date                       # == today + window - 1
    days: list[DayGroup]            # one per day, chronological from today
    backlog: list[PlannedItem]      # planned before today and still unfinished


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
        # One date per chapter: remove any existing plan (re-planning *moves* it),
        # so a chapter can never appear on more than one day / in more than one place.
        for existing in self._plans.for_chapter(chapter_id):
            self._plans.delete(existing)
        assignment = self._plans.add(chapter_id, planned_date)
        self._session.commit()
        return assignment

    def assignments_in_range(self, start: date, end: date) -> list[PlanAssignment]:
        return self._plans.in_range(start, end)

    def unassign(self, chapter_id: int) -> bool:
        """Remove a chapter from the plan entirely (planned by mistake).

        Deletes the chapter's plan assignment, so it disappears from the day
        view, the week view and every backlog. Returns True if something was
        removed, False if the chapter was not planned — asking to unplan an
        unplanned chapter is a harmless no-op, not an error.

        **Progress and activity are untouched.** Only the "do this on this day"
        link is removed; any completed minutes and the study events that recorded
        them stay exactly as they were, so unplanning never rewrites history.
        Dashboard *counts* (planned/done/backlog, and the week's planned-minutes
        bars) drop this chapter immediately because they are derived from the
        assignments at read time.

        Raises ValueError for an unknown chapter, including another user's (the
        repository reports those as missing).
        """
        if self._chapters.get(chapter_id) is None:
            raise ValueError("Chapter not found.")
        existing = self._plans.for_chapter(chapter_id)
        if not existing:
            return False
        for assignment in existing:
            self._plans.delete(assignment)
        self._session.commit()
        return True

    def today_plan(self, today: date) -> DayPlan:
        planned = [_to_item(a) for a in self._plans.on_date(today)]
        backlog = [
            _to_item(a)
            for a in self._plans.before(today)
            if not a.chapter.is_done
        ]
        backlog.sort(key=lambda item: item.planned_date)
        return DayPlan(day=today, planned=planned, backlog=backlog)

    def rolling_plan(self, today: date, window: int = ROLLING_WINDOW_DAYS) -> RollingPlan:
        """The plan for the next `window` days, grouped one section per day.

        Days run chronologically from `today` (inclusive) to `today + window - 1`.
        Items planned outside that window are not shown as day-groups; those
        planned *before* today and still unfinished appear in the overdue backlog.
        """
        end = today + timedelta(days=window - 1)

        # Bucket the window's assignments by their planned date.
        buckets: dict[date, list[PlannedItem]] = {}
        for a in self._plans.in_range(today, end):
            buckets.setdefault(a.planned_date, []).append(_to_item(a))
        for items in buckets.values():
            items.sort(key=lambda i: (i.subject_name, i.module_name, i.title))

        days = [
            DayGroup(
                day=today + timedelta(days=offset),
                today=today,
                items=buckets.get(today + timedelta(days=offset), []),
            )
            for offset in range(window)
        ]

        backlog = [
            _to_item(a)
            for a in self._plans.before(today)
            if not a.chapter.is_done
        ]
        backlog.sort(key=lambda item: item.planned_date)
        return RollingPlan(start=today, end=end, days=days, backlog=backlog)
