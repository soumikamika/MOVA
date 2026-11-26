"""ConstraintEngine.validate(context) -> ConstraintResult.

Runs every rule in app.constraints.rules.RULES, collects conflicts and
warnings, and determines feasibility from conflicts alone: `feasible` is True
iff no rule produced a (HIGH-severity) conflict. Warnings - including every
case where a rule could not be evaluated because required data was unknown -
never flip `feasible` to False and are never silently promoted into a
conflict either; they are reported as-is for the caller to review.

This engine ONLY detects and reports. It never rearranges, repairs, drops, or
re-optimizes itinerary items, never calls OR-Tools, and never calls an LLM -
that is explicitly out of scope for Phase E1 (see later-phase notes in
app/constraints/rules.py's module docstring and the project README).
"""
from app.constraints.context import ConstraintContext
from app.constraints.results import ConstraintResult
from app.constraints.rules import RULES


class ConstraintEngine:
    """Stateless; safe to reuse/share across requests."""

    def validate(self, context: ConstraintContext) -> ConstraintResult:
        conflicts = []
        warnings = []
        checked_rules = []
        for name, rule in RULES.items():
            rule_conflicts, rule_warnings = rule(context)
            conflicts.extend(rule_conflicts)
            warnings.extend(rule_warnings)
            checked_rules.append(name)
        return ConstraintResult(
            feasible=not conflicts, conflicts=conflicts, warnings=warnings, checked_rules=checked_rules,
        )
