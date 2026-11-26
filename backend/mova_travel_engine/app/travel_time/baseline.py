"""Deterministic, explicit baseline for travel-time - NOT machine learning.

travel_time_minutes = distance_km / assumed_speed_kmh * 60, plus a flat penalty
per known transfer. Every number is a named, documented constant below. This
formula has NOT been calibrated against any real travel-time data, so its
accuracy is unknown - confidence is capped at LOW regardless of how many
optional request fields are known (see the module docstring in
app.ml.confidence for why confidence never claims accuracy).

If `distance_km` is unknown, no baseline can be computed - the service must
return Prediction.unknown(...) rather than fabricate a distance.
"""
from app.schemas.common import ConfidenceLevel
from app.schemas.logistics import TravelTimeRequest
from app.schemas.prediction import Prediction, PredictionMethod

PREDICTION_TYPE = "travel_time_minutes"
UNIT = "minutes"

# Rough assumed average speeds, km/h. These are illustrative planning
# assumptions, not measured averages - e.g. "flight" bundles in typical
# check-in/boarding/taxi overhead as a reduced effective speed rather than
# modelling those phases separately.
BASELINE_SPEED_KMH: dict[str, float] = {
    "flight": 500.0, "train": 60.0, "bus": 40.0, "car": 50.0, "cab": 35.0,
    "two_wheeler": 30.0, "ferry": 25.0, "walk": 5.0,
}

TRANSFER_PENALTY_MINUTES = 20.0  # flat time added per known transfer (waiting/connection)
UNCERTAINTY_FACTOR = 0.25        # lower/upper bound = value * (1 -/+ this); a heuristic spread, not a statistic


def estimate(request: TravelTimeRequest) -> Prediction:
    if request.distance_km is None:
        return Prediction.unknown(PREDICTION_TYPE, UNIT, notes=[
            "distance_km is unknown; a baseline travel time cannot be computed without it.",
        ])

    speed = BASELINE_SPEED_KMH[request.mode.value]
    minutes = (request.distance_km / speed) * 60.0
    if request.num_transfers:
        minutes += request.num_transfers * TRANSFER_PENALTY_MINUTES

    notes = [
        f"Baseline: distance_km / {speed:.0f} km/h (an assumed average for {request.mode.value}) x 60"
        + (f", plus {request.num_transfers} x {TRANSFER_PENALTY_MINUTES:.0f} min transfer penalty."
           if request.num_transfers else "."),
        "This formula is not calibrated against real travel-time observations.",
    ]
    return Prediction(
        prediction_type=PREDICTION_TYPE, unit=UNIT, method=PredictionMethod.BASELINE,
        value=round(minutes, 1), lower_bound=round(minutes * (1 - UNCERTAINTY_FACTOR), 1),
        upper_bound=round(minutes * (1 + UNCERTAINTY_FACTOR), 1),
        is_estimated=True, is_unknown=False, confidence=ConfidenceLevel.LOW, notes=notes,
    )
