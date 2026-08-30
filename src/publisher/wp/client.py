"""The WordPress REST API, in the shape the publication stage needs.

Everything here is WordPress core: pages with a parent, application passwords over HTTP
Basic, and the media endpoint. Nothing installed on the site, which is what lets a throwaway
WordPress in Docker stand in for a production one exactly.

Two safety rules live in this module rather than in a README, because a README cannot enforce
them:

- **Credentials never leave over plain HTTP** unless the host is a loopback address. A site
  URL that is one typo away from ``http://`` would otherwise put an application password on
  the wire.
- **The authorization header never reaches an error message or a log line.** A failed request
  is exactly where a credential ends up in a CI log. An error is built from the response —
  the status and what the site said — and never from the request, so there is no path by
  which the header could be printed rather than a rule that it should not be.
"""

from __future__ import annotations

import base64
import ipaddress
import json
import mimetypes
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urlencode, urlparse

from publisher.wp.transport import Response, Transport, UrllibTransport

API = "/wp-json/wp/v2"

PRIVATE = "private"
PUBLISH = "publish"

_LOOPBACK_NAMES = frozenset({"localhost", "localhost.localdomain"})


class WordPressError(Exception):
    """Raised when the site rejects a request or answers with something unusable."""


class InsecureSite(WordPressError):
    """Raised when sending credentials to the configured site would expose them."""


@dataclass(frozen=True)
class Credentials:
    """A site and the application password used to write to it."""

    site: str
    user: str
    password: str

    @property
    def base(self) -> str:
        """Return the site URL without a trailing slash."""
        return self.site.rstrip("/")


class WordPress:
    """A WordPress site, addressed through its REST API."""

    def __init__(self, credentials: Credentials, transport: Transport | None = None) -> None:
        _require_safe(credentials.site)
        self._credentials = credentials
        self._transport = transport if transport is not None else UrllibTransport()

    # -- pages ---------------------------------------------------------------------------

    def find_page(self, slug: str, parent: int | None = None) -> dict | None:
        """Return the page with ``slug`` under ``parent``, or ``None`` when it is absent.

        Looking a page up rather than remembering its ID is what lets the same bundle publish
        to two sites whose IDs have nothing in common.
        """
        # `context=edit` is what makes the response carry `content.raw`, the text as stored.
        # Without it only `content.rendered` comes back, which has been through WordPress's
        # own filters and can never equal what was sent — so every page would look changed on
        # every run, and "unchanged" would be a state the publisher could never report.
        query = {"slug": slug, "status": "any", "per_page": "100", "context": "edit"}
        if parent is not None:
            query["parent"] = str(parent)
        found = self._get(f"{API}/pages", query)
        if not isinstance(found, list):
            raise WordPressError(f"Looking up the page {slug!r} returned {type(found).__name__}.")
        for page in found:
            if page.get("slug") == slug and (parent is None or page.get("parent") == parent):
                return page
        return None

    def children(self, parent: int) -> list[dict]:
        """Return every page directly under ``parent``, whatever its status."""
        query = {"parent": str(parent), "status": "any", "per_page": "100"}
        found = self._get(f"{API}/pages", query)
        if not isinstance(found, list):
            raise WordPressError(f"Listing children of {parent} returned {type(found).__name__}.")
        return found

    def create_page(
        self,
        *,
        slug: str,
        title: str,
        content: str,
        parent: int | None,
        status: str,
        menu_order: int = 0,
    ) -> dict:
        """Create a page and return it."""
        payload = {
            "slug": slug,
            "title": title,
            "content": content,
            "status": status,
            "menu_order": menu_order,
        }
        if parent is not None:
            payload["parent"] = parent
        return self._write(f"{API}/pages", payload, f"creating the page {slug!r}")

    def update_page(self, page_id: int, **fields: Any) -> dict:
        """Update ``page_id`` with ``fields`` and return the page."""
        return self._write(f"{API}/pages/{page_id}", fields, f"updating page {page_id}")

    # -- navigation ----------------------------------------------------------------------

    def find_navigation(self, slug: str) -> dict | None:
        """Return the navigation menu with ``slug``, or ``None`` when it is absent."""
        found = self._get(f"{API}/navigation", {"slug": slug, "status": "any", "context": "edit"})
        if not isinstance(found, list):
            raise WordPressError(f"Looking up the menu {slug!r} returned {type(found).__name__}.")
        for item in found:
            if item.get("slug") == slug:
                return item
        return None

    def create_navigation(self, *, slug: str, title: str, content: str) -> dict:
        """Create a navigation menu and return it."""
        payload = {"slug": slug, "title": title, "content": content, "status": PUBLISH}
        return self._write(f"{API}/navigation", payload, f"creating the menu {slug!r}")

    def update_navigation(self, navigation_id: int, **fields: Any) -> dict:
        """Update ``navigation_id`` with ``fields`` and return the menu."""
        return self._write(
            f"{API}/navigation/{navigation_id}", fields, f"updating menu {navigation_id}"
        )

    # -- media ---------------------------------------------------------------------------

    def find_media(self, filename: str) -> dict | None:
        """Return the attachment whose file is ``filename``, or ``None``.

        Uploading a name WordPress already holds makes it store the file as ``…-1.png`` and
        hand back a URL nothing references — an unnoticed duplicate that is permanently
        wrong. Looking first is what prevents that, so this is not an optimisation.
        """
        stem = filename.rsplit(".", 1)[0]
        found = self._get(f"{API}/media", {"search": stem, "per_page": "100"})
        if not isinstance(found, list):
            raise WordPressError(f"Looking up media {filename!r} returned {type(found).__name__}.")
        for item in found:
            if str(item.get("source_url", "")).rsplit("/", 1)[-1] == filename:
                return item
            if item.get("slug") == stem:
                return item
        return None

    def upload_media(self, path: Path, filename: str) -> dict:
        """Upload ``path`` as ``filename`` and return the attachment."""
        content_type = mimetypes.guess_type(filename)[0]
        if content_type is None:
            raise WordPressError(
                f"{filename!r} has no recognised media type, so WordPress would reject it. "
                "Publish it in a format the site accepts, or convert it."
            )
        headers = {
            "Content-Type": content_type,
            "Content-Disposition": f'attachment; filename="{filename}"',
        }
        response = self._send("POST", f"{API}/media", body=path.read_bytes(), headers=headers)
        return self._decode(response, f"uploading {filename!r}")

    def update_media(self, media_id: int, **fields: Any) -> dict:
        """Update ``media_id`` with ``fields`` and return the attachment."""
        return self._write(f"{API}/media/{media_id}", fields, f"updating media {media_id}")

    # -- plumbing ------------------------------------------------------------------------

    def _get(self, path: str, query: dict[str, str]) -> Any:
        """Return the decoded body of a GET, treating 404 as nothing found."""
        response = self._send("GET", f"{path}?{urlencode(query)}")
        if response.status == 404:
            return []
        return self._decode(response, f"reading {path}")

    def _write(self, path: str, payload: dict, what: str) -> dict:
        """Send a JSON body and return the decoded result."""
        response = self._send(
            "POST",
            path,
            body=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
        )
        result = self._decode(response, what)
        if not isinstance(result, dict):
            raise WordPressError(f"{what.capitalize()} returned {type(result).__name__}.")
        return result

    def _send(
        self,
        method: str,
        path: str,
        *,
        body: bytes | None = None,
        headers: dict[str, str] | None = None,
    ) -> Response:
        """Send one authenticated request."""
        url = f"{self._credentials.base}{path}"
        sent = {"Accept": "application/json", "Authorization": self._authorization()}
        sent.update(headers or {})
        return self._transport.request(method, url, headers=sent, body=body)

    def _authorization(self) -> str:
        """Return the HTTP Basic header value for the application password."""
        raw = f"{self._credentials.user}:{self._credentials.password}".encode()
        return f"Basic {base64.b64encode(raw).decode('ascii')}"

    def _decode(self, response: Response, what: str) -> Any:
        """Return the response body, failing with what the site said when it refused."""
        if response.status >= 400:
            raise WordPressError(f"{what.capitalize()} failed: {_explain(response)}")
        if not response.body:
            return {}
        try:
            return json.loads(response.body.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise WordPressError(f"{what.capitalize()} returned a body that is not JSON: {exc}")


def _explain(response: Response) -> str:
    """Return a one-line explanation of a refusal, carrying the site's own message.

    The response body is the site's account of what it objected to. It never contains the
    request headers, so nothing here can leak the application password — the header is only
    ever held in the client and never put into an error.
    """
    detail = ""
    try:
        payload = json.loads(response.body.decode("utf-8"))
        if isinstance(payload, dict):
            detail = str(payload.get("message") or payload.get("code") or "")
    except (UnicodeDecodeError, json.JSONDecodeError):
        detail = response.body[:200].decode("utf-8", "replace")
    return f"HTTP {response.status}{f' — {detail}' if detail else ''}"


def _require_safe(site: str) -> None:
    """Fail when sending an application password to ``site`` would expose it."""
    parsed = urlparse(site)
    if parsed.scheme == "https":
        return
    if parsed.scheme != "http":
        raise InsecureSite(
            f"The site URL {site!r} has no usable scheme. Give a full URL, "
            "such as https://example.org."
        )
    if _is_loopback(parsed.hostname or ""):
        return
    raise InsecureSite(
        f"Refusing to send an application password to {site!r} over plain HTTP. "
        "Credentials sent this way are readable in transit; use https, or a site on "
        "localhost for testing."
    )


def _is_loopback(host: str) -> bool:
    """Return whether ``host`` is this machine."""
    if host.lower() in _LOOPBACK_NAMES:
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False
