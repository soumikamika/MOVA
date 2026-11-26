"""Wire schemas for the Phase E2 optimizer.

The optimizer is deliberately independent of the future API layer.  The same
request/result objects can later be exposed through FastAPI without changing
optimization logic.
"""
from pydantic import Field

from app.schemas.common import MovaModel, TransportMode
from app.schemas.itinerary import Itinerary, PlanConflict
from app.schemas.place import Place, Restaurant
from app.schemas.recommendation import Recommendation
from app.schemas.trip import TripRequest


class OptimizerOptions(MovaModel):
    day_start: str = "09:00"
    day_end: str = "19:00"
    minimum_gap_minutes: int = Field(default=0, ge=0)
    default_transport: TransportMode = TransportMode.CAB
    max_activities_per_day: int = Field(default=4, ge=1, le=12)
    preserve_base_order: bool = False
    required_place_ids: list[str] = Field(default_factory=list)
    excluded_place_ids: list[str] = Field(default_factory=list)


class OptimizerRequest(MovaModel):
    trip: TripRequest
    candidates: list[Place] = Field(default_factory=list)
    recommendations: list[Recommendation] = Field(default_factory=list)
    restaurants: list[Restaurant] = Field(default_factory=list)
    base_itinerary: Itinerary | None = None
    options: OptimizerOptions = Field(default_factory=OptimizerOptions)


class OptimizationChange(MovaModel):
    action: str
    place_id: str | None = None
    day: int | None = None
    reason: str


class OptimizerResult(MovaModel):
    itinerary: Itinerary
    feasible: bool
    objective_score: float = Field(ge=0)
    optimizer_method: str
    iterations: int = Field(ge=0)
    changes: list[OptimizationChange] = Field(default_factory=list)
    rejected_place_ids: list[str] = Field(default_factory=list)
    conflicts: list[PlanConflict] = Field(default_factory=list)
    warnings: list[PlanConflict] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)
