# Git Strategy

BLOCKER rules. No exceptions — not for "my own branch," not to fix an out-of-date branch, not under time pressure.

## History only grows

- Never force-push (`git push --force`, `--force-with-lease`, `-f`, or any variant) — including to a branch only you have touched.
- Never rewrite existing commit history: no `git commit --amend` on a pushed commit, no `git rebase`, no interactive rebase, no `git filter-branch`, no `git reflog expire`, no `git update-ref -d`.
- New commits append; they never replace, reorder, or drop existing ones.

These are blocked at the tool level in [`.claude/settings.json`](../.claude/settings.json) (`permissions.deny`) — not just documented, refused.

**If a branch falls behind `main`:** merge, don't rebase — `git merge origin/main` (or GitHub's "Update branch" button). This adds a merge commit and is always safe: nothing is rewritten, no force-push required, no PR review comments or CI runs get orphaned.

## Staging — never `git add -A` or `git add .`

Stage only the specific paths you edited, by name. Blanket-staging risks committing stray or uncommitted work that happened to be sitting in the tree. Blocked in `.claude/settings.json` alongside the history rules.

## Branching

Before creating any new branch, update local `main` first: `git fetch origin`, then branch from `origin/main` (or `git checkout main && git pull origin main --ff-only`). Never branch off a stale local `main` — see [OpenSpec Branch Policy](openspec-workflow.md) for the additional rule that applies to `openspec/changes/**`.

## Why

Force-pushing or rewriting published history breaks things that look fine until someone hits them:

- PR review comments become orphaned or hard to re-map to new commits.
- CI check results are tied to a specific SHA; rewriting history invalidates them even if the content is identical.
- Any collaborator (or agent) with a local checkout based on the old commits ends up with a diverged, hard-to-reconcile branch.

A regular merge commit costs one extra line in the log. That's a good trade.
