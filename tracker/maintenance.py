"""One-off maintenance helpers.

`squash_duplicate_plans` enforces the "one date per chapter" rule retroactively
on data created before that rule existed. It keeps the **most recent** plan
assignment per chapter (highest id — the last one planned) and deletes the rest.
It does NOT commit; the caller owns the transaction (so a dry-run can roll back).
"""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from tracker.models import PlanAssignment


@dataclass(frozen=True)
class SquashResult:
    chapters_affected: int      # chapters that had more than one assignment
    assignments_removed: int    # duplicate assignments deleted


def squash_duplicate_plans(session: Session) -> SquashResult:
    """Collapse duplicate plan assignments so each chapter has at most one.

    Scans every chapter (all users). For any chapter with more than one
    assignment, keeps the one with the highest id (the most recently planned)
    and deletes the others. Flushes but does not commit.
    """
    duplicate_chapter_ids = list(
        session.execute(
            select(PlanAssignment.chapter_id)
            .group_by(PlanAssignment.chapter_id)
            .having(func.count() > 1)
        ).scalars()
    )

    removed = 0
    for chapter_id in duplicate_chapter_ids:
        rows = list(
            session.scalars(
                select(PlanAssignment)
                .where(PlanAssignment.chapter_id == chapter_id)
                .order_by(PlanAssignment.id.desc())
            )
        )
        for extra in rows[1:]:      # keep rows[0] (highest id = most recent)
            session.delete(extra)
            removed += 1

    session.flush()
    return SquashResult(
        chapters_affected=len(duplicate_chapter_ids),
        assignments_removed=removed,
    )
