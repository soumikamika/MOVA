"""Training interface for cost prediction: labelled examples -> evaluated
TravelCostModel. Same safety rules as every other domain trainer in this
project - see app.recommendation.trainer for the full rationale.
"""
import datetime as dt
from collections import Counter
from enum import StrEnum

import numpy as np
from pydantic import Field
from sklearn.metrics import mean_absolute_error, r2_score

from app.core.exceptions import InsufficientTrainingDataError
from app.ml.base_model import sklearn_version
from app.ml.model_metadata import ModelMetadata
from app.ml.trainer_core import fit_regressor
from app.ml.training_rules import MIN_PRODUCTION_EXAMPLES, TrainingPurpose, source_counts
from app.schemas.common import DataSource, MovaModel
from app.travel_cost.baseline import estimate as baseline_estimate
from app.travel_cost.features import FEATURE_NAMES, FeatureResult
from app.travel_cost.model import TravelCostModel

MIN_PIPELINE_TEST_EXAMPLES = 20

_NON_PRODUCTION_NOTE = (
    "PIPELINE-TEST MODEL: trained on non-production data (see source_counts / label_origins). "
    "This is NOT a validated cost predictor and must not be presented as one - it exists only "
    "to test the training and inference pipeline."
)


class LabelOrigin(StrEnum):
    BASELINE_HEURISTIC = "baseline_heuristic"  # label = quantity x unit_price_inr, not an observed price
    OBSERVED_PRICE = "observed_price"           # an actual known/booked price
    PROVIDER_API = "provider_api"               # price returned by a booking/pricing provider
    BOOKING_OUTCOME = "booking_outcome"         # derived from what the traveller actually paid


class TrainingExample(MovaModel):
    vector: dict[str, float]
    label: float = Field(ge=0)     # INR; unbounded above
    source: DataSource              # provenance of the LABEL, never upgraded/downgraded by this module
    label_origin: LabelOrigin


def make_training_example(
    features: FeatureResult, *, label: float, source: DataSource, label_origin: LabelOrigin,
) -> TrainingExample:
    return TrainingExample(vector=features.vector, label=label, source=source, label_origin=label_origin)


def build_pipeline_test_examples_from_baseline(
    feature_results: list[FeatureResult], requests: list,
) -> list[TrainingExample]:
    """Label = the deterministic baseline estimate for that request, when
    computable (quantity and unit_price_inr both known). Forces
    source=SYNTHETIC_DEV/label_origin=BASELINE_HEURISTIC regardless of
    anything else - a baseline-derived label is never real evidence about
    actual prices. Requests with neither a computable baseline nor an
    observed total are skipped: an unknown value cannot be a label.
    """
    out = []
    for fr, request in zip(feature_results, requests):
        pred = baseline_estimate(request)
        if pred.is_unknown or pred.method.value == "observed":
            # An OBSERVED total is real data, not a baseline-derived pseudo-label - excluded here on
            # purpose; feeding it in would also require deciding a (non-synthetic) source, which this
            # pipeline-test builder is not set up to do responsibly.
            continue
        out.append(make_training_example(fr, label=pred.value, source=DataSource.SYNTHETIC_DEV,
                                         label_origin=LabelOrigin.BASELINE_HEURISTIC))
    return out


def train(
    examples: list[TrainingExample], *, purpose: TrainingPurpose, seed: int = 42,
    validation_fraction: float = 0.2, model_params: dict | None = None,
) -> TravelCostModel:
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
    return TravelCostModel(result.sklearn_model, metadata)


def evaluate(model: TravelCostModel, examples: list[TrainingExample]) -> dict[str, float]:
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
