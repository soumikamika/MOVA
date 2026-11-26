"""Phase 1: the journey from the traveller's origin must affect the plan.

The routing provider is a FAKE keyed by city pair. The distances/durations below
are test fixtures chosen to exercise the logic; they are NOT real routing data.
"""
import datetime as dt

from app.routing.service import RoutingService
from app.schemas.common import ConflictType
from app.schemas.planner import PlanGenerationRequest
from app.schemas.routing import RouteResult
from app.services.planner import PlannerService
from tests.test_planner_routing import repos_for, trip

# (origin, destination) -> (km, minutes)   [fixtures]
FIXTURE_ROUTES = {
    ("Hyderabad", "Delhi"): (1550, 1560),
    ("Karimnagar", "Delhi"): (1500, 1500),
    ("Hyderabad", "Goa"): (650, 660),
}
ORIGIN_COORDS = {
    "Hyderabad": (17.385, 78.4867),
    "Karimnagar": (18.4386, 79.1288),
}


class PairRoutingProvider:
    def __init__(self):
        self.calls = []

    def route(self, **kwargs):
        self.calls.append(kwargs)
        pair = (kwargs["origin_name"], kwargs["destination_name"])
        if pair not in FIXTURE_ROUTES:
            return RouteResult(origin=pair[0], destination=pair[1], status="unavailable",
                               source="OSRM", notes=["No fixture route."])
        km, minutes = FIXTURE_ROUTES[pair]
        return RouteResult(origin=pair[0], destination=pair[1], distance_km=km,
                           duration_minutes=minutes, source="OSRM", status="available")


def planner_for(*names, provider=None):
    provider = provider or PairRoutingProvider()
    return PlannerService(repos_for(*names), routing_service=RoutingService(provider=provider)), provider


def delhi_trip(origin, days, **updates):
    lat, lon = ORIGIN_COORDS[origin]
    return trip(
        destination="Delhi", destinations=["Delhi"], origin=origin,
        origin_latitude=lat, origin_longitude=lon,
        end_date=dt.date.today() + dt.timedelta(days=30 + days - 1),
        budget=100000, **updates,
    )


def types(items):
    return [c.type for c in items]


def test_hyderabad_to_delhi_includes_origin_leg_and_time():
    planner, _ = planner_for("Delhi")
    result = planner.generate(PlanGenerationRequest(trip=delhi_trip("Hyderabad", 6)))
    leg = result.route_legs[0]
    assert (leg.origin, leg.destination) == ("Hyderabad", "Delhi")
    assert leg.distance_km == 1550 and leg.duration_minutes == 1560 and leg.status == "available"
    assert ConflictType.INSUFFICIENT_TIME not in types(result.conflicts)  # 6 days is enough
    assert any("Journey from Hyderabad" in n for n in result.notes)


def test_karimnagar_to_delhi_short_trip_reports_insufficient_time_without_dropping_activities():
    planner, _ = planner_for("Delhi")
    origin_result = planner.generate(PlanGenerationRequest(trip=delhi_trip("Karimnagar", 3)))
    leg = origin_result.route_legs[0]
    assert (leg.origin, leg.destination) == ("Karimnagar", "Delhi")
    assert leg.duration_minutes == 1500

    conflict = next(c for c in origin_result.conflicts if c.type == ConflictType.INSUFFICIENT_TIME)
    assert origin_result.feasible is False
    assert conflict.details["outbound_travel_minutes"] == 1500
    assert conflict.details["return_travel_minutes"] == 1500
    assert conflict.details["additional_minutes_required"] > 0
    assert conflict.details["additional_hours_required"] > 0
    assert "additional hours" in conflict.message

    # Activities are reported, never silently removed.
    local_only = planner.generate(PlanGenerationRequest(trip=delhi_trip("Karimnagar", 3).model_copy(
        update={"origin": None, "origin_latitude": None, "origin_longitude": None})))
    def n_activities(r):
        return sum(1 for d in r.itinerary.days for i in d.items if i.type.value == "activity")
    assert n_activities(origin_result) == n_activities(local_only)


def test_hyderabad_to_goa_origin_leg_and_no_time_conflict():
    planner, provider = planner_for("Goa")
    result = planner.generate(PlanGenerationRequest(trip=trip()))
    assert (result.route_legs[0].origin, result.route_legs[0].destination) == ("Hyderabad", "Goa")
    assert result.route_legs[0].duration_minutes == 660
    assert ConflictType.INSUFFICIENT_TIME not in types(result.conflicts)
    assert len(provider.calls) >= 1


def test_extra_trip_day_reduces_the_time_shortfall():
    planner, _ = planner_for("Delhi")
    two_days = planner.generate(PlanGenerationRequest(trip=delhi_trip("Hyderabad", 2)))
    three_days = planner.generate(PlanGenerationRequest(trip=delhi_trip("Hyderabad", 3)))
    def shortfall(r):
        return next(c for c in r.conflicts if c.type == ConflictType.INSUFFICIENT_TIME).details["additional_minutes_required"]
    assert shortfall(two_days) > shortfall(three_days)  # extra day shrinks the shortfall


def test_flight_preference_does_not_invent_duration_or_block_feasibility():
    planner, _ = planner_for("Delhi")
    result = planner.generate(PlanGenerationRequest(
        trip=delhi_trip("Karimnagar", 3, preferred_travel_methods=["flight"])))
    assert result.travel_method.recommended_mode == "flight"
    assert ConflictType.INSUFFICIENT_TIME not in types(result.conflicts)
    warning = next(w for w in result.warnings if w.type == ConflictType.MISSING_DATA and w.details.get("mode") == "flight")
    assert warning.details["status"] == "NOT_INTEGRATED"
    assert "not integrated" in warning.message


def test_unresolvable_origin_without_coordinates_warns_and_does_not_fabricate():
    planner, provider = planner_for("Goa")
    result = planner.generate(PlanGenerationRequest(trip=trip(
        origin="Nowhereville", origin_latitude=None, origin_longitude=None)))
    assert result.route_legs[0].status == "unavailable"
    assert provider.calls == []
    assert any(w.type == ConflictType.MISSING_DATA and "could not be calculated" in w.message
               for w in result.warnings)


def test_origin_in_bundled_dataset_is_resolved_without_live_provider():
    planner, provider = planner_for("Goa", "Hyderabad")
    result = planner.generate(PlanGenerationRequest(trip=trip(
        origin="Hyderabad", origin_latitude=None, origin_longitude=None)))
    assert result.route_legs[0].status == "available"
    assert provider.calls[0]["origin_latitude"] == 16.4  # bundled repo centre, not guessed


def test_trip_without_origin_is_unchanged_local_only():
    planner, provider = planner_for("Delhi")
    result = planner.generate(PlanGenerationRequest(trip=trip(
        destination="Delhi", destinations=["Delhi"], origin=None,
        origin_latitude=None, origin_longitude=None)))
    assert ConflictType.INSUFFICIENT_TIME not in types(result.conflicts)
    assert not any("Journey from" in n for n in result.notes)
    assert provider.calls == []
