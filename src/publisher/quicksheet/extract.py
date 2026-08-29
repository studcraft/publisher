"""Turn the ruleset AST and the specification file into a document.

This is the pipeline's first half:

    ruleset AST + spec.toml  ->  Document  ->  document.json

It does not write rules text. For each authored line its only jobs are to confirm the cited
rule ID resolves in the pinned ruleset, attach that rule's source document and line for
traceability, and fail the build when the ID is gone.

It is a pure function: no clock, no network, no randomness, and no iteration over an
unordered collection.
"""

from __future__ import annotations

import sys
from pathlib import Path

from publisher.quicksheet.index import Rule, UnknownRuleError, rule
from publisher.quicksheet.model import (
    Document,
    DocumentError,
    Line,
    Page,
    Section,
    Source,
)

if sys.version_info >= (3, 11):
    import tomllib
else:  # pragma: no cover - exercised on the CI interpreter, not the local one
    import tomli as tomllib


class SpecError(Exception):
    """Raised when the specification file is malformed or cites a rule that is gone."""


# Every key each table accepts. An unknown key is an error rather than a shrug: a
# misspelled `intro` that is silently ignored looks exactly like a renderer that does not
# print intros, and that is a much more expensive thing to debug.
_TOP_KEYS = frozenset({"language", "title", "name", "page", "section"})
_SECTION_KEYS = frozenset({"id", "heading", "intro", "line"})
_LINE_KEYS = frozenset({"rule", "text", "authored"})


def _reject_unknown(table: dict, known: frozenset, where: str) -> None:
    """Fail when ``table`` carries a key ``known`` does not list."""
    unknown = sorted(set(table) - known)
    if unknown:
        raise SpecError(
            f"{where} has unknown key(s): {', '.join(unknown)}. "
            f"Known keys: {', '.join(sorted(known))}."
        )


def load_spec(path: Path) -> dict:
    """Return the parsed specification file at ``path``."""
    if not path.exists():
        raise SpecError(f"No specification file at {path}.")
    try:
        return tomllib.loads(path.read_text(encoding="utf-8"))
    except tomllib.TOMLDecodeError as exc:
        raise SpecError(f"{path} is not valid TOML: {exc}") from exc


def _section_lines(raw: dict, section_id: str, index: dict[str, Rule]) -> tuple[Line, ...]:
    """Resolve one section's lines against the ruleset, failing by name on any problem."""
    lines = []
    for position, entry in enumerate(raw.get("line", [])):
        where = f"section {section_id!r} line {position}"
        if not isinstance(entry, dict):
            raise SpecError(f"{where} is not a table.")
        _reject_unknown(entry, _LINE_KEYS, where)
        text = entry.get("text")
        if not text:
            raise SpecError(f"{where} is missing 'text'.")

        if entry.get("authored"):
            if entry.get("rule"):
                raise SpecError(
                    f"{where} sets authored = true and also cites {entry['rule']}. "
                    "A line is either the publisher's scenario choice or a rule from the "
                    "ruleset; it cannot be both."
                )
            lines.append(Line(rule=None, text=text, doc=None, source_line=None))
            continue

        rule_id = entry.get("rule")
        if not rule_id:
            raise SpecError(f"{where} is missing 'rule'. Set authored = true if intentional.")
        try:
            resolved = rule(index, rule_id)
        except UnknownRuleError as exc:
            raise SpecError(f"{where} cites {rule_id}, which is not in the ruleset: {exc}") from exc
        lines.append(Line(rule=rule_id, text=text, doc=resolved.doc, source_line=resolved.line))
    if not lines:
        raise SpecError(f"section {section_id!r} has no lines.")
    return tuple(lines)


def build_document(
    index: dict[str, Rule],
    spec: dict,
    source: Source,
    glossary: tuple[str, ...] = (),
    name: str = "",
) -> Document:
    """Return the document ``spec`` describes, resolved against the pinned ``index``.

    Presentation parameters come from the spec's optional ``[page]`` table and land in the
    document, so a later render never needs the ruleset or the spec again.
    """
    _reject_unknown(spec, _TOP_KEYS, "The specification file")

    raw_sections = spec.get("section")
    if not raw_sections:
        raise SpecError("The specification file declares no sections.")

    sections = []
    for position, raw in enumerate(raw_sections):
        if not isinstance(raw, dict):
            raise SpecError(f"section {position} is not a table.")
        _reject_unknown(raw, _SECTION_KEYS, f"section {position}")
        section_id = raw.get("id")
        if not section_id:
            raise SpecError(f"section {position} is missing 'id'.")
        heading = raw.get("heading")
        if not heading:
            raise SpecError(f"section {section_id!r} is missing 'heading'.")
        sections.append(
            Section(
                id=section_id,
                heading=heading,
                intro=raw.get("intro", ""),
                lines=_section_lines(raw, section_id, index),
            )
        )

    try:
        page = Page.from_dict(spec.get("page"))
    except DocumentError as exc:
        raise SpecError(str(exc)) from exc

    language = spec.get("language")
    if not language:
        raise SpecError(
            "The specification file declares no 'language'. Publishing without one would "
            "collide with the sheet's own translations."
        )

    return Document(
        title=spec.get("title", "StudCraft Quick Sheet"),
        sections=tuple(sections),
        name=spec.get("name") or name,
        language=language,
        page=page,
        source=source,
        glossary=tuple(glossary),
    )


def draft_spec(index: dict[str, Rule], rule_ids: list[str]) -> str:
    """Return a draft specification file built mechanically from the cited rules.

    This is a bootstrap for authoring, not the shipping path. Rule prose is written for a
    reference document, not for a two-column A4; every line this emits is expected to be
    rewritten by hand and then checked against its source.
    """
    out = [
        'language = "en"',
        'title = "StudCraft Quick Sheet — 3v3"',
        "",
        "[[section]]",
        'id = "draft"',
        'heading = "Draft"',
        "",
    ]
    for rule_id in rule_ids:
        resolved = rule(index, rule_id)
        first = next(
            (" ".join(block.lines) for block in resolved.blocks if block.kind == "paragraph"),
            resolved.title,
        )
        out.append("[[section.line]]")
        out.append(f'rule = "{rule_id}"')
        out.append(f"text = {_toml_string(first)}")
        out.append("")
    return "\n".join(out)


def _toml_string(value: str) -> str:
    """Return ``value`` as a TOML basic string."""
    escaped = value.replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'
