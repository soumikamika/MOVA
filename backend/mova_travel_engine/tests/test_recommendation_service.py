import pytest

from app.recommendation.model import ModelMetadata, RecommendationModel, TrainingPurpose
from app.recommendation.service import RecommendationService
from app.schemas.common import ConfidenceLevel
from app.schemas.recommendation import ScoringMethod
from tests.factories import make_place
from tests.factories_recommendation import make_trip


def _service():
    return RecommendationService()


def test_empty_candidates_returns_empty_list():
    assert _service().recommend(make_trip(), []) == []


def test_recommend_returns_one_result_per_candidate_with_rank_and_method():
    places = [make_place(id="a"), make_place(id="b"), make_place(id="c")]
    recs = _service().recommend(make_trip(), places)
    assert {r.place_id for r in recs} == {"a", "b", "c"}
    assert [r.rank for r in recs] == [1, 2, 3]
    assert all(r.method == ScoringMethod.RULE_BASED_FALLBACK and r.model_version is None for r in recs)


def test_ranking_order_matches_score_descending():
    trip = make_trip(interests=["beaches"], dislikes=[])
    places = [make_place(id="no_match", tags=[]), make_place(id="match", tags=["beaches"])]
    recs = _service().recommend(trip, places)
    assert [r.place_id for r in recs] == ["match", "no_match"]
    assert recs[0].score >= recs[1].score


def test_ties_are_broken_by_place_id_for_determinism():
    places = [make_place(id="zzz", tags=[]), make_place(id="aaa", tags=[])]
    recs = _service().recommend(make_trip(interests=[], dislikes=[]), places)
    assert recs[0].score == pytest.approx(recs[1].score)
    assert [r.place_id for r in recs] == ["aaa", "zzz"]


def test_matched_and_conflicting_preferences_populated():
    trip = make_trip(interests=["beaches", "food"], dislikes=["crowds"])
    place = make_place(tags=["beaches", "crowds"])
    rec = _service().recommend(trip, [place])[0]
    assert rec.matched_preferences == ["beaches"] and rec.conflicting_preferences == ["crowds"]
    assert any("beaches" in r for r in rec.reasons)


def test_supporting_factors_and_data_sources_and_reasons_present():
    rec = _service().recommend(make_trip(), [make_place(source="synthetic_dev")])[0]
    assert rec.supporting_factors and isinstance(rec.supporting_factors, list)
    assert rec.data_sources == ["synthetic_dev"]
    assert rec.reasons


def test_score_components_are_present_and_sum_matches_score_for_fallback():
    rec = _service().recommend(make_trip(), [make_place()])[0]
    assert rec.score_components and rec.score == pytest.approx(
        max(0.0, min(1.0, sum(rec.score_components.values())))
    )


def test_synthetic_source_never_becomes_real_in_output():
    rec = _service().recommend(make_trip(), [make_place(source="synthetic_dev")])[0]
    assert rec.data_sources == ["synthetic_dev"]
    assert "real" not in rec.data_sources


def test_confidence_is_low_when_little_is_known_and_medium_when_more_is_known():
    sparse = _service().recommend(
        make_trip(interests=[]), [make_place(rating=None, popularity=None, entry_fee_inr=None)]
    )[0]
    rich = _service().recommend(
        make_trip(interests=["beaches"]), [make_place(rating=4.5, popularity=0.8, entry_fee_inr=100)]
    )[0]
    assert sparse.confidence == ConfidenceLevel.LOW
    assert rich.confidence == ConfidenceLevel.MEDIUM


def test_malformed_input_raises_instead_of_silently_scoring():
    with pytest.raises(Exception):
        _service().recommend(make_trip(), ["not-a-place"])


# ------------------------------ model integration -----------------------------
def _fake_model(purpose: TrainingPurpose, predict_value: float = 0.75) -> RecommendationModel:
    class _Sk:
        def predict(self, x):
            import numpy as np
            return np.full(len(x), predict_value)

    from app.recommendation.features import FEATURE_NAMES
    meta = ModelMetadata(
        purpose=purpose, trained_at="2026-01-01T00:00:00+00:00", n_examples=25,
        source_counts={"synthetic_dev": 25}, used_feature_names=list(FEATURE_NAMES),
        metrics={"mae": 0.1}, sklearn_version="x", model_class="_Sk", seed=1,
        notes=["test model"],
    )
    return RecommendationModel(_Sk(), meta)


def test_production_model_is_used_for_scoring():
    model = _fake_model(TrainingPurpose.PRODUCTION, predict_value=0.9)
    service = RecommendationService(model=model)
    rec = service.recommend(make_trip(), [make_place()])[0]
    assert rec.method == ScoringMethod.ML_MODEL
    assert rec.score == pytest.approx(0.9)
    assert rec.model_version == "_Sk"
    status = service.engine_status()
    assert status.model_loaded and status.model_is_production and status.scoring_method == ScoringMethod.ML_MODEL


def test_pipeline_test_model_is_never_used_for_scoring():
    model = _fake_model(TrainingPurpose.PIPELINE_TEST, predict_value=0.9)
    service = RecommendationService(model=model)
    rec = service.recommend(make_trip(), [make_place()])[0]
    assert rec.method == ScoringMethod.RULE_BASED_FALLBACK   # NOT the pipeline-test model's 0.9
    assert rec.score != pytest.approx(0.9)
    status = service.engine_status()
    assert status.model_loaded and not status.model_is_production
    assert status.scoring_method == ScoringMethod.RULE_BASED_FALLBACK
    assert status.model_notes == ["test model"]


def test_no_model_uses_fallback_and_status_reflects_it():
    status = RecommendationService().engine_status()
    assert not status.model_loaded and not status.model_is_production
    assert status.scoring_method == ScoringMethod.RULE_BASED_FALLBACK
