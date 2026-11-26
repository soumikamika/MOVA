"""ML side of cost prediction: a thin subclass of the shared BaseTrainedModel
(see app.recommendation.model for the fuller rationale of this model family).

Model choice: HistGradientBoostingRegressor - native NaN handling (quantity/
unit_price are often unknown), no deep learning. Predictions are bounded to
[0, inf): a cost cannot be negative, and there is no fixed upper bound.
"""
from app.ml.base_model import BaseTrainedModel
from app.travel_cost.features import FEATURE_NAMES


class TravelCostModel(BaseTrainedModel):
    canonical_feature_names = FEATURE_NAMES
    output_bounds = (0.0, float("inf"))
