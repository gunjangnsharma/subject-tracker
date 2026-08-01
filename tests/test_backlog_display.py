"""Backlog carry-over + heading display, for both the day and week views.

Covers the requirement: when a planned item is not completed and its day/week
has passed, it appears in the backlog *with its heading* (chapter title), marked
as carried over from the original date.
"""

from datetime import date, timedelta

import pytest

from tracker.services.planning_service import PlanningService
from tracker.services.subject_service import SubjectService

# A fixed "today" for the deterministic service-level checks (a Wednesday).
TODAY = date(2026, 8, 5)
YESTERDAY = TODAY - timedelta(days=1)
LAST_WEEK = TODAY - timedelta(days=8)          # always in a previous week


@pytest.fixture
def subjects(session, user_id):
    return SubjectService(session, user_id)


@pytest.fixture
def planning(session, user_id):
    return PlanningService(session, user_id)


def _chapter(subjects, title, completed=0, duration=120):
    subject = subjects.add_subject("S")
    module = subjects.add_module(subject.id, "M")
    ch = subjects.add_chapter(module.id, title, "video", duration)
    if completed:
        subjects.set_completed_minutes(ch.id, completed, when=LAST_WEEK)
    return ch


# --- Service level (deterministic clock) --------------------------------
def test_past_week_incomplete_goes_to_weekly_backlog(subjects, planning):
    ch = _chapter(subjects, "Fourier Transforms", completed=48)  # 40% done
    planning.assign(ch.id, LAST_WEEK)

    week = planning.rolling_plan(TODAY)
    titles = [item.title for item in week.backlog]
    assert "Fourier Transforms" in titles                 # carried over
    assert week.backlog[0].planned_date == LAST_WEEK       # keeps original date


def test_past_day_incomplete_goes_to_today_backlog(subjects, planning):
    ch = _chapter(subjects, "Gradient Descent", completed=60)
    planning.assign(ch.id, YESTERDAY)

    day = planning.today_plan(TODAY)
    titles = [item.title for item in day.backlog]
    assert "Gradient Descent" in titles
    assert day.backlog[0].planned_date == YESTERDAY


def test_completed_item_not_in_either_backlog(subjects, planning):
    ch = _chapter(subjects, "Finished Topic", completed=120)  # done
    planning.assign(ch.id, LAST_WEEK)
    assert planning.today_plan(TODAY).backlog == []
    assert planning.rolling_plan(TODAY).backlog == []


# --- Rendered page level (real clock, via HTTP) -------------------------
def _seed_via_http(client, title, planned_date, completed=None):
    # Assumes a clean DB per test, so ids start at 1.
    client.post("/subjects", data={"name": "Subj"}, follow_redirects=True)
    client.post("/subjects/1/modules", data={"name": "Mod"}, follow_redirects=True)
    client.post(
        "/modules/1/chapters",
        data={"title": title, "kind": "video", "duration_minutes": "120"},
        follow_redirects=True,
    )
    if completed is not None:
        client.post(
            "/chapters/1/completion",
            data={"completed_hours": str(completed // 60), "completed_minutes": str(completed % 60)},
            follow_redirects=True,
        )
    client.post("/chapters/1/plan", data={"planned_date": planned_date.isoformat()},
                follow_redirects=True)


def test_today_page_shows_backlog_heading(auth_client):
    today = date.today()
    yesterday = today - timedelta(days=1)
    _seed_via_http(auth_client, "Backprop Chapter", yesterday, completed=60)

    page = auth_client.get("/today").get_data(as_text=True)
    assert "Backprop Chapter" in page                 # heading is shown
    assert "Backlog" in page
    assert f"carried from {yesterday.isoformat()}" in page  # marked as carried over


def test_week_page_shows_backlog_heading(auth_client):
    today = date.today()
    last_week = today - timedelta(days=8)
    _seed_via_http(auth_client, "Eigen Chapter", last_week, completed=36)

    page = auth_client.get("/week").get_data(as_text=True)
    assert "Eigen Chapter" in page
    assert "Overdue backlog" in page
    assert f"carried from {last_week.isoformat()}" in page


def test_finished_item_absent_from_today_page(auth_client):
    today = date.today()
    yesterday = today - timedelta(days=1)
    _seed_via_http(auth_client, "Done Chapter", yesterday, completed=120)

    page = auth_client.get("/today").get_data(as_text=True)
    assert "carried from" not in page                 # nothing carried over
