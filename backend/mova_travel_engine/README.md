# MOVA Travel Intelligence Engine

Backend planning engine for MOVA (India-first travel platform). It answers:
**"Given everything the traveller wants, what can realistically fit into this trip?"**

The LLM is never the itinerary decision-maker. Data, ML models, ranking,
constraint checking, optimisation, routing, costing and explanation are separate layers.

## Status

| Phase | Scope | Status |
|-------|-------|--------|
| A | Schemas, validation, config, utils | **done** |
| B | Data layer (repositories, loaders, validation, dev data generator) | **done** |
| C | Recommendation model | **done** |
| D | Travel-time + cost prediction (originally split D/E) | **done** |
| E1 | Constraint engine (detection only) | **done** |
| E2 | Deterministic itinerary optimizer + E1 repair | **done** |
| E3 | Plan Orchestrator + API-ready contract | **done** |
| E4 | Modification / re-optimisation | **done** |
| E5 | FastAPI HTTP adapter | **done** |
| K | External provider adapters | next |
| L | LLM intent layer | - |

## Setup (Windows PowerShell; Python 3.11+ required)

```powershell
cd mova_travel_engine
py -3.12 -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
copy .env.example .env
pytest -v
```

(If PowerShell blocks activation: `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned`.)

Python 3.11+ is required because the schemas use `enum.StrEnum`.

## Data provenance (core rule)

Every data-bearing schema (`Place`, `Restaurant`, `Hotel`, `Destination`,
`TransportOption`, `Weather`) has a **required** `source` field:

`real` | `synthetic_dev` | `external_api` | `user_generated` | `mock`

`has_development_only_data()` flags `synthetic_dev`/`mock`; the API will surface
this on every plan so synthetic data can never pass as real-world performance.

## Design decisions in Phase A

- **`None` means unknown, never a guessed value** (e.g. `entry_fee_inr=None` vs `0` = free).
- **Schemas validate structure, not feasibility.** `ItineraryItem`/`DayPlan` accept
  overlapping or over-long days so the Constraint Engine (Phase F) can detect and report them.
- **`extra="forbid"`** on all schemas: a misspelt field is a 422, not silently ignored.
- **Tags** are normalised onto a controlled vocabulary (`app/core/vocabulary.py`);
  unknown tags are kept and later reported as assumptions.
- **Times** are strict `HH:MM` strings in JSON; internally minutes since midnight.
- `ItineraryItem` uses `from_id`/`to_id` (spec sketch used `from`/`to`).
- **Cost estimates** default to `confidence="unknown"`; bounds/MAE stay `None`
  unless produced by real evaluation.
- Secrets are `SecretStr`, loaded only from `.env`.

## Phase B: data layer

```
Planner Orchestrator  ->  Repositories (interfaces)  ->  JSON now / PostgreSQL later
```
- `app/data/repositories/base.py` - abstract interfaces + `Repositories` bundle (the ONLY thing planner code may import)
- `app/data/repositories/json_repos.py` - JSON-backed implementations (`load_json_repositories(dir)`)
- `app/data/filters.py` - database-agnostic query criteria (`PlaceFilter`, ...) with an explicit unknown-value policy
- `app/data/loaders.py` / `json_store.py` - strict/lenient loading, atomic writes, rollback on failed writes
- `app/data/dataset_validation.py` - integrity checks (orphans, coordinates, provenance, unknown values ...)
- `app/data/dev_data.py` - SYNTHETIC development dataset generator (only scripts/tests import it)

```powershell
python scripts/generate_dev_data.py            # writes data/dev/goa (all records source=synthetic_dev)
python scripts/validate_data.py                # exit 0 ok | 1 failed | 2 directory missing
python scripts/validate_data.py --strict --fail-on-synthetic   # production gate
```
Dev data lives in `data/dev/`, never in `data/raw/` (the generator refuses to write there).

## Phase C: recommendation / ranking engine

```
TripRequest + list[Place]  ->  extract_features()  ->  fallback OR production model  ->  list[Recommendation]
```
- `app/recommendation/features.py` - deterministic `(TripRequest, Place) -> (PlaceFacts, vector)`. Unknown
  Place attributes (`rating=None`, ...) become `NaN` in the vector, never a guessed value.
- `app/recommendation/fallback.py` - explicit, weighted, deterministic scorer (`WEIGHTS` dict). Not ML;
  used whenever no production model is available (today: always).
- `app/recommendation/explain.py` - turns `PlaceFacts` into reasons/tags, for both scoring methods.
- `app/recommendation/model.py` - `RecommendationModel` (HistGradientBoostingRegressor wrapper); save/load
  via joblib; refuses to load a model trained on a different feature schema.
- `app/recommendation/trainer.py` - `train(examples, purpose=...)`. `TrainingPurpose.PRODUCTION` requires
  >= `MIN_PRODUCTION_EXAMPLES` (500) real-sourced (`real`/`user_generated`/`external_api`) examples or raises
  `InsufficientTrainingDataError`; `TrainingPurpose.PIPELINE_TEST` allows synthetic/fallback-derived labels
  but the resulting model is never used by `RecommendationService` to score real recommendations.
- `app/recommendation/service.py` - `RecommendationService.recommend(trip, candidates) -> list[Recommendation]`.

**Model choice: `HistGradientBoostingRegressor`** - it handles missing numeric features (`NaN`) natively, so
Phase B's "unknown must never become a guessed value" rule holds all the way into the model, without an
imputation step. It captures non-linear/interacting signals (e.g. "an interest match matters more when
affordable") without deep learning. Trade-off: no simple per-instance feature attribution, which is why
explanations are built from `PlaceFacts` (facts directly observed from the data) rather than from the model.

```powershell
python scripts/train_recommender.py                      # pipeline-test model -> models/pipeline_test.joblib
python scripts/train_recommender.py --purpose production  # refuses: no real data yet (by design)
```

## Phase D: travel-time + cost prediction

```
Request (TravelTimeRequest / CostRequest)  ->  baseline OR production model  ->  Prediction
```
- `app/schemas/prediction.py` - the shared `Prediction` result (`value`, `unit`, `method`, `confidence`,
  `is_estimated`, `is_unknown`, bounds, `model_version`, `notes`). `Prediction.unknown(...)` is the explicit
  "we do not know" result; a validator enforces that `is_unknown=True` always means `value=None` (never 0 or a guess).
- `app/travel_time/` and `app/travel_cost/` - each has `features.py` (deterministic request -> facts + NaN-safe
  vector), `baseline.py` (transparent formula, no ML), `model.py` (thin `BaseTrainedModel` subclass), `trainer.py`,
  `service.py`. Structurally identical to `app/recommendation/`, deliberately - same review path, same guarantees.
- `app/ml/` - infrastructure now shared by all three domains (recommendation, travel_time, travel_cost), extracted
  during Phase D once the pattern repeated a third time:
  - `matrix.py` - `split_constant_columns()`, the fix for Phase C's "window shape cannot be larger than input
    array shape" crash: columns with fewer than 2 distinct values are dropped before fitting, for every domain.
  - `training_rules.py` - `MIN_PRODUCTION_EXAMPLES = 500`, `REAL_SOURCES`, `TrainingPurpose`.
  - `model_metadata.py` - the one `ModelMetadata` schema every domain's models use.
  - `base_model.py` - `BaseTrainedModel`: bounded `predict_one`/`predict_many`, `save`/`load` with schema-drift
    protection (a model saved by one domain cannot be loaded by another, or after `features.py` changes).
  - `trainer_core.py` - `fit_regressor()`: the one HistGradientBoostingRegressor fit/evaluate routine (constant-column
    guard, in-sample fallback for small batches, production/pipeline-test gating) every domain's `train()` calls.
  - `confidence.py` - `completeness_confidence()`: confidence is how much of the relevant input is known, never a
    claim about model accuracy (see Part 4 of the phase brief) - HIGH is reserved for directly `OBSERVED` values.

**Baseline vs ML:**
- Travel time: `distance_km / assumed_speed_kmh * 60` + a flat per-transfer penalty, only when `distance_km` is
  known; otherwise `Prediction.unknown(...)`. Never calibrated against real data - confidence is capped at LOW.
- Cost: `total_known_price_inr` (an already-known/observed price) always wins -> `OBSERVED`, `confidence=HIGH`,
  `is_estimated=False`. Otherwise `quantity * unit_price_inr` when both are known -> `BASELINE`, `confidence=LOW`.
  Otherwise unknown. No price is ever invented.
- ML (`HistGradientBoostingRegressor`, same choice and rationale as Phase C - native NaN handling, no deep
  learning): `TrainingPurpose.PRODUCTION` requires >= 500 real-sourced (`real`/`user_generated`/`external_api`)
  examples or raises `InsufficientTrainingDataError`; none exist yet, so production training always refuses today,
  by design. `TrainingPurpose.PIPELINE_TEST` trains on labels generated by each domain's own baseline formula,
  forced to `source=synthetic_dev` regardless of the underlying request, and such a model is never used by
  `TravelTimeService`/`TravelCostService` to answer a real `predict()` call - only baseline is, until real data exists.

```powershell
python -c "from app.travel_time.trainer import *"   # see scripts/train_recommender.py for the CLI pattern;
                                                      # an analogous scripts/train_travel_time.py /
                                                      # scripts/train_travel_cost.py can be added the same way
pytest -v
```

## Phase E3: Plan Orchestrator + API-ready contract

```
PlanGenerationRequest
        |
        v
Destination resolution + repository retrieval
        |
        v
RecommendationService
        |
        v
OptimizerService (E2) -> ConstraintEngine (E1)
        |
        v
PlanGenerationResult
```

- `app/services/planner.py` - the single business entry point for plan generation.
- `app/schemas/planner.py` - stable request/response contract intended for the future HTTP layer.
- Repository implementations are injected; planner code never depends on JSON, SQL, or a provider.
- Candidate places are resolved from the requested destination and trip month. Unknown attributes remain unknown.
- Restaurants/hotels can be retrieved as supporting context without pretending they are already optimized into the itinerary.
- The response exposes itinerary, recommendations, optimization changes, conflicts/warnings, engine status, and data provenance.
- Development-only data is explicitly surfaced through `data_quality.development_only`.
- No FastAPI dependency is introduced yet; the next API phase can wrap `PlannerService.generate()` directly.

Future HTTP mapping (contract only, not implemented yet):

```text
POST /api/plans/generate
request:  PlanGenerationRequest
response: PlanGenerationResult
```

## Phase E1: constraint engine (detection only)

```
ConstraintContext (trip, itinerary, places, restaurants, ...) -> ConstraintEngine.validate() -> ConstraintResult
```
- `app/constraints/context.py` - `ConstraintContext`: a plain dataclass (like `Repositories`) bundling the
  trip, itinerary, already-fetched `Place`/`Restaurant`/`Destination` records, and (for forward compatibility
  with later phases) the existing `TravelTimeService`/`TravelCostService`/`Repositories`. Building one never
  calls a repository itself - the caller fetches data and hands it over.
- `app/constraints/rules.py` - eight independent, deterministic rule functions (duplicate places, overlapping
  items, opening hours, invalid/missing place references, insufficient meal time, excessive density, budget
  overrun, excessive travel), each returning `(conflicts, warnings)` as existing `PlanConflict` objects. No new
  conflict schema was introduced - `PlanConflict`/`ConflictType`/`Severity` (Phase A) are reused as-is.
- `app/constraints/engine.py` - `ConstraintEngine.validate(context) -> ConstraintResult`: runs every rule,
  collects conflicts/warnings, and sets `feasible = not conflicts`. Deterministic order, no hidden state.
- `app/constraints/results.py` - `ConstraintResult`: `feasible: bool`, `conflicts`/`warnings: list[PlanConflict]`,
  `checked_rules: list[str]`.

**Hard vs soft, concretely:** a HIGH-severity, confirmed violation (duplicate place, overlap, confirmed-closed
venue, too-short a meal, an unresolvable place/restaurant reference, a confirmed budget overrun) becomes a
*conflict* and makes `feasible=False`. Everything else - excessive density, excessive travel, and any case
where a rule could not be evaluated because required data is unknown (opening hours = None, an item's
`cost_inr` = None) - becomes a *warning* and never flips `feasible`. Unknown data is always reported as a
`MISSING_DATA` warning; it is never silently treated as "open", "free", or skipped without a trace.

**Explicitly out of scope for E1** (reserved for later phases): the engine only detects and reports. It never
rearranges, repairs, drops, or re-optimizes itinerary items, and does not use OR-Tools or an LLM.

## Layout

## Layout

## Layout

```
app/
  core/       config, logging, constants, vocabulary, exceptions
  schemas/    common, trip, place, logistics, budget, itinerary, recommendation
  utils/      time, geo, validation
  data/          repositories, filters, loaders, JSON store, dataset validation, dev data (Phase B)
  recommendation/  Phase C: features, fallback, explain, model, trainer, service
  travel_time/     Phase D: features, baseline, model, trainer, service
  travel_cost/     Phase D: features, baseline, model, trainer, service
  services/        Phase E3: plan orchestrator
  constraints/     Phase E1: context, rules, engine, results (detection only)
  optimizer/       Phase E2: deterministic itinerary optimization + repair
  ml/              shared training/model infrastructure (Phase D extraction; see above)
  api/ services/ providers/ models/   (filled in by later phases)
training/  scripts/  data/{raw,processed,training,evaluation}  models/  tests/
```

## E4: plan modification / re-optimisation

Structured modifications are accepted by `PlanModificationService`. Supported actions are `add_place`, `remove_place`, `move_place`, and `reoptimize`. Natural-language commands are intentionally not parsed here; a future intent/LLM layer can translate user language into these deterministic operations. Every modification is sent back through E2 and E1 before being returned.

## E5: HTTP adapter

Run the API locally:

```powershell
uvicorn app.api.app:app --reload --port 8000
```

Endpoints:
- `GET /api/health`
- `POST /api/plans/generate`
- `POST /api/plans/optimize`
- `POST /api/plans/modify`
- `POST /api/plans/validate`

The frontend should treat `PlanGenerationResult` as the stable contract. It should not call recommendation, travel-time, travel-cost, optimizer, or constraint modules separately.

### Frontend integration contract

1. Create Plan sends `PlanGenerationRequest` to `/api/plans/generate`.
2. My Plans stores the returned `PlanGenerationResult` locally until user accounts/backend persistence are added.
3. Manual edits use `/api/plans/modify` with structured actions.
4. A re-optimization request uses `/api/plans/optimize` with the current itinerary as `base_itinerary`.
5. `/api/plans/validate` can be used for a fast pre-save validation state.
6. The UI must show `data_quality`, `warnings`, `conflicts`, and `engine` status instead of presenting development/synthetic records as live facts.

The HTTP layer is intentionally thin. PostgreSQL, live tourism/transport providers, authentication and an intent/LLM layer can be added later without changing the frontend contract.
