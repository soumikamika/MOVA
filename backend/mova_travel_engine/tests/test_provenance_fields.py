"""Phase B additions to the Phase A `Sourced` base: last_updated and confidence."""
import pytest
from pydantic import ValidationError

from tests.factories import make_place


def test_last_updated_and_confidence_default_to_none():
    p = make_place(last_updated=None, confidence=None)
    assert p.last_updated is None and p.confidence is None


def test_last_updated_parses_iso_string():
    p = make_place(last_updated="2026-03-01T10:30:00+00:00")
    assert p.last_updated.year == 2026 and p.last_updated.hour == 10


@pytest.mark.parametrize("bad", [-0.1, 1.5])
def test_confidence_must_be_between_0_and_1(bad):
    with pytest.raises(ValidationError, match="confidence"):
        make_place(confidence=bad)


def test_invalid_last_updated_rejected():
    with pytest.raises(ValidationError, match="last_updated"):
        make_place(last_updated="not-a-date")


@pytest.mark.parametrize("bad", ["verified", "REAL", "", "synthetic"])
def test_invalid_source_value_rejected(bad):
    with pytest.raises(ValidationError, match="source"):
        make_place(source=bad)
