"""Structured plan modification contract for E4.

Natural-language parsing belongs to a future intent layer. The core engine
receives explicit operations so modifications remain deterministic and testable.
"""
from pydantic import Field, model_validator
from app.schemas.common import MovaModel
from app.schemas.itinerary import Itinerary
from app.schemas.planner import PlannerOptions, PlanGenerationResult
from app.schemas.trip import TripRequest

class PlanModification(MovaModel):
    action: str = Field(min_length=1)
    place_id: str | None = None
    day: int | None = Field(default=None, ge=1)
    start: str | None = None
    end: str | None = None
    reason: str | None = None

    @model_validator(mode="after")
    def validate_action(self):
        allowed={"add_place","remove_place","move_place","reoptimize"}
        if self.action not in allowed:
            raise ValueError(f"unsupported action: {self.action}")
        if self.action in {"add_place","remove_place","move_place"} and not self.place_id:
            raise ValueError("place_id is required for this action")
        if self.action == "move_place" and self.day is None:
            raise ValueError("day is required for move_place")
        return self

class PlanModificationRequest(MovaModel):
    trip: TripRequest
    itinerary: Itinerary
    modifications: list[PlanModification] = Field(min_length=1, max_length=20)
    options: PlannerOptions = Field(default_factory=PlannerOptions)

class PlanModificationResult(MovaModel):
    plan: PlanGenerationResult
    applied: list[PlanModification] = Field(default_factory=list)
    rejected: list[PlanModification] = Field(default_factory=list)
    messages: list[str] = Field(default_factory=list)
