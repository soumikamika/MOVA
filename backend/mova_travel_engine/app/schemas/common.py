"""Shared enums, base model and provenance tracking.

Provenance is a first-class requirement: every data-bearing record must say where
it came from, and `source` has NO default so it can never be omitted by accident.
"""
import datetime as dt
from collections.abc import Iterable
from enum import StrEnum
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

# Strict 24h "HH:MM". Matches the JSON in the spec ("09:30").
ClockTime = Annotated[str, StringConstraints(pattern=r"^([01]\d|2[0-3]):[0-5]\d$")]


class MovaModel(BaseModel):
    """Base for all schemas.

    extra="forbid": a misspelt field ("intrests") is a 422 error, not silently
    ignored - silent ignoring would quietly degrade personalisation.
    """

    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")


class DataSource(StrEnum):
    REAL = "real"                    # curated / collected real-world data
    SYNTHETIC_DEV = "synthetic_dev"  # generated for development & tests ONLY
    EXTERNAL_API = "external_api"    # fetched live from a provider
    USER_GENERATED = "user_generated"
    MOCK = "mock"                    # fake provider response for offline dev

    @property
    def is_development_only(self) -> bool:
        return self in (DataSource.SYNTHETIC_DEV, DataSource.MOCK)


def has_development_only_data(sources: Iterable[DataSource]) -> bool:
    """True if any source is synthetic/mock. The API must surface this to the UI."""
    return any(DataSource(s).is_development_only for s in sources)


class Sourced(MovaModel):
    source: DataSource  # required, no default
    # Optional provenance (Phase B). None = not recorded / not applicable.
    last_updated: dt.datetime | None = None
    confidence: float | None = Field(default=None, ge=0, le=1)  # reliability of the record's attributes


class TripType(StrEnum):
    SOLO = "solo"
    COUPLE = "couple"
    FRIENDS = "friends"
    FAMILY = "family"
    GROUP = "group"


class ActivityLevel(StrEnum):
    RELAXED = "relaxed"
    MODERATE = "moderate"
    INTENSE = "intense"


class TransportPreference(StrEnum):
    FLEXIBLE = "flexible"
    FLIGHT = "flight"
    TRAIN = "train"
    BUS = "bus"
    ROAD = "road"  # own/rented car


class TransportMode(StrEnum):
    FLIGHT = "flight"
    TRAIN = "train"
    BUS = "bus"
    CAR = "car"
    CAB = "cab"
    TWO_WHEELER = "two_wheeler"
    FERRY = "ferry"
    WALK = "walk"


class DietaryPreference(StrEnum):
    VEGETARIAN = "vegetarian"
    VEGAN = "vegan"
    JAIN = "jain"
    EGGETARIAN = "eggetarian"
    NON_VEGETARIAN = "non_vegetarian"
    HALAL = "halal"
    GLUTEN_FREE = "gluten_free"


class HotelCategory(StrEnum):
    BUDGET = "budget"
    MIDRANGE = "midrange"
    PREMIUM = "premium"
    LUXURY = "luxury"


class AgeGroup(StrEnum):
    CHILD = "child"
    ADULT = "adult"
    SENIOR = "senior"


class PlaceCategory(StrEnum):
    BEACH = "beach"
    NATURE = "nature"
    WATERFALL = "waterfall"
    WILDLIFE = "wildlife"
    HISTORICAL = "historical"
    RELIGIOUS = "religious"
    MUSEUM = "museum"
    MARKET = "market"
    ADVENTURE = "adventure"
    NIGHTLIFE = "nightlife"
    VIEWPOINT = "viewpoint"
    WELLNESS = "wellness"
    PARK = "park"
    CULTURAL = "cultural"
    ENTERTAINMENT = "entertainment"
    OTHER = "other"


class TimeOfDay(StrEnum):
    MORNING = "morning"
    AFTERNOON = "afternoon"
    EVENING = "evening"
    NIGHT = "night"


class MealType(StrEnum):
    BREAKFAST = "breakfast"
    LUNCH = "lunch"
    DINNER = "dinner"
    SNACK = "snack"


class ItemType(StrEnum):
    ACTIVITY = "activity"
    TRAVEL = "travel"
    MEAL = "meal"
    REST = "rest"


class ConflictType(StrEnum):
    TIME_CONFLICT = "time_conflict"
    OVERLAP = "overlap"
    OPENING_HOURS = "opening_hours"
    INSUFFICIENT_MEAL_TIME = "insufficient_meal_time"
    EXCESSIVE_DENSITY = "excessive_density"
    EXCESSIVE_TRAVEL = "excessive_travel"
    BUDGET_OVERRUN = "budget_overrun"
    UNAVAILABLE_PLACE = "unavailable_place"
    DUPLICATE_PLACE = "duplicate_place"
    MISSING_DATA = "missing_data"
    INSUFFICIENT_TIME = "insufficient_time"


class Severity(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class ConfidenceLevel(StrEnum):
    UNKNOWN = "unknown"  # default: we do not claim accuracy we cannot back up
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
