"""Shared training-safety rules for every trainer in this project.

The rule, unchanged since Phase C: a PRODUCTION model may only be trained once
enough REAL-sourced examples exist (source in real/user_generated/
external_api). synthetic_dev/mock examples may be used for
TrainingPurpose.PIPELINE_TEST, which exercises the training/inference pipeline
but is never used by a service to score/predict real results (see each
service.py's engine_status()/model gating).
"""
from collections import Counter
from enum import StrEnum

from app.schemas.common import DataSource

# A conservative development default, not the output of a formal power
# analysis - there is no real dataset yet to base one on. Shared across every
# domain (recommendation, travel_time, travel_cost) so the bar is consistent.
MIN_PRODUCTION_EXAMPLES = 500

REAL_SOURCES = frozenset({DataSource.REAL, DataSource.USER_GENERATED, DataSource.EXTERNAL_API})


class TrainingPurpose(StrEnum):
    PIPELINE_TEST = "pipeline_test"  # dev-only: proves the training/inference pipeline works end to end
    PRODUCTION = "production"        # trained on enough real-sourced data to be used for real predictions


def source_counts(examples) -> dict[str, int]:
    """examples: anything with a `.source` (a DataSource) attribute."""
    return {k.value: v for k, v in Counter(e.source for e in examples).items()}


def real_count(examples) -> int:
    return sum(1 for e in examples if e.source in REAL_SOURCES)
