"""Tests for study-activity logging on completion changes."""

from datetime import date

import pytest

from tracker.repositories.activity_repository import ActivityRepository
from tracker.services.subject_service import SubjectService

DAY = date(2026, 8, 5)


@pytest.fixture
def service(session, user_id):
    return SubjectService(session, user_id)


def _chapter(service, duration=120):
    subject = service.add_subject("S")
    module = service.add_module(subject.id, "M")
    return service.add_chapter(module.id, "Ch", "video", duration)


def test_progress_logs_positive_delta(service, session, user_id):
    ch = _chapter(service, duration=120)
    service.set_completed_minutes(ch.id, 60, when=DAY)  # 0 -> 60 min
    events = ActivityRepository(session, user_id).on_date(DAY)
    assert len(events) == 1
    assert events[0].minutes_delta == 60


def test_reducing_completion_logs_negative_delta(service, session, user_id):
    ch = _chapter(service, duration=120)
    service.set_completed_minutes(ch.id, 60, when=DAY)   # 0 -> 60 min  (+60)
    service.set_completed_minutes(ch.id, 36, when=DAY)   # 60 -> 36 min (-24)
    deltas = sorted(e.minutes_delta for e in ActivityRepository(session, user_id).on_date(DAY))
    assert deltas == [-24, 60]


def test_no_change_logs_nothing(service, session, user_id):
    ch = _chapter(service, duration=120)
    service.set_completed_minutes(ch.id, 60, when=DAY)
    service.set_completed_minutes(ch.id, 60, when=DAY)  # no delta
    assert len(ActivityRepository(session, user_id).on_date(DAY)) == 1


def test_when_defaults_to_today(service, session, user_id):
    ch = _chapter(service, duration=60)
    service.set_completed_minutes(ch.id, 60)  # no `when` -> today
    assert len(ActivityRepository(session, user_id).on_date(date.today())) == 1
