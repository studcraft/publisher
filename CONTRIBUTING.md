# Contributing

## Setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements-dev.txt -e .
```

## Workflow

1. Create a branch off `main`.
2. Make your changes. Run `ruff check .`, `ruff format .`, and `pytest` before pushing.
3. Push and open a pull request.

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
