"""Shared model-metadata schema for every trained model in this project
(recommendation, travel_time, travel_cost, ...). One definition, reused
everywhere, so the production/pipeline-test distinction and its fields
(source provenance, used/dropped features, metrics) can never drift between
domains.
"""
import datetime as dt

from pydantic import Field, computed_field

from app.ml.training_rules import TrainingPurpose
from app.schemas.common import MovaModel


class ModelMetadata(MovaModel):
    purpose: TrainingPurpose
    trained_at: dt.datetime
    n_examples: int = Field(ge=1)
    source_counts: dict[str, int] = Field(default_factory=dict)     # DataSource.value -> count
    label_origins: dict[str, int] = Field(default_factory=dict)     # domain-specific LabelOrigin.value -> count
    used_feature_names: list[str] = Field(default_factory=list)     # columns actually given to sklearn, in order
    dropped_feature_names: list[str] = Field(default_factory=list)  # canonical features excluded (zero variance)
    metrics: dict[str, float] = Field(default_factory=dict)         # mae, rmse, r2, n_train, n_val, ...
    sklearn_version: str
    model_class: str
    seed: int
    notes: list[str] = Field(default_factory=list)

    @computed_field
    @property
    def is_production(self) -> bool:
        return self.purpose == TrainingPurpose.PRODUCTION

    @computed_field
    @property
    def real_example_count(self) -> int:
        """Examples sourced from real/user_generated/external_api, NEVER synthetic_dev/mock."""
        real_keys = {"real", "user_generated", "external_api"}
        return sum(v for k, v in self.source_counts.items() if k in real_keys)
