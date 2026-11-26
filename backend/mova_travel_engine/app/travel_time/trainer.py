"""Training interface for travel-time: labelled examples -> evaluated TravelTimeModel.

Same safety rules as app.recommendation.trainer (see that module for the full
rationale): TrainingPurpose.PRODUCTION requires >= MIN_PRODUCTION_EXAMPLES
real-sourced (real/user_generated/external_api) examples; PIPELINE_TEST allows
synthetic/baseline-derived data but the resulting model is labelled
non-production and TravelTimeService never uses one to score real predictions.
"""
import datetime as dt
from enum import StrEnum

import numpy as np
from pydantic import Field
from sklearn.metrics import mean_absolute_error, r2_score

from app.core.exceptions import InsufficientTrainingDataError
from app.ml.trainer_core import fit_regressor
from app.ml.training_rules import MIN_PRODUCTION_EXAMPLES, TrainingPurpose, source_counts
from app.schemas.common import DataSource, MovaModel
from app.travel_time.baseline import estimate as baseline_estimate
from app.travel_time.features import FEATURE_NAMES, FeatureResult
from app.travel_time.model import TravelTimeModel

MIN_PIPELINE_TEST_EXAMPLES = 20

_NON_PRODUCTION_NOTE = (
    "PIPELINE-TEST MODEL: trained on non-production data (see source_counts / label_origins). "
    "This is NOT a validated travel-time predictor and must not be presented as one - it exists only "
    "to test the training and inference pipeline."
)


class LabelOrigin(StrEnum):
    BASELINE_HEURISTIC = "baseline_heuristic"  # label = the deterministic baseline formula, not an observed time
    OBSERVED_DURATION = "observed_duration"    # an actual measured/logged travel duration
    PROVIDER_API = "provider_api"               # duration returned by a routing/maps provider
    HISTORICAL_LOG = "historical_log"           # derived from historical trip records


class TrainingExample(MovaModel):
    vector: dict[str, float]
    label: float = Field(ge=0)     # minutes; unbounded above
    source: DataSource              # provenance of the LABEL, never upgraded/downgraded by this module
    label_origin: LabelOrigin


def make_training_example(
    features: FeatureResult, *, label: float, source: DataSource, label_origin: LabelOrigin,
) -> TrainingExample:
    return TrainingExample(vector=features.vector, label=label, source=source, label_origin=label_origin)


def build_pipeline_test_examples_from_baseline(feature_results: list[FeatureResult]) -> list[TrainingExample]:
    """Label = the deterministic baseline estimate for that route, when computable.

    Forces source=SYNTHETIC_DEV/label_origin=BASELINE_HEURISTIC regardless of
    anything else about the request - a baseline-derived label is never real
    evidence about actual travel times. Requests whose baseline is unknown
    (distance_km missing) are skipped: an unknown value cannot be a label.
    """
    out = []
    for fr in feature_results:
        f = fr.facts
        # Reconstruct a minimal request-shaped estimate directly from facts/vector
        # rather than re-deriving a TravelTimeRequest, since only distance/mode
        # matter for the baseline formula itself.
        if f.distance_km is None:
            continue
        speed = _speed_for(f.mode.value)
        minutes = (f.distance_km / speed) * 60.0
        if f.num_transfers:
            minutes += f.num_transfers * 20.0
        out.append(make_training_example(fr, label=round(minutes, 1), source=DataSource.SYNTHETIC_DEV,
                                         label_origin=LabelOrigin.BASELINE_HEURISTIC))
    return out


def _speed_for(mode_value: str) -> float:
    from app.travel_time.baseline import BASELINE_SPEED_KMH
    return BASELINE_SPEED_KMH[mode_value]


def train(
    examples: list[TrainingExample], *, purpose: TrainingPurpose, seed: int = 42,
    validation_fraction: float = 0.2, model_params: dict | None = None,
) -> TravelTimeModel:
    from app.ml.model_metadata import ModelMetadata
    from app.ml.base_model import sklearn_version
    from collections import Counter

    result = fit_regressor(
        [e.vector for e in examples], [e.label for e in examples], [e.source for e in examples],
        feature_names=list(FEATURE_NAMES), purpose=purpose, seed=seed, validation_fraction=validation_fraction,
        min_production_examples=MIN_PRODUCTION_EXAMPLES, min_pipeline_test_examples=MIN_PIPELINE_TEST_EXAMPLES,
        model_params=model_params, non_production_note=_NON_PRODUCTION_NOTE,
    )
    label_origins = {k.value: v for k, v in Counter(e.label_origin for e in examples).items()}
    metadata = ModelMetadata(
        purpose=purpose, trained_at=dt.datetime.now(dt.timezone.utc), n_examples=result.n_examples,
        source_counts=source_counts(examples), label_origins=label_origins,
        used_feature_names=result.used_names, dropped_feature_names=result.dropped_names, metrics=result.metrics,
        sklearn_version=sklearn_version(), model_class=type(result.sklearn_model).__name__, seed=seed,
        notes=result.notes,
    )
    return TravelTimeModel(result.sklearn_model, metadata)


def evaluate(model: TravelTimeModel, examples: list[TrainingExample]) -> dict[str, float]:
    if not examples:
        raise InsufficientTrainingDataError("no examples provided for evaluation")
    y = np.array([e.label for e in examples], dtype=float)
    preds = np.array(model.predict_many([e.vector for e in examples]), dtype=float)
    return {
        "mae": float(mean_absolute_error(y, preds)),
        "rmse": float(np.sqrt(np.mean((y - preds) ** 2))),
        "r2": float(r2_score(y, preds)) if len(set(y.tolist())) > 1 else float("nan"),
        "n": float(len(examples)),
    }
