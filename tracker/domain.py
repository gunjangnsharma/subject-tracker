"""Pure domain calculations.

This module has **no** dependency on Flask or SQLAlchemy so the business
rules can be unit-tested in isolation and reused anywhere. Everything here
is a plain function operating on numbers/dates.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta

# Completion is expressed on a 0..10 scale (tenths of the item done).
COMPLETION_MIN = 0
COMPLETION_MAX = 10


def clamp_completion(value: int) -> int:
    """Clamp a completion value into the valid 0..10 range."""
    return max(COMPLETION_MIN, min(COMPLETION_MAX, int(value)))


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


def completed_minutes(duration_minutes: int, completion: int) -> float:
    """Minutes actually completed given a 0..10 completion value.

    Example: a 120-minute video at completion 5 -> 60 minutes done.
    """
    return duration_minutes * clamp_completion(completion) / COMPLETION_MAX


def percent(completed: float, total: float) -> float:
    """Percent complete, safe against a zero total."""
    if total <= 0:
        return 0.0
    return round(completed / total * 100, 1)


def is_done(completion: int) -> bool:
    """A chapter is finished only when completion has reached the max."""
    return clamp_completion(completion) >= COMPLETION_MAX


def week_bounds(day: date) -> tuple[date, date]:
    """Return (Monday, Sunday) of the ISO week containing ``day``."""
    monday = day - timedelta(days=day.weekday())
    sunday = monday + timedelta(days=6)
    return monday, sunday


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


def chapter_progress(duration_minutes: int, completion: int) -> Progress:
    """Progress for a single chapter."""
    return Progress(
        total_minutes=float(duration_minutes),
        completed_minutes=completed_minutes(duration_minutes, completion),
    )


def sum_progress(items: list[Progress]) -> Progress:
    """Aggregate many Progress values (module or subject roll-up)."""
    total = ZERO_PROGRESS
    for item in items:
        total = total + item
    return total
