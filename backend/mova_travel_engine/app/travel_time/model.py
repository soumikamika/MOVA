"""ML side of travel-time prediction: a thin subclass of the shared
BaseTrainedModel (see app.ml.base_model and app.recommendation.model for the
original, more heavily-documented rationale for this model family).

Model choice: HistGradientBoostingRegressor, for the same reasons as Phase C -
native NaN handling (distance/departure time/weekday are often unknown), no
deep learning, fast to train on this data size. Predictions are bounded to
[0, inf): a travel time cannot be negative, and there is no fixed upper bound.
"""
from app.ml.base_model import BaseTrainedModel
from app.travel_time.features import FEATURE_NAMES


class TravelTimeModel(BaseTrainedModel):
    canonical_feature_names = FEATURE_NAMES
    output_bounds = (0.0, float("inf"))
