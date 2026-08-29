"""Tests for the pipeline's middle stage: ``document.json``.

The point of this stage is that it is a real, editable file. These tests pin the two things
that makes true: it round-trips without loss, and a hand-edited file renders without any
part of the pipeline reaching back to the ruleset.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from publisher.quicksheet import document as document_io
from publisher.quicksheet import render as renderers
from publisher.quicksheet.model import Document, DocumentError, Line, Page, Section, Source


def _document(page: Page | None = None) -> Document:
    return Document(
        title="A Sheet",
        sections=(
            Section(
                id="setup",
                heading="Setup",
                intro="How it starts.",
                lines=(
                    Line(rule=None, text="Three per side."),
                    Line(rule="FLOW-001", text="Deploy.", doc="03.md", source_line=29),
                ),
            ),
        ),
        name="testprod",
        language="en",
        page=page or Page(),
        source=Source(repo="r", ruleset_version="0.2.0 Draft", commit="a" * 40),
        glossary=("Impact", "UB"),
    )


def test_round_trip_is_lossless(tmp_path: Path) -> None:
    """Everything a renderer reads survives a write and a read."""
    original = _document()
    path = document_io.write(original, tmp_path / "document.json")

    assert document_io.read(path) == original


def test_written_file_is_stable_and_diffable(tmp_path: Path) -> None:
    """Two writes give identical bytes, so the file diffs cleanly in review."""
    first = document_io.write(_document(), tmp_path / "a.json").read_bytes()
    second = document_io.write(_document(), tmp_path / "b.json").read_bytes()

    assert first == second
    assert first.endswith(b"\n")


def test_page_parameters_are_in_the_file(tmp_path: Path) -> None:
    """Sizes are data. If they were not in the file, editing them would mean editing code."""
    path = document_io.write(_document(), tmp_path / "document.json")
    payload = json.loads(path.read_text(encoding="utf-8"))

    assert payload["page"]["width_mm"] == 210.0
    assert payload["page"]["columns"] == 2
    assert payload["page"]["body_pt"][0] == 11.0


def test_hand_edited_file_renders(tmp_path: Path) -> None:
    """The whole point: edit the JSON, render again, no ruleset in sight."""
    path = document_io.write(_document(), tmp_path / "document.json")
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["title"] = "Edited By Hand"
    payload["page"].update({"width_mm": 297.0, "height_mm": 210.0, "columns": 3})
    payload["sections"][0]["lines"].append({"rule": None, "text": "A line nobody extracted."})
    path.write_text(json.dumps(payload), encoding="utf-8")

    document = document_io.read(path)
    written = renderers.render(document, "pdf", tmp_path / "out")

    assert document.title == "Edited By Hand"
    assert document.page.columns == 3
    assert document.sections[0].lines[-1].text == "A line nobody extracted."
    assert written.exists()


def test_missing_file_names_the_command_that_makes_it(tmp_path: Path) -> None:
    """An absent document points at ``extract`` rather than at a traceback."""
    with pytest.raises(DocumentError, match="extract"):
        document_io.read(tmp_path / "nope.json")


def test_invalid_json_fails(tmp_path: Path) -> None:
    """A document that is not JSON is reported as such."""
    path = tmp_path / "document.json"
    path.write_text("{not json", encoding="utf-8")

    with pytest.raises(DocumentError, match="not valid JSON"):
        document_io.read(path)


def test_unknown_schema_fails(tmp_path: Path) -> None:
    """A document from a future build is refused, not half-read."""
    path = tmp_path / "document.json"
    path.write_text(json.dumps({"schema": 99, "sections": []}), encoding="utf-8")

    with pytest.raises(DocumentError, match="schema"):
        document_io.read(path)


def test_misspelled_page_key_fails(tmp_path: Path) -> None:
    """A typo in an edited page must not look like a renderer that ignores margins."""
    path = tmp_path / "document.json"
    payload = _document().to_dict()
    payload["page"]["margins_mm"] = 5
    path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(DocumentError) as excinfo:
        document_io.read(path)

    assert "margins_mm" in str(excinfo.value)
    assert "margin_mm" in str(excinfo.value)


def test_document_without_sections_fails(tmp_path: Path) -> None:
    """An empty document produces no output, so it fails at read time."""
    path = tmp_path / "document.json"
    path.write_text(json.dumps({"schema": 1, "sections": []}), encoding="utf-8")

    with pytest.raises(DocumentError, match="no sections"):
        document_io.read(path)


def test_line_with_no_content_fails(tmp_path: Path) -> None:
    """An entry that prints nothing is a defect in the edited file."""
    path = tmp_path / "document.json"
    payload = _document().to_dict()
    del payload["sections"][0]["lines"][0]["text"]
    path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(DocumentError, match="prints nothing"):
        document_io.read(path)


def test_pdf_renderer_is_registered() -> None:
    """The format registry is what lets a second output target skip stages 1 and 2."""
    assert "pdf" in renderers.formats()
    assert renderers.get("pdf").extension == "pdf"
    assert callable(renderers.get("pdf").write)


def test_unknown_format_lists_what_exists(tmp_path: Path) -> None:
    """Asking for a format nobody wrote names the ones that exist."""
    with pytest.raises(renderers.UnknownFormat) as excinfo:
        renderers.render(_document(), "stl", tmp_path)

    assert "pdf" in str(excinfo.value)
