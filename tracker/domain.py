"""Pure domain calculations.

This module has **no** dependency on Flask or SQLAlchemy so the business
rules can be unit-tested in isolation and reused anywhere. Everything here
is a plain function operating on numbers/dates.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from typing import Iterable

def clamp_completed(duration_minutes: int, completed_minutes: int) -> int:
    """Clamp completed minutes into the valid 0..duration range.

    A chapter can never be 'more done' than its total length, nor negative.
    """
    return max(0, min(int(duration_minutes), int(completed_minutes)))


def minutes_to_hours(minutes: float) -> float:
    """Convert stored minutes to a decimal-hours number (90 -> 1.5).

    Used for numeric contexts such as chart axes. For user-facing text prefer
    ``format_hm`` (hours + minutes).
    """
    return round(minutes / 60.0, 2)


def format_hm(minutes: float) -> str:
    """Format minutes as human hours+minutes text.

    Examples: 130 -> "2h 10m", 120 -> "2h", 30 -> "30m", 0 -> "0m".
    Rounds to the nearest whole minute (completed minutes can be fractional).
    """
    total = int(round(minutes))
    hours, mins = divmod(total, 60)
    if hours and mins:
        return f"{hours}h {mins}m"
    if hours:
        return f"{hours}h"
    return f"{mins}m"


def percent(completed: float, total: float) -> float:
    """Percent complete, safe against a zero total."""
    if total <= 0:
        return 0.0
    return round(completed / total * 100, 1)


def is_done(duration_minutes: int, completed_minutes: int) -> bool:
    """A chapter is finished when completed time has reached its full length."""
    return completed_minutes >= duration_minutes


def week_bounds(day: date) -> tuple[date, date]:
    """Return (Monday, Sunday) of the ISO week containing ``day``."""
    monday = day - timedelta(days=day.weekday())
    sunday = monday + timedelta(days=6)
    return monday, sunday


def net_studied_minutes(deltas: "Iterable[float]") -> float:
    """Minutes actually studied, from a day's signed progress deltas.

    Sums **all** deltas — advancing *and* reducing — so completion changes cancel
    out. Ticking a chapter Done then un-ticking it records ``+60, -60`` and nets
    to ``0``, which is the truth: no time was studied.

    (Counting only the positive deltas inflated the total on every toggle: five
    Done/undone cycles on a 60-minute chapter reported 300 minutes studied while
    the chapter sat at 0% complete.)

    Clamped at ``0``: a day whose corrections outweigh its progress shows no
    study rather than a negative bar, which no chart can render sensibly. The
    reduced time is still reflected in the chapter's completion and roll-ups —
    this only governs the "studied on this day" figure.

    Netting is **per day**, so a correction only offsets progress recorded on the
    same day. Undoing today what you completed yesterday leaves yesterday's total
    intact (you did study then) and floors today at 0; the undo is visible in the
    chapter's completion dropping, not by rewriting a past day.
    """
    return max(0.0, float(sum(deltas)))


# Directions accepted by ``swap_index``/the reorder UI.
MOVE_UP = "up"
MOVE_DOWN = "down"
MOVE_DIRECTIONS = (MOVE_UP, MOVE_DOWN)


def swap_index(index: int, direction: str, count: int) -> int | None:
    """Index to swap ``index`` with when moving it one step, or None if it can't.

    Pure position arithmetic for reordering a list of ``count`` siblings.
    Returns None when the move would fall off either end — the first item can't
    move up and the last can't move down — so callers treat "no room" as a
    no-op rather than an error.

    >>> swap_index(2, MOVE_UP, 5)
    1
    >>> swap_index(0, MOVE_UP, 5) is None
    True
    """
    if direction not in MOVE_DIRECTIONS:
        raise ValueError(f"direction must be one of {MOVE_DIRECTIONS}.")
    if not 0 <= index < count:
        return None
    target = index - 1 if direction == MOVE_UP else index + 1
    return target if 0 <= target < count else None


@dataclass(frozen=True)
class Progress:
    """A computed roll-up of time at any level (chapter/module/subject)."""

    total_minutes: float
    completed_minutes: float

    @property
    def remaining_minutes(self) -> float:
        return max(0.0, self.total_minutes - self.completed_minutes)

    @property
    def percent(self) -> float:
        return percent(self.completed_minutes, self.total_minutes)

    # Display helpers: numeric hours (charts) ---------------------------------
    @property
    def total_hours(self) -> float:
        return minutes_to_hours(self.total_minutes)

    @property
    def completed_hours(self) -> float:
        return minutes_to_hours(self.completed_minutes)

    @property
    def remaining_hours(self) -> float:
        return minutes_to_hours(self.remaining_minutes)

    # Display helpers: hours+minutes text (UI) --------------------------------
    @property
    def total_hm(self) -> str:
        return format_hm(self.total_minutes)

    @property
    def completed_hm(self) -> str:
        return format_hm(self.completed_minutes)

    @property
    def remaining_hm(self) -> str:
        return format_hm(self.remaining_minutes)

    def __add__(self, other: "Progress") -> "Progress":
        return Progress(
            self.total_minutes + other.total_minutes,
            self.completed_minutes + other.completed_minutes,
        )


ZERO_PROGRESS = Progress(0.0, 0.0)


def chapter_progress(duration_minutes: int, completed_minutes: int) -> Progress:
    """Progress for a single chapter (completed time is stored directly)."""
    return Progress(
        total_minutes=float(duration_minutes),
        completed_minutes=float(clamp_completed(duration_minutes, completed_minutes)),
    )


def sum_progress(items: list[Progress]) -> Progress:
    """Aggregate many Progress values (module or subject roll-up)."""
    total = ZERO_PROGRESS
    for item in items:
        total = total + item
    return total
