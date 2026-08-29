# OpenSpec Branch Policy

**Hard rule: never create or modify OpenSpec change proposals (`openspec/changes/**`) directly on `main`.** Always work on a branch and open a PR — see [CONTRIBUTING.md](../CONTRIBUTING.md). No exceptions, including for repo admins.

This applies to every step of the OpenSpec lifecycle: `openspec new change`, editing artifacts (`proposal.md`, `design.md`, `tasks.md`, delta specs), implementing tasks, and archiving.

Enforcement, two layers:

- **`guard_openspec_branch.py`** (`.claude/hooks/`, wired as a `PreToolUse` hook in `.claude/settings.json`) denies any Write/Edit under `openspec/changes/**` while `HEAD` is `main`, before the edit happens. This is the real gate for agents: it lives in the repo, needs no local setup, and applies from a fresh clone.
- **`openspec-branch-gate`** (`.github/workflows/ci.yml`) runs on every push to `main` and fails loudly if a commit touching `openspec/changes/**` did not arrive through a pull request — a backstop for anything that bypasses the hook (a human editing outside an agent, for instance). Merged PRs pass; a direct admin push does not. It cannot block the push itself: GitHub branch protection lets repo admins push directly to `main`.

A third hook is not enforcement but orientation: **`session_orientation.py`** (`.claude/hooks/`, wired as a `SessionStart` hook) prints the open changes under `openspec/changes/` at the start of every session, plus a reminder of the rule above. It exists because that list is checked rather than recalled — the maintainer merges pull requests between turns, so any list carried forward inside a conversation is stale by construction. It prints nothing and exits 0 on any failure: a hook that breaks a session start to report that it could not read a directory is worse than no hook.
