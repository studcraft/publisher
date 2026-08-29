"""Assemble the document into the one bundle the push stage consumes.

    document.json  ->  publish/<name>/v<version>/<name>_<language>.wp.json

The bundle is one file on purpose. A published edition of the ruleset is a hundred and
ninety-odd pages, and as a tree of files it would need a second path-derivation scheme and
would spread "is this stale?" across a directory. As one file it is one reviewable diff, one
`cmp` for the determinism gate, and one thing for the push stage to read.

This stage owns presentation. It renders a document page's index, wraps every page in the
footer that says which ruleset version it came from, and computes the hash a later push
compares against. Nothing here reads the ruleset, so changing how a page looks never means
re-extracting it.
"""

from __future__ import annotations

import hashlib
import html as escaping
import json
from pathlib import Path

from publisher.quicksheet import publish
from publisher.rules_web import markup
from publisher.rules_web.model import DOCUMENT, Document, Page

BUNDLE_SCHEMA = 1
EXTENSION = "wp.json"


def path(document: Document, root: Path = publish.ROOT) -> Path:
    """Return where ``document``'s bundle is published, derived from the document itself."""
    return publish.path(document, EXTENSION, root)


def write(document: Document, destination: Path) -> Path:
    """Write ``document``'s bundle to ``destination`` and return the path."""
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(
        json.dumps(bundle(document), indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    return destination


def render(document: Document, root: Path = publish.ROOT) -> Path:
    """Render ``document`` to its derived publish path under ``root``."""
    return write(document, path(document, root))


def bundle(document: Document) -> dict:
    """Return the bundle ``document`` publishes as, with a fixed key order throughout."""
    pages = [_page(page, document) for page in document.pages]
    return {
        "schema": BUNDLE_SCHEMA,
        "name": document.name,
        "language": document.language,
        "base_path": document.base_path,
        "title": document.title,
        "source": {
            "repo": document.source.repo,
            "ruleset_version": document.source.ruleset_version,
            "commit": document.source.commit,
        },
        "pages": pages,
        "media": [
            {
                "filename": item.filename,
                "source": item.source,
                "alt": item.alt,
                "attach_to": item.attach_to,
                "content_hash": item.content_hash,
            }
            for item in document.media
        ],
    }


def _page(page: Page, document: Document) -> dict:
    """Return one page's payload, with its final HTML and the hash of what it publishes."""
    content = _content(page, document)
    return {
        "slug": page.slug,
        "parent": page.parent,
        "title": page.title,
        "kind": page.kind,
        "rule": page.rule,
        "doc": page.doc,
        "source_line": page.source_line,
        # Covers the title as well as the body: renaming a page is a change to publish, and a
        # hash over the body alone would call it unchanged.
        "content_hash": _hash(page.title, content),
        "html": content,
    }


def _content(page: Page, document: Document) -> str:
    """Return the whole HTML of one page: its own content, then the provenance footer."""
    parts = [_index(page) if page.kind == DOCUMENT else page.body_html, _footer(page, document)]
    return "\n".join(part for part in parts if part)


def _index(page: Page) -> str:
    """Return a document page's body: its introduction, then the rules it holds.

    The index links every rule in the document, in ruleset order, so the document page is
    where a reader who does not already know a rule's number starts. Each entry carries the
    ID as well as the title, because the ID is what people cite to each other.
    """
    parts = []
    if page.intro:
        parts.append(_intro(page))
    rows = "\n".join(
        f'  <li><a href="{escaping.escape(entry.slug)}">'
        f"<strong>{escaping.escape(entry.rule)}</strong> — {escaping.escape(entry.title)}"
        "</a></li>"
        for entry in page.entries
    )
    parts.append(f'<ul class="rule-index">\n{rows}\n</ul>')
    return "\n".join(parts)


def _intro(page: Page) -> str:
    """Return a document page's authored introduction, rendered from Markdown.

    An introduction is written by the publisher rather than taken from the ruleset, so it
    cites no rules and embeds no images. Rendering it with the transformations disabled keeps
    that true: an image here would be an image nothing uploads.
    """
    return markup.render(
        page.intro,
        links={},
        on_image=_no_images,
        where=f"the introduction to {page.slug!r}",
    )


def _no_images(source: str, alt: str) -> str:
    """Refuse an image in authored introduction text."""
    del alt
    raise markup.UnknownReference(
        f"An authored introduction embeds {source!r}. Only the ruleset supplies images, "
        "because only its images are collected for upload."
    )


def _footer(page: Page, document: Document) -> str:
    """Return the provenance footer every published page carries.

    It says three things, and each is there because someone would otherwise have to ask:
    which ruleset version this page states, which commit it was built from, and that editing
    it in WordPress is pointless because the next push overwrites it.
    """
    source = document.source
    origin = f"{escaping.escape(page.doc)}" if page.doc else "the StudCraft ruleset"
    if page.source_line:
        origin = f"{origin}, line {page.source_line}"
    return (
        '<hr class="page-provenance">\n'
        '<p class="page-provenance">Generated from '
        f"{origin} at ruleset version {escaping.escape(source.ruleset_version)}, commit "
        f"<code>{escaping.escape(source.commit[:12])}</code>. "
        "Edits made here are replaced by the next publication; fix the ruleset instead."
        "</p>"
    )


def _hash(title: str, content: str) -> str:
    """Return the hash recorded for what a page publishes."""
    payload = f"{title}\n{content}".encode()
    return f"sha256:{hashlib.sha256(payload).hexdigest()}"
