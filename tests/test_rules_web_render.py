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
    assert '<a href="/core-rules/core-001">' in page["html"]
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


# -- reading-order pagination --------------------------------------------------------------


def _paged() -> Document:
    """Return a document of a root, two systems, and two rules in each."""
    pages = [
        Page(
            slug="rules",
            title="Rules",
            kind="root",
            entries=(
                Entry(title="Core Rules", slug="core-rules"),
                Entry(title="Game Flow", slug="game-flow"),
            ),
        ),
        Page(slug="core-rules", title="Core Rules", kind="document", parent="rules"),
        Page(
            slug="core-001",
            title="CORE-001 — Unit Base",
            kind="rule",
            parent="core-rules",
            body_html="<p>a</p>",
        ),
        Page(
            slug="core-002",
            title="CORE-002 — Facing",
            kind="rule",
            parent="core-rules",
            body_html="<p>b</p>",
        ),
        Page(slug="game-flow", title="Game Flow", kind="document", parent="rules"),
        Page(
            slug="flow-001",
            title="FLOW-001 — Before Turn 1",
            kind="rule",
            parent="game-flow",
            body_html="<p>c</p>",
        ),
    ]
    return _document(pages=tuple(pages), media=())


def _html(slug: str, document: Document | None = None) -> str:
    """Return the rendered HTML of one page."""
    built = _paged() if document is None else document
    return next(page for page in render.bundle(built)["pages"] if page["slug"] == slug)["html"]


def test_a_rule_links_to_the_rule_before_and_after_it() -> None:
    """Reading the ruleset through should not mean going back to an index between rules."""
    html = _html("core-001")

    assert '<a class="prev" rel="prev" href="/rules/core-rules">' in html
    assert '<a class="next" rel="next" href="/rules/core-rules/core-002">' in html
    assert "CORE-002 — Facing" in html


def test_the_last_rule_of_a_system_goes_on_to_the_next_system() -> None:
    """Which is the whole reason the sequence is the reading order and not per document."""
    html = _html("core-002")

    assert '<a class="next" rel="next" href="/rules/game-flow">' in html
    assert "Game Flow" in html


def test_the_first_rule_of_a_system_goes_back_to_its_own_index() -> None:
    """The page before the first rule is the system that holds it."""
    assert '<a class="prev" rel="prev" href="/rules/core-rules">' in _html("core-001")


def test_the_first_page_has_no_previous_and_the_last_no_next() -> None:
    """A link to nowhere is worse than an absent one."""
    first = _html("rules")
    last = _html("flow-001")

    assert 'class="prev"' not in first
    assert 'class="next"' in first
    assert 'class="next"' not in last
    assert 'class="prev"' in last


def test_pagination_resolves_through_the_base_path() -> None:
    """A translated edition must page within itself, not into the English one."""
    html = _html("core-001", _document(pages=_paged().pages, media=(), base_path="es"))

    assert 'href="/es/rules/core-rules/core-002"' in html


def test_a_page_whose_neighbour_was_renamed_is_republished() -> None:
    """The link carries the neighbour's title, so the hash has to notice it changing."""
    before = next(page for page in render.bundle(_paged())["pages"] if page["slug"] == "core-001")[
        "content_hash"
    ]

    pages = list(_paged().pages)
    pages[3] = Page(
        slug="core-002",
        title="CORE-002 — Renamed",
        kind="rule",
        parent="core-rules",
        body_html="<p>b</p>",
    )
    after = next(
        page
        for page in render.bundle(_document(pages=tuple(pages), media=()))["pages"]
        if page["slug"] == "core-001"
    )["content_hash"]

    assert before != after


@pytest.mark.parametrize(
    ("placement", "expected"),
    [("bottom", 1), ("top", 1), ("both", 2), ("none", 0)],
)
def test_where_the_pagination_sits_is_configurable(placement: str, expected: int) -> None:
    """Long reference documentation is read both ways round, so the choice is the author's."""
    document = _document(pages=_paged().pages, media=(), pagination=placement)
    html = next(page for page in render.bundle(document)["pages"] if page["slug"] == "core-001")[
        "html"
    ]

    assert html.count('<nav class="rule-pagination">') == expected


def test_top_puts_the_links_before_the_body_and_bottom_after() -> None:
    """Which is the whole difference, and the reason both exists."""
    pages, media = _paged().pages, ()
    top = next(
        page
        for page in render.bundle(_document(pages=pages, media=media, pagination="top"))["pages"]
        if page["slug"] == "core-001"
    )["html"]
    bottom = next(
        page
        for page in render.bundle(_document(pages=pages, media=media, pagination="bottom"))["pages"]
        if page["slug"] == "core-001"
    )["html"]

    assert top.index("rule-pagination") < top.index("<p>a</p>")
    assert bottom.index("rule-pagination") > bottom.index("<p>a</p>")


def test_an_unknown_placement_is_refused() -> None:
    """A misspelled placement that was ignored would look like the setting not working."""
    with pytest.raises(WebDocumentError) as failure:
        Document.from_dict(
            {
                "schema": 1,
                "pagination": "sideways",
                "pages": [{"slug": "x", "title": "X", "kind": "rule", "body_html": "<p>x</p>"}],
            }
        )
    assert "top, bottom, both, none" in str(failure.value)
