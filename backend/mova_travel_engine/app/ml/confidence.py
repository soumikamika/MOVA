"""Shared, honest confidence heuristic for predictive services.

`confidence` on a Prediction/Recommendation is a DATA-COMPLETENESS signal -
"how much of the relevant input do we actually have" - never a claim about
model accuracy, which this project has no validated way to measure yet (no
real evaluation data exists for any of Phase C/D's domains).
"""
from app.schemas.common import ConfidenceLevel


def completeness_confidence(known_count: int, medium_threshold: int = 2) -> ConfidenceLevel:
    """known_count = how many of the relevant optional inputs are actually known.
    Reaching `medium_threshold` known values gives MEDIUM; otherwise LOW.
    HIGH is reserved for directly OBSERVED values, decided by the caller, not here.
    """
    return ConfidenceLevel.MEDIUM if known_count >= medium_threshold else ConfidenceLevel.LOW
