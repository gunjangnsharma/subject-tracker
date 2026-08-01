"""Unit tests for pure domain math (test plan section 2.1)."""

from datetime import date

from tracker import domain


def test_minutes_to_hours():  # D1, D2
    assert domain.minutes_to_hours(90) == 1.5
    assert domain.minutes_to_hours(0) == 0.0


def test_format_hm():
    assert domain.format_hm(130) == "2h 10m"   # the headline example
    assert domain.format_hm(90) == "1h 30m"
    assert domain.format_hm(120) == "2h"       # whole hours -> no minutes
    assert domain.format_hm(30) == "30m"       # under an hour -> minutes only
    assert domain.format_hm(0) == "0m"
    assert domain.format_hm(60) == "1h"
    assert domain.format_hm(22.5) == "22m"     # fractional minutes rounded


def test_progress_hm_strings():
    p = domain.chapter_progress(130, 65)        # 130 min, 65 done, 65 left
    assert p.total_hm == "2h 10m"
    assert p.completed_hm == "1h 5m"
    assert p.remaining_hm == "1h 5m"


def test_chapter_progress_from_minutes():  # D3, D4, D5
    assert domain.chapter_progress(120, 60).completed_minutes == 60   # half done
    assert domain.chapter_progress(60, 60).completed_minutes == 60    # fully done
    assert domain.chapter_progress(60, 0).completed_minutes == 0      # not started


def test_percent_safe_and_correct():  # D6, D7
    assert domain.percent(0, 0) == 0.0                 # no divide-by-zero
    assert domain.percent(30, 120) == 25.0


def test_completed_clamped():  # D8
    assert domain.clamp_completed(120, 200) == 120     # cannot exceed duration
    assert domain.clamp_completed(120, -5) == 0        # cannot go negative
    assert domain.clamp_completed(120, 45) == 45       # in range


def test_is_done():
    assert domain.is_done(120, 120) is True            # fully complete
    assert domain.is_done(120, 119) is False
    assert domain.is_done(120, 130) is True            # over-complete still done


def test_week_bounds_monday_to_sunday():  # P7 (pure part)
    wednesday = date(2026, 8, 5)  # a Wednesday
    start, end = domain.week_bounds(wednesday)
    assert start == date(2026, 8, 3)   # Monday
    assert end == date(2026, 8, 9)     # Sunday


def test_progress_rollup_addition():
    a = domain.chapter_progress(60, 60)   # 60 done / 60
    b = domain.chapter_progress(120, 60)  # 60 done / 120
    total = domain.sum_progress([a, b])
    assert total.total_minutes == 180
    assert total.completed_minutes == 120
    assert total.remaining_minutes == 60
    assert total.percent == round(120 / 180 * 100, 1)
