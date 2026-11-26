"""Clock/date helpers. All intra-day times are minutes since midnight (0..1439).

Plans are single-day-bounded: an item may not cross midnight. Venues open past
midnight must be modelled as two windows (handled where relevant in later phases).
"""
import re
from datetime import date, timedelta

_CLOCK_RE = re.compile(r"^([01]\d|2[0-3]):([0-5]\d)$")


def today() -> date:
    """Indirection so tests can monkeypatch 'now'."""
    return date.today()


def to_minutes(clock: str) -> int:
    """'09:30' -> 570. Raises ValueError on anything that is not strict HH:MM."""
    m = _CLOCK_RE.match(clock)
    if not m:
        raise ValueError(f"invalid clock time {clock!r}; expected HH:MM (00:00-23:59)")
    return int(m.group(1)) * 60 + int(m.group(2))


def from_minutes(minutes: int) -> str:
    """570 -> '09:30'. Raises ValueError outside 0..1439."""
    if not 0 <= minutes <= 1439:
        raise ValueError(f"minutes {minutes} outside a single day (0..1439)")
    return f"{minutes // 60:02d}:{minutes % 60:02d}"


def format_duration(minutes: int) -> str:
    """800 -> '13h 20m', 120 -> '2h', 45 -> '45m'. For human-readable messages."""
    if minutes < 0:
        raise ValueError("duration cannot be negative")
    h, m = divmod(int(minutes), 60)
    if h and m:
        return f"{h}h {m}m"
    if h:
        return f"{h}h"
    return f"{m}m"


def trip_days(start: date, end: date) -> int:
    """Inclusive number of calendar days. Same-day trip = 1."""
    if end < start:
        raise ValueError("end date is before start date")
    return (end - start).days + 1


def date_range(start: date, end: date) -> list[date]:
    return [start + timedelta(days=i) for i in range(trip_days(start, end))]


def intervals_overlap(a_start: int, a_end: int, b_start: int, b_end: int) -> bool:
    """Half-open overlap: [9:00,10:00) and [10:00,11:00) do NOT overlap."""
    return a_start < b_end and b_start < a_end
