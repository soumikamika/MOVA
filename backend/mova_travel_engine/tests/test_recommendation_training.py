import math

import pytest

from app.core.exceptions import InsufficientTrainingDataError, ModelLoadError
from app.recommendation.features import FEATURE_NAMES, extract_features
from app.recommendation.model import ModelMetadata, RecommendationModel, TrainingPurpose
from app.recommendation.trainer import (
    MIN_PIPELINE_TEST_EXAMPLES, MIN_PRODUCTION_EXAMPLES, LabelOrigin, build_pipeline_test_examples_from_fallback,
    evaluate, make_training_example, train,
)
from app.schemas.common import DataSource
from tests.factories import make_place
from tests.factories_recommendation import make_trip


def _pipeline_examples(n=40, seed=0):
    import random
    rng = random.Random(seed)
    trip = make_trip()
    results = []
    for i in range(n):
        place = make_place(
            id=f"p{i}", rating=rng.choice([None, 3.0, 4.5]), popularity=rng.choice([None, 0.2, 0.8]),
            entry_fee_inr=rng.choice([0, 500, 5000]), tags=rng.sample(["beaches", "food", "nature", "clubs"], k=2),
            intensity=rng.randint(1, 5),
        )
        results.append(extract_features(trip, place))
    return build_pipeline_test_examples_from_fallback(results)


# ------------------------------ example construction --------------------------
def test_pipeline_test_examples_are_forced_synthetic_even_if_place_is_real():
    trip, real_place = make_trip(), make_place(source="real")
    fr = extract_features(trip, real_place)
    [example] = build_pipeline_test_examples_from_fallback([fr])
    assert example.source == DataSource.SYNTHETIC_DEV
    assert example.label_origin == LabelOrigin.FALLBACK_HEURISTIC
    assert 0.0 <= example.label <= 1.0


def test_make_training_example_preserves_given_source():
    fr = extract_features(make_trip(), make_place())
    ex = make_training_example(fr, label=0.7, source=DataSource.REAL, label_origin=LabelOrigin.HUMAN_FEEDBACK)
    assert ex.source == DataSource.REAL and ex.label == 0.7


def test_training_example_label_must_be_in_unit_range():
    from pydantic import ValidationError
    fr = extract_features(make_trip(), make_place())
    with pytest.raises(ValidationError):
        make_training_example(fr, label=1.5, source=DataSource.SYNTHETIC_DEV, label_origin=LabelOrigin.FALLBACK_HEURISTIC)


# ------------------------------ insufficient-data safeguards ------------------
def test_empty_examples_rejected():
    with pytest.raises(InsufficientTrainingDataError):
        train([], purpose=TrainingPurpose.PIPELINE_TEST)


def test_too_few_pipeline_test_examples_rejected():
    with pytest.raises(InsufficientTrainingDataError, match=str(MIN_PIPELINE_TEST_EXAMPLES)):
        train(_pipeline_examples(n=MIN_PIPELINE_TEST_EXAMPLES - 1), purpose=TrainingPurpose.PIPELINE_TEST)


def test_production_training_refused_with_only_synthetic_data():
    examples = _pipeline_examples(n=600)   # plenty of examples, but ALL synthetic_dev
    with pytest.raises(InsufficientTrainingDataError, match="Insufficient real training data"):
        train(examples, purpose=TrainingPurpose.PRODUCTION)


def test_production_training_refused_below_threshold_even_with_real_examples():
    fr = extract_features(make_trip(), make_place())
    real_examples = [make_training_example(fr, label=0.6, source=DataSource.REAL,
                                           label_origin=LabelOrigin.HUMAN_FEEDBACK)
                     for _ in range(MIN_PRODUCTION_EXAMPLES - 1)]
    with pytest.raises(InsufficientTrainingDataError):
        train(real_examples, purpose=TrainingPurpose.PRODUCTION)


def test_production_training_succeeds_once_enough_real_examples_exist():
    import random
    rng = random.Random(1)
    trip = make_trip()
    examples = []
    for i in range(MIN_PRODUCTION_EXAMPLES + 20):
        place = make_place(id=f"real{i}", rating=rng.choice([2.0, 4.8]), tags=rng.sample(["beaches", "food"], k=1))
        fr = extract_features(trip, place)
        examples.append(make_training_example(fr, label=rng.random(), source=DataSource.REAL,
                                               label_origin=LabelOrigin.HUMAN_FEEDBACK))
    model = train(examples, purpose=TrainingPurpose.PRODUCTION, seed=3)
    assert model.metadata.is_production
    assert model.metadata.real_example_count == len(examples)
    assert "PIPELINE-TEST" not in " ".join(model.metadata.notes)


# ------------------------------ training mechanics -----------------------------
def test_pipeline_test_training_succeeds_and_is_labelled_non_production():
    model = train(_pipeline_examples(n=60), purpose=TrainingPurpose.PIPELINE_TEST, seed=1)
    assert not model.metadata.is_production
    assert model.metadata.purpose == TrainingPurpose.PIPELINE_TEST
    assert any("PIPELINE-TEST" in n for n in model.metadata.notes)
    assert model.metadata.source_counts == {"synthetic_dev": 60}
    assert model.metadata.real_example_count == 0
    assert set(model.metadata.metrics) >= {"mae", "rmse", "r2", "n_train", "n_val"}
    # used + dropped exactly partitions the full feature universe, in canonical order
    assert model.metadata.used_feature_names + model.metadata.dropped_feature_names != []
    assert set(model.metadata.used_feature_names) | set(model.metadata.dropped_feature_names) == set(FEATURE_NAMES)
    assert set(model.metadata.used_feature_names) & set(model.metadata.dropped_feature_names) == set()
    assert model.metadata.used_feature_names == [n for n in FEATURE_NAMES if n in set(model.metadata.used_feature_names)]
    # this dataset reuses one trip for every example, so category_*/trip_type_*/travellers/... are
    # genuinely constant and MUST have been dropped rather than crashing the underlying fit
    assert model.metadata.dropped_feature_names != []


def test_small_example_count_triggers_in_sample_warning():
    model = train(_pipeline_examples(n=MIN_PIPELINE_TEST_EXAMPLES), purpose=TrainingPurpose.PIPELINE_TEST)
    assert model.metadata.metrics["in_sample_evaluation"] == 1.0
    assert any("in-sample" in n for n in model.metadata.notes)


def test_predictions_are_bounded_to_unit_interval():
    model = train(_pipeline_examples(n=80), purpose=TrainingPurpose.PIPELINE_TEST, seed=2)
    for fr in [extract_features(make_trip(), make_place(id=str(i), rating=r))
              for i, r in enumerate([0.0, 5.0, None, 2.5])]:
        pred = model.predict_one(fr.vector)
        assert 0.0 <= pred <= 1.0 and not math.isnan(pred)


def test_predict_many_matches_predict_one_and_handles_empty():
    model = train(_pipeline_examples(n=50), purpose=TrainingPurpose.PIPELINE_TEST)
    vectors = [extract_features(make_trip(), make_place(id=str(i))).vector for i in range(3)]
    assert model.predict_many(vectors) == [model.predict_one(v) for v in vectors]
    assert model.predict_many([]) == []


def test_evaluate_reuses_predict_many_and_reports_metrics():
    examples = _pipeline_examples(n=50)
    model = train(examples, purpose=TrainingPurpose.PIPELINE_TEST)
    metrics = evaluate(model, examples[:10])
    assert set(metrics) == {"mae", "rmse", "r2", "n"} and metrics["n"] == 10


def test_evaluate_rejects_empty_examples():
    model = train(_pipeline_examples(n=30), purpose=TrainingPurpose.PIPELINE_TEST)
    with pytest.raises(InsufficientTrainingDataError):
        evaluate(model, [])


def test_training_is_reproducible_for_a_fixed_seed():
    examples = _pipeline_examples(n=60)
    a = train(examples, purpose=TrainingPurpose.PIPELINE_TEST, seed=5)
    b = train(examples, purpose=TrainingPurpose.PIPELINE_TEST, seed=5)
    fr = extract_features(make_trip(), make_place())
    assert a.predict_one(fr.vector) == pytest.approx(b.predict_one(fr.vector))


# ------------------------------ save / load -------------------------------------
def test_save_and_load_roundtrip(tmp_path):
    model = train(_pipeline_examples(n=40), purpose=TrainingPurpose.PIPELINE_TEST, seed=9)
    path = tmp_path / "m.joblib"
    model.save(path)
    loaded = RecommendationModel.load(path)
    fr = extract_features(make_trip(), make_place())
    assert loaded.predict_one(fr.vector) == pytest.approx(model.predict_one(fr.vector))
    assert loaded.metadata.purpose == TrainingPurpose.PIPELINE_TEST
    assert loaded.metadata.used_feature_names == model.metadata.used_feature_names
    assert loaded.metadata.dropped_feature_names == model.metadata.dropped_feature_names
    assert set(loaded.metadata.used_feature_names) <= set(FEATURE_NAMES)


def test_load_missing_file_raises():
    with pytest.raises(ModelLoadError, match="not found"):
        RecommendationModel.load("/nonexistent/path/model.joblib")


def test_load_corrupt_file_raises(tmp_path):
    path = tmp_path / "bad.joblib"
    path.write_bytes(b"not a joblib file")
    with pytest.raises(ModelLoadError):
        RecommendationModel.load(path)


def test_load_rejects_model_with_mismatched_feature_schema(tmp_path):
    model = train(_pipeline_examples(n=30), purpose=TrainingPurpose.PIPELINE_TEST)
    path = tmp_path / "m.joblib"
    model.save(path)
    import joblib
    payload = joblib.load(path)
    payload["canonical_feature_names"] = payload["canonical_feature_names"][:-1]  # schema drift
    joblib.dump(payload, path)
    with pytest.raises(ModelLoadError, match="feature schema"):
        RecommendationModel.load(path)


def test_load_rejects_file_missing_required_keys(tmp_path):
    import joblib
    path = tmp_path / "m.joblib"
    joblib.dump({"sklearn_model": None}, path)
    with pytest.raises(ModelLoadError):
        RecommendationModel.load(path)


# ------------------------------ constant-column guard --------------------------
# Regression coverage for: "ValueError: window shape cannot be larger than input
# array shape", raised by some scikit-learn/numpy version combinations when a
# feature column has fewer than two distinct values. Small or homogeneous
# training batches routinely produce such columns (a single trip's context
# fields, or one-hot columns for a category that never varies) - see
# split_constant_columns() and the "Constant-feature guard" note in model.py.
from app.recommendation.trainer import MIN_DISTINCT_VALUES, split_constant_columns  # noqa: E402


def test_split_constant_columns_drops_only_zero_variance_columns():
    import numpy as np
    x = np.array([
        [1.0, 5.0, float("nan")],
        [1.0, 6.0, float("nan")],
        [1.0, 7.0, 2.0],
    ])
    names = ["constant", "varying", "single_known_value"]
    reduced, kept, dropped = split_constant_columns(x, names)
    assert kept == ["varying"] and dropped == ["constant", "single_known_value"]
    assert reduced.shape == (3, 1)
    assert reduced[:, 0].tolist() == [5.0, 6.0, 7.0]


def test_split_constant_columns_keeps_binary_indicator_even_if_imbalanced():
    import numpy as np
    x = np.array([[0.0], [0.0], [0.0], [1.0]])   # 3 zeros, 1 one - still 2 distinct values
    reduced, kept, dropped = split_constant_columns(x, ["flag"])
    assert kept == ["flag"] and dropped == []
    assert reduced.shape == (4, 1)


def test_split_constant_columns_all_nan_column_is_dropped():
    import numpy as np
    x = np.array([[float("nan"), 1.0], [float("nan"), 2.0]])
    reduced, kept, dropped = split_constant_columns(x, ["all_unknown", "varying"])
    assert kept == ["varying"] and dropped == ["all_unknown"]


def test_split_constant_columns_preserves_canonical_order():
    import numpy as np
    x = np.array([[1.0, 2.0, 3.0], [1.0, 5.0, 9.0]])   # col 0 constant; cols 1,2 vary
    _, kept, dropped = split_constant_columns(x, ["a", "b", "c"])
    assert kept == ["b", "c"] and dropped == ["a"]


def test_all_constant_features_raise_a_clear_error_instead_of_crashing_sklearn():
    """The exact degenerate case: every example shares one trip AND one
    unvaried place, so literally every engineered feature is constant."""
    trip = make_trip()
    place = make_place()   # id fixed too, but that's not a feature
    results = [extract_features(trip, place) for _ in range(MIN_PIPELINE_TEST_EXAMPLES + 5)]
    examples = build_pipeline_test_examples_from_fallback(results)
    with pytest.raises(InsufficientTrainingDataError, match="constant"):
        train(examples, purpose=TrainingPurpose.PIPELINE_TEST)


def test_training_succeeds_at_the_minimum_pipeline_test_size_with_realistic_constant_columns():
    """Reproduces the reported failure shape directly: n == MIN_PIPELINE_TEST_EXAMPLES
    (the smallest allowed batch), a SINGLE reused trip (so every context/one-hot
    column - category_*, trip_type_*, travellers, trip_duration_days,
    budget_per_traveller_inr, ... - is constant), with only `rating` varying.
    Before the fix this shape reliably hit the sklearn/numpy binning edge case;
    it must now train without error and drop the constant columns explicitly."""
    trip = make_trip()
    results = [extract_features(trip, make_place(id=f"p{i}", rating=(3.0 if i % 2 else 4.5)))
              for i in range(MIN_PIPELINE_TEST_EXAMPLES)]
    examples = build_pipeline_test_examples_from_fallback(results)
    model = train(examples, purpose=TrainingPurpose.PIPELINE_TEST, seed=1)
    assert "rating" in model.metadata.used_feature_names
    assert len(model.metadata.dropped_feature_names) >= 30      # category_*, trip_type_*, context fields, ...
    pred = model.predict_one(results[0].vector)
    assert 0.0 <= pred <= 1.0


def test_predict_ignores_extra_vector_keys_not_in_used_feature_names():
    """At inference, a feature that was constant (and dropped) during training
    may genuinely differ for a new place; predict_many must not choke on it -
    it only reads metadata.used_feature_names."""
    model = train(_pipeline_examples(n=40), purpose=TrainingPurpose.PIPELINE_TEST)
    base = extract_features(make_trip(), make_place()).vector
    different_category = dict(base)
    for k in list(different_category):
        if k.startswith("category_"):
            different_category[k] = 1.0 if k == "category_museum" else 0.0
    pred = model.predict_one(different_category)
    assert 0.0 <= pred <= 1.0


def test_used_feature_names_never_include_dropped_ones_end_to_end():
    model = train(_pipeline_examples(n=50), purpose=TrainingPurpose.PIPELINE_TEST)
    assert set(model.metadata.used_feature_names).isdisjoint(model.metadata.dropped_feature_names)
    assert model.metadata.used_feature_names   # never empty for data with real variance
