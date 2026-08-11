#!/usr/bin/env python3
"""SessionStart hook: state where the repository is, so nobody greps for it.

Every session in this repository opens the same way — which branch is this,
is there an open OpenSpec change, is the tree dirty. This is checked, not
recalled: the maintainer merges pull requests between turns, so any branch
or change list carried forward in a conversation is stale by construction.

Prints nothing and exits 0 on any failure. A hook that breaks a session
start to report that it could not read a branch name is worse than no hook.
"""

import json
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
CHANGES_DIR = REPO_ROOT / "openspec" / "changes"


def git(*args: str) -> str:
    try:
        proc = subprocess.run(
            ["git", *args], cwd=REPO_ROOT, capture_output=True, text=True, timeout=10
        )
    except (OSError, subprocess.SubprocessError):
        return ""
    return proc.stdout.strip() if proc.returncode == 0 else ""


def main() -> int:
    lines: list[str] = []

    branch = git("rev-parse", "--abbrev-ref", "HEAD")
    if branch:
        note = ""
        if branch == "main":
            note = " — no OpenSpec change may be committed here; branch first"
        lines.append(f"Branch: {branch}{note}")

    dirty = git("status", "--short")
    if dirty:
        count = len(dirty.splitlines())
        lines.append(f"Working tree: {count} uncommitted path(s)")
    elif branch:
        lines.append("Working tree: clean")

    if CHANGES_DIR.is_dir():
        changes = sorted(
            p.name for p in CHANGES_DIR.iterdir() if p.is_dir() and p.name != "archive"
        )
        lines.append("Open OpenSpec changes: " + (", ".join(changes) if changes else "none"))

    if not lines:
        return 0

    print(
        json.dumps(
            {
                "hookSpecificOutput": {
                    "hookEventName": "SessionStart",
                    "additionalContext": "Repository state, read just now:\n"
                    + "\n".join(f"- {line}" for line in lines),
                }
            }
        )
    )
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception:
        sys.exit(0)
