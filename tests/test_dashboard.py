"""Tests for the dashboard aggregation (subjects + today + week activity)."""

from datetime import date, timedelta

import pytest

from tracker.services.dashboard_service import DashboardService
from tracker.services.planning_service import PlanningService
from tracker.services.subject_service import SubjectService

TODAY = date(2026, 8, 5)          # Wednesday
YESTERDAY = TODAY - timedelta(days=1)
MONDAY = TODAY - timedelta(days=TODAY.weekday())


@pytest.fixture
def subjects(session, user_id):
    return SubjectService(session, user_id)


@pytest.fixture
def planning(session, user_id):
    return PlanningService(session, user_id)


@pytest.fixture
def dashboard(session, user_id):
    return DashboardService(session, user_id)


def _chapter(subjects, subject_name="S", duration=120):
    subject = subjects.add_subject(subject_name)
    module = subjects.add_module(subject.id, "M")
    chapter = subjects.add_chapter(module.id, "Ch", "video", duration)
    return subject, chapter


def test_overall_progress_sums_subjects(subjects, dashboard):
    _, c1 = _chapter(subjects, "A", 60)
    _, c2 = _chapter(subjects, "B", 120)
    subjects.set_completion(c1.id, 10, when=TODAY)  # 60 done
    subjects.set_completion(c2.id, 5, when=TODAY)   # 60 done

    view = dashboard.build(TODAY)
    assert view.overall.total_minutes == 180
    assert view.overall.completed_minutes == 120
    assert len(view.subjects) == 2


def test_today_stats(subjects, planning, dashboard):
    _, ch = _chapter(subjects, "A", 120)
    planning.assign(ch.id, TODAY)              # planned today
    subjects.set_completion(ch.id, 5, when=TODAY)  # studied 60 min today

    # A separate backlog chapter, planned yesterday, still unfinished.
    _, back = _chapter(subjects, "B", 60)
    planning.assign(back.id, YESTERDAY)

    view = dashboard.build(TODAY)
    assert view.today.planned_count == 1
    assert view.today.done_count == 0          # 5/10, not finished
    assert view.today.backlog_count == 1
    assert view.today.studied_minutes == 60


def test_today_done_count(subjects, planning, dashboard):
    _, ch = _chapter(subjects, "A", 60)
    planning.assign(ch.id, TODAY)
    subjects.set_completion(ch.id, 10, when=TODAY)
    view = dashboard.build(TODAY)
    assert view.today.planned_count == 1
    assert view.today.done_count == 1


def test_week_activity_per_day(subjects, dashboard):
    _, ch = _chapter(subjects, "A", 120)
    # Studied 60 min on Monday, another 30 min on Wednesday(today).
    subjects.set_completion(ch.id, 5, when=MONDAY)   # +60
    subjects.set_completion(ch.id, 8, when=TODAY)    # +36 (8/10*120 - 60)

    view = dashboard.build(TODAY)
    days = {d.label: d.studied_minutes for d in view.week.days}
    assert days["Mon"] == 60
    assert days["Wed"] == pytest.approx(36)
    assert view.week.studied_total == pytest.approx(96)


def test_week_planned_per_day(subjects, planning, dashboard):
    _, ch = _chapter(subjects, "A", 90)
    planning.assign(ch.id, MONDAY)
    view = dashboard.build(TODAY)
    days = {d.label: d.planned_minutes for d in view.week.days}
    assert days["Mon"] == 90
    assert view.week.planned_total == 90


def test_week_has_seven_days(subjects, dashboard):
    view = dashboard.build(TODAY)
    assert len(view.week.days) == 7
    assert view.week.start == MONDAY
    assert [d.label for d in view.week.days] == ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]


def test_empty_dashboard(dashboard):
    view = dashboard.build(TODAY)
    assert view.subjects == []
    assert view.overall.total_minutes == 0
    assert view.today.planned_count == 0
    assert view.week.studied_total == 0
