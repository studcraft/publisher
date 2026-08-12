#!/usr/bin/env python3
"""SessionStart hook: list the open OpenSpec changes.

The harness already reports the branch and whether the tree is dirty, so this
only adds what it does not: which changes are open right now. That is checked,
not recalled — the maintainer merges pull requests between turns, so any list
carried forward in a conversation is stale by construction.

Prints nothing and exits 0 on any failure. A hook that breaks a session start
to report that it could not read a directory is worse than no hook.
"""

import json
import sys
from pathlib import Path

CHANGES_DIR = Path(__file__).resolve().parent.parent.parent / "openspec" / "changes"


def main() -> int:
    if not CHANGES_DIR.is_dir():
        return 0

    changes = sorted(p.name for p in CHANGES_DIR.iterdir() if p.is_dir() and p.name != "archive")
    summary = ", ".join(changes) if changes else "none"

    print(
        json.dumps(
            {
                "hookSpecificOutput": {
                    "hookEventName": "SessionStart",
                    "additionalContext": f"Open OpenSpec changes, read just now: {summary}. "
                    "They may never be created or edited on `main` — branch first "
                    "(see system/openspec-workflow.md).",
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
