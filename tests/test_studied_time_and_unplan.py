"""Studied-time accounting and removing a chapter from the plan.

Two related concerns:

1. **Net study time.** Repeatedly ticking a chapter Done and un-ticking it used
   to inflate "studied today" and the week's activity without bound, because the
   dashboard summed only *positive* deltas. Progress must net out.
2. **Unplanning.** A chapter planned by mistake can be removed from the plan from
   `/today` or `/week`, and the dashboard counts must follow — without rewriting
   any completion or activity history.
"""

from __future__ import annotations

from datetime import date, timedelta

import pytest

from tracker import domain
from tracker.repositories.activity_repository import ActivityRepository
from tracker.services.auth_service import AuthService
from tracker.services.dashboard_service import DashboardService
from tracker.services.planning_service import PlanningService
from tracker.services.subject_service import SubjectService

TODAY = date(2026, 8, 5)          # a Wednesday, so the ISO week is unambiguous


@pytest.fixture
def tracked(session, user_id):
    """A 60-minute chapter, plus the services needed to drive and read it."""
    subjects = SubjectService(session, user_id)
    subject = subjects.add_subject("S")
    module = subjects.add_module(subject.id, "M")
    chapter = subjects.add_chapter(module.id, "C", "video", 60)
    return {
        "subjects": subjects,
        "planning": PlanningService(session, user_id),
        "dashboard": DashboardService(session, user_id),
        "activity": ActivityRepository(session, user_id),
        "chapter": chapter,
        "module": module,
        "subject": subject,
    }


# --- Pure domain rule -------------------------------------------------------

def test_net_studied_minutes_cancels_out_a_toggle():
    """+60 then -60 nets to 0 — no time was actually studied."""
    assert domain.net_studied_minutes([60.0, -60.0]) == 0.0
    assert domain.net_studied_minutes([60.0, -60.0] * 5) == 0.0


def test_net_studied_minutes_keeps_real_progress():
    assert domain.net_studied_minutes([45.0]) == 45.0
    assert domain.net_studied_minutes([30.0, 15.0]) == 45.0
    assert domain.net_studied_minutes([60.0, -20.0]) == 40.0


def test_net_studied_minutes_never_negative():
    """A day whose corrections outweigh its progress shows 0, not a negative bar."""
    assert domain.net_studied_minutes([-60.0]) == 0.0
    assert domain.net_studied_minutes([20.0, -50.0]) == 0.0


def test_net_studied_minutes_of_nothing_is_zero():
    assert domain.net_studied_minutes([]) == 0.0


# --- The reported bug -------------------------------------------------------

def test_toggling_done_does_not_inflate_studied_today(tracked):
    """The regression: five Done/undone cycles reported 300 minutes studied."""
    subjects, dashboard = tracked["subjects"], tracked["dashboard"]
    chapter = tracked["chapter"]

    for _ in range(5):
        subjects.set_completed_minutes(chapter.id, 60, when=TODAY)   # Done
        subjects.set_completed_minutes(chapter.id, 0, when=TODAY)    # un-Done

    view = dashboard.build(TODAY)
    assert subjects.get_chapter(chapter.id).completed_minutes == 0
    assert view.today.studied_minutes == 0.0
    assert view.week.studied_total == 0.0


def test_toggling_done_does_not_inflate_the_week_chart(tracked):
    subjects, dashboard = tracked["subjects"], tracked["dashboard"]
    chapter = tracked["chapter"]

    for _ in range(3):
        subjects.set_completed_minutes(chapter.id, 60, when=TODAY)
        subjects.set_completed_minutes(chapter.id, 0, when=TODAY)

    view = dashboard.build(TODAY)
    wednesday = next(d for d in view.week.days if d.day == TODAY)
    assert wednesday.studied_minutes == 0.0


def test_ending_on_done_counts_once_however_many_toggles(tracked):
    """Toggle a few times but leave it Done: exactly one chapter's worth."""
    subjects, dashboard = tracked["subjects"], tracked["dashboard"]
    chapter = tracked["chapter"]

    for _ in range(4):
        subjects.set_completed_minutes(chapter.id, 60, when=TODAY)
        subjects.set_completed_minutes(chapter.id, 0, when=TODAY)
    subjects.set_completed_minutes(chapter.id, 60, when=TODAY)      # finish Done

    view = dashboard.build(TODAY)
    assert view.today.studied_minutes == 60.0
    assert view.week.studied_total == 60.0


def test_reducing_completion_reduces_studied_time(tracked):
    """Set 60, then correct down to 20 -> 20 studied, not 60."""
    subjects, dashboard = tracked["subjects"], tracked["dashboard"]
    chapter = tracked["chapter"]

    subjects.set_completed_minutes(chapter.id, 60, when=TODAY)
    subjects.set_completed_minutes(chapter.id, 20, when=TODAY)

    assert dashboard.build(TODAY).today.studied_minutes == 20.0


def test_activity_log_still_records_both_directions(tracked):
    """The fix is in the *aggregation*; the event log stays a full audit trail."""
    subjects, activity = tracked["subjects"], tracked["activity"]
    chapter = tracked["chapter"]

    subjects.set_completed_minutes(chapter.id, 60, when=TODAY)
    subjects.set_completed_minutes(chapter.id, 0, when=TODAY)

    deltas = sorted(e.minutes_delta for e in activity.on_date(TODAY))
    assert deltas == [-60.0, 60.0]      # both kept, they simply net to zero


def test_undoing_yesterdays_work_does_not_make_today_negative(tracked):
    """A correction dated today can't drive today's bar below zero.

    Deliberate consequence: netting is **per day**, so yesterday keeps the +60 it
    genuinely earned and today floors its -60 to 0 — the week therefore still
    reads 60. That is the honest reading of "how much did I study each day";
    the reduction shows up in the chapter's completion (back to 0), not by
    retroactively erasing a past day's effort.
    """
    subjects, dashboard = tracked["subjects"], tracked["dashboard"]
    chapter = tracked["chapter"]

    subjects.set_completed_minutes(chapter.id, 60, when=TODAY - timedelta(days=1))
    subjects.set_completed_minutes(chapter.id, 0, when=TODAY)       # -60 dated today

    view = dashboard.build(TODAY)
    yesterday = next(d for d in view.week.days if d.day == TODAY - timedelta(days=1))
    wednesday = next(d for d in view.week.days if d.day == TODAY)
    assert view.today.studied_minutes == 0.0     # today: floored, never negative
    assert wednesday.studied_minutes == 0.0
    assert yesterday.studied_minutes == 60.0     # yesterday's real work is kept
    assert subjects.get_chapter(chapter.id).completed_minutes == 0   # progress undone


def test_completion_route_toggling_does_not_inflate_the_dashboard(auth_client):
    """End-to-end through the Done checkbox's endpoint."""
    auth_client.post("/subjects", data={"name": "S"}, follow_redirects=True)
    page = auth_client.get("/subjects").get_data(as_text=True)
    subject_id = int(page.split("/subjects/")[1].split('"')[0])
    auth_client.post(f"/subjects/{subject_id}/modules", data={"name": "M"},
                     follow_redirects=True)
    detail = auth_client.get(f"/subjects/{subject_id}").get_data(as_text=True)
    module_id = int(detail.split("/modules/")[1].split("/")[0])
    auth_client.post(f"/modules/{module_id}/chapters",
                     data={"title": "C", "kind": "video", "duration_minutes": "60"},
                     follow_redirects=True)
    detail = auth_client.get(f"/subjects/{subject_id}").get_data(as_text=True)
    chapter_id = int(detail.split('data-chapter-row="')[1].split('"')[0])

    for _ in range(4):
        auth_client.post(f"/chapters/{chapter_id}/completion",
                         data={"completed_hours": "1", "completed_minutes": "0"},
                         headers={"X-Requested-With": "XMLHttpRequest"})
        auth_client.post(f"/chapters/{chapter_id}/completion",
                         data={"completed_hours": "0", "completed_minutes": "0"},
                         headers={"X-Requested-With": "XMLHttpRequest"})

    # 0m studied, not 240m. The dashboard renders the number in data-to="...".
    dashboard = auth_client.get("/").get_data(as_text=True)
    assert 'data-to="240' not in dashboard
    assert 'data-to="180' not in dashboard
    assert 'data-to="120' not in dashboard


# --- Unplanning -------------------------------------------------------------

def test_unassign_removes_the_plan(tracked):
    planning, chapter = tracked["planning"], tracked["chapter"]
    planning.assign(chapter.id, TODAY)

    assert planning.unassign(chapter.id) is True

    assert planning.today_plan(TODAY).planned == []
    assert planning.today_plan(TODAY).backlog == []


def test_unassign_keeps_progress_and_activity(tracked):
    """Unplanning is not undoing: completion and study history survive."""
    subjects, planning, activity = (
        tracked["subjects"], tracked["planning"], tracked["activity"]
    )
    chapter = tracked["chapter"]
    planning.assign(chapter.id, TODAY)
    subjects.set_completed_minutes(chapter.id, 45, when=TODAY)

    planning.unassign(chapter.id)

    assert subjects.get_chapter(chapter.id).completed_minutes == 45
    assert [e.minutes_delta for e in activity.on_date(TODAY)] == [45.0]


def test_unassign_an_unplanned_chapter_is_a_noop(tracked):
    planning, chapter = tracked["planning"], tracked["chapter"]
    assert planning.unassign(chapter.id) is False


def test_unassign_unknown_chapter_raises(session, user_id):
    with pytest.raises(ValueError):
        PlanningService(session, user_id).unassign(9999)


def test_cannot_unassign_another_users_chapter(session, user_id, tracked):
    planning, chapter = tracked["planning"], tracked["chapter"]
    planning.assign(chapter.id, TODAY)
    other = AuthService(session).register("intruder", "secret123").id

    with pytest.raises(ValueError):
        PlanningService(session, other).unassign(chapter.id)

    assert len(planning.today_plan(TODAY).planned) == 1      # still planned


def test_unassign_removes_it_from_the_backlog(tracked):
    """An overdue mistake can be cleared too."""
    planning, chapter = tracked["planning"], tracked["chapter"]
    planning.assign(chapter.id, TODAY - timedelta(days=3))
    assert len(planning.today_plan(TODAY).backlog) == 1

    planning.unassign(chapter.id)

    assert planning.today_plan(TODAY).backlog == []
    assert planning.rolling_plan(TODAY).backlog == []


def test_unassign_updates_dashboard_counts(tracked):
    planning, dashboard = tracked["planning"], tracked["dashboard"]
    chapter = tracked["chapter"]
    planning.assign(chapter.id, TODAY)

    before = dashboard.build(TODAY)
    assert before.today.planned_count == 1
    assert next(d for d in before.week.days if d.day == TODAY).planned_minutes == 60

    planning.unassign(chapter.id)

    after = dashboard.build(TODAY)
    assert after.today.planned_count == 0
    assert next(d for d in after.week.days if d.day == TODAY).planned_minutes == 0


def test_unassign_does_not_change_studied_time(tracked):
    """Removing the plan must not erase the fact that you studied."""
    subjects, planning, dashboard = (
        tracked["subjects"], tracked["planning"], tracked["dashboard"]
    )
    chapter = tracked["chapter"]
    planning.assign(chapter.id, TODAY)
    subjects.set_completed_minutes(chapter.id, 30, when=TODAY)

    planning.unassign(chapter.id)

    view = dashboard.build(TODAY)
    assert view.today.studied_minutes == 30.0
    assert view.week.studied_total == 30.0


# --- Unplan route + UI ------------------------------------------------------

def _planned_chapter(client, when: date) -> tuple[int, int]:
    client.post("/subjects", data={"name": "S"}, follow_redirects=True)
    page = client.get("/subjects").get_data(as_text=True)
    subject_id = int(page.split("/subjects/")[1].split('"')[0])
    client.post(f"/subjects/{subject_id}/modules", data={"name": "M"},
                follow_redirects=True)
    detail = client.get(f"/subjects/{subject_id}").get_data(as_text=True)
    module_id = int(detail.split("/modules/")[1].split("/")[0])
    client.post(f"/modules/{module_id}/chapters",
                data={"title": "Mistake", "kind": "video", "duration_minutes": "60"},
                follow_redirects=True)
    detail = client.get(f"/subjects/{subject_id}").get_data(as_text=True)
    chapter_id = int(detail.split('data-chapter-row="')[1].split('"')[0])
    client.post(f"/chapters/{chapter_id}/plan", data={"planned_date": when.isoformat()})
    return subject_id, chapter_id


def test_today_and_week_pages_offer_an_unplan_button(auth_client):
    _planned_chapter(auth_client, date.today())
    for path in ("/today", "/week"):
        html = auth_client.get(path).get_data(as_text=True)
        assert "Mistake" in html
        assert "/unplan" in html, f"no unplan button on {path}"


def test_unplan_route_removes_it_from_both_pages(auth_client):
    _, chapter_id = _planned_chapter(auth_client, date.today())

    response = auth_client.post(f"/chapters/{chapter_id}/unplan")
    assert response.status_code == 302

    for path in ("/today", "/week"):
        assert "Mistake" not in auth_client.get(path).get_data(as_text=True)


def test_unplan_route_keeps_the_chapter_itself(auth_client):
    subject_id, chapter_id = _planned_chapter(auth_client, date.today())
    auth_client.post(f"/chapters/{chapter_id}/unplan")
    # Still on the subject page, just no longer planned.
    detail = auth_client.get(f"/subjects/{subject_id}").get_data(as_text=True)
    assert "Mistake" in detail
    assert "Not planned" in detail


def test_unplan_route_ajax_returns_json(auth_client):
    _, chapter_id = _planned_chapter(auth_client, date.today())
    response = auth_client.post(
        f"/chapters/{chapter_id}/unplan",
        headers={"X-Requested-With": "XMLHttpRequest"},
    )
    assert response.status_code == 200
    assert response.get_json() == {"removed": True, "chapter_id": chapter_id}


def test_unplan_route_requires_login(client):
    assert client.post("/chapters/1/unplan").status_code == 302


def test_unplan_route_flashes_for_an_unknown_chapter(auth_client):
    response = auth_client.post("/chapters/9999/unplan", follow_redirects=True)
    assert response.status_code == 200
    assert "Chapter not found" in response.get_data(as_text=True)
