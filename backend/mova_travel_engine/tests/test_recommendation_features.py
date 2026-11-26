import datetime as dt
import math

import pytest

from app.recommendation.features import (
    FEATURE_NAMES, FamilyCompatibility, SeasonStatus, extract_features, vectorize,
)
from tests.factories import make_place
from tests.factories_recommendation import make_trip


def test_feature_names_has_no_duplicates_and_is_stable_order():
    assert len(FEATURE_NAMES) == len(set(FEATURE_NAMES))
    assert FEATURE_NAMES[0] == "rating"
    assert any(n.startswith("category_") for n in FEATURE_NAMES)
    assert any(n.startswith("trip_type_") for n in FEATURE_NAMES)


def test_vector_covers_every_feature_name():
    fr = extract_features(make_trip(), make_place())
    assert set(fr.vector) == set(FEATURE_NAMES)
    assert vectorize(fr.vector) == [fr.vector[n] for n in FEATURE_NAMES]


# ------------------------------ interest matching --------------------------
def test_interest_match_and_unmatched():
    trip = make_trip(interests=["beaches", "food"], dislikes=[])
    place = make_place(tags=["beaches", "water_sports"])
    facts = extract_features(trip, place).facts
    assert facts.interest_matches == ["beaches"]
    assert facts.unmatched_interests == ["food"]
    assert extract_features(trip, place).vector["interest_match_count"] == 1.0
    assert extract_features(trip, place).vector["interest_match_ratio"] == pytest.approx(0.5)


def test_no_interests_gives_zero_matches_and_unknown_ratio():
    trip = make_trip(interests=[], dislikes=[])
    facts = extract_features(trip, make_place(tags=["beaches"])).facts
    assert facts.interest_matches == []
    vec = extract_features(trip, make_place(tags=["beaches"])).vector
    assert vec["interest_match_count"] == 0.0
    assert math.isnan(vec["interest_match_ratio"])       # "no stated interests" is genuinely unknown, not 0


def test_dislike_conflict_detection():
    trip = make_trip(interests=[], dislikes=["clubs", "crowds"])
    facts = extract_features(trip, make_place(tags=["clubs", "beaches"])).facts
    assert facts.dislike_conflicts == ["clubs"]
    assert extract_features(trip, make_place(tags=["clubs"])).vector["dislike_conflict_count"] == 1.0


def test_no_conflicts_when_tags_disjoint():
    trip = make_trip(interests=["nature"], dislikes=["clubs"])
    facts = extract_features(trip, make_place(tags=["beaches"])).facts
    assert facts.interest_matches == [] and facts.dislike_conflicts == []


# ------------------------------ budget / fee --------------------------------
def test_budget_per_traveller_and_fee_share():
    trip = make_trip(budget=30000, travellers=3)   # 10,000 / traveller
    place = make_place(entry_fee_inr=2000)
    vec = extract_features(trip, place).vector
    assert vec["budget_per_traveller_inr"] == pytest.approx(10000.0)
    assert vec["fee_share_of_budget_per_traveller"] == pytest.approx(0.2)
    facts = extract_features(trip, place).facts
    assert facts.fee_share_of_budget_per_traveller == pytest.approx(0.2)


def test_unknown_fee_is_nan_not_zero():
    vec = extract_features(make_trip(), make_place(entry_fee_inr=None)).vector
    assert math.isnan(vec["fee_share_of_budget_per_traveller"])
    assert math.isnan(vec["entry_fee_inr"])
    assert extract_features(make_trip(), make_place(entry_fee_inr=None)).facts.entry_fee_inr is None


def test_free_entry_is_zero_not_unknown():
    vec = extract_features(make_trip(), make_place(entry_fee_inr=0)).vector
    assert vec["entry_fee_inr"] == 0.0 and vec["fee_share_of_budget_per_traveller"] == 0.0


# ------------------------------ unknown rating/popularity -------------------
def test_unknown_optional_numeric_fields_become_nan():
    vec = extract_features(make_trip(), make_place(rating=None, popularity=None, crowd_level=None)).vector
    assert math.isnan(vec["rating"]) and math.isnan(vec["popularity"]) and math.isnan(vec["crowd_level"])


def test_known_optional_numeric_fields_pass_through():
    vec = extract_features(make_trip(), make_place(rating=4.2, popularity=0.7, crowd_level=0.3)).vector
    assert vec["rating"] == 4.2 and vec["popularity"] == 0.7 and vec["crowd_level"] == 0.3


# ------------------------------ trip type / family --------------------------
@pytest.mark.parametrize("family_friendly,expected", [(True, "match"), (False, "conflict"), (None, "unknown")])
def test_family_trip_compatibility(family_friendly, expected):
    facts = extract_features(make_trip(trip_type="family", travellers=4),
                             make_place(family_friendly=family_friendly)).facts
    assert facts.family_compatibility.value == expected


def test_non_family_trip_is_always_unknown_compatibility():
    for ff in (True, False, None):
        facts = extract_features(make_trip(trip_type="solo", travellers=1), make_place(family_friendly=ff)).facts
        assert facts.family_compatibility == FamilyCompatibility.UNKNOWN


def test_family_match_vector_encoding():
    v_match = extract_features(make_trip(trip_type="family", travellers=4), make_place(family_friendly=True)).vector
    v_conflict = extract_features(make_trip(trip_type="family", travellers=4), make_place(family_friendly=False)).vector
    v_unknown = extract_features(make_trip(trip_type="solo", travellers=1), make_place(family_friendly=None)).vector
    assert v_match["family_match"] == 1.0 and v_conflict["family_match"] == -1.0
    assert math.isnan(v_unknown["family_match"])


# ------------------------------ activity level -------------------------------
@pytest.mark.parametrize("level,intensity,expected", [
    ("relaxed", 2, 0.5), ("moderate", 3, 0.0), ("intense", 5, 0.5), ("relaxed", 5, 3.5),
])
def test_activity_level_diff(level, intensity, expected):
    facts = extract_features(make_trip(activity_level=level), make_place(intensity=intensity)).facts
    assert facts.activity_level_diff == pytest.approx(expected)


# ------------------------------ season ---------------------------------------
def test_season_best_when_trip_month_in_best_months():
    trip = make_trip(start_date=dt.date(2027, 1, 10), end_date=dt.date(2027, 1, 12))
    facts = extract_features(trip, make_place(best_months=[1, 2], closed_months=[])).facts
    assert facts.season_status == SeasonStatus.BEST


def test_season_closed_when_trip_month_in_closed_months():
    trip = make_trip(start_date=dt.date(2027, 7, 10), end_date=dt.date(2027, 7, 12))
    facts = extract_features(trip, make_place(closed_months=[6, 7, 8], best_months=[])).facts
    assert facts.season_status == SeasonStatus.CLOSED


def test_season_closed_takes_priority_over_best_if_somehow_both_listed():
    trip = make_trip(start_date=dt.date(2027, 7, 10), end_date=dt.date(2027, 7, 12))
    facts = extract_features(trip, make_place(closed_months=[7], best_months=[7])).facts
    assert facts.season_status == SeasonStatus.CLOSED


def test_season_neutral_when_nothing_known_or_no_overlap():
    facts = extract_features(make_trip(), make_place(best_months=[], closed_months=[])).facts
    assert facts.season_status == SeasonStatus.NEUTRAL
    trip = make_trip(start_date=dt.date(2027, 5, 10), end_date=dt.date(2027, 5, 12))
    facts2 = extract_features(trip, make_place(best_months=[12, 1], closed_months=[6])).facts
    assert facts2.season_status == SeasonStatus.NEUTRAL


def test_trip_spanning_multiple_months_checks_all_of_them():
    trip = make_trip(start_date=dt.date(2027, 1, 30), end_date=dt.date(2027, 2, 2))
    facts = extract_features(trip, make_place(best_months=[2], closed_months=[])).facts
    assert facts.season_status == SeasonStatus.BEST


# ------------------------------ malformed / edge inputs ----------------------
def test_extraction_is_deterministic():
    trip, place = make_trip(), make_place()
    a, b = extract_features(trip, place), extract_features(trip, place)
    assert a.vector == b.vector and a.facts == b.facts


def test_category_and_trip_type_one_hot_are_mutually_exclusive():
    vec = extract_features(make_trip(trip_type="couple"), make_place(category="museum")).vector
    cat_on = [n for n in FEATURE_NAMES if n.startswith("category_") and vec[n] == 1.0]
    tt_on = [n for n in FEATURE_NAMES if n.startswith("trip_type_") and vec[n] == 1.0]
    assert cat_on == ["category_museum"] and tt_on == ["trip_type_couple"]
