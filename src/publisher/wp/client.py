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
import time
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urlencode, urlparse

from publisher.wp.transport import Response, Transport, UrllibTransport

API = "/wp-json/wp/v2"

PRIVATE = "private"
PUBLISH = "publish"

_LOOPBACK_NAMES = frozenset({"localhost", "localhost.localdomain"})

# Statuses worth trying again. A 429 is the site asking for less; the 5xx pair is a gateway
# or a worker that was momentarily unavailable. Everything else — a rejected slug, a missing
# capability, a firewall's refusal — will fail identically however many times it is sent.
TRANSIENT = frozenset({429, 502, 503, 504})

# What a status means when the request was authenticated and well-formed. These are the
# failures that are hard to place on someone else's WordPress, where the cause is usually
# infrastructure rather than the request.
_GUIDANCE = {
    401: (
        "The site did not accept the application password. Either application passwords are "
        "disabled there, or the server is dropping the Authorization header before PHP sees "
        "it — the usual cause under CGI/FastCGI, fixed host-side with `CGIPassAuth On` or "
        '`SetEnvIf Authorization "(.*)" HTTP_AUTHORIZATION=$1`.'
    ),
    403: (
        "The site refused the request outright. On a hosted WordPress this is usually a "
        "firewall or security plugin blocking writes to /wp-json, a rate limit reached by "
        "publishing too fast, or a user without the capability the write needs."
    ),
    429: (
        "The site is rate-limiting. Publish more slowly with a larger --pace, or from an "
        "address the host does not throttle."
    ),
}


class WordPressError(Exception):
    """Raised when the site rejects a request or answers with something unusable."""


class InsecureSite(WordPressError):
    """Raised when sending credentials to the configured site would expose them."""


@dataclass(frozen=True)
class Pacing:
    """How hard the publisher is allowed to push a site.

    Publishing the whole ruleset is a few hundred authenticated writes. Locally they go out
    as fast as the loop runs, which is fine; against a hosted WordPress that burst is exactly
    the shape a firewall reads as an attack, and the publication stops halfway with a 403.
    """

    interval: float = 0.0
    attempts: int = 4
    backoff: float = 1.0


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

    def __init__(
        self,
        credentials: Credentials,
        transport: Transport | None = None,
        pacing: Pacing = Pacing(),
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        _require_safe(credentials.site)
        self._credentials = credentials
        self._transport = transport if transport is not None else UrllibTransport()
        self._pacing = pacing
        self._sleep = sleep
        self._sent = 0

    # -- the site itself -------------------------------------------------------------------

    def reachable(self) -> dict:
        """Return the REST API's own description, failing when it cannot be read.

        The first thing to establish about someone else's WordPress: that /wp-json answers at
        all. A firewall that blocks the REST API blocks it here, before any credential is
        involved, which separates "the API is closed" from "the password is wrong".
        """
        found = self._get("/wp-json", {})
        if not isinstance(found, dict):
            raise WordPressError(f"The REST API returned {type(found).__name__}, not an object.")
        return found

    def me(self) -> dict:
        """Return the authenticated user, with the capabilities the site grants them."""
        found = self._get(f"{API}/users/me", {"context": "edit"})
        if not isinstance(found, dict):
            raise WordPressError(f"Reading the current user returned {type(found).__name__}.")
        return found

    # -- pages ---------------------------------------------------------------------------

    def find_page(self, slug: str, parent: int | None = None) -> dict | None:
        """Return the page with ``slug`` directly under ``parent``, or ``None`` when absent.

        Looking a page up rather than remembering its ID is what lets the same bundle publish
        to two sites whose IDs have nothing in common.

        ``parent`` is ``None`` for a page at the top level, and that means **the top level**
        rather than anywhere. A slug is not unique across a WordPress site — it is unique
        among siblings — so a lookup that ignored the parent would match a page somebody else
        made in an unrelated corner of the site, and the caller would then overwrite it.
        Identity here is the pair, never the slug alone.
        """
        # `context=edit` is what makes the response carry `content.raw`, the text as stored.
        # Without it only `content.rendered` comes back, which has been through WordPress's
        # own filters and can never equal what was sent — so every page would look changed on
        # every run, and "unchanged" would be a state the publisher could never report.
        wanted = parent or 0
        query = {
            "slug": slug,
            "status": "any",
            "per_page": "100",
            "context": "edit",
            "parent": str(wanted),
        }
        found = self._get(f"{API}/pages", query)
        if not isinstance(found, list):
            raise WordPressError(f"Looking up the page {slug!r} returned {type(found).__name__}.")
        for page in found:
            if page.get("slug") == slug and (page.get("parent") or 0) == wanted:
                return page
        return None

    def children(self, parent: int) -> list[dict]:
        """Return every page directly under ``parent``, whatever its status."""
        query = {"parent": str(parent), "status": "any", "per_page": "100"}
        found = self._get(f"{API}/pages", query)
        if not isinstance(found, list):
            raise WordPressError(f"Listing children of {parent} returned {type(found).__name__}.")
        return found

    def list_pages(self, per_page: int = 100) -> Iterator[dict]:
        """Yield every page on the site, whatever its status.

        Read in pages of a hundred rather than one lookup per slug: checking a bundle of two
        hundred against a site is two requests this way and two hundred the other, and the
        difference is what keeps a preflight check from tripping the rate limit it exists to
        warn about.
        """
        page = 1
        while True:
            found = self._get(
                f"{API}/pages",
                {
                    "per_page": str(per_page),
                    "page": str(page),
                    "status": "any",
                    "context": "edit",
                    "orderby": "id",
                    "order": "asc",
                },
            )
            if not isinstance(found, list):
                raise WordPressError(f"Listing pages returned {type(found).__name__}.")
            yield from found
            if len(found) < per_page:
                return
            page += 1

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

        for attempt in range(1, max(1, self._pacing.attempts) + 1):
            self._pace()
            response = self._transport.request(method, url, headers=sent, body=body)
            if response.status not in TRANSIENT or attempt == self._pacing.attempts:
                return response
            self._sleep(_retry_after(response, self._pacing.backoff * 2 ** (attempt - 1)))
        raise WordPressError(f"{method} {path} was never attempted.")  # pragma: no cover

    def _pace(self) -> None:
        """Wait between requests, when the caller asked to publish gently."""
        if self._sent and self._pacing.interval:
            self._sleep(self._pacing.interval)
        self._sent += 1

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

    said = f" — {detail}" if detail else ""
    guidance = _GUIDANCE.get(response.status)
    return f"HTTP {response.status}{said}" + (f"\n{guidance}" if guidance else "")


def _retry_after(response: Response, fallback: float) -> float:
    """Return how long to wait before trying again, preferring what the site asked for."""
    header = response.headers.get("retry-after", "")
    try:
        return max(0.0, float(header))
    except ValueError:
        return fallback


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
