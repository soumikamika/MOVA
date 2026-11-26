"""Phase E1: the constraint engine. Every test proves a specific violation is
detected, proves a specific non-violation is NOT falsely raised, or proves
unknown data is reported rather than fabricated."""
import pytest

from app.constraints.context import ConstraintContext
from app.constraints.engine import ConstraintEngine
from app.constraints.rules import RULES
from app.schemas.common import ConflictType, Severity
from app.schemas.itinerary import Itinerary, ItineraryItem
from app.schemas.place import OpeningHours
from tests.factories_constraints import (
    START, activity, day, itinerary, make_context, make_eatery, make_place, make_trip, meal, rest, travel,
)

engine = ConstraintEngine()


def _types(items, severity=None):
    return [c.type.value for c in items if severity is None or c.severity == severity]


# ------------------------------ valid baseline -----------------------------------
def test_valid_itinerary_produces_no_conflicts():
    trip = make_trip(budget=5000)
    place = make_place()
    plan = itinerary(day(1, [activity("09:00", "11:00", 120)]))
    result = engine.validate(make_context(trip, plan, {"p1": place}))
    assert result.feasible is True
    assert result.conflicts == []


def test_empty_itinerary_is_feasible_with_no_conflicts_or_warnings():
    result = engine.validate(make_context())
    assert result.feasible is True
    assert result.conflicts == [] and result.warnings == []


def test_rest_item_with_no_cost_field_does_not_affect_budget():
    trip = make_trip(budget=10)
    plan = itinerary(day(1, [rest("09:00", "10:00", 60)]))
    result = engine.validate(make_context(trip, plan))
    assert result.feasible is True


# ------------------------------ 1. duplicate places -------------------------------
def test_duplicate_place_detected():
    trip = make_trip()
    place = make_place()
    plan = itinerary(day(1, [
        activity("09:00", "10:00", 60, place_id="p1"),
        activity("11:00", "12:00", 60, place_id="p1"),
    ]))
    result = engine.validate(make_context(trip, plan, {"p1": place}))
    assert result.feasible is False
    assert ConflictType.DUPLICATE_PLACE.value in _types(result.conflicts)
    conflict = next(c for c in result.conflicts if c.type == ConflictType.DUPLICATE_PLACE)
    assert conflict.severity == Severity.HIGH
    assert conflict.details["place_id"] == "p1"


def test_different_places_are_not_flagged_as_duplicates():
    trip = make_trip()
    plan = itinerary(day(1, [
        activity("09:00", "10:00", 60, place_id="p1"),
        activity("11:00", "12:00", 60, place_id="p2"),
    ]))
    result = engine.validate(make_context(trip, plan, {"p1": make_place(id="p1"), "p2": make_place(id="p2")}))
    assert ConflictType.DUPLICATE_PLACE.value not in _types(result.conflicts)


# ------------------------------ 2. overlapping items ------------------------------
def test_overlapping_itinerary_items_detected():
    trip = make_trip()
    plan = itinerary(day(1, [activity("09:00", "11:00", 120), activity("10:00", "12:00", 120, place_id="p2")]))
    result = engine.validate(make_context(trip, plan, {"p1": make_place(), "p2": make_place(id="p2")}))
    assert result.feasible is False
    assert ConflictType.OVERLAP.value in _types(result.conflicts)


def test_touching_items_do_not_overlap():
    trip = make_trip()
    plan = itinerary(day(1, [activity("09:00", "11:00", 120), activity("11:00", "12:00", 60)]))
    result = engine.validate(make_context(trip, plan, {"p1": make_place()}))
    assert ConflictType.OVERLAP.value not in _types(result.conflicts)


# ------------------------------ 3. opening hours ----------------------------------
def test_opening_hours_conflict_detected():
    trip = make_trip()
    place = make_place(opening_hours=OpeningHours.daily("12:00", "18:00"))
    plan = itinerary(day(1, [activity("09:00", "10:00", 60)]))
    result = engine.validate(make_context(trip, plan, {"p1": place}))
    assert result.feasible is False
    assert ConflictType.OPENING_HOURS.value in _types(result.conflicts, Severity.HIGH)


def test_open_at_scheduled_time_is_not_flagged():
    trip = make_trip()
    place = make_place(opening_hours=OpeningHours.daily("08:00", "20:00"))
    plan = itinerary(day(1, [activity("09:00", "10:00", 60)]))
    result = engine.validate(make_context(trip, plan, {"p1": place}))
    assert ConflictType.OPENING_HOURS.value not in _types(result.conflicts)


def test_visit_exactly_at_opening_boundary_is_not_flagged():
    trip = make_trip()
    place = make_place(opening_hours=OpeningHours.daily("09:00", "10:00"))
    plan = itinerary(day(1, [activity("09:00", "10:00", 60)]))
    result = engine.validate(make_context(trip, plan, {"p1": place}))
    assert result.feasible is True


def test_unknown_opening_hours_is_a_warning_not_a_conflict():
    trip = make_trip()
    place = make_place(opening_hours=None)
    plan = itinerary(day(1, [activity("09:00", "10:00", 60)]))
    result = engine.validate(make_context(trip, plan, {"p1": place}))
    assert result.feasible is True          # a warning never blocks feasibility
    assert ConflictType.OPENING_HOURS.value not in _types(result.conflicts)
    assert ConflictType.MISSING_DATA.value in _types(result.warnings, Severity.LOW)


def test_restaurant_opening_hours_checked_for_meals():
    trip = make_trip()
    eatery = make_eatery(opening_hours=OpeningHours.daily("18:00", "22:00"))
    plan = itinerary(day(1, [meal("12:00", "13:00", 60)]))
    result = engine.validate(make_context(trip, plan, restaurants={"r1": eatery}))
    assert result.feasible is False
    assert ConflictType.OPENING_HOURS.value in _types(result.conflicts)


# ------------------------------ 4. invalid/missing place references --------------
def test_missing_place_reference_detected():
    trip = make_trip()
    plan = itinerary(day(1, [activity("09:00", "10:00", 60, place_id="does_not_exist")]))
    result = engine.validate(make_context(trip, plan, places={}))
    assert result.feasible is False
    assert ConflictType.UNAVAILABLE_PLACE.value in _types(result.conflicts, Severity.HIGH)


def test_missing_restaurant_reference_detected():
    trip = make_trip()
    plan = itinerary(day(1, [meal("12:00", "13:00", 60, restaurant_id="does_not_exist")]))
    result = engine.validate(make_context(trip, plan, restaurants={}))
    assert result.feasible is False
    assert ConflictType.UNAVAILABLE_PLACE.value in _types(result.conflicts)


def test_valid_place_reference_not_flagged():
    trip = make_trip()
    plan = itinerary(day(1, [activity("09:00", "10:00", 60, place_id="p1")]))
    result = engine.validate(make_context(trip, plan, {"p1": make_place()}))
    assert ConflictType.UNAVAILABLE_PLACE.value not in _types(result.conflicts)


# ------------------------------ 5. insufficient meal time -------------------------
def test_insufficient_meal_time_detected():
    trip = make_trip()
    plan = itinerary(day(1, [meal("12:00", "12:10", 10)]))
    result = engine.validate(make_context(trip, plan, restaurants={"r1": make_eatery()}))
    assert result.feasible is False
    assert ConflictType.INSUFFICIENT_MEAL_TIME.value in _types(result.conflicts, Severity.HIGH)


def test_sufficient_meal_time_not_flagged():
    trip = make_trip()
    plan = itinerary(day(1, [meal("12:00", "13:00", 60)]))
    result = engine.validate(make_context(trip, plan, restaurants={"r1": make_eatery()}))
    assert ConflictType.INSUFFICIENT_MEAL_TIME.value not in _types(result.conflicts)


def test_meal_duration_exactly_at_minimum_is_not_flagged():
    trip = make_trip()
    plan = itinerary(day(1, [meal("12:00", "12:20", 20)]))   # exactly DEFAULT_MIN_MEAL_MINUTES
    result = engine.validate(make_context(trip, plan, restaurants={"r1": make_eatery()}))
    assert ConflictType.INSUFFICIENT_MEAL_TIME.value not in _types(result.conflicts)


# ------------------------------ 6. excessive density ------------------------------
def test_excessive_density_detected_as_warning():
    trip = make_trip()
    place = make_place(opening_hours=OpeningHours(always_open=True))
    plan = itinerary(day(1, [activity("06:00", "16:00", 600, place_id="p1")]))  # 10h, exceeds 600-min default? equal
    # push just over the threshold
    plan = itinerary(day(1, [activity("06:00", "16:01", 601, place_id="p1")]))
    result = engine.validate(make_context(trip, plan, {"p1": place}))
    assert result.feasible is True   # density is a warning, never blocking
    assert ConflictType.EXCESSIVE_DENSITY.value in _types(result.warnings, Severity.MEDIUM)


def test_moderate_density_not_flagged():
    trip = make_trip()
    place = make_place()
    plan = itinerary(day(1, [activity("09:00", "11:00", 120, place_id="p1")]))
    result = engine.validate(make_context(trip, plan, {"p1": place}))
    assert ConflictType.EXCESSIVE_DENSITY.value not in _types(result.warnings)


# ------------------------------ 7. budget overrun ---------------------------------
def test_budget_overrun_detected():
    trip = make_trip(budget=100)
    plan = itinerary(day(1, [activity("09:00", "10:00", 60, cost_inr=5000)]))
    result = engine.validate(make_context(trip, plan, {"p1": make_place()}))
    assert result.feasible is False
    assert ConflictType.BUDGET_OVERRUN.value in _types(result.conflicts, Severity.HIGH)


def test_budget_within_limit_not_flagged():
    trip = make_trip(budget=1000)
    plan = itinerary(day(1, [activity("09:00", "10:00", 60, cost_inr=500)]))
    result = engine.validate(make_context(trip, plan, {"p1": make_place()}))
    assert result.feasible is True
    assert ConflictType.BUDGET_OVERRUN.value not in _types(result.conflicts)


def test_zero_cost_is_valid_not_treated_as_unknown():
    trip = make_trip(budget=100)
    plan = itinerary(day(1, [activity("09:00", "10:00", 60, cost_inr=0)]))
    result = engine.validate(make_context(trip, plan, {"p1": make_place()}))
    assert result.feasible is True
    assert result.warnings == []


def test_unknown_item_cost_is_a_warning_not_assumed_free():
    trip = make_trip(budget=100)
    plan = itinerary(day(1, [activity("09:00", "10:00", 60, cost_inr=None)]))
    result = engine.validate(make_context(trip, plan, {"p1": make_place()}))
    assert result.feasible is True   # unknown cost cannot assert an overrun, so it's a warning, not a conflict
    assert ConflictType.MISSING_DATA.value in _types(result.warnings, Severity.MEDIUM)
    assert ConflictType.BUDGET_OVERRUN.value not in _types(result.conflicts)


# ------------------------------ 8. excessive travel -------------------------------
def test_excessive_travel_detected_as_warning():
    trip = make_trip()
    plan = itinerary(day(1, [travel("09:00", "13:30", 270, from_id="p1", to_id="p2")]))  # 4.5h > 4h default
    result = engine.validate(make_context(trip, plan))
    assert result.feasible is True
    assert ConflictType.EXCESSIVE_TRAVEL.value in _types(result.warnings, Severity.MEDIUM)


def test_moderate_travel_not_flagged():
    trip = make_trip()
    plan = itinerary(day(1, [travel("09:00", "09:30", 30, from_id="p1", to_id="p2")]))
    result = engine.validate(make_context(trip, plan))
    assert ConflictType.EXCESSIVE_TRAVEL.value not in _types(result.warnings)


# ------------------------------ multiple conflicts collected together ------------
def test_multiple_conflicts_are_collected_together():
    trip = make_trip(budget=10)
    place = make_place(opening_hours=OpeningHours.daily("12:00", "18:00"))
    plan = itinerary(day(1, [
        activity("09:00", "10:30", 90, place_id="p1", cost_inr=5000),
        activity("10:00", "11:00", 60, place_id="p1", cost_inr=0),   # overlaps + duplicates p1
    ]))
    result = engine.validate(make_context(trip, plan, {"p1": place}))
    assert result.feasible is False
    found = {c.type for c in result.conflicts}
    assert {ConflictType.DUPLICATE_PLACE, ConflictType.OVERLAP, ConflictType.OPENING_HOURS,
           ConflictType.BUDGET_OVERRUN} <= found


# ------------------------------ warnings never flip feasibility ------------------
def test_warnings_do_not_make_an_otherwise_feasible_plan_infeasible():
    trip = make_trip(budget=5000)
    place = make_place(opening_hours=None)  # -> warning only
    plan = itinerary(day(1, [
        activity("09:00", "13:30", 270, place_id="p1"),              # excessive travel/density not triggered here
        travel("13:30", "18:00", 270, from_id="p1", to_id="p2"),     # excessive travel -> warning
    ]))
    result = engine.validate(make_context(trip, plan, {"p1": place}))
    assert result.conflicts == []
    assert result.warnings != []
    assert result.feasible is True


def test_hard_conflicts_make_feasible_false():
    trip = make_trip()
    plan = itinerary(day(1, [activity("09:00", "10:00", 60, place_id="missing")]))
    result = engine.validate(make_context(trip, plan, places={}))
    assert result.conflicts != [] and result.feasible is False


# ------------------------------ all rules execute ---------------------------------
def test_all_registered_rules_execute_through_the_engine():
    trip = make_trip()
    result = engine.validate(make_context(trip, itinerary()))
    assert result.checked_rules == list(RULES.keys())
    assert len(result.checked_rules) == 8


def test_checked_rules_present_even_when_itinerary_has_no_days():
    result = engine.validate(make_context())
    assert len(result.checked_rules) == 8


# ------------------------------ malformed inputs ----------------------------------
def test_malformed_itinerary_item_rejected_at_schema_level():
    with pytest.raises(Exception):
        ItineraryItem(type="activity", start="10:00", end="09:00", duration_minutes=60, place_id="p1")


def test_engine_does_not_crash_on_itinerary_with_no_days():
    result = engine.validate(make_context(itin=Itinerary(plan_id="empty")))
    assert result.feasible is True


# ------------------------------ result schema invariants --------------------------
def test_constraint_result_fields_present():
    trip = make_trip()
    plan = itinerary(day(1, [activity("09:00", "10:00", 60)]))
    result = engine.validate(make_context(trip, plan, {"p1": make_place()}))
    assert isinstance(result.feasible, bool)
    assert isinstance(result.conflicts, list) and isinstance(result.warnings, list)
    assert isinstance(result.checked_rules, list) and all(isinstance(r, str) for r in result.checked_rules)


def test_result_reuses_existing_planconflict_schema():
    from app.schemas.itinerary import PlanConflict
    trip = make_trip(budget=10)
    plan = itinerary(day(1, [activity("09:00", "10:00", 60, cost_inr=500)]))
    result = engine.validate(make_context(trip, plan, {"p1": make_place()}))
    assert all(isinstance(c, PlanConflict) for c in result.conflicts)


# ------------------------------ existing Phase D behavior unaffected -------------
def test_recommendation_service_still_works():
    from app.recommendation.service import RecommendationService
    from tests.factories import make_place as reco_place
    from tests.factories_recommendation import make_trip as reco_trip
    recs = RecommendationService().recommend(reco_trip(), [reco_place(id="a"), reco_place(id="b")])
    assert len(recs) == 2


def test_travel_time_and_travel_cost_services_still_work():
    from app.travel_time.service import TravelTimeService
    from app.travel_cost.service import TravelCostService
    from app.schemas.logistics import TravelTimeRequest, CostRequest
    tt = TravelTimeService().predict(TravelTimeRequest(origin="A", destination="B", mode="car", distance_km=50))
    tc = TravelCostService().predict(CostRequest(category="food", travellers=2, quantity=2, unit_price_inr=300))
    assert tt.prediction_type == "travel_time_minutes" and tc.prediction_type == "cost_food_inr"
