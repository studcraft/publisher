"""The document a renderer consumes.

This is the pipeline's middle stage, and the only thing a renderer is allowed to read:

    ruleset AST  ->  document.json  ->  renderer  ->  output

A :class:`Document` carries both the content and the presentation parameters — page size,
margins, columns, type sizes — because a renderer that reached back into the ruleset, or
that hardcoded its geometry, would make the intermediate file decorative. The file is meant
to be edited by hand and re-rendered without re-reading the ruleset.

Everything here is frozen: extraction is a pure function, and an immutable result is the
cheapest way to keep it one.
"""

from __future__ import annotations

from dataclasses import dataclass, field, fields, replace
from typing import Any

SCHEMA_VERSION = 1


class DocumentError(Exception):
    """Raised when a document file is missing, malformed, or of an unknown schema."""


@dataclass(frozen=True)
class Outcome:
    """One row of a lookup: a condition and what it produces.

    A row may cite its own rule. The rows of one lookup often come from different rules —
    the three obstacle thresholds are three rules — and an entry that could cite only one
    would print a table whose other rows are anchored to nothing.
    """

    when: str
    then: str
    rule: str | None = None
    doc: str | None = None
    source_line: int | None = None


@dataclass(frozen=True)
class Line:
    """One entry on the sheet, and the rule it condenses.

    An entry takes one of three shapes, because at a table the three are read differently:

    - **prose** — ``text`` alone. A statement to read.
    - **lookup** — ``outcomes``. A dice result or threshold answered by scanning a column,
      not by reading a sentence and extracting the numbers from it.
    - **sequence** — ``steps``. A procedure followed in order.

    Any shape may carry a ``label``: the word a player's eye searches for, set apart from
    the value so finding it does not mean reading the line.

    ``doc`` and ``source_line`` are attached from the ruleset so any entry can be checked
    against the rule it claims to state.

    ``rule`` is ``None`` only for an entry the publisher authored rather than took from the
    ruleset — the scenario definition the ruleset deliberately leaves open. Such an entry
    must say so explicitly, and the renderer sets it apart, so nobody reads a scenario
    choice as a core rule.
    """

    rule: str | None
    text: str = ""
    label: str = ""
    outcomes: tuple[Outcome, ...] = ()
    steps: tuple[str, ...] = ()
    doc: str | None = None
    source_line: int | None = None

    @property
    def authored(self) -> bool:
        """True when this entry is a scenario choice, not a rule from the ruleset."""
        return self.rule is None

    @property
    def cited(self) -> tuple[str, ...]:
        """Return every rule this entry cites, the entry's own first, without repeats."""
        ids = [self.rule] + [o.rule for o in self.outcomes]
        seen: dict[str, None] = {}
        for rule_id in ids:
            if rule_id:
                seen.setdefault(rule_id, None)
        return tuple(seen)

    @property
    def kind(self) -> str:
        """Return which of the three shapes this entry takes."""
        if self.outcomes:
            return "lookup"
        if self.steps:
            return "sequence"
        return "prose"


@dataclass(frozen=True)
class Section:
    """A headed group of lines."""

    id: str
    heading: str
    intro: str = ""
    lines: tuple[Line, ...] = ()


@dataclass(frozen=True)
class Page:
    """The presentation parameters a renderer lays the document out with.

    These live in the document rather than in renderer code so that changing the page is
    editing data, not editing Python. A renderer that cannot honour a parameter should say
    so rather than ignore it.

    ``body_pt`` is the list of body type sizes to try, largest first; the first that fits
    wins. A single-entry list pins the size and turns overflow into a hard failure.
    """

    format: str = "A4"
    width_mm: float = 210.0
    height_mm: float = 297.0
    margin_mm: float = 10.0
    columns: int = 2
    gutter_mm: float = 6.0
    header_mm: float = 11.0
    footer_mm: float = 6.0
    title_pt: float = 15.0
    footer_pt: float = 6.0
    body_pt: tuple[float, ...] = (11.0, 10.5, 10.0, 9.5, 9.0, 8.5, 8.0, 7.5, 7.0, 6.5, 6.0)
    heading_ratio: float = 1.30
    line_height_ratio: float = 0.425
    heading_lead_ratio: float = 0.42
    section_gap_ratio: float = 0.30

    @classmethod
    def from_dict(cls, payload: Any) -> Page:
        """Return a page from ``payload``, keeping defaults for anything absent."""
        return _build(cls, payload, "page")

    @property
    def column_width_mm(self) -> float:
        """Return the width of one column, from the page width, margins and gutter."""
        gutters = self.gutter_mm * (self.columns - 1)
        return (self.width_mm - 2 * self.margin_mm - gutters) / self.columns

    def column_x_mm(self) -> tuple[float, ...]:
        """Return the left edge of each column."""
        step = self.column_width_mm + self.gutter_mm
        return tuple(self.margin_mm + step * n for n in range(self.columns))


@dataclass(frozen=True)
class Source:
    """Where the content came from, so any output can be traced back to it."""

    repo: str = ""
    ruleset_version: str = ""
    commit: str = ""


@dataclass(frozen=True)
class Document:
    """A whole document: what to print, how to print it, and where it came from.

    ``name`` and ``language`` are identity, not decoration: together with the ruleset
    version in ``source`` they determine where a rendered output is published, so that two
    languages of the same sheet, or the same sheet against two ruleset versions, can never
    land on the same path.
    """

    title: str
    sections: tuple[Section, ...]
    name: str = "document"
    language: str = "en"
    page: Page = field(default_factory=Page)
    source: Source = field(default_factory=Source)
    glossary: tuple[str, ...] = ()
    schema: int = SCHEMA_VERSION

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-ready mapping. Key order is fixed so the file diffs cleanly."""
        return {
            "schema": self.schema,
            "name": self.name,
            "language": self.language,
            "title": self.title,
            "source": _as_dict(self.source),
            "page": _as_dict(self.page),
            "glossary": list(self.glossary),
            "sections": [
                {
                    "id": section.id,
                    "heading": section.heading,
                    "intro": section.intro,
                    "lines": [_line_dict(line) for line in section.lines],
                }
                for section in self.sections
            ],
        }

    @classmethod
    def from_dict(cls, payload: Any) -> Document:
        """Return the document ``payload`` describes, failing by name on any problem."""
        if not isinstance(payload, dict):
            raise DocumentError(f"Expected an object, got {type(payload).__name__}.")

        schema = payload.get("schema")
        if schema != SCHEMA_VERSION:
            raise DocumentError(
                f"Unknown document schema {schema!r}; this build understands {SCHEMA_VERSION}."
            )

        raw_sections = payload.get("sections")
        if not isinstance(raw_sections, list) or not raw_sections:
            raise DocumentError("The document has no sections.")

        sections = []
        for position, raw in enumerate(raw_sections):
            if not isinstance(raw, dict):
                raise DocumentError(f"sections[{position}] is not an object.")
            for required in ("id", "heading"):
                if not raw.get(required):
                    raise DocumentError(f"sections[{position}] is missing {required!r}.")
            lines = []
            for index, entry in enumerate(raw.get("lines") or []):
                lines.append(_read_line(entry, f"section {raw['id']!r} line {index}"))
            if not lines:
                raise DocumentError(f"section {raw['id']!r} has no lines.")
            sections.append(
                Section(
                    id=raw["id"],
                    heading=raw["heading"],
                    intro=raw.get("intro", ""),
                    lines=tuple(lines),
                )
            )

        return cls(
            title=payload.get("title", ""),
            sections=tuple(sections),
            name=payload.get("name") or "document",
            language=payload.get("language") or "en",
            page=_build(Page, payload.get("page"), "page"),
            source=_build(Source, payload.get("source"), "source"),
            glossary=tuple(payload.get("glossary") or ()),
            schema=schema,
        )


def _line_dict(line: Line) -> dict[str, Any]:
    """Return one entry as a mapping, omitting the shapes it does not use.

    Absent keys rather than empty ones: a prose entry carrying ``"outcomes": []`` invites
    the reader to wonder which shape it really is.
    """
    out: dict[str, Any] = {"rule": line.rule}
    if line.label:
        out["label"] = line.label
    if line.text:
        out["text"] = line.text
    if line.outcomes:
        out["outcomes"] = [
            {
                "when": o.when,
                "then": o.then,
                "rule": o.rule,
                "doc": o.doc,
                "source_line": o.source_line,
            }
            for o in line.outcomes
        ]
    if line.steps:
        out["steps"] = list(line.steps)
    out["doc"] = line.doc
    out["source_line"] = line.source_line
    return out


def _read_line(entry: Any, where: str) -> Line:
    """Return the entry ``entry`` describes, failing by name on any problem."""
    if not isinstance(entry, dict):
        raise DocumentError(f"{where} is not an object.")

    outcomes = []
    for position, raw in enumerate(entry.get("outcomes") or []):
        if not isinstance(raw, dict):
            raise DocumentError(f"{where} outcome {position} is not an object.")
        for required in ("when", "then"):
            if not raw.get(required):
                raise DocumentError(f"{where} outcome {position} is missing {required!r}.")
        outcomes.append(
            Outcome(
                when=raw["when"],
                then=raw["then"],
                rule=raw.get("rule"),
                doc=raw.get("doc"),
                source_line=raw.get("source_line"),
            )
        )

    steps = tuple(entry.get("steps") or ())
    shapes = [
        name
        for name, used in (("text", entry.get("text")), ("outcomes", outcomes), ("steps", steps))
        if used
    ]
    if not shapes:
        raise DocumentError(f"{where} has no 'text', 'outcomes' or 'steps'; it prints nothing.")
    if len(shapes) > 1:
        raise DocumentError(
            f"{where} has {' and '.join(shapes)}. An entry takes one shape: a statement to "
            "read, a lookup to scan, or a sequence to follow."
        )

    return Line(
        rule=entry.get("rule"),
        text=entry.get("text", ""),
        label=entry.get("label", ""),
        outcomes=tuple(outcomes),
        steps=steps,
        doc=entry.get("doc"),
        source_line=entry.get("source_line"),
    )


def _as_dict(value: Any) -> dict[str, Any]:
    """Return a flat dataclass as a mapping, tuples become lists."""
    out = {}
    for spec in fields(value):
        item = getattr(value, spec.name)
        out[spec.name] = list(item) if isinstance(item, tuple) else item
    return out


def _build(cls: type, payload: Any, where: str) -> Any:
    """Return ``cls`` built from ``payload``, keeping defaults for anything absent.

    An unknown key is an error rather than a shrug: a misspelled ``margin_mm`` that is
    silently ignored looks exactly like a renderer that does not honour margins.
    """
    if payload is None:
        return cls()
    if not isinstance(payload, dict):
        raise DocumentError(f"{where} is not an object.")

    known = {spec.name: spec for spec in fields(cls)}
    unknown = sorted(set(payload) - set(known))
    if unknown:
        raise DocumentError(
            f"{where} has unknown key(s): {', '.join(unknown)}. "
            f"Known keys: {', '.join(sorted(known))}."
        )

    values = {}
    for name, value in payload.items():
        default = getattr(cls(), name)
        values[name] = tuple(value) if isinstance(default, tuple) else value
    return replace(cls(), **values)
