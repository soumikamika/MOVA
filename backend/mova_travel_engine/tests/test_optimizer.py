import datetime as dt

from app.optimizer.service import OptimizerService
from app.schemas.optimizer import OptimizerRequest, OptimizerOptions
from tests.factories_constraints import make_place, make_trip, itinerary, day, activity
from app.schemas.itinerary import Itinerary


def test_optimizer_generates_a_structurally_valid_itinerary():
    trip = make_trip(start_date=dt.date.today() + dt.timedelta(days=30), end_date=dt.date.today() + dt.timedelta(days=31))
    places = [
        make_place(id="p1", name="One", avg_visit_minutes=60),
        make_place(id="p2", name="Two", avg_visit_minutes=60),
        make_place(id="p3", name="Three", avg_visit_minutes=60),
    ]
    result = OptimizerService().optimize(OptimizerRequest(trip=trip, candidates=places))
    assert isinstance(result.itinerary, Itinerary)
    assert len(result.itinerary.days) == 2
    assert result.optimizer_method == "greedy_e2"
    assert result.itinerary.days[0].items


def test_optimizer_does_not_schedule_closed_place():
    trip = make_trip()
    closed = make_place(id="closed", opening_hours=None, closed_months=[trip.start_date.month])
    result = OptimizerService().optimize(OptimizerRequest(trip=trip, candidates=[closed]))
    assert result.itinerary.days[0].items == []
    assert "closed" in result.rejected_place_ids


def test_optimizer_respects_max_activities_per_day():
    trip = make_trip()
    places = [make_place(id=f"p{i}") for i in range(6)]
    result = OptimizerService().optimize(OptimizerRequest(
        trip=trip, candidates=places,
        options=OptimizerOptions(max_activities_per_day=2),
    ))
    assert sum(i.type.value == "activity" for i in result.itinerary.days[0].items) <= 2


def test_optimizer_preserves_unknown_costs_instead_of_guessing():
    trip = make_trip()
    place = make_place(id="unknown", entry_fee_inr=None)
    result = OptimizerService().optimize(OptimizerRequest(trip=trip, candidates=[place]))
    activity_items = [i for d in result.itinerary.days for i in d.items if i.place_id == "unknown"]
    assert activity_items and activity_items[0].cost_inr is None
    assert any(w.type.value == "missing_data" for w in result.warnings)


def test_optimizer_repairs_duplicate_place_conflict_in_base_itinerary():
    trip = make_trip()
    place = make_place(id="p1")
    base = itinerary(day(1, [activity("09:00", "10:00", 60, place_id="p1"), activity("11:00", "12:00", 60, place_id="p1")]))
    result = OptimizerService().optimize(OptimizerRequest(trip=trip, candidates=[place], base_itinerary=base))
    assert result.feasible
    assert len([i for d in result.itinerary.days for i in d.items if i.place_id == "p1"]) == 1
    assert result.changes and result.changes[-1].action == "remove"
