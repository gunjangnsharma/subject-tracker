"""Unit tests for pure domain math (test plan section 2.1)."""

from datetime import date

from tracker import domain


def test_minutes_to_hours():  # D1, D2
    assert domain.minutes_to_hours(90) == 1.5
    assert domain.minutes_to_hours(0) == 0.0


def test_completed_minutes():  # D3, D4, D5
    assert domain.completed_minutes(120, 5) == 60      # 2h video half done
    assert domain.completed_minutes(60, 10) == 60      # fully done
    assert domain.completed_minutes(60, 0) == 0        # not started


def test_percent_safe_and_correct():  # D6, D7
    assert domain.percent(0, 0) == 0.0                 # no divide-by-zero
    assert domain.percent(30, 120) == 25.0


def test_completion_clamped():  # D8
    assert domain.clamp_completion(11) == 10
    assert domain.clamp_completion(-1) == 0
    assert domain.clamp_completion(7) == 7


def test_is_done():
    assert domain.is_done(10) is True
    assert domain.is_done(9) is False


def test_week_bounds_monday_to_sunday():  # P7 (pure part)
    wednesday = date(2026, 8, 5)  # a Wednesday
    start, end = domain.week_bounds(wednesday)
    assert start == date(2026, 8, 3)   # Monday
    assert end == date(2026, 8, 9)     # Sunday


def test_progress_rollup_addition():
    a = domain.chapter_progress(60, 10)   # 60 done / 60
    b = domain.chapter_progress(120, 5)   # 60 done / 120
    total = domain.sum_progress([a, b])
    assert total.total_minutes == 180
    assert total.completed_minutes == 120
    assert total.remaining_minutes == 60
    assert total.percent == round(120 / 180 * 100, 1)
