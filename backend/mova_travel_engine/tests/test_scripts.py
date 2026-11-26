import json

from scripts.generate_dev_data import main as generate_main
from scripts.validate_data import main as validate_main

FIXED = "2026-01-01T00:00:00+00:00"


def _generate(out, *extra):
    return generate_main(["--out", str(out), "--generated-at", FIXED, *extra])


def test_generate_writes_labelled_synthetic_dataset(tmp_path, capsys):
    out = tmp_path / "goa"
    assert _generate(out) == 0
    text = capsys.readouterr().out
    assert "SYNTHETIC" in text and "NOT REAL" in text
    doc = json.loads((out / "places.json").read_text(encoding="utf-8"))
    assert doc["meta"]["data_source"] == "synthetic_dev"
    assert all(r["source"] == "synthetic_dev" for r in doc["records"])


def test_generate_refuses_overwrite_then_force(tmp_path, capsys):
    out = tmp_path / "goa"
    assert _generate(out) == 0
    capsys.readouterr()
    assert _generate(out) == 2
    assert "already exist" in capsys.readouterr().err
    assert _generate(out, "--force") == 0


def test_generate_refuses_raw_directory(tmp_path, capsys):
    assert _generate(tmp_path / "raw" / "goa") == 2
    assert "raw" in capsys.readouterr().err


def test_validate_passes_on_generated_data(tmp_path, capsys):
    _generate(tmp_path / "goa")
    capsys.readouterr()
    assert validate_main(["--data-dir", str(tmp_path / "goa")]) == 0
    out = capsys.readouterr().out
    assert "PASSED" in out and "SYNTHETIC" in out and "synthetic_dev=" in out


def test_validate_json_output(tmp_path, capsys):
    _generate(tmp_path / "goa")
    capsys.readouterr()
    assert validate_main(["--data-dir", str(tmp_path / "goa"), "--json"]) == 0
    doc = json.loads(capsys.readouterr().out)
    assert doc["passed"] is True and doc["ok"] is True and doc["has_development_only_data"] is True
    assert doc["record_counts"]["destinations"] == 1


def test_validate_gates_for_production(tmp_path, capsys):
    _generate(tmp_path / "goa")
    d = str(tmp_path / "goa")
    assert validate_main(["--data-dir", d, "--fail-on-synthetic"]) == 1     # synthetic data present
    assert validate_main(["--data-dir", d, "--strict"]) == 1                # generated data has warnings (unknown hours)


def test_validate_fails_on_malformed_record(tmp_path, capsys):
    d = tmp_path / "goa"
    _generate(d)
    path = d / "places.json"
    doc = json.loads(path.read_text(encoding="utf-8"))
    del doc["records"][0]["name"]
    doc["records"][1]["source"] = "verified"
    path.write_text(json.dumps(doc), encoding="utf-8")
    capsys.readouterr()
    assert validate_main(["--data-dir", str(d)]) == 1
    out = capsys.readouterr().out
    assert "malformed_record" in out and "FAILED" in out


def test_validate_missing_directory_exit_code_2(tmp_path, capsys):
    assert validate_main(["--data-dir", str(tmp_path / "nope")]) == 2
    assert "not found" in capsys.readouterr().err
