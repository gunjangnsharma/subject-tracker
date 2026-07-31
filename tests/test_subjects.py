"""Integration tests for subject/module/chapter service + roll-ups
(test plan sections 2.2 and 2.3)."""

import pytest

from tracker.services.subject_service import SubjectService


@pytest.fixture
def service(session, user_id):
    return SubjectService(session, user_id)


def test_add_and_list_subject(service):  # S1
    service.add_subject("Math")
    names = [s.name for s in service.list_subjects()]
    assert "Math" in names


def test_add_module_and_chapter(service):  # S2, S3
    subject = service.add_subject("Physics")
    module = service.add_module(subject.id, "Mechanics")
    assert module.subject_id == subject.id

    chapter = service.add_chapter(module.id, "Newton's laws", "video", 90)
    assert chapter.completion == 0
    assert chapter.duration_minutes == 90


def test_update_completion_reflects_minutes(service):  # S4
    subject = service.add_subject("Chem")
    module = service.add_module(subject.id, "Atoms")
    chapter = service.add_chapter(module.id, "Orbitals", "video", 120)

    service.set_completion(chapter.id, 5)
    assert service.get_chapter(chapter.id).progress.completed_minutes == 60


def test_completion_is_clamped(service):
    subject = service.add_subject("Bio")
    module = service.add_module(subject.id, "Cells")
    chapter = service.add_chapter(module.id, "Mitosis", "text", 30)
    service.set_completion(chapter.id, 99)
    assert service.get_chapter(chapter.id).completion == 10


def test_module_and_subject_rollup(service):  # R1, R2
    subject = service.add_subject("Stats")
    m = service.add_module(subject.id, "Distributions")
    c1 = service.add_chapter(m.id, "Normal", "video", 60)
    c2 = service.add_chapter(m.id, "Poisson", "video", 120)
    service.set_completion(c1.id, 10)   # 60 done
    service.set_completion(c2.id, 5)    # 60 done

    module = service.get_module(m.id)
    assert module.progress.total_minutes == 180
    assert module.progress.completed_minutes == 120
    assert module.progress.remaining_minutes == 60

    subject = service.get_subject(subject.id)
    assert subject.progress.total_minutes == 180
    assert subject.progress.completed_minutes == 120


def test_empty_module_rollup(service):  # R3
    subject = service.add_subject("Empty")
    m = service.add_module(subject.id, "Nothing")
    module = service.get_module(m.id)
    assert module.progress.total_minutes == 0
    assert module.progress.percent == 0.0


def test_delete_subject_cascades(service):  # R4
    subject = service.add_subject("Temp")
    m = service.add_module(subject.id, "Mod")
    service.add_chapter(m.id, "Ch", "text", 10)
    sid = subject.id

    service.delete_subject(sid)
    assert service.get_subject(sid) is None
    assert service.get_module(m.id) is None


def test_delete_chapter_recalculates(service):  # S5
    subject = service.add_subject("Del")
    m = service.add_module(subject.id, "Mod")
    c1 = service.add_chapter(m.id, "Keep", "video", 60)
    c2 = service.add_chapter(m.id, "Drop", "video", 60)

    service.delete_chapter(c2.id)
    module = service.get_module(m.id)
    assert module.progress.total_minutes == 60
    assert [c.id for c in module.chapters] == [c1.id]


def test_invalid_inputs_raise(service):
    with pytest.raises(ValueError):
        service.add_subject("   ")
    subject = service.add_subject("V")
    m = service.add_module(subject.id, "M")
    with pytest.raises(ValueError):
        service.add_chapter(m.id, "bad kind", "audio", 10)
