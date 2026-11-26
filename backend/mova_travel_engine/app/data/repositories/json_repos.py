"""JSON-backed repository implementations (development / small deployments).

Business logic must depend on `base.py` only. Replacing these with PostgreSQL
means writing new classes that implement the same abstract interfaces.
"""
from collections.abc import Iterable
from pathlib import Path
from typing import Generic, TypeVar

from app.data.filters import (
    HotelFilter, PlaceFilter, RestaurantFilter, TransportFilter,
    match_destination, normalize_name, rank_text_matches,
)
from app.data.json_store import JsonCollectionStore
from app.data.loaders import DATASET_SPECS
from app.data.repositories.base import (
    DestinationRepository, HotelRepository, PlaceRepository, Repositories,
    RestaurantRepository, TransportRepository, _check_limit,
)
from app.schemas.common import Sourced
from app.schemas.logistics import TransportOption
from app.schemas.place import Destination, Hotel, Place, Restaurant

T = TypeVar("T", bound=Sourced)


class _JsonBacked(Generic[T]):
    """Shared CRUD core; listed FIRST in each class's bases so it satisfies the ABC."""

    def __init__(self, store: JsonCollectionStore[T]):
        self._store = store

    @property
    def store(self) -> JsonCollectionStore[T]:
        return self._store

    def get(self, record_id: str) -> T | None:
        return self._store.get(record_id)

    def list_all(self) -> list[T]:
        return self._store.scan()

    def add(self, record: T) -> T:
        return self._store.put(record, overwrite=False)

    def upsert(self, record: T) -> T:
        return self._store.put(record, overwrite=True)

    def delete(self, record_id: str) -> bool:
        return self._store.delete(record_id)

    def count(self) -> int:
        return len(self._store)

    def _query(self, criteria, limit: int | None) -> list[T]:
        _check_limit(limit)
        found = self._store.scan(criteria.matches if criteria is not None else None)
        return found if limit is None else found[:limit]


class JsonDestinationRepository(_JsonBacked[Destination], DestinationRepository):
    def resolve(self, query: str) -> Destination | None:
        found = match_destination(query, self._store.scan())
        return found

    def search(self, text: str, *, limit: int = 10) -> list[Destination]:
        _check_limit(limit)
        return rank_text_matches(
            self._store.scan(), text, name=lambda d: d.name,
            haystack=lambda d: " ".join([d.id, d.name, d.state or "", *d.aliases]), limit=limit)


class JsonPlaceRepository(_JsonBacked[Place], PlaceRepository):
    def query(self, criteria: PlaceFilter | None = None, *, limit: int | None = None) -> list[Place]:
        return self._query(criteria, limit)

    def search(self, text: str, *, destination_id: str | None = None, limit: int = 20) -> list[Place]:
        _check_limit(limit)
        pool = self._store.scan(None if destination_id is None else (lambda p: p.destination_id == destination_id))
        return rank_text_matches(
            pool, text, name=lambda p: p.name,
            haystack=lambda p: " ".join([p.name, p.category.value, *p.tags, p.description or ""]), limit=limit)


class JsonRestaurantRepository(_JsonBacked[Restaurant], RestaurantRepository):
    def query(self, criteria: RestaurantFilter | None = None, *, limit: int | None = None) -> list[Restaurant]:
        return self._query(criteria, limit)


class JsonHotelRepository(_JsonBacked[Hotel], HotelRepository):
    def query(self, criteria: HotelFilter | None = None, *, limit: int | None = None) -> list[Hotel]:
        return self._query(criteria, limit)


class JsonTransportRepository(_JsonBacked[TransportOption], TransportRepository):
    def query(self, criteria: TransportFilter | None = None, *, limit: int | None = None) -> list[TransportOption]:
        return self._query(criteria, limit)


def load_json_repositories(
    directory: Path | str, *, strict: bool = True, missing_ok: bool = False, persist: bool = True,
) -> Repositories:
    """Load a dataset directory (see DATASET_SPECS for file names).

    strict=True  -> any malformed record/meta raises DataLoadError.
    missing_ok   -> absent files become empty collections instead of errors.
    """
    d = Path(directory)
    if not d.is_dir():
        from app.core.exceptions import DataLoadError
        raise DataLoadError(f"dataset directory not found: {d}", details={"path": str(d)})

    def store(name: str) -> JsonCollectionStore:
        spec = DATASET_SPECS[name]
        return JsonCollectionStore(spec.model, d / spec.filename, strict=strict,
                                   missing_ok=missing_ok, persist=persist)

    return Repositories(
        destinations=JsonDestinationRepository(store("destinations")),
        places=JsonPlaceRepository(store("places")),
        restaurants=JsonRestaurantRepository(store("restaurants")),
        hotels=JsonHotelRepository(store("hotels")),
        transport=JsonTransportRepository(store("transport")),
    )


def json_repositories_in_memory(
    *, destinations: Iterable[Destination] = (), places: Iterable[Place] = (),
    restaurants: Iterable[Restaurant] = (), hotels: Iterable[Hotel] = (),
    transport: Iterable[TransportOption] = (),
) -> Repositories:
    """Non-persistent repositories (tests, mocks, previews)."""
    return Repositories(
        destinations=JsonDestinationRepository(JsonCollectionStore(Destination, records=destinations)),
        places=JsonPlaceRepository(JsonCollectionStore(Place, records=places)),
        restaurants=JsonRestaurantRepository(JsonCollectionStore(Restaurant, records=restaurants)),
        hotels=JsonHotelRepository(JsonCollectionStore(Hotel, records=hotels)),
        transport=JsonTransportRepository(JsonCollectionStore(TransportOption, records=transport)),
    )
