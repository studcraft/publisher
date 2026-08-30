"""Tests for how images reach the web edition.

The ruleset treats images as load-bearing — a rule that is a spatial fact is not fully stated
without one — so dropping one silently is the failure worth guarding against.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from publisher.quicksheet.index import Block, Rule
from publisher.quicksheet.model import Source
from publisher.rules_web import extract, spec

SPEC = '[[document]]\nfile = "02-core-rules.md"\nslug = "core-rules"\n'

PIXEL = b"\x89PNG\r\n\x1a\n" + b"pretend this is an image"


def _clone(tmp_path: Path, *names: str) -> Path:
    """Return a clone root holding ``names`` under ``assets/images``."""
    images = tmp_path / "clone" / "assets" / "images"
    images.mkdir(parents=True, exist_ok=True)
    for name in names:
        images.joinpath(name).write_bytes(PIXEL)
    return tmp_path / "clone"


def _rule(rule_id: str, *paragraphs: str) -> Rule:
    """Build a rule whose body is the given paragraphs."""
    return Rule(
        id=rule_id,
        title="A rule",
        doc="02-core-rules.md",
        line=1,
        line_end=9,
        blocks=tuple(
            Block(kind="paragraph", line_start=1, line_end=1, lines=(text,)) for text in paragraphs
        ),
    )


def _build(tmp_path: Path, index: dict, clone: Path):
    """Build a document from ``index`` against ``clone``."""
    path = tmp_path / "spec.toml"
    path.write_text(SPEC, encoding="utf-8")
    return extract.build(
        spec=spec.load(path),
        index=index,
        source=Source(),
        clone_root=clone,
    )


def test_an_embedded_image_is_collected_with_its_alt_and_page(tmp_path: Path) -> None:
    """Everything the upload needs comes from the embed, not from a second list."""
    clone = _clone(tmp_path, "core-001-unit-base.png")
    index = {
        "CORE-001": _rule(
            "CORE-001", "![CORE-001 — unit base](../assets/images/core-001-unit-base.png)"
        )
    }

    document = _build(tmp_path, index, clone)

    assert len(document.media) == 1
    item = document.media[0]
    assert item.filename == "core-001-unit-base.png"
    assert item.source == "assets/images/core-001-unit-base.png"
    assert item.alt == "CORE-001 — unit base"
    assert item.attach_to == "core-001"
    assert item.content_hash.startswith("sha256:")


def test_the_page_carries_a_placeholder_rather_than_a_url(tmp_path: Path) -> None:
    """A baked URL would carry the upload month and break render determinism."""
    clone = _clone(tmp_path, "core-001-unit-base.png")
    index = {"CORE-001": _rule("CORE-001", "![alt](../assets/images/core-001-unit-base.png)")}

    document = _build(tmp_path, index, clone)

    assert "{{media:core-001-unit-base.png}}" in document.pages[2].body_html
    assert "assets/images" not in document.pages[2].body_html


def test_an_image_embedded_twice_is_collected_once(tmp_path: Path) -> None:
    """One file, one upload. Two entries would mean uploading it twice."""
    clone = _clone(tmp_path, "shared.png")
    index = {
        "CORE-001": _rule("CORE-001", "![a](../assets/images/shared.png)"),
        "CORE-002": _rule("CORE-002", "![b](../assets/images/shared.png)"),
    }

    document = _build(tmp_path, index, clone)

    assert [item.filename for item in document.media] == ["shared.png"]
    assert document.media[0].attach_to == "core-001"


def test_a_missing_image_file_fails_the_build(tmp_path: Path) -> None:
    """The ruleset embeds only what exists, so an absent file means a broken clone."""
    clone = _clone(tmp_path)
    index = {"CORE-001": _rule("CORE-001", "![alt](../assets/images/never-drawn.png)")}

    with pytest.raises(extract.ExtractError) as failure:
        _build(tmp_path, index, clone)
    assert "never-drawn.png" in str(failure.value)


def test_an_image_from_outside_the_clone_is_refused(tmp_path: Path) -> None:
    """An image has to come from the ruleset it illustrates."""
    clone = _clone(tmp_path)
    index = {"CORE-001": _rule("CORE-001", "![alt](../../elsewhere/secret.png)")}

    with pytest.raises(extract.ExtractError) as failure:
        _build(tmp_path, index, clone)
    assert "outside the ruleset clone" in str(failure.value)


def test_two_different_files_with_the_same_name_are_refused(tmp_path: Path) -> None:
    """They publish to one URL, so one would silently replace the other."""
    clone = _clone(tmp_path, "same.png")
    (clone / "assets" / "other").mkdir(parents=True)
    (clone / "assets" / "other" / "same.png").write_bytes(PIXEL)
    index = {
        "CORE-001": _rule("CORE-001", "![a](../assets/images/same.png)"),
        "CORE-002": _rule("CORE-002", "![b](../assets/other/same.png)"),
    }

    with pytest.raises(extract.ExtractError) as failure:
        _build(tmp_path, index, clone)
    assert "overwrite each other" in str(failure.value)
