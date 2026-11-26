# Model artifacts

Saved `RecommendationModel` artifacts (`joblib` files) go here. **Nothing in
this repository ships a trained model** - `.gitignore` excludes everything
under `models/` except this file.

Every artifact carries a `ModelMetadata.purpose`:

- `pipeline_test` - trained on non-production data (currently: labels derived
  from the deterministic fallback formula over the synthetic Goa dataset).
  It exists to prove the training → save → load → predict pipeline works. It
  is **not** trained travel intelligence and `RecommendationService` will
  never use one to score real recommendations (it always falls back to the
  deterministic formula instead).
- `production` - trained on at least `trainer.MIN_PRODUCTION_EXAMPLES` (500)
  real-sourced examples (`source` in `real` / `user_generated` /
  `external_api`). No such data exists yet, so no `production` artifact can
  currently be produced - `trainer.train(..., purpose=PRODUCTION)` raises
  `InsufficientTrainingDataError` until it does.

Generate a pipeline-test artifact:

```powershell
python scripts\train_recommender.py --purpose pipeline_test --out models\pipeline_test.joblib
```
