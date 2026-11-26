"""Itinerary items, days, plans and conflicts.

Design note: these schemas validate STRUCTURE only (types, non-negative times,
end > start, required ids per item type, consecutive days). They deliberately do
NOT reject semantic problems such as overlaps, closed venues or over-long days:
the Constraint Engine (Phase F) must be able to represent an invalid plan in
order to detect and report it.
"""
import datetime as dt
from typing import Any

from pydantic import Field, computed_field, model_validator

from app.schemas.common import (
    ClockTime, ConflictType, ItemType, MealType, MovaModel, Severity, TransportMode,
)
from app.utils.time import to_minutes

FactValue = str | int | float | bool | None


class ItineraryItem(MovaModel):
    type: ItemType
    start: ClockTime
    end: ClockTime
    duration_minutes: int = Field(gt=0)

    place_id: str | None = None         # activity
    restaurant_id: str | None = None    # meal
    meal_type: MealType | None = None
    from_id: str | None = None          # travel
    to_id: str | None = None            # travel
    transport_mode: TransportMode | None = None

    cost_inr: float | None = Field(default=None, ge=0)
    # Structured facts (distances, matched tags, ...) consumed by the explanation
    # layer, so explanations are generated from data rather than invented.
    facts: dict[str, FactValue] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _structure(self) -> "ItineraryItem":
        s, e = to_minutes(self.start), to_minutes(self.end)
        if e <= s:
            raise ValueError("end must be after start (items cannot cross midnight)")
        if self.duration_minutes != e - s:
            raise ValueError(
                f"duration_minutes ({self.duration_minutes}) does not match start/end ({e - s})"
            )
        if self.type == ItemType.ACTIVITY and not self.place_id:
            raise ValueError("activity items require place_id")
        if self.type == ItemType.MEAL and not (self.restaurant_id or self.place_id):
            raise ValueError("meal items require restaurant_id (or place_id)")
        if self.type == ItemType.TRAVEL and not (self.from_id and self.to_id and self.transport_mode):
            raise ValueError("travel items require from_id, to_id and transport_mode")
        return self


class DayPlan(MovaModel):
    day: int = Field(ge=1)
    date: dt.date
    items: list[ItineraryItem] = Field(default_factory=list)

    def _minutes_of(self, item_type: ItemType) -> int:
        return sum(i.duration_minutes for i in self.items if i.type == item_type)

    @computed_field
    @property
    def total_activity_minutes(self) -> int:
        return self._minutes_of(ItemType.ACTIVITY)

    @computed_field
    @property
    def total_travel_minutes(self) -> int:
        return self._minutes_of(ItemType.TRAVEL)


class Itinerary(MovaModel):
    plan_id: str
    days: list[DayPlan] = Field(default_factory=list)

    @model_validator(mode="after")
    def _days_consecutive(self) -> "Itinerary":
        for idx, d in enumerate(self.days):
            if d.day != idx + 1:
                raise ValueError(f"days must be numbered 1..N in order; got day {d.day} at position {idx + 1}")
            if idx > 0 and d.date != self.days[idx - 1].date + dt.timedelta(days=1):
                raise ValueError("day dates must be consecutive calendar days")
        return self


class PlanConflict(MovaModel):
    type: ConflictType
    severity: Severity
    message: str = Field(min_length=1)
    day: int | None = Field(default=None, ge=1)
    item_refs: list[str] = Field(default_factory=list)
    details: dict[str, Any] = Field(default_factory=dict)
