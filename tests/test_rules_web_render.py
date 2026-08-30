"""Tests for :mod:`publisher.rules_web.render` and the document's own JSON round trip."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from publisher.quicksheet.model import DocumentError, Source
from publisher.rules_web import document as document_io
from publisher.rules_web import render
from publisher.rules_web.markup import UnknownReference
from publisher.rules_web.model import Document, Entry, Media, Page, WebDocumentError


def _document(**overrides) -> Document:
    """Return a small document: one index page, one rule page."""
    fields = {
        "title": "StudCraft Rules",
        "pages": (
            Page(
                slug="core-rules",
                title="Core Rules",
                kind="document",
                intro="The universal rules.",
                entries=(Entry(rule="CORE-001", title="Unit Base (UB)", slug="core-001"),),
                doc="02-core-rules.md",
            ),
            Page(
                slug="core-001",
                title="CORE-001 — Unit Base (UB)",
                kind="rule",
                parent="core-rules",
                body_html="<p>A volume.</p>",
                rule="CORE-001",
                doc="02-core-rules.md",
                source_line=56,
            ),
        ),
        "media": (
            Media(
                filename="core-001.png",
                source="assets/images/core-001.png",
                alt="unit base",
                attach_to="core-001",
                content_hash="sha256:abc",
            ),
        ),
        "source": Source(repo="r", ruleset_version="0.2.0 Draft", commit="abc123def4567"),
    }
    fields.update(overrides)
    return Document(**fields)


def test_the_publish_path_is_derived_from_the_document(tmp_path: Path) -> None:
    """Name, version and language decide where a bundle lands; the caller does not."""
    written = render.render(_document(), tmp_path)
    assert written == tmp_path / "rules_web" / "v0.2.0draft" / "rules_web_en.wp.json"


def test_a_document_page_becomes_an_index_of_its_rules() -> None:
    """The index is built here, not at extraction: it is presentation."""
    page = render.bundle(_document())["pages"][0]
    assert '<ul class="rule-index">' in page["html"]
    assert '<a href="core-001">' in page["html"]
    assert "<strong>CORE-001</strong> — Unit Base (UB)" in page["html"]
    assert "<p>The universal rules.</p>" in page["html"]


def test_every_page_carries_its_provenance() -> None:
    """Which version, which commit, and that editing it in WordPress achieves nothing."""
    page = render.bundle(_document())["pages"][1]
    assert "02-core-rules.md, line 56" in page["html"]
    assert "0.2.0 Draft" in page["html"]
    assert "<code>abc123def456</code>" in page["html"]
    assert "fix the ruleset instead" in page["html"]


def test_a_page_with_no_source_document_still_gets_a_footer() -> None:
    """Provenance is unconditional; only its detail varies."""
    document = _document(
        pages=(Page(slug="x", title="X", kind="rule", body_html="<p>x</p>"),),
        media=(),
    )
    assert "the StudCraft ruleset" in render.bundle(document)["pages"][0]["html"]


def test_the_hash_covers_the_title_as_well_as_the_body() -> None:
    """Renaming a page is a change to publish; a body-only hash would call it unchanged."""
    first = render.bundle(_document())["pages"][1]["content_hash"]
    renamed = list(_document().pages)
    renamed[1] = Page(
        slug="core-001",
        title="CORE-001 — Something else",
        kind="rule",
        parent="core-rules",
        body_html="<p>A volume.</p>",
    )
    second = render.bundle(_document(pages=tuple(renamed)))["pages"][1]["content_hash"]
    assert first != second


def test_rendering_twice_gives_identical_bytes(tmp_path: Path) -> None:
    """The committed bundle is compared byte for byte in CI."""
    first = render.render(_document(), tmp_path / "one")
    second = render.render(_document(), tmp_path / "two")
    assert first.read_bytes() == second.read_bytes()


def test_an_image_in_an_authored_introduction_is_refused() -> None:
    """Only ruleset images are collected for upload, so any other would never resolve."""
    document = _document(
        pages=(
            Page(
                slug="core-rules",
                title="Core Rules",
                kind="document",
                intro="![nope](nope.png)",
                entries=(Entry(rule="CORE-001", title="Unit Base", slug="core-001"),),
            ),
        )
    )
    with pytest.raises(UnknownReference):
        render.bundle(document)


def test_a_document_without_a_ruleset_version_cannot_be_published() -> None:
    """Two versions of the same edition would otherwise land on one path."""
    with pytest.raises(DocumentError):
        render.path(_document(source=Source()))


def test_a_document_round_trips_through_json(tmp_path: Path) -> None:
    """The middle stage is editable by hand, so it has to read back as it was written."""
    path = document_io.write(_document(), tmp_path / "document.json")
    again = document_io.read(path)

    assert again.to_dict() == _document().to_dict()
    assert again.pages[0].entries[0].rule == "CORE-001"
    assert again.media[0].filename == "core-001.png"


def test_reading_a_missing_document_says_what_to_run(tmp_path: Path) -> None:
    """The fix is one command, so the error names it."""
    with pytest.raises(WebDocumentError) as failure:
        document_io.read(tmp_path / "absent.json")
    assert "extract" in str(failure.value)


def test_reading_a_document_that_is_not_json_fails(tmp_path: Path) -> None:
    """Reported as a parse failure rather than as a shape failure further in."""
    path = tmp_path / "document.json"
    path.write_text("{not json", encoding="utf-8")
    with pytest.raises(WebDocumentError) as failure:
        document_io.read(path)
    assert "not valid JSON" in str(failure.value)


@pytest.mark.parametrize(
    ("payload", "expected"),
    [
        ("a string", "Expected an object"),
        ({"schema": 99, "pages": []}, "Unknown document schema"),
        ({"schema": 1, "pages": []}, "no pages"),
        ({"schema": 1, "pages": [["not", "an", "object"]]}, "not an object"),
        ({"schema": 1, "pages": [{"slug": "x", "kind": "rule"}]}, "missing 'title'"),
        (
            {"schema": 1, "pages": [{"slug": "x", "title": "X", "kind": "chapter"}]},
            "expected one of root, document, rule",
        ),
        (
            {"schema": 1, "pages": [{"slug": "x", "title": "X", "kind": "rule"}]},
            "prints nothing",
        ),
        (
            {
                "schema": 1,
                "pages": [{"slug": "x", "title": "X", "kind": "rule", "body_html": "<p>x</p>"}],
                "source": "not an object",
            },
            "source is not an object",
        ),
    ],
)
def test_a_malformed_document_fails_by_name(payload: object, expected: str) -> None:
    """Every failure says which part of the file is wrong."""
    with pytest.raises(WebDocumentError) as failure:
        Document.from_dict(payload)
    assert expected in str(failure.value)


def test_a_malformed_index_entry_fails_by_name() -> None:
    """An index entry with no target would publish a link to nowhere."""
    payload = {
        "schema": 1,
        "pages": [
            {
                "slug": "core-rules",
                "title": "Core Rules",
                "kind": "document",
                "entries": [{"rule": "CORE-001", "title": "Unit Base"}],
            }
        ],
    }
    with pytest.raises(WebDocumentError) as failure:
        Document.from_dict(payload)
    assert "missing 'slug'" in str(failure.value)


def test_a_malformed_media_item_fails_by_name() -> None:
    """An upload with no file to read is a bundle nothing can publish."""
    payload = {
        "schema": 1,
        "pages": [{"slug": "x", "title": "X", "kind": "rule", "body_html": "<p>x</p>"}],
        "media": [{"filename": "a.png"}],
    }
    with pytest.raises(WebDocumentError) as failure:
        Document.from_dict(payload)
    assert "missing 'source'" in str(failure.value)


def test_the_bundle_is_json_with_a_trailing_newline(tmp_path: Path) -> None:
    """It is a tracked file: it has to diff like one."""
    written = render.render(_document(), tmp_path)
    text = written.read_text(encoding="utf-8")
    assert text.endswith("\n")
    assert json.loads(text)["schema"] == render.BUNDLE_SCHEMA


def test_a_page_knows_its_own_path() -> None:
    """The published address of a page, for anything that needs to report one."""
    document = _document()
    assert document.pages[0].path == "core-rules"
    assert document.pages[1].path == "core-rules/core-001"
