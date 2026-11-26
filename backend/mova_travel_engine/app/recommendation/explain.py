"""Turns PlaceFacts into human-readable reasons and machine-readable tags.

Used for BOTH scoring methods (fallback and ML): a trained gradient-boosting
model does not give reliable, faithful per-instance feature attributions
without extra tooling this project does not use (e.g. SHAP), so rather than
inventing an explanation from model internals, every recommendation - however
it was scored - is explained from these same directly-observed facts.
"""
from app.recommendation.features import FamilyCompatibility, PlaceFacts, SeasonStatus


def build_reasons(facts: PlaceFacts) -> list[str]:
    """Ordered, deterministic sentences. Nothing here is invented: every
    sentence corresponds to a field already present on `facts`."""
    reasons: list[str] = []

    if facts.interest_matches:
        reasons.append(f"Matches your interest in {', '.join(facts.interest_matches)}.")
    if facts.dislike_conflicts:
        reasons.append(f"Conflicts with things you said you dislike: {', '.join(facts.dislike_conflicts)}.")
    if facts.season_status == SeasonStatus.BEST:
        reasons.append("Falls within the recommended season for this place.")
    elif facts.season_status == SeasonStatus.CLOSED:
        reasons.append("This place is typically closed during your travel month(s).")
    if facts.family_compatibility == FamilyCompatibility.MATCH:
        reasons.append("Marked as family-friendly.")
    elif facts.family_compatibility == FamilyCompatibility.CONFLICT:
        reasons.append("Not marked as family-friendly.")
    if facts.rating is not None:
        reasons.append(f"Has a rating of {facts.rating:.1f}/5.")
    if facts.entry_fee_inr == 0:
        reasons.append("Free entry.")
    if facts.activity_level_diff <= 0.5:
        reasons.append("Matches your selected activity level.")
    elif facts.activity_level_diff >= 2.0:
        reasons.append("May be more or less strenuous than your selected activity level.")
    if facts.fee_share_of_budget_per_traveller is not None and facts.fee_share_of_budget_per_traveller > 1.0:
        reasons.append("The entry fee alone would exceed your average per-traveller budget.")
    return reasons


def build_supporting_factors(facts: PlaceFacts) -> list[str]:
    """Short machine-readable tags mirroring build_reasons(), for programmatic use."""
    tags: list[str] = [f"interest_match:{t}" for t in facts.interest_matches]
    tags += [f"dislike_conflict:{t}" for t in facts.dislike_conflicts]
    tags.append(f"season:{facts.season_status.value}")
    tags.append(f"family:{facts.family_compatibility.value}")
    if facts.rating is not None:
        tags.append("rating_known")
    if facts.popularity is not None:
        tags.append("popularity_known")
    if facts.entry_fee_inr is not None:
        tags.append("entry_fee_known" if facts.entry_fee_inr > 0 else "free_entry")
    if facts.activity_level_diff <= 0.5:
        tags.append("activity_level_match")
    return tags
