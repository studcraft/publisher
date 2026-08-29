"""Tests for :mod:`publisher.sync`."""

from __future__ import annotations

import json
from pathlib import Path
from unittest import mock

import pytest

from publisher import sync


def _write_docs(clone_root: Path, versions: dict[str, str]) -> None:
    """Create a ``docs/`` tree under ``clone_root`` with the given per-file versions."""
    docs = clone_root / "docs"
    docs.mkdir(parents=True, exist_ok=True)
    for name, version in versions.items():
        docs.joinpath(name).write_text(
            f"# Title\n\n**Version:** {version}\n\n---\n", encoding="utf-8"
        )


def _fake_run(commit: str = "abc123", versions: dict[str, str] | None = None):
    """Build a ``subprocess.run`` stub that creates the clone dir and reports ``commit``."""
    versions = {"01-foundations.md": "0.2.0 Draft"} if versions is None else versions

    def run(cmd: list[str], **kwargs: object) -> mock.Mock:
        if "clone" in cmd:
            dest = Path(cmd[-1])
            dest.mkdir(parents=True, exist_ok=True)
            _write_docs(dest, versions)
            return mock.Mock(stdout="")
        return mock.Mock(stdout=f"{commit}\n")

    return run


def test_clone_source_replaces_existing_checkout(tmp_path: Path) -> None:
    """A stale checkout is deleted before the clone runs."""
    dest = tmp_path / "studcraft"
    dest.mkdir()
    (dest / "stale.txt").write_text("old")

    with mock.patch.object(sync.subprocess, "run", side_effect=_fake_run()):
        commit = sync.clone_source(rev="main", dest=dest, lock_path=tmp_path / "lock.json")

    assert commit == "abc123"
    assert not (dest / "stale.txt").exists()


def test_main_passes_rev_and_prints(tmp_path: Path, capsys: object) -> None:
    """``main`` forwards ``--rev`` and reports the resolved commit."""
    dest = tmp_path / "studcraft"

    with mock.patch.object(sync.subprocess, "run", side_effect=_fake_run("deadbeef")):
        exit_code = sync.main(
            ["--rev", "v1.0.0", "--dest", str(dest), "--lock", str(tmp_path / "lock.json")]
        )

    assert exit_code == 0
    out = capsys.readouterr().out
    assert "v1.0.0" in out
    assert "deadbeef" in out


def test_clone_writes_lock_file(tmp_path: Path) -> None:
    """A successful clone records repo, rev, commit and version."""
    dest = tmp_path / "studcraft"
    lock = tmp_path / "studcraft.lock.json"

    with mock.patch.object(sync.subprocess, "run", side_effect=_fake_run("cafe1234")):
        sync.clone_source(repo="https://example.test/x.git", rev="main", dest=dest, lock_path=lock)

    payload = json.loads(lock.read_text(encoding="utf-8"))
    assert payload == {
        "commit": "cafe1234",
        "repo": "https://example.test/x.git",
        "rev": "main",
        "version": "0.2.0 Draft",
    }
    assert lock.read_text(encoding="utf-8").endswith("\n")


def test_lock_records_requested_rev_verbatim(tmp_path: Path) -> None:
    """An explicit ``--rev`` is recorded as asked for, alongside what it resolved to."""
    dest = tmp_path / "studcraft"
    lock = tmp_path / "studcraft.lock.json"

    with mock.patch.object(sync.subprocess, "run", side_effect=_fake_run("99887766")):
        sync.clone_source(rev="v0.2.0", dest=dest, lock_path=lock)

    payload = json.loads(lock.read_text(encoding="utf-8"))
    assert payload["rev"] == "v0.2.0"
    assert payload["commit"] == "99887766"


def test_version_disagreement_fails(tmp_path: Path) -> None:
    """Documents that disagree on the version are an upstream defect, not a guess."""
    dest = tmp_path / "studcraft"
    versions = {"01-foundations.md": "0.2.0 Draft", "02-core-rules.md": "0.3.0 Draft"}

    with mock.patch.object(sync.subprocess, "run", side_effect=_fake_run(versions=versions)):
        with pytest.raises(sync.SyncError) as excinfo:
            sync.clone_source(dest=dest, lock_path=tmp_path / "lock.json")

    message = str(excinfo.value)
    assert "01-foundations.md" in message
    assert "02-core-rules.md" in message
    assert "0.3.0 Draft" in message


def test_missing_version_fails(tmp_path: Path) -> None:
    """A clone whose documents declare no version cannot be pinned."""
    clone_root = tmp_path / "studcraft"
    (clone_root / "docs").mkdir(parents=True)
    (clone_root / "docs" / "01-foundations.md").write_text("# Title\n\nNo header here.\n")

    with pytest.raises(sync.SyncError, match="Version"):
        sync.read_ruleset_version(clone_root)


def test_failed_clone_leaves_previous_lock_intact(tmp_path: Path) -> None:
    """A clone that fails must not overwrite the pin a working build depends on."""
    lock = tmp_path / "studcraft.lock.json"
    lock.write_text('{"commit": "previous"}\n', encoding="utf-8")

    def failing_run(cmd: list[str], **kwargs: object) -> mock.Mock:
        raise sync.subprocess.CalledProcessError(returncode=128, cmd=cmd)

    with mock.patch.object(sync.subprocess, "run", side_effect=failing_run):
        with pytest.raises(sync.subprocess.CalledProcessError):
            sync.clone_source(dest=tmp_path / "studcraft", lock_path=lock)

    assert json.loads(lock.read_text(encoding="utf-8"))["commit"] == "previous"


def test_read_lock_missing_file(tmp_path: Path) -> None:
    """Reading an absent pin points the operator at the command that creates it."""
    with pytest.raises(sync.SyncError, match="publisher.sync"):
        sync.read_lock(tmp_path / "nope.json")


_GIT_ENV = {
    "GIT_AUTHOR_NAME": "t",
    "GIT_AUTHOR_EMAIL": "t@example.test",
    "GIT_COMMITTER_NAME": "t",
    "GIT_COMMITTER_EMAIL": "t@example.test",
    "PATH": "/usr/bin:/bin:/usr/local/bin",
}


def _git(*args: str) -> str:
    import subprocess

    return subprocess.run(
        ["git", *args], check=True, capture_output=True, text=True, env=_GIT_ENV
    ).stdout.strip()


def test_restore_pinned_checks_out_the_pinned_commit(tmp_path: Path) -> None:
    """A build can always get back to the commit the lock file records.

    Cloning a branch cannot do this: it resolves to wherever the branch is now, which drifts
    the moment upstream moves. The pinned commit here is deliberately not the tip.
    """
    origin = tmp_path / "origin"
    origin.mkdir()
    _git("init", "-q", str(origin))
    (origin / "a.txt").write_text("first", encoding="utf-8")
    _git("-C", str(origin), "add", "a.txt")
    _git("-C", str(origin), "commit", "-qm", "first")
    pinned = _git("-C", str(origin), "rev-parse", "HEAD")

    (origin / "a.txt").write_text("second", encoding="utf-8")
    _git("-C", str(origin), "add", "a.txt")
    _git("-C", str(origin), "commit", "-qm", "second")
    tip = _git("-C", str(origin), "rev-parse", "HEAD")
    assert tip != pinned

    lock = tmp_path / "studcraft.lock.json"
    lock.write_text(
        json.dumps({"commit": pinned, "repo": str(origin), "rev": "main", "version": "1.0"}),
        encoding="utf-8",
    )
    dest = tmp_path / "studcraft"

    assert sync.restore_pinned(lock, dest) == pinned
    assert _git("-C", str(dest), "rev-parse", "HEAD") == pinned
    assert (dest / "a.txt").read_text(encoding="utf-8") == "first"


def test_restore_pinned_replaces_an_existing_checkout(tmp_path: Path) -> None:
    """Whatever was in the destination is gone, so no stale file survives the restore."""
    origin = tmp_path / "origin"
    origin.mkdir()
    _git("init", "-q", str(origin))
    (origin / "a.txt").write_text("first", encoding="utf-8")
    _git("-C", str(origin), "add", "a.txt")
    _git("-C", str(origin), "commit", "-qm", "first")
    pinned = _git("-C", str(origin), "rev-parse", "HEAD")

    dest = tmp_path / "studcraft"
    dest.mkdir()
    (dest / "stale.txt").write_text("old", encoding="utf-8")

    lock = tmp_path / "studcraft.lock.json"
    lock.write_text(json.dumps({"commit": pinned, "repo": str(origin)}), encoding="utf-8")

    sync.restore_pinned(lock, dest)

    assert not (dest / "stale.txt").exists()


def test_restore_pinned_without_lock(tmp_path: Path) -> None:
    """Restoring without a pin says so rather than guessing a commit."""
    with pytest.raises(sync.SyncError, match="lock file"):
        sync.restore_pinned(tmp_path / "nope.json", tmp_path / "studcraft")
