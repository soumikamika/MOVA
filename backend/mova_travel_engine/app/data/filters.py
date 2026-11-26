"""Query criteria for repositories.

Criteria are plain Pydantic models. `matches()` is the REFERENCE implementation
used by in-memory/JSON repositories; a PostgreSQL repository translates the same
fields to SQL. Planner code only ever builds criteria - it never sees storage.

Unknown-value policy: a record attribute that is None (or an empty list, where
empty means "unknown") is NOT silently treated as passing or failing. The caller
chooses via `include_unknown` (default True = keep records we cannot rule out).
"""
from collections.abc import Callable, Iterable
from typing import Any, TypeVar

from pydantic import Field, field_validator, model_validator

from app.schemas.common import (
    DataSource, DietaryPreference, HotelCategory, MealType, MovaModel,
    PlaceCategory, TransportMode,
)
from app.schemas.logistics import TransportOption
from app.schemas.place import Destination, Hotel, Place, Restaurant
from app.utils.validation import normalize_tags, normalize_text

T = TypeVar("T")


def normalize_name(value: str) -> str:
    """Case-/whitespace-insensitive key for names, aliases and city strings."""
    return normalize_text(value).casefold()


class RecordFilter(MovaModel):
    sources: set[DataSource] | None = None  # allow-list; an empty set matches nothing
    exclude_development_only: bool = False  # drop synthetic_dev / mock records
    include_unknown: bool = True

    def _source_ok(self, record: Any) -> bool:
        if self.sources is not None and record.source not in self.sources:
            return False
        if self.exclude_development_only and record.source.is_development_only:
            return False
        return True

    def _known(self, value: Any, predicate: Callable[[Any], bool]) -> bool:
        if value is None:
            return self.include_unknown
        return bool(predicate(value))

    def _known_list(self, values: list, predicate: Callable[[list], bool]) -> bool:
        """For list attributes where an empty list means 'unknown'."""
        if not values:
            return self.include_unknown
        return bool(predicate(values))


class PlaceFilter(RecordFilter):
    destination_id: str | None = None
    categories: set[PlaceCategory] | None = None
    exclude_categories: set[PlaceCategory] = Field(default_factory=set)
    tags_any: list[str] = Field(default_factory=list)      # at least one must match
    tags_exclude: list[str] = Field(default_factory=list)  # none may match
    min_rating: float | None = Field(default=None, ge=0, le=5)
    max_entry_fee_inr: float | None = Field(default=None, ge=0)
    max_intensity: int | None = Field(default=None, ge=1, le=5)
    max_visit_minutes: int | None = Field(default=None, gt=0)
    require_family_friendly: bool = False
    require_wheelchair_accessible: bool = False
    # Excludes places whose closed_months contain this month. An empty
    # closed_months list is read as "no known closures".
    available_in_month: int | None = Field(default=None, ge=1, le=12)

    @field_validator("tags_any", "tags_exclude")
    @classmethod
    def _norm_tags(cls, v: list[str]) -> list[str]:
        return normalize_tags(v)

    def matches(self, place: Place) -> bool:
        if not self._source_ok(place):
            return False
        if self.destination_id is not None and place.destination_id != self.destination_id:
            return False
        if self.categories is not None and place.category not in self.categories:
            return False
        if place.category in self.exclude_categories:
            return False
        tags = set(place.tags)
        if self.tags_any and not (tags & set(self.tags_any)):
            return False
        if self.tags_exclude and (tags & set(self.tags_exclude)):
            return False
        if self.max_intensity is not None and place.intensity > self.max_intensity:
            return False
        if self.max_visit_minutes is not None and place.avg_visit_minutes > self.max_visit_minutes:
            return False
        if self.available_in_month is not None and self.available_in_month in place.closed_months:
            return False
        if self.min_rating is not None and not self._known(place.rating, lambda r: r >= self.min_rating):
            return False
        if self.max_entry_fee_inr is not None and not self._known(
            place.entry_fee_inr, lambda f: f <= self.max_entry_fee_inr
        ):
            return False
        if self.require_family_friendly and not self._known(place.family_friendly, bool):
            return False
        if self.require_wheelchair_accessible and not self._known(place.wheelchair_accessible, bool):
            return False
        return True


class OpenDuring(MovaModel):
    """'Open for the whole of [start, end] on this weekday' (0=Mon)."""

    weekday: int = Field(ge=0, le=6)
    start_minute: int = Field(ge=0, le=1439)
    end_minute: int = Field(gt=0, le=1440)

    @model_validator(mode="after")
    def _ordered(self) -> "OpenDuring":
        if self.end_minute <= self.start_minute:
            raise ValueError("end_minute must be after start_minute")
        return self


class RestaurantFilter(RecordFilter):
    destination_id: str | None = None
    cuisines_any: list[str] = Field(default_factory=list)
    dietary_all: list[DietaryPreference] = Field(default_factory=list)  # must offer ALL
    serves: MealType | None = None
    max_price_per_person_inr: float | None = Field(default=None, ge=0)
    min_rating: float | None = Field(default=None, ge=0, le=5)
    open_during: OpenDuring | None = None

    def matches(self, r: Restaurant) -> bool:
        if not self._source_ok(r):
            return False
        if self.destination_id is not None and r.destination_id != self.destination_id:
            return False
        if self.cuisines_any:
            wanted = {normalize_name(c) for c in self.cuisines_any}
            if not self._known_list(r.cuisines, lambda cs: bool({normalize_name(c) for c in cs} & wanted)):
                return False
        if self.dietary_all and not self._known_list(
            r.dietary_options, lambda opts: all(d in opts for d in self.dietary_all)
        ):
            return False
        if self.serves is not None and not self._known_list(r.serves, lambda s: self.serves in s):
            return False
        if self.max_price_per_person_inr is not None and not self._known(
            r.avg_price_per_person_inr, lambda p: p <= self.max_price_per_person_inr
        ):
            return False
        if self.min_rating is not None and not self._known(r.rating, lambda x: x >= self.min_rating):
            return False
        if self.open_during is not None:
            w = self.open_during
            if not self._known(r.opening_hours, lambda oh: oh.is_open(w.weekday, w.start_minute, w.end_minute)):
                return False
        return True


class HotelFilter(RecordFilter):
    destination_id: str | None = None
    categories: set[HotelCategory] | None = None
    max_price_per_night_inr: float | None = Field(default=None, gt=0)
    min_rating: float | None = Field(default=None, ge=0, le=5)
    min_occupancy_per_room: int | None = Field(default=None, ge=1)
    amenities_all: list[str] = Field(default_factory=list)

    def matches(self, h: Hotel) -> bool:
        if not self._source_ok(h):
            return False
        if self.destination_id is not None and h.destination_id != self.destination_id:
            return False
        if self.categories is not None and h.category not in self.categories:
            return False
        if self.max_price_per_night_inr is not None and h.price_per_night_inr > self.max_price_per_night_inr:
            return False
        if self.min_occupancy_per_room is not None and h.max_occupancy_per_room < self.min_occupancy_per_room:
            return False
        if self.min_rating is not None and not self._known(h.rating, lambda x: x >= self.min_rating):
            return False
        if self.amenities_all:
            wanted = {normalize_name(a) for a in self.amenities_all}
            if not self._known_list(h.amenities, lambda am: wanted <= {normalize_name(a) for a in am}):
                return False
        return True


class TransportFilter(RecordFilter):
    origin: str | None = None
    destination: str | None = None
    modes: set[TransportMode] | None = None
    max_price_per_person_inr: float | None = Field(default=None, ge=0)
    max_duration_minutes: int | None = Field(default=None, gt=0)

    def matches(self, t: TransportOption) -> bool:
        if not self._source_ok(t):
            return False
        if self.origin is not None and normalize_name(t.origin) != normalize_name(self.origin):
            return False
        if self.destination is not None and normalize_name(t.destination) != normalize_name(self.destination):
            return False
        if self.modes is not None and t.mode not in self.modes:
            return False
        if self.max_price_per_person_inr is not None and t.price_per_person_inr > self.max_price_per_person_inr:
            return False
        if self.max_duration_minutes is not None and t.duration_minutes > self.max_duration_minutes:
            return False
        return True


# ---- destination lookup & text search (shared by every implementation) ------
def match_destination(query: str, destinations: Iterable[Destination]) -> Destination | None:
    """Exact (case/whitespace-insensitive) match on id or name, then on aliases.

    Deterministic: candidates are checked in id order. Returns None if unknown -
    the planner decides whether that is an error.
    """
    q = normalize_name(query)
    if not q:
        return None
    ordered = sorted(destinations, key=lambda d: d.id)
    for d in ordered:
        if q in (normalize_name(d.id), normalize_name(d.name)):
            return d
    for d in ordered:
        if q in {normalize_name(a) for a in d.aliases}:
            return d
    return None


def rank_text_matches(
    items: Iterable[T], text: str, *, name: Callable[[T], str],
    haystack: Callable[[T], str], limit: int | None = None,
) -> list[T]:
    """Every whitespace-separated token must occur in the haystack.

    Ranking: exact name, name prefix, name substring, then other-field match;
    ties broken alphabetically. Blank text returns [] (never 'everything').
    """
    tokens = normalize_name(text).split()
    if not tokens:
        return []
    q = " ".join(tokens)
    scored: list[tuple[int, str, T]] = []
    for it in items:
        n = normalize_name(name(it))
        h = normalize_name(haystack(it))
        if all(t in h for t in tokens):
            rank = 0 if n == q else 1 if n.startswith(q) else 2 if q in n else 3
            scored.append((rank, n, it))
    scored.sort(key=lambda x: (x[0], x[1]))
    out = [it for _, _, it in scored]
    return out if limit is None else out[:limit]
