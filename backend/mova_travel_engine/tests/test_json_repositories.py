from unittest import mock

import pytest
from pydantic import ValidationError

from app.core.exceptions import DataLoadError, DuplicateRecordError, NotFoundError
from app.data.filters import HotelFilter, PlaceFilter, RestaurantFilter, TransportFilter
from app.data.repositories import (
    DestinationRepository, HotelRepository, PlaceRepository, Repositories, Repository,
    RestaurantRepository, TransportRepository, json_repositories_in_memory, load_json_repositories,
)
from app.data.repositories.json_repos import JsonPlaceRepository
from app.data.json_store import JsonCollectionStore
from app.schemas.place import Hotel, Place
from tests.factories import (
    make_destination, make_hotel, make_place, make_repos, make_restaurant, make_transport, write_dir,
)


# ------------------------------ interfaces ---------------------------------
def test_abstract_interfaces_cannot_be_instantiated():
    for cls in (Repository, DestinationRepository, PlaceRepository, RestaurantRepository,
                HotelRepository, TransportRepository):
        with pytest.raises(TypeError):
            cls()


def test_json_repos_implement_the_interfaces():
    r = make_repos()
    assert isinstance(r.destinations, DestinationRepository)
    assert isinstance(r.places, PlaceRepository)
    assert isinstance(r.restaurants, RestaurantRepository)
    assert isinstance(r.hotels, HotelRepository)
    assert isinstance(r.transport, TransportRepository)


class _ListHotelRepo(HotelRepository):
    """A non-JSON implementation, to prove business logic depends only on the interface."""

    def __init__(self, hotels): self._h = {h.id: h for h in hotels}
    def get(self, record_id): return self._h.get(record_id)
    def list_all(self): return sorted(self._h.values(), key=lambda h: h.id)
    def add(self, record): self._h[record.id] = record; return record
    def upsert(self, record): self._h[record.id] = record; return record
    def delete(self, record_id): return self._h.pop(record_id, None) is not None
    def count(self): return len(self._h)
    def query(self, criteria=None, *, limit=None):
        out = [h for h in self.list_all() if criteria is None or criteria.matches(h)]
        return out if limit is None else out[:limit]


def _cheapest_hotel(hotels: HotelRepository, destination_id: str):
    """Stand-in for planner logic: only uses the HotelRepository interface."""
    found = hotels.list_by_destination(destination_id, HotelFilter(min_occupancy_per_room=2))
    return min(found, key=lambda h: h.price_per_night_inr) if found else None


def test_planner_style_logic_works_with_any_implementation():
    data = [make_hotel(id="a", price_per_night_inr=5000), make_hotel(id="b", price_per_night_inr=2000)]
    json_repo = json_repositories_in_memory(hotels=data).hotels
    assert _cheapest_hotel(json_repo, "testville").id == "b"
    assert _cheapest_hotel(_ListHotelRepo(data), "testville").id == "b"
    assert _cheapest_hotel(_ListHotelRepo([]), "testville") is None


# ------------------------------ CRUD ---------------------------------------
def test_get_require_exists_count():
    repo = make_repos().places
    assert repo.get("p1").name == "Test Beach"
    assert repo.get("nope") is None and repo.exists("p1") and not repo.exists("nope")
    assert repo.count() == 1
    with pytest.raises(NotFoundError, match="nope"):
        repo.require("nope")


def test_add_duplicate_raises_but_upsert_overwrites():
    repo = make_repos().places
    with pytest.raises(DuplicateRecordError):
        repo.add(make_place(id="p1", name="Other"))
    assert repo.get("p1").name == "Test Beach"
    repo.upsert(make_place(id="p1", name="Renamed"))
    assert repo.get("p1").name == "Renamed" and repo.count() == 1
    repo.add(make_place(id="p2"))
    assert repo.count() == 2


def test_delete():
    repo = make_repos().places
    assert repo.delete("p1") is True
    assert repo.delete("p1") is False
    assert repo.count() == 0 and repo.get("p1") is None


def test_returned_records_are_copies():
    repo = make_repos().places
    p = repo.get("p1")
    p.name = "MUTATED"
    p.tags.append("hacked")
    assert repo.get("p1").name == "Test Beach" and "hacked" not in repo.get("p1").tags
    repo.list_all()[0].name = "MUTATED"
    assert repo.get("p1").name == "Test Beach"


def test_wrong_type_and_invalid_mutated_record_rejected():
    repo = make_repos().places
    with pytest.raises(TypeError):
        repo.add(make_hotel())
    bad = make_place(id="bad")
    bad.rating = 99          # attribute assignment bypasses validation ...
    with pytest.raises(ValidationError):
        repo.add(bad)        # ... but the repository re-validates before storing
    assert not repo.exists("bad")


def test_list_all_ordered_by_id():
    repo = json_repositories_in_memory(places=[make_place(id="c"), make_place(id="a"), make_place(id="b")]).places
    assert [p.id for p in repo.list_all()] == ["a", "b", "c"]


def test_duplicate_ids_in_initial_records_rejected():
    with pytest.raises(DuplicateRecordError):
        json_repositories_in_memory(places=[make_place(id="x"), make_place(id="x")])


# ------------------------------ destinations --------------------------------
def test_destination_resolve_and_search_multiple_destinations():
    repos = json_repositories_in_memory(destinations=[
        make_destination(id="testville", name="Testville", aliases=["Test City"], state="Testland"),
        make_destination(id="otherton", name="Otherton", state="Testland"),
    ])
    d = repos.destinations
    assert d.resolve("TESTVILLE").id == "testville"
    assert d.resolve("test city").id == "testville"
    assert d.resolve("otherton").id == "otherton"
    assert d.resolve("Goa") is None and d.resolve("") is None
    assert [x.id for x in d.search("test")] == ["testville", "otherton"]   # name-prefix beats state match
    assert [x.id for x in d.search("other")] == ["otherton"]
    assert d.search("   ") == []
    with pytest.raises(ValueError):
        d.search("x", limit=0)


# ------------------------------ places --------------------------------------
def _multi_dest_places():
    return json_repositories_in_memory(places=[
        make_place(id="a1", destination_id="a", name="Alpha Beach", category="beach", tags=["beaches"], rating=4.5),
        make_place(id="a2", destination_id="a", name="Alpha Fort", category="historical", tags=["history"], rating=None),
        make_place(id="b1", destination_id="b", name="Beta Beach", category="beach", tags=["beaches", "crowds"], rating=3.0),
    ]).places


def test_list_by_destination_isolates_destinations():
    repo = _multi_dest_places()
    assert [p.id for p in repo.list_by_destination("a")] == ["a1", "a2"]
    assert [p.id for p in repo.list_by_destination("b")] == ["b1"]
    assert repo.list_by_destination("zzz") == []


def test_query_with_filters_and_limit():
    repo = _multi_dest_places()
    assert [p.id for p in repo.query(PlaceFilter(categories={"beach"}))] == ["a1", "b1"]
    assert [p.id for p in repo.query(PlaceFilter(tags_exclude=["crowds"]))] == ["a1", "a2"]
    assert [p.id for p in repo.list_by_destination("a", PlaceFilter(min_rating=4))] == ["a1", "a2"]       # None kept
    assert [p.id for p in repo.list_by_destination("a", PlaceFilter(min_rating=4, include_unknown=False))] == ["a1"]
    assert len(repo.query(limit=2)) == 2 and len(repo.query()) == 3
    with pytest.raises(ValueError):
        repo.query(limit=0)


def test_list_by_destination_does_not_mutate_callers_criteria():
    repo = _multi_dest_places()
    crit = PlaceFilter(categories={"beach"})
    repo.list_by_destination("a", crit)
    assert crit.destination_id is None


def test_place_search():
    repo = _multi_dest_places()
    assert [p.id for p in repo.search("beach")] == ["a1", "b1"]
    assert [p.id for p in repo.search("beach", destination_id="b")] == ["b1"]
    assert [p.id for p in repo.search("history")] == ["a2"]      # matches tags
    assert repo.search("zzz") == [] and repo.search("  ") == []
    assert len(repo.search("beach", limit=1)) == 1


def test_get_many_returns_found_only():
    repo = _multi_dest_places()
    found = repo.get_many(["a1", "missing", "b1"])
    assert set(found) == {"a1", "b1"} and repo.get_many([]) == {}


# ------------------------- restaurants / hotels / transport -----------------
def test_restaurant_queries():
    repos = json_repositories_in_memory(restaurants=[
        make_restaurant(id="r1", dietary_options=["vegetarian"]),
        make_restaurant(id="r2", dietary_options=["non_vegetarian"]),
        make_restaurant(id="r3", destination_id="other", dietary_options=["vegetarian"]),
    ])
    veg = repos.restaurants.list_by_destination("testville", RestaurantFilter(dietary_all=["vegetarian"]))
    assert [r.id for r in veg] == ["r1"]
    assert len(repos.restaurants.query()) == 3


def test_hotel_queries():
    repos = json_repositories_in_memory(hotels=[
        make_hotel(id="h1", category="budget", price_per_night_inr=1500),
        make_hotel(id="h2", category="luxury", price_per_night_inr=20000),
    ])
    assert [h.id for h in repos.hotels.query(HotelFilter(max_price_per_night_inr=5000))] == ["h1"]
    assert [h.id for h in repos.hotels.list_by_destination("testville", HotelFilter(categories={"luxury"}))] == ["h2"]


def test_transport_between():
    repos = json_repositories_in_memory(transport=[
        make_transport(id="t1", origin="Mumbai", mode="train"),
        make_transport(id="t2", origin="Mumbai", mode="flight"),
        make_transport(id="t3", origin="Pune", mode="bus"),
    ])
    assert [t.id for t in repos.transport.between("mumbai", "TESTVILLE")] == ["t1", "t2"]
    assert [t.id for t in repos.transport.between("Mumbai", "Testville", TransportFilter(modes={"flight"}))] == ["t2"]
    assert repos.transport.between("Delhi", "Testville") == []


# ------------------------------ empty datasets ------------------------------
def test_empty_repositories_behave_sanely():
    r = json_repositories_in_memory()
    for repo in (r.destinations, r.places, r.restaurants, r.hotels, r.transport):
        assert repo.count() == 0 and repo.list_all() == [] and repo.get("x") is None
        assert repo.sources_in_use() == set()
    assert r.places.query() == [] and r.places.search("beach") == []
    assert r.destinations.resolve("goa") is None and r.destinations.search("g") == []
    assert r.hotels.list_by_destination("x") == [] and r.transport.between("a", "b") == []
    assert r.sources_in_use() == set() and r.has_development_only_data() is False


# ------------------------------ provenance ----------------------------------
def test_sources_in_use_and_development_flag():
    real_only = make_repos(places=[make_place(source="real")], destinations=[make_destination(source="real")],
                           restaurants=[], hotels=[], transport=[])
    assert real_only.has_development_only_data() is False
    mixed = make_repos(places=[make_place(source="real")])
    assert "synthetic_dev" in {s.value for s in mixed.sources_in_use()}
    assert mixed.has_development_only_data() is True
    assert {s.value for s in mixed.places.sources_in_use()} == {"real"}


# ------------------------------ persistence ---------------------------------
def test_load_directory_and_persist_changes(tmp_path):
    write_dir(tmp_path)
    repos = load_json_repositories(tmp_path)
    assert repos.places.count() == 1 and repos.destinations.resolve("testville") is not None
    repos.places.add(make_place(id="p2", name="Second"))
    repos.places.delete("p1")
    again = load_json_repositories(tmp_path)               # fresh load from disk
    assert [p.id for p in again.places.list_all()] == ["p2"]


def test_persist_false_does_not_touch_disk(tmp_path):
    write_dir(tmp_path)
    repos = load_json_repositories(tmp_path, persist=False)
    repos.places.add(make_place(id="p2"))
    assert repos.places.count() == 2
    assert load_json_repositories(tmp_path).places.count() == 1


def test_failed_write_rolls_back_memory(tmp_path):
    write_dir(tmp_path)
    repos = load_json_repositories(tmp_path)
    with mock.patch("app.data.json_store.write_dataset_file", side_effect=OSError("disk full")):
        with pytest.raises(OSError):
            repos.places.add(make_place(id="p2"))
        with pytest.raises(OSError):
            repos.places.delete("p1")
    assert not repos.places.exists("p2") and repos.places.exists("p1")


def test_metadata_is_preserved_on_save(tmp_path):
    write_dir(tmp_path)
    repos = load_json_repositories(tmp_path)
    assert repos.places.store.meta.data_source.value == "synthetic_dev"
    repos.places.add(make_place(id="p2"))
    assert load_json_repositories(tmp_path).places.store.meta.dataset == "test"


def test_missing_directory_and_files(tmp_path):
    with pytest.raises(DataLoadError, match="directory"):
        load_json_repositories(tmp_path / "nope")
    (tmp_path / "empty").mkdir()
    with pytest.raises(DataLoadError, match="not found"):
        load_json_repositories(tmp_path / "empty")
    repos = load_json_repositories(tmp_path / "empty", missing_ok=True)
    assert repos.places.count() == 0
    repos.places.add(make_place())                            # creates places.json on first write
    assert (tmp_path / "empty" / "places.json").exists()


def test_malformed_record_strict_vs_lenient(tmp_path):
    write_dir(tmp_path)
    import json
    path = tmp_path / "places.json"
    doc = json.loads(path.read_text(encoding="utf-8"))
    bad = dict(doc["records"][0], id="bad")
    del bad["name"]
    doc["records"].append(bad)
    path.write_text(json.dumps(doc), encoding="utf-8")
    with pytest.raises(DataLoadError):
        load_json_repositories(tmp_path)
    lenient = load_json_repositories(tmp_path, strict=False)
    assert [p.id for p in lenient.places.list_all()] == ["p1"]
    assert len(lenient.places.store.load_report.rejected) == 1


def test_store_rejects_records_plus_existing_path(tmp_path):
    write_dir(tmp_path)
    with pytest.raises(ValueError):
        JsonCollectionStore(Place, tmp_path / "places.json", records=[make_place()])


def test_place_repository_is_a_place_repository():
    repo = JsonPlaceRepository(JsonCollectionStore(Place))
    assert isinstance(repo, PlaceRepository) and repo.count() == 0
