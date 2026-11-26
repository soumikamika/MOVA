"""Deterministic feature extraction: (TripRequest, Place) -> facts + a numeric vector.

Two outputs, built together so they can never drift apart:
  * PlaceFacts  - structured, human-checkable facts used by explain.py. Every
                  field here is either a direct schema value or a simple,
                  documented derivation. Nothing here is invented.
  * vector      - a flat dict[str, float] for the ML model. Unknown attributes
                  (Place.rating is None, etc.) become float('nan'), NEVER 0 or
                  an average. HistGradientBoostingRegressor (Phase C's model)
                  handles NaN natively, so no imputation is needed or performed.

FEATURE_NAMES is the single source of truth for vector width/order; model.py
stores it with every saved model and refuses to load a model trained against a
different feature schema (see ModelLoadError).
"""
import math
from dataclasses import dataclass
from enum import StrEnum

from app.schemas.common import MovaModel, PlaceCategory, TripType
from app.schemas.place import Place
from app.schemas.trip import TripRequest

NAN = math.nan

# Rough bucket centres on the same 1..5 scale as Place.intensity. This is a
# simplifying heuristic (not derived from data) so activity level and place
# intensity can be compared; it is documented here rather than left implicit.
ACTIVITY_LEVEL_CENTRE = {"relaxed": 1.5, "moderate": 3.0, "intense": 4.5}


class SeasonStatus(StrEnum):
    BEST = "best"       # trip month(s) overlap the place's stated best_months
    CLOSED = "closed"   # trip month(s) overlap the place's stated closed_months
    NEUTRAL = "neutral"  # neither is known/overlapping


class FamilyCompatibility(StrEnum):
    MATCH = "match"      # trip_type is family AND place.family_friendly is True
    CONFLICT = "conflict"  # trip_type is family AND place.family_friendly is False
    UNKNOWN = "unknown"  # not a family trip, or family_friendly is unknown


class PlaceFacts(MovaModel):
    """Structured, explainable facts about one (trip, place) pairing."""

    place_id: str
    category: PlaceCategory
    trip_type: TripType

    interest_matches: list[str] = []      # trip.interests that are also in place.tags
    dislike_conflicts: list[str] = []     # trip.dislikes that are also in place.tags
    unmatched_interests: list[str] = []   # trip.interests NOT found on this place

    rating: float | None
    popularity: float | None
    entry_fee_inr: float | None
    fee_share_of_budget_per_traveller: float | None  # entry_fee / (budget / travellers); None if fee unknown

    intensity: int
    avg_visit_minutes: int
    activity_level_diff: float  # |ACTIVITY_LEVEL_CENTRE[trip] - place.intensity|, always known

    family_compatibility: FamilyCompatibility
    season_status: SeasonStatus


@dataclass(frozen=True)
class FeatureResult:
    facts: PlaceFacts
    vector: dict[str, float]


_CONTINUOUS_FEATURES = (
    "rating", "popularity", "crowd_level", "avg_visit_minutes", "entry_fee_inr",
    "intensity", "travellers", "trip_duration_days", "budget_per_traveller_inr",
    "interest_match_count", "interest_match_ratio", "dislike_conflict_count",
    "fee_share_of_budget_per_traveller", "activity_level_diff", "family_match", "season_match",
)
_CATEGORY_FEATURES = tuple(f"category_{c.value}" for c in PlaceCategory)
_TRIP_TYPE_FEATURES = tuple(f"trip_type_{t.value}" for t in TripType)

FEATURE_NAMES: tuple[str, ...] = _CONTINUOUS_FEATURES + _CATEGORY_FEATURES + _TRIP_TYPE_FEATURES


def vectorize(vector: dict[str, float]) -> list[float]:
    """Project a feature dict onto the canonical FEATURE_NAMES order.

    Raises KeyError if `vector` is missing a name - extract_features() always
    produces every name, so a KeyError here means an extraction bug, not
    missing data (missing DATA is represented by NaN, already inside `vector`).
    """
    return [vector[name] for name in FEATURE_NAMES]


def _season_status(trip: TripRequest, place: Place) -> SeasonStatus:
    trip_months = {d.month for d in trip.dates}
    if place.closed_months and trip_months & set(place.closed_months):
        return SeasonStatus.CLOSED
    if place.best_months and trip_months & set(place.best_months):
        return SeasonStatus.BEST
    return SeasonStatus.NEUTRAL


def _family_compatibility(trip: TripRequest, place: Place) -> FamilyCompatibility:
    if trip.trip_type != TripType.FAMILY:
        return FamilyCompatibility.UNKNOWN
    if place.family_friendly is True:
        return FamilyCompatibility.MATCH
    if place.family_friendly is False:
        return FamilyCompatibility.CONFLICT
    return FamilyCompatibility.UNKNOWN


def extract_features(trip: TripRequest, place: Place) -> FeatureResult:
    interests, dislikes, tags = set(trip.interests), set(trip.dislikes), set(place.tags)
    interest_matches = sorted(interests & tags)
    dislike_conflicts = sorted(dislikes & tags)
    unmatched_interests = sorted(interests - tags)

    budget_per_traveller = trip.budget / trip.travellers  # always safe: both are strictly positive
    fee_share = (place.entry_fee_inr / budget_per_traveller) if place.entry_fee_inr is not None else None
    activity_diff = abs(ACTIVITY_LEVEL_CENTRE[trip.activity_level.value] - place.intensity)
    family = _family_compatibility(trip, place)
    season = _season_status(trip, place)

    facts = PlaceFacts(
        place_id=place.id, category=place.category, trip_type=trip.trip_type,
        interest_matches=interest_matches, dislike_conflicts=dislike_conflicts,
        unmatched_interests=unmatched_interests, rating=place.rating, popularity=place.popularity,
        entry_fee_inr=place.entry_fee_inr, fee_share_of_budget_per_traveller=fee_share,
        intensity=place.intensity, avg_visit_minutes=place.avg_visit_minutes,
        activity_level_diff=activity_diff, family_compatibility=family, season_status=season,
    )

    vector: dict[str, float] = {
        "rating": place.rating if place.rating is not None else NAN,
        "popularity": place.popularity if place.popularity is not None else NAN,
        "crowd_level": place.crowd_level if place.crowd_level is not None else NAN,
        "avg_visit_minutes": float(place.avg_visit_minutes),
        "entry_fee_inr": place.entry_fee_inr if place.entry_fee_inr is not None else NAN,
        "intensity": float(place.intensity),
        "travellers": float(trip.travellers),
        "trip_duration_days": float(trip.num_days),
        "budget_per_traveller_inr": float(budget_per_traveller),
        "interest_match_count": float(len(interest_matches)),
        "interest_match_ratio": (len(interest_matches) / len(interests)) if interests else NAN,
        "dislike_conflict_count": float(len(dislike_conflicts)),
        "fee_share_of_budget_per_traveller": fee_share if fee_share is not None else NAN,
        "activity_level_diff": activity_diff,
        "family_match": {"match": 1.0, "conflict": -1.0, "unknown": NAN}[family.value],
        "season_match": {"best": 1.0, "closed": -1.0, "neutral": 0.0}[season.value],
    }
    for c in PlaceCategory:
        vector[f"category_{c.value}"] = 1.0 if place.category == c else 0.0
    for t in TripType:
        vector[f"trip_type_{t.value}"] = 1.0 if trip.trip_type == t else 0.0

    return FeatureResult(facts=facts, vector=vector)
