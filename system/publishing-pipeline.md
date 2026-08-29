# Publishing Pipeline

Published documents are produced by a three-stage pipeline. Each stage reads only the stage
before it.

```
ruleset AST  ──extract──▶  document.json  ──render──▶  publish/…/<name>_<lang>.<ext>
```

| Path | Written by | Tracked | Edit by hand? |
|---|---|---|---|
| `data/<product>/spec.toml` | a person | yes | **yes — this is the source** |
| `data/<product>/document.json` | `extract` | yes | only for a one-off; `extract` overwrites it |
| `publish/<product>/v<version>/…` | `render` | yes | never |

## The ruleset is pinned

The pipeline reads a clone of the StudCraft ruleset in git-ignored `source/studcraft/`, at
exactly the commit `source/studcraft.lock.json` records. That lock file **is** tracked, and
every build verifies the clone matches it before doing anything.

```bash
python -m publisher.sync --pinned    # restore the clone to the pinned commit — do this
python -m publisher.sync             # clone whatever `main` is now AND rewrite the pin
```

Those two are not interchangeable, and the second is the trap. Without `--pinned`, `sync`
resolves the branch to wherever it is today and overwrites the lock file, so the sheet
silently starts describing a ruleset nobody reviewed. Bumping the pinned ruleset is a
deliberate change: run it, rebuild, and let the `document.json` diff show which lines of the
sheet the new rules changed.

## Two rules follow, and CI enforces both

- **Never edit a generated file to fix a problem in its source.** A wrong line on the sheet
  is fixed in `spec.toml`, not in `document.json` and not in the PDF.
- **Regenerate and commit in the same change.** `python -m publisher.quicksheet build`, then
  commit `data/` and `publish/` together with the spec edit. CI fails on
  `git diff --exit-code` against either.

Reference documentation, not restated here:

- **[`data/SPEC-FORMAT.md`](../data/SPEC-FORMAT.md)** — every key of `spec.toml`, its
  defaults, what fails the build, and how to write a line without misstating the rule it
  cites. **Read this before writing or editing a spec.**
- [`data/README.md`](../data/README.md) — the product directory layout.
- [`publish/README.md`](../publish/README.md) — how a publish path is derived, and why the
  tree is committed.
