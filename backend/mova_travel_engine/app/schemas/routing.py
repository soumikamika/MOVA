"""API-ready routing and travel-method contracts."""
from __future__ import annotations

from pydantic import Field

from app.schemas.common import MovaModel


class RouteResult(MovaModel):
    origin: str
    destination: str
    distance_km: float | None = Field(default=None, ge=0)
    duration_minutes: float | None = Field(default=None, ge=0)
    geometry: list[list[float]] = Field(default_factory=list)
    source: str | None = None
    status: str
    notes: list[str] = Field(default_factory=list)


class RouteLeg(MovaModel):
    origin: str
    destination: str
    distance_km: float | None = Field(default=None, ge=0)
    duration_minutes: float | None = Field(default=None, ge=0)
    mode: str
    estimated_cost_inr: float | None = Field(default=None, ge=0)
    source: str | None = None
    status: str
    geometry: list[list[float]] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)


class TravelOption(MovaModel):
    mode: str
    duration_minutes: float | None = Field(default=None, ge=0)
    distance_km: float | None = Field(default=None, ge=0)
    estimated_cost_inr: float | None = Field(default=None, ge=0)
    status: str
    source: str | None = None
    reason: str
    fuel_type: str | None = None
    fuel_cost_inr: float | None = Field(default=None, ge=0)


class TravelMethodRecommendation(MovaModel):
    recommended_mode: str | None = None
    options: list[TravelOption] = Field(default_factory=list)
    reason: str
    travellers: int = Field(ge=1)
    source: str
