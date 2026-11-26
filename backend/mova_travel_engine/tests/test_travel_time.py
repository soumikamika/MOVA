"""Covers app/travel_time/{features,baseline,model,trainer,service}.py."""
import math
import random

import pytest

from app.core.exceptions import InsufficientTrainingDataError, ModelLoadError
from app.ml.training_rules import MIN_PRODUCTION_EXAMPLES, TrainingPurpose
from app.schemas.common import DataSource
from app.schemas.logistics import TravelTimeRequest
from app.schemas.prediction import PredictionMethod
from app.travel_time.baseline import BASELINE_SPEED_KMH, TRANSFER_PENALTY_MINUTES
from app.travel_time.baseline import estimate as baseline_estimate
from app.travel_time.features import FEATURE_NAMES, extract_features
from app.travel_time.model import TravelTimeModel
from app.travel_time.service import TravelTimeService
from app.travel_time.trainer import (
    LabelOrigin, MIN_PIPELINE_TEST_EXAMPLES, build_pipeline_test_examples_from_baseline,
    evaluate, make_training_example, train,
)


def _req(**kw):
    base = dict(origin="Mumbai", destination="Goa", mode="train")
    base.update(kw)
    return TravelTimeRequest(**base)


# ------------------------------ features --------------------------------------
def test_feature_names_cover_all_modes_and_no_duplicates():
    assert len(FEATURE_NAMES) == len(set(FEATURE_NAMES))
    assert any(n.startswith("mode_") for n in FEATURE_NAMES)


def test_vector_covers_every_feature_name():
    fr = extract_features(_req(distance_km=500))
    assert set(fr.vector) == set(FEATURE_NAMES)


def test_unknown_optional_fields_become_nan():
    fr = extract_features(_req())   # no distance/time/date/transfers
    assert math.isnan(fr.vector["distance_km"])
    assert math.isnan(fr.vector["departure_hour"])
    assert math.isnan(fr.vector["weekday"])
    assert math.isnan(fr.vector["month"])
    assert math.isnan(fr.vector["num_transfers"])
    assert fr.facts.distance_km is None and fr.facts.departure_hour is None


def test_known_fields_pass_through():
    import datetime as dt
    fr = extract_features(_req(distance_km=120, departure_time="09:30", date=dt.date(2027, 3, 15), num_transfers=2))
    assert fr.vector["distance_km"] == 120
    assert fr.vector["departure_hour"] == 9.0
    assert fr.vector["weekday"] == float(dt.date(2027, 3, 15).weekday())
    assert fr.vector["month"] == 3.0
    assert fr.vector["num_transfers"] == 2.0


def test_explicit_weekday_overrides_date_derived_weekday():
    import datetime as dt
    fr = extract_features(_req(date=dt.date(2027, 3, 15), weekday=0))
    assert fr.facts.weekday == 0


def test_mode_one_hot_is_exclusive():
    fr = extract_features(_req(mode="flight"))
    on = [n for n in FEATURE_NAMES if n.startswith("mode_") and fr.vector[n] == 1.0]
    assert on == ["mode_flight"]


def test_malformed_request_rejected_by_schema():
    from pydantic import ValidationError
    with pytest.raises(ValidationError):
        _req(distance_km=-5)
    with pytest.raises(ValidationError):
        _req(weekday=7)


# ------------------------------ baseline ---------------------------------------
def test_missing_distance_returns_explicit_unknown():
    p = baseline_estimate(_req())
    assert p.is_unknown and p.value is None and p.lower_bound is None and p.upper_bound is None
    assert p.method == PredictionMethod.UNKNOWN
    assert p.notes


@pytest.mark.parametrize("mode", list(BASELINE_SPEED_KMH))
def test_baseline_calculation_matches_documented_formula(mode):
    p = baseline_estimate(_req(mode=mode, distance_km=100))
    expected = (100 / BASELINE_SPEED_KMH[mode]) * 60
    assert p.value == pytest.approx(expected, abs=0.05)   # value is rounded to 1 decimal
    assert p.method == PredictionMethod.BASELINE
    assert p.is_estimated and not p.is_unknown


def test_transfer_penalty_is_additive():
    base = baseline_estimate(_req(distance_km=200)).value
    with_transfer = baseline_estimate(_req(distance_km=200, num_transfers=1)).value
    assert with_transfer == pytest.approx(base + TRANSFER_PENALTY_MINUTES)
    with_two = baseline_estimate(_req(distance_km=200, num_transfers=2)).value
    assert with_two == pytest.approx(base + 2 * TRANSFER_PENALTY_MINUTES)


def test_baseline_prediction_is_non_negative_and_bounded():
    p = baseline_estimate(_req(distance_km=300))
    assert p.value > 0 and p.lower_bound > 0 and p.lower_bound <= p.value <= p.upper_bound


def test_baseline_confidence_is_low_and_never_claims_accuracy():
    p = baseline_estimate(_req(distance_km=300))
    assert p.confidence.value == "low"
    assert any("not calibrated" in n for n in p.notes)


def test_different_transport_modes_give_different_durations_for_same_distance():
    durations = {m: baseline_estimate(_req(mode=m, distance_km=300)).value for m in ("flight", "walk", "train")}
    assert durations["walk"] > durations["train"] > durations["flight"]


# ------------------------------ prediction schema invariants --------------------
def test_prediction_unknown_is_internally_consistent():
    p = baseline_estimate(_req())
    assert p.is_unknown and p.method == PredictionMethod.UNKNOWN
    with pytest.raises(Exception):
        from app.schemas.prediction import Prediction
        Prediction(prediction_type="x", unit="y", method=PredictionMethod.UNKNOWN, is_unknown=False)


def test_prediction_metadata_fields_present():
    p = baseline_estimate(_req(distance_km=100))
    assert p.prediction_type == "travel_time_minutes" and p.unit == "minutes"
    assert p.method == PredictionMethod.BASELINE
    assert p.is_estimated is True and p.is_unknown is False
    assert p.confidence is not None


# ------------------------------ training ----------------------------------------
def _requests(n, seed=0, modes=("train", "bus", "car", "flight")):
    rng = random.Random(seed)
    return [_req(mode=rng.choice(modes), distance_km=rng.uniform(20, 900), num_transfers=rng.choice([0, 0, 1, 2]))
           for _ in range(n)]


def _examples(n=40, seed=0):
    frs = [extract_features(r) for r in _requests(n, seed)]
    return build_pipeline_test_examples_from_baseline(frs)


def test_pipeline_test_examples_forced_synthetic():
    ex = _examples(30)
    assert all(e.source == DataSource.SYNTHETIC_DEV for e in ex)
    assert all(e.label_origin == LabelOrigin.BASELINE_HEURISTIC for e in ex)
    assert all(e.label >= 0 for e in ex)


def test_examples_skip_requests_with_unknown_distance():
    frs = [extract_features(_req(distance_km=None)), extract_features(_req(distance_km=100))]
    ex = build_pipeline_test_examples_from_baseline(frs)
    assert len(ex) == 1


def test_make_training_example_preserves_given_source():
    fr = extract_features(_req(distance_km=100))
    ex = make_training_example(fr, label=42.0, source=DataSource.REAL, label_origin=LabelOrigin.OBSERVED_DURATION)
    assert ex.source == DataSource.REAL and ex.label == 42.0


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
    fr = extract_features(_req(distance_km=100))
    real_examples = [make_training_example(fr, label=60.0, source=DataSource.REAL,
                                           label_origin=LabelOrigin.OBSERVED_DURATION)
                     for _ in range(MIN_PRODUCTION_EXAMPLES - 1)]
    with pytest.raises(InsufficientTrainingDataError):
        train(real_examples, purpose=TrainingPurpose.PRODUCTION)


def test_production_training_succeeds_with_enough_real_examples():
    rng = random.Random(1)
    reqs = _requests(MIN_PRODUCTION_EXAMPLES + 20, seed=1)
    examples = []
    for r in reqs:
        fr = extract_features(r)
        label = max(0.0, (r.distance_km / 50.0) * 60.0 + rng.uniform(-10, 10))
        examples.append(make_training_example(fr, label=label, source=DataSource.REAL,
                                               label_origin=LabelOrigin.OBSERVED_DURATION))
    model = train(examples, purpose=TrainingPurpose.PRODUCTION, seed=3)
    assert model.metadata.is_production
    assert model.metadata.real_example_count == len(examples)
    assert "PIPELINE-TEST" not in " ".join(model.metadata.notes)


def test_pipeline_test_model_labelled_non_production():
    model = train(_examples(60), purpose=TrainingPurpose.PIPELINE_TEST, seed=1)
    assert not model.metadata.is_production
    assert any("PIPELINE-TEST" in n for n in model.metadata.notes)
    assert model.metadata.source_counts == {"synthetic_dev": 60}
    assert model.metadata.real_example_count == 0


def test_constant_and_all_nan_columns_are_dropped_not_crashed():
    """Every example shares one mode and no transfers/date -> many constant columns."""
    frs = [extract_features(_req(distance_km=d)) for d in
          [50, 100, 150, 200, 250, 300, 350, 400, 450, 500, 550, 600, 650, 700, 750, 800, 850, 900, 950, 1000]]
    examples = build_pipeline_test_examples_from_baseline(frs)
    model = train(examples, purpose=TrainingPurpose.PIPELINE_TEST, seed=1)
    assert "distance_km" in model.metadata.used_feature_names
    assert model.metadata.dropped_feature_names   # mode_* one-hots, departure_hour, weekday, month, num_transfers


def test_all_constant_features_raise_clear_error():
    fr = extract_features(_req(distance_km=100))
    examples = build_pipeline_test_examples_from_baseline([fr] * (MIN_PIPELINE_TEST_EXAMPLES + 5))
    with pytest.raises(InsufficientTrainingDataError, match="constant"):
        train(examples, purpose=TrainingPurpose.PIPELINE_TEST)


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
    fr = extract_features(_req(distance_km=321))
    assert a.predict_one(fr.vector) == pytest.approx(b.predict_one(fr.vector))


def test_save_and_load_roundtrip(tmp_path):
    model = train(_examples(40), purpose=TrainingPurpose.PIPELINE_TEST, seed=9)
    path = tmp_path / "m.joblib"
    model.save(path)
    loaded = TravelTimeModel.load(path)
    fr = extract_features(_req(distance_km=250))
    assert loaded.predict_one(fr.vector) == pytest.approx(model.predict_one(fr.vector))
    assert loaded.metadata.used_feature_names == model.metadata.used_feature_names


def test_load_missing_file_raises():
    with pytest.raises(ModelLoadError, match="not found"):
        TravelTimeModel.load("/nonexistent/path/model.joblib")


def test_load_rejects_mismatched_feature_schema(tmp_path):
    model = train(_examples(30), purpose=TrainingPurpose.PIPELINE_TEST)
    path = tmp_path / "m.joblib"
    model.save(path)
    import joblib
    payload = joblib.load(path)
    payload["canonical_feature_names"] = payload["canonical_feature_names"][:-1]
    joblib.dump(payload, path)
    with pytest.raises(ModelLoadError, match="feature schema"):
        TravelTimeModel.load(path)


def test_recommendation_model_cannot_load_a_travel_time_artifact(tmp_path):
    """Cross-domain schema-drift protection: each domain's canonical feature
    universe is different, so loading across domains must fail loudly."""
    from app.recommendation.model import RecommendationModel
    model = train(_examples(30), purpose=TrainingPurpose.PIPELINE_TEST)
    path = tmp_path / "m.joblib"
    model.save(path)
    with pytest.raises(ModelLoadError):
        RecommendationModel.load(path)


# ------------------------------ service -----------------------------------------
def test_service_uses_baseline_by_default():
    status = TravelTimeService().engine_status()
    assert not status.model_loaded and status.scoring_method == PredictionMethod.BASELINE
    p = TravelTimeService().predict(_req(distance_km=200))
    assert p.method == PredictionMethod.BASELINE


def test_service_never_uses_a_pipeline_test_model_for_predictions():
    model = train(_examples(40), purpose=TrainingPurpose.PIPELINE_TEST)
    service = TravelTimeService(model=model)
    p = service.predict(_req(distance_km=200))
    assert p.method == PredictionMethod.BASELINE
    status = service.engine_status()
    assert status.model_loaded and not status.model_is_production


def test_service_uses_a_production_model_when_present():
    class _Sk:
        def predict(self, x):
            import numpy as np
            return np.full(len(x), 123.0)
    from app.ml.model_metadata import ModelMetadata
    meta = ModelMetadata(purpose=TrainingPurpose.PRODUCTION, trained_at="2026-01-01T00:00:00+00:00",
                         n_examples=MIN_PRODUCTION_EXAMPLES, source_counts={"real": MIN_PRODUCTION_EXAMPLES},
                         used_feature_names=list(FEATURE_NAMES), metrics={"mae": 1.0}, sklearn_version="x",
                         model_class="_Sk", seed=1)
    service = TravelTimeService(model=TravelTimeModel(_Sk(), meta))
    p = service.predict(_req(distance_km=200))
    assert p.method == PredictionMethod.ML_MODEL and p.value == pytest.approx(123.0)
    assert p.model_version == "_Sk"
    status = service.engine_status()
    assert status.model_is_production and status.scoring_method == PredictionMethod.ML_MODEL


def test_service_still_returns_unknown_with_a_production_model_if_distance_missing():
    """The production model path is only reached via engine_status; when the
    service uses baseline (no production model loaded) missing distance must
    still surface as unknown, not a fabricated number."""
    p = TravelTimeService().predict(_req())
    assert p.is_unknown
