"""Train and save a RecommendationModel.

Development (default - always works, no real data required):

    python scripts/train_recommender.py
    python scripts/train_recommender.py --out models/pipeline_test.joblib --seed 7

This generates PIPELINE-TEST training examples from the synthetic Goa dataset:
for many (synthetic trip, synthetic place) pairs it computes the deterministic
fallback score and uses that as the label. The resulting model is explicitly
NOT travel intelligence - see models/README.md. It exists to prove the
training/inference pipeline works before any real data exists.

Production (will refuse until real data exists):

    python scripts/train_recommender.py --purpose production --examples path/to/real_examples.json

There is no --examples loader for real data yet (Phase C does not have a real
dataset to load); passing --purpose production today will always raise
InsufficientTrainingDataError, which is the correct, intended behaviour.
"""
import argparse
import itertools
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.core.exceptions import DataLoadError, InsufficientTrainingDataError  # noqa: E402
from app.data.dev_data import generate_goa_dev_dataset  # noqa: E402
from app.data.repositories.json_repos import load_json_repositories  # noqa: E402
from app.recommendation.features import extract_features  # noqa: E402
from app.recommendation.model import TrainingPurpose  # noqa: E402
from app.recommendation.trainer import build_pipeline_test_examples_from_fallback, train  # noqa: E402
from app.schemas.common import ActivityLevel, TripType  # noqa: E402
from app.schemas.trip import TripRequest  # noqa: E402

DEFAULT_OUT = ROOT / "models" / "pipeline_test.joblib"


def _synthetic_pipeline_test_trips() -> list[TripRequest]:
    """A handful of varied SYNTHETIC trip requests, purely to generate a spread
    of (trip, place) pairs for the pipeline-test label generator. These are
    not real traveller data."""
    import datetime as dt
    start = dt.date.today() + dt.timedelta(days=30)
    trips = []
    combos = itertools.product(
        (TripType.SOLO, TripType.FAMILY, TripType.FRIENDS),
        (ActivityLevel.RELAXED, ActivityLevel.MODERATE, ActivityLevel.INTENSE),
        ([], ["beaches", "food"], ["nature", "history"], ["nightlife", "adventure"]),
    )
    for trip_type, level, interests in combos:
        trips.append(TripRequest(
            destination="Goa", start_date=start, end_date=start + dt.timedelta(days=4),
            travellers=2 if trip_type != TripType.FAMILY else 4, trip_type=trip_type, budget=30000,
            interests=interests, dislikes=[], activity_level=level,
        ))
    return trips


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--purpose", choices=[e.value for e in TrainingPurpose], default=TrainingPurpose.PIPELINE_TEST.value)
    p.add_argument("--out", type=Path, default=DEFAULT_OUT)
    p.add_argument("--seed", type=int, default=42)
    p.add_argument("--data-dir", type=Path, default=ROOT / "data" / "dev" / "goa",
                   help="dev dataset to draw synthetic places from (generated on the fly if missing)")
    args = p.parse_args(argv)
    purpose = TrainingPurpose(args.purpose)

    if purpose is TrainingPurpose.PRODUCTION:
        print("error: --purpose production requires real-sourced training examples, which this script does not "
              "yet load (none exist). This is expected until real interaction data is collected.", file=sys.stderr)
        return 2

    try:
        repos = load_json_repositories(args.data_dir)
    except DataLoadError:
        print(f"'{args.data_dir}' not found or unreadable; generating an in-memory synthetic dataset instead.")
        repos = generate_goa_dev_dataset(seed=args.seed).repositories()

    places = repos.places.list_all()
    if not places:
        print("error: no places available to build pipeline-test examples from", file=sys.stderr)
        return 2

    print("!! Training a PIPELINE-TEST model on synthetic/fallback-derived data. This is NOT travel "
          "intelligence - see models/README.md.")
    feature_results = [extract_features(trip, place) for trip in _synthetic_pipeline_test_trips() for place in places]
    examples = build_pipeline_test_examples_from_fallback(feature_results)
    print(f"  built {len(examples)} pipeline-test examples from {len(places)} places")

    try:
        model = train(examples, purpose=purpose, seed=args.seed)
    except InsufficientTrainingDataError as exc:
        print(f"error: {exc.message}", file=sys.stderr)
        return 2

    model.save(args.out)
    print(f"  metrics: {model.metadata.metrics}")
    for note in model.metadata.notes:
        print(f"  NOTE: {note}")
    print(f"saved to {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
