"""How a request actually leaves the process, and the seam that lets it not.

The client takes its transport as a dependency rather than calling ``urllib`` directly. That
one seam is what makes the publication stage testable: create-versus-update, orphan handling,
media lookup and the credential refusals are all behaviour worth pinning, and none of it
should need a WordPress — or a network — to exercise.
"""

from __future__ import annotations

import urllib.error
import urllib.request
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Protocol

DEFAULT_TIMEOUT = 30


@dataclass(frozen=True)
class Response:
    """One HTTP response: enough to act on, and nothing about how it was fetched."""

    status: int
    body: bytes
    headers: Mapping[str, str] = field(default_factory=dict)


class Transport(Protocol):
    """Sends one request and returns its response.

    An implementation MUST return a :class:`Response` for an error status rather than raising:
    the client turns a 404 into "this page does not exist yet", which is an ordinary part of
    publishing rather than a failure.
    """

    def request(
        self,
        method: str,
        url: str,
        *,
        headers: Mapping[str, str],
        body: bytes | None = None,
    ) -> Response:
        """Return the response to ``method url``."""
        ...  # pragma: no cover - a protocol declaration has no body to run


class UrllibTransport:
    """The real transport, over the standard library.

    No third-party HTTP client: the whole surface used here is four verbs and a JSON body,
    and a dependency that has to be pinned and audited for that is a poor trade.
    """

    def __init__(self, timeout: int = DEFAULT_TIMEOUT) -> None:
        self._timeout = timeout

    def request(
        self,
        method: str,
        url: str,
        *,
        headers: Mapping[str, str],
        body: bytes | None = None,
    ) -> Response:
        """Return the response to ``method url``, treating an error status as a response."""
        request = urllib.request.Request(url, data=body, method=method)
        for name, value in headers.items():
            request.add_header(name, value)
        try:
            with urllib.request.urlopen(request, timeout=self._timeout) as reply:
                return Response(
                    status=reply.status,
                    body=reply.read(),
                    headers={key.lower(): value for key, value in reply.headers.items()},
                )
        except urllib.error.HTTPError as error:
            # WordPress explains a rejection in the body — an unknown parameter, a slug that
            # collides, a capability the user lacks. Discarding it here would leave the caller
            # with a bare status code to guess from.
            return Response(
                status=error.code,
                body=error.read(),
                headers={key.lower(): value for key, value in error.headers.items()},
            )
