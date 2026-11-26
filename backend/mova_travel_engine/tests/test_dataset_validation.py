import json

import pytest

from app.core.exceptions import DataLoadError
from app.data.dataset_validation import IssueSeverity, validate_collections, validate_directory
from app.data.loaders import DatasetMeta
from app.schemas.place import OpeningHours, TimeWindow
from tests.factories import (
    clean_collections, make_destination, make_hotel, make_place, make_restaurant, make_transport, write_dir,
)

E, W, I = IssueSeverity.ERROR, IssueSeverity.WARNING, IssueSeverity.INFO


def _validate(**overrides):
    c = clean_collections()
    metas = overrides.pop("metas", None)
    c.update(overrides)
    return validate_collections(**c, metas=metas)


def test_clean_dataset_passes():
    r = _validate()
    assert r.ok and r.error_count == 0 and r.warning_count == 0
    assert r.record_counts == {"destinations": 1, "places": 1, "restaurants": 1, "hotels": 1, "transport": 1}
    assert r.sources_in_use == {"synthetic_dev": 5}
    assert r.has_development_only_data is True
    assert "development_only_data" in r.codes(I)


def test_report_serialises_with_computed_fields():
    doc = _validate().model_dump(mode="json")
    assert doc["ok"] is True and doc["error_count"] == 0 and isinstance(doc["issues"], list)


# ------------------------------- emptiness -----------------------------------
def test_completely_empty_dataset():
    r = validate_collections(destinations=[], places=[], restaurants=[], hotels=[], transport=[])
    assert not r.ok
    errs = [i.entity for i in r.issues if i.code == "empty_collection" and i.severity == E]
    assert sorted(errs) == ["destinations", "places"]
    assert {i.entity for i in r.issues if i.code == "empty_collection" and i.severity == W} == \
           {"restaurants", "hotels", "transport"}
    assert r.sources_in_use == {} and r.has_development_only_data is False


def test_optional_collections_empty_is_only_a_warning():
    r = _validate(restaurants=[], hotels=[], transport=[])
    assert r.ok and r.warning_count == 3


def test_destination_without_records_warned():
    r = _validate(destinations=[make_destination(), make_destination(id="empty", name="Emptyville")])
    assert any(i.code == "destination_without_records" and i.record_id == "empty" for i in r.issues)


# ------------------------------- integrity -----------------------------------
def test_orphan_destination_is_error():
    r = _validate(places=[make_place(destination_id="ghost")])
    assert not r.ok and "orphan_destination" in r.codes(E)


def test_swapped_coordinates_is_error_and_outside_india_is_warning():
    swapped = make_place(location={"latitude": 73.8, "longitude": 15.5})
    r = _validate(places=[swapped])
    assert "swapped_coordinates" in r.codes(E)
    london = make_place(location={"latitude": 51.5, "longitude": -0.12})
    r2 = _validate(places=[london])
    assert "outside_india_bounds" in r2.codes(W) and "swapped_coordinates" not in r2.codes()


def test_far_from_destination_center_warned_and_configurable():
    far = make_place(location={"latitude": 19.0, "longitude": 73.8})      # ~390 km north
    assert "far_from_destination_center" in _validate(places=[far]).codes(W)
    r = validate_collections(**dict(clean_collections(), places=[far]), max_distance_from_center_km=1000)
    assert "far_from_destination_center" not in r.codes()


def test_duplicate_names_warned_per_destination():
    r = _validate(places=[make_place(id="a", name="Same Name"), make_place(id="b", name=" same  name ")])
    assert "duplicate_name" in r.codes(W)
    ok = _validate(places=[make_place(id="a", name="Same", destination_id="testville"),
                           make_place(id="b", name="Same", destination_id="other")])
    assert "duplicate_name" not in ok.codes()


def test_ambiguous_destination_alias_is_error():
    r = _validate(destinations=[make_destination(id="a", name="Alpha", aliases=["Shared"]),
                                make_destination(id="b", name="Beta", aliases=["shared"])],
                  places=[make_place(destination_id="a")])
    assert "ambiguous_destination_name" in r.codes(E)


def test_transport_checks():
    r = _validate(transport=[make_transport(id="t1", origin="Testville", destination="testville")])
    assert "transport_same_endpoints" in r.codes(E)
    r2 = _validate(transport=[make_transport(id="t2", destination="Atlantis")])
    assert "transport_unknown_destination" in r2.codes(W) and r2.ok


# ------------------------------- unknown / None values ------------------------
def test_unknown_values_reported_not_hidden():
    r = _validate(places=[make_place(id="a", opening_hours=None, entry_fee_inr=None, rating=None),
                          make_place(id="b", name="Known")],
                  restaurants=[make_restaurant(opening_hours=None, dietary_options=[], avg_price_per_person_inr=None)])
    assert r.ok
    assert {"unknown_opening_hours"} <= r.codes(W)
    assert {"unknown_entry_fee", "unknown_rating", "unknown_dietary_options", "unknown_price"} <= r.codes(I)
    msg = next(i.message for i in r.issues if i.code == "unknown_opening_hours" and i.entity == "place")
    assert msg.startswith("1 place record(s)") and "a" in msg


def test_unknown_tags_info():
    r = _validate(places=[make_place(tags=["beaches", "zorbing"])])
    assert "unknown_tags" in r.codes(I) and r.ok


def test_visit_longer_than_any_opening_window_warned():
    oh = OpeningHours(weekly={0: [TimeWindow(open="09:00", close="10:00")]})
    r = _validate(places=[make_place(avg_visit_minutes=120, opening_hours=oh)])
    assert "visit_longer_than_opening_window" in r.codes(W)
    fine = _validate(places=[make_place(avg_visit_minutes=45, opening_hours=oh)])
    assert "visit_longer_than_opening_window" not in fine.codes()


def test_never_open_place_warned():
    assert "never_open" in _validate(places=[make_place(closed_months=list(range(1, 13)))]).codes(W)


# ------------------------------- provenance ------------------------------------
def test_synthetic_data_must_not_claim_high_confidence():
    r = _validate(places=[make_place(confidence=0.9)])
    assert "overconfident_synthetic" in r.codes(W)


def test_mixed_sources_warned_and_real_without_last_updated_warned():
    r = _validate(places=[make_place(id="a", source="real", last_updated=None), make_place(id="b")])
    assert "mixed_sources" in r.codes(W) and "missing_last_updated" in r.codes(W)
    assert set(r.sources_in_use) == {"real", "synthetic_dev"}


def test_meta_source_mismatch_is_error():
    real_meta = DatasetMeta(dataset="x", data_source="real")
    r = _validate(metas={"places": real_meta})                 # synthetic records under a 'real' label
    assert not r.ok and "source_mismatch" in r.codes(E)
    synth_meta = DatasetMeta(dataset="x", data_source="synthetic_dev")
    assert _validate(metas={"places": synth_meta}).ok
    r2 = _validate(places=[make_place(source="real", last_updated=None)], metas={"places": synth_meta})
    assert "source_mismatch" in r2.codes(E)                     # real record hiding in a synthetic file


def test_missing_meta_and_schema_version():
    assert "missing_meta" in _validate(metas={"places": None}).codes(W)
    assert "schema_version_mismatch" in _validate(
        metas={"places": DatasetMeta(dataset="x", data_source="synthetic_dev", schema_version=99)}).codes(W)


# ------------------------------- directory validation -------------------------
def test_valid_directory_passes(tmp_path):
    r = validate_directory(write_dir(tmp_path))
    assert r.ok and r.record_counts["places"] == 1


def test_directory_missing_raises(tmp_path):
    with pytest.raises(DataLoadError):
        validate_directory(tmp_path / "nope")


def test_missing_required_and_optional_files(tmp_path):
    write_dir(tmp_path)
    (tmp_path / "places.json").unlink()
    (tmp_path / "hotels.json").unlink()
    r = validate_directory(tmp_path)
    by = {(i.code, i.entity): i.severity for i in r.issues}
    assert by[("missing_file", "places")] == E and by[("missing_file", "hotels")] == W
    assert not r.ok


def test_malformed_and_duplicate_records_reported_with_lenient_load(tmp_path):
    write_dir(tmp_path)
    path = tmp_path / "places.json"
    doc = json.loads(path.read_text(encoding="utf-8"))
    good = doc["records"][0]
    missing_name = dict(good, id="nn"); del missing_name["name"]
    bad_source = dict(good, id="bs", source="verified")
    doc["records"] += [missing_name, bad_source, dict(good)]         # last one duplicates p1
    path.write_text(json.dumps(doc), encoding="utf-8")
    r = validate_directory(tmp_path)
    assert not r.ok
    assert sum(1 for i in r.issues if i.code == "malformed_record") == 2
    assert sum(1 for i in r.issues if i.code == "duplicate_id") == 1
    assert r.record_counts["places"] == 1                             # only the valid one loaded


def test_invalid_json_file_reported_not_raised(tmp_path):
    write_dir(tmp_path)
    (tmp_path / "hotels.json").write_text("{not json", encoding="utf-8")
    r = validate_directory(tmp_path)
    assert "unreadable_file" in r.codes(E) and not r.ok
    assert not any(i.code == "empty_collection" and i.entity == "hotels" for i in r.issues)


def test_malformed_meta_reported(tmp_path):
    write_dir(tmp_path)
    path = tmp_path / "places.json"
    doc = json.loads(path.read_text(encoding="utf-8"))
    doc["meta"]["data_source"] = "verified"
    path.write_text(json.dumps(doc), encoding="utf-8")
    assert "malformed_meta" in validate_directory(tmp_path).codes(E)


def test_directory_file_declaring_real_but_containing_synthetic_fails(tmp_path):
    r = validate_directory(write_dir(tmp_path, source="real"))
    assert not r.ok and "source_mismatch" in r.codes(E)
