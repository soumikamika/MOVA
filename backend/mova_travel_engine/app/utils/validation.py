"""Text / tag normalisation shared by schemas and data validation scripts."""
import re
from collections.abc import Iterable

from app.core.vocabulary import CANONICAL_TAGS, TAG_SYNONYMS

_WS_RE = re.compile(r"\s+")
_SEP_RE = re.compile(r"[\s\-/]+")
_JUNK_RE = re.compile(r"[^a-z0-9_]")
_MULTI_US_RE = re.compile(r"_+")


def normalize_text(value: str) -> str:
    """Trim and collapse internal whitespace."""
    return _WS_RE.sub(" ", value).strip()


def normalize_tag(value: str) -> str:
    """'Water Sports' -> 'water_sports'; 'Beach' -> 'beaches' (via synonyms)."""
    t = _SEP_RE.sub("_", value.strip().lower())
    t = _JUNK_RE.sub("", t)
    t = _MULTI_US_RE.sub("_", t).strip("_")
    return TAG_SYNONYMS.get(t, t)


def normalize_tags(values: Iterable[str]) -> list[str]:
    """Normalise, drop empties, de-duplicate preserving first-seen order."""
    seen: set[str] = set()
    out: list[str] = []
    for v in values:
        t = normalize_tag(v)
        if t and t not in seen:
            seen.add(t)
            out.append(t)
    return out


def unknown_tags(tags: Iterable[str]) -> list[str]:
    """Tags outside the controlled vocabulary (reported later as assumptions)."""
    return [t for t in tags if t not in CANONICAL_TAGS]
