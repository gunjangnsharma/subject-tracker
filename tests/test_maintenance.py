"""Tests for the duplicate-plan squash maintenance helper."""

from datetime import date

import pytest

from tracker.maintenance import squash_duplicate_plans
from tracker.repositories.plan_repository import PlanRepository
from tracker.services.subject_service import SubjectService


@pytest.fixture
def subjects(session, user_id):
    return SubjectService(session, user_id)


def _chapter(subjects, title="C"):
    subject = subjects.add_subject(f"S-{title}")
    module = subjects.add_module(subject.id, "M")
    return subjects.add_chapter(module.id, title, "video", 60)


def test_squash_keeps_most_recent_and_removes_rest(session, subjects, user_id):
    ch = _chapter(subjects)
    plans = PlanRepository(session, user_id)
    # Insert duplicates directly (bypassing the service upsert) to simulate old data.
    plans.add(ch.id, date(2026, 8, 1))
    plans.add(ch.id, date(2026, 8, 2))
    newest = plans.add(ch.id, date(2026, 8, 3))   # highest id -> should survive
    session.commit()

    result = squash_duplicate_plans(session)
    session.commit()

    assert result.chapters_affected == 1
    assert result.assignments_removed == 2
    remaining = plans.for_chapter(ch.id)
    assert len(remaining) == 1
    assert remaining[0].id == newest.id
    assert remaining[0].planned_date == date(2026, 8, 3)


def test_squash_leaves_single_assignment_untouched(session, subjects, user_id):
    ch = _chapter(subjects)
    plans = PlanRepository(session, user_id)
    plans.add(ch.id, date(2026, 8, 1))
    session.commit()

    result = squash_duplicate_plans(session)
    session.commit()

    assert result.chapters_affected == 0
    assert result.assignments_removed == 0
    assert len(plans.for_chapter(ch.id)) == 1


def test_squash_is_idempotent(session, subjects, user_id):
    ch = _chapter(subjects)
    plans = PlanRepository(session, user_id)
    plans.add(ch.id, date(2026, 8, 1))
    plans.add(ch.id, date(2026, 8, 2))
    session.commit()

    squash_duplicate_plans(session)
    session.commit()
    # Running again finds nothing to do.
    result = squash_duplicate_plans(session)
    session.commit()
    assert result.assignments_removed == 0
    assert len(plans.for_chapter(ch.id)) == 1


def test_squash_handles_multiple_chapters(session, subjects, user_id):
    a = _chapter(subjects, "A")
    b = _chapter(subjects, "B")
    c = _chapter(subjects, "C")  # single assignment, untouched
    plans = PlanRepository(session, user_id)
    plans.add(a.id, date(2026, 8, 1)); plans.add(a.id, date(2026, 8, 2))
    plans.add(b.id, date(2026, 8, 1)); plans.add(b.id, date(2026, 8, 2)); plans.add(b.id, date(2026, 8, 3))
    plans.add(c.id, date(2026, 8, 1))
    session.commit()

    result = squash_duplicate_plans(session)
    session.commit()

    assert result.chapters_affected == 2       # a and b
    assert result.assignments_removed == 3      # 1 from a + 2 from b
    assert len(plans.for_chapter(a.id)) == 1
    assert len(plans.for_chapter(b.id)) == 1
    assert len(plans.for_chapter(c.id)) == 1
