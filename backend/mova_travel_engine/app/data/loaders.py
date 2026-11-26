"""Reading and writing dataset files.

File format (one file per collection):

    {"meta": {...DatasetMeta...}, "records": [ {...}, ... ]}

A bare top-level JSON array is also accepted (meta is then None, which the data
validator reports as a warning). Malformed records are never silently dropped:
strict mode raises, lenient mode returns them in `LoadResult.rejected`.
"""
import datetime as dt
import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Generic, TypeVar

from pydantic import Field, ValidationError

from app.core.exceptions import DataLoadError
from app.schemas.common import DataSource, MovaModel, Sourced
from app.schemas.logistics import TransportOption
from app.schemas.place import Destination, Hotel, Place, Restaurant

T = TypeVar("T", bound=Sourced)
SCHEMA_VERSION = 1


class DatasetMeta(MovaModel):
    dataset: str = Field(min_length=1)
    schema_version: int = Field(default=SCHEMA_VERSION, ge=1)
    data_source: DataSource  # the provenance this file CLAIMS for its records
    generated_at: dt.datetime | None = None
    generated_by: str | None = None
    seed: int | None = None
    disclaimer: str | None = None


@dataclass(frozen=True)
class DatasetSpec:
    name: str
    model: type
    filename: str
    required: bool  # a dataset without required collections cannot support planning


DATASET_SPECS: dict[str, DatasetSpec] = {
    s.name: s
    for s in (
        DatasetSpec("destinations", Destination, "destinations.json", True),
        DatasetSpec("places", Place, "places.json", True),
        DatasetSpec("restaurants", Restaurant, "restaurants.json", False),
        DatasetSpec("hotels", Hotel, "hotels.json", False),
        DatasetSpec("transport", TransportOption, "transport_options.json", False),
    )
}


@dataclass
class RejectedRecord:
    index: int
    record_id: str | None
    errors: list[str]


@dataclass
class LoadResult(Generic[T]):
    path: Path
    records: list[T] = field(default_factory=list)
    meta: DatasetMeta | None = None
    meta_error: str | None = None
    rejected: list[RejectedRecord] = field(default_factory=list)
    total_in_file: int = 0

    @property
    def ok(self) -> bool:
        return not self.rejected and self.meta_error is None


def format_validation_errors(exc: ValidationError) -> list[str]:
    out = []
    for e in exc.errors():
        loc = ".".join(str(p) for p in e.get("loc", ()))
        out.append(f"{loc}: {e['msg']}" if loc else str(e["msg"]))
    return out


def read_json_file(path: Path) -> Any:
    try:
        with open(path, "r", encoding="utf-8") as fh:
            return json.load(fh)
    except FileNotFoundError as exc:
        raise DataLoadError(f"dataset file not found: {path}", details={"path": str(path)}) from exc
    except json.JSONDecodeError as exc:
        raise DataLoadError(
            f"invalid JSON in {path}: {exc.msg} (line {exc.lineno}, col {exc.colno})",
            details={"path": str(path)},
        ) from exc
    except (OSError, UnicodeDecodeError) as exc:
        raise DataLoadError(f"cannot read {path}: {exc}", details={"path": str(path)}) from exc


def _split_document(doc: Any, path: Path) -> tuple[Any, list[Any]]:
    if isinstance(doc, list):
        return None, doc
    if isinstance(doc, dict):
        records = doc.get("records")
        if not isinstance(records, list):
            raise DataLoadError(f"{path}: top-level object must contain a 'records' array",
                                details={"path": str(path)})
        return doc.get("meta"), records
    raise DataLoadError(f"{path}: top level must be an object or an array", details={"path": str(path)})


def load_records(path: Path | str, model: type[T], *, strict: bool = True) -> LoadResult[T]:
    """Parse and validate every record. Duplicate ids are rejected (first one wins)."""
    path = Path(path)
    meta_raw, raw_records = _split_document(read_json_file(path), path)
    result: LoadResult[T] = LoadResult(path=path, total_in_file=len(raw_records))

    if meta_raw is not None:
        try:
            result.meta = DatasetMeta.model_validate(meta_raw)
        except ValidationError as exc:
            result.meta_error = "; ".join(format_validation_errors(exc))
        except (TypeError, ValueError) as exc:  # e.g. meta is not an object
            result.meta_error = f"meta is invalid: {exc}"

    first_seen: dict[str, int] = {}
    for idx, raw in enumerate(raw_records):
        rid = raw.get("id") if isinstance(raw, dict) else None
        rid = rid if isinstance(rid, str) else None
        if not isinstance(raw, dict):
            result.rejected.append(RejectedRecord(idx, None, ["record must be a JSON object"]))
            continue
        try:
            rec = model.model_validate(raw)
        except ValidationError as exc:
            result.rejected.append(RejectedRecord(idx, rid, format_validation_errors(exc)))
            continue
        if rec.id in first_seen:
            result.rejected.append(RejectedRecord(
                idx, rec.id, [f"duplicate id {rec.id!r} (first seen at index {first_seen[rec.id]})"]))
            continue
        first_seen[rec.id] = idx
        result.records.append(rec)

    if strict and not result.ok:
        problems = [f"{path.name}: {result.meta_error}"] if result.meta_error else []
        problems += [f"{path.name}[{r.index}] id={r.record_id!r}: {'; '.join(r.errors)}" for r in result.rejected]
        raise DataLoadError(
            f"{len(problems)} problem(s) loading {path}: " + " | ".join(problems[:5])
            + (" | ..." if len(problems) > 5 else ""),
            details={"path": str(path), "rejected": [
                {"index": r.index, "id": r.record_id, "errors": r.errors} for r in result.rejected],
                "meta_error": result.meta_error},
        )
    return result


def write_dataset_file(path: Path | str, records: list[T], meta: DatasetMeta | None = None) -> None:
    """Atomic write (temp file + replace) so a crash never leaves a half-written dataset."""
    path = Path(path)
    doc: dict[str, Any] = {}
    if meta is not None:
        doc["meta"] = meta.model_dump(mode="json")
    doc["records"] = [r.model_dump(mode="json") for r in records]
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(doc, fh, indent=2, ensure_ascii=False)
        fh.write("\n")
    os.replace(tmp, path)
