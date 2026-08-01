"""Tests for JSON export / import (backup & restore)."""

import io
import json
from datetime import date

import pytest

from tracker.services.auth_service import AuthService
from tracker.services.backup_service import (
    BACKUP_FORMAT,
    BACKUP_VERSION,
    BackupError,
    BackupService,
)
from tracker.services.planning_service import PlanningService
from tracker.services.subject_service import SubjectService

DAY = date(2026, 8, 5)
PLAN_DAY = date(2026, 8, 3)


def _populate(session, user_id):
    subjects = SubjectService(session, user_id)
    planning = PlanningService(session, user_id)
    subject = subjects.add_subject("Machine Learning")
    module = subjects.add_module(subject.id, "Linear Algebra")
    ch = subjects.add_chapter(module.id, "Vectors", "video", 120)
    subjects.set_completion(ch.id, 5, when=DAY)   # 60 min studied -> activity
    planning.assign(ch.id, PLAN_DAY)               # a plan date
    # a text chapter too
    subjects.add_chapter(module.id, "Notes", "text", 40)
    return subject


# --- Export --------------------------------------------------------------
def test_export_structure(session, user_id):
    _populate(session, user_id)
    data = BackupService(session, user_id).export_data()

    assert data["format"] == BACKUP_FORMAT
    assert data["version"] == BACKUP_VERSION
    assert "exported_at" in data
    assert data["user"]["username"] == "tester"

    subj = data["subjects"][0]
    assert subj["name"] == "Machine Learning"
    module = subj["modules"][0]
    chapter = module["chapters"][0]
    assert chapter["title"] == "Vectors"
    assert chapter["kind"] == "video"
    assert chapter["duration_minutes"] == 120
    assert chapter["completion"] == 5
    assert chapter["plan_dates"] == [PLAN_DAY.isoformat()]
    assert chapter["activity"] == [{"occurred_on": DAY.isoformat(), "minutes_delta": 60.0}]


def test_export_is_json_serialisable(session, user_id):
    _populate(session, user_id)
    data = BackupService(session, user_id).export_data()
    # Round-trips through JSON without error.
    assert json.loads(json.dumps(data))["format"] == BACKUP_FORMAT


# --- Import round-trip ---------------------------------------------------
def test_export_then_import_into_another_user(session):
    auth = AuthService(session)
    alice = auth.register("alice", "secret123")
    bob = auth.register("bob", "secret123")

    _populate(session, alice.id)
    exported = BackupService(session, alice.id).export_data()

    summary = BackupService(session, bob.id).import_data(exported)
    assert summary.subjects == 1
    assert summary.modules == 1
    assert summary.chapters == 2
    assert summary.plans == 1
    assert summary.activity == 1

    # Bob's data now mirrors Alice's (ignoring the user field / timestamp).
    bob_export = BackupService(session, bob.id).export_data()
    assert bob_export["subjects"] == exported["subjects"]


def test_import_preserves_completion_without_extra_activity(session, user_id):
    payload = {
        "format": BACKUP_FORMAT,
        "version": BACKUP_VERSION,
        "subjects": [
            {"name": "S", "modules": [
                {"name": "M", "chapters": [
                    {"title": "C", "kind": "video", "duration_minutes": 100,
                     "completion": 7, "plan_dates": [], "activity": []}
                ]}
            ]}
        ],
    }
    BackupService(session, user_id).import_data(payload)
    out = BackupService(session, user_id).export_data()
    chapter = out["subjects"][0]["modules"][0]["chapters"][0]
    assert chapter["completion"] == 7
    assert chapter["activity"] == []   # import must not fabricate activity


def test_import_keeps_one_plan_date_per_chapter(session, user_id):
    # Older backups may carry several plan_dates; import keeps only the first,
    # honouring the one-date-per-chapter rule.
    payload = {
        "format": BACKUP_FORMAT, "version": BACKUP_VERSION,
        "subjects": [{"name": "S", "modules": [
            {"name": "M", "chapters": [
                {"title": "C", "kind": "video", "duration_minutes": 60, "completion": 0,
                 "plan_dates": ["2026-08-03", "2026-08-05"], "activity": []}
            ]}
        ]}],
    }
    summary = BackupService(session, user_id).import_data(payload)
    assert summary.plans == 1
    out = BackupService(session, user_id).export_data()
    assert out["subjects"][0]["modules"][0]["chapters"][0]["plan_dates"] == ["2026-08-03"]


def test_import_is_additive(session, user_id):
    subjects = SubjectService(session, user_id)
    subjects.add_subject("Existing")
    payload = {
        "format": BACKUP_FORMAT, "version": BACKUP_VERSION,
        "subjects": [{"name": "Imported", "modules": []}],
    }
    BackupService(session, user_id).import_data(payload)
    names = sorted(s.name for s in subjects.list_subjects())
    assert names == ["Existing", "Imported"]


# --- Validation ----------------------------------------------------------
@pytest.mark.parametrize("bad", [
    "not a dict",
    {"format": "something-else", "version": 1, "subjects": []},
    {"format": BACKUP_FORMAT, "version": 999, "subjects": []},
    {"format": BACKUP_FORMAT, "version": BACKUP_VERSION, "subjects": "nope"},
])
def test_invalid_envelope_rejected(session, user_id, bad):
    with pytest.raises(BackupError):
        BackupService(session, user_id).import_data(bad)


def test_invalid_kind_rejected_and_rolls_back(session, user_id):
    payload = {
        "format": BACKUP_FORMAT, "version": BACKUP_VERSION,
        "subjects": [{"name": "S", "modules": [
            {"name": "M", "chapters": [
                {"title": "C", "kind": "audio", "duration_minutes": 10, "completion": 0}
            ]}
        ]}],
    }
    with pytest.raises(BackupError):
        BackupService(session, user_id).import_data(payload)
    # Atomic: nothing from the failed import persisted.
    assert SubjectService(session, user_id).list_subjects() == []


def test_bad_date_rejected(session, user_id):
    payload = {
        "format": BACKUP_FORMAT, "version": BACKUP_VERSION,
        "subjects": [{"name": "S", "modules": [
            {"name": "M", "chapters": [
                {"title": "C", "kind": "video", "duration_minutes": 10,
                 "completion": 0, "plan_dates": ["not-a-date"]}
            ]}
        ]}],
    }
    with pytest.raises(BackupError):
        BackupService(session, user_id).import_data(payload)


# --- Routes --------------------------------------------------------------
def test_export_route_returns_download(auth_client):
    auth_client.post("/subjects", data={"name": "RouteSubj"}, follow_redirects=True)
    resp = auth_client.get("/export")
    assert resp.status_code == 200
    assert resp.mimetype == "application/json"
    assert "attachment" in resp.headers["Content-Disposition"]
    body = json.loads(resp.get_data(as_text=True))
    assert body["subjects"][0]["name"] == "RouteSubj"


def test_import_route_adds_data(auth_client):
    payload = {
        "format": BACKUP_FORMAT, "version": BACKUP_VERSION,
        "subjects": [{"name": "FromFile", "modules": []}],
    }
    data = {
        "backup": (io.BytesIO(json.dumps(payload).encode()), "backup.json"),
    }
    resp = auth_client.post("/import", data=data,
                            content_type="multipart/form-data", follow_redirects=True)
    assert resp.status_code == 200
    assert "FromFile" in auth_client.get("/subjects").get_data(as_text=True)


def test_import_route_rejects_bad_json(auth_client):
    data = {"backup": (io.BytesIO(b"{not json"), "backup.json")}
    resp = auth_client.post("/import", data=data,
                            content_type="multipart/form-data", follow_redirects=True)
    assert b"not valid JSON" in resp.data
