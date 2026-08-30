"""Tests for :mod:`publisher.rules_web.extract` and :mod:`publisher.rules_web.spec`."""

from __future__ import annotations

from pathlib import Path

import pytest

from publisher.quicksheet.index import Block, Rule
from publisher.quicksheet.model import Source
from publisher.rules_web import extract, spec
from publisher.rules_web.markup import UnknownReference

SPEC = """
title = "StudCraft Rules"

[[document]]
file = "02-core-rules.md"
slug = "core-rules"
title = "Core Rules"
intro = "The universal rules."

[[document]]
file = "03-game-flow.md"
"""


def _rule(rule_id: str, doc: str, title: str, *paragraphs: str) -> Rule:
    """Build a rule whose body is the given paragraphs."""
    return Rule(
        id=rule_id,
        title=title,
        doc=doc,
        line=10,
        line_end=20,
        blocks=tuple(
            Block(kind="paragraph", line_start=10, line_end=10, lines=(text,))
            for text in paragraphs
        )
        + (Block(kind="break", line_start=21, line_end=21, lines=("---",)),),
    )


def _index() -> dict:
    """Return a small rule index spanning two documents."""
    return {
        "CORE-001": _rule(
            "CORE-001", "02-core-rules.md", "Unit Base (UB)", "A volume. See FLOW-001."
        ),
        "CORE-002": _rule("CORE-002", "02-core-rules.md", "Facing", "Every unit has a facing."),
        "FLOW-001": _rule("FLOW-001", "03-game-flow.md", "Before Turn 1", "Agree the size."),
    }


def _spec(tmp_path: Path, text: str = SPEC) -> spec.Spec:
    """Write ``text`` as a specification file and load it."""
    path = tmp_path / "spec.toml"
    path.write_text(text, encoding="utf-8")
    return spec.load(path)


def _build(tmp_path: Path, index=None, text: str = SPEC):
    """Build a document from ``index`` against the specification in ``text``."""
    return extract.build(
        spec=_spec(tmp_path, text),
        index=_index() if index is None else index,
        source=Source(repo="r", ruleset_version="0.2.0 Draft", commit="abc123def456"),
        clone_root=tmp_path / "clone",
    )


def test_the_whole_edition_hangs_from_one_root_page(tmp_path: Path) -> None:
    """The published shape: one root, a page per document under it, a page per rule under that."""
    document = _build(tmp_path)

    kinds = [(page.slug, page.kind, page.parent) for page in document.pages]
    assert kinds == [
        ("rules", "root", None),
        ("core-rules", "document", "rules"),
        ("core-001", "rule", "core-rules"),
        ("core-002", "rule", "core-rules"),
        ("game-flow", "document", "rules"),
        ("flow-001", "rule", "game-flow"),
    ]


def test_the_root_page_indexes_the_documents_in_reading_order(tmp_path: Path) -> None:
    """The specification's order is the ruleset's numbering, which is how it is meant to be read."""
    root = _build(tmp_path).pages[0]

    assert [entry.slug for entry in root.entries] == ["core-rules", "game-flow"]
    assert [entry.title for entry in root.entries] == ["Core Rules", "Game Flow"]
    assert root.entries[0].rule is None


def test_menu_order_follows_reading_order_rather_than_the_alphabet(tmp_path: Path) -> None:
    """WordPress sorts a menu by this field and falls back to the title when it is zero."""
    pages = {page.slug: page.menu_order for page in _build(tmp_path).pages}

    assert pages["core-rules"] == 1
    assert pages["game-flow"] == 2
    assert (pages["core-001"], pages["core-002"]) == (1, 2)


def test_a_document_page_indexes_its_rules_in_ruleset_order(tmp_path: Path) -> None:
    """A reader who does not know a rule's number starts at the document page."""
    document = _build(tmp_path)
    index_page = document.pages[1]

    assert [entry.rule for entry in index_page.entries] == ["CORE-001", "CORE-002"]
    assert index_page.entries[0].title == "Unit Base (UB)"
    assert index_page.entries[0].slug == "core-001"


def test_a_rule_page_carries_the_body_and_its_provenance(tmp_path: Path) -> None:
    """A published page can be checked against the rule it claims to state."""
    document = _build(tmp_path)
    page = document.pages[2]

    assert page.title == "CORE-001 — Unit Base (UB)"
    assert page.rule == "CORE-001"
    assert page.doc == "02-core-rules.md"
    assert page.source_line == 10
    assert "<p>A volume." in page.body_html


def test_a_citation_is_linked_through_the_base_path(tmp_path: Path) -> None:
    """A future translated tree must link inside itself, not back into the English one."""
    document = _build(tmp_path, text='base_path = "es"\n' + SPEC)
    body = document.pages[2].body_html

    assert 'href="/es/rules/game-flow/flow-001"' in body


def test_the_separator_between_rules_is_not_part_of_a_rule(tmp_path: Path) -> None:
    """A `break` block is punctuation in the source document, not content on the page."""
    document = _build(tmp_path)
    assert "<hr" not in document.pages[2].body_html


def test_publishing_a_document_the_ruleset_has_no_rules_for_fails(tmp_path: Path) -> None:
    """Naming a document that is not there is a specification error, not an empty page."""
    text = '[[document]]\nfile = "99-nothing.md"\n'
    with pytest.raises(extract.ExtractError) as failure:
        _build(tmp_path, text=text)
    assert "99-nothing.md" in str(failure.value)


def test_citing_a_rule_in_an_unpublished_document_fails(tmp_path: Path) -> None:
    """There is no page to link to, so the citation cannot be honoured."""
    text = '[[document]]\nfile = "02-core-rules.md"\n'
    with pytest.raises(UnknownReference) as failure:
        _build(tmp_path, text=text)
    assert "does not publish" in str(failure.value)


def test_a_document_title_falls_back_to_the_filename(tmp_path: Path) -> None:
    """A specification that cares says so; one that does not still gets something readable."""
    document = _build(tmp_path)
    assert document.pages[4].title == "Game Flow"


def test_the_body_of_a_rule_reconstructs_its_markdown() -> None:
    """A list has to arrive at the renderer as a list, not as the lines of one."""
    rule = Rule(
        id="X-001",
        title="A list",
        doc="d.md",
        line=1,
        line_end=5,
        blocks=(
            Block(kind="paragraph", line_start=1, line_end=1, lines=("Intro.",)),
            Block(kind="list", line_start=3, line_end=4, lines=("* one", "* two")),
        ),
    )
    assert extract.body(rule) == "Intro.\n\n* one\n* two"
