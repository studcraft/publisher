"""Tests for :mod:`publisher.quicksheet.index`."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from publisher.quicksheet import index as idx

FIXTURE = Path(__file__).parent / "fixtures" / "mini-docs"


@pytest.fixture()
def clone(tmp_path: Path) -> Path:
    """Return a writable copy of the mini-docs stand-in for a ruleset clone."""
    destination = tmp_path / "studcraft"
    shutil.copytree(FIXTURE, destination)
    return destination


def _feed_path(clone_root: Path) -> Path:
    return clone_root / "scripts" / "feed.json"


def test_build_index_collects_rules_across_documents(clone: Path) -> None:
    """Every rule ID in the feed is indexed, including nested ones."""
    result = idx.build_index(clone)

    assert sorted(result) == ["MINI-001", "MINI-002", "MINI-003"]
    assert result["MINI-002"].doc == "01-mini.md"
    assert result["MINI-003"].doc == "02-mini.md"


def test_rule_carries_title_location_and_blocks(clone: Path) -> None:
    """A rule knows where it came from, so a sheet line can cite it."""
    rule = idx.rule(idx.build_index(clone), "MINI-001")

    assert rule.title == "First rule"
    assert rule.doc == "01-mini.md"
    assert (rule.line, rule.line_end) == (7, 18)
    assert [block.kind for block in rule.blocks] == ["paragraph", "table"]
    assert rule.blocks[1].lines[0] == "| Result | Effect |"


def test_unknown_rule_fails_by_name(clone: Path) -> None:
    """A rule ID that is not in the ruleset is named in the error."""
    with pytest.raises(idx.UnknownRuleError, match="MINI-404"):
        idx.rule(idx.build_index(clone), "MINI-404")


def test_missing_field_in_feed_fails(clone: Path) -> None:
    """An upstream schema change fails loudly instead of thinning the sheet."""
    feed = json.loads(_feed_path(clone).read_text(encoding="utf-8"))
    del feed["01-mini.md"]["root"]["children"][0]["line_end"]
    _feed_path(clone).write_text(json.dumps(feed), encoding="utf-8")

    with pytest.raises(idx.FeedError, match="line_end"):
        idx.build_index(clone)


def test_invalid_json_from_parser_fails(clone: Path) -> None:
    """Output that is not JSON is reported as such."""
    _feed_path(clone).write_text("not json at all", encoding="utf-8")

    with pytest.raises(idx.FeedError, match="valid JSON"):
        idx.build_index(clone)


def test_parser_non_zero_exit_surfaces_stderr(clone: Path) -> None:
    """The upstream script's own error output reaches the operator."""
    (clone / "scripts" / "parse_ruleset.py").write_text(
        "import sys\nsys.stderr.write('upstream exploded')\nsys.exit(3)\n", encoding="utf-8"
    )

    with pytest.raises(idx.FeedError, match="upstream exploded"):
        idx.build_index(clone)


def test_missing_parser_fails(clone: Path) -> None:
    """A clone without the upstream parser is not a usable feed."""
    (clone / "scripts" / "parse_ruleset.py").unlink()

    with pytest.raises(idx.FeedError, match="parser not found"):
        idx.build_index(clone)


def test_feed_without_rules_fails(clone: Path) -> None:
    """A feed that parses but carries no rule IDs is a defect, not an empty sheet."""
    _feed_path(clone).write_text("{}", encoding="utf-8")

    with pytest.raises(idx.FeedError, match="No rules found"):
        idx.build_index(clone)


def _make_git_clone(root: Path, content: str) -> str:
    """Create a real one-commit git repository at ``root`` and return its commit SHA."""
    import subprocess

    root.mkdir(parents=True, exist_ok=True)
    (root / "file.txt").write_text(content, encoding="utf-8")
    env = {
        "GIT_AUTHOR_NAME": "t",
        "GIT_AUTHOR_EMAIL": "t@example.test",
        "GIT_COMMITTER_NAME": "t",
        "GIT_COMMITTER_EMAIL": "t@example.test",
        "PATH": "/usr/bin:/bin:/usr/local/bin",
    }
    subprocess.run(["git", "init", "-q", str(root)], check=True, env=env)
    subprocess.run(["git", "-C", str(root), "add", "file.txt"], check=True, env=env)
    subprocess.run(["git", "-C", str(root), "commit", "-qm", "x"], check=True, env=env)
    return subprocess.run(
        ["git", "-C", str(root), "rev-parse", "HEAD"],
        check=True,
        capture_output=True,
        text=True,
        env=env,
    ).stdout.strip()


def test_verify_pin_accepts_matching_clone(tmp_path: Path) -> None:
    """A clone sitting on the pinned commit is allowed to build."""
    root = tmp_path / "studcraft"
    commit = _make_git_clone(root, "one")
    lock = tmp_path / "lock.json"
    lock.write_text(json.dumps({"commit": commit}), encoding="utf-8")

    assert idx.verify_pin(root, lock) == commit


def test_verify_pin_rejects_drifted_clone(tmp_path: Path) -> None:
    """A clone that moved off the pin names both SHAs and refuses to build."""
    root = tmp_path / "studcraft"
    commit = _make_git_clone(root, "one")
    lock = tmp_path / "lock.json"
    lock.write_text(json.dumps({"commit": "0" * 40}), encoding="utf-8")

    with pytest.raises(idx.PinError) as excinfo:
        idx.verify_pin(root, lock)

    message = str(excinfo.value)
    assert commit in message
    assert "0" * 40 in message


def test_verify_pin_without_clone(tmp_path: Path) -> None:
    """An absent clone points the operator at the command that creates one."""
    lock = tmp_path / "lock.json"
    lock.write_text(json.dumps({"commit": "0" * 40}), encoding="utf-8")

    with pytest.raises(idx.PinError, match="publisher.sync"):
        idx.verify_pin(tmp_path / "nope", lock)


def test_verify_pin_without_lock(tmp_path: Path) -> None:
    """An absent pin is reported as a missing lock file, not a mismatch."""
    root = tmp_path / "studcraft"
    _make_git_clone(root, "one")

    with pytest.raises(idx.PinError, match="lock file"):
        idx.verify_pin(root, tmp_path / "nope.json")
