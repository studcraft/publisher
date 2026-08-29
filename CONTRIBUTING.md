# Contributing

## Setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements-dev.txt -e .
```

## Workflow

1. Update local `main` (`git fetch origin`, then branch off `origin/main`) and create a branch — see [Git Strategy](system/git-strategy.md).
2. Make your changes. Run `ruff check .`, `ruff format .`, and `pytest --cov` before
   pushing. The coverage floor is enforced on the pull request, not just advised —
   see [Testing](system/testing.md).
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

A pull request that fails the suite does not merge, and neither does one that drops coverage
below its floor. Both run inside `lint-and-test`, the required check on `main`.

```bash
pytest              # fast, and works on a subset: pytest tests/test_sync.py
pytest --cov        # adds the coverage report and the floor, as CI runs it
```

See [Testing](system/testing.md) for the floor, why it is coverage rather than "did you add
a test", and what the gate does *not* catch.
