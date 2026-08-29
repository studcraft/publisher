"""Stage a rendered bundle on a WordPress site, as pages only editors can see.

``push`` reads the bundle and nothing else — not the ruleset, not the specification. The
bytes reviewed in a pull request are the bytes the site receives.

Everything it writes is ``private``: published at its real URL, in its real place in the
hierarchy, visible only to someone logged in. That is the review surface. Making it public is
:mod:`publisher.wp.promote`, a separate command, because a publication that can happen by
accident will.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

from publisher.wp.client import PRIVATE, WordPress, WordPressError

# Beyond this many pages disappearing at once, `push` refuses rather than unpublishing them.
# Losing that much of the site is what a broken extraction looks like, not what deleting a
# few rules looks like.
DEFAULT_ORPHAN_LIMIT = 10

_PLACEHOLDER = re.compile(r"\{\{media:([^}]+)\}\}")


class PushError(Exception):
    """Raised when a bundle cannot be staged as it stands."""


@dataclass
class Report:
    """What one push did, in the terms someone reviewing it would ask about."""

    created: list[str] = field(default_factory=list)
    updated: list[str] = field(default_factory=list)
    unchanged: list[str] = field(default_factory=list)
    orphaned: list[str] = field(default_factory=list)
    uploaded: list[str] = field(default_factory=list)
    reused: list[str] = field(default_factory=list)

    def summary(self) -> str:
        """Return the one-paragraph account printed at the end of a run."""
        lines = [
            f"pages: {len(self.created)} created, {len(self.updated)} updated, "
            f"{len(self.unchanged)} unchanged",
            f"media: {len(self.uploaded)} uploaded, {len(self.reused)} already present",
        ]
        if self.orphaned:
            lines.append(
                "unpublished, no longer in the ruleset: " + ", ".join(sorted(self.orphaned))
            )
        return "\n".join(lines)


def push(
    bundle: dict,
    site: WordPress,
    *,
    clone_root: Path,
    orphan_limit: int = DEFAULT_ORPHAN_LIMIT,
) -> Report:
    """Stage every page in ``bundle`` on ``site`` as ``private``, and return what happened."""
    report = Report()
    urls, attachments = _media(bundle, site, clone_root, report)

    parents: dict[str, int] = {}
    written: dict[str, int] = {}
    for page in _ordered(bundle):
        parent_slug = page.get("parent")
        if parent_slug is not None and parent_slug not in parents:
            raise PushError(
                f"The page {page['slug']!r} sits under {parent_slug!r}, which the bundle does "
                "not contain. The bundle is inconsistent; re-render it."
            )
        parent_id = parents.get(parent_slug) if parent_slug else None
        page_id = _page(page, site, parent_id, urls, report)
        written[page["slug"]] = page_id
        if page.get("kind") == "document":
            parents[page["slug"]] = page_id

    _attach(bundle, site, attachments, written)
    _orphans(bundle, site, parents, orphan_limit, report)
    return report


def _ordered(bundle: dict) -> list[dict]:
    """Return the bundle's pages with every document page before any rule page.

    A child page needs its parent's ID, and the ID only exists once the parent is written.
    Ordering here rather than trusting the bundle's order means a re-ordered bundle cannot
    produce a page parented to nothing.
    """
    pages = bundle.get("pages") or []
    documents = [page for page in pages if page.get("kind") == "document"]
    rules = [page for page in pages if page.get("kind") != "document"]
    return documents + rules


def _media(
    bundle: dict, site: WordPress, clone_root: Path, report: Report
) -> tuple[dict[str, str], dict[str, int]]:
    """Upload every image the bundle references that the site does not already hold."""
    urls: dict[str, str] = {}
    attachments: dict[str, int] = {}
    for item in bundle.get("media") or []:
        filename = item["filename"]
        existing = site.find_media(filename)
        if existing is None:
            path = clone_root / item["source"]
            if not path.is_file():
                raise PushError(
                    f"The bundle references {item['source']!r}, which is not in the ruleset "
                    f"clone at {path}. Restore the clone with `python -m publisher.sync "
                    "--pinned`."
                )
            existing = site.upload_media(path, filename)
            report.uploaded.append(filename)
        else:
            report.reused.append(filename)
        urls[filename] = existing["source_url"]
        attachments[filename] = existing["id"]
    return urls, attachments


def _attach(bundle: dict, site: WordPress, attachments: dict[str, int], written: dict[str, int]):
    """Point each attachment at the page that embeds it, and give it its alt text.

    Done after the pages exist, because attaching needs the page's ID and the page's content
    needs the upload's URL. Neither can come first, so they are three passes rather than two.
    """
    for item in bundle.get("media") or []:
        media_id = attachments.get(item["filename"])
        page_id = written.get(item["attach_to"])
        if media_id is None or page_id is None:
            continue
        site.update_media(media_id, alt_text=item.get("alt", ""), post=page_id)


def _page(
    page: dict, site: WordPress, parent_id: int | None, urls: dict[str, str], report: Report
) -> int:
    """Create or update one page as ``private``, and return its ID."""
    content = resolve(page["html"], urls, page["slug"])
    existing = site.find_page(page["slug"], parent_id)

    if existing is None:
        created = site.create_page(
            slug=page["slug"],
            title=page["title"],
            content=content,
            parent=parent_id,
            status=PRIVATE,
        )
        report.created.append(page["slug"])
        return created["id"]

    if _matches(existing, page["title"], content):
        report.unchanged.append(page["slug"])
        return existing["id"]

    site.update_page(existing["id"], title=page["title"], content=content, status=PRIVATE)
    report.updated.append(page["slug"])
    return existing["id"]


def _matches(existing: dict, title: str, content: str) -> bool:
    """Return whether the site already holds exactly this page.

    The comparison is against ``raw``, the content as stored, not against ``rendered``: the
    rendered form has been through WordPress's own filters and would never equal what was
    sent, which would make every page look changed on every run.
    """
    stored = existing.get("content")
    stored_title = existing.get("title")
    if not isinstance(stored, dict) or not isinstance(stored_title, dict):
        return False
    if "raw" not in stored or "raw" not in stored_title:
        return False
    return stored["raw"] == content and stored_title["raw"] == title


def resolve(html: str, urls: dict[str, str], where: str) -> str:
    """Return ``html`` with every media placeholder replaced by its uploaded URL."""

    def substitute(match: re.Match) -> str:
        filename = match.group(1)
        try:
            return urls[filename]
        except KeyError:
            raise PushError(
                f"The page {where!r} refers to the image {filename!r}, which the bundle's "
                "media list does not contain, so there is no URL to put in its place. "
                "Re-render the bundle."
            ) from None

    return _PLACEHOLDER.sub(substitute, html)


def _orphans(
    bundle: dict,
    site: WordPress,
    parents: dict[str, int],
    orphan_limit: int,
    report: Report,
) -> None:
    """Unpublish pages under a managed document that the bundle no longer contains.

    Only pages beneath a document this bundle publishes are considered. Anything else on the
    site belongs to whoever put it there.
    """
    published = {page["slug"] for page in bundle.get("pages") or []}
    found: list[tuple[int, str]] = []
    for slug, parent_id in parents.items():
        del slug
        for child in site.children(parent_id):
            if child.get("slug") not in published:
                found.append((child["id"], child.get("slug", str(child["id"]))))

    if len(found) > orphan_limit:
        raise PushError(
            f"{len(found)} published pages are not in this bundle, which is more than the "
            f"limit of {orphan_limit}. That many disappearing at once is what a broken "
            "extraction looks like, not what removing a rule looks like. Nothing was changed."
        )

    for page_id, slug in found:
        try:
            site.update_page(page_id, status=PRIVATE)
        except WordPressError as exc:
            raise PushError(f"Could not unpublish the orphaned page {slug!r}: {exc}") from exc
        report.orphaned.append(slug)
