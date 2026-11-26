"""Plain builders for valid records. Uses a fictional destination on purpose: the
data layer must not depend on any real destination."""
import datetime as dt
from pathlib import Path

from app.data.loaders import DATASET_SPECS, DatasetMeta, write_dataset_file
from app.data.repositories.json_repos import json_repositories_in_memory
from app.schemas.logistics import TransportOption
from app.schemas.place import Destination, Hotel, OpeningHours, Place, Restaurant

TS = dt.datetime(2026, 1, 1, tzinfo=dt.timezone.utc)
CENTER = {"latitude": 15.5, "longitude": 73.8}


def _merge(base: dict, kw: dict) -> dict:
    base.update(kw)
    return base


def make_destination(**kw) -> Destination:
    return Destination(**_merge(dict(id="testville", name="Testville", center=CENTER,
                                     source="synthetic_dev", last_updated=TS, confidence=0.3), kw))


def make_place(**kw) -> Place:
    return Place(**_merge(dict(
        id="p1", destination_id="testville", name="Test Beach", category="beach", location=CENTER,
        avg_visit_minutes=60, intensity=2, tags=["beaches"], rating=4.0, entry_fee_inr=0,
        opening_hours=OpeningHours.daily("08:00", "20:00"), source="synthetic_dev",
        last_updated=TS, confidence=0.2), kw))


def make_restaurant(**kw) -> Restaurant:
    return Restaurant(**_merge(dict(
        id="r1", destination_id="testville", name="Test Diner", location=CENTER, cuisines=["indian"],
        dietary_options=["vegetarian"], serves=["lunch", "dinner"], avg_price_per_person_inr=300,
        rating=4.0, opening_hours=OpeningHours.daily("11:00", "23:00"), source="synthetic_dev",
        last_updated=TS, confidence=0.1), kw))


def make_hotel(**kw) -> Hotel:
    return Hotel(**_merge(dict(
        id="h1", destination_id="testville", name="Test Stay", category="midrange", location=CENTER,
        price_per_night_inr=3000, max_occupancy_per_room=3, rating=4.0, amenities=["wifi", "pool"],
        source="synthetic_dev", last_updated=TS, confidence=0.1), kw))


def make_transport(**kw) -> TransportOption:
    return TransportOption(**_merge(dict(
        id="t1", mode="train", origin="Mumbai", destination="Testville", duration_minutes=600,
        price_per_person_inr=900, source="synthetic_dev", last_updated=TS, confidence=0.2), kw))


def clean_collections() -> dict[str, list]:
    return {"destinations": [make_destination()], "places": [make_place()],
            "restaurants": [make_restaurant()], "hotels": [make_hotel()], "transport": [make_transport()]}


def make_repos(**overrides):
    """In-memory repositories pre-filled with one valid record each (override any collection)."""
    c = clean_collections()
    c.update(overrides)
    return json_repositories_in_memory(**c)


def write_dir(path: Path, source: str = "synthetic_dev", **overrides) -> Path:
    """Write a dataset directory using the real file format."""
    c = clean_collections()
    c.update(overrides)
    meta = DatasetMeta(dataset="test", data_source=source)
    for name, spec in DATASET_SPECS.items():
        write_dataset_file(path / spec.filename, c[name], meta)
    return path
