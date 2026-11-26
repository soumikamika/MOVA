# MOVA Travel Engine — Repository Structure

This repository is the canonical cumulative codebase.

Development phases are checkpoints, not separate project folders. Each phase
extends the same `app/`, `tests/`, `data/`, `models/`, and `scripts/` trees.

Current verified checkpoint:
- Phase A: complete
- Phase B: complete
- Phase C: complete — 300/300 tests
- Phase D: complete — 397/397 tests on the user's Windows/Python 3.14 environment
- Phase E1: complete — 434/434 tests (397 baseline + 37 new), verified in the development sandbox; pending re-verification on the user's Windows/Python 3.14 environment

## Domain boundaries

- `app/core/` — shared configuration, constants, exceptions, logging
- `app/schemas/` — canonical domain schemas
- `app/data/` — repository/data-access layer
- `app/ml/` — shared ML infrastructure
- `app/recommendation/` — recommendation domain
- `app/travel_time/` — travel-time prediction domain
- `app/travel_cost/` — travel-cost prediction domain
- `app/constraints/` — constraint engine (Phase E1): detects/reports itinerary feasibility problems; never rearranges, repairs, or optimizes
- `app/utils/` — shared utilities
- `tests/` — cumulative regression suite

Do not create `phase_a/`, `phase_b/`, `phase_c/`, etc. folders for future work.
When a new phase is completed, its code remains in the appropriate domain
module and its tests are added to the same `tests/` tree.

## Checkpoints

For safety, keep a copy/tag of each verified phase externally or in Git.
The working repository itself should remain a single cumulative project.
