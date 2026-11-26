"""Destination, Place, Restaurant, Hotel + opening hours."""
from pydantic import Field, field_validator, model_validator

from app.core.constants import DEFAULT_TIMEZONE
from app.schemas.common import (
    ClockTime, DietaryPreference, HotelCategory, MealType, MovaModel,
    PlaceCategory, Sourced, TimeOfDay,
)
from app.utils.geo import haversine_km
from app.utils.time import to_minutes
from app.utils.validation import normalize_tags


class GeoPoint(MovaModel):
    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)

    def distance_km_to(self, other: "GeoPoint") -> float:
        """Straight-line distance. Road distance/time come from the route layer."""
        return haversine_km(self.latitude, self.longitude, other.latitude, other.longitude)


class TimeWindow(MovaModel):
    open: ClockTime
    close: ClockTime

    @model_validator(mode="after")
    def _open_before_close(self) -> "TimeWindow":
        if to_minutes(self.open) >= to_minutes(self.close):
            raise ValueError("close time must be after open time (split overnight hours into two windows)")
        return self


class OpeningHours(MovaModel):
    """Weekly opening hours. Weekday 0=Monday ... 6=Sunday.

    A weekday with no entry means CLOSED that day. Unknown hours are represented
    by `opening_hours=None` on the parent record, never by an empty schedule.
    """

    always_open: bool = False
    weekly: dict[int, list[TimeWindow]] = Field(default_factory=dict)

    @field_validator("weekly")
    @classmethod
    def _validate_weekly(cls, v: dict[int, list[TimeWindow]]) -> dict[int, list[TimeWindow]]:
        cleaned: dict[int, list[TimeWindow]] = {}
        for day, windows in v.items():
            if not 0 <= day <= 6:
                raise ValueError(f"weekday key {day} must be 0 (Mon) .. 6 (Sun)")
            ordered = sorted(windows, key=lambda w: to_minutes(w.open))
            for prev, nxt in zip(ordered, ordered[1:]):
                if to_minutes(nxt.open) < to_minutes(prev.close):
                    raise ValueError(f"overlapping opening windows on weekday {day}")
            cleaned[day] = ordered
        return cleaned

    @model_validator(mode="after")
    def _consistent(self) -> "OpeningHours":
        has_windows = any(self.weekly.values())
        if self.always_open and has_windows:
            raise ValueError("always_open cannot be combined with weekly windows")
        if not self.always_open and not has_windows:
            raise ValueError("provide always_open=True or at least one weekly window")
        return self

    @classmethod
    def daily(cls, open: str, close: str) -> "OpeningHours":
        """Same window every day of the week."""
        return cls(weekly={d: [TimeWindow(open=open, close=close)] for d in range(7)})

    def windows_for(self, weekday: int) -> list[tuple[int, int]]:
        """Open windows for a weekday as (open_min, close_min) pairs."""
        if self.always_open:
            return [(0, 1440)]
        return [(to_minutes(w.open), to_minutes(w.close)) for w in self.weekly.get(weekday, [])]

    def is_open(self, weekday: int, start_minute: int, end_minute: int) -> bool:
        """True iff [start, end] fits entirely inside ONE open window that day."""
        return any(o <= start_minute and end_minute <= c for o, c in self.windows_for(weekday))


def _validate_months(v: list[int]) -> list[int]:
    for m in v:
        if not 1 <= m <= 12:
            raise ValueError(f"month {m} must be 1..12")
    return sorted(set(v))


class Destination(Sourced):
    id: str = Field(min_length=1)
    name: str = Field(min_length=1, max_length=100)
    state: str | None = None
    country: str = "India"
    center: GeoPoint
    aliases: list[str] = Field(default_factory=list)
    timezone: str = DEFAULT_TIMEZONE
    best_months: list[int] = Field(default_factory=list)
    description: str | None = None

    @field_validator("best_months")
    @classmethod
    def _check_best_months(cls, v: list[int]) -> list[int]:
        return _validate_months(v)


class Place(Sourced):
    """A visitable place/activity. `None` means UNKNOWN - never a guessed value."""

    id: str = Field(min_length=1)
    destination_id: str = Field(min_length=1)
    name: str = Field(min_length=1, max_length=150)
    category: PlaceCategory
    tags: list[str] = Field(default_factory=list)
    location: GeoPoint

    rating: float | None = Field(default=None, ge=0, le=5)
    rating_count: int | None = Field(default=None, ge=0)
    popularity: float | None = Field(default=None, ge=0, le=1)
    crowd_level: float | None = Field(default=None, ge=0, le=1)

    avg_visit_minutes: int = Field(gt=0, le=720)
    entry_fee_inr: float | None = Field(default=None, ge=0)  # per person; 0 = free; None = unknown
    intensity: int = Field(ge=1, le=5)  # 1 = very light ... 5 = very strenuous

    opening_hours: OpeningHours | None = None  # None = unknown
    closed_months: list[int] = Field(default_factory=list)
    best_months: list[int] = Field(default_factory=list)
    best_times_of_day: list[TimeOfDay] = Field(default_factory=list)

    family_friendly: bool | None = None
    wheelchair_accessible: bool | None = None
    description: str | None = None

    @field_validator("tags")
    @classmethod
    def _norm_tags(cls, v: list[str]) -> list[str]:
        return normalize_tags(v)

    @field_validator("closed_months", "best_months")
    @classmethod
    def _check_months(cls, v: list[int]) -> list[int]:
        return _validate_months(v)


class Restaurant(Sourced):
    id: str = Field(min_length=1)
    destination_id: str = Field(min_length=1)
    name: str = Field(min_length=1, max_length=150)
    location: GeoPoint
    cuisines: list[str] = Field(default_factory=list)
    dietary_options: list[DietaryPreference] = Field(default_factory=list)
    serves: list[MealType] = Field(default_factory=list)
    avg_price_per_person_inr: float | None = Field(default=None, ge=0)
    rating: float | None = Field(default=None, ge=0, le=5)
    opening_hours: OpeningHours | None = None


class Hotel(Sourced):
    id: str = Field(min_length=1)
    destination_id: str = Field(min_length=1)
    name: str = Field(min_length=1, max_length=150)
    category: HotelCategory
    location: GeoPoint
    price_per_night_inr: float = Field(gt=0)  # per ROOM
    max_occupancy_per_room: int = Field(ge=1, le=10)
    rating: float | None = Field(default=None, ge=0, le=5)
    amenities: list[str] = Field(default_factory=list)
