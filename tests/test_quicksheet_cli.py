"""Tests for :mod:`publisher.quicksheet.cli`."""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

from publisher.quicksheet import cli

FIXTURE = Path(__file__).parent / "fixtures" / "mini-docs"

SPEC = """
language = "en"
title = "Mini Sheet"

[[section]]
id = "setup"
heading = "Setup"

[[section.line]]
authored = true
text = "Three minifigures per warband."

[[section.line]]
rule = "MINI-001"
text = "The first rule, condensed."
"""

_GIT_ENV = {
    "GIT_AUTHOR_NAME": "t",
    "GIT_AUTHOR_EMAIL": "t@example.test",
    "GIT_COMMITTER_NAME": "t",
    "GIT_COMMITTER_EMAIL": "t@example.test",
    "PATH": "/usr/bin:/bin:/usr/local/bin",
}


@pytest.fixture()
def workspace(tmp_path: Path) -> dict:
    """Return a pinned mini clone, its lock file, and a valid specification file."""
    clone = tmp_path / "studcraft"
    shutil.copytree(FIXTURE, clone)
    subprocess.run(["git", "init", "-q", str(clone)], check=True, env=_GIT_ENV)
    subprocess.run(["git", "-C", str(clone), "add", "."], check=True, env=_GIT_ENV)
    subprocess.run(["git", "-C", str(clone), "commit", "-qm", "x"], check=True, env=_GIT_ENV)
    commit = subprocess.run(
        ["git", "-C", str(clone), "rev-parse", "HEAD"],
        check=True,
        capture_output=True,
        text=True,
        env=_GIT_ENV,
    ).stdout.strip()

    lock = tmp_path / "studcraft.lock.json"
    lock.write_text(
        json.dumps({"commit": commit, "repo": "x", "rev": "main", "version": "9.9.9 Test"}),
        encoding="utf-8",
    )
    # Always an explicit --data: the CLI defaults to the repository's real product
    # directory, and a test that relied on that default would read and overwrite it.
    data = tmp_path / "quicksheet_3x3"
    data.mkdir()
    (data / "spec.toml").write_text(SPEC, encoding="utf-8")
    return {
        "clone": clone,
        "lock": lock,
        "commit": commit,
        "root": tmp_path,
        "data": data,
        "document": data / "document.json",
    }


def _data(workspace: dict) -> list[str]:
    """Return the --data flag, always explicit, never the CLI default."""
    return ["--data", str(workspace["data"])]


def _published(out: Path) -> Path:
    """Return where the fixture product publishes, derived the same way the code does."""
    return out / "quicksheet_3x3" / "v9.9.9test" / "quicksheet_3x3_en.pdf"


def _argv(workspace: dict, command: str, *rest: str) -> list[str]:
    """Build an argv for ``command``, pointing it at this workspace's clone and lock."""
    return [
        command,
        "--clone",
        str(workspace["clone"]),
        "--lock",
        str(workspace["lock"]),
        *rest,
    ]


def test_build_writes_the_pdf(workspace: dict, capsys: object) -> None:
    """A successful build writes the sheet and reports where."""
    out = workspace["root"] / "dist"

    exit_code = cli.main(_argv(workspace, "build", *_data(workspace), "--out", str(out)))

    assert exit_code == 0
    assert _published(out).exists()
    assert "quicksheet_3x3_en.pdf" in capsys.readouterr().out


def test_build_creates_missing_output_directory(workspace: dict) -> None:
    """A missing output directory is created rather than being an error."""
    out = workspace["root"] / "deep" / "nested"

    assert cli.main(_argv(workspace, "build", *_data(workspace), "--out", str(out))) == 0
    assert _published(out).exists()


def test_build_is_byte_reproducible(workspace: dict) -> None:
    """Two builds of the same inputs produce identical PDFs, as CI asserts."""
    first = workspace["root"] / "one"
    second = workspace["root"] / "two"

    cli.main(_argv(workspace, "build", *_data(workspace), "--out", str(first)))
    cli.main(_argv(workspace, "build", *_data(workspace), "--out", str(second)))

    assert _published(first).read_bytes() == _published(second).read_bytes()


def test_build_fails_on_drifted_pin(workspace: dict, capsys: object) -> None:
    """A clone that moved off the pin fails before the parser runs."""
    workspace["lock"].write_text(
        json.dumps({"commit": "0" * 40, "version": "9.9.9 Test"}), encoding="utf-8"
    )

    exit_code = cli.main(
        _argv(workspace, "build", *_data(workspace), "--out", str(workspace["root"]))
    )

    assert exit_code == 1
    assert "pins" in capsys.readouterr().err


def test_build_fails_on_missing_rule(workspace: dict, capsys: object) -> None:
    """A rule removed upstream fails the build with a non-zero exit."""
    (workspace["data"] / "spec.toml").write_text(
        'language = "en"\n[[section]]\nid = "x"\nheading = "X"\n\n[[section.line]]\n'
        'rule = "MINI-404"\ntext = "gone"\n',
        encoding="utf-8",
    )

    exit_code = cli.main(
        _argv(workspace, "build", *_data(workspace), "--out", str(workspace["root"]))
    )

    assert exit_code == 1
    assert "MINI-404" in capsys.readouterr().err


def test_draft_prints_a_usable_spec(workspace: dict, capsys: object) -> None:
    """The bootstrap draft goes to stdout for redirection into a file."""
    exit_code = cli.main(_argv(workspace, "draft", "MINI-001", "MINI-003"))

    assert exit_code == 0
    out = capsys.readouterr().out
    assert 'rule = "MINI-001"' in out
    assert 'rule = "MINI-003"' in out


def test_extract_writes_only_the_document(workspace: dict) -> None:
    """`extract` stops at the data file; rendering is a separate stage."""
    out = workspace["root"] / "dist"

    exit_code = cli.main(_argv(workspace, "extract", *_data(workspace)))

    assert exit_code == 0
    assert workspace["document"].exists()
    assert not _published(out).exists()


def test_document_is_written_outside_the_render_directory(workspace: dict) -> None:
    """The data file is tracked and the renders are not, so they must not share a home."""
    out = workspace["root"] / "dist"

    cli.main(_argv(workspace, "build", *_data(workspace), "--out", str(out)))

    assert workspace["document"].exists()
    assert _published(out).exists()
    assert not (out / "document.json").exists()


def test_render_does_not_need_the_ruleset(workspace: dict) -> None:
    """The whole point of the middle stage: render works with the clone deleted.

    If this passes only because the renderer quietly re-read the ruleset, deleting the
    clone would break it.
    """
    out = workspace["root"] / "dist"
    cli.main(_argv(workspace, "extract", *_data(workspace)))

    shutil.rmtree(workspace["clone"])
    workspace["lock"].unlink()

    exit_code = cli.main(["render", *_data(workspace), "--out", str(out)])

    assert exit_code == 0
    assert _published(out).exists()


def test_render_reflects_hand_edits(workspace: dict) -> None:
    """Editing the data file changes the output, with no code and no re-extraction."""
    out = workspace["root"] / "dist"
    cli.main(_argv(workspace, "extract", *_data(workspace)))

    document = workspace["document"]
    before = document.read_bytes()
    render_argv = ["render", *_data(workspace), "--out", str(out)]
    cli.main(render_argv)
    first = _published(out).read_bytes()

    payload = json.loads(before)
    payload["title"] = "Retitled By Hand"
    payload["page"]["width_mm"] = 297.0
    payload["page"]["height_mm"] = 210.0
    document.write_text(json.dumps(payload), encoding="utf-8")
    cli.main(render_argv)

    after = _published(out).read_bytes()
    assert after != first
    # 297mm x 210mm in PDF points: the edited page size really reached the output.
    assert b"/MediaBox [0 0 841.89 595.28]" in after


def test_render_rejects_an_unknown_format(workspace: dict, capsys: object) -> None:
    """An unregistered format is refused by the argument parser, listing what exists."""
    with pytest.raises(SystemExit):
        cli.main(["render", *_data(workspace), "--out", str(workspace["root"]), "--format", "stl"])

    assert "pdf" in capsys.readouterr().err


def test_missing_document_names_extract(workspace: dict, capsys: object) -> None:
    """Rendering before extracting says which command makes the file."""
    exit_code = cli.main(
        ["render", "--data", str(workspace["root"] / "absent"), "--out", str(workspace["root"])]
    )

    assert exit_code == 1
    assert "extract" in capsys.readouterr().err
