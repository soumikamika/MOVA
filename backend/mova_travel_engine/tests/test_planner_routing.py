import datetime as dt

from app.data.repositories.json_repos import json_repositories_in_memory
from app.schemas.planner import PlanGenerationRequest
from app.schemas.routing import RouteResult
from app.schemas.trip import TripRequest
from app.services.planner import PlannerService
from app.routing.service import RoutingService
from tests.factories import make_destination, make_place, make_repos


class FakeRoutingProvider:
    def __init__(self):
        self.calls = []

    def route(self, **kwargs):
        self.calls.append(kwargs)
        return RouteResult(
            origin=kwargs["origin_name"],
            destination=kwargs["destination_name"],
            distance_km=100,
            duration_minutes=120,
            source="OSRM",
            status="available",
        )


def trip(**updates):
    data = dict(
        destination="Goa",
        destinations=["Goa"],
        start_date=dt.date.today() + dt.timedelta(days=30),
        end_date=dt.date.today() + dt.timedelta(days=31),
        travellers=2,
        trip_type="friends",
        budget=30000,
        interests=["beach"],
        origin="Hyderabad",
        origin_latitude=17.385,
        origin_longitude=78.4867,
    )
    data.update(updates)
    return TripRequest(**data)


def repos_for(*names):
    destinations = []
    places = []
    for index, name in enumerate(names):
        destinations.append(make_destination(
            id=name.lower(), name=name,
            center={"latitude": 15.4 + index, "longitude": 74.0 + index},
        ))
        places.extend([
            make_place(id=f"{name.lower()}-p1", name=f"{name} Beach", destination_id=name.lower(),
                       location={"latitude": 15.5 + index, "longitude": 74.1 + index}),
            make_place(id=f"{name.lower()}-p2", name=f"{name} Museum", destination_id=name.lower(),
                       location={"latitude": 15.6 + index, "longitude": 74.2 + index}),
        ])
    return json_repositories_in_memory(destinations=destinations, places=places)


def test_planner_adds_origin_to_destination_route():
    provider = FakeRoutingProvider()
    planner = PlannerService(repos_for("Goa"), routing_service=RoutingService(provider=provider))
    result = planner.generate(PlanGenerationRequest(trip=trip()))
    assert len(result.route_legs) == 1
    assert result.route_legs[0].origin == "Hyderabad"
    assert result.route_legs[0].destination == "Goa"
    assert result.route_legs[0].distance_km == 100
    assert result.travel_method.recommended_mode == "car"


def test_planner_builds_inter_destination_route_legs():
    provider = FakeRoutingProvider()
    planner = PlannerService(
        repos_for("Goa", "Mumbai", "Pune"),
        routing_service=RoutingService(provider=provider),
    )
    result = planner.generate(PlanGenerationRequest(trip=trip(
        destination="Goa",
        destinations=["Goa", "Mumbai", "Pune"],
        end_date=dt.date.today() + dt.timedelta(days=32),
    )))
    assert [(x.origin, x.destination) for x in result.route_legs] == [
        ("Hyderabad", "Goa"),
        ("Goa", "Mumbai"),
        ("Mumbai", "Pune"),
    ]
    assert result.travel_method.recommended_mode == "car"


def test_planner_does_not_require_routing_coordinates():
    provider = FakeRoutingProvider()
    planner = PlannerService(repos_for("Goa"), routing_service=RoutingService(provider=provider))
    result = planner.generate(PlanGenerationRequest(trip=trip(
        origin=None, origin_latitude=None, origin_longitude=None,
    )))
    assert result.itinerary.days
    assert result.route_legs[0].status == "unavailable"
    assert provider.calls == []


class FakeOriginGeocoder:
    def resolve_destination(self, query):
        if query.casefold() == "hyderabad":
            return make_destination(id="hyd", name="Hyderabad", center={"latitude":17.385,"longitude":78.4867})
        return None


def test_planner_geocodes_manual_origin_when_coordinates_are_missing():
    provider = FakeOriginGeocoder()
    routing = RoutingService(provider=FakeRoutingProvider())
    planner = PlannerService(repos_for("Goa"), routing_service=routing, live_provider=provider)
    result = planner.generate(PlanGenerationRequest(trip=trip(
        origin="Hyderabad", origin_latitude=None, origin_longitude=None,
    )))
    assert result.route_legs[0].origin == "Hyderabad"
    assert result.route_legs[0].status == "available"
