"""Thread-safe in-memory collection with optional JSON-file persistence."""
from collections.abc import Callable, Iterable
from pathlib import Path
from threading import RLock
from typing import Generic, TypeVar

from app.core.exceptions import DataLoadError, DuplicateRecordError
from app.data.loaders import DatasetMeta, LoadResult, load_records, write_dataset_file
from app.schemas.common import Sourced

T = TypeVar("T", bound=Sourced)


class JsonCollectionStore(Generic[T]):
    """Holds validated records by id.

    - path=None -> purely in-memory (tests, mocks).
    - Reads return deep copies; writes re-validate, so an invalid record can
      never be persisted and break the next load.
    - A failed disk write rolls the in-memory change back.
    - Single-process safe (RLock). Multi-process access is out of scope for JSON.
    """

    def __init__(
        self, model: type[T], path: Path | str | None = None, *,
        records: Iterable[T] = (), meta: DatasetMeta | None = None,
        strict: bool = True, missing_ok: bool = False, persist: bool = True,
    ):
        self._model = model
        self._path = Path(path) if path is not None else None
        self._persist = persist
        self._meta = meta
        self._lock = RLock()
        self._items: dict[str, T] = {}
        self.load_report: LoadResult[T] | None = None

        initial = list(records)
        if self._path is not None and self._path.exists():
            if initial:
                raise ValueError("pass either an existing path or initial records, not both")
            self.load_report = load_records(self._path, model, strict=strict)
            self._meta = self.load_report.meta
            self._items = {r.id: r for r in self.load_report.records}
        else:
            if self._path is not None and not missing_ok:
                raise DataLoadError(f"dataset file not found: {self._path}", details={"path": str(self._path)})
            for r in initial:
                self._items_put(r, overwrite=False)

    # ---- helpers ----
    def _validated_copy(self, record: T) -> T:
        if not isinstance(record, self._model):
            raise TypeError(f"expected {self._model.__name__}, got {type(record).__name__}")
        return self._model.model_validate(record.model_dump())

    def _items_put(self, record: T, *, overwrite: bool) -> T:
        rec = self._validated_copy(record)
        if not overwrite and rec.id in self._items:
            raise DuplicateRecordError(f"{self._model.__name__} id {rec.id!r} already exists",
                                       details={"id": rec.id})
        self._items[rec.id] = rec
        return rec

    def _flush(self) -> None:
        if self._persist and self._path is not None:
            write_dataset_file(self._path, list(self._items.values()), self._meta)

    # ---- public API ----
    @property
    def meta(self) -> DatasetMeta | None:
        return self._meta

    @meta.setter
    def meta(self, value: DatasetMeta | None) -> None:
        self._meta = value

    def __len__(self) -> int:
        return len(self._items)

    def get(self, record_id: str) -> T | None:
        with self._lock:
            rec = self._items.get(record_id)
            return rec.model_copy(deep=True) if rec is not None else None

    def scan(self, predicate: Callable[[T], bool] | None = None) -> list[T]:
        """Copies of all matching records, ordered by id."""
        with self._lock:
            return [r.model_copy(deep=True) for _, r in sorted(self._items.items())
                    if predicate is None or predicate(r)]

    def put(self, record: T, *, overwrite: bool) -> T:
        with self._lock:
            previous = self._items.get(getattr(record, "id", None))
            rec = self._items_put(record, overwrite=overwrite)
            try:
                self._flush()
            except Exception:
                if previous is None:
                    self._items.pop(rec.id, None)
                else:
                    self._items[rec.id] = previous
                raise
            return rec.model_copy(deep=True)

    def delete(self, record_id: str) -> bool:
        with self._lock:
            previous = self._items.pop(record_id, None)
            if previous is None:
                return False
            try:
                self._flush()
            except Exception:
                self._items[record_id] = previous
                raise
            return True

    def save(self) -> None:
        if self._path is None:
            raise ValueError("this store has no file path")
        with self._lock:
            write_dataset_file(self._path, list(self._items.values()), self._meta)
