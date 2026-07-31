"""Assembles the dashboard view model: subjects + today + week activity.

Pure aggregation over the other layers; returns plain dataclasses so the
numbers are trivial to unit-test and to hand to the template / charts.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta

from sqlalchemy.orm import Session

from tracker import domain
from tracker.repositories.activity_repository import ActivityRepository
from tracker.services.planning_service import PlanningService
from tracker.services.subject_service import SubjectService


@dataclass(frozen=True)
class SubjectSummary:
    id: int
    name: str
    progress: domain.Progress


@dataclass(frozen=True)
class TodayStats:
    planned_count: int          # chapters planned for today
    done_count: int             # of those, how many are finished
    backlog_count: int          # unfinished carried over from earlier days
    studied_minutes: float      # minutes actually progressed today


@dataclass(frozen=True)
class DayActivity:
    day: date
    label: str                  # e.g. "Mon"
    studied_minutes: float      # actual progress that day
    planned_minutes: float      # target: duration of chapters planned that day

    @property
    def studied_hours(self) -> float:
        return domain.minutes_to_hours(self.studied_minutes)

    @property
    def planned_hours(self) -> float:
        return domain.minutes_to_hours(self.planned_minutes)


@dataclass(frozen=True)
class WeekStats:
    start: date
    end: date
    days: list[DayActivity]

    @property
    def studied_total(self) -> float:
        return sum(d.studied_minutes for d in self.days)

    @property
    def planned_total(self) -> float:
        return sum(d.planned_minutes for d in self.days)


@dataclass(frozen=True)
class DashboardView:
    overall: domain.Progress
    subjects: list[SubjectSummary]
    today: TodayStats
    week: WeekStats


class DashboardService:
    def __init__(self, session: Session) -> None:
        self._session = session
        self._subjects = SubjectService(session)
        self._planning = PlanningService(session)
        self._activity = ActivityRepository(session)

    def build(self, today: date) -> DashboardView:
        subjects = self._subjects.list_subjects()
        summaries = [
            SubjectSummary(id=s.id, name=s.name, progress=s.progress) for s in subjects
        ]
        overall = domain.sum_progress([s.progress for s in summaries])

        today_stats = self._today_stats(today)
        week_stats = self._week_stats(today)
        return DashboardView(
            overall=overall,
            subjects=summaries,
            today=today_stats,
            week=week_stats,
        )

    # --- Today -------------------------------------------------------------
    def _today_stats(self, today: date) -> TodayStats:
        plan = self._planning.today_plan(today)
        studied = self._studied_minutes(self._activity.on_date(today))
        return TodayStats(
            planned_count=len(plan.planned),
            done_count=sum(1 for i in plan.planned if i.is_done),
            backlog_count=len(plan.backlog),
            studied_minutes=studied,
        )

    # --- Week --------------------------------------------------------------
    def _week_stats(self, today: date) -> WeekStats:
        start, end = domain.week_bounds(today)
        events = self._activity.between(start, end)
        assignments = self._planning.assignments_in_range(start, end)

        studied_by_day: dict[date, float] = {}
        for ev in events:
            if ev.minutes_delta > 0:  # count study, not corrections
                studied_by_day[ev.occurred_on] = (
                    studied_by_day.get(ev.occurred_on, 0.0) + ev.minutes_delta
                )
        planned_by_day: dict[date, float] = {}
        for a in assignments:
            planned_by_day[a.planned_date] = (
                planned_by_day.get(a.planned_date, 0.0) + a.chapter.duration_minutes
            )

        labels = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
        days = [
            DayActivity(
                day=start + timedelta(days=i),
                label=labels[i],
                studied_minutes=studied_by_day.get(start + timedelta(days=i), 0.0),
                planned_minutes=planned_by_day.get(start + timedelta(days=i), 0.0),
            )
            for i in range(7)
        ]
        return WeekStats(start=start, end=end, days=days)

    @staticmethod
    def _studied_minutes(events) -> float:
        return sum(ev.minutes_delta for ev in events if ev.minutes_delta > 0)
