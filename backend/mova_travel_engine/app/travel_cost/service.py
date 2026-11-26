"""predict(request) -> Prediction. Same shape and rationale as
app.travel_time.service - see that module's docstring for the full
gating rationale (production-only model use, baseline-by-default today).
"""
from dataclasses import dataclass

from app.ml.confidence import completeness_confidence
from app.schemas.logistics import CostRequest
from app.schemas.prediction import Prediction, PredictionMethod
from app.travel_cost import baseline
from app.travel_cost.features import extract_features
from app.travel_cost.model import TravelCostModel


@dataclass
class EngineStatus:
    scoring_method: PredictionMethod
    model_loaded: bool
    model_is_production: bool
    model_notes: list[str]


class TravelCostService:
    def __init__(self, model: TravelCostModel | None = None):
        self._model = model

    @property
    def model(self) -> TravelCostModel | None:
        return self._model

    def engine_status(self) -> EngineStatus:
        using_model = self._model is not None and self._model.metadata.is_production
        return EngineStatus(
            scoring_method=PredictionMethod.ML_MODEL if using_model else PredictionMethod.BASELINE,
            model_loaded=self._model is not None,
            model_is_production=bool(self._model and self._model.metadata.is_production),
            model_notes=list(self._model.metadata.notes) if self._model else [],
        )

    def predict(self, request: CostRequest) -> Prediction:
        # An already-known/observed price always wins, model or not - it is real data, not a prediction.
        if request.total_known_price_inr is not None:
            return baseline.estimate(request)

        use_model = self._model is not None and self._model.metadata.is_production
        if not use_model:
            return baseline.estimate(request)

        fr = extract_features(request)
        known = sum(x is not None for x in (fr.facts.quantity, fr.facts.unit_price_inr))
        value = self._model.predict_one(fr.vector)
        return Prediction(
            prediction_type=f"cost_{request.category.value}_inr", unit="inr", method=PredictionMethod.ML_MODEL,
            value=round(value, 2), is_estimated=True, is_unknown=False,
            confidence=completeness_confidence(known), model_version=self._model.metadata.model_class,
            notes=["Produced by a trained production model."],
        )
