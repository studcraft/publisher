#!/usr/bin/env python3
"""PreToolUse guard for Write and Edit: refuse OpenSpec changes on main.

system/openspec-workflow.md states the rule: openspec/changes/** may never be
created or modified directly on main, no exceptions. CI enforces it too (the
openspec-branch-gate job in .github/workflows/ci.yml), but only after a push
— and only for whoever reads the red check. This hook refuses the edit at
the moment it is attempted, before anything reaches disk.

Input is the PreToolUse JSON payload on stdin. Output is either nothing
(allow) or a deny decision whose reason is what the agent reads instead of
the edit.

Fails open. A missing git binary, a detached HEAD, or any unexpected
exception allows the edit: a guard that blocks work it does not understand
gets switched off, and then nothing is enforced at all.
"""

import json
import os
import subprocess
import sys
from pathlib import Path


def allow():
    sys.exit(0)


def deny(reason):
    print(
        json.dumps(
            {
                "hookSpecificOutput": {
                    "hookEventName": "PreToolUse",
                    "permissionDecision": "deny",
                    "permissionDecisionReason": reason,
                }
            }
        )
    )
    sys.exit(0)


def git(root, *args):
    result = subprocess.run(["git", *args], cwd=root, capture_output=True, text=True, timeout=10)
    return result.stdout.strip() if result.returncode == 0 else ""


def main():
    payload = json.load(sys.stdin)
    tool_input = payload.get("tool_input") or {}

    raw_path = tool_input.get("file_path")
    if not raw_path:
        allow()

    project_dir = os.environ.get("CLAUDE_PROJECT_DIR")
    root = (
        Path(project_dir)
        if project_dir
        else Path(git(Path.cwd(), "rev-parse", "--show-toplevel") or ".")
    )
    if not (root / "AGENTS.md").is_file():
        allow()  # Not this repository. Not this hook's business.

    target = Path(raw_path)
    if not target.is_absolute():
        target = root / target

    try:
        rel = target.resolve().relative_to(root.resolve())
    except ValueError:
        allow()  # Outside the repository.

    rel_posix = rel.as_posix()
    if not rel_posix.startswith("openspec/changes/"):
        allow()

    branch = git(root, "rev-parse", "--abbrev-ref", "HEAD")
    if not branch or branch == "HEAD":
        allow()  # Detached or unreadable. Fail open.

    if branch == "main":
        deny(
            f"You are on `main`. OpenSpec change proposals ({rel_posix}) may "
            "never be created or edited directly on main — no exceptions, "
            "including for repo admins. See system/openspec-workflow.md. "
            "Create a branch first, e.g.: git checkout -b <change-name>"
        )

    allow()


if __name__ == "__main__":
    try:
        main()
    except Exception:
        sys.exit(0)  # Fail open, deliberately.
