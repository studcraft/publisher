"""Tests for :mod:`publisher.wp.check`.

Everything here is read-only by construction. The point of the check is that it answers the
questions publishing depends on *before* publishing writes anything, so a test that let it
write would be testing the wrong thing.
"""

from __future__ import annotations

from publisher.wp.check import check
from publisher.wp.client import Credentials, WordPress
from tests.fake_wordpress import BrokenTransport, FakeWordPress

LOCAL = Credentials(site="http://localhost:8080", user="admin", password="pw")


def _bundle() -> dict:
    """Return a bundle of a root, a document and a rule."""
    return {
        "pages": [
            {"slug": "rules", "parent": None, "kind": "root", "title": "Rules"},
            {"slug": "movement", "parent": "rules", "kind": "document", "title": "Movement"},
            {"slug": "move-001", "parent": "movement", "kind": "rule", "title": "MOVE-001"},
        ]
    }


def _check(fake, credentials: Credentials = LOCAL):
    """Run the check against ``fake``."""
    return check(_bundle(), WordPress(credentials, fake))


def test_a_healthy_site_passes_and_writes_nothing() -> None:
    """The whole check is reads; a site it ran against is a site it did not change."""
    fake = FakeWordPress()
    report = _check(fake)

    assert report.ok
    assert fake.pages == {}
    assert all(method == "GET" for method, _ in fake.requests)


def test_an_unreachable_rest_api_stops_the_check() -> None:
    """Nothing later can be established, and a wall of failures would hide the first one."""
    report = _check(BrokenTransport(403, {"message": "Forbidden by firewall"}))

    assert not report.ok
    assert len(report.findings) == 1
    assert "firewall" in report.summary()


def test_a_403_explains_what_causes_one() -> None:
    """On someone else's WordPress the cause is infrastructure, and the status alone hides it."""
    report = _check(BrokenTransport(403, {"message": "Nope"}))
    assert "rate limit" in report.summary()


def test_a_401_names_the_dropped_authorization_header() -> None:
    """The cause nobody guesses: PHP under CGI never sees the header the client sent."""
    report = _check(FakeWordPress(authorized=False))

    assert not report.ok
    assert "Authorization header" in report.summary()


def test_who_the_password_authenticates_as_is_reported() -> None:
    """Publishing to the wrong account is a thing that happens, and it is silent."""
    report = _check(FakeWordPress())
    assert "admin (administrator)" in report.summary()


def test_a_user_who_cannot_publish_fails_the_check() -> None:
    """Finding this out at write ninety leaves the site half published."""
    fake = FakeWordPress(capabilities={"publish_pages": False, "upload_files": True})
    report = _check(fake)

    assert not report.ok
    assert "FAIL  the user may publish pages" in report.summary()


def test_a_user_who_cannot_write_a_menu_is_told_but_not_blocked() -> None:
    """`push` and `promote` work for an editor; only the navigation needs an administrator."""
    fake = FakeWordPress(capabilities={"publish_pages": True, "upload_files": True})
    report = _check(fake)

    assert report.ok
    assert "needs an administrator" in report.summary()


def test_pages_this_bundle_already_owns_are_reported_as_adoptions() -> None:
    """On a second publication every page collides with itself, which is not a warning."""
    fake = FakeWordPress()
    root = fake.add_page("rules")
    fake.add_page("movement", parent=root["id"])

    report = _check(fake)

    assert sorted(report.adopted) == ["movement", "rules"]
    assert report.foreign == []


def test_a_page_elsewhere_sharing_a_slug_is_reported_as_safe() -> None:
    """Identity is slug and parent together, so this page is not this publication's."""
    fake = FakeWordPress()
    fake.add_page("movement")

    report = _check(fake)

    assert report.ok
    assert report.adopted == []
    assert any("movement" in item for item in report.foreign)
    assert "left alone" in report.summary()


def test_a_page_inside_the_published_tree_that_the_bundle_dropped_is_an_orphan() -> None:
    """The reader should know a push would unpublish it, before the push does."""
    fake = FakeWordPress()
    root = fake.add_page("rules")
    document = fake.add_page("movement", parent=root["id"])
    fake.add_page("move-404", parent=document["id"])

    report = _check(fake)

    assert report.orphaned == ["move-404"]
    assert "never deletes a page" in report.summary()


def test_nothing_outside_the_published_tree_is_ever_called_an_orphan() -> None:
    """The publisher owns one subtree; the rest of the site is not its business."""
    fake = FakeWordPress()
    fake.add_page("rules")
    elsewhere = fake.add_page("handbook")
    fake.add_page("appendix", parent=elsewhere["id"])

    report = _check(fake)

    assert report.orphaned == []


def test_pages_unrelated_to_the_bundle_are_not_mentioned() -> None:
    """The rest of the site is not this publication's business."""
    fake = FakeWordPress()
    fake.add_page("about-us")

    report = _check(fake)

    assert report.foreign == []
    assert "about-us" not in report.summary()


def test_a_site_that_will_not_list_its_pages_fails() -> None:
    """Without the listing there is no way to know what a push would overwrite."""

    class OnlyListingFails(FakeWordPress):
        def request(self, method, url, *, headers, body=None):
            if "per_page=100" in url:
                return BrokenTransport(403, {"message": "no"}).request(
                    method, url, headers=headers, body=body
                )
            return super().request(method, url, headers=headers, body=body)

    report = check(_bundle(), WordPress(LOCAL, OnlyListingFails()))

    assert not report.ok
    assert "FAIL  the site's pages can be listed" in report.summary()
