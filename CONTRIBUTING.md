# Contributing

## Setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements-dev.txt -e .
```

## Workflow

1. Update local `main` (`git fetch origin`, then branch off `origin/main`) and create a branch — see [Git Strategy](system/git-strategy.md).
2. Make your changes. Run `ruff check .`, `ruff format .`, and `pytest` before pushing.
3. If you changed anything under `data/`, run `python -m publisher.quicksheet build` and
   commit the regenerated `data/` and `publish/` files with it — CI fails if they are stale.
   See [Publishing Pipeline](system/publishing-pipeline.md).
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

See [`system/language.md`](system/language.md).

## Tests

Add or update tests in `tests/` for behavior you change. Run locally with:

```bash
pytest
```
