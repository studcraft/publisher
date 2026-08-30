"""Tests for :mod:`publisher.wp.push` and :mod:`publisher.wp.promote`."""

from __future__ import annotations

from pathlib import Path

import pytest

from publisher.wp import promote as promotion
from publisher.wp import push as staging
from publisher.wp.client import Credentials, WordPress, WordPressError
from publisher.wp.transport import Response
from tests.fake_wordpress import FakeWordPress

LOCAL = Credentials(site="http://localhost:8080", user="admin", password="pw")

PIXEL = b"\x89PNG\r\n\x1a\nbytes"


def _bundle(**overrides) -> dict:
    """Return a bundle in the shape a real one has: a root, a document, two rules."""
    bundle = {
        "schema": 1,
        "name": "rules_web",
        "language": "en",
        "base_path": "",
        "title": "StudCraft Rules",
        "source": {"repo": "r", "ruleset_version": "0.2.0 Draft", "commit": "abc"},
        "pages": [
            {
                "slug": "rules",
                "parent": None,
                "title": "Rules",
                "kind": "root",
                "menu_order": 0,
                "rule": None,
                "doc": None,
                "source_line": None,
                "content_hash": "sha256:r",
                "html": '<ul><li><a href="core-rules">Core Rules</a></li></ul>',
            },
            {
                "slug": "core-rules",
                "parent": "rules",
                "title": "Core Rules",
                "kind": "document",
                "menu_order": 1,
                "rule": None,
                "doc": "02-core-rules.md",
                "source_line": None,
                "content_hash": "sha256:a",
                "html": "<ul><li>core-001</li></ul>",
            },
            {
                "slug": "core-001",
                "parent": "core-rules",
                "title": "CORE-001 — Unit Base (UB)",
                "kind": "rule",
                "rule": "CORE-001",
                "doc": "02-core-rules.md",
                "source_line": 56,
                "content_hash": "sha256:b",
                "html": '<p>A volume.</p><img src="{{media:core-001.png}}">',
            },
            {
                "slug": "core-002",
                "parent": "core-rules",
                "title": "CORE-002 — Facing",
                "kind": "rule",
                "rule": "CORE-002",
                "doc": "02-core-rules.md",
                "source_line": 80,
                "content_hash": "sha256:c",
                "html": "<p>Every unit has a facing.</p>",
            },
        ],
        "media": [
            {
                "filename": "core-001.png",
                "source": "assets/images/core-001.png",
                "alt": "unit base",
                "attach_to": "core-001",
                "content_hash": "sha256:d",
            }
        ],
    }
    bundle.update(overrides)
    return bundle


def _clone(tmp_path: Path) -> Path:
    """Return a clone root holding the bundle's one image."""
    images = tmp_path / "clone" / "assets" / "images"
    images.mkdir(parents=True)
    images.joinpath("core-001.png").write_bytes(PIXEL)
    return tmp_path / "clone"


def _push(tmp_path: Path, fake: FakeWordPress, bundle: dict | None = None, **kwargs):
    """Push ``bundle`` at ``fake`` and return the report."""
    return staging.push(
        _bundle() if bundle is None else bundle,
        WordPress(LOCAL, fake),
        clone_root=_clone(tmp_path) if not (tmp_path / "clone").exists() else tmp_path / "clone",
        **kwargs,
    )


def test_a_first_push_creates_the_whole_hierarchy(tmp_path: Path) -> None:
    """Three levels: the root, a page per document under it, a page per rule under that."""
    fake = FakeWordPress()
    report = _push(tmp_path, fake)

    assert sorted(report.created) == ["core-001", "core-002", "core-rules", "rules"]
    root = fake.page_by_slug("rules")
    document = fake.page_by_slug("core-rules")
    assert root["parent"] == 0
    assert document["parent"] == root["id"]
    assert fake.page_by_slug("core-001")["parent"] == document["id"]


def test_everything_is_staged_private(tmp_path: Path) -> None:
    """Nothing reaches the public in one step."""
    fake = FakeWordPress()
    _push(tmp_path, fake)
    assert {page["status"] for page in fake.pages.values()} == {"private"}


def test_a_second_push_of_the_same_bundle_changes_nothing(tmp_path: Path) -> None:
    """Publishing is idempotent, so a re-run is not a rewrite of the whole site."""
    fake = FakeWordPress()
    _push(tmp_path, fake)
    report = _push(tmp_path, fake)

    assert report.created == []
    assert report.updated == []
    assert sorted(report.unchanged) == ["core-001", "core-002", "core-rules", "rules"]
    assert len(fake.pages) == 4


def test_a_changed_page_is_updated_in_place(tmp_path: Path) -> None:
    """Its URL is public, so an update must not become a create at a new address."""
    fake = FakeWordPress()
    _push(tmp_path, fake)
    identifier = fake.page_by_slug("core-002")["id"]

    changed = _bundle()
    changed["pages"][3]["html"] = "<p>Rewritten.</p>"
    report = _push(tmp_path, fake, changed)

    assert report.updated == ["core-002"]
    assert fake.page_by_slug("core-002")["id"] == identifier
    assert fake.pages[identifier]["content"]["raw"] == "<p>Rewritten.</p>"


def test_a_page_edited_in_wordpress_is_overwritten(tmp_path: Path) -> None:
    """WordPress is not an editing surface; the fix belongs in the ruleset."""
    fake = FakeWordPress()
    _push(tmp_path, fake)
    identifier = fake.page_by_slug("core-001")["id"]
    fake.pages[identifier]["content"] = {"raw": "someone edited this", "rendered": ""}

    report = _push(tmp_path, fake)

    assert report.updated == ["core-001"]
    assert "A volume." in fake.pages[identifier]["content"]["raw"]


def test_an_already_published_page_is_left_published_when_unchanged(tmp_path: Path) -> None:
    """Forcing private on every run would take the live site down between push and promote."""
    fake = FakeWordPress()
    _push(tmp_path, fake)
    promotion.promote(_bundle(), WordPress(LOCAL, fake))

    _push(tmp_path, fake)

    assert {page["status"] for page in fake.pages.values()} == {"publish"}


def test_a_changed_page_goes_back_to_private(tmp_path: Path) -> None:
    """A change nobody reviewed must not be public because its page already was."""
    fake = FakeWordPress()
    _push(tmp_path, fake)
    promotion.promote(_bundle(), WordPress(LOCAL, fake))

    changed = _bundle()
    changed["pages"][3]["html"] = "<p>Rewritten.</p>"
    _push(tmp_path, fake, changed)

    assert fake.page_by_slug("core-002")["status"] == "private"
    assert fake.page_by_slug("core-001")["status"] == "publish"


# -- media --------------------------------------------------------------------------------


def test_an_image_is_uploaded_once_and_its_url_substituted(tmp_path: Path) -> None:
    """The placeholder exists precisely because the URL is not known until now."""
    fake = FakeWordPress()
    report = _push(tmp_path, fake)

    assert report.uploaded == ["core-001.png"]
    content = fake.page_by_slug("core-001")["content"]["raw"]
    assert "{{media:" not in content
    assert "uploads/core-001.png" in content


def test_a_second_push_does_not_upload_the_image_again(tmp_path: Path) -> None:
    """A duplicate would be stored as `-1.png` and its URL would be permanently wrong."""
    fake = FakeWordPress()
    _push(tmp_path, fake)
    report = _push(tmp_path, fake)

    assert report.uploaded == []
    assert report.reused == ["core-001.png"]
    assert len(fake.media) == 1


def test_an_image_is_attached_to_the_page_that_embeds_it(tmp_path: Path) -> None:
    """It makes the media library navigable and an orphaned image visible."""
    fake = FakeWordPress()
    _push(tmp_path, fake)

    item = next(iter(fake.media.values()))
    assert item["post"] == fake.page_by_slug("core-001")["id"]
    assert item["alt_text"] == "unit base"


def test_a_placeholder_with_no_media_entry_fails(tmp_path: Path) -> None:
    """Better a failed publication than a page with a broken image on it."""
    bundle = _bundle()
    bundle["media"] = []
    fake = FakeWordPress()

    with pytest.raises(staging.PushError) as failure:
        _push(tmp_path, fake, bundle)
    assert "core-001.png" in str(failure.value)


def test_an_image_missing_from_the_clone_says_how_to_restore_it(tmp_path: Path) -> None:
    """The fix is one command, so the message names it."""
    (tmp_path / "clone" / "assets" / "images").mkdir(parents=True)
    fake = FakeWordPress()

    with pytest.raises(staging.PushError) as failure:
        _push(tmp_path, fake)
    assert "publisher.sync" in str(failure.value)


# -- orphans ------------------------------------------------------------------------------


def test_a_page_no_longer_in_the_bundle_is_unpublished_not_deleted(tmp_path: Path) -> None:
    """History only grows: an unpublished page can be looked at, a deleted one cannot."""
    fake = FakeWordPress()
    _push(tmp_path, fake)

    smaller = _bundle()
    smaller["pages"] = [page for page in smaller["pages"] if page["slug"] != "core-002"]
    smaller["media"] = []
    smaller["pages"][2]["html"] = "<p>A volume.</p>"
    report = _push(tmp_path, fake, smaller)

    assert report.orphaned == ["core-002"]
    assert fake.page_by_slug("core-002")["status"] == "private"
    assert len(fake.pages) == 4


def test_losing_more_pages_than_the_limit_fails_without_touching_anything(
    tmp_path: Path,
) -> None:
    """That much disappearing is a broken extraction, not a ruleset that shrank."""
    fake = FakeWordPress()
    _push(tmp_path, fake)

    smaller = _bundle()
    smaller["pages"] = smaller["pages"][:1]
    smaller["media"] = []
    with pytest.raises(staging.PushError) as failure:
        _push(tmp_path, fake, smaller, orphan_limit=1)

    assert "Nothing was changed" in str(failure.value)
    assert {page["status"] for page in fake.pages.values()} == {"private"}


def test_pages_outside_the_published_tree_are_left_alone(tmp_path: Path) -> None:
    """Anything else on the site belongs to whoever put it there."""
    fake = FakeWordPress()
    fake.add_page("about", status="publish")
    _push(tmp_path, fake)

    assert fake.page_by_slug("about")["status"] == "publish"


def test_a_bundle_whose_child_has_no_parent_is_refused(tmp_path: Path) -> None:
    """A page parented to nothing would land at the site root, at the wrong URL."""
    bundle = _bundle()
    bundle["pages"] = [bundle["pages"][2]]
    bundle["media"] = []
    bundle["pages"][0]["html"] = "<p>A volume.</p>"

    with pytest.raises(staging.PushError) as failure:
        _push(tmp_path, FakeWordPress(), bundle)
    assert "core-rules" in str(failure.value)


def test_the_summary_reports_what_happened(tmp_path: Path) -> None:
    """The run's own account, which is what a reviewer reads."""
    fake = FakeWordPress()
    summary = _push(tmp_path, fake).summary()
    assert "4 created" in summary
    assert "1 uploaded" in summary


# -- promote ------------------------------------------------------------------------------


def test_promote_publishes_every_page_and_changes_nothing_else(tmp_path: Path) -> None:
    """Whatever the editors reviewed is exactly what becomes public."""
    fake = FakeWordPress()
    _push(tmp_path, fake)
    before = {page["id"]: page["content"]["raw"] for page in fake.pages.values()}

    report = promotion.promote(_bundle(), WordPress(LOCAL, fake))

    assert sorted(report.promoted) == ["core-001", "core-002", "core-rules", "rules"]
    assert {page["status"] for page in fake.pages.values()} == {"publish"}
    assert {page["id"]: page["content"]["raw"] for page in fake.pages.values()} == before


def test_promoting_twice_reports_the_second_run_as_a_no_op(tmp_path: Path) -> None:
    """Running it again after a partial failure has to be safe."""
    fake = FakeWordPress()
    _push(tmp_path, fake)
    promotion.promote(_bundle(), WordPress(LOCAL, fake))

    report = promotion.promote(_bundle(), WordPress(LOCAL, fake))

    assert report.promoted == []
    assert len(report.already) == 4
    assert "4 already public" in report.summary()


def test_promoting_something_that_was_never_pushed_fails() -> None:
    """Publishing a page that does not exist is not a thing that can be done quietly."""
    with pytest.raises(promotion.PromoteError) as failure:
        promotion.promote(_bundle(), WordPress(LOCAL, FakeWordPress()))
    assert "push" in str(failure.value)


def test_promote_leaves_pages_the_bundle_does_not_name(tmp_path: Path) -> None:
    """Promoting somebody else's page would publish something nobody asked for."""
    fake = FakeWordPress()
    fake.add_page("drafts-of-mine", status="draft")
    _push(tmp_path, fake)

    promotion.promote(_bundle(), WordPress(LOCAL, fake))

    assert fake.page_by_slug("drafts-of-mine")["status"] == "draft"


def test_menu_order_reaches_the_site(tmp_path: Path) -> None:
    """WordPress sorts a menu by it and falls back to the title, so it has to be sent."""
    bundle = _bundle()
    bundle["pages"][2]["menu_order"] = 1
    bundle["pages"][3]["menu_order"] = 2
    fake = FakeWordPress()

    _push(tmp_path, fake, bundle)

    assert fake.page_by_slug("core-001")["menu_order"] == 1
    assert fake.page_by_slug("core-002")["menu_order"] == 2


def test_a_reordered_page_is_updated(tmp_path: Path) -> None:
    """Reading order is part of what is published, so changing it is a change to push."""
    fake = FakeWordPress()
    _push(tmp_path, fake)

    reordered = _bundle()
    reordered["pages"][3]["menu_order"] = 7
    report = _push(tmp_path, fake, reordered)

    assert report.updated == ["core-002"]
    assert fake.page_by_slug("core-002")["menu_order"] == 7


def test_a_removed_document_takes_its_rules_with_it(tmp_path: Path) -> None:
    """The rules under it are orphans too, and nothing the bundle names still points at them."""
    fake = FakeWordPress()
    _push(tmp_path, fake)

    root_only = _bundle()
    root_only["pages"] = root_only["pages"][:1]
    root_only["media"] = []
    report = _push(tmp_path, fake, root_only)

    assert sorted(report.orphaned) == ["core-001", "core-002", "core-rules"]
    assert fake.page_by_slug("core-001")["status"] == "private"


# -- ownership ----------------------------------------------------------------------------


def test_a_page_somebody_else_made_elsewhere_is_never_adopted(tmp_path: Path) -> None:
    """Ownership is the whole path, not the last segment of it.

    A page at `/handbook/rules` shares the root's slug and nothing else. Adopting it would
    overwrite somebody's work because two unrelated things were given the same name.
    """
    fake = FakeWordPress()
    section = fake.add_page("handbook")
    stray = fake.add_page("rules", parent=section["id"], status="publish")

    _push(tmp_path, fake)

    assert fake.pages[stray["id"]]["content"]["raw"] == ""
    assert fake.pages[stray["id"]]["status"] == "publish"
    assert fake.pages[stray["id"]]["parent"] == section["id"]


def test_a_top_level_page_sharing_a_document_slug_is_never_adopted(tmp_path: Path) -> None:
    """`/movement` is not `/rules/movement`, however alike they read."""
    fake = FakeWordPress()
    stray = fake.add_page("core-rules", status="publish")

    _push(tmp_path, fake)

    assert fake.pages[stray["id"]]["content"]["raw"] == ""
    assert fake.page_by_slug("rules")["id"] != stray["id"]


def test_a_push_that_failed_partway_converges_when_it_is_run_again(tmp_path: Path) -> None:
    """Recovery is a rerun. Nothing has to be undone first, and nothing is written twice."""

    class FailsAfter:
        """Passes requests through until the nth write, then answers 500 for ever."""

        def __init__(self, writes: int) -> None:
            self._left = writes
            self.site = FakeWordPress()

        def request(self, method, url, *, headers, body=None):
            if method == "POST":
                if self._left <= 0:
                    return Response(status=500, body=b'{"message": "gateway went away"}')
                self._left -= 1
            return self.site.request(method, url, headers=headers, body=body)

    transport = FailsAfter(writes=3)
    with pytest.raises(WordPressError):
        staging.push(_bundle(), WordPress(LOCAL, transport), clone_root=_clone(tmp_path))

    partial = len(transport.site.pages)
    assert 0 < partial < 4

    report = staging.push(
        _bundle(), WordPress(LOCAL, transport.site), clone_root=tmp_path / "clone"
    )

    assert len(transport.site.pages) == 4
    assert sorted(report.created + report.unchanged + report.updated) == [
        "core-001",
        "core-002",
        "core-rules",
        "rules",
    ]
