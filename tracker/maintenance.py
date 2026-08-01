"""One-off maintenance helpers.

`squash_duplicate_plans` enforces the "one date per chapter" rule retroactively
on data created before that rule existed. It keeps the **most recent** plan
assignment per chapter (highest id — the last one planned) and deletes the rest.
It does NOT commit; the caller owns the transaction (so a dry-run can roll back).

`backfill_chapter_positions` gives real display positions to chapters written
before `Chapter.position` existed (they all arrive as 0). Same contract: no
commit, caller owns the transaction.
"""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from tracker.models import Chapter, PlanAssignment


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


@dataclass(frozen=True)
class BackfillResult:
    modules_affected: int       # modules whose chapters were renumbered
    chapters_renumbered: int    # chapters given a new position value


def backfill_chapter_positions(session: Session) -> BackfillResult:
    """Give each module's chapters distinct 0-based positions.

    Chapters created before ``Chapter.position`` existed all default to 0, which
    makes "swap with my neighbour" meaningless. This assigns positions from the
    order those chapters currently display in (``position, id`` — so for legacy
    rows, id order: the order they were added).

    Only renumbers modules that actually need it: a module whose positions are
    already ``0..n-1`` is left untouched, which makes this idempotent and safe to
    run on every startup. Flushes but does not commit.
    """
    module_ids = list(session.execute(select(Chapter.module_id).distinct()).scalars())

    modules_affected = 0
    renumbered = 0
    for module_id in module_ids:
        chapters = list(
            session.scalars(
                select(Chapter)
                .where(Chapter.module_id == module_id)
                .order_by(Chapter.position, Chapter.id)
            )
        )
        # Already a clean 0..n-1 sequence? Nothing to do for this module.
        if [c.position for c in chapters] == list(range(len(chapters))):
            continue
        modules_affected += 1
        for index, chapter in enumerate(chapters):
            if chapter.position != index:
                chapter.position = index
                renumbered += 1

    session.flush()
    return BackfillResult(modules_affected=modules_affected, chapters_renumbered=renumbered)
