"""Write the site's navigation menu: one entry, with the ruleset's documents under it.

Without this, a block theme's header renders a **Page List**, which walks the whole page
hierarchy — every one of the ruleset's rules becomes a menu item, sorted alphabetically
because nothing set an order. Measured on a stock Twenty Twenty-Five: 194 entries, starting
at Combat.

What replaces it is a `wp_navigation` post, which is core — a block theme's navigation block
falls back to the most recent one when its own has no reference, so publishing this menu is
enough and the theme's templates are never touched. That matters: templates are the site
owner's, and a publisher that rewrote them would be deciding how the site looks.

The menu deliberately stops one level down. The rules themselves are reached from the
document page that indexes them, because a menu with a hundred and eighty entries is not a
menu.
"""

from __future__ import annotations

import json
from dataclasses import dataclass

from publisher.wp.client import WordPress

# The navigation this publisher owns, found by slug so it is updated rather than duplicated.
SLUG = "studcraft-rules"


class MenuError(Exception):
    """Raised when the menu cannot be written as the bundle describes it."""


@dataclass
class Report:
    """What one menu write did."""

    action: str = ""
    entries: int = 0

    def summary(self) -> str:
        """Return the one-line account printed at the end of a run."""
        return f"menu {self.action} with {self.entries} entries under it"


def write(bundle: dict, site: WordPress, title: str = "Rules") -> Report:
    """Create or update the navigation menu for ``bundle`` and return what happened."""
    root, documents = _structure(bundle)
    content = _blocks(bundle.get("base_path", ""), root, documents)

    existing = site.find_navigation(SLUG)
    if existing is None:
        site.create_navigation(slug=SLUG, title=title, content=content)
        action = "created"
    else:
        site.update_navigation(existing["id"], title=title, content=content)
        action = "updated"

    return Report(action=action, entries=len(documents))


def _structure(bundle: dict) -> tuple[dict, list[dict]]:
    """Return the bundle's root page and the document pages directly under it."""
    pages = bundle.get("pages") or []
    roots = [page for page in pages if page.get("kind") == "root"]
    if len(roots) != 1:
        raise MenuError(
            f"The bundle has {len(roots)} root pages; a menu needs exactly one thing to "
            "hang the documents from."
        )
    root = roots[0]
    documents = [page for page in pages if page.get("parent") == root["slug"]]
    if not documents:
        raise MenuError("The bundle publishes no documents, so the menu would be empty.")
    return root, documents


def _blocks(base_path: str, root: dict, documents: list[dict]) -> str:
    """Return the block markup for the menu.

    Entries are addressed by URL rather than by page ID. IDs differ between a local site and
    a production one, and this is the same bundle published to both — a menu carrying IDs
    would point at whatever those numbers happen to mean on the other site.
    """
    root_url = _url(base_path, root["slug"])
    children = "\n".join(
        _link(_url(base_path, root["slug"], page["slug"]), page["title"]) for page in documents
    )
    return _submenu(root_url, root["title"], children)


def _url(*parts: str) -> str:
    """Return a site-relative URL from the path segments that are not empty."""
    return "/" + "/".join(part.strip("/") for part in parts if part.strip("/")) + "/"


def _submenu(url: str, label: str, children: str) -> str:
    """Return one navigation entry that opens to reveal ``children``."""
    return (
        f"<!-- wp:navigation-submenu {_attributes(url, label)} -->\n"
        f"{children}\n"
        "<!-- /wp:navigation-submenu -->"
    )


def _link(url: str, label: str) -> str:
    """Return one navigation entry that goes straight to a page."""
    return f"<!-- wp:navigation-link {_attributes(url, label)} /-->"


def _attributes(url: str, label: str) -> str:
    """Return one entry's attributes, as the block editor writes them."""
    return json.dumps({"label": label, "url": url, "kind": "custom"}, ensure_ascii=False)
