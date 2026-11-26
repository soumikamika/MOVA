"""Generate the SYNTHETIC Goa development dataset.

    python scripts/generate_dev_data.py                # -> data/dev/goa
    python scripts/generate_dev_data.py --out some/dir --seed 7 --force

Output is labelled source="synthetic_dev" on every record. It is for testing the
engine only and is never real tourism information.
"""
import argparse
import datetime as dt
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.data.dev_data import DISCLAIMER, generate_goa_dev_dataset, write_dev_dataset  # noqa: E402

DEFAULT_OUT = ROOT / "data" / "dev" / "goa"


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--out", type=Path, default=DEFAULT_OUT, help="output directory")
    p.add_argument("--seed", type=int, default=42)
    p.add_argument("--force", action="store_true", help="overwrite existing files")
    p.add_argument("--generated-at", type=dt.datetime.fromisoformat, default=None,
                   help="ISO timestamp to stamp on records (default: now, UTC); fix it for reproducible output")
    args = p.parse_args(argv)

    print("!! " + DISCLAIMER)
    try:
        ds = generate_goa_dev_dataset(seed=args.seed, generated_at=args.generated_at)
        paths = write_dev_dataset(ds, args.out, force=args.force)
    except (FileExistsError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    for name, recs in ds.collections().items():
        print(f"  {name:<13} {len(recs):>3} records (source=synthetic_dev)")
    print(f"written to {args.out} ({len(paths)} files)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
