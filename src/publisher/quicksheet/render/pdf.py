"""Render a :class:`~publisher.quicksheet.model.Document` to a one-sided PDF.

Every measurement comes from the document's ``page``, never from a constant here: changing
the page is editing data, not editing this file. What stays here is the mechanism — column
balancing, glossary highlighting, and the values that keep the output byte-reproducible.

Reproducibility: the creation date, producer and creator strings are pinned and the font is
a PDF core font, so no font file is embedded. ``fpdf2`` derives the trailer ``/ID`` from the
document content, so with those pinned the bytes are identical across runs, machines and
hash seeds.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from fpdf import FPDF

from publisher.quicksheet.model import Document, Line, Page, Section
from publisher.quicksheet.render import RenderError

FIXED_DATE = datetime(2000, 1, 1, tzinfo=timezone.utc)
PRODUCER = "publisher-quicksheet"
EXTENSION = "pdf"

# PDF core fonts cover latin-1 and nothing else, and using one is what keeps the output
# byte-reproducible without embedding a font file. These typographic characters are common
# enough in authored prose to be worth converting rather than rejecting. Anything not listed
# fails loudly: silently dropping a character would change what the document says.
_SUBSTITUTIONS = {
    "—": "-",  # em dash
    "–": "-",  # en dash
    "‘": "'",
    "’": "'",
    "“": '"',
    "”": '"',
    "…": "...",
    " ": " ",
    "→": "->",
    "×": "x",
}


class UnsupportedCharacter(RenderError):
    """Raised when text carries a character the PDF core font cannot print."""


class Overflow(RenderError):
    """Raised when the content does not fit on one page.

    A sheet that quietly became two pages is worse than a red build: nobody re-reads a PDF
    they have already approved.
    """


def _printable(text: str) -> str:
    """Return ``text`` with known typographic characters converted, failing on the rest."""
    converted = "".join(_SUBSTITUTIONS.get(char, char) for char in text)
    try:
        converted.encode("latin-1")
    except UnicodeEncodeError as exc:
        bad = converted[exc.start : exc.end]
        raise UnsupportedCharacter(
            f"Character {bad!r} in {text!r} is not in latin-1, so the PDF core font cannot "
            "print it. Rewrite the line, or add a substitution to pdf._SUBSTITUTIONS."
        ) from exc
    return converted


@dataclass(frozen=True)
class Metrics:
    """The measurements that follow from one body size, given the document's page."""

    body: float
    heading: float
    line_height: float
    heading_lead: float
    section_gap: float

    @classmethod
    def for_body(cls, body: float, page: Page) -> Metrics:
        """Return the metrics for ``body``, using the page's ratios."""
        return cls(
            body=body,
            heading=body * page.heading_ratio,
            line_height=body * page.line_height_ratio,
            heading_lead=body * page.heading_lead_ratio,
            section_gap=body * page.section_gap_ratio,
        )


def write(document: Document, path: Path) -> Path:
    """Write ``document`` to ``path`` as a one-sided PDF and return the path."""
    page = document.page
    if page.columns < 1:
        raise RenderError(f"page.columns must be at least 1, got {page.columns}.")
    if not page.body_pt:
        raise RenderError("page.body_pt is empty; give at least one type size to try.")

    for body in page.body_pt:
        try:
            pdf = _compose(document, Metrics.for_body(body, page))
        except Overflow:
            continue
        pdf.output(str(path))
        return path

    raise Overflow(
        f"The document does not fit on one page even at {min(page.body_pt)}pt. "
        "Shorten it, add a column, or lower page.body_pt."
    )


def _new_document(document: Document) -> FPDF:
    """Return an FPDF document with the page applied and every varying value pinned."""
    page = document.page
    pdf = FPDF(orientation="P", unit="mm", format=(page.width_mm, page.height_mm))
    pdf.set_creation_date(FIXED_DATE)
    pdf.set_producer(PRODUCER)
    pdf.set_creator(PRODUCER)
    pdf.set_title(document.title)
    pdf.set_auto_page_break(False)
    pdf.set_margins(page.margin_mm, page.margin_mm, page.margin_mm)
    return pdf


def _compose(document: Document, metrics: Metrics) -> FPDF:
    """Lay the document out at ``metrics``, raising :class:`Overflow` if it does not fit."""
    page = document.page
    pdf = _new_document(document)
    pdf.add_page()

    text_width = page.width_mm - 2 * page.margin_mm
    pdf.set_font("Helvetica", "B", page.title_pt)
    pdf.set_xy(page.margin_mm, page.margin_mm)
    pdf.cell(text_width, 6, _printable(document.title), align="L")

    column_top = page.margin_mm + page.header_mm
    column_x = page.column_x_mm()
    column_bottom = page.height_mm - page.margin_mm - page.footer_mm
    column_height = column_bottom - column_top
    width = page.column_width_mm

    column = 0
    y = column_top

    pattern = _term_pattern(document.glossary)
    heights = [_section_height(pdf, s, metrics, pattern, width) for s in document.sections]
    # Balance the columns rather than filling the first and leaving the rest empty.
    per_column = (sum(heights) + metrics.section_gap * (len(heights) - 1)) / page.columns

    for section, height in zip(document.sections, heights):
        used = y - column_top
        # Break at whichever side of this section leaves the columns closest in height,
        # not at the first section that crosses the boundary.
        needs_break = used + height > column_height or (
            column < page.columns - 1 and used > 0 and used + height / 2 > per_column
        )
        if needs_break:
            column += 1
            y = column_top
            if column >= page.columns:
                raise Overflow(
                    f"Section {section.id!r} does not fit in {page.columns} column(s) on one "
                    f"{page.format} page. Shorten it, or raise page.columns."
                )
        if y + height > column_bottom:
            raise Overflow(
                f"Section {section.id!r} is taller than a column. "
                "Split it, or shorten the document."
            )
        y = _draw_section(pdf, section, column_x[column], y, metrics, pattern, width)
        y += metrics.section_gap

    _draw_footer(pdf, document)

    if pdf.page_no() != 1:
        raise Overflow(f"Rendered {pdf.page_no()} pages; the sheet must be exactly one.")
    return pdf


def _term_pattern(terms: Iterable[str]) -> re.Pattern[str] | None:
    """Return a pattern matching any glossary term, or ``None`` when there are none.

    Matching is case-sensitive because StudCraft capitalises its defined terms: that is
    what separates "a Turn ends" the defined term from "turn the model" the verb, and it
    is the difference between a useful highlight and a page of noise. A trailing "s" is
    allowed so "Impacts" still matches "Impact".
    """
    terms = [term for term in terms if term]
    if not terms:
        return None
    # Longest first so "Weapon Front Footprint" wins over "Weapon Front".
    alternatives = "|".join(
        re.escape(term) + ("" if term.endswith("s") else "s?")
        for term in sorted(terms, key=lambda term: (-len(term), term))
    )
    return re.compile(rf"(?<![\w-])({alternatives})(?![\w-])")


def _split_terms(text: str, pattern: re.Pattern[str] | None) -> list[tuple[str, bool]]:
    """Return ``text`` as (fragment, is_term) pairs, in order."""
    if pattern is None:
        return [(text, False)]
    parts = []
    position = 0
    for match in pattern.finditer(text):
        if match.start() > position:
            parts.append((text[position : match.start()], False))
        parts.append((match.group(0), True))
        position = match.end()
    if position < len(text):
        parts.append((text[position:], False))
    return parts or [(text, False)]


def _words(text: str, pattern: re.Pattern[str] | None) -> list[tuple[tuple[str, bool], ...]]:
    """Return ``text`` as words, each a tuple of (fragment, is_term) runs.

    A word is what whitespace separates, which is not the same as what term matching
    separates. "Priority." is one word made of a bold run and a plain full stop; splitting
    on the term boundary instead would put a space before the full stop. A multi-word term
    like "Attack Dice" is two words, each entirely bold.
    """
    words: list[tuple[tuple[str, bool], ...]] = []
    current: list[tuple[str, bool]] = []
    for fragment, is_term in _split_terms(text, pattern):
        for piece in re.split(r"(\s+)", fragment):
            if not piece:
                continue
            if piece.isspace():
                if current:
                    words.append(tuple(current))
                    current = []
            else:
                current.append((piece, is_term))
    if current:
        words.append(tuple(current))
    return words


def _style(base: str, bold: bool) -> str:
    """Return the FPDF font style for ``base`` with the glossary highlight applied."""
    return f"B{base}" if bold else base


def _wrapped(
    pdf: FPDF,
    text: str,
    width: float,
    size: float,
    base: str = "",
    pattern: re.Pattern[str] | None = None,
) -> list[list[tuple[tuple[str, bool], ...]]]:
    """Return ``text`` wrapped to ``width`` as lines of words.

    Words are measured in the style they will be drawn in — bold Helvetica is wider than
    regular — so the wrap and the drawing cannot disagree.
    """
    words = _words(text, pattern)
    if not words:
        return [[]]

    def measure(fragment: str, bold: bool) -> float:
        pdf.set_font("Helvetica", _style(base, bold), size)
        return pdf.get_string_width(fragment)

    space = measure(" ", False)
    lines: list[list[tuple[tuple[str, bool], ...]]] = []
    current: list[tuple[tuple[str, bool], ...]] = []
    used = 0.0
    for word in words:
        advance = sum(measure(fragment, is_term) for fragment, is_term in word)
        gap = space if current else 0.0
        if current and used + gap + advance > width:
            lines.append(current)
            current, used = [word], advance
        else:
            current.append(word)
            used += gap + advance
    lines.append(current)
    return lines


def _draw_wrapped(
    pdf: FPDF,
    lines: list[list[tuple[tuple[str, bool], ...]]],
    x: float,
    y: float,
    size: float,
    base: str,
    line_height: float,
) -> float:
    """Draw pre-wrapped lines at ``x``/``y`` and return the y position just below them."""
    for words in lines:
        cursor = x
        for position, word in enumerate(words):
            if position:
                pdf.set_font("Helvetica", base, size)
                cursor += pdf.get_string_width(" ")
            for fragment, is_term in word:
                pdf.set_font("Helvetica", _style(base, is_term), size)
                advance = pdf.get_string_width(fragment)
                pdf.set_xy(cursor, y)
                pdf.cell(advance, line_height, fragment, align="L")
                cursor += advance
        y += line_height
    return y


def _section_body(section: Section) -> list[tuple[str, str]]:
    """Return the section's drawable text as (font style, text) pairs, in order."""
    body = []
    if section.intro:
        body.append(("I", _printable(section.intro)))
    for line in section.lines:
        body.append(("I" if line.authored else "", _line_text(line)))
    return body


def _line_text(line: Line) -> str:
    """Return the printed form of ``line``.

    A rule-anchored line carries its rule ID, so a disputed call can be looked up in the
    ruleset. An authored line carries no ID because there is none to carry, and that
    absence is the marker: it is set in italic and the footer says what italic means. A
    literal "[scenario]" prefix was tried and removed — on a play aid it reads as noise
    beside a heading and an intro that already say the same thing.
    """
    if line.authored:
        return _printable(line.text)
    return _printable(f"{line.text}  ({line.rule})")


def _section_height(
    pdf: FPDF,
    section: Section,
    metrics: Metrics,
    pattern: re.Pattern[str] | None,
    width: float,
) -> float:
    """Return the vertical space ``section`` needs, without drawing it."""
    height = metrics.heading_lead + metrics.line_height
    for base, text in _section_body(section):
        height += metrics.line_height * len(_wrapped(pdf, text, width, metrics.body, base, pattern))
    return height


def _draw_section(
    pdf: FPDF,
    section: Section,
    x: float,
    y: float,
    metrics: Metrics,
    pattern: re.Pattern[str] | None,
    width: float,
) -> float:
    """Draw ``section`` at ``x``/``y`` and return the y position just below it."""
    y += metrics.heading_lead
    pdf.set_font("Helvetica", "B", metrics.heading)
    pdf.set_xy(x, y)
    pdf.cell(width, metrics.line_height, _printable(section.heading), align="L")
    y += metrics.line_height

    for base, text in _section_body(section):
        lines = _wrapped(pdf, text, width, metrics.body, base, pattern)
        y = _draw_wrapped(pdf, lines, x, y, metrics.body, base, metrics.line_height)

    return y


def _draw_footer(pdf: FPDF, document: Document) -> None:
    """Print the provenance line, so any output can be traced to the rules it came from."""
    page, source = document.page, document.source
    pdf.set_font("Helvetica", "", page.footer_pt)
    pdf.set_xy(page.margin_mm, page.height_mm - page.margin_mm - 3.0)
    pdf.cell(
        page.width_mm - 2 * page.margin_mm,
        3.0,
        _printable(
            f"StudCraft ruleset {source.ruleset_version} @ {source.commit[:12]}. "
            "Italic lines are this sheet's scenario definition, not core rules."
        ),
        align="L",
    )
