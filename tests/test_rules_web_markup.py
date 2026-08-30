"""Tests for :mod:`publisher.rules_web.markup`.

The two transformations here are the ones a regular expression over rendered HTML would get
wrong, so the cases that matter are the ones where a naive implementation would misfire: a
rule ID inside a code span, inside an existing link, and a page citing itself.
"""

from __future__ import annotations

import pytest

from publisher.rules_web import markup

LINKS = {
    "CORE-001": "/core-rules/core-001",
    "FLOW-013": "/game-flow/flow-013",
    "DMG-003": "/damage-system/dmg-003",
}


def _render(text: str, **kwargs) -> str:
    """Render ``text`` with the standard link table and an image sink that records nothing."""
    kwargs.setdefault("links", LINKS)
    kwargs.setdefault("on_image", lambda source, alt: source.rsplit("/", 1)[-1])
    kwargs.setdefault("where", "a test")
    return markup.render(text, **kwargs)


def test_a_citation_becomes_a_link() -> None:
    """The whole point: a rule ID people cite becomes a rule people can click."""
    html = _render("Height is counted in plate layers (`16-damage-system.md`, DMG-003).")
    assert '<a href="/damage-system/dmg-003" class="rule-reference">DMG-003</a>' in html


def test_a_rule_id_inside_a_code_span_is_left_alone() -> None:
    """A code span is not prose. It is also not a `text` token, which is why this works."""
    html = _render("The literal `CORE-001` is a code span.")
    assert "<code>CORE-001</code>" in html
    assert "<a" not in html


def test_a_rule_id_inside_an_existing_link_is_left_alone() -> None:
    """Wrapping an anchor around an anchor would produce invalid HTML."""
    html = _render("See [CORE-001 elsewhere](https://example.test/).")
    assert html.count("<a ") == 1
    assert 'href="https://example.test/"' in html


def test_a_page_does_not_link_to_itself() -> None:
    """A rule's own ID appears throughout its body; linking it back would be noise."""
    html = _render("CORE-001 defines the Unit Base, unlike FLOW-013.", skip="CORE-001")
    assert ">CORE-001<" not in html
    assert "CORE-001 defines" in html
    assert 'href="/game-flow/flow-013"' in html


def test_an_unknown_rule_id_fails_the_build() -> None:
    """A dead link would publish a ruleset error behind a page that renders fine."""
    with pytest.raises(markup.UnknownReference) as failure:
        _render("As stated in WPN-999.")
    assert "WPN-999" in str(failure.value)
    assert "not in the pinned ruleset" in str(failure.value)


def test_citing_a_rule_from_an_unpublished_document_says_so() -> None:
    """A different mistake from a rule that does not exist, so a different message."""
    with pytest.raises(markup.UnknownReference) as failure:
        _render("As stated in MEL-013.", unpublished=frozenset({"MEL-013"}))
    assert "does not publish" in str(failure.value)


def test_an_image_becomes_a_placeholder_and_is_recorded() -> None:
    """The URL is not known until the file is uploaded, so nothing bakes one in."""
    seen = []

    def on_image(source: str, alt: str) -> str:
        seen.append((source, alt))
        return source.rsplit("/", 1)[-1]

    html = _render(
        "![CORE-001 — unit base](../assets/images/core-001-unit-base.png)", on_image=on_image
    )
    assert 'src="{{media:core-001-unit-base.png}}"' in html
    assert 'alt="CORE-001 — unit base"' in html
    assert seen == [("../assets/images/core-001-unit-base.png", "CORE-001 — unit base")]


def test_an_image_with_emphasis_in_its_alt_text_keeps_the_words() -> None:
    """Alt text is published plain: the emphasis markers go, the words they wrapped stay."""
    captured = {}

    def on_image(source: str, alt: str) -> str:
        captured["alt"] = alt
        return "x.png"

    _render("![a **bold** caption](x.png)", on_image=on_image)
    assert captured["alt"] == "a bold caption"


def test_an_image_with_no_source_fails() -> None:
    """An embed with nothing to upload cannot be published as anything."""
    with pytest.raises(markup.UnknownReference):
        _render("![alt]()")


def test_lists_tables_and_quotes_survive() -> None:
    """The ruleset uses all three, and a rule reduced to paragraphs would misstate itself."""
    html = _render("* one\n* two\n\n| a | b |\n|---|---|\n| 1 | 2 |\n\n> quoted\n")
    assert "<ul>" in html
    assert "<table>" in html
    assert "<blockquote>" in html


def test_rendering_is_deterministic() -> None:
    """The committed bundle is diffed in review, so the same input must give the same bytes."""
    text = "A paragraph citing CORE-001.\n\n* a list\n"
    assert _render(text) == _render(text)


# -- references to whole ruleset documents --------------------------------------------------

DOCUMENTS = {
    "05-construction-components.md": "/rules/construction-components",
    "11-combat.md": "/rules/combat",
}


def test_a_filename_in_a_code_span_becomes_a_link_around_the_code_span() -> None:
    """On the web a filename is a worse address than the page it names."""
    html = _render("Parts follow `05-construction-components.md`.", documents=DOCUMENTS)

    assert (
        '<a href="/rules/construction-components" class="document-reference">'
        "<code>05-construction-components.md</code></a>" in html
    )


def test_a_filename_written_as_prose_is_linked_too() -> None:
    """The ruleset does it in a few places, and how it was typed is not the reader's problem."""
    html = _render("Follows:\n\n- 11-combat.md\n", documents=DOCUMENTS)

    assert '<li><a href="/rules/combat" class="document-reference">11-combat.md</a></li>' in html


def test_a_document_this_edition_does_not_publish_is_left_as_it_was() -> None:
    """Unlike a rule ID: a glossary or a foreword is not published, and that is a choice."""
    html = _render("See `14-glossary.md` and 01-foundations.md.", documents=DOCUMENTS)

    assert "<code>14-glossary.md</code>" in html
    assert "01-foundations.md" in html
    assert "document-reference" not in html


def test_a_code_span_that_is_not_a_filename_is_untouched() -> None:
    """Most code spans in the ruleset are measurements, and none of them are references."""
    html = _render("Read horizontally, it is `4 × 3` studs.", documents=DOCUMENTS)

    assert "<code>4 × 3</code>" in html
    assert "<a" not in html


def test_a_filename_inside_an_existing_link_is_left_alone() -> None:
    """Nested anchors are invalid, and the author already chose where that link goes."""
    html = _render("[11-combat.md](https://example.test/)", documents=DOCUMENTS)

    assert html.count("<a ") == 1
