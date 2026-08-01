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
def subjects(session, user_id):
    return SubjectService(session, user_id)


@pytest.fixture
def planning(session, user_id):
    return PlanningService(session, user_id)


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


def test_past_incomplete_is_rolling_backlog(subjects, planning):  # P4
    ch = _make_chapter(subjects, completion=3)
    planning.assign(ch.id, LAST_WEEK)
    plan = planning.rolling_plan(TODAY)
    assert [i.chapter.id for i in plan.backlog] == [ch.id]


def test_future_shows_in_its_day_not_backlog(subjects, planning):  # P5
    ch = _make_chapter(subjects, completion=2)
    day3 = TODAY + timedelta(days=3)
    planning.assign(ch.id, day3)
    plan = planning.rolling_plan(TODAY)
    assert [i.chapter.id for i in plan.days[3].items] == [ch.id]
    assert plan.days[0].items == []
    assert plan.backlog == []


def test_finishing_backlog_removes_it(subjects, planning):  # P6
    ch = _make_chapter(subjects, completion=5)
    planning.assign(ch.id, YESTERDAY)
    planning.assign(ch.id, LAST_WEEK)

    assert planning.today_plan(TODAY).backlog        # present before
    assert planning.rolling_plan(TODAY).backlog

    subjects.set_completion(ch.id, 10)               # finish it

    assert planning.today_plan(TODAY).backlog == []  # gone from both
    assert planning.rolling_plan(TODAY).backlog == []


def test_rolling_window_is_today_to_today_plus_6(planning):  # P7
    plan = planning.rolling_plan(TODAY)   # TODAY = 2026-08-05
    assert plan.start == TODAY                       # window starts today
    assert plan.end == TODAY + timedelta(days=6)     # ends today + 6
    assert len(plan.days) == 7
    assert plan.days[0].day == TODAY and plan.days[0].is_today
    assert [d.day for d in plan.days] == [TODAY + timedelta(days=i) for i in range(7)]
