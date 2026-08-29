"""Turn the pinned ruleset and the specification into the web edition's document.

    ruleset AST + spec.toml  ->  Document  ->  document.json

It is a pure function of the pinned ruleset and the specification: no clock, no network, no
randomness, and no iteration over an unordered collection. Rules keep the order the ruleset
gives them, and documents keep the order the specification lists them in, so the same inputs
always produce the same file.
"""

from __future__ import annotations

import hashlib
import posixpath
from pathlib import Path

from publisher.quicksheet.index import Rule
from publisher.quicksheet.model import Source
from publisher.rules_web import markup
from publisher.rules_web.model import DOCUMENT, RULE, Document, Entry, Media, Page
from publisher.rules_web.slugs import rule_slug
from publisher.rules_web.spec import Spec

# Where the ruleset keeps the documents an embed's relative path is resolved against.
DOCS = "docs"


class ExtractError(Exception):
    """Raised when the ruleset and the specification cannot be reconciled."""


def build(spec: Spec, index: dict[str, Rule], source: Source, clone_root: Path) -> Document:
    """Return the document ``spec`` describes, built from the rules in ``index``."""
    by_document = _group(index)
    _check_documents(spec, by_document)

    published = {
        rule_id: _page_path(spec.base_path, entry.slug, rule_slug(rule_id))
        for entry in spec.documents
        for rule_id in by_document.get(entry.file, ())
    }
    unpublished = frozenset(set(index) - set(published))

    collector = _Media(clone_root)
    pages: list[Page] = []

    for entry in spec.documents:
        rule_ids = by_document[entry.file]
        pages.append(
            Page(
                slug=entry.slug,
                title=entry.title or _document_title(entry.file),
                kind=DOCUMENT,
                intro=entry.intro,
                entries=tuple(
                    Entry(
                        rule=rule_id,
                        title=index[rule_id].title,
                        slug=rule_slug(rule_id),
                    )
                    for rule_id in rule_ids
                ),
                doc=entry.file,
            )
        )
        for rule_id in rule_ids:
            rule = index[rule_id]
            pages.append(
                Page(
                    slug=rule_slug(rule_id),
                    title=f"{rule_id} — {rule.title}",
                    kind=RULE,
                    parent=entry.slug,
                    body_html=markup.render(
                        body(rule),
                        links=published,
                        on_image=collector.for_page(rule_slug(rule_id)),
                        where=f"{rule_id} ({rule.doc})",
                        skip=rule_id,
                        unpublished=unpublished,
                    ),
                    rule=rule_id,
                    doc=rule.doc,
                    source_line=rule.line,
                )
            )

    return Document(
        title=spec.title,
        name=spec.name,
        language=spec.language,
        base_path=spec.base_path,
        pages=tuple(pages),
        media=collector.collected(),
        source=source,
    )


def body(rule: Rule) -> str:
    """Return a rule's body as the Markdown it was written in.

    The parser hands a rule back as typed blocks, each holding the lines it spans. Joining
    them with a blank line reconstructs the Markdown the author wrote, which is what the
    renderer needs: a list has to arrive as a list, not as the lines of one.

    ``break`` blocks are the horizontal rules separating rules in the source document. They
    are punctuation between rules, not part of any rule, and a page that ends in a rule is
    not improved by a line under it.
    """
    return "\n\n".join("\n".join(block.lines) for block in rule.blocks if block.kind != "break")


class _Media:
    """Collects the images the pages embed, once each, in the order they were met."""

    def __init__(self, clone_root: Path) -> None:
        self._clone_root = clone_root
        self._items: dict[str, Media] = {}

    def for_page(self, slug: str):
        """Return the callback that records an embed found on the page ``slug``."""

        def record(source: str, alt: str) -> str:
            return self._record(source, alt, slug)

        return record

    def _record(self, source: str, alt: str, slug: str) -> str:
        """Register one embed and return the filename the page should refer to."""
        relative = posixpath.normpath(posixpath.join(DOCS, source))
        if relative.startswith(".."):
            raise ExtractError(
                f"The page {slug!r} embeds {source!r}, which resolves outside the ruleset "
                "clone. An image has to come from the ruleset it illustrates."
            )

        path = self._clone_root / relative
        if not path.is_file():
            raise ExtractError(
                f"The page {slug!r} embeds {source!r}, which is not in the ruleset clone at "
                f"{path}. The ruleset embeds an image only when the file exists, so this "
                "means the clone is incomplete rather than that the drawing is pending."
            )

        filename = posixpath.basename(relative)
        existing = self._items.get(filename)
        if existing is None:
            self._items[filename] = Media(
                filename=filename,
                source=relative,
                alt=alt,
                attach_to=slug,
                content_hash=_hash(path.read_bytes()),
            )
        elif existing.source != relative:
            raise ExtractError(
                f"Two different files are both published as {filename!r}: "
                f"{existing.source!r} and {relative!r}. They would overwrite each other."
            )
        return filename

    def collected(self) -> tuple[Media, ...]:
        """Return every image met, in the order the pages embedded them."""
        return tuple(self._items.values())


def _group(index: dict[str, Rule]) -> dict[str, list[str]]:
    """Return the rule IDs of each ruleset document, in the order the ruleset gives them."""
    grouped: dict[str, list[str]] = {}
    for rule_id, rule in index.items():
        grouped.setdefault(rule.doc, []).append(rule_id)
    return grouped


def _check_documents(spec: Spec, by_document: dict[str, list[str]]) -> None:
    """Fail when the specification names a document the ruleset does not have rules for."""
    for entry in spec.documents:
        if entry.file not in by_document:
            known = ", ".join(sorted(by_document)) or "none"
            raise ExtractError(
                f"The specification publishes {entry.file!r}, which holds no rules in the "
                f"pinned ruleset. Documents with rules: {known}."
            )


def _document_title(file: str) -> str:
    """Return a document page's title when the specification does not give one.

    The ruleset's own document titles are not in the parser's output, so this falls back to
    the filename. A specification that cares says so with an explicit ``title``.
    """
    stem = file.rsplit("/", 1)[-1]
    if stem.endswith(".md"):
        stem = stem[: -len(".md")]
    words = stem.split("-")
    if words and words[0].isdigit():
        words = words[1:]
    return " ".join(word.capitalize() for word in words)


def _page_path(base_path: str, document: str, rule: str) -> str:
    """Return the site path of a rule page, resolved through the edition's base path."""
    return "/" + "/".join(part for part in (base_path, document, rule) if part)


def _hash(payload: bytes) -> str:
    """Return the content hash recorded for a file."""
    return f"sha256:{hashlib.sha256(payload).hexdigest()}"
