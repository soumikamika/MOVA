import datetime as dt

import pytest

from app.core.exceptions import DataUnavailableError, NotFoundError
from app.data.repositories.json_repos import json_repositories_in_memory
from app.schemas.planner import PlanGenerationRequest, PlannerOptions
from app.services.planner import PlannerService
from tests.factories import make_destination, make_place, make_restaurant, make_hotel, make_repos
from tests.factories_constraints import make_trip


def future_trip(**kw):
    base = dict(
        destination="Testville",
        start_date=dt.date.today() + dt.timedelta(days=30),
        end_date=dt.date.today() + dt.timedelta(days=31),
        travellers=2,
        trip_type="friends",
        budget=30000,
        interests=["beach"],
    )
    base.update(kw)
    from app.schemas.trip import TripRequest
    return TripRequest(**base)


def test_planner_orchestrates_recommendation_optimizer_and_returns_contract():
    repos = make_repos(
        places=[
            make_place(id="p1", name="One"),
            make_place(id="p2", name="Two", location={"latitude": 15.51, "longitude": 73.81}),
        ]
    )
    result = PlannerService(repos).generate(PlanGenerationRequest(trip=future_trip()))
    assert result.destination_id == "testville"
    assert result.recommendations
    assert result.itinerary.days
    assert result.optimizer_method.startswith("greedy_e2")
    assert result.engine.optimizer_method == result.optimizer_method
    assert result.data_quality.candidates == 2


def test_planner_resolves_destination_case_insensitively_via_repository():
    repos = make_repos()
    result = PlannerService(repos).generate(
        PlanGenerationRequest(trip=future_trip(destination=" testville "))
    )
    assert result.destination_name == "Testville"


def test_planner_rejects_unknown_destination():
    repos = make_repos()
    with pytest.raises(NotFoundError):
        PlannerService(repos).generate(PlanGenerationRequest(trip=future_trip(destination="Unknownville")))


def test_planner_reports_missing_places_instead_of_fabricating():
    repos = make_repos(places=[])
    with pytest.raises(DataUnavailableError):
        PlannerService(repos).generate(PlanGenerationRequest(trip=future_trip()))


def test_planner_can_generate_from_base_itinerary_without_new_candidates():
    from tests.factories_constraints import itinerary, day, activity
    repos = make_repos(places=[make_place(id="p1")])
    trip = future_trip()
    base = itinerary(day(1, [activity("09:00", "10:00", 60, place_id="p1")]), day(2, []))
    result = PlannerService(repos).generate(
        PlanGenerationRequest(trip=trip, base_itinerary=base)
    )
    assert result.itinerary.days[0].items


def test_planner_surfaces_development_only_data():
    repos = make_repos()
    result = PlannerService(repos).generate(PlanGenerationRequest(trip=future_trip()))
    assert result.data_quality.development_only is True
    assert "development" in " ".join(result.data_quality.notes).lower()


def test_planner_candidate_limit_is_applied():
    places = [make_place(id=f"p{i}") for i in range(8)]
    repos = make_repos(places=places)
    result = PlannerService(repos).generate(
        PlanGenerationRequest(trip=future_trip(), options=PlannerOptions(candidate_limit=3))
    )
    assert result.data_quality.candidates == 3
    assert len(result.recommendations) == 3


def test_planner_optional_supporting_data_can_be_disabled():
    repos = make_repos()
    result = PlannerService(repos).generate(
        PlanGenerationRequest(
            trip=future_trip(),
            options=PlannerOptions(include_restaurants=False, include_hotels=False),
        )
    )
    assert result.data_quality.restaurants == 0
    assert result.data_quality.hotels == 0
