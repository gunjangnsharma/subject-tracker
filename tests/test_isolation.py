"""Multi-user data isolation and admin-view tests.

The critical security property: one user can never read or mutate another
user's subjects/modules/chapters/plans, even by guessing ids.
"""

from datetime import date

import pytest

from tracker.services.auth_service import AuthService
from tracker.services.dashboard_service import DashboardService
from tracker.services.planning_service import PlanningService
from tracker.services.subject_service import SubjectService

TODAY = date(2026, 8, 5)


@pytest.fixture
def two_users(session):
    auth = AuthService(session)
    a = auth.register("alice", "secret123")
    b = auth.register("bob", "secret123")
    return a.id, b.id


def test_list_is_scoped_per_user(session, two_users):
    a_id, b_id = two_users
    SubjectService(session, a_id).add_subject("Alice Math")
    SubjectService(session, b_id).add_subject("Bob Physics")

    a_names = [s.name for s in SubjectService(session, a_id).list_subjects()]
    b_names = [s.name for s in SubjectService(session, b_id).list_subjects()]
    assert a_names == ["Alice Math"]
    assert b_names == ["Bob Physics"]


def test_cannot_get_other_users_subject(session, two_users):
    a_id, b_id = two_users
    subject = SubjectService(session, a_id).add_subject("Alice Only")
    # Bob tries to fetch Alice's subject by id -> denied.
    assert SubjectService(session, b_id).get_subject(subject.id) is None


def test_cannot_edit_other_users_chapter(session, two_users):
    a_id, b_id = two_users
    a = SubjectService(session, a_id)
    subject = a.add_subject("A")
    module = a.add_module(subject.id, "M")
    chapter = a.add_chapter(module.id, "Ch", "video", 60)

    # Bob cannot see or change Alice's chapter completion.
    b = SubjectService(session, b_id)
    assert b.get_chapter(chapter.id) is None
    with pytest.raises(ValueError):
        b.set_completion(chapter.id, 10)


def test_cannot_plan_other_users_chapter(session, two_users):
    a_id, b_id = two_users
    a = SubjectService(session, a_id)
    subject = a.add_subject("A")
    module = a.add_module(subject.id, "M")
    chapter = a.add_chapter(module.id, "Ch", "video", 60)

    with pytest.raises(ValueError):
        PlanningService(session, b_id).assign(chapter.id, TODAY)


def test_dashboard_is_scoped(session, two_users):
    a_id, b_id = two_users
    a = SubjectService(session, a_id)
    subject = a.add_subject("A")
    module = a.add_module(subject.id, "M")
    ch = a.add_chapter(module.id, "Ch", "video", 60)
    a.set_completion(ch.id, 10, when=TODAY)

    a_view = DashboardService(session, a_id).build(TODAY)
    b_view = DashboardService(session, b_id).build(TODAY)
    assert a_view.overall.total_minutes == 60
    assert b_view.overall.total_minutes == 0        # Bob sees nothing of Alice's
    assert b_view.subjects == []


# --- Admin views ---------------------------------------------------------
def test_admin_can_see_overview(client, session):
    AuthService(session).register("boss", "secret123", role="admin")
    client.post("/login", data={"username": "boss", "password": "secret123"})
    resp = client.get("/admin")
    assert resp.status_code == 200
    assert b"Admin overview" in resp.data


def test_regular_user_forbidden_from_admin(auth_client):
    # auth_client is a normal (non-admin) user.
    assert auth_client.get("/admin").status_code == 403


def test_admin_link_hidden_for_regular_user(auth_client):
    body = auth_client.get("/").get_data(as_text=True)
    assert 'href="/admin"' not in body
