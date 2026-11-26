"""ConstraintContext: bundles everything a rule needs into one argument.

A plain dataclass, not a pydantic schema - like app.data.repositories.base's
`Repositories`, this is internal wiring (it can carry live service instances
and repository interfaces), not a wire/storage schema. Building a context
never calls a repository or a provider itself: the caller (a future planner/
orchestrator) fetches whatever Place/Restaurant/Destination records it already
has and hands them over, keeping the constraint engine decoupled from
repository implementations.

`travel_time_service`/`travel_cost_service`/`repositories` are accepted for
forward compatibility with later phases (e.g. cross-checking a stated
duration against an independent prediction) - the Phase E1 rules below do not
call them, since every E1 rule operates on data the itinerary already
contains.
"""
from collections.abc import Mapping
from dataclasses import dataclass, field

from app.data.repositories.base import Repositories
from app.schemas.itinerary import Itinerary
from app.schemas.place import Destination, Place, Restaurant
from app.schemas.trip import TripRequest
from app.travel_cost.service import TravelCostService
from app.travel_time.service import TravelTimeService


@dataclass(frozen=True)
class ConstraintContext:
    trip: TripRequest
    itinerary: Itinerary

    places: Mapping[str, Place] = field(default_factory=dict)
    restaurants: Mapping[str, Restaurant] = field(default_factory=dict)
    destinations: Mapping[str, Destination] = field(default_factory=dict)

    travel_time_service: TravelTimeService | None = None
    travel_cost_service: TravelCostService | None = None
    repositories: Repositories | None = None
