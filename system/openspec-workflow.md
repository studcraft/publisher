# OpenSpec Branch Policy

**Hard rule: never create or modify OpenSpec change proposals (`openspec/changes/**`) directly on `main`.** Always work on a branch and open a PR — see [CONTRIBUTING.md](../CONTRIBUTING.md). No exceptions, including for repo admins.

This applies to every step of the OpenSpec lifecycle: `openspec new change`, editing artifacts (`proposal.md`, `design.md`, `tasks.md`, delta specs), implementing tasks, and archiving.

Enforcement: the `openspec-branch-gate` job in CI (`.github/workflows/ci.yml`) runs on every push to `main` and fails loudly if `openspec/changes/**` was touched by that push. It cannot block the push itself — GitHub branch protection lets repo admins push directly to `main` (see [`.github/CODEOWNERS`](../.github/CODEOWNERS) and the repo's branch protection settings). This rule is the actual gate: an agent working in this repo must treat it as non-negotiable and always branch before touching `openspec/changes/**`.
