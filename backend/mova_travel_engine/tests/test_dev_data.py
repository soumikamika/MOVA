import datetime as dt
from pathlib import Path

import pytest

from app.data.dev_data import DISCLAIMER, generate_goa_dev_dataset, write_dev_dataset
from app.data.filters import PlaceFilter, RestaurantFilter
from app.data.repositories import load_json_repositories

FIXED = dt.datetime(2026, 1, 1, tzinfo=dt.timezone.utc)
ROOT = Path(__file__).resolve().parents[1]


def _ds(seed=42):
    return generate_goa_dev_dataset(seed=seed, generated_at=FIXED)


def _all(ds):
    return [r for recs in ds.collections().values() for r in recs]


def test_every_record_is_explicitly_synthetic_dev():
    ds = _ds()
    assert len(_all(ds)) > 50
    assert all(r.source.value == "synthetic_dev" for r in _all(ds))
    for recs in ds.collections().values():                    # also in the serialised form
        assert all(r.model_dump(mode="json")["source"] == "synthetic_dev" for r in recs)


def test_every_record_carries_last_updated_and_low_confidence():
    for r in _all(_ds()):
        assert r.last_updated == FIXED
        assert r.confidence is not None and r.confidence <= 0.3


def test_metas_declare_synthetic_and_carry_disclaimer():
    ds = _ds()
    assert set(ds.metas) == {"destinations", "places", "restaurants", "hotels", "transport"}
    for m in ds.metas.values():
        assert m.data_source.value == "synthetic_dev" and m.seed == 42
        assert "NOT REAL" in m.disclaimer and m.disclaimer == DISCLAIMER


def test_generated_dataset_passes_its_own_validation():
    r = _ds().validate()
    assert r.ok and r.error_count == 0
    assert r.has_development_only_data and set(r.sources_in_use) == {"synthetic_dev"}


def test_deterministic_for_same_seed_and_different_for_other_seed():
    dump = lambda ds: {k: [x.model_dump(mode="json") for x in v] for k, v in ds.collections().items()}  # noqa: E731
    assert dump(_ds(1)) == dump(_ds(1))
    assert dump(_ds(1)) != dump(_ds(2))


def test_ids_are_unique_and_sizes_are_small():
    ds = _ds()
    for name, recs in ds.collections().items():
        ids = [r.id for r in recs]
        assert len(ids) == len(set(ids)), name
    assert len(ds.destinations) == 1 and 20 <= len(ds.places) <= 40
    assert 10 <= len(ds.restaurants) <= 30 and 8 <= len(ds.hotels) <= 20 and len(ds.transport) >= 8


def test_fictional_businesses_are_visibly_marked():
    ds = _ds()
    assert all(r.name.startswith("DEV ") for r in ds.restaurants + ds.hotels)
    assert all("SYNTHETIC" in p.description for p in ds.places)


def test_contains_unknown_values_to_exercise_the_engine():
    ds = _ds()
    assert any(p.opening_hours is None for p in ds.places)
    assert any(p.entry_fee_inr is None for p in ds.places)
    assert any(p.rating is None for p in ds.places)
    assert any(p.family_friendly is None for p in ds.places)


def test_geography_spans_north_and_south_for_clustering_tests():
    lats = [p.location.latitude for p in _ds().places]
    assert max(lats) - min(lats) > 0.5


def test_seasonality_split_windows_and_single_day_markets_present():
    ds = _ds()
    falls = next(p for p in ds.places if "dudhsagar" in p.id)
    assert 7 in falls.closed_months
    assert any(len(p.opening_hours.windows_for(0)) == 2 for p in ds.places if p.opening_hours)   # midday break
    assert any(p.opening_hours and p.opening_hours.windows_for(2) and not p.opening_hours.windows_for(0)
               for p in ds.places)                                                               # Wednesday only


def test_vegetarian_options_exist_and_hotel_categories_cover_all_levels():
    ds = _ds()
    repos = ds.repositories()
    veg = repos.restaurants.query(RestaurantFilter(dietary_all=["vegetarian"], include_unknown=False))
    assert len({r.id.split("_")[2] for r in veg}) >= 5
    assert {h.category.value for h in ds.hotels} == {"budget", "midrange", "premium", "luxury"}


def test_flagging_lets_callers_exclude_all_synthetic_data():
    repos = _ds().repositories()
    assert repos.has_development_only_data() is True
    assert repos.places.query(PlaceFilter(exclude_development_only=True)) == []
    assert repos.destinations.resolve("goa").id == "goa"
    assert repos.destinations.resolve("Goa, India").id == "goa"


def test_write_and_reload_roundtrip(tmp_path):
    ds = _ds()
    paths = write_dev_dataset(ds, tmp_path / "goa")
    assert len(paths) == 5 and all(p.exists() for p in paths)
    repos = load_json_repositories(tmp_path / "goa")
    assert repos.places.count() == len(ds.places) and repos.hotels.count() == len(ds.hotels)
    assert {s.value for s in repos.sources_in_use()} == {"synthetic_dev"}
    assert repos.places.get("goa_dudhsagar_falls").closed_months == [6, 7, 8, 9]


def test_refuses_overwrite_without_force_and_raw_directory(tmp_path):
    write_dev_dataset(_ds(), tmp_path / "goa")
    with pytest.raises(FileExistsError):
        write_dev_dataset(_ds(), tmp_path / "goa")
    write_dev_dataset(_ds(), tmp_path / "goa", force=True)
    with pytest.raises(ValueError, match="raw"):
        write_dev_dataset(_ds(), tmp_path / "raw" / "goa")


def test_no_itineraries_in_generated_data():
    ds = _ds()
    assert not hasattr(ds, "itinerary") and "days" not in ds.collections()


def test_engine_code_is_destination_agnostic():
    """Only the dev-data module may mention Goa; nothing in the engine may import it."""
    offenders = []
    for path in (ROOT / "app").rglob("*.py"):
        if path.name == "dev_data.py":
            continue
        text = path.read_text(encoding="utf-8")
        if "goa" in text.lower() or "dev_data" in text:
            offenders.append(str(path.relative_to(ROOT)))
    assert offenders == []
