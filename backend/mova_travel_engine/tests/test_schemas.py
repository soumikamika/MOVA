from datetime import date, timedelta

import pytest
from pydantic import ValidationError

from app.schemas.budget import Budget, BudgetStatus, CostBreakdown, CostEstimate, EstimationMethod
from app.schemas.common import (
    DataSource, has_development_only_data, ItemType, TransportMode,
)
from app.schemas.itinerary import DayPlan, Itinerary, ItineraryItem
from app.schemas.logistics import Weather
from app.schemas.place import OpeningHours, Place, TimeWindow
from app.schemas.trip import Trip, TripRequest


def _payload(**overrides):
    start = date.today() + timedelta(days=30)
    base = {
        "destination": "Goa",
        "start_date": start.isoformat(),
        "end_date": (start + timedelta(days=4)).isoformat(),
        "travellers": 3,
        "trip_type": "friends",
        "budget": 30000,
        "interests": ["beaches", "food", "nature"],
        "dislikes": ["clubs", "crowds"],
        "transport_preference": "flexible",
        "activity_level": "moderate",
        "meal_preferences": ["vegetarian"],
    }
    base.update(overrides)
    return base


def _place(**overrides):
    base = {
        "id": "p1", "destination_id": "goa", "name": "Baga Beach",
        "category": "beach", "location": {"latitude": 15.55, "longitude": 73.75},
        "avg_visit_minutes": 120, "intensity": 2, "source": "synthetic_dev",
    }
    base.update(overrides)
    return base


# ======================= TripRequest ======================================
def test_valid_spec_example_parses():
    r = TripRequest(**_payload())
    assert r.num_days == 5
    assert r.destination == "Goa"
    assert r.interests == ["beaches", "food", "nature"]
    assert r.preference.activity_level.value == "moderate"
    assert len(r.dates) == 5


def test_tags_are_normalised_and_deduped():
    r = TripRequest(**_payload(interests=["Beach", "beaches", "Water Sports"], dislikes=[]))
    assert r.interests == ["beaches", "water_sports"]


def test_same_day_trip_is_valid():
    d = (date.today() + timedelta(days=5)).isoformat()
    assert TripRequest(**_payload(start_date=d, end_date=d)).num_days == 1


def test_end_before_start_rejected():
    start = date.today() + timedelta(days=30)
    with pytest.raises(ValidationError, match="end_date"):
        TripRequest(**_payload(end_date=(start - timedelta(days=1)).isoformat()))


def test_past_start_rejected():
    past = (date.today() - timedelta(days=3)).isoformat()
    with pytest.raises(ValidationError, match="past"):
        TripRequest(**_payload(start_date=past, end_date=past))


def test_too_long_trip_rejected():
    start = date.today() + timedelta(days=10)
    with pytest.raises(ValidationError, match="longer than"):
        TripRequest(**_payload(start_date=start.isoformat(), end_date=(start + timedelta(days=45)).isoformat()))


@pytest.mark.parametrize("bad", [0, -1, -30000])
def test_non_positive_budget_rejected(bad):
    with pytest.raises(ValidationError, match="budget"):
        TripRequest(**_payload(budget=bad))


@pytest.mark.parametrize("bad", [0, -2, 51])
def test_bad_traveller_count_rejected(bad):
    with pytest.raises(ValidationError, match="travellers"):
        TripRequest(**_payload(travellers=bad))


def test_blank_destination_rejected():
    with pytest.raises(ValidationError):
        TripRequest(**_payload(destination="   "))


def test_invalid_date_format_rejected():
    with pytest.raises(ValidationError, match="start_date"):
        TripRequest(**_payload(start_date="10/12/2026"))


def test_invalid_enum_rejected():
    with pytest.raises(ValidationError, match="activity_level"):
        TripRequest(**_payload(activity_level="extreme"))


def test_unknown_field_rejected():
    with pytest.raises(ValidationError, match="intrests"):
        TripRequest(**_payload(intrests=["beaches"]))


def test_interest_and_dislike_conflict_rejected():
    with pytest.raises(ValidationError, match="both interests and dislikes"):
        TripRequest(**_payload(interests=["beach"], dislikes=["Beaches"]))


def test_traveller_profiles_length_must_match():
    with pytest.raises(ValidationError, match="traveller_profiles"):
        TripRequest(**_payload(traveller_profiles=[{"age_group": "adult"}]))


def test_trip_wrapper_gets_id_and_timestamp():
    t = Trip.new(TripRequest(**_payload()))
    assert t.id and t.created_at.tzinfo is not None


# ======================= OpeningHours =====================================
def test_opening_hours_daily_and_is_open():
    oh = OpeningHours.daily("09:00", "17:30")
    assert oh.is_open(0, 9 * 60, 11 * 60) is True
    assert oh.is_open(0, 8 * 60, 10 * 60) is False       # starts before opening
    assert oh.is_open(0, 16 * 60, 18 * 60) is False      # ends after closing


def test_missing_weekday_means_closed():
    oh = OpeningHours(weekly={0: [TimeWindow(open="09:00", close="17:00")]})
    assert oh.is_open(0, 600, 660) is True
    assert oh.is_open(1, 600, 660) is False


def test_split_windows_activity_cannot_span_break():
    oh = OpeningHours(weekly={2: [
        TimeWindow(open="09:00", close="13:00"),
        TimeWindow(open="16:00", close="20:00"),
    ]})
    assert oh.is_open(2, 12 * 60, 13 * 60) is True
    assert oh.is_open(2, 12 * 60 + 30, 16 * 60 + 30) is False


def test_always_open():
    oh = OpeningHours(always_open=True)
    assert oh.is_open(6, 0, 1440) is True


def test_string_weekday_keys_from_json_are_coerced():
    oh = OpeningHours.model_validate({"weekly": {"0": [{"open": "09:00", "close": "10:00"}]}})
    assert oh.windows_for(0) == [(540, 600)]


def test_close_before_open_rejected():
    with pytest.raises(ValidationError, match="after open"):
        TimeWindow(open="17:00", close="09:00")


def test_overlapping_windows_rejected():
    with pytest.raises(ValidationError, match="overlapping"):
        OpeningHours(weekly={0: [
            TimeWindow(open="09:00", close="12:00"),
            TimeWindow(open="11:00", close="15:00"),
        ]})


def test_empty_schedule_rejected():
    with pytest.raises(ValidationError):
        OpeningHours()


def test_bad_weekday_key_rejected():
    with pytest.raises(ValidationError, match="weekday"):
        OpeningHours(weekly={7: [TimeWindow(open="09:00", close="10:00")]})


# ======================= Place / provenance ===============================
def test_valid_place_and_tag_normalisation():
    p = Place(**_place(tags=["Beach", "Water Sports"], closed_months=[6, 7, 7]))
    assert p.tags == ["beaches", "water_sports"]
    assert p.closed_months == [6, 7]
    assert p.entry_fee_inr is None  # unknown stays unknown, not 0


def test_source_is_mandatory():
    payload = _place()
    del payload["source"]
    with pytest.raises(ValidationError, match="source"):
        Place(**payload)


@pytest.mark.parametrize(
    "field,value",
    [
        ("rating", 5.5), ("entry_fee_inr", -10), ("avg_visit_minutes", 0),
        ("intensity", 0), ("intensity", 6), ("popularity", 1.2),
    ],
)
def test_bad_place_numbers_rejected(field, value):
    with pytest.raises(ValidationError, match=field):
        Place(**_place(**{field: value}))


def test_bad_coordinates_rejected():
    with pytest.raises(ValidationError):
        Place(**_place(location={"latitude": 95, "longitude": 73}))


def test_bad_month_rejected():
    with pytest.raises(ValidationError, match="month"):
        Place(**_place(best_months=[0, 13]))


def test_development_only_source_detection():
    assert has_development_only_data([DataSource.REAL, DataSource.SYNTHETIC_DEV]) is True
    assert has_development_only_data([DataSource.MOCK]) is True
    assert has_development_only_data([DataSource.REAL, DataSource.EXTERNAL_API]) is False
    assert has_development_only_data([]) is False


def test_weather_min_le_max():
    with pytest.raises(ValidationError, match="temp_min_c"):
        Weather(destination_id="goa", date=date(2026, 12, 10), temp_min_c=30, temp_max_c=20,
                source="external_api")


# ======================= Itinerary ========================================
def _activity(start="09:30", end="11:30", minutes=120, **kw):
    return dict(type="activity", start=start, end=end, duration_minutes=minutes, place_id="p1", **kw)


def test_valid_items():
    a = ItineraryItem(**_activity())
    t = ItineraryItem(type="travel", start="11:30", end="12:00", duration_minutes=30,
                      from_id="p1", to_id="r1", transport_mode="cab")
    m = ItineraryItem(type="meal", start="12:15", end="13:15", duration_minutes=60, restaurant_id="r1")
    assert (a.type, t.transport_mode, m.type) == (ItemType.ACTIVITY, TransportMode.CAB, ItemType.MEAL)


def test_item_end_not_after_start_rejected():
    with pytest.raises(ValidationError, match="end must be after start"):
        ItineraryItem(**_activity(start="11:30", end="09:30", minutes=120))


def test_item_duration_mismatch_rejected():
    with pytest.raises(ValidationError, match="does not match"):
        ItineraryItem(**_activity(minutes=90))


def test_activity_needs_place_id():
    with pytest.raises(ValidationError, match="place_id"):
        ItineraryItem(type="activity", start="09:00", end="10:00", duration_minutes=60)


def test_travel_needs_endpoints_and_mode():
    with pytest.raises(ValidationError, match="travel items require"):
        ItineraryItem(type="travel", start="09:00", end="09:30", duration_minutes=30, from_id="a")


def test_schema_allows_overlaps_so_constraint_engine_can_detect_them():
    day = DayPlan(day=1, date=date(2026, 12, 10), items=[
        ItineraryItem(**_activity("09:00", "11:00", 120)),
        ItineraryItem(**_activity("10:00", "12:00", 120)),  # overlaps - structurally fine
    ])
    assert day.total_activity_minutes == 240


def test_day_totals():
    day = DayPlan(day=1, date=date(2026, 12, 10), items=[
        ItineraryItem(**_activity("09:30", "11:30", 120)),
        ItineraryItem(type="travel", start="11:30", end="12:00", duration_minutes=30,
                      from_id="p1", to_id="p2", transport_mode="cab"),
    ])
    assert day.total_activity_minutes == 120
    assert day.total_travel_minutes == 30


def test_itinerary_day_numbering_and_dates():
    d1 = DayPlan(day=1, date=date(2026, 12, 10))
    d2 = DayPlan(day=2, date=date(2026, 12, 11))
    assert len(Itinerary(plan_id="x", days=[d1, d2]).days) == 2
    with pytest.raises(ValidationError, match="numbered"):
        Itinerary(plan_id="x", days=[d2, d1])
    with pytest.raises(ValidationError, match="consecutive"):
        Itinerary(plan_id="x", days=[d1, DayPlan(day=2, date=date(2026, 12, 15))])


def test_empty_itinerary_is_representable():
    assert Itinerary(plan_id="x").days == []


# ======================= Budget ===========================================
def test_over_budget_example_from_spec():
    status = BudgetStatus.evaluate(
        Budget(total_inr=30000, travellers=3),
        CostBreakdown(transport=12000, hotel=10000, food=6000, activities=4000, buffer=1500),
    )
    assert status.estimated_total_inr == 33500
    assert status.is_over_budget is True
    assert status.overrun_inr == 3500
    assert status.remaining_inr == -3500
    assert status.per_traveller_inr == pytest.approx(11166.67)


def test_within_budget():
    status = BudgetStatus.evaluate(Budget(total_inr=30000, travellers=3), CostBreakdown(hotel=20000))
    assert status.is_over_budget is False
    assert status.overrun_inr == 0
    assert status.remaining_inr == 10000


def test_breakdown_total_and_negative_rejected():
    assert CostBreakdown(transport=7000, hotel=9000, food=6000, activities=4500,
                         local_transport=1500, buffer=500).total == 28500
    with pytest.raises(ValidationError):
        CostBreakdown(food=-1)


@pytest.mark.parametrize("bad", [0, -5])
def test_budget_must_be_positive(bad):
    with pytest.raises(ValidationError):
        Budget(total_inr=bad, travellers=2)


def test_cost_estimate_defaults_to_unknown_confidence_and_checks_bounds():
    est = CostEstimate(breakdown=CostBreakdown(hotel=1000), method=EstimationMethod.RULE_BASED)
    assert est.confidence.value == "unknown"
    assert est.lower_bound_inr is None and est.typical_error_mae_inr is None
    with pytest.raises(ValidationError, match="upper_bound"):
        CostEstimate(breakdown=CostBreakdown(hotel=1000), method="rule_based", upper_bound_inr=500)
    with pytest.raises(ValidationError, match="lower_bound"):
        CostEstimate(breakdown=CostBreakdown(hotel=1000), method="rule_based", lower_bound_inr=2000)
