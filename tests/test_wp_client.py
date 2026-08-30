"""Tests for :mod:`publisher.wp.client`.

The two security rules are the reason this module exists rather than a few calls to
``urllib``, so they are pinned first: credentials must not go out over plain HTTP, and the
authorization header must not come back in an error.
"""

from __future__ import annotations

import base64
from pathlib import Path

import pytest

from publisher.wp.client import Credentials, InsecureSite, WordPress, WordPressError
from tests.fake_wordpress import BrokenTransport, FakeWordPress

LOCAL = Credentials(site="http://localhost:8080", user="admin", password="app pass word")


def _site(fake: FakeWordPress | None = None, credentials: Credentials = LOCAL) -> WordPress:
    """Return a client wired to ``fake``."""
    return WordPress(credentials, fake if fake is not None else FakeWordPress())


# -- the security rules -------------------------------------------------------------------


def test_plain_http_to_a_real_host_is_refused() -> None:
    """A site URL one typo from https would put an application password on the wire."""
    with pytest.raises(InsecureSite) as failure:
        WordPress(Credentials(site="http://studcraft.example", user="a", password="b"))
    assert "plain HTTP" in str(failure.value)


@pytest.mark.parametrize(
    "site",
    ["http://localhost:8080", "http://127.0.0.1:8080", "http://[::1]:8080", "http://LOCALHOST"],
)
def test_plain_http_to_this_machine_is_allowed(site: str) -> None:
    """The local harness is the whole point, and nothing leaves the machine."""
    assert _site(credentials=Credentials(site=site, user="a", password="b")) is not None


def test_https_is_always_allowed() -> None:
    """The ordinary case."""
    assert _site(credentials=Credentials(site="https://studcraft.example", user="a", password="b"))


def test_a_url_with_no_scheme_is_refused() -> None:
    """ "studcraft.example" is not a site; guessing a scheme for it could pick the wrong one."""
    with pytest.raises(InsecureSite) as failure:
        WordPress(Credentials(site="studcraft.example", user="a", password="b"))
    assert "full URL" in str(failure.value)


def test_the_authorization_header_never_reaches_an_error() -> None:
    """A failed request is exactly where a credential ends up in a CI log."""
    site = _site(BrokenTransport(500, {"message": "Something broke"}))
    with pytest.raises(WordPressError) as failure:
        site.find_page("core-001")

    message = str(failure.value)
    assert "Something broke" in message
    assert "Basic" not in message
    assert base64.b64encode(b"admin:app pass word").decode() not in message


def test_the_password_is_sent_as_http_basic() -> None:
    """Application passwords authenticate this way; nothing else is enabled by default."""
    fake = FakeWordPress()
    _site(fake).find_page("core-001")
    expected = base64.b64encode(b"admin:app pass word").decode()
    assert fake.headers_seen[0]["Authorization"] == f"Basic {expected}"


# -- pages --------------------------------------------------------------------------------


def test_a_page_is_found_by_slug_and_parent() -> None:
    """Two rules in different documents can share neither slug nor parent by accident."""
    fake = FakeWordPress()
    parent = fake.add_page("core-rules")
    fake.add_page("core-001", parent=parent["id"])
    fake.add_page("core-001", parent=999)

    found = _site(fake).find_page("core-001", parent["id"])
    assert found is not None
    assert found["parent"] == parent["id"]


def test_an_absent_page_is_reported_as_absent_rather_than_as_a_failure() -> None:
    """Not existing yet is an ordinary part of publishing."""
    assert _site().find_page("core-001") is None


def test_creating_a_page_sends_its_parent_and_status() -> None:
    """The hierarchy and the staging status are both properties of the page as created."""
    fake = FakeWordPress()
    site = _site(fake)
    parent = site.create_page(
        slug="core-rules", title="Core Rules", content="<p>x</p>", parent=None, status="private"
    )
    child = site.create_page(
        slug="core-001", title="CORE-001", content="<p>y</p>", parent=parent["id"], status="private"
    )

    assert child["parent"] == parent["id"]
    assert child["status"] == "private"


def test_children_are_listed_whatever_their_status() -> None:
    """An orphan may be private already; a status filter would hide it."""
    fake = FakeWordPress()
    parent = fake.add_page("core-rules")
    fake.add_page("core-001", parent=parent["id"], status="private")

    assert [page["slug"] for page in _site(fake).children(parent["id"])] == ["core-001"]


def test_a_rejected_write_carries_what_the_site_said() -> None:
    """A bare status code leaves the reader guessing at a message WordPress already wrote."""
    site = _site(BrokenTransport(400, {"message": "Invalid slug."}))
    with pytest.raises(WordPressError) as failure:
        site.update_page(7, status="publish")
    assert "Invalid slug." in str(failure.value)
    assert "400" in str(failure.value)


def test_a_body_that_is_not_json_is_reported_as_such() -> None:
    """A proxy's HTML error page is a different problem from a rejected request."""
    site = _site(BrokenTransport(200))
    with pytest.raises(WordPressError) as failure:
        site.find_page("core-001")
    assert "not JSON" in str(failure.value)


def test_a_lookup_that_returns_the_wrong_shape_fails() -> None:
    """A list was asked for; anything else means the endpoint is not what it claimed."""
    site = _site(BrokenTransport(200, {"unexpected": True}))
    with pytest.raises(WordPressError):
        site.find_page("core-001")


def test_an_unauthenticated_site_fails_rather_than_publishing_nothing_quietly() -> None:
    """The commonest local misconfiguration, and it must not look like an empty site."""
    site = _site(FakeWordPress(authorized=False))
    with pytest.raises(WordPressError) as failure:
        site.create_page(slug="x", title="X", content="", parent=None, status="private")
    assert "401" in str(failure.value)


# -- media --------------------------------------------------------------------------------


def test_an_image_is_uploaded_with_its_filename(tmp_path: Path) -> None:
    """WordPress names the stored file from the disposition header, so it has to be right."""
    path = tmp_path / "core-001.png"
    path.write_bytes(b"\x89PNG\r\n\x1a\nbytes")
    fake = FakeWordPress()

    item = _site(fake).upload_media(path, "core-001.png")

    assert item["source_url"].endswith("/core-001.png")
    assert fake.media[item["id"]]["bytes"] == path.stat().st_size


def test_an_existing_upload_is_found_rather_than_replaced(tmp_path: Path) -> None:
    """Uploading twice would store `-1.png` and leave a URL nothing references."""
    path = tmp_path / "core-001.png"
    path.write_bytes(b"\x89PNG\r\n\x1a\nbytes")
    fake = FakeWordPress()
    site = _site(fake)
    first = site.upload_media(path, "core-001.png")

    found = site.find_media("core-001.png")

    assert found is not None
    assert found["id"] == first["id"]
    assert len(fake.media) == 1


def test_media_that_is_not_there_is_reported_as_absent() -> None:
    """So the caller uploads it."""
    assert _site().find_media("never-drawn.png") is None


def test_a_format_wordpress_would_not_recognise_is_refused(tmp_path: Path) -> None:
    """Better a message that names the file than a REST error nobody can read."""
    path = tmp_path / "drawing.sketchfile"
    path.write_bytes(b"x")
    with pytest.raises(WordPressError) as failure:
        _site().upload_media(path, "drawing.sketchfile")
    assert "media type" in str(failure.value)


def test_an_attachment_is_given_its_alt_text_and_its_page() -> None:
    """Alt text is already written in the ruleset; publishing without it throws it away."""
    fake = FakeWordPress()
    site = _site(fake)
    item = fake.media.setdefault(
        1, {"id": 1, "slug": "core-001", "source_url": "u", "alt_text": "", "post": 0}
    )

    site.update_media(item["id"], alt_text="unit base", post=42)

    assert fake.media[1]["alt_text"] == "unit base"
    assert fake.media[1]["post"] == 42


def test_a_lookup_is_the_slug_and_the_parent_never_the_slug_alone() -> None:
    """A slug is unique among siblings, not across a site.

    A lookup that ignored the parent would match a page somebody else made in an unrelated
    corner of the site, and the caller would then overwrite it.
    """
    fake = FakeWordPress()
    section = fake.add_page("handbook")
    fake.add_page("rules", parent=section["id"])

    assert _site(fake).find_page("rules") is None


def test_a_top_level_lookup_means_the_top_level() -> None:
    """`parent=None` is a place, not a wildcard."""
    fake = FakeWordPress()
    fake.add_page("rules")

    found = _site(fake).find_page("rules")

    assert found is not None
    assert found["parent"] == 0
