"""ORM models: Subject -> Module -> Chapter, plus PlanAssignment.

Roll-up totals are intentionally **not** stored here. They are computed from
chapters (see ``tracker.domain``) so aggregates can never drift out of sync.
Each model exposes a small ``.progress`` helper that returns a domain.Progress.
"""

from __future__ import annotations

from datetime import date

from sqlalchemy import Date, Enum, Float, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from tracker import domain
from tracker.database import Base

CHAPTER_KINDS = ("video", "text")
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

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    subject_id: Mapped[int] = mapped_column(
        ForeignKey("subjects.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)

    subject: Mapped["Subject"] = relationship(back_populates="modules")
    chapters: Mapped[list["Chapter"]] = relationship(
        back_populates="module",
        cascade="all, delete-orphan",
        order_by="Chapter.id",
    )

    @property
    def progress(self) -> domain.Progress:
        return domain.sum_progress([c.progress for c in self.chapters])


class Chapter(Base):
    __tablename__ = "chapters"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    module_id: Mapped[int] = mapped_column(
        ForeignKey("modules.id", ondelete="CASCADE"), nullable=False
    )
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    kind: Mapped[str] = mapped_column(Enum(*CHAPTER_KINDS, name="chapter_kind"), default="video")
    duration_minutes: Mapped[int] = mapped_column(Integer, default=0)
    # Minutes of the chapter completed so far (0..duration_minutes).
    completed_minutes: Mapped[int] = mapped_column(Integer, default=0)

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


class PlanAssignment(Base):
    """A chapter planned for a specific calendar day.

    The week is derived from ``planned_date`` (see domain.week_bounds), so we
    do not store a separate week column. Backlog is computed by comparing
    ``planned_date`` to 'today' at read time — nothing is moved between days.
    """

    __tablename__ = "plan_assignments"

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

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    chapter_id: Mapped[int] = mapped_column(
        ForeignKey("chapters.id", ondelete="CASCADE"), nullable=False
    )
    occurred_on: Mapped[date] = mapped_column(Date, nullable=False)
    minutes_delta: Mapped[float] = mapped_column(Float, nullable=False)

    chapter: Mapped["Chapter"] = relationship(back_populates="events")
