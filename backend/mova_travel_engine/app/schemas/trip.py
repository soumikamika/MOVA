"""Trip input: Traveller, Preference, TripRequest, Trip."""
import datetime as dt
import uuid

from pydantic import Field, field_validator, model_validator

from app.core.constants import MAX_BUDGET_INR, MAX_TAGS_PER_LIST, MAX_TRAVELLERS, MAX_TRIP_DAYS
from app.schemas.common import (
    ActivityLevel, AgeGroup, DietaryPreference, HotelCategory, MovaModel,
    TransportPreference, TransportMode, TripType,
)
from app.utils.time import date_range, today, trip_days
from app.utils.validation import normalize_tags, normalize_text


class Traveller(MovaModel):
    age_group: AgeGroup = AgeGroup.ADULT
    dietary_preferences: list[DietaryPreference] = Field(default_factory=list)
    needs_accessibility: bool = False


class Preference(MovaModel):
    interests: list[str] = Field(default_factory=list)
    dislikes: list[str] = Field(default_factory=list)
    activity_level: ActivityLevel = ActivityLevel.MODERATE
    meal_preferences: list[DietaryPreference] = Field(default_factory=list)
    transport_preference: TransportPreference = TransportPreference.FLEXIBLE
    hotel_category: HotelCategory | None = None


class TripRequest(MovaModel):
    """Body of POST /api/plans/generate. Budget is total INR for the whole party."""

    destination: str = Field(min_length=1, max_length=100)
    destinations: list[str] = Field(default_factory=list, max_length=12)
    destination_ids: list[str] = Field(default_factory=list, max_length=12)
    must_visit_places: list[str] = Field(default_factory=list, max_length=12)
    origin: str | None = Field(default=None, max_length=100)  # needed for intercity cost/transport
    origin_latitude: float | None = Field(default=None, ge=-90, le=90)
    origin_longitude: float | None = Field(default=None, ge=-180, le=180)
    invited_people: list[str] = Field(default_factory=list, max_length=20)
    start_date: dt.date
    end_date: dt.date
    travellers: int = Field(ge=1, le=MAX_TRAVELLERS)
    trip_type: TripType
    budget: float = Field(gt=0, le=MAX_BUDGET_INR)

    # Explicit cost assumptions used for the trip budget breakdown. MOVA never
    # invents fuel or food prices: these are traveller-provided inputs.
    food_budget_per_person_per_day: float | None = Field(default=None, ge=0)
    vehicle_fuel_type: str | None = Field(default=None, max_length=20)
    vehicle_mileage_kmpl: float | None = Field(default=None, gt=0, le=100)
    fuel_price_inr_per_litre: float | None = Field(default=None, ge=0)

    interests: list[str] = Field(default_factory=list, max_length=MAX_TAGS_PER_LIST)
    dislikes: list[str] = Field(default_factory=list, max_length=MAX_TAGS_PER_LIST)
    transport_preference: TransportPreference = TransportPreference.FLEXIBLE
    preferred_travel_methods: list[TransportMode] = Field(default_factory=list)
    avoid_travel_methods: list[TransportMode] = Field(default_factory=list)
    activity_level: ActivityLevel = ActivityLevel.MODERATE
    meal_preferences: list[DietaryPreference] = Field(default_factory=list)
    hotel_category: HotelCategory | None = None
    traveller_profiles: list[Traveller] | None = None

    @field_validator("destination")
    @classmethod
    def _clean_destination(cls, v: str) -> str:
        v = normalize_text(v)
        if not v:
            raise ValueError("destination must not be blank")
        return v

    @field_validator("origin")
    @classmethod
    def _clean_origin(cls, v: str | None) -> str | None:
        if v is None:
            return None
        v = normalize_text(v)
        return v or None

    @field_validator("interests", "dislikes")
    @classmethod
    def _clean_tags(cls, v: list[str]) -> list[str]:
        return normalize_tags(v)

    @field_validator("destinations", "destination_ids", "must_visit_places", "invited_people")
    @classmethod
    def _clean_lists(cls, v: list[str]) -> list[str]:
        return [x.strip() for x in dict.fromkeys(v) if isinstance(x, str) and x.strip()]

    @field_validator("meal_preferences")
    @classmethod
    def _dedupe_meals(cls, v: list[DietaryPreference]) -> list[DietaryPreference]:
        return list(dict.fromkeys(v))

    @model_validator(mode="after")
    def _cross_field_checks(self) -> "TripRequest":
        if self.end_date < self.start_date:
            raise ValueError("end_date must be on or after start_date")
        if self.start_date < today():
            raise ValueError("start_date cannot be in the past")
        if trip_days(self.start_date, self.end_date) > MAX_TRIP_DAYS:
            raise ValueError(f"trips longer than {MAX_TRIP_DAYS} days are not supported")
        both = sorted(set(self.interests) & set(self.dislikes))
        if both:
            raise ValueError(f"these are listed as both interests and dislikes: {', '.join(both)}")
        if self.traveller_profiles is not None and len(self.traveller_profiles) != self.travellers:
            raise ValueError("traveller_profiles length must equal travellers")
        return self

    @property
    def num_days(self) -> int:
        return trip_days(self.start_date, self.end_date)

    @property
    def dates(self) -> list[dt.date]:
        return date_range(self.start_date, self.end_date)

    @property
    def preference(self) -> Preference:
        return Preference(
            interests=self.interests,
            dislikes=self.dislikes,
            activity_level=self.activity_level,
            meal_preferences=self.meal_preferences,
            transport_preference=self.transport_preference,
            hotel_category=self.hotel_category,
        )


class Trip(MovaModel):
    id: str
    request: TripRequest
    created_at: dt.datetime

    @classmethod
    def new(cls, request: TripRequest) -> "Trip":
        return cls(
            id=uuid.uuid4().hex,
            request=request,
            created_at=dt.datetime.now(dt.timezone.utc),
        )
