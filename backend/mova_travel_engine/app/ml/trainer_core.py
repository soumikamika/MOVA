"""The one sklearn fit/evaluate routine shared by every domain trainer
(recommendation, travel_time, travel_cost). Each domain's trainer.py converts
its own TrainingExample schema into (vectors, labels, sources) and its own
ModelMetadata, but the actual fitting - including the constant-column guard
and the small-dataset in-sample fallback - lives here exactly once.
"""
import numpy as np
from sklearn.ensemble import HistGradientBoostingRegressor
from sklearn.metrics import mean_absolute_error, r2_score
from sklearn.model_selection import train_test_split

from app.core.exceptions import InsufficientTrainingDataError
from app.ml.matrix import MIN_DISTINCT_VALUES, split_constant_columns
from app.ml.training_rules import MIN_PRODUCTION_EXAMPLES, REAL_SOURCES, TrainingPurpose
from app.schemas.common import DataSource

DEFAULT_MODEL_PARAMS = dict(max_iter=100, max_depth=4, learning_rate=0.1)


class FitResult:
    def __init__(self, sklearn_model, used_names, dropped_names, metrics, notes, real_count, n_examples):
        self.sklearn_model = sklearn_model
        self.used_names = used_names
        self.dropped_names = dropped_names
        self.metrics = metrics
        self.notes = notes
        self.real_count = real_count
        self.n_examples = n_examples


def fit_regressor(
    vectors: list[dict[str, float]], labels: list[float], sources: list[DataSource], *,
    feature_names: list[str], purpose: TrainingPurpose, seed: int = 42,
    validation_fraction: float = 0.2, min_production_examples: int = MIN_PRODUCTION_EXAMPLES,
    min_pipeline_test_examples: int = 20, model_params: dict | None = None,
    non_production_note: str | None = None,
) -> FitResult:
    """Fit one HistGradientBoostingRegressor and evaluate it on a held-out split.

    Enforces the same safety rules everywhere: a PRODUCTION fit requires
    `min_production_examples` real-sourced (real/user_generated/external_api)
    examples; a PIPELINE_TEST fit requires at least `min_pipeline_test_examples`
    examples of any source. Both raise InsufficientTrainingDataError otherwise.
    Zero-variance feature columns are dropped before fitting (see
    app.ml.matrix.split_constant_columns) - this is what prevents the
    scikit-learn/numpy "window shape cannot be larger than input array shape"
    edge case seen in Phase C on small/homogeneous training batches.
    """
    n = len(vectors)
    if n == 0:
        raise InsufficientTrainingDataError("no training examples were provided")
    if len(labels) != n or len(sources) != n:
        raise ValueError("vectors, labels and sources must be the same length")

    real_examples = sum(1 for s in sources if s in REAL_SOURCES)
    if purpose == TrainingPurpose.PRODUCTION and real_examples < min_production_examples:
        real_names = ", ".join(s.value for s in sorted(REAL_SOURCES, key=lambda s: s.value))
        raise InsufficientTrainingDataError(
            f"Insufficient real training data: {real_examples} real-sourced example(s) found "
            f"(sources counted as real: {real_names}); at least {min_production_examples} are required to "
            "train a production model. Use TrainingPurpose.PIPELINE_TEST during development, or collect real "
            "interaction/outcome data before training a production model.",
            details={"real_example_count": real_examples, "required": min_production_examples},
        )
    if purpose == TrainingPurpose.PIPELINE_TEST and n < min_pipeline_test_examples:
        raise InsufficientTrainingDataError(
            f"Insufficient examples for even a pipeline test: {n} found, {min_pipeline_test_examples} required.",
            details={"example_count": n, "required": min_pipeline_test_examples},
        )

    x_full = np.array([[v[name] for name in feature_names] for v in vectors], dtype=float)
    y = np.array(labels, dtype=float)

    x, used_names, dropped_names = split_constant_columns(x_full, list(feature_names))
    if not used_names:
        raise InsufficientTrainingDataError(
            f"every engineered feature is constant across these {n} training example(s); a model cannot be "
            "trained until the examples vary in at least one feature.",
            details={"n_examples": n},
        )

    # Below this, a held-out split is too small to be a meaningful evaluation - all data is used for
    # both training and (in-sample, clearly labelled) evaluation instead.
    in_sample = n < 25 or int(n * validation_fraction) < 2
    if in_sample:
        x_train, y_train, x_val, y_val = x, y, x, y
    else:
        x_train, x_val, y_train, y_val = train_test_split(x, y, test_size=validation_fraction, random_state=seed)

    params = dict(DEFAULT_MODEL_PARAMS)
    if model_params:
        params.update(model_params)
    model = HistGradientBoostingRegressor(random_state=seed, **params)
    model.fit(x_train, y_train)

    preds = model.predict(x_val)
    metrics = {
        "mae": float(mean_absolute_error(y_val, preds)),
        "rmse": float(np.sqrt(np.mean((y_val - preds) ** 2))),
        "r2": float(r2_score(y_val, preds)) if len(set(y_val.tolist())) > 1 else float("nan"),
        "n_train": float(len(x_train)), "n_val": float(len(x_val)),
        "in_sample_evaluation": 1.0 if in_sample else 0.0,
    }

    notes = []
    if dropped_names:
        preview = ", ".join(dropped_names[:8]) + (", ..." if len(dropped_names) > 8 else "")
        notes.append(
            f"{len(dropped_names)} of {len(feature_names)} feature(s) had fewer than {MIN_DISTINCT_VALUES} "
            f"distinct values in this training set and were excluded (they carry no information for a tree "
            f"split; predictions are unaffected): {preview}"
        )
    if purpose == TrainingPurpose.PIPELINE_TEST:
        notes.append(non_production_note or (
            "PIPELINE-TEST MODEL: trained on non-production data (see source_counts / label_origins). "
            "This is NOT a validated production model and must not be presented as one - it exists only to "
            "test the training and inference pipeline."
        ))
    if in_sample:
        notes.append("Validation set equals the training set (too few examples to hold data out); "
                     "the reported metrics are in-sample and almost certainly optimistic.")
    if real_examples == 0:
        notes.append("Zero real-sourced (real / user_generated / external_api) examples were used.")

    return FitResult(model, used_names, dropped_names, metrics, notes, real_examples, n)
