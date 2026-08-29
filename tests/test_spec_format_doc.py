"""The `spec.toml` reference must describe the code, not what it once described.

A format reference that drifts is worse than none: it teaches a shape the loader rejects.
These tests fail when a key or a default changes without the documentation following.
"""

from __future__ import annotations

import re
from dataclasses import fields
from pathlib import Path

from publisher.quicksheet import extract
from publisher.quicksheet.model import Page

DOC = Path(__file__).parent.parent / "data" / "SPEC-FORMAT.md"


def _text() -> str:
    return DOC.read_text(encoding="utf-8")


def test_every_page_key_is_documented() -> None:
    """A page parameter nobody documented is one nobody can use."""
    documented = set(re.findall(r"^\| `(\w+)` \|", _text(), re.M))
    undocumented = sorted({field.name for field in fields(Page)} - documented)

    assert not undocumented, f"undocumented [page] keys: {undocumented}"


def test_page_defaults_match_the_code() -> None:
    """A stale default sends someone chasing a value the renderer never used."""
    text = _text()
    stale = []
    for field in fields(Page):
        default = field.default if field.default is not None else field.default_factory()
        if isinstance(default, (int, float)) and not isinstance(default, bool):
            if f"| `{field.name}` | `{default}` |" not in text:
                stale.append((field.name, default))

    assert not stale, f"documented defaults differ from the code: {stale}"


def test_every_accepted_key_is_documented() -> None:
    """The loader rejects unknown keys, so the accepted set must be findable."""
    # Table keys appear as `[page]` and `[[section.line]]`, so compare on the bare names
    # inside every backticked token rather than on an exact spelling.
    # Only single-word tokens: fenced code blocks use triple backticks, and pairing them
    # naively swallows whole paragraphs.
    named = {
        part
        for token in re.findall(r"`(\[*[\w.]+\]*)`", _text())
        for part in token.strip("[]").split(".")
    }
    missing = [
        key
        for known in (extract._TOP_KEYS, extract._SECTION_KEYS, extract._LINE_KEYS)
        for key in known
        if key not in named
    ]

    assert not missing, f"accepted keys absent from the reference: {sorted(missing)}"
