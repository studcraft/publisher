# Code Style

Python code follows [PEP 8](https://peps.python.org/pep-0008/), enforced automatically by [Ruff](https://docs.astral.sh/ruff/) — do not hand-format or debate style in review, run the tool.

- **Formatting**: `ruff format` (Black-compatible). Line length 100.
- **Linting**: `ruff check`, rule sets `E`, `F`, `I` (import sorting), `UP` (pyupgrade). Configured in `pyproject.toml`.
- **Naming**: `snake_case` for functions/variables/modules, `PascalCase` for classes, `UPPER_CASE` for constants — standard PEP 8.
- **Type hints**: required on public function signatures (parameters and return type).
- **Docstrings**: required on public modules, classes, and functions. One-line summary; expand only when the behavior isn't obvious from the signature.
- **Language**: English only — see [Language](language.md).

Both checks (`ruff check .` and `ruff format --check .`) run in CI. Neither is optional; a PR that fails either does not merge (see [CONTRIBUTING.md](../CONTRIBUTING.md)).
