"""Deterministic, independently-testable constraint rules.

Each rule takes a ConstraintContext and returns (conflicts, warnings) - two
lists of PlanConflict. A rule NEVER mutates the itinerary and NEVER fabricates
missing data: if a rule cannot be evaluated because required data is unknown
(an opening-hours record is None, an item's cost is None, ...), it reports
that explicitly via a warning rather than silently assuming "open", "free",
or skipping without a trace.

Severity convention used throughout (matches the project's existing
`Severity` enum and the brief's guidance):
    HIGH    -> a confirmed violation; goes into ConstraintResult.conflicts
               and makes the plan infeasible.
    MEDIUM  -> a real but non-blocking issue (density/travel/unknown budget
               data); goes into ConstraintResult.warnings.
    LOW     -> missing non-critical metadata (e.g. unknown opening hours);
               goes into ConstraintResult.warnings.
Only HIGH-severity results are returned as "conflicts"; everything else is a
"warning" - see engine.py for how the two lists are assembled.
"""
from collections.abc import Callable

from app.constraints.context import ConstraintContext
from app.schemas.budget import Budget, BudgetStatus, CostBreakdown
from app.schemas.common import ConflictType, ItemType, Severity
from app.schemas.itinerary import PlanConflict
from app.utils.time import intervals_overlap, to_minutes

RuleResult = tuple[list[PlanConflict], list[PlanConflict]]  # (conflicts, warnings)

DEFAULT_MIN_MEAL_MINUTES = 20
DEFAULT_MAX_DAILY_ACTIVE_MINUTES = 600   # "excessive density": activity + travel minutes in one day
DEFAULT_MAX_DAILY_TRAVEL_MINUTES = 240   # "excessive travel": travel minutes in one day


def _ref(day: int, idx: int) -> str:
    return f"day{day}:item{idx}"


# ---------------------------------------------------------------------------
# 1. Duplicate places
# ---------------------------------------------------------------------------
def rule_duplicate_places(context: ConstraintContext) -> RuleResult:
    """A place scheduled as more than one ACTIVITY anywhere in the plan.
    Revisiting a place is treated as a hard conflict by design (per the
    brief); a future phase could relax this for places explicitly marked
    revisit-friendly."""
    seen: dict[str, str] = {}
    conflicts: list[PlanConflict] = []
    for day_plan in context.itinerary.days:
        for idx, item in enumerate(day_plan.items):
            if item.type != ItemType.ACTIVITY or not item.place_id:
                continue
            ref = _ref(day_plan.day, idx)
            if item.place_id in seen:
                conflicts.append(PlanConflict(
                    type=ConflictType.DUPLICATE_PLACE, severity=Severity.HIGH, day=day_plan.day,
                    item_refs=[seen[item.place_id], ref],
                    message=f"place {item.place_id!r} is scheduled more than once "
                            f"({seen[item.place_id]} and {ref})",
                    details={"place_id": item.place_id},
                ))
            else:
                seen[item.place_id] = ref
    return conflicts, []


# ---------------------------------------------------------------------------
# 2. Overlapping itinerary items
# ---------------------------------------------------------------------------
def rule_overlapping_items(context: ConstraintContext) -> RuleResult:
    conflicts: list[PlanConflict] = []
    for day_plan in context.itinerary.days:
        items = sorted(enumerate(day_plan.items), key=lambda p: to_minutes(p[1].start))
        for (ia, a), (ib, b) in zip(items, items[1:]):
            if intervals_overlap(to_minutes(a.start), to_minutes(a.end), to_minutes(b.start), to_minutes(b.end)):
                ref_a, ref_b = _ref(day_plan.day, ia), _ref(day_plan.day, ib)
                conflicts.append(PlanConflict(
                    type=ConflictType.OVERLAP, severity=Severity.HIGH, day=day_plan.day, item_refs=[ref_a, ref_b],
                    message=f"{ref_a} ({a.start}-{a.end}) overlaps {ref_b} ({b.start}-{b.end})",
                ))
    return conflicts, []


# ---------------------------------------------------------------------------
# 3. Opening hours - confirmed-closed is a conflict; UNKNOWN hours is a
#    warning, never silently treated as open.
# ---------------------------------------------------------------------------
def rule_opening_hours(context: ConstraintContext) -> RuleResult:
    conflicts: list[PlanConflict] = []
    warnings: list[PlanConflict] = []
    for day_plan in context.itinerary.days:
        weekday = day_plan.date.weekday()
        for idx, item in enumerate(day_plan.items):
            ref = _ref(day_plan.day, idx)
            record = None
            if item.type == ItemType.ACTIVITY and item.place_id:
                record = context.places.get(item.place_id)
            elif item.type == ItemType.MEAL and item.restaurant_id:
                record = context.restaurants.get(item.restaurant_id)
            if record is None:
                continue  # an unresolvable reference is rule_invalid_place_references' concern, not this rule's

            if record.opening_hours is None:
                warnings.append(PlanConflict(
                    type=ConflictType.MISSING_DATA, severity=Severity.LOW, day=day_plan.day, item_refs=[ref],
                    message=f"{ref}: opening hours for {record.name!r} are unknown; this visit's feasibility "
                            "could not be confirmed (not assumed open)",
                    details={"place_id": getattr(record, "id", None)},
                ))
                continue

            s, e = to_minutes(item.start), to_minutes(item.end)
            if not record.opening_hours.is_open(weekday, s, e):
                conflicts.append(PlanConflict(
                    type=ConflictType.OPENING_HOURS, severity=Severity.HIGH, day=day_plan.day, item_refs=[ref],
                    message=f"{ref}: {record.name!r} is not open {item.start}-{item.end} on that day",
                    details={"place_id": getattr(record, "id", None)},
                ))
    return conflicts, warnings


# ---------------------------------------------------------------------------
# 4. Invalid / missing place references
# ---------------------------------------------------------------------------
def rule_invalid_place_references(context: ConstraintContext) -> RuleResult:
    conflicts: list[PlanConflict] = []
    for day_plan in context.itinerary.days:
        for idx, item in enumerate(day_plan.items):
            ref = _ref(day_plan.day, idx)
            if item.type == ItemType.ACTIVITY and item.place_id and item.place_id not in context.places:
                conflicts.append(PlanConflict(
                    type=ConflictType.UNAVAILABLE_PLACE, severity=Severity.HIGH, day=day_plan.day,
                    item_refs=[ref], message=f"{ref}: place {item.place_id!r} is not available in the supplied data",
                    details={"place_id": item.place_id},
                ))
            if item.type == ItemType.MEAL and item.restaurant_id and item.restaurant_id not in context.restaurants:
                conflicts.append(PlanConflict(
                    type=ConflictType.UNAVAILABLE_PLACE, severity=Severity.HIGH, day=day_plan.day,
                    item_refs=[ref],
                    message=f"{ref}: restaurant {item.restaurant_id!r} is not available in the supplied data",
                    details={"restaurant_id": item.restaurant_id},
                ))
    return conflicts, []


# ---------------------------------------------------------------------------
# 5. Insufficient meal time
# ---------------------------------------------------------------------------
def rule_insufficient_meal_time(context: ConstraintContext) -> RuleResult:
    conflicts: list[PlanConflict] = []
    for day_plan in context.itinerary.days:
        for idx, item in enumerate(day_plan.items):
            if item.type == ItemType.MEAL and item.duration_minutes < DEFAULT_MIN_MEAL_MINUTES:
                ref = _ref(day_plan.day, idx)
                conflicts.append(PlanConflict(
                    type=ConflictType.INSUFFICIENT_MEAL_TIME, severity=Severity.HIGH, day=day_plan.day,
                    item_refs=[ref],
                    message=f"{ref}: meal duration {item.duration_minutes}m is below the minimum "
                            f"{DEFAULT_MIN_MEAL_MINUTES}m",
                    details={"duration_minutes": item.duration_minutes, "minimum_minutes": DEFAULT_MIN_MEAL_MINUTES},
                ))
    return conflicts, []


# ---------------------------------------------------------------------------
# 6. Excessive day/activity density (warning only)
# ---------------------------------------------------------------------------
def rule_excessive_density(context: ConstraintContext) -> RuleResult:
    warnings: list[PlanConflict] = []
    for day_plan in context.itinerary.days:
        active = day_plan.total_activity_minutes + day_plan.total_travel_minutes
        if active > DEFAULT_MAX_DAILY_ACTIVE_MINUTES:
            warnings.append(PlanConflict(
                type=ConflictType.EXCESSIVE_DENSITY, severity=Severity.MEDIUM, day=day_plan.day,
                message=f"day {day_plan.day}: {active} minutes of scheduled activity+travel exceeds the "
                        f"preferred daily maximum of {DEFAULT_MAX_DAILY_ACTIVE_MINUTES}",
                details={"active_minutes": active, "limit_minutes": DEFAULT_MAX_DAILY_ACTIVE_MINUTES},
            ))
    return [], warnings


# ---------------------------------------------------------------------------
# 7. Budget overrun - reuses BudgetStatus.evaluate() rather than
#    re-implementing cost totalling.
# ---------------------------------------------------------------------------
_CATEGORY_FOR_ITEM_TYPE = {
    ItemType.ACTIVITY: "activities", ItemType.MEAL: "food", ItemType.TRAVEL: "local_transport",
}


def rule_budget_overrun(context: ConstraintContext) -> RuleResult:
    totals = {"activities": 0.0, "food": 0.0, "local_transport": 0.0, "miscellaneous": 0.0}
    unknown_refs: list[str] = []
    for day_plan in context.itinerary.days:
        for idx, item in enumerate(day_plan.items):
            if item.type == ItemType.REST:
                continue
            if item.cost_inr is None:
                unknown_refs.append(_ref(day_plan.day, idx))
                continue
            totals[_CATEGORY_FOR_ITEM_TYPE.get(item.type, "miscellaneous")] += item.cost_inr

    if unknown_refs:
        return [], [PlanConflict(
            type=ConflictType.MISSING_DATA, severity=Severity.MEDIUM, item_refs=unknown_refs,
            message=f"{len(unknown_refs)} item(s) have an unknown cost; total trip cost could not be fully "
                    "verified against the budget (not assumed free)",
        )]

    breakdown = CostBreakdown(**totals)
    status = BudgetStatus.evaluate(Budget(total_inr=context.trip.budget, travellers=context.trip.travellers),
                                   breakdown)
    if status.is_over_budget:
        return [PlanConflict(
            type=ConflictType.BUDGET_OVERRUN, severity=Severity.HIGH,
            message=f"estimated cost {status.estimated_total_inr:.2f} INR exceeds the budget "
                    f"{status.budget_inr:.2f} INR by {status.overrun_inr:.2f} INR",
            details={"estimated_total_inr": status.estimated_total_inr, "budget_inr": status.budget_inr,
                     "overrun_inr": status.overrun_inr},
        )], []
    return [], []


# ---------------------------------------------------------------------------
# 8. Excessive travel time (warning only)
# ---------------------------------------------------------------------------
def rule_excessive_travel(context: ConstraintContext) -> RuleResult:
    warnings: list[PlanConflict] = []
    for day_plan in context.itinerary.days:
        if day_plan.total_travel_minutes > DEFAULT_MAX_DAILY_TRAVEL_MINUTES:
            warnings.append(PlanConflict(
                type=ConflictType.EXCESSIVE_TRAVEL, severity=Severity.MEDIUM, day=day_plan.day,
                message=f"day {day_plan.day}: {day_plan.total_travel_minutes} minutes of travel exceeds the "
                        f"preferred daily maximum of {DEFAULT_MAX_DAILY_TRAVEL_MINUTES}",
                details={"travel_minutes": day_plan.total_travel_minutes,
                         "limit_minutes": DEFAULT_MAX_DAILY_TRAVEL_MINUTES},
            ))
    return [], warnings


# Deterministic execution order (insertion order of a plain dict).
RULES: dict[str, Callable[[ConstraintContext], RuleResult]] = {
    "duplicate_places": rule_duplicate_places,
    "overlapping_items": rule_overlapping_items,
    "opening_hours": rule_opening_hours,
    "invalid_place_references": rule_invalid_place_references,
    "insufficient_meal_time": rule_insufficient_meal_time,
    "excessive_density": rule_excessive_density,
    "budget_overrun": rule_budget_overrun,
    "excessive_travel": rule_excessive_travel,
}
