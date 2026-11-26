"""Deterministic, transparent cost baseline - NOT machine learning, and never
an invented price.

Three outcomes only:
  1. `total_known_price_inr` given  -> method=OBSERVED, is_estimated=False.
     This is real, already-known data (e.g. a booked hotel's actual total), so
     confidence is HIGH - not because of a model, but because nothing was
     estimated at all.
  2. `quantity` AND `unit_price_inr` given -> method=BASELINE, a single
     auditable multiplication (e.g. nights x nightly rate, or
     distance_km x per-km rate). confidence is LOW: the arithmetic is exact,
     but the inputs themselves are user/caller-supplied assumptions, not a
     validated model.
  3. Otherwise -> Prediction.unknown(...). No guessing, ever.
"""
from app.schemas.common import ConfidenceLevel
from app.schemas.logistics import CostRequest
from app.schemas.prediction import Prediction, PredictionMethod


def _prediction_type(request: CostRequest) -> str:
    return f"cost_{request.category.value}_inr"


def estimate(request: CostRequest) -> Prediction:
    ptype = _prediction_type(request)

    if request.total_known_price_inr is not None:
        return Prediction(
            prediction_type=ptype, unit="inr", method=PredictionMethod.OBSERVED,
            value=request.total_known_price_inr, is_estimated=False, is_unknown=False,
            confidence=ConfidenceLevel.HIGH,
            notes=["This is an already-known/observed price, not a calculation or estimate."],
        )

    if request.quantity is not None and request.unit_price_inr is not None:
        value = round(request.quantity * request.unit_price_inr, 2)
        return Prediction(
            prediction_type=ptype, unit="inr", method=PredictionMethod.BASELINE,
            value=value, is_estimated=True, is_unknown=False, confidence=ConfidenceLevel.LOW,
            notes=[f"Computed as quantity ({request.quantity}) x unit_price_inr ({request.unit_price_inr}); "
                  "not validated against real prices."],
        )

    missing = [name for name, val in (("quantity", request.quantity), ("unit_price_inr", request.unit_price_inr))
              if val is None]
    return Prediction.unknown(ptype, "inr", notes=[
        f"Missing required input(s) for a baseline calculation: {', '.join(missing)}.",
    ])
