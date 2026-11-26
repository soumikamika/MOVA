"""Deterministic feature extraction: TravelTimeRequest -> facts + a numeric vector.

Same discipline as app.recommendation.features: unknown request fields
(distance_km, departure_time, weekday/date, num_transfers) become NaN in the
vector, NEVER a guessed value. `TravelTimeFacts` mirrors the request in a form
convenient for baseline.py/service.py notes.
"""
import math
from dataclasses import dataclass

from app.schemas.common import MovaModel, TransportMode
from app.schemas.logistics import TravelTimeRequest
from app.utils.time import to_minutes

NAN = math.nan


class TravelTimeFacts(MovaModel):
    origin: str
    destination: str
    mode: TransportMode
    distance_km: float | None
    departure_hour: int | None
    weekday: int | None
    month: int | None
    num_transfers: int | None


@dataclass(frozen=True)
class FeatureResult:
    facts: TravelTimeFacts
    vector: dict[str, float]


_CONTINUOUS_FEATURES = ("distance_km", "departure_hour", "weekday", "month", "num_transfers")
_MODE_FEATURES = tuple(f"mode_{m.value}" for m in TransportMode)

FEATURE_NAMES: tuple[str, ...] = _CONTINUOUS_FEATURES + _MODE_FEATURES


def vectorize(vector: dict[str, float]) -> list[float]:
    return [vector[name] for name in FEATURE_NAMES]


def extract_features(request: TravelTimeRequest) -> FeatureResult:
    departure_hour = (to_minutes(request.departure_time) // 60) if request.departure_time is not None else None
    weekday = request.weekday if request.weekday is not None else (
        request.date.weekday() if request.date is not None else None
    )
    month = request.date.month if request.date is not None else None

    facts = TravelTimeFacts(
        origin=request.origin, destination=request.destination, mode=request.mode,
        distance_km=request.distance_km, departure_hour=departure_hour, weekday=weekday,
        month=month, num_transfers=request.num_transfers,
    )

    vector: dict[str, float] = {
        "distance_km": request.distance_km if request.distance_km is not None else NAN,
        "departure_hour": float(departure_hour) if departure_hour is not None else NAN,
        "weekday": float(weekday) if weekday is not None else NAN,
        "month": float(month) if month is not None else NAN,
        "num_transfers": float(request.num_transfers) if request.num_transfers is not None else NAN,
    }
    for m in TransportMode:
        vector[f"mode_{m.value}"] = 1.0 if request.mode == m else 0.0

    return FeatureResult(facts=facts, vector=vector)
