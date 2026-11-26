"""The ML side of Phase C: a thin, honest wrapper around one scikit-learn model.

Model choice: HistGradientBoostingRegressor.
  * Handles missing values (NaN) in numeric features NATIVELY - during training
    it learns, per split, which direction a missing value should go. This
    matters a lot here: Place attributes like rating/popularity/entry_fee are
    frequently None ("unknown"), and Phase B's rule is that unknown must never
    be silently imputed to a fake value. Most alternatives (plain
    RandomForest, linear models) require imputation first, which would violate
    that rule.
  * Gradient-boosted trees capture the non-linear, interacting signals this
    problem has (e.g. "an interest match matters more when the fee is
    affordable") without manual feature crosses.
  * It is not deep learning, trains in milliseconds on this data size, and its
    behaviour (a regressor bounded to [0, 1] at inference) is easy to reason
    about - important given Phase C's small, currently-synthetic dataset.
  * Trade-off: HistGradientBoostingRegressor gives no simple per-instance
    feature attribution (unlike a linear model's coefficients), which is why
    explain.py builds explanations from directly observed facts instead of
    from the model.

Constant-feature guard (see trainer.py's `split_constant_columns`, now shared
via app.ml.matrix): small or homogeneous training batches routinely produce
feature columns with a single distinct value (e.g. every example sharing one
place category, or one trip's context fields such as
`travellers`/`budget_per_traveller_inr`). Some scikit-learn/numpy version
combinations raise `ValueError: window shape cannot be larger than input array
shape` deep inside histogram-bin-threshold computation when a numeric column
has fewer than two distinct values. Rather than chase that internal edge case
across library versions, trainer.py drops zero-variance columns before fitting
- a column with a single value carries no splitting information for a tree
model anyway, so this is a correct simplification, not a workaround that
changes behaviour. `ModelMetadata.used_feature_names` records exactly which
columns, and in what order, the underlying sklearn model actually expects;
`predict_many()` (in the shared `BaseTrainedModel`) uses that - NOT the full
FEATURE_NAMES universe - to build its input.

This module never decides whether a model is trustworthy - it only trains,
predicts and (de)serialises. trainer.py enforces the real/synthetic data
rules; service.py decides whether a loaded model is used at all.
"""
# Re-exported for backward compatibility: existing code imports these from here.
from app.ml.base_model import sklearn_version  # noqa: F401
from app.ml.model_metadata import ModelMetadata  # noqa: F401
from app.ml.training_rules import TrainingPurpose  # noqa: F401
from app.ml.base_model import BaseTrainedModel
from app.recommendation.features import FEATURE_NAMES


class RecommendationModel(BaseTrainedModel):
    """A trained sklearn regressor plus the metadata needed to use it honestly."""

    canonical_feature_names = FEATURE_NAMES
    output_bounds = (0.0, 1.0)  # suitability_score is always in [0, 1]
