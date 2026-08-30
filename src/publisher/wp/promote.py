"""Make a staged publication public.

``promote`` sends one thing per page: a status. It does not touch a title, a body, an image
or a parent, so promoting cannot introduce a change nobody reviewed — whatever the editors
looked at while it was ``private`` is exactly what becomes public.

It is not atomic. WordPress has no transaction, so there is a window in which some pages are
public and others are not. A status-only pass is the shortest that window can be made, and
saying so here is better than implying a guarantee that does not exist.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from publisher.wp.client import PUBLISH, WordPress
from publisher.wp.push import ordered


class PromoteError(Exception):
    """Raised when a bundle cannot be promoted as it stands."""


@dataclass
class Report:
    """What one promotion did."""

    promoted: list[str] = field(default_factory=list)
    already: list[str] = field(default_factory=list)

    def summary(self) -> str:
        """Return the one-line account printed at the end of a run."""
        return f"{len(self.promoted)} pages promoted, {len(self.already)} already public"


def promote(bundle: dict, site: WordPress) -> Report:
    """Publish every page ``bundle`` contains, and return what happened.

    Only pages the bundle names are touched. A page on the site that this edition does not
    publish is somebody else's, and promoting it would be publishing something nobody asked
    for.
    """
    report = Report()
    found: dict[str, int] = {}

    for page in ordered(bundle):
        parent_slug = page.get("parent")
        parent_id = found.get(parent_slug) if parent_slug else None
        existing = site.find_page(page["slug"], parent_id)
        if existing is None:
            raise PromoteError(
                f"The page {page['slug']!r} is not on the site, so there is nothing to "
                "promote. Run `python -m publisher.wp push` first."
            )
        found[page["slug"]] = existing["id"]

        if existing.get("status") == PUBLISH:
            report.already.append(page["slug"])
            continue

        site.update_page(existing["id"], status=PUBLISH)
        report.promoted.append(page["slug"])

    return report
