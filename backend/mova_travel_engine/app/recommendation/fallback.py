"""Deterministic, explicit fallback ranking - NOT machine learning.

Used whenever no trained production model is available (which, until real
interaction data exists, is always). Every weight is a named constant below;
`score_place` returns the per-component contributions alongside the total so
the formula is auditable rather than a black box.

The formula is a hand-written heuristic. It has not been fit or validated
against real outcomes, so its accuracy is unknown - callers should treat its
output as a reasonable ordering, not a calibrated probability.
"""
from dataclasses import dataclass

from app.recommendation.features import FamilyCompatibility, PlaceFacts, SeasonStatus

# Every number the fallback formula uses, in one place, with a one-line reason.
WEIGHTS: dict[str, float] = {
    "baseline": 0.5,                    # neutral starting point (no info -> coin flip)
    "interest_match_each": 0.08,        # + per trip interest tag also on the place
    "interest_match_cap": 0.32,         # contribution cap (4 matches)
    "dislike_conflict_each": -0.15,     # - per trip dislike tag also on the place
    "dislike_conflict_cap": -0.45,      # cap (3 conflicts)
    "rating_scale": 0.15,               # * (rating-3)/2, so a 5-star place gets +0.15, 1-star gets -0.15
    "popularity_scale": 0.10,           # * (popularity-0.5)*2, so max popularity gets +0.10
    "family_match": 0.10,
    "family_conflict": -0.25,
    "season_best": 0.08,
    "season_closed": -0.30,             # visiting something closed in-season is a real problem
    "activity_mismatch_each_point": -0.05,
    "activity_mismatch_cap": -0.15,   # max uncapped magnitude (|4.5-1|*0.05=0.175) slightly exceeds this
    "fee_overshare_scale": -0.20,       # * min(fee_share - 1, 1) when a place alone would exceed the per-traveller budget
    "fee_bargain_bonus": 0.03,          # flat bonus when the fee is a small share (<30%) of the per-traveller budget
}


@dataclass(frozen=True)
class FallbackResult:
    score: float                      # clipped to [0, 1]
    components: dict[str, float]      # every contribution, including zeros, for auditability


def _clip01(x: float) -> float:
    return max(0.0, min(1.0, x))


def score_place(facts: PlaceFacts) -> FallbackResult:
    w = WEIGHTS
    c: dict[str, float] = {"baseline": w["baseline"]}

    c["interest_match"] = min(w["interest_match_each"] * len(facts.interest_matches), w["interest_match_cap"])
    c["dislike_conflict"] = max(w["dislike_conflict_each"] * len(facts.dislike_conflicts), w["dislike_conflict_cap"])

    c["rating"] = w["rating_scale"] * ((facts.rating - 3.0) / 2.0) if facts.rating is not None else 0.0
    c["popularity"] = w["popularity_scale"] * ((facts.popularity - 0.5) * 2.0) if facts.popularity is not None else 0.0

    c["family"] = {
        FamilyCompatibility.MATCH: w["family_match"],
        FamilyCompatibility.CONFLICT: w["family_conflict"],
        FamilyCompatibility.UNKNOWN: 0.0,
    }[facts.family_compatibility]

    c["season"] = {
        SeasonStatus.BEST: w["season_best"],
        SeasonStatus.CLOSED: w["season_closed"],
        SeasonStatus.NEUTRAL: 0.0,
    }[facts.season_status]

    c["activity_mismatch"] = max(
        w["activity_mismatch_each_point"] * facts.activity_level_diff, w["activity_mismatch_cap"]
    )

    if facts.fee_share_of_budget_per_traveller is None:
        c["fee"] = 0.0
    elif facts.fee_share_of_budget_per_traveller > 1.0:
        c["fee"] = w["fee_overshare_scale"] * min(facts.fee_share_of_budget_per_traveller - 1.0, 1.0)
    elif facts.fee_share_of_budget_per_traveller < 0.3:
        c["fee"] = w["fee_bargain_bonus"]
    else:
        c["fee"] = 0.0

    total = sum(c.values())
    return FallbackResult(score=_clip01(total), components=c)
