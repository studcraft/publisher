"""Tests for :mod:`publisher.quicksheet.extract`."""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from publisher.quicksheet import extract
from publisher.quicksheet.index import build_index
from publisher.quicksheet.model import Source

FIXTURE = Path(__file__).parent / "fixtures" / "mini-docs"

GOOD_SPEC = """
language = "en"
title = "Mini Sheet"

[[section]]
id = "setup"
heading = "Setup"
intro = "How the mode is set up."

[[section.line]]
authored = true
text = "Three minifigures per warband."

[[section.line]]
rule = "MINI-001"
text = "The first rule, condensed."

[[section]]
id = "more"
heading = "More"

[[section.line]]
rule = "MINI-003"
text = "A rule from the second document."
"""


@pytest.fixture()
def index(tmp_path: Path) -> dict:
    """Build an index from a writable copy of the mini-docs stand-in."""
    destination = tmp_path / "studcraft"
    shutil.copytree(FIXTURE, destination)
    return build_index(destination)


def _spec(tmp_path: Path, body: str) -> dict:
    path = tmp_path / "spec.toml"
    # Every product declares a language; tests that do not care still need one.
    if "language" not in body:
        body = 'language = "en"\n' + body
    path.write_text(body, encoding="utf-8")
    return extract.load_spec(path)


SOURCE = Source(repo="r", ruleset_version="9.9.9 Test", commit="cafe" * 10)


def _build(index: dict, spec: dict) -> object:
    """Build a document with a fixed source, so tests read as content assertions."""
    return extract.build_document(index, spec, SOURCE)


def test_build_document_resolves_rules_and_attaches_sources(index: dict, tmp_path: Path) -> None:
    """Each cited line carries the document and line of the rule it condenses."""
    sheet = _build(index, _spec(tmp_path, GOOD_SPEC))

    assert sheet.title == "Mini Sheet"
    assert sheet.source.ruleset_version == "9.9.9 Test"
    assert [section.id for section in sheet.sections] == ["setup", "more"]

    setup = sheet.sections[0]
    assert setup.intro == "How the mode is set up."
    assert setup.lines[0].authored is True
    assert setup.lines[0].rule is None
    assert setup.lines[1].rule == "MINI-001"
    assert setup.lines[1].doc == "01-mini.md"
    assert setup.lines[1].source_line == 7


def test_build_document_is_pure(index: dict, tmp_path: Path) -> None:
    """Two calls with the same inputs return equal results."""
    spec = _spec(tmp_path, GOOD_SPEC)
    first = _build(index, spec)
    second = _build(index, spec)

    assert first == second


def test_missing_rule_names_id_and_section(index: dict, tmp_path: Path) -> None:
    """A rule removed upstream fails the build, naming the ID and the section."""
    body = """
[[section]]
id = "movement"
heading = "Movement"

[[section.line]]
rule = "MINI-404"
text = "Cites a rule that is gone."
"""
    with pytest.raises(extract.SpecError) as excinfo:
        _build(index, _spec(tmp_path, body))

    message = str(excinfo.value)
    assert "MINI-404" in message
    assert "movement" in message


def test_section_without_heading_fails(index: dict, tmp_path: Path) -> None:
    """A section missing its heading is named in the error."""
    body = """
[[section]]
id = "nameless"

[[section.line]]
rule = "MINI-001"
text = "x"
"""
    with pytest.raises(extract.SpecError, match="nameless"):
        _build(index, _spec(tmp_path, body))


def test_section_without_id_fails(index: dict, tmp_path: Path) -> None:
    """A section with no id cannot be reported on later, so it fails now."""
    body = """
[[section]]
heading = "Anonymous"

[[section.line]]
rule = "MINI-001"
text = "x"
"""
    with pytest.raises(extract.SpecError, match="missing 'id'"):
        _build(index, _spec(tmp_path, body))


def test_line_without_rule_fails(index: dict, tmp_path: Path) -> None:
    """An unanchored line is a defect unless it declares itself authored."""
    body = """
[[section]]
id = "movement"
heading = "Movement"

[[section.line]]
text = "Where did this come from?"
"""
    with pytest.raises(extract.SpecError, match="missing 'rule'"):
        _build(index, _spec(tmp_path, body))


def test_line_without_text_fails(index: dict, tmp_path: Path) -> None:
    """A line with a rule but no text prints nothing, so it fails."""
    body = """
[[section]]
id = "movement"
heading = "Movement"

[[section.line]]
rule = "MINI-001"
"""
    with pytest.raises(extract.SpecError, match="missing 'text'"):
        _build(index, _spec(tmp_path, body))


def test_empty_section_fails(index: dict, tmp_path: Path) -> None:
    """A heading with nothing under it is a mistake, not an empty column."""
    body = """
[[section]]
id = "movement"
heading = "Movement"
"""
    with pytest.raises(extract.SpecError, match="no lines"):
        _build(index, _spec(tmp_path, body))


def test_spec_without_sections_fails(index: dict, tmp_path: Path) -> None:
    """A specification file with no sections produces no sheet."""
    with pytest.raises(extract.SpecError, match="no sections"):
        _build(index, _spec(tmp_path, 'title = "Empty"\n'))


def test_invalid_toml_fails(tmp_path: Path) -> None:
    """A malformed specification file is reported as such."""
    path = tmp_path / "spec.toml"
    path.write_text("this is not = = toml", encoding="utf-8")

    with pytest.raises(extract.SpecError, match="not valid TOML"):
        extract.load_spec(path)


def test_missing_spec_file_fails(tmp_path: Path) -> None:
    """An absent specification file names the path that was looked for."""
    with pytest.raises(extract.SpecError, match="No specification file"):
        extract.load_spec(tmp_path / "nope.toml")


def test_draft_spec_round_trips(index: dict, tmp_path: Path) -> None:
    """The bootstrap draft is valid TOML that builds a sheet without hand-editing."""
    drafted = extract.draft_spec(index, ["MINI-001", "MINI-003"])
    path = tmp_path / "draft.toml"
    path.write_text(drafted, encoding="utf-8")

    sheet = _build(index, extract.load_spec(path))

    assert [line.rule for line in sheet.sections[0].lines] == ["MINI-001", "MINI-003"]
    assert sheet.sections[0].lines[0].text == "The first rule says one thing."


def test_page_settings_come_from_the_spec(index: dict, tmp_path: Path) -> None:
    """Sizes are authored in the spec and land in the document, not in renderer code."""
    body = (
        GOOD_SPEC
        + """
[page]
columns = 3
width_mm = 297.0
body_pt = [9.0, 8.0]
"""
    )
    document = _build(index, _spec(tmp_path, body))

    assert document.page.columns == 3
    assert document.page.width_mm == 297.0
    assert document.page.body_pt == (9.0, 8.0)


def test_page_defaults_apply_when_unspecified(index: dict, tmp_path: Path) -> None:
    """A spec with no [page] table still produces a complete page."""
    document = _build(index, _spec(tmp_path, GOOD_SPEC))

    assert document.page.columns == 2
    assert document.page.format == "A4"


def test_misspelled_page_key_fails(index: dict, tmp_path: Path) -> None:
    """A typo in [page] is an error, not a setting that quietly does nothing."""
    body = (
        GOOD_SPEC
        + """
[page]
collumns = 3
"""
    )
    with pytest.raises(extract.SpecError, match="collumns"):
        _build(index, _spec(tmp_path, body))


def test_language_is_required(index: dict, tmp_path: Path) -> None:
    """A document with no language cannot be published without colliding with its own
    translations, so the omission fails at extraction rather than at publish time."""
    path = tmp_path / "nolang.toml"
    path.write_text(GOOD_SPEC.replace('language = "en"\n', ""), encoding="utf-8")

    with pytest.raises(extract.SpecError, match="language"):
        _build(index, extract.load_spec(path))


def test_name_defaults_to_the_data_directory(index: dict, tmp_path: Path) -> None:
    """The product name follows its directory, so the two cannot drift."""
    document = extract.build_document(
        index, _spec(tmp_path, GOOD_SPEC), SOURCE, name="quicksheet_3x3"
    )

    assert document.name == "quicksheet_3x3"


def test_spec_can_override_the_name(index: dict, tmp_path: Path) -> None:
    """An explicit name in the spec wins over the directory."""
    body = GOOD_SPEC.replace('title = "Mini Sheet"', 'name = "explicit"\ntitle = "Mini Sheet"')
    document = extract.build_document(index, _spec(tmp_path, body), SOURCE, name="from_dir")

    assert document.name == "explicit"


def test_unknown_section_key_fails(index: dict, tmp_path: Path) -> None:
    """A misspelled section key must not look like a renderer that ignores intros."""
    body = """
[[section]]
id = "s"
heading = "H"
introo = "typo"

[[section.line]]
rule = "MINI-001"
text = "t"
"""
    with pytest.raises(extract.SpecError) as excinfo:
        _build(index, _spec(tmp_path, body))

    assert "introo" in str(excinfo.value)
    assert "intro" in str(excinfo.value)


def test_unknown_line_key_fails(index: dict, tmp_path: Path) -> None:
    """Same for a line: a key nobody reads is a mistake, not a comment."""
    body = """
[[section]]
id = "s"
heading = "H"

[[section.line]]
rule = "MINI-001"
text = "t"
note = "where did this go?"
"""
    with pytest.raises(extract.SpecError, match="note"):
        _build(index, _spec(tmp_path, body))


def test_unknown_top_level_key_fails(index: dict, tmp_path: Path) -> None:
    """A misspelled 'title' would silently publish the default title."""
    body = """
titel = "Typo"

[[section]]
id = "s"
heading = "H"

[[section.line]]
rule = "MINI-001"
text = "t"
"""
    with pytest.raises(extract.SpecError, match="titel"):
        _build(index, _spec(tmp_path, body))


def test_authored_line_cannot_also_cite_a_rule(index: dict, tmp_path: Path) -> None:
    """Both at once is ambiguous: the rule would be silently ignored."""
    body = """
[[section]]
id = "s"
heading = "H"

[[section.line]]
authored = true
rule = "MINI-001"
text = "t"
"""
    with pytest.raises(extract.SpecError, match="cannot be both"):
        _build(index, _spec(tmp_path, body))
