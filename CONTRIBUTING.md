# Contributing

## Setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements-dev.txt -e .
pre-commit install
```

`pre-commit install` is required on every machine — it is not carried over by `git clone`. Without it, lint/format issues still get caught by CI, but later, on your open PR.

## Workflow

1. Create a branch off `main`.
2. Make your changes.
3. Commit — the pre-commit hook runs Ruff (lint + format) automatically.
4. Push and open a pull request.

`main` is protected:

- Direct pushes are rejected (except for repo admins).
- The PR must pass CI (`ruff check`, `ruff format --check`, `pytest`).
- The PR needs 1 approval from a code owner (see [`.github/CODEOWNERS`](.github/CODEOWNERS)).

## Commits

Use [Conventional Commits](https://www.conventionalcommits.org/) (`feat:`, `fix:`, `chore:`, `docs:`, ...).

## Code style

See [`system/code-style.md`](system/code-style.md).

## Language

Code, comments, and documentation must be in English — see [`system/code-language.md`](system/code-language.md). This applies regardless of what language you use to discuss the work.

## Tests

Add or update tests in `tests/` for behavior you change. Run locally with:

```bash
pytest
```
