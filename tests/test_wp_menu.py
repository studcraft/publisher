"""Tests for :mod:`publisher.wp.menu`."""

from __future__ import annotations

import pytest

from publisher.wp import menu
from publisher.wp.client import Credentials, WordPress
from tests.fake_wordpress import FakeWordPress

LOCAL = Credentials(site="http://localhost:8080", user="admin", password="pw")


def _bundle(**overrides) -> dict:
    """Return a bundle with a root, two documents and a rule under one of them."""
    bundle = {
        "base_path": "",
        "pages": [
            {"slug": "rules", "parent": None, "kind": "root", "title": "Rules"},
            {"slug": "core-rules", "parent": "rules", "kind": "document", "title": "Core Rules"},
            {"slug": "game-flow", "parent": "rules", "kind": "document", "title": "Game Flow"},
            {"slug": "core-001", "parent": "core-rules", "kind": "rule", "title": "CORE-001"},
        ],
    }
    bundle.update(overrides)
    return bundle


def _write(fake: FakeWordPress, bundle: dict | None = None):
    """Write the menu for ``bundle`` at ``fake``."""
    return menu.write(_bundle() if bundle is None else bundle, WordPress(LOCAL, fake))


def test_the_menu_is_one_entry_with_the_documents_under_it() -> None:
    """A menu of a hundred and eighty rules is not a menu; the rules are reached from a page."""
    fake = FakeWordPress()
    report = _write(fake)

    content = next(iter(fake.navigations.values()))["content"]["raw"]
    assert report.entries == 2
    assert content.count("wp:navigation-submenu") == 2  # the opening and closing comment
    assert '"label": "Core Rules", "url": "/rules/core-rules/"' in content
    assert "core-001" not in content


def test_documents_keep_the_order_the_bundle_gives_them() -> None:
    """That order is the ruleset's reading order, which is the whole complaint being fixed."""
    fake = FakeWordPress()
    _write(fake)

    content = next(iter(fake.navigations.values()))["content"]["raw"]
    assert content.index("Core Rules") < content.index("Game Flow")


def test_entries_are_addressed_by_url_rather_than_by_page_id() -> None:
    """The same bundle publishes to two sites whose IDs mean different things."""
    fake = FakeWordPress()
    _write(fake)

    content = next(iter(fake.navigations.values()))["content"]["raw"]
    assert '"kind": "custom"' in content
    assert '"id"' not in content


def test_a_second_write_updates_the_same_menu() -> None:
    """Two menus would leave the site picking one, and the wrong one half the time."""
    fake = FakeWordPress()
    first = _write(fake)
    second = _write(fake)

    assert (first.action, second.action) == ("created", "updated")
    assert len(fake.navigations) == 1
    assert "1 menu" not in second.summary()
    assert "2 entries" in second.summary()


def test_a_language_tree_links_inside_itself() -> None:
    """A translated edition must not send its readers back into the English one."""
    fake = FakeWordPress()
    _write(fake, _bundle(base_path="es"))

    content = next(iter(fake.navigations.values()))["content"]["raw"]
    assert '"url": "/es/rules/core-rules/"' in content


def test_a_bundle_with_no_root_is_refused() -> None:
    """There would be nothing to hang the documents from."""
    with pytest.raises(menu.MenuError) as failure:
        _write(FakeWordPress(), _bundle(pages=[]))
    assert "root pages" in str(failure.value)


def test_a_bundle_with_no_documents_is_refused() -> None:
    """An empty menu is worse than the page list it replaces."""
    bundle = _bundle(pages=[{"slug": "rules", "parent": None, "kind": "root", "title": "Rules"}])
    with pytest.raises(menu.MenuError) as failure:
        _write(FakeWordPress(), bundle)
    assert "no documents" in str(failure.value)
