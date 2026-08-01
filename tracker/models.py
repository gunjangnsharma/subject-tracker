"""ORM models: Subject -> Module -> Chapter, plus PlanAssignment.

Roll-up totals are intentionally **not** stored here. They are computed from
chapters (see ``tracker.domain``) so aggregates can never drift out of sync.
Each model exposes a small ``.progress`` helper that returns a domain.Progress.
"""

from __future__ import annotations

from datetime import date

from sqlalchemy import Date, Enum, Float, ForeignKey, Index, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from tracker import domain
from tracker.database import Base

#: Chapter types. Adding one needs no database migration: the Enum column is
#: created WITHOUT a CHECK constraint (SQLAlchemy 2.0's `create_constraint=False`
#: default), so an existing database accepts a new value immediately. Validation
#: lives in the services, which check membership of this tuple. Each kind needs a
#: matching `.pill-<kind>` rule in style.css.
CHAPTER_KINDS = ("video", "text", "quiz")
USER_ROLES = ("user", "admin")


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    username: Mapped[str] = mapped_column(String(80), unique=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[str] = mapped_column(Enum(*USER_ROLES, name="user_role"), default="user")

    subjects: Mapped[list["Subject"]] = relationship(
        back_populates="user",
        cascade="all, delete-orphan",
        order_by="Subject.name",
    )

    @property
    def is_admin(self) -> bool:
        return self.role == "admin"


class Subject(Base):
    __tablename__ = "subjects"
    # Every query is scoped to the logged-in user, so this index carries almost
    # all subject lookups. SQLite does NOT index foreign keys automatically.
    __table_args__ = (Index("ix_subjects_user_id", "user_id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)

    user: Mapped["User"] = relationship(back_populates="subjects")
    modules: Mapped[list["Module"]] = relationship(
        back_populates="subject",
        cascade="all, delete-orphan",
        order_by="Module.id",
    )

    @property
    def progress(self) -> domain.Progress:
        return domain.sum_progress([m.progress for m in self.modules])


class Module(Base):
    __tablename__ = "modules"
    __table_args__ = (Index("ix_modules_subject_id", "subject_id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    subject_id: Mapped[int] = mapped_column(
        ForeignKey("subjects.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)

    subject: Mapped["Subject"] = relationship(back_populates="modules")
    chapters: Mapped[list["Chapter"]] = relationship(
        back_populates="module",
        cascade="all, delete-orphan",
        # User-defined order (see Chapter.position). `id` is the tiebreak so rows
        # that share a position — e.g. legacy data backfilled to 0 — keep a
        # stable, insertion-ordered sequence instead of an arbitrary one.
        order_by="Chapter.position, Chapter.id",
    )

    @property
    def progress(self) -> domain.Progress:
        return domain.sum_progress([c.progress for c in self.chapters])


class Chapter(Base):
    __tablename__ = "chapters"
    # (module_id, position) covers both "this module's chapters" and the
    # (position, id) display ordering in one index.
    __table_args__ = (Index("ix_chapters_module_id_position", "module_id", "position"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    module_id: Mapped[int] = mapped_column(
        ForeignKey("modules.id", ondelete="CASCADE"), nullable=False
    )
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    kind: Mapped[str] = mapped_column(Enum(*CHAPTER_KINDS, name="chapter_kind"), default="video")
    duration_minutes: Mapped[int] = mapped_column(Integer, default=0)
    # Minutes of the chapter completed so far (0..duration_minutes).
    completed_minutes: Mapped[int] = mapped_column(Integer, default=0)
    # Display order **within its module** (0-based, ascending). Users reorder
    # chapters with the up/down buttons on the subject page. Not globally
    # unique — positions only mean anything relative to sibling chapters.
    # Defaults to 0 so rows written before this column existed still load; the
    # `Chapter.position, Chapter.id` ordering keeps those stable, and
    # `maintenance.backfill_chapter_positions` assigns them real values.
    position: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")

    module: Mapped["Module"] = relationship(back_populates="chapters")
    assignments: Mapped[list["PlanAssignment"]] = relationship(
        back_populates="chapter",
        cascade="all, delete-orphan",
    )
    events: Mapped[list["ProgressEvent"]] = relationship(
        back_populates="chapter",
        cascade="all, delete-orphan",
    )

    @property
    def progress(self) -> domain.Progress:
        return domain.chapter_progress(self.duration_minutes, self.completed_minutes)

    @property
    def is_done(self) -> bool:
        return domain.is_done(self.duration_minutes, self.completed_minutes)

    # Convenience for the h/m inputs in the UI.
    @property
    def completed_h(self) -> int:
        return self.completed_minutes // 60

    @property
    def completed_m(self) -> int:
        return self.completed_minutes % 60

    @property
    def planned_date(self) -> date | None:
        """The date this chapter is planned for, or None if unplanned.

        A chapter has **at most one** assignment (see PlanningService.assign —
        planning is an upsert), so this collapses the relationship to the single
        date the UI cares about. Older data could carry duplicates; take the
        earliest so the value is deterministic either way.
        """
        if not self.assignments:
            return None
        return min(a.planned_date for a in self.assignments)


class PlanAssignment(Base):
    """A chapter planned for a specific calendar day.

    The week is derived from ``planned_date`` (see domain.week_bounds), so we
    do not store a separate week column. Backlog is computed by comparing
    ``planned_date`` to 'today' at read time — nothing is moved between days.
    """

    __tablename__ = "plan_assignments"
    __table_args__ = (
        # Backlog/day/window queries all filter on planned_date...
        Index("ix_plan_assignments_planned_date", "planned_date"),
        # ...and the one-date-per-chapter upsert looks up by chapter_id.
        Index("ix_plan_assignments_chapter_id", "chapter_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    chapter_id: Mapped[int] = mapped_column(
        ForeignKey("chapters.id", ondelete="CASCADE"), nullable=False
    )
    planned_date: Mapped[date] = mapped_column(Date, nullable=False)

    chapter: Mapped["Chapter"] = relationship(back_populates="assignments")


class ProgressEvent(Base):
    """A record of study activity: how many minutes of progress happened on a day.

    Written whenever a chapter's completion changes. ``minutes_delta`` is the
    change in completed minutes (positive when advancing, negative if reduced).
    This log is what powers 'today' and 'this week' *activity* — the current
    completion value alone cannot tell us *when* the work happened.
    """

    __tablename__ = "progress_events"
    __table_args__ = (
        # The dashboard sums deltas for a day / a week.
        Index("ix_progress_events_occurred_on", "occurred_on"),
        Index("ix_progress_events_chapter_id", "chapter_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    chapter_id: Mapped[int] = mapped_column(
        ForeignKey("chapters.id", ondelete="CASCADE"), nullable=False
    )
    occurred_on: Mapped[date] = mapped_column(Date, nullable=False)
    minutes_delta: Mapped[float] = mapped_column(Float, nullable=False)

    chapter: Mapped["Chapter"] = relationship(back_populates="events")
