"""Tests for how hard the client is allowed to push a site.

Publishing the ruleset is a few hundred authenticated writes in a few seconds. Locally that
is free; against a hosted WordPress it is the shape a firewall reads as an attack, and the
publication stops halfway through with a 403 that says nothing useful.
"""

from __future__ import annotations

import pytest

from publisher.wp.client import Credentials, Pacing, WordPress, WordPressError
from publisher.wp.transport import Response
from tests.fake_wordpress import FakeWordPress

LOCAL = Credentials(site="http://localhost:8080", user="admin", password="pw")


class _Flaky:
    """Answers with ``statuses`` in turn, then like a healthy site."""

    def __init__(self, *statuses: int, retry_after: str | None = None) -> None:
        self._statuses = list(statuses)
        self._retry_after = retry_after
        self.calls = 0
        self._site = FakeWordPress()

    def request(self, method, url, *, headers, body=None) -> Response:
        self.calls += 1
        if self._statuses:
            status = self._statuses.pop(0)
            headers = {"retry-after": self._retry_after} if self._retry_after else {}
            return Response(status=status, body=b'{"message": "later"}', headers=headers)
        return self._site.request(method, url, headers=headers, body=body)


def _site(transport, **pacing) -> tuple[WordPress, list[float]]:
    """Return a client over ``transport``, and the list its sleeps are recorded in."""
    waits: list[float] = []
    return (
        WordPress(LOCAL, transport, pacing=Pacing(**pacing), sleep=waits.append),
        waits,
    )


def test_a_rate_limited_request_is_tried_again() -> None:
    """A 429 is the site asking for less, not a refusal."""
    transport = _Flaky(429)
    site, waits = _site(transport, attempts=4, backoff=1.0)

    assert site.find_page("core-001") is None
    assert transport.calls == 2
    assert waits == [1.0]


def test_the_wait_doubles_each_time() -> None:
    """Trying again at the same interval is what turns a rate limit into a ban."""
    transport = _Flaky(503, 503, 429)
    site, waits = _site(transport, attempts=4, backoff=1.0)

    site.find_page("core-001")
    assert waits == [1.0, 2.0, 4.0]


def test_the_site_s_own_retry_after_wins() -> None:
    """It knows when it will be ready and we do not."""
    transport = _Flaky(429, retry_after="30")
    site, waits = _site(transport, attempts=2, backoff=1.0)

    site.find_page("core-001")
    assert waits == [30.0]


def test_an_unparseable_retry_after_falls_back_to_the_backoff() -> None:
    """A date-shaped header is valid HTTP and useless to us; do not crash on it."""
    transport = _Flaky(429, retry_after="Wed, 21 Oct 2026 07:28:00 GMT")
    site, waits = _site(transport, attempts=2, backoff=2.0)

    site.find_page("core-001")
    assert waits == [2.0]


def test_giving_up_reports_what_the_site_said() -> None:
    """After the last attempt the failure is real and must not be swallowed."""
    transport = _Flaky(429, 429, 429)
    site, _ = _site(transport, attempts=3, backoff=0.5)

    with pytest.raises(WordPressError) as failure:
        site.find_page("core-001")
    assert "429" in str(failure.value)
    assert "rate-limiting" in str(failure.value)
    assert transport.calls == 3


def test_a_refusal_is_not_retried() -> None:
    """A rejected slug or a missing capability fails identically however often it is sent."""
    transport = _Flaky(403, 403, 403)
    site, waits = _site(transport, attempts=4)

    with pytest.raises(WordPressError):
        site.find_page("core-001")
    assert transport.calls == 1
    assert waits == []


def test_the_pace_puts_a_gap_between_requests() -> None:
    """The first request goes at once; every one after it waits."""
    site, waits = _site(FakeWordPress(), interval=0.25)

    site.find_page("a")
    site.find_page("b")
    site.find_page("c")

    assert waits == [0.25, 0.25]


def test_no_pace_means_no_waiting() -> None:
    """The local harness is not rate-limited, and 195 pages should not take a minute."""
    site, waits = _site(FakeWordPress())

    site.find_page("a")
    site.find_page("b")

    assert waits == []
