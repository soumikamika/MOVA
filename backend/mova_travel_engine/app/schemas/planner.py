"""Stable wire contract for the MOVA Plan Orchestrator.

These schemas are intentionally API-ready but do not depend on FastAPI.  The
same objects can be used by a future HTTP adapter without changing planner
business logic.
"""
from app.schemas.common import ConfidenceLevel, DataSource, MovaModel
from app.schemas.itinerary import Itinerary, PlanConflict
from app.schemas.budget import BudgetStatus
from app.schemas.optimizer import OptimizationChange, OptimizerOptions
from app.schemas.recommendation import Recommendation
from app.schemas.trip import TripRequest
from app.schemas.routing import RouteLeg, TravelMethodRecommendation
from pydantic import Field


class PlannerOptions(MovaModel):
    """Controls data retrieval and optimization without exposing repositories."""
    candidate_limit: int = Field(default=100, ge=1, le=500)
    include_restaurants: bool = True
    include_hotels: bool = True
    optimizer: OptimizerOptions = Field(default_factory=OptimizerOptions)


class PlanGenerationRequest(MovaModel):
    """Future POST /api/plans/generate request body."""
    trip: TripRequest
    base_itinerary: Itinerary | None = None
    options: PlannerOptions = Field(default_factory=PlannerOptions)


class EngineStatus(MovaModel):
    recommendation_method: str
    recommendation_model_loaded: bool
    recommendation_model_production: bool
    travel_time_method: str
    travel_time_model_loaded: bool
    travel_time_model_production: bool
    travel_cost_method: str
    travel_cost_model_loaded: bool
    travel_cost_model_production: bool
    optimizer_method: str


class DataQuality(MovaModel):
    """Provenance summary for the UI; never presented as model accuracy."""
    sources: list[DataSource] = Field(default_factory=list)
    development_only: bool
    destinations: int = Field(ge=0)
    candidates: int = Field(ge=0)
    restaurants: int = Field(ge=0)
    hotels: int = Field(ge=0)
    recommendations: int = Field(ge=0)
    confidence: ConfidenceLevel
    notes: list[str] = Field(default_factory=list)


class PlanGenerationResult(MovaModel):
    """Single stable response for Create Plan / My Plans integration."""
    plan_id: str
    destination_id: str
    destination_name: str
    trip: TripRequest
    itinerary: Itinerary
    recommendations: list[Recommendation] = Field(default_factory=list)
    changes: list[OptimizationChange] = Field(default_factory=list)
    rejected_place_ids: list[str] = Field(default_factory=list)
    feasible: bool
    objective_score: float = Field(ge=0)
    optimizer_method: str
    iterations: int = Field(ge=0)
    conflicts: list[PlanConflict] = Field(default_factory=list)
    warnings: list[PlanConflict] = Field(default_factory=list)
    route_legs: list[RouteLeg] = Field(default_factory=list)
    travel_method: TravelMethodRecommendation | None = None
    budget_status: BudgetStatus | None = None
    engine: EngineStatus
    data_quality: DataQuality
    notes: list[str] = Field(default_factory=list)
