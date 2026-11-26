"""Deterministic feature extraction: CostRequest -> facts + a numeric vector.

`total_known_price_inr` is DELIBERATELY excluded from the vector: it is either
the value we are trying to predict (when unknown) or an already-final observed
answer (when known, in which case no prediction is needed at all - see
baseline.py). Including it as a model input would leak the label into the
feature set and be meaningless at real inference time. Unknown request fields
(quantity, unit_price_inr) become NaN, never a guessed value.
"""
import math
from dataclasses import dataclass

from app.schemas.common import MovaModel
from app.schemas.logistics import CostCategory, CostRequest

NAN = math.nan


class CostFacts(MovaModel):
    category: CostCategory
    travellers: int
    quantity: float | None
    unit_price_inr: float | None
    total_known_price_inr: float | None


@dataclass(frozen=True)
class FeatureResult:
    facts: CostFacts
    vector: dict[str, float]


_CONTINUOUS_FEATURES = ("quantity", "unit_price_inr", "travellers")
_CATEGORY_FEATURES = tuple(f"category_{c.value}" for c in CostCategory)

FEATURE_NAMES: tuple[str, ...] = _CONTINUOUS_FEATURES + _CATEGORY_FEATURES


def vectorize(vector: dict[str, float]) -> list[float]:
    return [vector[name] for name in FEATURE_NAMES]


def extract_features(request: CostRequest) -> FeatureResult:
    facts = CostFacts(
        category=request.category, travellers=request.travellers, quantity=request.quantity,
        unit_price_inr=request.unit_price_inr, total_known_price_inr=request.total_known_price_inr,
    )
    vector: dict[str, float] = {
        "quantity": request.quantity if request.quantity is not None else NAN,
        "unit_price_inr": request.unit_price_inr if request.unit_price_inr is not None else NAN,
        "travellers": float(request.travellers),
    }
    for c in CostCategory:
        vector[f"category_{c.value}"] = 1.0 if request.category == c else 0.0
    return FeatureResult(facts=facts, vector=vector)
