"""An in-memory WordPress, standing in for the real one in tests.

It answers the handful of REST calls the publisher makes, keeping pages and attachments in
dictionaries. That is enough to exercise the behaviour worth pinning — create against update,
lookup by slug and parent, an upload that must not happen twice, orphan handling — with no
network and no Docker, which is what lets the publication stage be covered by the required
check.

It imitates the two WordPress behaviours the publisher is written around, because a stub that
did not would let a bug through: a slug is lowercased on the way in, and re-uploading a
filename that already exists stores a renamed duplicate.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any
from urllib.parse import parse_qs, urlparse

from publisher.wp.transport import Response


class FakeWordPress:
    """A WordPress site that lives in a dictionary."""

    def __init__(self, *, authorized: bool = True, capabilities: dict | None = None) -> None:
        self.user = {
            "id": 1,
            "name": "admin",
            "roles": ["administrator"],
            "capabilities": {
                "publish_pages": True,
                "upload_files": True,
                "edit_theme_options": True,
            }
            if capabilities is None
            else capabilities,
        }
        self.pages: dict[int, dict] = {}
        self.media: dict[int, dict] = {}
        self.navigations: dict[int, dict] = {}
        self.requests: list[tuple[str, str]] = []
        self.headers_seen: list[Mapping[str, str]] = []
        self._next_id = 1
        self._authorized = authorized

    # -- the transport seam ---------------------------------------------------------------

    def request(
        self,
        method: str,
        url: str,
        *,
        headers: Mapping[str, str],
        body: bytes | None = None,
    ) -> Response:
        """Answer one request the way WordPress would."""
        self.requests.append((method, url))
        self.headers_seen.append(dict(headers))
        if not self._authorized:
            return _json(401, {"code": "rest_not_logged_in", "message": "You are not logged in."})

        parsed = urlparse(url)
        if parsed.path == "/wp-json":
            return _json(200, {"name": "A site", "namespaces": ["wp/v2"]})
        path = parsed.path.replace("/wp-json/wp/v2", "", 1)
        if path == "/users/me":
            return _json(200, self.user)
        query = {key: values[0] for key, values in parse_qs(parsed.query).items()}

        if path == "/pages":
            return self._pages(method, query, body)
        if path.startswith("/pages/"):
            return self._page(int(path.rsplit("/", 1)[1]), body)
        if path == "/navigation":
            return self._navigations(method, query, body)
        if path.startswith("/navigation/"):
            return self._navigation(int(path.rsplit("/", 1)[1]), body)
        if path == "/media":
            return self._media(method, query, headers, body)
        if path.startswith("/media/"):
            return self._attachment(int(path.rsplit("/", 1)[1]), body)
        return _json(404, {"code": "rest_no_route", "message": f"No route for {path}."})

    # -- pages ----------------------------------------------------------------------------

    def _pages(self, method: str, query: dict, body: bytes | None) -> Response:
        if method == "GET":
            found = list(self.pages.values())
            if "page" in query and int(query["page"]) > 1:
                # One page of results is enough for every fixture here; a second request
                # means the client is paginating, and there is nothing more to give it.
                return _json(200, [])
            if "slug" in query:
                found = [page for page in found if page["slug"] == query["slug"]]
            if "parent" in query:
                found = [page for page in found if page["parent"] == int(query["parent"])]
            return _json(200, found)

        payload = json.loads((body or b"{}").decode("utf-8"))
        page = {
            "id": self._take_id(),
            # WordPress lowercases a slug on the way in. Imitating it here is what makes a
            # test able to catch a publisher that sent an uppercase one.
            "slug": str(payload.get("slug", "")).lower(),
            "parent": payload.get("parent", 0) or 0,
            "status": payload.get("status", "draft"),
            "menu_order": payload.get("menu_order", 0),
            "title": _both(payload.get("title", "")),
            "content": _both(payload.get("content", "")),
        }
        self.pages[page["id"]] = page
        return _json(201, page)

    def _page(self, page_id: int, body: bytes | None) -> Response:
        page = self.pages.get(page_id)
        if page is None:
            return _json(404, {"code": "rest_post_invalid_id", "message": "Invalid page."})
        payload = json.loads((body or b"{}").decode("utf-8"))
        for field in ("status", "parent", "menu_order"):
            if field in payload:
                page[field] = payload[field]
        for field in ("title", "content"):
            if field in payload:
                page[field] = _both(payload[field])
        return _json(200, page)

    # -- navigation ------------------------------------------------------------------------

    def _navigations(self, method: str, query: dict, body: bytes | None) -> Response:
        if method == "GET":
            found = list(self.navigations.values())
            if "slug" in query:
                found = [item for item in found if item["slug"] == query["slug"]]
            return _json(200, found)

        payload = json.loads((body or b"{}").decode("utf-8"))
        item = {
            "id": self._take_id(),
            "slug": payload.get("slug", ""),
            "title": _both(payload.get("title", "")),
            "content": _both(payload.get("content", "")),
        }
        self.navigations[item["id"]] = item
        return _json(201, item)

    def _navigation(self, navigation_id: int, body: bytes | None) -> Response:
        item = self.navigations.get(navigation_id)
        if item is None:
            return _json(404, {"code": "rest_post_invalid_id", "message": "Invalid menu."})
        payload = json.loads((body or b"{}").decode("utf-8"))
        for field in ("title", "content"):
            if field in payload:
                item[field] = _both(payload[field])
        return _json(200, item)

    # -- media ----------------------------------------------------------------------------

    def _media(
        self, method: str, query: dict, headers: Mapping[str, str], body: bytes | None
    ) -> Response:
        if method == "GET":
            search = query.get("search", "")
            return _json(
                200, [item for item in self.media.values() if search in item["source_url"]]
            )

        filename = _filename(headers.get("Content-Disposition", ""))
        stem, _, suffix = filename.rpartition(".")
        # WordPress never overwrites an upload: a name it already holds becomes `name-1.png`,
        # and the URL the caller gets back is not the one anything references. A stub that
        # silently overwrote would hide exactly the bug the publisher looks up to avoid.
        taken = {item["source_url"].rsplit("/", 1)[1] for item in self.media.values()}
        if filename in taken:
            filename = f"{stem}-1.{suffix}"
        item = {
            "id": self._take_id(),
            "slug": stem,
            "source_url": f"https://example.test/uploads/{filename}",
            "alt_text": "",
            "post": 0,
            "bytes": len(body or b""),
        }
        self.media[item["id"]] = item
        return _json(201, item)

    def _attachment(self, media_id: int, body: bytes | None) -> Response:
        item = self.media.get(media_id)
        if item is None:
            return _json(404, {"code": "rest_post_invalid_id", "message": "Invalid media."})
        item.update(json.loads((body or b"{}").decode("utf-8")))
        return _json(200, item)

    # -- helpers --------------------------------------------------------------------------

    def _take_id(self) -> int:
        identifier = self._next_id
        self._next_id += 1
        return identifier

    def page_by_slug(self, slug: str) -> dict:
        """Return the page with ``slug``, for a test to assert on."""
        for page in self.pages.values():
            if page["slug"] == slug:
                return page
        raise AssertionError(f"No page with slug {slug!r}. Have: {sorted(self.slugs())}")

    def slugs(self) -> list[str]:
        """Return every page slug the site holds."""
        return [page["slug"] for page in self.pages.values()]

    def add_page(self, slug: str, parent: int = 0, status: str = "publish") -> dict:
        """Put a page on the site that the publisher did not create."""
        page = {
            "id": self._take_id(),
            "slug": slug,
            "parent": parent,
            "status": status,
            "menu_order": 0,
            "title": _both(slug),
            "content": _both(""),
        }
        self.pages[page["id"]] = page
        return page


class BrokenTransport:
    """A transport that answers everything with the same status, for failure paths."""

    def __init__(self, status: int, payload: Any = None) -> None:
        self._status = status
        self._payload = payload

    def request(self, method: str, url: str, *, headers, body=None) -> Response:
        """Answer with the configured status, whatever was asked."""
        del method, url, headers, body
        if self._payload is None:
            return Response(status=self._status, body=b"not json at all")
        return _json(self._status, self._payload)


def _json(status: int, payload: Any) -> Response:
    """Return a response carrying ``payload`` as JSON."""
    return Response(status=status, body=json.dumps(payload).encode("utf-8"))


def _both(value: str) -> dict:
    """Return the raw/rendered pair WordPress answers with under ``context=edit``."""
    return {"raw": value, "rendered": f"<!-- rendered -->{value}"}


def _filename(disposition: str) -> str:
    """Return the filename out of a Content-Disposition header."""
    marker = 'filename="'
    start = disposition.find(marker)
    if start == -1:
        return "upload.bin"
    return disposition[start + len(marker) : disposition.find('"', start + len(marker))]
