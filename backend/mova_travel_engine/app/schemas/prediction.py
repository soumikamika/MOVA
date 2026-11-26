"""Shared result type for every predictive service (travel_time, travel_cost, ...).

Confidence here is a data-completeness/provenance signal - "how much do we
actually know" - NEVER a claim about model accuracy. See each service's
`confidence.py`/module docstring for the exact rule it applies. A Prediction
with `is_unknown=True` carries no numeric claim at all: `value` is None and
downstream code (constraint engine, optimizer) MUST treat it as missing data,
not as zero or an average.
"""
import datetime as dt
from enum import StrEnum

from pydantic import Field, model_validator

from app.schemas.common import ConfidenceLevel, DataSource, MovaModel


class PredictionMethod(StrEnum):
    UNKNOWN = "unknown"        # no data to predict from at all
    OBSERVED = "observed"      # the value came directly from a data record, not a calculation
    BASELINE = "baseline"      # a transparent, documented formula over known quantities
    ML_MODEL = "ml_model"      # a trained production model (see TrainingPurpose.PRODUCTION)


class Prediction(MovaModel):
    prediction_type: str = Field(min_length=1)   # e.g. "travel_time_minutes", "cost_transport_inr"
    unit: str = Field(min_length=1)              # e.g. "minutes", "inr"
    method: PredictionMethod

    value: float | None = None            # None iff is_unknown
    lower_bound: float | None = None
    upper_bound: float | None = None

    is_estimated: bool = True   # False only for a directly OBSERVED value; True for baseline/ml_model
    is_unknown: bool = False    # True -> value/bounds MUST all be None; see the validator below

    confidence: ConfidenceLevel = ConfidenceLevel.UNKNOWN
    source: DataSource | None = None       # provenance of the underlying data, when applicable
    model_version: str | None = None       # set only when method == ML_MODEL
    last_updated: dt.datetime | None = None
    notes: list[str] = Field(default_factory=list)  # short, factual caveats (e.g. "distance unknown")

    @model_validator(mode="after")
    def _unknown_is_consistent(self) -> "Prediction":
        if self.is_unknown:
            if self.value is not None or self.lower_bound is not None or self.upper_bound is not None:
                raise ValueError("is_unknown=True requires value/lower_bound/upper_bound to all be None")
            if self.method != PredictionMethod.UNKNOWN:
                raise ValueError("is_unknown=True requires method=PredictionMethod.UNKNOWN")
        elif self.method == PredictionMethod.UNKNOWN:
            raise ValueError("method=PredictionMethod.UNKNOWN requires is_unknown=True")
        elif self.value is None:
            raise ValueError("value is required unless is_unknown=True")
        if self.lower_bound is not None and self.value is not None and self.lower_bound > self.value:
            raise ValueError("lower_bound cannot exceed value")
        if self.upper_bound is not None and self.value is not None and self.upper_bound < self.value:
            raise ValueError("upper_bound cannot be below value")
        if self.method != PredictionMethod.OBSERVED and self.is_estimated is False:
            raise ValueError("is_estimated=False is only valid for method=PredictionMethod.OBSERVED")
        if self.method == PredictionMethod.ML_MODEL and self.model_version is None:
            raise ValueError("model_version is required when method=PredictionMethod.ML_MODEL")
        return self

    @classmethod
    def unknown(cls, prediction_type: str, unit: str, *, notes: list[str] | None = None) -> "Prediction":
        """The explicit 'we do not know' result - never fabricate a number instead of this."""
        return cls(prediction_type=prediction_type, unit=unit, method=PredictionMethod.UNKNOWN,
                   is_estimated=True, is_unknown=True, confidence=ConfidenceLevel.UNKNOWN,
                   notes=notes or [])
