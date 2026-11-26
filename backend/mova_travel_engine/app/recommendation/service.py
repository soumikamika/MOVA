"""recommend(trip, candidates) -> ranked Recommendation list.

Deliberately independent of any repository: it takes a list[Place] the caller
already fetched, so JSON-backed repositories can be swapped for PostgreSQL (or
anything else) without touching this module. A future FastAPI layer calls:

    places = repos.places.list_by_destination(destination_id, some_filter)
    recs = RecommendationService().recommend(trip_request, places)

Scoring method choice:
  * A loaded model is only used when its metadata says purpose=PRODUCTION.
  * Until real interaction data exists (see trainer.py), no production model
    can be trained, so the service ALWAYS uses the deterministic fallback
    today. That is by design, not a placeholder bug.
  * A loaded pipeline_test model is visible via engine_status() for debugging
    but is never used to produce recommendations - presenting its output as a
    real recommendation would misrepresent synthetic-data pipeline-test
    results as travel intelligence.
"""
from dataclasses import dataclass

from app.recommendation.explain import build_reasons, build_supporting_factors
from app.recommendation.fallback import score_place
from app.recommendation.features import extract_features
from app.recommendation.model import RecommendationModel
from app.schemas.common import ConfidenceLevel
from app.schemas.place import Place
from app.schemas.recommendation import Recommendation, ScoringMethod
from app.schemas.trip import TripRequest


def _completeness_confidence(known_count: int, has_interests: bool) -> ConfidenceLevel:
    """Confidence reflects how much relevant data we actually have, NOT model
    accuracy (which is unvalidated) or a fabricated probability calibration.
    known_count = how many of {rating, popularity, entry_fee} are known.
    """
    if known_count >= 2 and has_interests:
        return ConfidenceLevel.MEDIUM
    if known_count >= 1 or has_interests:
        return ConfidenceLevel.LOW
    return ConfidenceLevel.LOW


@dataclass
class EngineStatus:
    scoring_method: ScoringMethod
    model_loaded: bool
    model_is_production: bool
    model_notes: list[str]


class RecommendationService:
    def __init__(self, model: RecommendationModel | None = None):
        self._model = model

    @property
    def model(self) -> RecommendationModel | None:
        return self._model

    def engine_status(self) -> EngineStatus:
        using_model = self._model is not None and self._model.metadata.is_production
        return EngineStatus(
            scoring_method=ScoringMethod.ML_MODEL if using_model else ScoringMethod.RULE_BASED_FALLBACK,
            model_loaded=self._model is not None,
            model_is_production=bool(self._model and self._model.metadata.is_production),
            model_notes=list(self._model.metadata.notes) if self._model else [],
        )

    def recommend(self, trip: TripRequest, candidates: list[Place]) -> list[Recommendation]:
        if not candidates:
            return []

        use_model = self._model is not None and self._model.metadata.is_production
        results = [extract_features(trip, p) for p in candidates]

        if use_model:
            scores = self._model.predict_many([fr.vector for fr in results])
            components_list = [{"model_score": s} for s in scores]
            method, model_version = ScoringMethod.ML_MODEL, self._model.metadata.model_class
        else:
            fallback = [score_place(fr.facts) for fr in results]
            scores = [f.score for f in fallback]
            components_list = [f.components for f in fallback]
            method, model_version = ScoringMethod.RULE_BASED_FALLBACK, None

        recs: list[Recommendation] = []
        for place, fr, score, components in zip(candidates, results, scores, components_list):
            facts = fr.facts
            known = sum(x is not None for x in (facts.rating, facts.popularity, facts.entry_fee_inr))
            recs.append(Recommendation(
                place_id=place.id, score=score, reasons=build_reasons(facts),
                score_components=components, method=method, model_version=model_version,
                matched_preferences=facts.interest_matches, conflicting_preferences=facts.dislike_conflicts,
                supporting_factors=build_supporting_factors(facts), data_sources=[place.source],
                confidence=_completeness_confidence(known, bool(trip.interests)),
            ))

        recs.sort(key=lambda r: (-r.score, r.place_id))
        for i, r in enumerate(recs, start=1):
            r.rank = i
        return recs
