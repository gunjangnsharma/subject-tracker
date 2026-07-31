"""Use-cases for subjects, modules and chapters (incl. progress roll-ups)."""

from __future__ import annotations

from datetime import date

from sqlalchemy.orm import Session

from tracker import domain
from tracker.models import CHAPTER_KINDS, Chapter, Subject
from tracker.repositories.activity_repository import ActivityRepository
from tracker.repositories.chapter_repository import ChapterRepository
from tracker.repositories.subject_repository import ModuleRepository, SubjectRepository


class SubjectService:
    """Coordinates subject/module/chapter CRUD and owns the commit boundary."""

    def __init__(self, session: Session) -> None:
        self._session = session
        self._subjects = SubjectRepository(session)
        self._modules = ModuleRepository(session)
        self._chapters = ChapterRepository(session)
        self._activity = ActivityRepository(session)

    # --- Subjects ----------------------------------------------------------
    def add_subject(self, name: str) -> Subject:
        name = (name or "").strip()
        if not name:
            raise ValueError("Subject name is required.")
        subject = self._subjects.add(name)
        self._session.commit()
        return subject

    def list_subjects(self) -> list[Subject]:
        return self._subjects.list_all()

    def get_subject(self, subject_id: int) -> Subject | None:
        return self._subjects.get(subject_id)

    def delete_subject(self, subject_id: int) -> None:
        subject = self._subjects.get(subject_id)
        if subject is None:
            return
        self._subjects.delete(subject)  # cascades to modules + chapters
        self._session.commit()

    # --- Modules -----------------------------------------------------------
    def add_module(self, subject_id: int, name: str):
        name = (name or "").strip()
        if not name:
            raise ValueError("Module name is required.")
        if self._subjects.get(subject_id) is None:
            raise ValueError("Subject not found.")
        module = self._modules.add(subject_id, name)
        self._session.commit()
        return module

    def get_module(self, module_id: int):
        return self._modules.get(module_id)

    def delete_module(self, module_id: int) -> None:
        module = self._modules.get(module_id)
        if module is None:
            return
        self._modules.delete(module)
        self._session.commit()

    # --- Chapters ----------------------------------------------------------
    def add_chapter(self, module_id: int, title: str, kind: str, duration_minutes: int) -> Chapter:
        title = (title or "").strip()
        if not title:
            raise ValueError("Chapter title is required.")
        if kind not in CHAPTER_KINDS:
            raise ValueError(f"kind must be one of {CHAPTER_KINDS}.")
        if duration_minutes < 0:
            raise ValueError("Duration cannot be negative.")
        if self._modules.get(module_id) is None:
            raise ValueError("Module not found.")
        chapter = self._chapters.add(module_id, title, kind, duration_minutes)
        self._session.commit()
        return chapter

    def get_chapter(self, chapter_id: int) -> Chapter | None:
        return self._chapters.get(chapter_id)

    def set_completion(
        self, chapter_id: int, completion: int, when: date | None = None
    ) -> Chapter:
        chapter = self._chapters.get(chapter_id)
        if chapter is None:
            raise ValueError("Chapter not found.")
        # Log the study activity: the change in completed minutes on `when`.
        before = chapter.progress.completed_minutes
        # Clamp via domain rules so out-of-range input never persists.
        self._chapters.set_completion(chapter, domain.clamp_completion(completion))
        delta = chapter.progress.completed_minutes - before
        if delta != 0:
            self._activity.add(chapter_id, when or date.today(), delta)
        self._session.commit()
        return chapter

    def delete_chapter(self, chapter_id: int) -> None:
        chapter = self._chapters.get(chapter_id)
        if chapter is None:
            return
        self._chapters.delete(chapter)
        self._session.commit()
