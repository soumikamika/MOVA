"""Covers app/travel_cost/{features,baseline,model,trainer,service}.py."""
import math
import random

import pytest

from app.core.exceptions import InsufficientTrainingDataError, ModelLoadError
from app.ml.training_rules import MIN_PRODUCTION_EXAMPLES, TrainingPurpose
from app.schemas.common import DataSource
from app.schemas.logistics import CostRequest
from app.schemas.prediction import PredictionMethod
from app.travel_cost.baseline import estimate as baseline_estimate
from app.travel_cost.features import FEATURE_NAMES, extract_features
from app.travel_cost.model import TravelCostModel
from app.travel_cost.service import TravelCostService
from app.travel_cost.trainer import (
    LabelOrigin, MIN_PIPELINE_TEST_EXAMPLES, build_pipeline_test_examples_from_baseline,
    evaluate, make_training_example, train,
)


def _req(**kw):
    base = dict(category="accommodation", travellers=3)
    base.update(kw)
    return CostRequest(**base)


# ------------------------------ features --------------------------------------
def test_feature_names_cover_all_categories_and_exclude_total_known_price():
    assert len(FEATURE_NAMES) == len(set(FEATURE_NAMES))
    assert any(n.startswith("category_") for n in FEATURE_NAMES)
    assert "total_known_price_inr" not in FEATURE_NAMES   # would leak the label - see features.py docstring


def test_vector_covers_every_feature_name():
    fr = extract_features(_req(quantity=3, unit_price_inr=2000))
    assert set(fr.vector) == set(FEATURE_NAMES)


def test_unknown_quantity_and_price_become_nan():
    fr = extract_features(_req())
    assert math.isnan(fr.vector["quantity"]) and math.isnan(fr.vector["unit_price_inr"])
    assert fr.facts.quantity is None and fr.facts.unit_price_inr is None


def test_travellers_is_always_known():
    fr = extract_features(_req(travellers=5))
    assert fr.vector["travellers"] == 5.0


def test_category_one_hot_is_exclusive():
    fr = extract_features(_req(category="food"))
    on = [n for n in FEATURE_NAMES if n.startswith("category_") and fr.vector[n] == 1.0]
    assert on == ["category_food"]


def test_malformed_request_rejected_by_schema():
    from pydantic import ValidationError
    with pytest.raises(ValidationError):
        _req(travellers=0)
    with pytest.raises(ValidationError):
        _req(quantity=-1)


# ------------------------------ baseline ---------------------------------------
def test_known_price_times_quantity_calculation():
    p = baseline_estimate(_req(quantity=4, unit_price_inr=3000))
    assert p.value == pytest.approx(12000.0)
    assert p.method == PredictionMethod.BASELINE and p.is_estimated and not p.is_unknown


def test_distance_times_per_distance_cost_example():
    p = baseline_estimate(_req(category="transport", quantity=350.0, unit_price_inr=12.5))
    assert p.value == pytest.approx(350.0 * 12.5)


def test_missing_price_returns_unknown():
    p = baseline_estimate(_req(quantity=4))
    assert p.is_unknown and p.value is None
    assert "unit_price_inr" in p.notes[0]


def test_missing_quantity_returns_unknown():
    p = baseline_estimate(_req(unit_price_inr=3000))
    assert p.is_unknown and p.value is None
    assert "quantity" in p.notes[0]


def test_missing_both_returns_unknown_listing_both():
    p = baseline_estimate(_req())
    assert p.is_unknown
    assert "quantity" in p.notes[0] and "unit_price_inr" in p.notes[0]


def test_observed_total_price_is_used_directly_not_recomputed():
    p = baseline_estimate(_req(quantity=4, unit_price_inr=3000, total_known_price_inr=9999))
    assert p.value == 9999   # observed wins over the quantity*unit_price calculation
    assert p.method == PredictionMethod.OBSERVED and p.is_estimated is False
    assert p.confidence.value == "high"


def test_multiple_cost_categories_all_work():
    for cat in ("transport", "accommodation", "food", "activities", "local_transport", "miscellaneous"):
        p = baseline_estimate(_req(category=cat, quantity=2, unit_price_inr=500))
        assert p.value == pytest.approx(1000.0)
        assert p.prediction_type == f"cost_{cat}_inr"


def test_predictions_are_non_negative():
    p = baseline_estimate(_req(quantity=0, unit_price_inr=500))
    assert p.value == 0.0    # zero is a real, valid cost - not "unknown"
    assert not p.is_unknown


def test_baseline_confidence_is_low_and_never_claims_accuracy():
    p = baseline_estimate(_req(quantity=2, unit_price_inr=500))
    assert p.confidence.value == "low"
    assert any("not validated" in n for n in p.notes)


# ------------------------------ prediction schema invariants --------------------
def test_prediction_metadata_fields_present():
    p = baseline_estimate(_req(quantity=2, unit_price_inr=500))
    assert p.unit == "inr" and p.method == PredictionMethod.BASELINE
    assert p.is_estimated is True and p.is_unknown is False and p.confidence is not None


# ------------------------------ training ----------------------------------------
def _requests(n, seed=0, cats=("accommodation", "food", "transport", "activities")):
    rng = random.Random(seed)
    return [_req(category=rng.choice(cats), travellers=rng.randint(1, 6),
                quantity=rng.uniform(1, 10), unit_price_inr=rng.uniform(100, 5000))
           for _ in range(n)]


def _examples(n=40, seed=0):
    reqs = _requests(n, seed)
    frs = [extract_features(r) for r in reqs]
    return build_pipeline_test_examples_from_baseline(frs, reqs)


def test_pipeline_test_examples_forced_synthetic():
    ex = _examples(30)
    assert all(e.source == DataSource.SYNTHETIC_DEV for e in ex)
    assert all(e.label_origin == LabelOrigin.BASELINE_HEURISTIC for e in ex)
    assert all(e.label >= 0 for e in ex)


def test_examples_skip_requests_with_unknown_or_observed_price():
    reqs = [_req(quantity=None, unit_price_inr=None), _req(quantity=2, unit_price_inr=100),
           _req(total_known_price_inr=500)]
    frs = [extract_features(r) for r in reqs]
    ex = build_pipeline_test_examples_from_baseline(frs, reqs)
    assert len(ex) == 1
    assert ex[0].label == pytest.approx(200.0)


def test_make_training_example_preserves_given_source():
    fr = extract_features(_req(quantity=2, unit_price_inr=500))
    ex = make_training_example(fr, label=1000.0, source=DataSource.REAL, label_origin=LabelOrigin.OBSERVED_PRICE)
    assert ex.source == DataSource.REAL and ex.label == 1000.0


def test_empty_examples_rejected():
    with pytest.raises(InsufficientTrainingDataError):
        train([], purpose=TrainingPurpose.PIPELINE_TEST)


def test_too_few_pipeline_test_examples_rejected():
    with pytest.raises(InsufficientTrainingDataError, match=str(MIN_PIPELINE_TEST_EXAMPLES)):
        train(_examples(MIN_PIPELINE_TEST_EXAMPLES - 1), purpose=TrainingPurpose.PIPELINE_TEST)


def test_production_training_refused_with_only_synthetic_data():
    with pytest.raises(InsufficientTrainingDataError, match="Insufficient real training data"):
        train(_examples(600), purpose=TrainingPurpose.PRODUCTION)


def test_production_training_refused_below_threshold_even_with_real_examples():
    fr = extract_features(_req(quantity=2, unit_price_inr=500))
    real_examples = [make_training_example(fr, label=1000.0, source=DataSource.REAL,
                                           label_origin=LabelOrigin.OBSERVED_PRICE)
                     for _ in range(MIN_PRODUCTION_EXAMPLES - 1)]
    with pytest.raises(InsufficientTrainingDataError):
        train(real_examples, purpose=TrainingPurpose.PRODUCTION)


def test_production_training_succeeds_with_enough_real_examples():
    rng = random.Random(1)
    reqs = _requests(MIN_PRODUCTION_EXAMPLES + 20, seed=1)
    examples = []
    for r in reqs:
        fr = extract_features(r)
        label = max(0.0, r.quantity * r.unit_price_inr + rng.uniform(-50, 50))
        examples.append(make_training_example(fr, label=label, source=DataSource.REAL,
                                               label_origin=LabelOrigin.OBSERVED_PRICE))
    model = train(examples, purpose=TrainingPurpose.PRODUCTION, seed=3)
    assert model.metadata.is_production
    assert model.metadata.real_example_count == len(examples)


def test_pipeline_test_model_labelled_non_production():
    model = train(_examples(60), purpose=TrainingPurpose.PIPELINE_TEST, seed=1)
    assert not model.metadata.is_production
    assert any("PIPELINE-TEST" in n for n in model.metadata.notes)
    assert model.metadata.source_counts == {"synthetic_dev": 60}


def test_constant_columns_are_dropped_not_crashed():
    """Every example shares one category and one traveller count -> constant columns."""
    reqs = [_req(category="food", travellers=2, quantity=q, unit_price_inr=300) for q in range(20, 40)]
    frs = [extract_features(r) for r in reqs]
    examples = build_pipeline_test_examples_from_baseline(frs, reqs)
    model = train(examples, purpose=TrainingPurpose.PIPELINE_TEST, seed=1)
    assert "quantity" in model.metadata.used_feature_names
    assert model.metadata.dropped_feature_names   # travellers, unit_price_inr, most category_* one-hots


def test_all_constant_features_raise_clear_error():
    fr = extract_features(_req(quantity=2, unit_price_inr=500))
    examples = build_pipeline_test_examples_from_baseline(
        [fr] * (MIN_PIPELINE_TEST_EXAMPLES + 5), [_req(quantity=2, unit_price_inr=500)] * (MIN_PIPELINE_TEST_EXAMPLES + 5)
    )
    with pytest.raises(InsufficientTrainingDataError, match="constant"):
        train(examples, purpose=TrainingPurpose.PIPELINE_TEST)


def test_all_nan_column_is_dropped():
    """quantity/unit_price known for every example but travellers constant and
    total_known_price_inr excluded entirely (never a feature) -> no crash."""
    model = train(_examples(40), purpose=TrainingPurpose.PIPELINE_TEST, seed=2)
    assert set(model.metadata.used_feature_names) <= set(FEATURE_NAMES)


def test_predictions_are_non_negative_and_unbounded_above():
    model = train(_examples(80), purpose=TrainingPurpose.PIPELINE_TEST, seed=2)
    for r in _requests(5, seed=9):
        pred = model.predict_one(extract_features(r).vector)
        assert pred >= 0.0 and not math.isnan(pred)


def test_predict_many_matches_predict_one_and_handles_empty():
    model = train(_examples(50), purpose=TrainingPurpose.PIPELINE_TEST)
    vectors = [extract_features(r).vector for r in _requests(3, seed=4)]
    assert model.predict_many(vectors) == [model.predict_one(v) for v in vectors]
    assert model.predict_many([]) == []


def test_evaluate_and_empty_rejection():
    examples = _examples(50)
    model = train(examples, purpose=TrainingPurpose.PIPELINE_TEST)
    metrics = evaluate(model, examples[:10])
    assert set(metrics) == {"mae", "rmse", "r2", "n"} and metrics["n"] == 10
    with pytest.raises(InsufficientTrainingDataError):
        evaluate(model, [])


def test_training_is_reproducible_for_a_fixed_seed():
    examples = _examples(60)
    a = train(examples, purpose=TrainingPurpose.PIPELINE_TEST, seed=5)
    b = train(examples, purpose=TrainingPurpose.PIPELINE_TEST, seed=5)
    fr = extract_features(_req(quantity=3, unit_price_inr=1200))
    assert a.predict_one(fr.vector) == pytest.approx(b.predict_one(fr.vector))


def test_save_and_load_roundtrip(tmp_path):
    model = train(_examples(40), purpose=TrainingPurpose.PIPELINE_TEST, seed=9)
    path = tmp_path / "m.joblib"
    model.save(path)
    loaded = TravelCostModel.load(path)
    fr = extract_features(_req(quantity=2, unit_price_inr=800))
    assert loaded.predict_one(fr.vector) == pytest.approx(model.predict_one(fr.vector))
    assert loaded.metadata.used_feature_names == model.metadata.used_feature_names


def test_load_missing_file_raises():
    with pytest.raises(ModelLoadError, match="not found"):
        TravelCostModel.load("/nonexistent/path/model.joblib")


def test_load_rejects_mismatched_feature_schema(tmp_path):
    model = train(_examples(30), purpose=TrainingPurpose.PIPELINE_TEST)
    path = tmp_path / "m.joblib"
    model.save(path)
    import joblib
    payload = joblib.load(path)
    payload["canonical_feature_names"] = payload["canonical_feature_names"][:-1]
    joblib.dump(payload, path)
    with pytest.raises(ModelLoadError, match="feature schema"):
        TravelCostModel.load(path)


def test_travel_time_model_cannot_load_a_travel_cost_artifact(tmp_path):
    from app.travel_time.model import TravelTimeModel
    model = train(_examples(30), purpose=TrainingPurpose.PIPELINE_TEST)
    path = tmp_path / "m.joblib"
    model.save(path)
    with pytest.raises(ModelLoadError):
        TravelTimeModel.load(path)


# ------------------------------ service -----------------------------------------
def test_service_uses_baseline_by_default():
    status = TravelCostService().engine_status()
    assert not status.model_loaded and status.scoring_method == PredictionMethod.BASELINE
    p = TravelCostService().predict(_req(quantity=2, unit_price_inr=500))
    assert p.method == PredictionMethod.BASELINE


def test_service_prefers_observed_total_over_any_model():
    class _Sk:
        def predict(self, x):
            import numpy as np
            return np.full(len(x), 99999.0)
    from app.ml.model_metadata import ModelMetadata
    meta = ModelMetadata(purpose=TrainingPurpose.PRODUCTION, trained_at="2026-01-01T00:00:00+00:00",
                         n_examples=MIN_PRODUCTION_EXAMPLES, source_counts={"real": MIN_PRODUCTION_EXAMPLES},
                         used_feature_names=list(FEATURE_NAMES), metrics={"mae": 1.0}, sklearn_version="x",
                         model_class="_Sk", seed=1)
    service = TravelCostService(model=TravelCostModel(_Sk(), meta))
    p = service.predict(_req(total_known_price_inr=4200))
    assert p.value == 4200 and p.method == PredictionMethod.OBSERVED


def test_service_never_uses_a_pipeline_test_model_for_predictions():
    model = train(_examples(40), purpose=TrainingPurpose.PIPELINE_TEST)
    service = TravelCostService(model=model)
    p = service.predict(_req(quantity=2, unit_price_inr=500))
    assert p.method == PredictionMethod.BASELINE
    status = service.engine_status()
    assert status.model_loaded and not status.model_is_production


def test_service_uses_a_production_model_when_present():
    class _Sk:
        def predict(self, x):
            import numpy as np
            return np.full(len(x), 777.0)
    from app.ml.model_metadata import ModelMetadata
    meta = ModelMetadata(purpose=TrainingPurpose.PRODUCTION, trained_at="2026-01-01T00:00:00+00:00",
                         n_examples=MIN_PRODUCTION_EXAMPLES, source_counts={"real": MIN_PRODUCTION_EXAMPLES},
                         used_feature_names=list(FEATURE_NAMES), metrics={"mae": 1.0}, sklearn_version="x",
                         model_class="_Sk", seed=1)
    service = TravelCostService(model=TravelCostModel(_Sk(), meta))
    p = service.predict(_req(quantity=2, unit_price_inr=500))
    assert p.method == PredictionMethod.ML_MODEL and p.value == pytest.approx(777.0)
    status = service.engine_status()
    assert status.model_is_production


def test_service_returns_unknown_when_baseline_cannot_compute():
    p = TravelCostService().predict(_req())
    assert p.is_unknown
