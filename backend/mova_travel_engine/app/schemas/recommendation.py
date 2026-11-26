from enum import StrEnum

from pydantic import Field

from app.schemas.common import ConfidenceLevel, DataSource, MovaModel


class ScoringMethod(StrEnum):
    ML_MODEL = "ml_model"
    RULE_BASED_FALLBACK = "rule_based_fallback"  # used when no trained model / no data


class Recommendation(MovaModel):
    place_id: str = Field(min_length=1)
    score: float = Field(ge=0, le=1)  # "suitability_score" - NOT a calibrated probability
    rank: int | None = Field(default=None, ge=1)
    reasons: list[str] = Field(default_factory=list)          # human-readable sentences
    score_components: dict[str, float] = Field(default_factory=dict)
    method: ScoringMethod
    model_version: str | None = None

    # Phase C additions (additive; all optional so Phase A callers are unaffected).
    matched_preferences: list[str] = Field(default_factory=list)      # place tags matching trip interests
    conflicting_preferences: list[str] = Field(default_factory=list)  # place tags matching trip dislikes
    supporting_factors: list[str] = Field(default_factory=list)       # machine-readable fact keys, e.g. "season_best"
    data_sources: list[DataSource] = Field(default_factory=list)      # provenance of the place record(s) used
    confidence: ConfidenceLevel = ConfidenceLevel.UNKNOWN              # data-completeness heuristic, not a model metric
