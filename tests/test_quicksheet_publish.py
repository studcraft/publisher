"""Tests for where a rendered document is published.

The publish path is identity, not convenience: two languages of the same sheet, or the same
sheet against two ruleset versions, must never land on the same file.
"""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest

from publisher.quicksheet import publish
from publisher.quicksheet.model import Document, DocumentError, Line, Section, Source


def _document(**changes: object) -> Document:
    base = Document(
        title="A Sheet",
        sections=(Section(id="s", heading="S", lines=(Line(rule=None, text="x"),)),),
        name="quicksheet_3x3",
        language="en",
        source=Source(ruleset_version="0.2.0 Draft", commit="a" * 40),
    )
    return replace(base, **changes) if changes else base


def test_path_carries_product_version_and_language() -> None:
    """The published path says what the file is, so it is findable without a manifest."""
    assert publish.relative_path(_document(), "pdf") == Path(
        "quicksheet_3x3/v0.2.0draft/quicksheet_3x3_en.pdf"
    )


def test_languages_do_not_collide() -> None:
    """Two translations of one sheet are two files."""
    english = publish.relative_path(_document(), "pdf")
    spanish = publish.relative_path(_document(language="es"), "pdf")

    assert english != spanish
    assert english.parent == spanish.parent


def test_ruleset_versions_do_not_collide() -> None:
    """A sheet built against a newer ruleset lands beside the old one, not on top of it."""
    old = publish.relative_path(_document(), "pdf")
    new = publish.relative_path(
        _document(source=Source(ruleset_version="0.3.0", commit="b" * 40)), "pdf"
    )

    assert old.parent != new.parent


def test_formats_share_the_version_directory() -> None:
    """Every format of one document publishes together, so a version is one directory."""
    pdf = publish.relative_path(_document(), "pdf")
    html = publish.relative_path(_document(), "html")

    assert pdf.parent == html.parent
    assert pdf.stem == html.stem


def test_version_is_slugged_into_one_token() -> None:
    """'0.2.0 Draft' becomes v0.2.0draft: sortable, and no separator to guess wrong."""
    assert publish.slug("0.2.0 Draft") == "0.2.0draft"
    assert publish.slug("  1.0 Release Candidate ") == "1.0releasecandidate"


def test_slug_drops_characters_that_would_escape_the_tree() -> None:
    """A version or name from upstream must not be able to write outside publish/."""
    assert publish.slug("../../etc") == "....etc"
    assert "/" not in publish.slug("a/b")


def test_missing_version_refuses_to_publish() -> None:
    """Publishing without a version would make two different sheets one file."""
    with pytest.raises(DocumentError, match="version"):
        publish.relative_path(_document(source=Source()), "pdf")


def test_missing_language_refuses_to_publish() -> None:
    """Publishing without a language would collide with the sheet's own translations."""
    with pytest.raises(DocumentError, match="language"):
        publish.relative_path(_document(language=""), "pdf")


def test_missing_name_refuses_to_publish() -> None:
    """A nameless product has nowhere to live."""
    with pytest.raises(DocumentError, match="name"):
        publish.relative_path(_document(name=""), "pdf")


def test_root_is_prepended(tmp_path: Path) -> None:
    """The root is the only part a caller chooses; the rest is derived."""
    assert publish.path(_document(), "pdf", tmp_path) == tmp_path / publish.relative_path(
        _document(), "pdf"
    )
