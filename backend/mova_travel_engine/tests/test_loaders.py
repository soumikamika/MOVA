import json

import pytest

from app.core.exceptions import DataLoadError
from app.data.loaders import DatasetMeta, load_records, read_json_file, write_dataset_file
from app.schemas.place import OpeningHours, Place, TimeWindow
from tests.factories import make_place


def _write(path, doc):
    path.write_text(json.dumps(doc), encoding="utf-8")
    return path


def _doc(*records, meta=None):
    d = {"records": list(records)}
    if meta is not None:
        d["meta"] = meta
    return d


def _valid():
    return make_place().model_dump(mode="json")


META = {"dataset": "t", "data_source": "synthetic_dev"}


# ------------------------------- happy paths -------------------------------
def test_roundtrip_with_meta(tmp_path):
    path = tmp_path / "places.json"
    write_dataset_file(path, [make_place(id="a"), make_place(id="b")], DatasetMeta(dataset="t", data_source="synthetic_dev", seed=3))
    res = load_records(path, Place)
    assert res.ok and [p.id for p in res.records] == ["a", "b"]
    assert res.meta.seed == 3 and res.meta.data_source.value == "synthetic_dev"
    assert res.total_in_file == 2


def test_bare_array_accepted_without_meta(tmp_path):
    res = load_records(_write(tmp_path / "p.json", [_valid()]), Place)
    assert len(res.records) == 1 and res.meta is None and res.ok


def test_empty_records_is_a_valid_empty_dataset(tmp_path):
    res = load_records(_write(tmp_path / "p.json", _doc(meta=META)), Place)
    assert res.records == [] and res.ok and res.total_in_file == 0


def test_unknown_values_survive_roundtrip_as_none(tmp_path):
    path = tmp_path / "p.json"
    write_dataset_file(path, [make_place(entry_fee_inr=None, opening_hours=None, rating=None)])
    p = load_records(path, Place).records[0]
    assert p.entry_fee_inr is None and p.opening_hours is None and p.rating is None   # not 0 / not {}


def test_opening_hours_roundtrip_through_json(tmp_path):
    oh = OpeningHours(weekly={2: [TimeWindow(open="09:00", close="12:00"), TimeWindow(open="15:00", close="18:00")]})
    path = tmp_path / "p.json"
    write_dataset_file(path, [make_place(opening_hours=oh)])
    back = load_records(path, Place).records[0].opening_hours
    assert back.windows_for(2) == [(540, 720), (900, 1080)] and back.windows_for(3) == []


def test_unicode_and_no_tmp_file_left_behind(tmp_path):
    path = tmp_path / "sub" / "p.json"      # parent directory is created
    write_dataset_file(path, [make_place(name="Café São Tomé")])
    assert load_records(path, Place).records[0].name == "Café São Tomé"
    assert [f.name for f in path.parent.iterdir()] == ["p.json"]


# ------------------------------- file-level errors -------------------------
def test_missing_file_raises(tmp_path):
    with pytest.raises(DataLoadError, match="not found"):
        load_records(tmp_path / "nope.json", Place)


def test_invalid_json_raises_with_position(tmp_path):
    p = tmp_path / "bad.json"
    p.write_text('{"records": [', encoding="utf-8")
    with pytest.raises(DataLoadError, match="invalid JSON"):
        read_json_file(p)


@pytest.mark.parametrize("doc", [42, "text", {"meta": {}}, {"records": "nope"}, None])
def test_wrong_top_level_shape_raises(tmp_path, doc):
    with pytest.raises(DataLoadError):
        load_records(_write(tmp_path / "p.json", doc), Place)


# ------------------------------- record-level errors -----------------------
def test_missing_required_field_rejected(tmp_path):
    bad = _valid()
    del bad["name"]
    res = load_records(_write(tmp_path / "p.json", _doc(bad, _valid())), Place, strict=False)
    assert len(res.records) == 1 and len(res.rejected) == 1
    assert res.rejected[0].index == 0 and any("name" in e for e in res.rejected[0].errors)
    assert not res.ok


def test_missing_source_rejected(tmp_path):
    bad = _valid()
    del bad["source"]
    res = load_records(_write(tmp_path / "p.json", _doc(bad)), Place, strict=False)
    assert any("source" in e for e in res.rejected[0].errors)


@pytest.mark.parametrize("value", ["verified", "REAL", "", None, 7])
def test_invalid_source_value_rejected(tmp_path, value):
    bad = _valid()
    bad["source"] = value
    res = load_records(_write(tmp_path / "p.json", _doc(bad)), Place, strict=False)
    assert res.records == [] and any("source" in e for e in res.rejected[0].errors)


def test_extra_unknown_field_rejected(tmp_path):
    bad = _valid()
    bad["colour"] = "red"
    res = load_records(_write(tmp_path / "p.json", _doc(bad)), Place, strict=False)
    assert any("colour" in e for e in res.rejected[0].errors)


def test_out_of_range_values_rejected(tmp_path):
    bad = _valid()
    bad["rating"] = 9
    bad["intensity"] = 0
    res = load_records(_write(tmp_path / "p.json", _doc(bad)), Place, strict=False)
    joined = " ".join(res.rejected[0].errors)
    assert "rating" in joined and "intensity" in joined


def test_non_object_record_rejected(tmp_path):
    res = load_records(_write(tmp_path / "p.json", _doc("oops", 5, _valid())), Place, strict=False)
    assert len(res.records) == 1 and [r.index for r in res.rejected] == [0, 1]
    assert res.rejected[0].record_id is None


def test_duplicate_ids_first_wins_rest_rejected(tmp_path):
    a, b = _valid(), _valid()
    b["name"] = "Second"
    res = load_records(_write(tmp_path / "p.json", _doc(a, b)), Place, strict=False)
    assert len(res.records) == 1 and res.records[0].name == "Test Beach"
    assert "duplicate id" in res.rejected[0].errors[0] and res.rejected[0].record_id == "p1"


def test_strict_mode_raises_and_reports_details(tmp_path):
    bad = _valid()
    del bad["name"]
    with pytest.raises(DataLoadError, match="p1") as ei:
        load_records(_write(tmp_path / "p.json", _doc(bad)), Place, strict=True)
    assert ei.value.details["rejected"][0]["index"] == 0


def test_invalid_meta_reported_and_strict_raises(tmp_path):
    path = _write(tmp_path / "p.json", _doc(_valid(), meta={"dataset": "t", "data_source": "verified"}))
    res = load_records(path, Place, strict=False)
    assert res.meta is None and "data_source" in res.meta_error and not res.ok and len(res.records) == 1
    with pytest.raises(DataLoadError, match="data_source"):
        load_records(path, Place, strict=True)


def test_meta_that_is_not_an_object_is_reported(tmp_path):
    res = load_records(_write(tmp_path / "p.json", _doc(_valid(), meta="oops")), Place, strict=False)
    assert res.meta is None and res.meta_error
