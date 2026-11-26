"""ConstraintResult: what ConstraintEngine.validate() returns.

Reuses the existing PlanConflict/ConflictType/Severity schemas (app.schemas
.itinerary / app.schemas.common) rather than inventing a parallel result
shape - a "conflict" here is exactly a PlanConflict, same as the rest of the
project already uses for itinerary problems.
"""
from pydantic import Field

from app.schemas.common import MovaModel
from app.schemas.itinerary import PlanConflict


class ConstraintResult(MovaModel):
    feasible: bool
    conflicts: list[PlanConflict] = Field(default_factory=list)   # HIGH-severity, confirmed violations
    warnings: list[PlanConflict] = Field(default_factory=list)    # lower-severity issues and unknown-data notices
    checked_rules: list[str] = Field(default_factory=list)        # names of every rule that actually ran
