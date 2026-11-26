from datetime import date

import pytest

from app.utils.geo import haversine_km, is_within_india_bounds
from app.utils.time import (
    date_range, format_duration, from_minutes, intervals_overlap, to_minutes, trip_days,
)
from app.utils.validation import normalize_tag, normalize_tags, normalize_text, unknown_tags


# ---- time -------------------------------------------------------------
def test_to_minutes_and_back():
    assert to_minutes("09:30") == 570
    assert to_minutes("00:00") == 0
    assert to_minutes("23:59") == 1439
    assert from_minutes(570) == "09:30"


@pytest.mark.parametrize("bad", ["9:30", "24:00", "12:60", "", "ab:cd", "09:30:00", "09-30"])
def test_to_minutes_rejects_bad_clock(bad):
    with pytest.raises(ValueError):
        to_minutes(bad)


@pytest.mark.parametrize("bad", [-1, 1440, 5000])
def test_from_minutes_rejects_out_of_day(bad):
    with pytest.raises(ValueError):
        from_minutes(bad)


def test_format_duration():
    assert format_duration(800) == "13h 20m"
    assert format_duration(630) == "10h 30m"
    assert format_duration(120) == "2h"
    assert format_duration(45) == "45m"
    assert format_duration(0) == "0m"
    with pytest.raises(ValueError):
        format_duration(-5)


def test_trip_days_inclusive():
    assert trip_days(date(2026, 12, 10), date(2026, 12, 14)) == 5
    assert trip_days(date(2026, 12, 10), date(2026, 12, 10)) == 1
    with pytest.raises(ValueError):
        trip_days(date(2026, 12, 14), date(2026, 12, 10))


def test_date_range():
    days = date_range(date(2026, 12, 30), date(2027, 1, 2))
    assert days == [date(2026, 12, 30), date(2026, 12, 31), date(2027, 1, 1), date(2027, 1, 2)]


def test_intervals_overlap_is_half_open():
    assert intervals_overlap(540, 600, 570, 630) is True
    assert intervals_overlap(540, 600, 600, 660) is False  # touching is fine
    assert intervals_overlap(540, 600, 700, 760) is False


# ---- geo --------------------------------------------------------------
def test_haversine_known_distance():
    # Delhi -> Mumbai straight-line is roughly 1,150 km
    d = haversine_km(28.6139, 77.2090, 19.0760, 72.8777)
    assert 1130 < d < 1170


def test_haversine_zero_and_symmetry():
    assert haversine_km(15.5, 73.8, 15.5, 73.8) == pytest.approx(0.0, abs=1e-9)
    a = haversine_km(15.49, 73.83, 15.30, 73.96)
    b = haversine_km(15.30, 73.96, 15.49, 73.83)
    assert a == pytest.approx(b)


def test_india_bounds():
    assert is_within_india_bounds(15.49, 73.83) is True      # Goa
    assert is_within_india_bounds(73.83, 15.49) is False     # swapped lat/lng
    assert is_within_india_bounds(51.5, -0.12) is False      # London


# ---- validation -------------------------------------------------------
@pytest.mark.parametrize(
    "raw,expected",
    [
        ("Beach", "beaches"),
        ("  Water Sports ", "water_sports"),
        ("water-sports", "water_sports"),
        ("Night Life", "nightlife"),
        ("CLUBS", "clubs"),
        ("crowd", "crowds"),
        ("some-new-thing!", "some_new_thing"),
    ],
)
def test_normalize_tag(raw, expected):
    assert normalize_tag(raw) == expected


def test_normalize_tags_dedupes_and_drops_empty():
    assert normalize_tags(["Beach", "beaches", " ", "Food", "food"]) == ["beaches", "food"]


def test_unknown_tags_reported_not_dropped():
    tags = normalize_tags(["beach", "zorbing"])
    assert "zorbing" in tags
    assert unknown_tags(tags) == ["zorbing"]


def test_normalize_text():
    assert normalize_text("  North   Goa  ") == "North Goa"
