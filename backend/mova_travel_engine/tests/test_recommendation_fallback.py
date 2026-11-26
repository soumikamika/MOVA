import pytest

from app.recommendation.fallback import WEIGHTS, score_place
from app.recommendation.features import extract_features
from tests.factories import make_place
from tests.factories_recommendation import make_trip


def _score(trip=None, place=None):
    return score_place(extract_features(trip or make_trip(), place or make_place()).facts)


def test_score_is_bounded_and_components_sum_to_it():
    r = _score()
    assert 0.0 <= r.score <= 1.0
    assert r.score == pytest.approx(max(0.0, min(1.0, sum(r.components.values()))))


def test_baseline_component_is_the_named_constant():
    assert _score().components["baseline"] == WEIGHTS["baseline"]


def test_more_interest_matches_increase_score_monotonically():
    trip = make_trip(interests=["beaches", "food", "nature"], dislikes=[])
    s0 = _score(trip, make_place(tags=[])).score
    s1 = _score(trip, make_place(tags=["beaches"])).score
    s2 = _score(trip, make_place(tags=["beaches", "food"])).score
    s3 = _score(trip, make_place(tags=["beaches", "food", "nature"])).score
    assert s0 < s1 < s2 < s3


def test_interest_match_contribution_is_capped():
    trip = make_trip(interests=["a", "b", "c", "d", "e", "f"], dislikes=[])
    place = make_place(tags=["a", "b", "c", "d", "e", "f"])
    r = _score(trip, place)
    assert r.components["interest_match"] == pytest.approx(WEIGHTS["interest_match_cap"])


def test_dislike_conflicts_decrease_score_and_are_capped():
    trip = make_trip(interests=[], dislikes=["a", "b", "c", "d"])
    r = _score(trip, make_place(tags=["a", "b", "c", "d"]))
    assert r.components["dislike_conflict"] == pytest.approx(WEIGHTS["dislike_conflict_cap"])
    clean = _score(trip, make_place(tags=[]))
    assert r.score < clean.score


def test_conflicting_and_matching_tags_can_coexist_and_partly_cancel():
    trip = make_trip(interests=["nature"], dislikes=["crowds"])
    r = _score(trip, make_place(tags=["nature", "crowds"]))
    assert r.components["interest_match"] > 0 and r.components["dislike_conflict"] < 0


# ------------------------------ rating / popularity --------------------------
def test_high_rating_increases_score_low_rating_decreases_it():
    high = _score(place=make_place(rating=5.0))
    low = _score(place=make_place(rating=1.0))
    unknown = _score(place=make_place(rating=None))
    assert high.score > unknown.score > low.score
    assert unknown.components["rating"] == 0.0     # unknown must be neutral, not guessed


def test_popularity_effect_and_unknown_is_neutral():
    assert _score(place=make_place(popularity=0.9)).score > _score(place=make_place(popularity=0.1)).score
    assert _score(place=make_place(popularity=None)).components["popularity"] == 0.0


# ------------------------------ family / trip type ----------------------------
def test_family_match_and_conflict():
    trip = make_trip(trip_type="family", travellers=4)
    match = _score(trip, make_place(family_friendly=True))
    conflict = _score(trip, make_place(family_friendly=False))
    unknown = _score(trip, make_place(family_friendly=None))
    assert match.components["family"] == WEIGHTS["family_match"]
    assert conflict.components["family"] == WEIGHTS["family_conflict"]
    assert unknown.components["family"] == 0.0
    assert match.score > unknown.score > conflict.score


def test_family_field_is_neutral_for_non_family_trips():
    trip = make_trip(trip_type="solo", travellers=1)
    assert _score(trip, make_place(family_friendly=False)).components["family"] == 0.0


# ------------------------------ budget / fee ----------------------------------
def test_budget_compatibility_cheap_place_gets_bargain_bonus():
    trip = make_trip(budget=30000, travellers=3)   # 10,000/traveller
    cheap = _score(trip, make_place(entry_fee_inr=500))     # 5% share
    mid = _score(trip, make_place(entry_fee_inr=5000))      # 50% share
    over = _score(trip, make_place(entry_fee_inr=25000))    # 250% share
    assert cheap.components["fee"] == WEIGHTS["fee_bargain_bonus"]
    assert mid.components["fee"] == 0.0
    assert over.components["fee"] < 0
    assert cheap.score > mid.score > over.score


def test_unknown_fee_does_not_affect_score():
    assert _score(place=make_place(entry_fee_inr=None)).components["fee"] == 0.0


# ------------------------------ activity level --------------------------------
def test_activity_mismatch_penalised_and_capped():
    trip = make_trip(activity_level="relaxed")
    close = _score(trip, make_place(intensity=2))
    far = _score(trip, make_place(intensity=5))
    assert close.score > far.score
    assert far.components["activity_mismatch"] == pytest.approx(WEIGHTS["activity_mismatch_cap"])


# ------------------------------ determinism / no missing data invented -------
def test_deterministic_for_same_input():
    trip, place = make_trip(), make_place()
    a = score_place(extract_features(trip, place).facts)
    b = score_place(extract_features(trip, place).facts)
    assert a.score == b.score and a.components == b.components


def test_all_unknowns_still_produces_a_valid_neutral_score():
    place = make_place(rating=None, popularity=None, entry_fee_inr=None, family_friendly=None,
                       best_months=[], closed_months=[])
    trip = make_trip(interests=[], dislikes=[])
    r = _score(trip, place)
    assert 0.0 <= r.score <= 1.0
    assert r.components["rating"] == r.components["popularity"] == r.components["fee"] == r.components["family"] == 0.0
