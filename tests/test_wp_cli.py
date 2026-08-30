"""Tests for :mod:`publisher.wp.cli`."""

from __future__ import annotations

import json
from pathlib import Path
from unittest import mock

import pytest

from publisher.quicksheet.model import Source
from publisher.rules_web import document as document_io
from publisher.rules_web import render as rendering
from publisher.rules_web.model import Document, Entry, Page
from publisher.wp import cli
from publisher.wp.client import Credentials, WordPress
from tests.fake_wordpress import FakeWordPress

ENVIRONMENT = {
    "WP_BASE_URL": "http://localhost:8080",
    "WP_USER": "admin",
    "WP_APP_PASSWORD": "pw",
}


def _document() -> Document:
    """Return a document of one index page and one rule page."""
    return Document(
        title="StudCraft Rules",
        pages=(
            Page(
                slug="rules",
                title="Rules",
                kind="root",
                entries=(Entry(title="Core Rules", slug="core-rules"),),
            ),
            Page(
                slug="core-rules",
                title="Core Rules",
                kind="document",
                parent="rules",
                entries=(Entry(rule="CORE-001", title="Unit Base", slug="core-001"),),
            ),
            Page(
                slug="core-001",
                title="CORE-001 — Unit Base",
                kind="rule",
                parent="core-rules",
                body_html="<p>A volume.</p>",
            ),
        ),
        source=Source(repo="r", ruleset_version="0.2.0 Draft", commit="abc123"),
    )


def _published(tmp_path: Path) -> tuple[Path, Path]:
    """Write a document and its bundle, and return the data directory and publish root."""
    data = tmp_path / "data"
    data.mkdir()
    document_io.write(_document(), data / "document.json")
    out = tmp_path / "publish"
    rendering.render(_document(), out)
    return data, out


def _run(argv: list[str], fake: FakeWordPress, environment: dict | None = None) -> int:
    """Run the CLI with ``fake`` standing in for the site."""
    made = mock.Mock(
        side_effect=lambda credentials, **kwargs: WordPress(credentials, fake, **kwargs),
    )
    with mock.patch.dict(
        cli.os.environ, ENVIRONMENT if environment is None else environment, clear=True
    ):
        with mock.patch.object(cli, "WordPress", made):
            return cli.main(argv)


def test_push_stages_the_bundle(tmp_path: Path, capsys) -> None:
    """The bundle is the only input, and the site ends up holding every page."""
    data, out = _published(tmp_path)
    fake = FakeWordPress()

    assert _run(["push", "--data", str(data), "--out", str(out)], fake) == 0

    assert sorted(fake.slugs()) == ["core-001", "core-rules", "rules"]
    assert {page["status"] for page in fake.pages.values()} == {"private"}
    assert "3 created" in capsys.readouterr().out


def test_promote_publishes_what_push_staged(tmp_path: Path, capsys) -> None:
    """Two commands, because the gap between them is the review."""
    data, out = _published(tmp_path)
    fake = FakeWordPress()
    _run(["push", "--data", str(data), "--out", str(out)], fake)

    assert _run(["promote", "--data", str(data), "--out", str(out)], fake) == 0

    assert {page["status"] for page in fake.pages.values()} == {"publish"}
    assert "3 pages promoted" in capsys.readouterr().out


def test_missing_credentials_are_named(tmp_path: Path, capsys) -> None:
    """Told which variables are absent, rather than a failure at the first request."""
    data, out = _published(tmp_path)
    partial = {"WP_BASE_URL": "http://localhost:8080"}

    assert _run(["push", "--data", str(data), "--out", str(out)], FakeWordPress(), partial) == 2

    error = capsys.readouterr().err
    assert "WP_USER" in error
    assert "WP_APP_PASSWORD" in error


def test_credentials_come_from_the_environment() -> None:
    """Never from a flag: a password in a command line reaches shell history."""
    credentials = cli.credentials(ENVIRONMENT)
    assert credentials == Credentials(site="http://localhost:8080", user="admin", password="pw")


def test_a_site_failure_exits_nonzero(tmp_path: Path, capsys) -> None:
    """A publication that did not happen must not exit as though it had."""
    data, out = _published(tmp_path)

    assert (
        _run(["push", "--data", str(data), "--out", str(out)], FakeWordPress(authorized=False)) == 1
    )
    assert "error:" in capsys.readouterr().err


def test_the_bundle_is_found_from_the_document(tmp_path: Path) -> None:
    """Derived, so the command cannot be pointed at another version's bundle by mistake."""
    data, out = _published(tmp_path)
    path = cli.bundle_path(data, out)

    assert path.name == "rules_web_en.wp.json"
    assert json.loads(path.read_text(encoding="utf-8"))["schema"] == rendering.BUNDLE_SCHEMA


def test_a_command_is_required() -> None:
    """`python -m publisher.wp` on its own publishes nothing, and says so."""
    with pytest.raises(SystemExit):
        cli.main([])


def test_menu_writes_the_navigation(tmp_path: Path, capsys) -> None:
    """The header menu is written from the bundle, not maintained by hand."""
    data, out = _published(tmp_path)
    fake = FakeWordPress()

    assert _run(["menu", "--data", str(data), "--out", str(out)], fake) == 0

    assert len(fake.navigations) == 1
    assert "1 entries" in capsys.readouterr().out


def test_check_reports_and_writes_nothing(tmp_path: Path, capsys) -> None:
    """The preflight is reads only: a site it ran against is a site it did not change."""
    data, out = _published(tmp_path)
    fake = FakeWordPress()

    assert _run(["check", "--data", str(data), "--out", str(out)], fake) == 0

    assert fake.pages == {}
    assert "the REST API answers" in capsys.readouterr().out


def test_check_exits_nonzero_when_the_site_cannot_be_published_to(tmp_path: Path) -> None:
    """An action has to be able to stop on this rather than push into a broken site."""
    data, out = _published(tmp_path)
    fake = FakeWordPress(capabilities={"publish_pages": False, "upload_files": True})

    assert _run(["check", "--data", str(data), "--out", str(out)], fake) == 1


def test_the_pace_and_attempts_reach_the_client(tmp_path: Path) -> None:
    """They are the first thing to reach for after a 403, so they have to be settable."""
    data, out = _published(tmp_path)
    seen = {}

    def record(credentials, pacing=None, **kwargs):
        seen["pacing"] = pacing
        return WordPress(credentials, FakeWordPress(), pacing=pacing, **kwargs)

    with mock.patch.dict(cli.os.environ, ENVIRONMENT, clear=True):
        with mock.patch.object(cli, "WordPress", record):
            cli.main(
                [
                    "check",
                    "--data",
                    str(data),
                    "--out",
                    str(out),
                    "--pace",
                    "0.5",
                    "--attempts",
                    "7",
                ]
            )

    assert (seen["pacing"].interval, seen["pacing"].attempts) == (0.5, 7)
