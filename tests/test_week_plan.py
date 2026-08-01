"""Rolling 7-day week plan: service grouping + rendered /week page.

The week plan shows a rolling window of 7 day-groups starting today (today ..
today+6), one section per day in chronological order, plus an overdue backlog
(items planned before today that are still unfinished).
"""

from datetime import date, timedelta

import pytest

from tracker.services.planning_service import PlanningService
from tracker.services.subject_service import SubjectService

TODAY = date(2026, 8, 5)          # a Wednesday (deterministic clock for service tests)


@pytest.fixture
def subjects(session, user_id):
    return SubjectService(session, user_id)


@pytest.fixture
def planning(session, user_id):
    return PlanningService(session, user_id)


def _chapter(subjects, title="C", completed=0, duration=60):
    subject = subjects.add_subject(f"S-{title}")
    module = subjects.add_module(subject.id, "M")
    ch = subjects.add_chapter(module.id, title, "video", duration)
    if completed:
        subjects.set_completed_minutes(ch.id, completed, when=TODAY - timedelta(days=10))
    return ch


# --- Service: window shape ----------------------------------------------
def test_window_is_seven_days_from_today(planning):
    plan = planning.rolling_plan(TODAY)
    assert plan.start == TODAY
    assert plan.end == TODAY + timedelta(days=6)
    assert len(plan.days) == 7
    assert [d.day for d in plan.days] == [TODAY + timedelta(days=i) for i in range(7)]
    assert plan.days[0].is_today
    assert not plan.days[1].is_today
    assert plan.days[0].weekday == "Wed"     # 2026-08-05 is a Wednesday


def test_window_rolls_with_today(planning):
    # A different "today" shifts the whole window; still 7 days, still starts today.
    other = TODAY + timedelta(days=1)
    plan = planning.rolling_plan(other)
    assert plan.start == other
    assert plan.days[0].day == other
    assert len(plan.days) == 7


# --- Service: grouping ---------------------------------------------------
def test_today_item_in_first_group(subjects, planning):
    ch = _chapter(subjects)
    planning.assign(ch.id, TODAY)
    plan = planning.rolling_plan(TODAY)
    assert [i.chapter.id for i in plan.days[0].items] == [ch.id]
    assert all(d.items == [] for d in plan.days[1:])


def test_future_item_in_its_own_day(subjects, planning):
    ch = _chapter(subjects)
    planning.assign(ch.id, TODAY + timedelta(days=4))
    plan = planning.rolling_plan(TODAY)
    assert plan.days[4].items and plan.days[4].items[0].chapter.id == ch.id
    assert plan.days[4].count == 1
    # not in any other day, not in backlog
    assert sum(d.count for d in plan.days) == 1
    assert plan.backlog == []


def test_beyond_window_is_not_shown(subjects, planning):
    ch = _chapter(subjects)
    planning.assign(ch.id, TODAY + timedelta(days=8))   # outside the 7-day window
    plan = planning.rolling_plan(TODAY)
    assert sum(d.count for d in plan.days) == 0
    assert plan.backlog == []                            # future, so not overdue either


def test_multiple_items_same_day_grouped_and_sorted(subjects, planning):
    s = subjects.add_subject("Zeta")
    m = subjects.add_module(s.id, "M")
    b = subjects.add_chapter(m.id, "Beta", "video", 60)
    a = subjects.add_chapter(m.id, "Alpha", "video", 60)
    day2 = TODAY + timedelta(days=2)
    planning.assign(b.id, day2)
    planning.assign(a.id, day2)
    plan = planning.rolling_plan(TODAY)
    titles = [i.title for i in plan.days[2].items]
    assert titles == ["Alpha", "Beta"]      # sorted within the day


# --- Service: overdue backlog -------------------------------------------
def test_overdue_incomplete_in_backlog_not_days(subjects, planning):
    ch = _chapter(subjects, completed=24)   # unfinished (of 60)
    planning.assign(ch.id, TODAY - timedelta(days=3))
    plan = planning.rolling_plan(TODAY)
    assert [i.chapter.id for i in plan.backlog] == [ch.id]
    assert sum(d.count for d in plan.days) == 0


def test_overdue_complete_excluded(subjects, planning):
    ch = _chapter(subjects, completed=60)   # finished (of 60)
    planning.assign(ch.id, TODAY - timedelta(days=3))
    plan = planning.rolling_plan(TODAY)
    assert plan.backlog == []


# --- One date per chapter (no duplicates) -------------------------------
def test_reassigning_moves_chapter(subjects, planning):
    ch = _chapter(subjects)
    planning.assign(ch.id, TODAY)
    planning.assign(ch.id, TODAY + timedelta(days=2))   # re-plan -> moves
    plan = planning.rolling_plan(TODAY)
    assert plan.days[0].items == []                      # no longer on today
    assert [i.chapter.id for i in plan.days[2].items] == [ch.id]
    assert sum(d.count for d in plan.days) == 1          # exactly one appearance


def test_assign_same_date_twice_keeps_one(subjects, planning):
    ch = _chapter(subjects)
    planning.assign(ch.id, TODAY)
    planning.assign(ch.id, TODAY)
    plan = planning.rolling_plan(TODAY)
    assert plan.days[0].count == 1


def test_chapter_appears_once_across_today_and_week(subjects, planning):
    ch = _chapter(subjects)
    planning.assign(ch.id, TODAY)
    day = planning.today_plan(TODAY)
    week = planning.rolling_plan(TODAY)
    assert [i.chapter.id for i in day.planned] == [ch.id]   # once on today's page
    assert day.backlog == []
    assert sum(d.count for d in week.days) == 1             # once in the week


# --- Rendered /week page (real clock) -----------------------------------
def test_week_page_shows_seven_day_sections(auth_client):
    today = date.today()
    page = auth_client.get("/week").get_data(as_text=True)
    assert page.count("day-group") >= 7           # 7 day sections rendered
    for i in range(7):
        d = today + timedelta(days=i)
        assert d.strftime("%d %b") in page        # each day's date label present
    assert "today-badge" in page                  # today section badge (not the nav link)
    assert "Overdue backlog" in page


def test_week_page_task_under_its_day(auth_client):
    today = date.today()
    target = today + timedelta(days=3)
    auth_client.post("/subjects", data={"name": "S"}, follow_redirects=True)
    auth_client.post("/subjects/1/modules", data={"name": "M"}, follow_redirects=True)
    auth_client.post(
        "/modules/1/chapters",
        data={"title": "Future Task", "kind": "video", "duration_minutes": "60"},
        follow_redirects=True,
    )
    auth_client.post(
        "/chapters/1/plan",
        data={"planned_date": target.isoformat()},
        follow_redirects=True,
    )
    page = auth_client.get("/week").get_data(as_text=True)
    assert "Future Task" in page
    assert target.strftime("%d %b") in page       # its day's heading is shown


def test_week_page_empty_day_shows_nothing_planned(auth_client):
    # No tasks at all -> every day shows the empty state.
    page = auth_client.get("/week").get_data(as_text=True)
    assert "Nothing planned." in page


def test_week_page_replan_shows_task_once(auth_client):
    today = date.today()
    auth_client.post("/subjects", data={"name": "S"}, follow_redirects=True)
    auth_client.post("/subjects/1/modules", data={"name": "M"}, follow_redirects=True)
    auth_client.post(
        "/modules/1/chapters",
        data={"title": "Solo Task", "kind": "video", "duration_minutes": "60"},
        follow_redirects=True,
    )
    # Plan it twice, to different days.
    auth_client.post("/chapters/1/plan", data={"planned_date": today.isoformat()},
                     follow_redirects=True)
    auth_client.post("/chapters/1/plan",
                     data={"planned_date": (today + timedelta(days=2)).isoformat()},
                     follow_redirects=True)
    page = auth_client.get("/week").get_data(as_text=True)
    assert page.count("Solo Task") == 1          # appears exactly once, on the latest day
