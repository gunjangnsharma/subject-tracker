"""Integration tests for planning + backlog rollover (test plan section 2.4).

Dates are injected (services take a `today` argument) so these never depend on
the real clock.
"""

from datetime import date, timedelta

import pytest

from tracker.services.planning_service import PlanningService
from tracker.services.subject_service import SubjectService

TODAY = date(2026, 8, 5)          # a Wednesday
YESTERDAY = TODAY - timedelta(days=1)
LAST_WEEK = TODAY - timedelta(days=8)


@pytest.fixture
def subjects(session):
    return SubjectService(session)


@pytest.fixture
def planning(session):
    return PlanningService(session)


def _make_chapter(subjects, duration=120, completion=0):
    subject = subjects.add_subject("S")
    module = subjects.add_module(subject.id, "M")
    chapter = subjects.add_chapter(module.id, "Chapter A", "video", duration)
    if completion:
        subjects.set_completion(chapter.id, completion)
    return chapter


def test_assigned_today_shows_in_plan(subjects, planning):  # P1
    ch = _make_chapter(subjects)
    planning.assign(ch.id, TODAY)
    plan = planning.today_plan(TODAY)
    assert [i.chapter.id for i in plan.planned] == [ch.id]
    assert plan.backlog == []


def test_yesterday_incomplete_is_backlog(subjects, planning):  # P2
    ch = _make_chapter(subjects, completion=5)  # half done
    planning.assign(ch.id, YESTERDAY)
    plan = planning.today_plan(TODAY)
    assert [i.chapter.id for i in plan.backlog] == [ch.id]
    assert plan.backlog[0].planned_date == YESTERDAY


def test_yesterday_complete_not_backlog(subjects, planning):  # P3
    ch = _make_chapter(subjects, completion=10)  # finished
    planning.assign(ch.id, YESTERDAY)
    plan = planning.today_plan(TODAY)
    assert plan.backlog == []


def test_last_week_incomplete_is_weekly_backlog(subjects, planning):  # P4
    ch = _make_chapter(subjects, completion=3)
    planning.assign(ch.id, LAST_WEEK)
    plan = planning.week_plan(TODAY)
    assert [i.chapter.id for i in plan.backlog] == [ch.id]


def test_this_week_shows_in_week_plan_not_backlog(subjects, planning):  # P5
    ch = _make_chapter(subjects, completion=2)
    # Monday of this week
    monday = TODAY - timedelta(days=TODAY.weekday())
    planning.assign(ch.id, monday)
    plan = planning.week_plan(TODAY)
    assert [i.chapter.id for i in plan.planned] == [ch.id]
    assert plan.backlog == []


def test_finishing_backlog_removes_it(subjects, planning):  # P6
    ch = _make_chapter(subjects, completion=5)
    planning.assign(ch.id, YESTERDAY)
    planning.assign(ch.id, LAST_WEEK)

    assert planning.today_plan(TODAY).backlog        # present before
    assert planning.week_plan(TODAY).backlog

    subjects.set_completion(ch.id, 10)               # finish it

    assert planning.today_plan(TODAY).backlog == []  # gone from both
    assert planning.week_plan(TODAY).backlog == []


def test_week_bounds_range(planning):  # P7
    plan = planning.week_plan(TODAY)
    assert plan.start == date(2026, 8, 3)   # Monday
    assert plan.end == date(2026, 8, 9)     # Sunday
