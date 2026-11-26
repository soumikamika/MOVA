"""Repository interfaces (the ONLY thing planner/business logic may depend on).

Contract notes for every implementation (JSON today, PostgreSQL later):
- Returned records are independent copies; mutating them never changes storage.
- Results are ordered by `id` so behaviour is deterministic.
- `get` returns None when missing; `require` raises NotFoundError.
- `add` raises DuplicateRecordError on an existing id; `upsert` overwrites.
- Unknown (None) attribute values are handled via the filter's `include_unknown`.
- Nothing here knows about files, SQL or any specific destination.
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import ClassVar, Generic, TypeVar

from app.core.exceptions import NotFoundError
from app.data.filters import (
    HotelFilter, PlaceFilter, RestaurantFilter, TransportFilter,
)
from app.schemas.common import DataSource, Sourced, has_development_only_data
from app.schemas.logistics import TransportOption
from app.schemas.place import Destination, Hotel, Place, Restaurant

T = TypeVar("T", bound=Sourced)


class Repository(ABC, Generic[T]):
    entity_name: ClassVar[str] = "record"

    @abstractmethod
    def get(self, record_id: str) -> T | None: ...

    @abstractmethod
    def list_all(self) -> list[T]: ...

    @abstractmethod
    def add(self, record: T) -> T: ...

    @abstractmethod
    def upsert(self, record: T) -> T: ...

    @abstractmethod
    def delete(self, record_id: str) -> bool: ...

    @abstractmethod
    def count(self) -> int: ...

    # ---- concrete helpers built on the abstract core ----
    def require(self, record_id: str) -> T:
        rec = self.get(record_id)
        if rec is None:
            raise NotFoundError(
                f"{self.entity_name} {record_id!r} not found",
                details={"entity": self.entity_name, "id": record_id},
            )
        return rec

    def exists(self, record_id: str) -> bool:
        return self.get(record_id) is not None

    def sources_in_use(self) -> set[DataSource]:
        """Provenance of everything stored (the API surfaces this on every plan)."""
        return {r.source for r in self.list_all()}


def _check_limit(limit: int | None) -> None:
    if limit is not None and limit < 1:
        raise ValueError("limit must be >= 1")


class DestinationRepository(Repository[Destination]):
    entity_name = "destination"

    @abstractmethod
    def resolve(self, query: str) -> Destination | None:
        """Exact id/name/alias lookup for user input such as 'jaipur' or 'Jaipur, India'."""

    @abstractmethod
    def search(self, text: str, *, limit: int = 10) -> list[Destination]:
        """Partial-text search over name, state and aliases."""


class PlaceRepository(Repository[Place]):
    entity_name = "place"

    @abstractmethod
    def query(self, criteria: PlaceFilter | None = None, *, limit: int | None = None) -> list[Place]: ...

    @abstractmethod
    def search(self, text: str, *, destination_id: str | None = None, limit: int = 20) -> list[Place]:
        """Free-text search over name, tags, category and description."""

    def list_by_destination(self, destination_id: str, criteria: PlaceFilter | None = None) -> list[Place]:
        base = criteria or PlaceFilter()
        return self.query(base.model_copy(update={"destination_id": destination_id}))

    def get_many(self, ids: list[str]) -> dict[str, Place]:
        """Found records only; compare with `ids` to detect missing ones."""
        found = {}
        for i in ids:
            rec = self.get(i)
            if rec is not None:
                found[i] = rec
        return found


class RestaurantRepository(Repository[Restaurant]):
    entity_name = "restaurant"

    @abstractmethod
    def query(self, criteria: RestaurantFilter | None = None, *, limit: int | None = None) -> list[Restaurant]: ...

    def list_by_destination(self, destination_id: str, criteria: RestaurantFilter | None = None) -> list[Restaurant]:
        base = criteria or RestaurantFilter()
        return self.query(base.model_copy(update={"destination_id": destination_id}))


class HotelRepository(Repository[Hotel]):
    entity_name = "hotel"

    @abstractmethod
    def query(self, criteria: HotelFilter | None = None, *, limit: int | None = None) -> list[Hotel]: ...

    def list_by_destination(self, destination_id: str, criteria: HotelFilter | None = None) -> list[Hotel]:
        base = criteria or HotelFilter()
        return self.query(base.model_copy(update={"destination_id": destination_id}))


class TransportRepository(Repository[TransportOption]):
    entity_name = "transport option"

    @abstractmethod
    def query(self, criteria: TransportFilter | None = None, *, limit: int | None = None) -> list[TransportOption]: ...

    def between(self, origin: str, destination: str, criteria: TransportFilter | None = None) -> list[TransportOption]:
        base = criteria or TransportFilter()
        return self.query(base.model_copy(update={"origin": origin, "destination": destination}))


@dataclass(frozen=True)
class Repositories:
    """What the Planner Orchestrator receives. Swap the implementations, keep the planner."""

    destinations: DestinationRepository
    places: PlaceRepository
    restaurants: RestaurantRepository
    hotels: HotelRepository
    transport: TransportRepository

    def sources_in_use(self) -> set[DataSource]:
        out: set[DataSource] = set()
        for repo in (self.destinations, self.places, self.restaurants, self.hotels, self.transport):
            out |= repo.sources_in_use()
        return out

    def has_development_only_data(self) -> bool:
        return has_development_only_data(self.sources_in_use())
