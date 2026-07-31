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


def _chapter(subjects, title, completion=0, duration=120):
    subject = subjects.add_subject("S")
    module = subjects.add_module(subject.id, "M")
    ch = subjects.add_chapter(module.id, title, "video", duration)
    if completion:
        subjects.set_completion(ch.id, completion, when=LAST_WEEK)
    return ch


# --- Service level (deterministic clock) --------------------------------
def test_past_week_incomplete_goes_to_weekly_backlog(subjects, planning):
    ch = _chapter(subjects, "Fourier Transforms", completion=4)  # 40% done
    planning.assign(ch.id, LAST_WEEK)

    week = planning.week_plan(TODAY)
    titles = [item.title for item in week.backlog]
    assert "Fourier Transforms" in titles                 # carried over
    assert week.backlog[0].planned_date == LAST_WEEK       # keeps original date


def test_past_day_incomplete_goes_to_today_backlog(subjects, planning):
    ch = _chapter(subjects, "Gradient Descent", completion=5)
    planning.assign(ch.id, YESTERDAY)

    day = planning.today_plan(TODAY)
    titles = [item.title for item in day.backlog]
    assert "Gradient Descent" in titles
    assert day.backlog[0].planned_date == YESTERDAY


def test_completed_item_not_in_either_backlog(subjects, planning):
    ch = _chapter(subjects, "Finished Topic", completion=10)  # done
    planning.assign(ch.id, LAST_WEEK)
    assert planning.today_plan(TODAY).backlog == []
    assert planning.week_plan(TODAY).backlog == []


# --- Rendered page level (real clock, via HTTP) -------------------------
def _seed_via_http(client, title, planned_date, completion=None):
    client.post("/subjects", data={"name": "Subj"}, follow_redirects=True)
    # subject/module ids increment; fetch the just-made subject page is not needed —
    # we create module+chapter under the latest ids.
    # To keep ids predictable, create everything fresh per call is avoided; instead
    # the caller controls order. Here we assume a clean DB per test.
    client.post("/subjects/1/modules", data={"name": "Mod"}, follow_redirects=True)
    client.post(
        "/modules/1/chapters",
        data={"title": title, "kind": "video", "duration_minutes": "120"},
        follow_redirects=True,
    )
    if completion is not None:
        client.post("/chapters/1/completion", data={"completion": str(completion)},
                    follow_redirects=True)
    client.post("/chapters/1/plan", data={"planned_date": planned_date.isoformat()},
                follow_redirects=True)


def test_today_page_shows_backlog_heading(auth_client):
    today = date.today()
    yesterday = today - timedelta(days=1)
    _seed_via_http(auth_client, "Backprop Chapter", yesterday, completion=5)

    page = auth_client.get("/today").get_data(as_text=True)
    assert "Backprop Chapter" in page                 # heading is shown
    assert "Backlog" in page
    assert f"carried from {yesterday.isoformat()}" in page  # marked as carried over


def test_week_page_shows_backlog_heading(auth_client):
    today = date.today()
    last_week = today - timedelta(days=8)
    _seed_via_http(auth_client, "Eigen Chapter", last_week, completion=3)

    page = auth_client.get("/week").get_data(as_text=True)
    assert "Eigen Chapter" in page
    assert "Weekly backlog" in page
    assert f"carried from {last_week.isoformat()}" in page


def test_finished_item_absent_from_today_page(auth_client):
    today = date.today()
    yesterday = today - timedelta(days=1)
    _seed_via_http(auth_client, "Done Chapter", yesterday, completion=10)

    page = auth_client.get("/today").get_data(as_text=True)
    assert "carried from" not in page                 # nothing carried over
