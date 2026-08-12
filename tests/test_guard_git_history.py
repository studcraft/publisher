"""Regression tests for the git-history PreToolUse guard.

The guard used to grep the raw command string, so a commit message that merely
mentioned a banned operation was blocked. These cases pin both directions:
what must be denied however it is wrapped, and what must stay allowed.
"""

import json
import subprocess
import sys
from pathlib import Path

import pytest

HOOK = Path(__file__).resolve().parent.parent / ".claude" / "hooks" / "guard_git_history.py"

ALLOWED = [
    'git commit -m "docs: explain why we never rebase"',
    "git config --get pull.rebase",
    "git branch -D feature/rebase-cleanup",
    "git config alias.ci 'commit --amend'",
    "git log --grep=amend",
    "git push origin main",
    "git add src/foo.py",
    "git add ./src",
    "git status --short",
    "git merge origin/main",
    "git commit -m \"$(cat <<'EOF'\nfix: stop the rebase\nEOF\n)\"",
]

DENIED = [
    "git rebase",
    "git rebase -i HEAD~3",
    "git -C /tmp/x rebase main",
    "cd /tmp && git rebase",
    "env FOO=bar git rebase",
    "git status && git rebase",
    "git commit --amend --no-edit",
    "git --git-dir=/tmp/x/.git commit --amend",
    "git push --force origin main",
    "git push -f origin main",
    "git push -fu origin main",
    "git push --force-with-lease origin main",
    "git push --force-with-lease=main origin main",
    "git filter-branch --tree-filter true HEAD",
    "git reflog expire --expire=now --all",
    "git update-ref -d refs/heads/x",
    "git add -A",
    "git add --all",
    "git add .",
    "git add -- .",
]

ASKED = [
    "git reset --hard HEAD~3",
    "git clean -fdx",
    "git checkout -- .",
    "git restore src/foo.py",
]


def decision(command: str) -> str:
    """Run the hook on a command and return its permission decision."""
    payload = json.dumps({"tool_input": {"command": command}})
    result = subprocess.run(
        [sys.executable, str(HOOK)], input=payload, capture_output=True, text=True, timeout=10
    )
    if not result.stdout.strip():
        return "allow"
    return json.loads(result.stdout)["hookSpecificOutput"]["permissionDecision"]


@pytest.mark.parametrize("command", ALLOWED)
def test_allowed(command: str) -> None:
    assert decision(command) == "allow"


@pytest.mark.parametrize("command", DENIED)
def test_denied(command: str) -> None:
    assert decision(command) == "deny"


@pytest.mark.parametrize("command", ASKED)
def test_asked(command: str) -> None:
    assert decision(command) == "ask"


def test_malformed_payload_fails_open() -> None:
    result = subprocess.run(
        [sys.executable, str(HOOK)], input="not json", capture_output=True, text=True, timeout=10
    )
    assert result.returncode == 0
    assert result.stdout.strip() == ""
