"""Validate a dataset directory.

    python scripts/validate_data.py                       # data/dev/goa
    python scripts/validate_data.py --data-dir data/processed/goa
    python scripts/validate_data.py --json                # machine-readable
    python scripts/validate_data.py --strict --fail-on-synthetic   # CI / production gate

Exit codes: 0 ok | 1 validation failed | 2 dataset directory not found.
"""
import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.core.exceptions import DataLoadError  # noqa: E402
from app.data.dataset_validation import IssueSeverity, validate_directory  # noqa: E402

DEFAULT_DIR = ROOT / "data" / "dev" / "goa"


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--data-dir", type=Path, default=DEFAULT_DIR)
    p.add_argument("--json", action="store_true", help="print the report as JSON")
    p.add_argument("--strict", action="store_true", help="treat warnings as failures")
    p.add_argument("--fail-on-synthetic", action="store_true",
                   help="fail if any synthetic_dev/mock record is present (production gate)")
    p.add_argument("--max-distance-km", type=float, default=150.0,
                   help="warn when a record is farther than this from its destination centre")
    args = p.parse_args(argv)

    try:
        report = validate_directory(args.data_dir, max_distance_from_center_km=args.max_distance_km)
    except DataLoadError as exc:
        print(f"error: {exc.message}", file=sys.stderr)
        return 2

    failed = (not report.ok) or (args.strict and report.warning_count > 0) \
        or (args.fail_on_synthetic and report.has_development_only_data)

    if args.json:
        import json
        doc = report.model_dump(mode="json")
        doc["has_development_only_data"] = report.has_development_only_data
        doc["passed"] = not failed
        print(json.dumps(doc, indent=2))
        return 1 if failed else 0

    print(f"Dataset: {args.data_dir}")
    print("Records: " + ", ".join(f"{k}={v}" for k, v in report.record_counts.items()))
    print("Sources: " + (", ".join(f"{k}={v}" for k, v in report.sources_in_use.items()) or "none"))
    if report.has_development_only_data:
        print("NOTE: contains SYNTHETIC/MOCK development data - not real travel information.")
    for sev in (IssueSeverity.ERROR, IssueSeverity.WARNING, IssueSeverity.INFO):
        for i in (x for x in report.issues if x.severity == sev):
            where = f" [{i.entity}{':' + i.record_id if i.record_id else ''}]" if i.entity else ""
            print(f"  {sev.value.upper():<7} {i.code}{where}: {i.message}")
    print(f"Result: {'PASSED' if not failed else 'FAILED'} "
          f"({report.error_count} error(s), {report.warning_count} warning(s))")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
