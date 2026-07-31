"""Data access for Chapter."""

from __future__ import annotations

from sqlalchemy.orm import Session

from tracker.models import Chapter


class ChapterRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def add(self, module_id: int, title: str, kind: str, duration_minutes: int) -> Chapter:
        chapter = Chapter(
            module_id=module_id,
            title=title,
            kind=kind,
            duration_minutes=duration_minutes,
            completion=0,
        )
        self._session.add(chapter)
        self._session.flush()
        return chapter

    def get(self, chapter_id: int) -> Chapter | None:
        return self._session.get(Chapter, chapter_id)

    def set_completion(self, chapter: Chapter, completion: int) -> Chapter:
        # Domain clamping happens in the service; store what we are given.
        chapter.completion = completion
        self._session.flush()
        return chapter

    def delete(self, chapter: Chapter) -> None:
        self._session.delete(chapter)
