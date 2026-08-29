## Why

StudCraft's rules live in `studcraft/docs/` as ~181 numbered rules across 15 documents. A
group that wants to play the simplest mode — 3 minifigures per warband, last warband
standing — has no way to do it without the full ruleset open on a screen. There is no
printable reference for that mode, and hand-writing one guarantees it drifts from the rules
the moment upstream changes.

`publisher` already clones the ruleset (`python -m publisher.sync`). This change turns that
clone into a printable artefact whose every line is anchored to a rule ID, so the build
fails loudly when a rule it depends on disappears.

## What Changes

- **Pin the ruleset.** `publisher.sync` also writes a tracked lock file recording the repo,
  requested revision, resolved commit SHA, and the ruleset version read from the docs
  headers. Builds read the pinned commit; bumping it is a reviewed PR.
- **New `publisher.quicksheet` package, built as three separable stages.**

      ruleset AST  ->  document.json  ->  renderer  ->  output

  `extract` reads the pinned clone through upstream's own `scripts/parse_ruleset.py --json`
  and writes `document.json`. `render` reads only that file. `build` runs both.
- **`document.json` is the editable middle stage, and it is tracked in git.** It carries the
  content *and* the presentation parameters — page size, margins, column count, type sizes —
  so changing the page is editing data, not editing Python. Being tracked is what makes it a
  review surface: `git diff data/quicksheet_3x3/document.json` shows exactly which lines of
  the sheet a ruleset bump changed. A hand-edited document renders to any format without the
  ruleset present.
- **Renderers are a registry keyed by format.** `--format pdf` today; adding a second target
  never touches the two stages before it.
- **New tracked `publish/` tree.** Rendered artefacts go to
  `publish/<product>/v<ruleset version>/<product>_<language>.<ext>`, a path derived from the
  document rather than chosen by the caller. Two languages, two ruleset versions, or two
  formats can never collide. The tree is committed, so "which PDF did we publish for ruleset
  0.2.0 Draft" is answerable from the repository alone.
- **New `data/<product>/` layout.** Each published product keeps its two tracked files in
  one directory: `spec.toml` (authored — an ordered list of sections, every line carrying
  the rule ID it condenses) and `document.json` (generated). One `--data` flag names the
  directory, so a spec can never be paired with another product's document. This change
  ships one product, `data/quicksheet_3x3/`.
  The generator does not write rules text — it verifies that each cited ID resolves in the
  pinned ruleset and fails the build if one is gone.
- **Glossary highlighting.** The ruleset's 47 defined terms are set in bold wherever they
  appear on the sheet, so a reader can see which words carry an exact meaning. Terms are read
  from the ruleset, identified by the glossary's heading rather than its filename.
- **Byte-reproducible output.** Two builds of the same commit produce identical PDF bytes,
  asserted by a test and again in CI.
- **New CI job.** Sync; re-extract in place and fail if `git diff` shows the committed
  document changed; render and fail the same way on `publish/`; render again elsewhere and
  compare bytes; upload the tree. A stale committed document or publication is a build
  failure: both must always match what they claim to come from.
- New exact-pinned runtime dependency: `fpdf2`. `publisher` has had none until now.

Not breaking: nothing existing changes behaviour. `publisher.sync` gains an output file.

### Non-goals

Deliberately out of scope, each its own later proposal:

- **Adapters** as a registry. There is one product here (the 3v3 sheet), so there is one
  extractor. The renderer side *is* a registry, because that is the seam a second output
  target needs; the extractor side is not, because a second product does not exist yet and
  designing its abstraction blind is how you get the wrong one.
- Any output format other than PDF (HTML, PNG). The registry makes adding one cheap; this
  change does not add one.
- Publishing to external media — WordPress or otherwise. This change produces a file; it
  distributes nothing.
- A card deck, or any multi-page or multi-item artefact. `Document` holds one page's worth
  of sections; a deck needs a repeated-item shape this does not have.
- Melee rules. They do not fit alongside flow, movement, shooting and damage on one side of
  A4, and a partial melee section is worse than none.
- Images. The two images in the ruleset belong to rules outside this sheet's scope.

## Capabilities

### New Capabilities

- `ruleset-pin`: recording and reading the exact upstream ruleset commit and version a build
  was produced from, so any build can be reproduced and any output can be traced to its
  source.
- `quicksheet`: producing a one-sided A4 quick-play PDF for the 3v3 mode from the pinned
  ruleset and a curated, rule-ID-anchored specification file.

### Modified Capabilities

None. `openspec/specs/` is empty; this is the first specified capability in the repo.

## Impact

**Code**

- `src/publisher/sync.py` — extended to write the lock file. Existing behaviour unchanged.
- `src/publisher/quicksheet/` — new package: `index.py` (ruleset AST), `model.py`
  (`Document`, `Page`, `Section`, `Line`, `Source`), `extract.py` (AST + spec -> document),
  `document.py` (read/write `document.json`), `render/` (format registry + `pdf.py`),
  `cli.py` (`extract`, `render`, `build`, `draft`).
- `data/quicksheet_3x3/spec.toml` and `data/quicksheet_3x3/document.json` — new tracked
  files. The spec is the authored source; the document is the generated, reviewable middle
  stage. `data/README.md` documents the layout for the next product.
- `publish/quicksheet_3x3/v0.2.0draft/quicksheet_3x3_en.pdf` — the published artefact,
  tracked. `publish/README.md` documents the naming scheme and its one weakness.
- `src/publisher/quicksheet/publish.py` — derives every publish path from the document.
- `tests/` — new tests for the index, the extractor (golden fixtures), and byte-identical
  rendering.
- `source/.gitignore` — un-ignore the lock file so it is tracked.
- `.github/workflows/ci.yml` — new `quicksheet` job.

**Dependencies**

- `fpdf2`, pinned exactly. Chosen over `weasyprint` because it is a pure-Python wheel with
  no system packages, so the install is identical locally and on `ubuntu-latest`;
  `weasyprint` pulls in Cairo/Pango, whose versions affect output bytes and would break the
  reproducibility assertion.
- `tomllib` is stdlib from Python 3.11; the project targets 3.9, so `tomli` is needed as a
  conditional dependency for the spec file.

**External**

- Depends on upstream's `scripts/parse_ruleset.py --json` output format. The index validates
  that output on load, so an upstream format change fails the build rather than silently
  producing a wrong sheet.
- Runs a script from the cloned repository. The clone is a repository the project owns and
  the commit is pinned and reviewed.

**Not affected**

Everything else. No existing test, workflow, or module changes behaviour.
