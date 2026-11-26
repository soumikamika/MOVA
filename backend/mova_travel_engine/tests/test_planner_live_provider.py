import datetime as dt

from app.data.repositories.json_repos import json_repositories_in_memory
from app.providers.osm import OSMProvider
from app.schemas.common import DataSource
from app.schemas.place import Destination, GeoPoint, Place
from app.schemas.planner import PlanGenerationRequest
from app.schemas.trip import TripRequest
from app.services.planner import PlannerService


class FakeProvider:
    def resolve_destination(self, query):
        if query.casefold() != "hyderabad":
            return None
        return Destination(
            id="osm:relation:999", name="Hyderabad", state="Telangana",
            center=GeoPoint(latitude=17.385, longitude=78.4867),
            source=DataSource.EXTERNAL_API,
        )

    def discover_places(self, destination):
        return [Place(
            id="osm:node:1", destination_id=destination.id, name="Live Museum",
            category="museum", location=GeoPoint(latitude=17.39, longitude=78.49),
            avg_visit_minutes=60, intensity=2, source=DataSource.EXTERNAL_API,
        )]


def test_planner_falls_back_to_live_provider_for_unknown_destination():
    trip = TripRequest(
        destination="Hyderabad", destinations=["Hyderabad"],
        start_date=dt.date.today() + dt.timedelta(days=10),
        end_date=dt.date.today() + dt.timedelta(days=11),
        travellers=2, trip_type="friends", budget=10000,
        interests=["culture"],
    )
    repos = json_repositories_in_memory()
    result = PlannerService(repos, live_provider=FakeProvider()).generate(PlanGenerationRequest(trip=trip))
    assert result.destination_name == "Hyderabad"
    assert result.data_quality.sources == [DataSource.EXTERNAL_API]
    assert result.data_quality.development_only is False
    assert result.data_quality.candidates == 1
    assert result.itinerary.days
