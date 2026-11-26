"""Training interface: labelled examples -> evaluated RecommendationModel.

Data flow:  examples -> vectorize -> train/validation split -> fit -> evaluate
            -> ModelMetadata -> RecommendationModel (in memory; save() persists it)

The hard rule this module enforces: a PRODUCTION model may only be trained
when enough REAL-sourced examples exist (source in real/user_generated/
external_api). Until MOVA has real interaction data, requesting
TrainingPurpose.PRODUCTION always raises InsufficientTrainingDataError - this
is intentional, not a bug. TrainingPurpose.PIPELINE_TEST exists so the rest of
the pipeline (vectorization, fit, evaluation, save/load, service integration)
can be exercised and tested before real data exists, and every such model is
labelled, in its own metadata, as not for production use.

The actual sklearn fit/evaluate routine (including the constant-column guard)
is shared across every domain trainer - see app.ml.trainer_core.fit_regressor.
"""
import datetime as dt
from collections import Counter
from enum import StrEnum

import numpy as np
from pydantic import Field
from sklearn.metrics import mean_absolute_error, r2_score

from app.core.exceptions import InsufficientTrainingDataError
from app.ml.matrix import MIN_DISTINCT_VALUES, split_constant_columns  # re-exported for backward compatibility
from app.ml.trainer_core import fit_regressor
from app.ml.training_rules import (
    MIN_PRODUCTION_EXAMPLES, REAL_SOURCES, TrainingPurpose, real_count as _shared_real_count,
    source_counts as _shared_source_counts,
)
from app.recommendation.fallback import score_place
from app.recommendation.features import FEATURE_NAMES, FeatureResult
from app.recommendation.model import ModelMetadata, RecommendationModel, sklearn_version
from app.schemas.common import DataSource, MovaModel

# Recommendation-specific threshold (travel_time/travel_cost define their own).
MIN_PIPELINE_TEST_EXAMPLES = 20

_NON_PRODUCTION_NOTE = (
    "PIPELINE-TEST MODEL: trained on non-production data (see source_counts / label_origins). "
    "This is NOT trained travel intelligence and must not be presented as one - it exists only to "
    "test the training and inference pipeline."
)


class LabelOrigin(StrEnum):
    FALLBACK_HEURISTIC = "fallback_heuristic"  # label = the deterministic fallback score, NOT a real preference
    HUMAN_FEEDBACK = "human_feedback"          # explicit user rating/feedback on a recommendation
    BOOKING_OUTCOME = "booking_outcome"        # derived from what the traveller actually did (booked/skipped/...)
    EXPLICIT_RATING = "explicit_rating"        # a direct place rating tied to a specific traveller/trip


class TrainingExample(MovaModel):
    place_id: str = Field(min_length=1)
    vector: dict[str, float]
    label: float = Field(ge=0, le=1)
    source: DataSource            # provenance of the LABEL, never upgraded/downgraded by this module
    label_origin: LabelOrigin


def make_training_example(
    features: FeatureResult, *, label: float, source: DataSource, label_origin: LabelOrigin,
) -> TrainingExample:
    return TrainingExample(place_id=features.facts.place_id, vector=features.vector,
                           label=label, source=source, label_origin=label_origin)


def build_pipeline_test_examples_from_fallback(feature_results: list[FeatureResult]) -> list[TrainingExample]:
    """Label = the deterministic fallback score for that (trip, place) pair.

    This produces internally-consistent data to exercise the training/serving
    pipeline (vectorization, fit, save/load, prediction) end to end. It teaches
    a model to approximate the fallback FORMULA, not real traveller
    preferences, so every example is forced to source=SYNTHETIC_DEV /
    label_origin=FALLBACK_HEURISTIC regardless of the underlying place's own
    `source` - a fallback-derived label is never real evidence, even about a
    real place.
    """
    out = []
    for fr in feature_results:
        label = score_place(fr.facts).score
        out.append(make_training_example(fr, label=label, source=DataSource.SYNTHETIC_DEV,
                                         label_origin=LabelOrigin.FALLBACK_HEURISTIC))
    return out


def _source_counts(examples: list[TrainingExample]) -> dict[str, int]:
    return _shared_source_counts(examples)


def _label_origin_counts(examples: list[TrainingExample]) -> dict[str, int]:
    return {k.value: v for k, v in Counter(e.label_origin for e in examples).items()}


def _real_count(examples: list[TrainingExample]) -> int:
    return _shared_real_count(examples)


def train(
    examples: list[TrainingExample], *, purpose: TrainingPurpose, seed: int = 42,
    validation_fraction: float = 0.2, model_params: dict | None = None,
) -> RecommendationModel:
    result = fit_regressor(
        [e.vector for e in examples], [e.label for e in examples], [e.source for e in examples],
        feature_names=list(FEATURE_NAMES), purpose=purpose, seed=seed, validation_fraction=validation_fraction,
        min_production_examples=MIN_PRODUCTION_EXAMPLES, min_pipeline_test_examples=MIN_PIPELINE_TEST_EXAMPLES,
        model_params=model_params, non_production_note=_NON_PRODUCTION_NOTE,
    )
    metadata = ModelMetadata(
        purpose=purpose, trained_at=dt.datetime.now(dt.timezone.utc), n_examples=result.n_examples,
        source_counts=_source_counts(examples), label_origins=_label_origin_counts(examples),
        used_feature_names=result.used_names, dropped_feature_names=result.dropped_names, metrics=result.metrics,
        sklearn_version=sklearn_version(), model_class=type(result.sklearn_model).__name__, seed=seed,
        notes=result.notes,
    )
    return RecommendationModel(result.sklearn_model, metadata)


def evaluate(model: RecommendationModel, examples: list[TrainingExample]) -> dict[str, float]:
    """Re-evaluate an already-trained model against a (possibly different) example set."""
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
