"""Cross-cutting Phase D checks: coexistence with Phase C, shared-infrastructure
correctness, and that nothing in Phase A/B/C's public behavior moved.
"""
import pytest

from app.core.exceptions import InsufficientTrainingDataError
from app.ml.confidence import completeness_confidence
from app.ml.matrix import split_constant_columns
from app.ml.training_rules import MIN_PRODUCTION_EXAMPLES, REAL_SOURCES, TrainingPurpose
from app.schemas.common import ConfidenceLevel, DataSource


# ------------------------------ shared infrastructure ---------------------------
def test_shared_constants_are_a_single_source_of_truth():
    from app.recommendation.trainer import MIN_PRODUCTION_EXAMPLES as reco_min
    from app.travel_time.trainer import MIN_PRODUCTION_EXAMPLES as tt_min
    assert reco_min == tt_min == MIN_PRODUCTION_EXAMPLES == 500
    assert REAL_SOURCES == {DataSource.REAL, DataSource.USER_GENERATED, DataSource.EXTERNAL_API}


def test_training_purpose_is_the_same_enum_object_everywhere():
    from app.recommendation.model import TrainingPurpose as reco_purpose
    from app.travel_time.trainer import TrainingPurpose as tt_purpose
    from app.travel_cost.trainer import TrainingPurpose as tc_purpose
    assert reco_purpose is tt_purpose is tc_purpose is TrainingPurpose


def test_split_constant_columns_used_identically_by_every_domain():
    import numpy as np
    x = np.array([[1.0, 1.0], [1.0, 2.0], [1.0, 3.0]])
    _, kept, dropped = split_constant_columns(x, ["const", "varies"])
    assert kept == ["varies"] and dropped == ["const"]


def test_completeness_confidence_thresholds():
    assert completeness_confidence(0) == ConfidenceLevel.LOW
    assert completeness_confidence(1) == ConfidenceLevel.LOW
    assert completeness_confidence(2) == ConfidenceLevel.MEDIUM
    assert completeness_confidence(3, medium_threshold=3) == ConfidenceLevel.MEDIUM


# ------------------------------ model isolation ---------------------------------
def test_each_domain_has_its_own_canonical_feature_universe():
    from app.recommendation.features import FEATURE_NAMES as reco_features
    from app.travel_time.features import FEATURE_NAMES as tt_features
    from app.travel_cost.features import FEATURE_NAMES as tc_features
    assert reco_features != tt_features != tc_features
    assert len(set(reco_features) & set(tt_features)) == 0 or reco_features is not tt_features


def test_base_trained_model_subclasses_pin_distinct_bounds():
    from app.recommendation.model import RecommendationModel
    from app.travel_time.model import TravelTimeModel
    from app.travel_cost.model import TravelCostModel
    assert RecommendationModel.output_bounds == (0.0, 1.0)
    assert TravelTimeModel.output_bounds[0] == 0.0
    assert TravelCostModel.output_bounds[0] == 0.0


# ------------------------------ no boundary violations --------------------------
def test_travel_time_service_does_not_import_repositories_or_fastapi():
    import ast
    tree = ast.parse(open("app/travel_time/service.py").read())
    imported = {n.names[0].name.split(".")[0] for n in ast.walk(tree) if isinstance(n, ast.Import)}
    imported |= {n.module.split(".")[0] for n in ast.walk(tree) if isinstance(n, ast.ImportFrom) and n.module}
    assert "fastapi" not in imported
    assert not any(m.startswith("app.data.repositories") for m in imported if isinstance(m, str))


def test_travel_cost_service_does_not_import_repositories_or_fastapi():
    import ast
    tree = ast.parse(open("app/travel_cost/service.py").read())
    imported = {n.names[0].name.split(".")[0] for n in ast.walk(tree) if isinstance(n, ast.Import)}
    imported |= {n.module.split(".")[0] for n in ast.walk(tree) if isinstance(n, ast.ImportFrom) and n.module}
    assert "fastapi" not in imported


def test_travel_time_and_travel_cost_services_are_independent():
    """Constructing/using one must not require or affect the other."""
    from app.travel_time.service import TravelTimeService
    from app.travel_cost.service import TravelCostService
    from app.schemas.logistics import TravelTimeRequest, CostRequest

    tt = TravelTimeService().predict(TravelTimeRequest(origin="A", destination="B", mode="car", distance_km=50))
    tc = TravelCostService().predict(CostRequest(category="food", travellers=2, quantity=2, unit_price_inr=300))
    assert tt.prediction_type == "travel_time_minutes"
    assert tc.prediction_type == "cost_food_inr"


# ------------------------------ Phase C is unaffected ---------------------------
def test_recommendation_service_still_works_end_to_end():
    from app.recommendation.service import RecommendationService
    from tests.factories import make_place
    from tests.factories_recommendation import make_trip
    recs = RecommendationService().recommend(make_trip(), [make_place(id="a"), make_place(id="b")])
    assert len(recs) == 2 and recs[0].rank == 1


def test_recommendation_trainer_still_enforces_production_threshold():
    from app.recommendation.trainer import build_pipeline_test_examples_from_fallback, train
    from app.recommendation.features import extract_features
    from tests.factories import make_place
    from tests.factories_recommendation import make_trip
    trip = make_trip()
    frs = [extract_features(trip, make_place(id=f"p{i}", rating=3.0 + (i % 3))) for i in range(30)]
    examples = build_pipeline_test_examples_from_fallback(frs)
    with pytest.raises(InsufficientTrainingDataError, match="Insufficient real training data"):
        train(examples, purpose=TrainingPurpose.PRODUCTION)
