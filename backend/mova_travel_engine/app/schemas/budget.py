"""Budget, cost breakdown, budget status and cost estimates."""
from enum import StrEnum

from pydantic import Field, computed_field, model_validator

from app.core.constants import DEFAULT_CURRENCY, MAX_BUDGET_INR, MAX_TRAVELLERS
from app.schemas.common import ConfidenceLevel, DataSource, MovaModel


class CostBreakdown(MovaModel):
    """Absolute INR amounts for the whole party, by category."""

    transport: float = Field(default=0, ge=0)        # intercity
    hotel: float = Field(default=0, ge=0)
    food: float = Field(default=0, ge=0)
    activities: float = Field(default=0, ge=0)
    local_transport: float = Field(default=0, ge=0)
    miscellaneous: float = Field(default=0, ge=0)
    buffer: float = Field(default=0, ge=0)           # emergency buffer

    @computed_field
    @property
    def total(self) -> float:
        return round(
            self.transport + self.hotel + self.food + self.activities
            + self.local_transport + self.miscellaneous + self.buffer,
            2,
        )


class Budget(MovaModel):
    total_inr: float = Field(gt=0, le=MAX_BUDGET_INR)
    travellers: int = Field(ge=1, le=MAX_TRAVELLERS)
    currency: str = DEFAULT_CURRENCY

    @computed_field
    @property
    def per_traveller_inr(self) -> float:
        return round(self.total_inr / self.travellers, 2)


class BudgetStatus(MovaModel):
    """Result of comparing an estimate to a budget.

    remaining_inr is SIGNED (negative when over budget); overrun_inr is >= 0.
    """

    budget_inr: float
    estimated_total_inr: float
    remaining_inr: float
    overrun_inr: float
    per_traveller_inr: float
    utilisation: float  # estimated / budget; > 1.0 means over budget
    is_over_budget: bool
    breakdown: CostBreakdown

    @classmethod
    def evaluate(cls, budget: Budget, breakdown: CostBreakdown) -> "BudgetStatus":
        est = breakdown.total
        overrun = round(max(0.0, est - budget.total_inr), 2)
        return cls(
            budget_inr=budget.total_inr,
            estimated_total_inr=est,
            remaining_inr=round(budget.total_inr - est, 2),
            overrun_inr=overrun,
            per_traveller_inr=round(est / budget.travellers, 2),
            utilisation=round(est / budget.total_inr, 4),
            is_over_budget=overrun > 0,
            breakdown=breakdown,
        )


class EstimationMethod(StrEnum):
    RULE_BASED = "rule_based"  # deterministic baseline from price data
    ML_MODEL = "ml_model"
    HYBRID = "hybrid"


class CostEstimate(MovaModel):
    """A cost prediction that states how much it can be trusted.

    Bounds / MAE are None unless they come from real evaluation - we never
    fabricate an interval to look precise. confidence defaults to UNKNOWN.
    """

    breakdown: CostBreakdown
    method: EstimationMethod
    lower_bound_inr: float | None = Field(default=None, ge=0)
    upper_bound_inr: float | None = Field(default=None, ge=0)
    typical_error_mae_inr: float | None = Field(default=None, ge=0)  # from held-out evaluation
    confidence: ConfidenceLevel = ConfidenceLevel.UNKNOWN
    data_sources: list[DataSource] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)

    @computed_field
    @property
    def total_inr(self) -> float:
        return self.breakdown.total

    @model_validator(mode="after")
    def _bounds_ordered(self) -> "CostEstimate":
        total = self.breakdown.total
        if self.lower_bound_inr is not None and self.lower_bound_inr > total:
            raise ValueError("lower_bound_inr cannot exceed the estimated total")
        if self.upper_bound_inr is not None and self.upper_bound_inr < total:
            raise ValueError("upper_bound_inr cannot be below the estimated total")
        return self
