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

## Products

Two, and they share every stage but the last:

- **`quicksheet_3x3`** — the printed quick sheet. `render --format pdf` writes a PDF.
- **`rules_web`** — the ruleset as web pages. `render` writes one JSON bundle holding every
  page, which a fourth stage publishes to WordPress.

```bash
python -m publisher.quicksheet build     # the sheet
python -m publisher.rules_web build      # the web edition
```

## The fourth stage: WordPress

```
… ──render──▶ publish/rules_web/v<version>/rules_web_en.wp.json ──push──▶ WordPress
                                                                ──promote──▶ public
```

`push` reads the bundle and **nothing else** — not the ruleset, not the spec. The bytes
reviewed in a pull request are the bytes the site receives. It writes every page `private`:
the real URL, the real hierarchy, visible to editors only. `promote` sends one thing per
page, a status, so making a publication public cannot introduce a change nobody reviewed.

```bash
python -m publisher.wp push       # stage as `private`
python -m publisher.wp menu       # write the site's navigation menu
python -m publisher.wp promote    # make public
```

`menu` is the one command that writes something other than the pages: a `wp_navigation` post
holding **Rules** and the ruleset's systems in reading order. Without it a block theme
renders a Page List of all 194 pages, alphabetically. It writes no template and no theme
file — those stay the site owner's.

Both read `WP_BASE_URL`, `WP_USER` and `WP_APP_PASSWORD` from the environment; the local
harness in [`tools/wordpress-local/`](../tools/wordpress-local/README.md) writes all three
into a git-ignored `.env`. Test against that, never against a live site.

**Nothing is installed on WordPress.** Pages, the REST API, application passwords and the
`/%postname%/` permalink structure are all core. A change that needs a plugin is a finding
about the design, not a missing step.

**WordPress is the last generated stage, so the rule below extends to it unchanged.** An
editor who fixes a typo in wp-admin loses it at the next `push`, silently — `push` overwrites
title and content and makes no attempt to detect a human edit, because detecting one would
invite treating WordPress as a source. Editors review while it is `private` and report; the
fix goes in `spec.toml` or upstream in the ruleset.

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
- **Regenerate and commit in the same change.** `python -m publisher.quicksheet build` and
  `python -m publisher.rules_web build`, then commit `data/` and `publish/` together with the
  spec edit. CI fails on `git diff --exit-code` against either. A ruleset bump touches both
  products, so build both.

Reference documentation, not restated here:

- **[`data/SPEC-FORMAT.md`](../data/SPEC-FORMAT.md)** — every key of `spec.toml`, its
  defaults, what fails the build, and how to write a line without misstating the rule it
  cites. **Read this before writing or editing a spec.**
- [`data/README.md`](../data/README.md) — the product directory layout.
- [`publish/README.md`](../publish/README.md) — how a publish path is derived, and why the
  tree is committed.
