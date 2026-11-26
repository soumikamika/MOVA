"""Generic trained-model wrapper: bounded prediction + save/load with
schema-drift protection. Each domain (recommendation, travel_time,
travel_cost) subclasses this, pinning its own canonical feature universe and
output bounds - see app/recommendation/model.py for the reference subclass.
"""
from pathlib import Path
from typing import Any

import joblib
import numpy as np
import sklearn

from app.core.exceptions import ModelLoadError
from app.ml.model_metadata import ModelMetadata

ARTIFACT_KEYS = {"sklearn_model", "metadata", "canonical_feature_names"}


def sklearn_version() -> str:
    return sklearn.__version__


class BaseTrainedModel:
    #: Set by each subclass to its domain's full FEATURE_NAMES tuple (features.py).
    canonical_feature_names: tuple[str, ...] = ()
    #: Set by each subclass to the valid output range for predict(), e.g. (0.0, 1.0).
    output_bounds: tuple[float, float] | None = None

    def __init__(self, sklearn_model: Any, metadata: ModelMetadata):
        self.sklearn_model = sklearn_model
        self.metadata = metadata

    def predict_one(self, vector: dict[str, float]) -> float:
        return self.predict_many([vector])[0]

    def predict_many(self, vectors: list[dict[str, float]]) -> list[float]:
        if not vectors:
            return []
        names = self.metadata.used_feature_names
        x = np.array([[v[n] for n in names] for v in vectors], dtype=float)
        raw = self.sklearn_model.predict(x)
        if self.output_bounds is not None:
            lo, hi = self.output_bounds
            return [float(min(hi, max(lo, v))) for v in raw]
        return [float(v) for v in raw]

    def save(self, path: Path | str) -> None:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        joblib.dump(
            {"sklearn_model": self.sklearn_model,
             # exclude computed fields (is_production, real_example_count): they are derived, and re-loading
             # them as plain input would hit extra="forbid" (MovaModel) since they aren't real fields.
             "metadata": self.metadata.model_dump(mode="json", exclude={"is_production", "real_example_count"}),
             "canonical_feature_names": list(self.canonical_feature_names)},
            path,
        )

    @classmethod
    def load(cls, path: Path | str) -> "BaseTrainedModel":
        path = Path(path)
        if not path.exists():
            raise ModelLoadError(f"model artifact not found: {path}", details={"path": str(path)})
        try:
            payload = joblib.load(path)
        except Exception as exc:  # corrupt/foreign file - never crash the caller with a raw pickle error
            raise ModelLoadError(f"could not read model artifact {path}: {exc}", details={"path": str(path)}) from exc
        if not isinstance(payload, dict) or not ARTIFACT_KEYS <= payload.keys():
            raise ModelLoadError(f"{path} is not a recognised MOVA model artifact", details={"path": str(path)})
        if list(payload["canonical_feature_names"]) != list(cls.canonical_feature_names):
            raise ModelLoadError(
                f"{path} was trained against a different feature schema than the one currently in use; retrain it",
                details={"path": str(path)},
            )
        metadata = ModelMetadata.model_validate(payload["metadata"])
        if not set(metadata.used_feature_names) <= set(cls.canonical_feature_names):
            raise ModelLoadError(
                f"{path}'s recorded used_feature_names are not a subset of the current feature schema; retrain it",
                details={"path": str(path)},
            )
        return cls(payload["sklearn_model"], metadata)
