"""TransportOption, Weather, and the request schemas for Phase D's prediction services."""
import datetime as dt
from enum import StrEnum

from pydantic import Field, model_validator

from app.schemas.common import ClockTime, MovaModel, Sourced, TransportMode


class TransportOption(Sourced):
    id: str = Field(min_length=1)
    mode: TransportMode
    origin: str = Field(min_length=1)
    destination: str = Field(min_length=1)
    duration_minutes: int = Field(gt=0)
    price_per_person_inr: float = Field(ge=0)
    departure_time: ClockTime | None = None
    provider_name: str | None = None


class Weather(Sourced):
    destination_id: str = Field(min_length=1)
    date: dt.date
    temp_min_c: float = Field(ge=-90, le=60)
    temp_max_c: float = Field(ge=-90, le=60)
    precipitation_probability: float | None = Field(default=None, ge=0, le=1)
    condition: str | None = None
    is_forecast: bool = True

    @model_validator(mode="after")
    def _min_le_max(self) -> "Weather":
        if self.temp_min_c > self.temp_max_c:
            raise ValueError("temp_min_c cannot exceed temp_max_c")
        return self


class TravelTimeRequest(MovaModel):
    """A route/travel-time query. Everything except origin/destination/mode is
    optional - the traveller may legitimately not know distance, an exact
    departure time, or transfer count, and the service must not fabricate them.
    """

    origin: str = Field(min_length=1)
    destination: str = Field(min_length=1)
    mode: TransportMode

    distance_km: float | None = Field(default=None, ge=0)
    departure_time: ClockTime | None = None
    weekday: int | None = Field(default=None, ge=0, le=6)   # 0=Monday .. 6=Sunday
    date: dt.date | None = None
    num_transfers: int | None = Field(default=None, ge=0)


class CostCategory(StrEnum):
    TRANSPORT = "transport"
    ACCOMMODATION = "accommodation"
    FOOD = "food"
    ACTIVITIES = "activities"
    LOCAL_TRANSPORT = "local_transport"
    MISCELLANEOUS = "miscellaneous"


class CostRequest(MovaModel):
    """A cost query for one category and one quantity/unit-price pair.

    Baseline behaviour (see app/travel_cost/baseline.py):
      * `total_known_price_inr` set        -> OBSERVED (an already-known real price; no calculation)
      * `quantity` AND `unit_price_inr` set -> BASELINE = quantity * unit_price_inr
                                               (e.g. nights x nightly rate, or distance_km x per-km rate)
      * otherwise                          -> explicit unknown result

    `travellers` is context for feature engineering only; the baseline never
    multiplies by it implicitly - callers fold travellers into `quantity` or
    `unit_price_inr` themselves so the calculation stays a single, auditable
    multiplication.
    """

    category: CostCategory
    travellers: int = Field(ge=1)

    quantity: float | None = Field(default=None, ge=0)          # e.g. nights, distance_km, meal count
    unit_price_inr: float | None = Field(default=None, ge=0)    # e.g. nightly rate, per-km rate, per-meal price
    total_known_price_inr: float | None = Field(default=None, ge=0)  # an already-known/observed total

    date: dt.date | None = None
