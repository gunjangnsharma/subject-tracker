"""Data access for Chapter, scoped to one user via Module -> Subject."""

from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from tracker.models import Chapter


class ChapterRepository:
    def __init__(self, session: Session, user_id: int) -> None:
        self._session = session
        self._user_id = user_id

    def add(self, module_id: int, title: str, kind: str, duration_minutes: int) -> Chapter:
        chapter = Chapter(
            module_id=module_id,
            title=title,
            kind=kind,
            duration_minutes=duration_minutes,
            completed_minutes=0,
            # New chapters land at the end of their module's list.
            position=self.next_position(module_id),
        )
        self._session.add(chapter)
        self._session.flush()
        return chapter

    def get(self, chapter_id: int) -> Chapter | None:
        chapter = self._session.get(Chapter, chapter_id)
        if chapter is None or chapter.module.subject.user_id != self._user_id:
            return None
        return chapter

    def siblings(self, module_id: int) -> list[Chapter]:
        """Every chapter in ``module_id``, in display order (position, then id).

        Same ordering as ``Module.chapters``, expressed as a query so reordering
        can work from an explicit, indexable list.
        """
        return list(
            self._session.scalars(
                select(Chapter)
                .where(Chapter.module_id == module_id)
                .order_by(Chapter.position, Chapter.id)
            )
        )

    def next_position(self, module_id: int) -> int:
        """The position after the module's current last chapter (0 when empty)."""
        highest = self._session.scalar(
            select(func.max(Chapter.position)).where(Chapter.module_id == module_id)
        )
        return 0 if highest is None else highest + 1

    def set_positions(self, positions: dict[Chapter, int]) -> None:
        """Assign new positions to several chapters at once."""
        for chapter, position in positions.items():
            chapter.position = position
        self._session.flush()

    def set_completed(self, chapter: Chapter, completed_minutes: int) -> Chapter:
        # Domain clamping happens in the service; store what we are given.
        chapter.completed_minutes = completed_minutes
        self._session.flush()
        return chapter

    def delete(self, chapter: Chapter) -> None:
        self._session.delete(chapter)
