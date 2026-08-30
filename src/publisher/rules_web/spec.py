"""The authored half of the web edition: which ruleset documents are published, and as what.

The specification names documents and nothing else. It does not restate a rule, choose a
rule's slug, or order the rules within a document — all of that follows from the ruleset, and
a second copy here would drift from it. What it does own is the two things the ruleset cannot
know: which of its documents belong on the web at all, and what a document is called there.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path

from publisher.rules_web.slugs import document_slug

if sys.version_info >= (3, 11):
    import tomllib
else:  # pragma: no cover - exercised on the CI interpreter, not the local one
    import tomli as tomllib


class SpecError(Exception):
    """Raised when the specification file is missing or malformed."""


# An unknown key is an error rather than a shrug: a misspelled `slug` that is silently
# ignored looks exactly like slug overrides not working, and that is far more expensive to
# debug than a failed build.
_TOP_KEYS = frozenset({"title", "language", "base_path", "name", "root", "document"})
_ROOT_KEYS = frozenset({"slug", "title", "intro"})
_DOCUMENT_KEYS = frozenset({"file", "slug", "title", "intro"})

DEFAULT_ROOT_SLUG = "rules"


@dataclass(frozen=True)
class RootSpec:
    """The single page every published document hangs from.

    It exists so the site has one thing called "Rules" rather than thirteen top-level
    entries in reading order that a visitor has to recognise as a set.
    """

    slug: str
    title: str
    intro: str = ""


@dataclass(frozen=True)
class DocumentSpec:
    """One ruleset document to publish, and the page it becomes."""

    file: str
    slug: str
    title: str
    intro: str = ""


@dataclass(frozen=True)
class Spec:
    """The whole specification: the edition's identity and the documents it publishes."""

    title: str
    language: str
    base_path: str
    name: str
    root: RootSpec
    documents: tuple[DocumentSpec, ...]


def load(path: Path) -> Spec:
    """Return the specification at ``path``, failing by name on any problem."""
    if not path.exists():
        raise SpecError(f"No specification file at {path}.")
    try:
        raw = tomllib.loads(path.read_text(encoding="utf-8"))
    except tomllib.TOMLDecodeError as exc:
        raise SpecError(f"{path} is not valid TOML: {exc}") from exc
    return from_dict(raw, str(path))


def from_dict(raw: dict, where: str) -> Spec:
    """Return the specification ``raw`` describes."""
    _reject_unknown(raw, _TOP_KEYS, where)

    entries = raw.get("document") or []
    if not entries:
        raise SpecError(f"{where} publishes no documents; it lists no [[document]] tables.")

    documents = []
    seen: dict[str, str] = {}
    for position, entry in enumerate(entries):
        spec = _document(entry, f"{where} document {position}")
        if spec.slug in seen:
            raise SpecError(
                f"{where} gives the slug {spec.slug!r} to both {seen[spec.slug]!r} and "
                f"{spec.file!r}. Two documents cannot publish to the same URL."
            )
        seen[spec.slug] = spec.file
        documents.append(spec)

    root = _root(raw.get("root") or {}, f"{where} root")
    if root.slug in seen:
        raise SpecError(
            f"{where} gives the root page the slug {root.slug!r}, which the document "
            f"{seen[root.slug]!r} already uses. They would publish to the same URL."
        )

    return Spec(
        root=root,
        title=raw.get("title", ""),
        language=raw.get("language") or "en",
        base_path=raw.get("base_path", "").strip("/"),
        name=raw.get("name") or "rules_web",
        documents=tuple(documents),
    )


def _root(entry: object, where: str) -> RootSpec:
    """Return the root page entry, defaulting everything that is not given."""
    if not isinstance(entry, dict):
        raise SpecError(f"{where} is not a table.")
    _reject_unknown(entry, _ROOT_KEYS, where)
    return RootSpec(
        slug=entry.get("slug") or DEFAULT_ROOT_SLUG,
        title=entry.get("title") or "Rules",
        intro=entry.get("intro", ""),
    )


def _document(entry: object, where: str) -> DocumentSpec:
    """Return one document entry, failing by name on any problem."""
    if not isinstance(entry, dict):
        raise SpecError(f"{where} is not a table.")
    _reject_unknown(entry, _DOCUMENT_KEYS, where)

    file = entry.get("file")
    if not file:
        raise SpecError(f"{where} is missing 'file', the ruleset document it publishes.")

    return DocumentSpec(
        file=file,
        slug=entry.get("slug") or document_slug(file),
        title=entry.get("title", ""),
        intro=entry.get("intro", ""),
    )


def _reject_unknown(table: dict, known: frozenset, where: str) -> None:
    """Fail when ``table`` carries a key ``known`` does not list."""
    unknown = sorted(set(table) - known)
    if unknown:
        raise SpecError(
            f"{where} has unknown key(s): {', '.join(unknown)}. "
            f"Known keys: {', '.join(sorted(known))}."
        )
