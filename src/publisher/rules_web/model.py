"""The web edition of the ruleset: the pages to publish, and the images they embed.

This is the middle stage of the same three-stage pipeline the quick sheet uses:

    ruleset AST  ->  document.json  ->  bundle  ->  WordPress

A :class:`Document` is every page of one language of the ruleset, in publication order, plus
the media those pages reference. It carries no site URL and no post IDs: it describes what to
publish, never where it ended up. That is what lets the same document publish identically to
a throwaway local site and to a production one.

The split between this stage and the renderer is content against presentation. A rule page
holds the rule's body and nothing else; the index a document page shows is a list of entries
rather than a list rendered into HTML; the footer saying which ruleset version a page came
from does not exist here at all. All of that is assembled by the renderer, so changing how a
page looks never means re-reading the ruleset.

Everything is frozen. Extraction is a pure function, and an immutable result is the cheapest
way to keep it one.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from publisher.quicksheet.model import Source

SCHEMA_VERSION = 1

# A page's HTML refers to an image through this, never through a URL. WordPress stores an
# upload under a directory named for the month it arrived, so a URL baked in at render time
# would make the same ruleset render to different bytes in a different month — and the
# render-twice determinism gate would be pinning a value that legitimately drifts. The push
# stage substitutes the real URL once it knows where the file landed.
MEDIA_PLACEHOLDER = "{{media:%s}}"

ROOT = "root"
DOCUMENT = "document"
RULE = "rule"
KINDS = (ROOT, DOCUMENT, RULE)


class WebDocumentError(Exception):
    """Raised when a web document is missing, malformed, or of an unknown schema."""


@dataclass(frozen=True)
class Media:
    """One image a page embeds, and where to read it from at publication time.

    ``source`` is relative to the ruleset clone, so the push stage can find the file without
    knowing how the clone was laid out. ``content_hash`` is what tells a later run that the
    drawing changed, without storing anything on the site to compare against.
    """

    filename: str
    source: str
    alt: str
    attach_to: str
    content_hash: str


@dataclass(frozen=True)
class Entry:
    """One line of an index page: something to read, and where to find it.

    ``rule`` is the rule ID when the entry is a rule, and ``None`` when it is a whole ruleset
    document — the root page indexes documents, which have no ID of their own.
    """

    title: str
    slug: str
    rule: str | None = None


@dataclass(frozen=True)
class Page:
    """One page to publish.

    ``kind`` is ``"document"`` for the page that indexes a ruleset document's rules, and
    ``"rule"`` for the page carrying one rule's body. ``parent`` is the slug of the page this
    one sits under, and is ``None`` for a document page.

    ``rule``, ``doc`` and ``source_line`` are the trace back to the ruleset, so a published
    page can be checked against the rule it claims to state.
    """

    slug: str
    title: str
    kind: str
    parent: str | None = None
    # What WordPress orders a menu by. Left at zero, it falls back to sorting by title, and
    # the ruleset's reading order — the whole point of its numbering — is lost.
    menu_order: int = 0
    intro: str = ""
    body_html: str = ""
    entries: tuple[Entry, ...] = ()
    rule: str | None = None
    doc: str | None = None
    source_line: int | None = None

    @property
    def path(self) -> str:
        """Return the page's path under the edition's root, without a leading slash."""
        return f"{self.parent}/{self.slug}" if self.parent else self.slug


@dataclass(frozen=True)
class Document:
    """Every page of one language of the ruleset, and the media they reference.

    ``base_path`` is the segment every page sits under, empty for the primary language. It
    exists now, unused, because retrofitting it would move every published URL: a later
    Spanish edition is this same renderer with ``base_path = "es"``, and link rewriting
    already resolves through it so a translated page links inside its own tree.
    """

    title: str = ""
    name: str = "rules_web"
    language: str = "en"
    base_path: str = ""
    pages: tuple[Page, ...] = ()
    media: tuple[Media, ...] = ()
    source: Source = field(default_factory=Source)
    schema: int = SCHEMA_VERSION

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-ready mapping. Key order is fixed so the file diffs cleanly."""
        return {
            "schema": self.schema,
            "name": self.name,
            "language": self.language,
            "base_path": self.base_path,
            "title": self.title,
            "source": {
                "repo": self.source.repo,
                "ruleset_version": self.source.ruleset_version,
                "commit": self.source.commit,
            },
            "pages": [_page_dict(page) for page in self.pages],
            "media": [
                {
                    "filename": item.filename,
                    "source": item.source,
                    "alt": item.alt,
                    "attach_to": item.attach_to,
                    "content_hash": item.content_hash,
                }
                for item in self.media
            ],
        }

    @classmethod
    def from_dict(cls, payload: Any) -> Document:
        """Return the document ``payload`` describes, failing by name on any problem."""
        if not isinstance(payload, dict):
            raise WebDocumentError(f"Expected an object, got {type(payload).__name__}.")

        schema = payload.get("schema")
        if schema != SCHEMA_VERSION:
            raise WebDocumentError(
                f"Unknown document schema {schema!r}; this build understands {SCHEMA_VERSION}."
            )

        raw_pages = payload.get("pages")
        if not isinstance(raw_pages, list) or not raw_pages:
            raise WebDocumentError("The document has no pages.")

        raw_source = payload.get("source") or {}
        if not isinstance(raw_source, dict):
            raise WebDocumentError("source is not an object.")

        return cls(
            title=payload.get("title", ""),
            name=payload.get("name") or "rules_web",
            language=payload.get("language") or "en",
            base_path=payload.get("base_path", ""),
            pages=tuple(_read_page(raw, index) for index, raw in enumerate(raw_pages)),
            media=tuple(
                _read_media(raw, index) for index, raw in enumerate(payload.get("media") or ())
            ),
            source=Source(
                repo=raw_source.get("repo", ""),
                ruleset_version=raw_source.get("ruleset_version", ""),
                commit=raw_source.get("commit", ""),
            ),
            schema=schema,
        )


def _page_dict(page: Page) -> dict[str, Any]:
    """Return one page as a mapping, with a fixed key order.

    A shape a page does not use is left out rather than written empty: a rule page carrying
    ``"entries": []`` invites the reader to wonder whether it was meant to index something.
    """
    out: dict[str, Any] = {
        "slug": page.slug,
        "parent": page.parent,
        "title": page.title,
        "kind": page.kind,
        "menu_order": page.menu_order,
        "rule": page.rule,
        "doc": page.doc,
        "source_line": page.source_line,
    }
    if page.intro:
        out["intro"] = page.intro
    if page.entries:
        out["entries"] = [
            {"rule": entry.rule, "title": entry.title, "slug": entry.slug} for entry in page.entries
        ]
    if page.body_html:
        out["body_html"] = page.body_html
    return out


def _read_page(raw: Any, index: int) -> Page:
    """Return the page ``raw`` describes, failing by name on any problem."""
    if not isinstance(raw, dict):
        raise WebDocumentError(f"pages[{index}] is not an object.")
    for required in ("slug", "title", "kind"):
        if not raw.get(required):
            raise WebDocumentError(f"pages[{index}] is missing {required!r}.")
    kind = raw["kind"]
    if kind not in KINDS:
        raise WebDocumentError(
            f"pages[{index}] has kind {kind!r}; expected one of {', '.join(KINDS)}."
        )

    entries = []
    for position, entry in enumerate(raw.get("entries") or ()):
        if not isinstance(entry, dict):
            raise WebDocumentError(f"pages[{index}] entry {position} is not an object.")
        # `rule` is absent on the root page's entries, which index whole ruleset documents
        # rather than rules. A title and somewhere to go are what every entry needs.
        for required in ("title", "slug"):
            if not entry.get(required):
                raise WebDocumentError(f"pages[{index}] entry {position} is missing {required!r}.")
        entries.append(Entry(title=entry["title"], slug=entry["slug"], rule=entry.get("rule")))

    page = Page(
        slug=raw["slug"],
        title=raw["title"],
        kind=kind,
        parent=raw.get("parent"),
        menu_order=raw.get("menu_order", 0),
        intro=raw.get("intro", ""),
        body_html=raw.get("body_html", ""),
        entries=tuple(entries),
        rule=raw.get("rule"),
        doc=raw.get("doc"),
        source_line=raw.get("source_line"),
    )
    if kind == RULE and not page.body_html:
        raise WebDocumentError(f"pages[{index}] is a rule page with no body; it prints nothing.")
    return page


def _read_media(raw: Any, index: int) -> Media:
    """Return the media item ``raw`` describes, failing by name on any problem."""
    if not isinstance(raw, dict):
        raise WebDocumentError(f"media[{index}] is not an object.")
    for required in ("filename", "source", "attach_to"):
        if not raw.get(required):
            raise WebDocumentError(f"media[{index}] is missing {required!r}.")
    return Media(
        filename=raw["filename"],
        source=raw["source"],
        alt=raw.get("alt", ""),
        attach_to=raw["attach_to"],
        content_hash=raw.get("content_hash", ""),
    )
