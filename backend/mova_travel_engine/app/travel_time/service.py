"""predict(request) -> Prediction.

Independent of any repository, provider, or FastAPI layer - a future routes
provider or FastAPI endpoint calls this with a TravelTimeRequest it built
itself. Scoring method choice mirrors app.recommendation.service: a loaded
model is only used when its metadata says purpose=PRODUCTION; until real
travel-time observations exist, no production model can be trained (see
trainer.py), so this always uses the deterministic baseline today. A loaded
pipeline_test model is visible via engine_status() but never used to answer
predict() - presenting its output as a real travel-time prediction would
misrepresent a synthetic-data pipeline test as travel intelligence.
"""
from dataclasses import dataclass

from app.ml.confidence import completeness_confidence
from app.schemas.logistics import TravelTimeRequest
from app.schemas.prediction import Prediction, PredictionMethod
from app.travel_time import baseline
from app.travel_time.features import extract_features
from app.travel_time.model import TravelTimeModel


@dataclass
class EngineStatus:
    scoring_method: PredictionMethod
    model_loaded: bool
    model_is_production: bool
    model_notes: list[str]


class TravelTimeService:
    def __init__(self, model: TravelTimeModel | None = None):
        self._model = model

    @property
    def model(self) -> TravelTimeModel | None:
        return self._model

    def engine_status(self) -> EngineStatus:
        using_model = self._model is not None and self._model.metadata.is_production
        return EngineStatus(
            scoring_method=PredictionMethod.ML_MODEL if using_model else PredictionMethod.BASELINE,
            model_loaded=self._model is not None,
            model_is_production=bool(self._model and self._model.metadata.is_production),
            model_notes=list(self._model.metadata.notes) if self._model else [],
        )

    def predict(self, request: TravelTimeRequest) -> Prediction:
        use_model = self._model is not None and self._model.metadata.is_production
        if not use_model:
            return baseline.estimate(request)

        fr = extract_features(request)
        known = sum(x is not None for x in (fr.facts.distance_km, fr.facts.departure_hour, fr.facts.weekday))
        value = self._model.predict_one(fr.vector)
        return Prediction(
            prediction_type="travel_time_minutes", unit="minutes", method=PredictionMethod.ML_MODEL,
            value=round(value, 1), is_estimated=True, is_unknown=False,
            confidence=completeness_confidence(known), model_version=self._model.metadata.model_class,
            notes=["Produced by a trained production model."],
        )
