"""Dataset integrity checks. Pure functions over already-parsed records.

IssueSeverity meaning:
  ERROR   - dataset cannot be trusted / planner would misbehave; fails validation
  WARNING - usable, but planner will need assumptions or results may be poor
  INFO    - worth knowing (unknown values, synthetic data present, ...)
"""
from collections import defaultdict
from collections.abc import Iterable, Mapping
from enum import StrEnum
from pathlib import Path
from typing import Any

from pydantic import Field, computed_field

from app.core.exceptions import DataLoadError
from app.core.vocabulary import CANONICAL_TAGS
from app.data.filters import match_destination, normalize_name
from app.data.loaders import DATASET_SPECS, SCHEMA_VERSION, DatasetMeta, load_records
from app.schemas.common import DataSource, MovaModel
from app.utils.geo import haversine_km, is_within_india_bounds


class IssueSeverity(StrEnum):
    ERROR = "error"
    WARNING = "warning"
    INFO = "info"


class ValidationIssue(MovaModel):
    severity: IssueSeverity
    code: str
    message: str
    entity: str | None = None
    record_id: str | None = None


class ValidationReport(MovaModel):
    issues: list[ValidationIssue] = Field(default_factory=list)
    record_counts: dict[str, int] = Field(default_factory=dict)
    sources_in_use: dict[str, int] = Field(default_factory=dict)

    @computed_field
    @property
    def error_count(self) -> int:
        return sum(1 for i in self.issues if i.severity == IssueSeverity.ERROR)

    @computed_field
    @property
    def warning_count(self) -> int:
        return sum(1 for i in self.issues if i.severity == IssueSeverity.WARNING)

    @computed_field
    @property
    def ok(self) -> bool:
        return self.error_count == 0

    def codes(self, severity: IssueSeverity | None = None) -> set[str]:
        return {i.code for i in self.issues if severity is None or i.severity == severity}

    @property
    def has_development_only_data(self) -> bool:
        return any(DataSource(s).is_development_only for s in self.sources_in_use)


class _Collector:
    def __init__(self) -> None:
        self.issues: list[ValidationIssue] = []

    def add(self, severity: IssueSeverity, code: str, message: str, entity: str | None = None,
            record_id: str | None = None) -> None:
        self.issues.append(ValidationIssue(severity=severity, code=code, message=message,
                                           entity=entity, record_id=record_id))

    def aggregate(self, severity: IssueSeverity, code: str, entity: str, ids: list[str], problem: str) -> None:
        if not ids:
            return
        sample = ", ".join(ids[:5]) + (", ..." if len(ids) > 5 else "")
        self.add(severity, code, f"{len(ids)} {entity} record(s) {problem} (e.g. {sample})", entity)


def _check_geo(c: _Collector, entity: str, recs: Iterable[Any], dest_by_id: Mapping[str, Any],
               max_km: float) -> None:
    for r in recs:
        lat, lng = r.location.latitude, r.location.longitude
        if not is_within_india_bounds(lat, lng):
            if is_within_india_bounds(lng, lat):
                c.add(IssueSeverity.ERROR, "swapped_coordinates",
                      f"{entity} coordinates look like latitude/longitude are swapped ({lat}, {lng})", entity, r.id)
            else:
                c.add(IssueSeverity.WARNING, "outside_india_bounds",
                      f"{entity} coordinates ({lat}, {lng}) are outside India's bounding box", entity, r.id)
        d = dest_by_id.get(r.destination_id)
        if d is not None:
            km = haversine_km(lat, lng, d.center.latitude, d.center.longitude)
            if km > max_km:
                c.add(IssueSeverity.WARNING, "far_from_destination_center",
                      f"{entity} is {km:.0f} km from the centre of {d.name} (limit {max_km:.0f} km)", entity, r.id)


def _check_provenance(c: _Collector, entity: str, recs: list[Any]) -> None:
    if not recs:
        return
    dev = [r for r in recs if r.source.is_development_only]
    if dev:
        c.add(IssueSeverity.INFO, "development_only_data",
              f"{len(dev)} of {len(recs)} {entity} record(s) are synthetic/mock development data", entity)
        c.aggregate(IssueSeverity.WARNING, "overconfident_synthetic", entity,
                    [r.id for r in dev if r.confidence is not None and r.confidence > 0.5],
                    "are synthetic but claim confidence > 0.5")
    if dev and len(dev) != len(recs):
        c.add(IssueSeverity.WARNING, "mixed_sources",
              f"{entity} mixes development-only and real/external records", entity)
    c.aggregate(IssueSeverity.WARNING, "missing_last_updated", entity,
                [r.id for r in recs if not r.source.is_development_only and r.last_updated is None],
                "have no last_updated although they are not synthetic")


def _check_duplicate_names(c: _Collector, entity: str, recs: Iterable[Any]) -> None:
    groups: dict[tuple[str, str], list[str]] = defaultdict(list)
    for r in recs:
        groups[(r.destination_id, normalize_name(r.name))].append(r.id)
    for (dest, name), ids in groups.items():
        if len(ids) > 1:
            c.add(IssueSeverity.WARNING, "duplicate_name",
                  f"{entity} name {name!r} appears {len(ids)} times in {dest}: {', '.join(ids)}", entity)


def validate_collections(
    *, destinations: list, places: list, restaurants: list, hotels: list, transport: list,
    metas: Mapping[str, DatasetMeta | None] | None = None, max_distance_from_center_km: float = 150.0,
) -> ValidationReport:
    c = _Collector()
    collections = {"destinations": destinations, "places": places, "restaurants": restaurants,
                   "hotels": hotels, "transport": transport}
    dest_by_id = {d.id: d for d in destinations}

    # -- emptiness ---------------------------------------------------------
    if not destinations:
        c.add(IssueSeverity.ERROR, "empty_collection", "no destinations in dataset", "destinations")
    if not places:
        c.add(IssueSeverity.ERROR, "empty_collection", "no places in dataset", "places")
    for name, recs in (("restaurants", restaurants), ("hotels", hotels), ("transport", transport)):
        if not recs:
            c.add(IssueSeverity.WARNING, "empty_collection", f"no {name} in dataset", name)
    if destinations and places:
        for d in destinations:
            for name, recs in (("places", places), ("restaurants", restaurants), ("hotels", hotels)):
                if recs and not any(r.destination_id == d.id for r in recs):
                    c.add(IssueSeverity.WARNING, "destination_without_records",
                          f"destination {d.id!r} has no {name}", "destinations", d.id)

    # -- referential integrity & geography ----------------------------------
    for entity, recs in (("place", places), ("restaurant", restaurants), ("hotel", hotels)):
        for r in recs:
            if r.destination_id not in dest_by_id:
                c.add(IssueSeverity.ERROR, "orphan_destination",
                      f"{entity} references unknown destination {r.destination_id!r}", entity, r.id)
        _check_geo(c, entity, recs, dest_by_id, max_distance_from_center_km)
        _check_duplicate_names(c, entity, recs)

    # -- destinations: alias ambiguity --------------------------------------
    keys: dict[str, set[str]] = defaultdict(set)
    for d in destinations:
        for k in [d.id, d.name, *d.aliases]:
            keys[normalize_name(k)].add(d.id)
    for k, ids in sorted(keys.items()):
        if len(ids) > 1:
            c.add(IssueSeverity.ERROR, "ambiguous_destination_name",
                  f"name/alias {k!r} maps to several destinations: {', '.join(sorted(ids))}", "destinations")

    # -- places: unknown values & feasibility -------------------------------
    c.aggregate(IssueSeverity.WARNING, "unknown_opening_hours", "place",
                [p.id for p in places if p.opening_hours is None],
                "have unknown opening hours (planner must treat them as an assumption)")
    c.aggregate(IssueSeverity.INFO, "unknown_entry_fee", "place",
                [p.id for p in places if p.entry_fee_inr is None], "have unknown entry fee")
    c.aggregate(IssueSeverity.INFO, "unknown_rating", "place",
                [p.id for p in places if p.rating is None], "have no rating")
    for p in places:
        if len(p.closed_months) == 12:
            c.add(IssueSeverity.WARNING, "never_open", "place is closed in every month", "place", p.id)
        oh = p.opening_hours
        if oh is not None and not oh.always_open:
            longest = max((e - s for w in range(7) for s, e in oh.windows_for(w)), default=0)
            if p.avg_visit_minutes > longest:
                c.add(IssueSeverity.WARNING, "visit_longer_than_opening_window",
                      f"avg visit ({p.avg_visit_minutes} min) exceeds the longest opening window ({longest} min)",
                      "place", p.id)
    unk = sorted({t for p in places for t in p.tags} - CANONICAL_TAGS)
    if unk:
        c.add(IssueSeverity.INFO, "unknown_tags",
              f"{len(unk)} tag(s) outside the controlled vocabulary: {', '.join(unk[:10])}", "place")

    # -- restaurants ---------------------------------------------------------
    c.aggregate(IssueSeverity.WARNING, "unknown_opening_hours", "restaurant",
                [r.id for r in restaurants if r.opening_hours is None], "have unknown opening hours")
    c.aggregate(IssueSeverity.INFO, "unknown_dietary_options", "restaurant",
                [r.id for r in restaurants if not r.dietary_options], "list no dietary options")
    c.aggregate(IssueSeverity.INFO, "unknown_price", "restaurant",
                [r.id for r in restaurants if r.avg_price_per_person_inr is None], "have no price")

    # -- transport ------------------------------------------------------------
    for t in transport:
        if normalize_name(t.origin) == normalize_name(t.destination):
            c.add(IssueSeverity.ERROR, "transport_same_endpoints",
                  f"origin and destination are both {t.origin!r}", "transport", t.id)
        if destinations and match_destination(t.destination, destinations) is None:
            c.add(IssueSeverity.WARNING, "transport_unknown_destination",
                  f"destination {t.destination!r} does not resolve to a known destination", "transport", t.id)

    # -- provenance & meta ----------------------------------------------------
    for name, recs in collections.items():
        _check_provenance(c, name, recs)
    for name, meta in (metas or {}).items():
        recs = collections.get(name, [])
        if meta is None:
            c.add(IssueSeverity.WARNING, "missing_meta", f"{name} file has no valid 'meta' block", name)
            continue
        if meta.schema_version != SCHEMA_VERSION:
            c.add(IssueSeverity.WARNING, "schema_version_mismatch",
                  f"{name} schema_version {meta.schema_version} != supported {SCHEMA_VERSION}", name)
        c.aggregate(IssueSeverity.ERROR, "source_mismatch", name,
                    [r.id for r in recs
                     if r.source.is_development_only != meta.data_source.is_development_only],
                    f"contradict the file's declared data_source={meta.data_source.value!r}")

    counts: dict[str, int] = {n: len(r) for n, r in collections.items()}
    by_source: dict[str, int] = defaultdict(int)
    for recs in collections.values():
        for r in recs:
            by_source[r.source.value] += 1
    return ValidationReport(issues=c.issues, record_counts=counts, sources_in_use=dict(by_source))


def validate_directory(directory: Path | str, *, max_distance_from_center_km: float = 150.0) -> ValidationReport:
    """Lenient-load every dataset file, report every problem, then cross-validate what loaded."""
    d = Path(directory)
    if not d.is_dir():
        raise DataLoadError(f"dataset directory not found: {d}", details={"path": str(d)})
    c = _Collector()
    loaded: dict[str, list] = {}
    metas: dict[str, DatasetMeta | None] = {}
    for name, spec in DATASET_SPECS.items():
        path = d / spec.filename
        loaded[name] = []
        if not path.exists():
            c.add(IssueSeverity.ERROR if spec.required else IssueSeverity.WARNING, "missing_file",
                  f"{spec.filename} not found", name)
            continue
        try:
            res = load_records(path, spec.model, strict=False)
        except DataLoadError as exc:
            c.add(IssueSeverity.ERROR, "unreadable_file", exc.message, name)
            continue
        loaded[name] = res.records
        metas[name] = res.meta
        if res.meta_error:
            c.add(IssueSeverity.ERROR, "malformed_meta", res.meta_error, name)
        for rej in res.rejected:
            dup = any("duplicate id" in e for e in rej.errors)
            c.add(IssueSeverity.ERROR, "duplicate_id" if dup else "malformed_record",
                  f"index {rej.index}: {'; '.join(rej.errors)}", name, rej.record_id)
    report = validate_collections(
        destinations=loaded["destinations"], places=loaded["places"], restaurants=loaded["restaurants"],
        hotels=loaded["hotels"], transport=loaded["transport"], metas=metas,
        max_distance_from_center_km=max_distance_from_center_km)
    # File-level problems first, then cross-record findings. A file that failed to
    # load must not also trigger 'empty' noise for the same collection.
    file_level = c.issues
    skip = {i.entity for i in file_level if i.code in ("missing_file", "unreadable_file")}
    merged = file_level + [i for i in report.issues
                           if not (i.code in ("empty_collection", "missing_meta") and i.entity in skip)]
    return ValidationReport(issues=merged, record_counts=report.record_counts,
                            sources_in_use=report.sources_in_use)
