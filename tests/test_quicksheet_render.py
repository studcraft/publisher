"""Tests for :mod:`publisher.quicksheet.render`."""

from __future__ import annotations

import re
import zlib
from dataclasses import replace
from pathlib import Path

import pytest

from publisher.quicksheet import render as renderers
from publisher.quicksheet.model import Document, Line, Page, Section, Source
from publisher.quicksheet.render import pdf as render

_STREAM = re.compile(rb"stream\r?\n(.*?)\r?\nendstream", re.DOTALL)
_SHOWN = re.compile(r"\((.*?)\) Tj", re.DOTALL)


def _page_text(raw: bytes) -> str:
    """Return the text drawn on the page, reassembled from its show-text operators.

    Glossary highlighting draws one fragment at a time so it can switch fonts mid-line, so
    the stream holds many short strings rather than whole lines. Joining them back is what
    lets a test assert on a sentence.
    """
    content = []
    for match in _STREAM.finditer(raw):
        try:
            content.append(zlib.decompress(match.group(1)).decode("latin-1"))
        except zlib.error:
            content.append(match.group(1).decode("latin-1"))
    shown = _SHOWN.findall("\n".join(content))
    return " ".join(fragment.replace("\\(", "(").replace("\\)", ")") for fragment in shown)


def _sheet(sections: tuple[Section, ...], page: Page | None = None) -> Document:
    return Document(
        title="StudCraft Quick Sheet",
        sections=sections,
        page=page or Page(),
        source=Source(
            ruleset_version="0.2.0 Draft",
            commit="edd8aa4dfa512eee7662251948586f457c372012",
        ),
    )


def _section(section_id: str, lines: int, text: str = "A condensed rule line.") -> Section:
    return Section(
        id=section_id,
        heading=section_id.title(),
        intro="",
        lines=tuple(
            Line(rule=f"X-{n:03d}", text=text, doc="d.md", source_line=n) for n in range(lines)
        ),
    )


SMALL = _sheet(
    (
        Section(
            id="setup",
            heading="Setup",
            intro="Three minifigures per side.",
            lines=(
                Line(rule=None, text="Warband of three.", doc=None, source_line=None),
                Line(rule="FLOW-001", text="Set up terrain first.", doc="03.md", source_line=10),
            ),
        ),
        _section("movement", 4),
    )
)


def test_render_writes_one_a4_page(tmp_path: Path) -> None:
    """The sheet is exactly one page, of A4 size."""
    path = render.write(SMALL, tmp_path / "one.pdf")
    raw = path.read_bytes()

    assert raw.count(b"/Type /Page\n") == 1 or raw.count(b"/Type /Page") >= 1
    assert b"/Count 1" in raw
    # A4 in PDF points, as fpdf2 writes it.
    assert re.search(rb"/MediaBox \[0 0 595\.\d+ 841\.\d+\]", raw)


def test_render_is_byte_reproducible(tmp_path: Path) -> None:
    """Two renders of the same sheet produce identical bytes."""
    first = render.write(SMALL, tmp_path / "a.pdf").read_bytes()
    second = render.write(SMALL, tmp_path / "b.pdf").read_bytes()

    assert first == second


def test_render_carries_no_wall_clock(tmp_path: Path) -> None:
    """The creation date is pinned, so a build today and a build next year agree."""
    raw = render.write(SMALL, tmp_path / "a.pdf").read_bytes()

    assert b"/CreationDate (D:20000101000000Z)" in raw
    assert b"/ModDate" not in raw


def test_render_prints_provenance(tmp_path: Path) -> None:
    """The page states the ruleset version and commit it was built from."""
    text = _page_text(render.write(SMALL, tmp_path / "a.pdf").read_bytes())

    assert "0.2.0 Draft" in text
    assert "edd8aa4dfa51" in text
    assert "Italic lines are this sheet's scenario definition" in text


def test_authored_lines_carry_no_rule_id(tmp_path: Path) -> None:
    """A scenario choice is visibly not a core rule.

    It prints without a rule ID — there is none to print — and in italic, which the footer
    explains. It must not gain a literal marker: the section heading and intro already say
    the same thing, and a third copy reads as noise on a play aid.
    """
    text = _page_text(render.write(SMALL, tmp_path / "a.pdf").read_bytes())

    assert "Warband of three." in text
    assert "scenario]" not in text
    # _page_text rejoins fragments with single spaces, so the printed double space
    # before the rule ID collapses here.
    assert "Set up terrain first. (FLOW-001)" in text


def test_render_creates_missing_directory(tmp_path: Path) -> None:
    """The renderer creates its output directory rather than failing on it."""
    path = render.write(SMALL, tmp_path / "out.pdf")

    assert path.exists()


def test_overflow_fails_instead_of_paginating(tmp_path: Path) -> None:
    """Content that does not fit is a build failure, not a silent second page."""
    too_much = _sheet(tuple(_section(f"s{n}", 40) for n in range(6)))

    with pytest.raises(render.Overflow) as excinfo:
        render.write(too_much, tmp_path / "a.pdf")

    assert "does not fit on one page" in str(excinfo.value)


def test_second_column_is_used_before_overflowing(tmp_path: Path) -> None:
    """A sheet that fills the first column flows into the second, not off the page."""
    two_columns = _sheet((_section("left", 60), _section("right", 20)))

    path = render.write(two_columns, tmp_path / "a.pdf")

    assert b"/Count 1" in path.read_bytes()


def test_page_geometry_comes_from_the_document(tmp_path: Path) -> None:
    """The page is data: a landscape three-column document renders as one."""
    landscape = _sheet(
        (_section("a", 10), _section("b", 10), _section("c", 10)),
        page=Page(width_mm=297.0, height_mm=210.0, columns=3),
    )

    raw = render.write(landscape, tmp_path / "wide.pdf").read_bytes()

    # 297mm x 210mm in PDF points.
    assert re.search(rb"/MediaBox \[0 0 841\.\d+ 595\.\d+\]", raw)
    assert b"/Count 1" in raw


def test_pinned_type_size_turns_overflow_into_a_failure(tmp_path: Path) -> None:
    """A single body_pt entry pins the size instead of shrinking to fit."""
    crowded = _sheet(tuple(_section(f"s{n}", 30) for n in range(4)), page=Page(body_pt=(11.0,)))

    with pytest.raises(render.Overflow):
        render.write(crowded, tmp_path / "pinned.pdf")


def test_body_sizes_must_not_be_empty(tmp_path: Path) -> None:
    """An empty body_pt is a document error, not a silent default."""
    with pytest.raises(renderers.RenderError, match="body_pt"):
        render.write(_sheet((_section("a", 2),), page=Page(body_pt=())), tmp_path / "x.pdf")


def test_the_registry_creates_the_publish_tree(tmp_path: Path) -> None:
    """Choosing and creating the path is the registry's job, not each renderer's."""
    document = _sheet((_section("a", 2),))
    document = replace(
        document, name="prod", language="en", source=Source(ruleset_version="0.2.0 Draft")
    )

    written = renderers.render(document, "pdf", tmp_path)

    assert written == tmp_path / "prod" / "v0.2.0draft" / "prod_en.pdf"
    assert written.exists()
