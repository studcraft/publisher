"""Tests for :mod:`publisher.wp.transport`.

The real transport is thin on purpose, and its one interesting behaviour is that an error
status comes back as a response rather than as an exception — the client turns a 404 into
"this page does not exist yet", and a transport that raised would make that impossible.
"""

from __future__ import annotations

import io
import urllib.error
from unittest import mock

from publisher.wp.transport import UrllibTransport


class _Reply:
    """Stands in for the object ``urlopen`` returns."""

    def __init__(self, status: int, body: bytes) -> None:
        self.status = status
        self._body = body
        self.headers = {"Content-Type": "application/json"}

    def read(self) -> bytes:
        return self._body

    def __enter__(self) -> _Reply:
        return self

    def __exit__(self, *exc: object) -> None:
        return None


def test_a_request_carries_its_method_headers_and_body() -> None:
    """All three are what the WordPress API distinguishes calls by."""
    with mock.patch("publisher.wp.transport.urllib.request.urlopen") as urlopen:
        urlopen.return_value = _Reply(200, b'{"ok": true}')
        response = UrllibTransport().request(
            "POST",
            "https://example.test/wp-json/wp/v2/pages",
            headers={"Authorization": "Basic x"},
            body=b'{"slug": "core-001"}',
        )

    request = urlopen.call_args.args[0]
    assert request.method == "POST"
    assert request.data == b'{"slug": "core-001"}'
    assert request.get_header("Authorization") == "Basic x"
    assert response.status == 200
    assert response.body == b'{"ok": true}'
    assert response.headers["content-type"] == "application/json"


def test_an_error_status_comes_back_as_a_response() -> None:
    """WordPress explains a refusal in the body; raising here would discard it."""
    error = urllib.error.HTTPError(
        url="https://example.test",
        code=400,
        msg="Bad Request",
        hdrs={"Content-Type": "application/json"},
        fp=io.BytesIO(b'{"message": "Invalid slug."}'),
    )

    with mock.patch("publisher.wp.transport.urllib.request.urlopen", side_effect=error):
        response = UrllibTransport().request("GET", "https://example.test", headers={})

    assert response.status == 400
    assert b"Invalid slug." in response.body
