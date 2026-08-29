"""Tests for :mod:`publisher.rules_web.cli`."""

from __future__ import annotations

import json
from pathlib import Path
from unittest import mock

import pytest

from publisher.quicksheet.index import Block, Rule
from publisher.rules_web import cli

SPEC = 'title = "StudCraft Rules"\n[[document]]\nfile = "02-core-rules.md"\nslug = "core-rules"\n'


def _index() -> dict:
    """Return a one-rule index."""
    return {
        "CORE-001": Rule(
            id="CORE-001",
            title="Unit Base (UB)",
            doc="02-core-rules.md",
            line=56,
            line_end=77,
            blocks=(Block(kind="paragraph", line_start=56, line_end=56, lines=("A volume.",)),),
        )
    }


def _data(tmp_path: Path) -> Path:
    """Return a data directory holding a specification."""
    data = tmp_path / "data"
    data.mkdir()
    data.joinpath("spec.toml").write_text(SPEC, encoding="utf-8")
    return data


def _pinned():
    """Patch the ruleset feed so no clone or network is needed."""
    return (
        mock.patch.object(cli, "verify_pin", return_value="abc123def456"),
        mock.patch.object(cli, "read_lock", return_value={"repo": "r", "version": "0.2.0 Draft"}),
        mock.patch.object(cli, "read_ruleset", return_value=(_index(), ())),
    )


def test_extract_writes_the_document(tmp_path: Path, capsys) -> None:
    """The first stage, and it renders nothing."""
    data = _data(tmp_path)
    with _pinned()[0], _pinned()[1], _pinned()[2]:
        assert cli.main(["extract", "--data", str(data)]) == 0

    payload = json.loads((data / "document.json").read_text(encoding="utf-8"))
    assert [page["slug"] for page in payload["pages"]] == ["core-rules", "core-001"]
    assert "2 pages" in capsys.readouterr().out


def test_build_extracts_and_renders(tmp_path: Path) -> None:
    """The convenience path, and the one CI runs."""
    data = _data(tmp_path)
    out = tmp_path / "publish"
    with _pinned()[0], _pinned()[1], _pinned()[2]:
        assert cli.main(["build", "--data", str(data), "--out", str(out)]) == 0

    assert (out / "rules_web" / "v0.2.0draft" / "rules_web_en.wp.json").is_file()


def test_render_reads_only_the_document(tmp_path: Path) -> None:
    """A hand-edited document can be re-rendered without going near the ruleset."""
    data = _data(tmp_path)
    out = tmp_path / "publish"
    with _pinned()[0], _pinned()[1], _pinned()[2]:
        cli.main(["extract", "--data", str(data)])

    # No ruleset patches in scope: reaching for one here would raise rather than pass.
    assert cli.main(["render", "--data", str(data), "--out", str(out)]) == 0
    assert (out / "rules_web" / "v0.2.0draft" / "rules_web_en.wp.json").is_file()


def test_a_failure_is_reported_and_exits_nonzero(tmp_path: Path, capsys) -> None:
    """A build that cannot run must not look like one that produced nothing to do."""
    data = tmp_path / "data"
    data.mkdir()

    assert cli.main(["render", "--data", str(data)]) == 1
    assert "error:" in capsys.readouterr().err


def test_the_spec_and_document_live_together(tmp_path: Path) -> None:
    """One directory per product, so the two can never be mismatched across products."""
    assert cli.spec_path(Path("data/rules_web")).name == "spec.toml"
    assert cli.document_path(Path("data/rules_web")).name == "document.json"


def test_a_command_is_required(capsys) -> None:
    """`python -m publisher.rules_web` on its own does nothing, and says so."""
    with pytest.raises(SystemExit):
        cli.main([])
