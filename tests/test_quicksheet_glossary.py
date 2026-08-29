"""Tests for glossary-term extraction and highlighting."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from publisher.quicksheet.index import read_ruleset
from publisher.quicksheet.model import Document, Line, Section, Source
from publisher.quicksheet.render import pdf as render

FIXTURE = Path(__file__).parent / "fixtures" / "mini-docs"

TERMS = ("Weapon Front Footprint", "Attack Roll", "Attack Dice", "Weapon Front", "Impact", "UB")


@pytest.fixture()
def clone(tmp_path: Path) -> Path:
    """Return a writable copy of the mini-docs stand-in for a ruleset clone."""
    destination = tmp_path / "studcraft"
    shutil.copytree(FIXTURE, destination)
    return destination


def _flat(text: str, terms: tuple[str, ...] = TERMS) -> list[tuple[str, bool]]:
    """Return the (fragment, is_term) runs for ``text``, ignoring word boundaries."""
    pattern = render._term_pattern(terms)
    return [run for word in render._words([(text, False)], pattern) for run in word]


def test_terms_come_from_the_glossary_document(clone: Path) -> None:
    """The glossary is found by its heading, so renumbering the file does not lose it."""
    _, terms = read_ruleset(clone)

    assert set(terms) == {"Attack Roll", "Attack Dice", "Impact", "UB"}


def test_terms_are_longest_first(clone: Path) -> None:
    """Order is what makes matching work; a shorter term must never win a prefix."""
    _, terms = read_ruleset(clone)

    assert list(terms) == sorted(terms, key=lambda term: (-len(term), term))


def test_no_glossary_document_yields_no_terms(clone: Path) -> None:
    """A ruleset without a glossary renders unhighlighted rather than failing."""
    feed = clone / "scripts" / "feed.json"
    payload = json.loads(feed.read_text(encoding="utf-8"))
    del payload["03-glossary.md"]
    feed.write_text(json.dumps(payload), encoding="utf-8")

    assert read_ruleset(clone)[1] == ()


def test_longest_term_wins() -> None:
    """'Weapon Front Footprint' must win over the 'Weapon Front' that is a prefix of it.

    Had the shorter term matched first, 'Footprint' would be left plain. That is the whole
    check: every word of the longer term is highlighted, including the one the shorter term
    does not cover.
    """
    runs = _flat("The Weapon Front Footprint matters.")

    assert runs == [
        ("The", False),
        ("Weapon", True),
        ("Front", True),
        ("Footprint", True),
        ("matters.", False),
    ]


def test_matching_is_case_sensitive() -> None:
    """StudCraft capitalises its defined terms; the lowercase word is ordinary prose."""
    assert _flat("An Impact lands.") == [("An", False), ("Impact", True), ("lands.", False)]
    assert _flat("It may impact things.") == [
        ("It", False),
        ("may", False),
        ("impact", False),
        ("things.", False),
    ]


def test_plurals_match() -> None:
    """'Impacts' is the same defined term as 'Impact'."""
    assert ("Impacts", True) in _flat("Count the Impacts now.")


def test_partial_words_do_not_match() -> None:
    """A term inside a longer word is not that term."""
    runs = _flat("The UBS and the Impactful thing.")

    assert not any(is_term for _, is_term in runs)


def test_punctuation_stays_attached_to_its_term() -> None:
    """A term followed by a full stop is one word, or the page shows 'Impact .'."""
    pattern = render._term_pattern(TERMS)
    words = render._words([("Resolve the Impact, then stop.", False)], pattern)

    assert (("Impact", True), (",", False)) in words


def test_multi_word_term_is_two_bold_words() -> None:
    """'Attack Roll' wraps like two words but both are bold."""
    pattern = render._term_pattern(TERMS)
    words = render._words([("The Attack Roll decides.", False)], pattern)

    assert (("Attack", True),) in words
    assert (("Roll", True),) in words


def test_no_terms_gives_no_pattern() -> None:
    """An empty glossary short-circuits rather than building a pattern matching nothing."""
    assert render._term_pattern(()) is None
    assert _flat("Anything at all.", ()) == [
        ("Anything", False),
        ("at", False),
        ("all.", False),
    ]


def _sheet(glossary: tuple[str, ...]) -> Document:
    return Document(
        title="T",
        source=Source(ruleset_version="0.2.0 Draft", commit="c" * 40),
        sections=(
            Section(
                id="s",
                heading="S",
                intro="",
                lines=(
                    Line(rule="X-001", text="Each Impact resolves.", doc="d.md", source_line=1),
                ),
            ),
        ),
        glossary=glossary,
    )


def test_highlighting_changes_the_rendered_page(tmp_path: Path) -> None:
    """Bold is really emitted, not just computed and dropped."""
    plain = render.write(_sheet(()), tmp_path / "plain.pdf").read_bytes()
    bold = render.write(_sheet(("Impact",)), tmp_path / "bold.pdf").read_bytes()

    assert plain != bold


def test_highlighting_stays_reproducible(tmp_path: Path) -> None:
    """Two renders of a highlighted sheet are still byte-identical."""
    sheet = _sheet(("Impact", "UB"))

    first = render.write(sheet, tmp_path / "a.pdf").read_bytes()
    second = render.write(sheet, tmp_path / "b.pdf").read_bytes()

    assert first == second
