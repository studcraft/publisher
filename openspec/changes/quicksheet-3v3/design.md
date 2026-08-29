## Context

`publisher` is a small Python repo (Ruff, pytest, `target-version = "py39"`, CI on Python
3.9) with zero runtime dependencies today. `publisher.sync` shallow-clones
`github.com/studcraft/studcraft` into the git-ignored `source/studcraft/`.

Three properties of the ruleset shape this design:

- **"The Model Is The Rules."** StudCraft has no unit profiles and no stat cards — the
  physical LEGO model defines behaviour (weapon length is range, functional muzzles are
  attack dice). The artefact is therefore a *procedure reminder*: sequences, tables, and
  state names. It must never introduce a derived number, because a number on the sheet that
  is not in the ruleset is a rule the sheet invented.
- **Upstream parses itself.** `scripts/parse_ruleset.py --json` prints the whole `docs/` AST
  to stdout: headings, rule IDs, line ranges, and typed blocks (`paragraph`, `list`, `table`,
  `fence`, `quote`, `break`). Table blocks arrive as the raw Markdown pipe lines.
  `scripts/build_index.py` additionally writes `.studcraft/index.json` with per-rule
  `summary`, `cites`, `cited_by`, and `images`. Upstream's docs warn explicitly against a
  second parser drifting from theirs.
- **Rule IDs are stable.** Upstream never renumbers or reuses an ID after removal. Anchoring
  to specific IDs is therefore safe, and a missing ID is a real signal rather than noise.

## The pipeline

    ruleset AST  ->  document.json  ->  renderer  ->  output
      index.py        model/document      render/

Three stages, separable at the command line (`extract`, `render`, `build`). Two properties
justify the split, and both are tested:

- **`render` reads only the document.** The test deletes the clone and the lock file, then
  renders. If the renderer had quietly reached back to the ruleset, that would fail.
- **The document carries its own presentation.** Page size, margins, column count and type
  sizes live in `document.json`, not in renderer constants. Editing the page is editing
  data. A hand-edited document rendered to A4 landscape in three columns is a test, not a
  code change.

### Where the files live

```
data/quicksheet_3x3/
  spec.toml                                        authored,  tracked
  document.json                                    generated, tracked
publish/quicksheet_3x3/v0.2.0draft/
  quicksheet_3x3_en.pdf                            rendered,  tracked
```

One directory per product, named by `--data`. The first version of this put both files at
the repository root, which works for exactly one product and stops working at two. Keeping
the pair together also removes a whole class of mistake: there is no way to run one
product's spec against another's document, because the file names inside the directory are
fixed and only the directory is selectable.

**`document.json` is tracked; `dist/` is not.** The first implementation of this split wrote
the document into `dist/` alongside the PDF, which quietly defeated the point: a file nobody
can diff and the next build overwrites is not a review surface, it is a temporary variable
that happens to touch the disk. Tracking it buys three things:

- A ruleset bump arrives as a readable diff — which sheet lines changed, not just "the PDF
  is different". `git diff data/quicksheet_3x3/document.json`.
- A hand edit is a reviewable change rather than something the next `build` erases silently.
- CI can regenerate it in place and fail on `git diff --exit-code`, so the data file can
  never drift from the ruleset it names.

The alternative — one function from ruleset to PDF, with geometry as module constants — was
what the first implementation did. It made the intermediate representation invisible, so
every new output or layout meant editing Python, and re-rendering meant re-reading the
ruleset. That is the shape this design exists to avoid.

**Renderers are a registry keyed by format**; extractors are not. One product exists, so one
extractor exists. The renderer side is where a second target actually lands, and that seam is
worth building before the second target arrives; the extractor side is not, because designing
that abstraction against a single known consumer designs it blind.

### Publish paths are derived, not chosen

```
publish/<product>/v<ruleset version>/<product>_<language>.<extension>
```

The path comes from the document's `name`, `source.ruleset_version` and `language`. Nothing
about it is an argument, because a published artefact has to be findable from what it *is* —
which sheet, which ruleset version, which language — rather than from whatever directory the
person who ran the command typed. That is what makes the tree pushable to a single source of
truth and comparable across versions without a manifest to keep in sync.

Three collisions the scheme makes impossible, each a test:

- Two languages of one sheet are two files in one version directory.
- A sheet built against a newer ruleset lands beside the old one, never on top of it.
- Every format of one document shares its version directory.

A document recording no name, version or language is refused rather than published to a path
that would collide with something else. The version is slugged to a single token
(`0.2.0 Draft` -> `v0.2.0draft`) so it sorts next to its neighbours and has no separator to
guess wrong; the slug also strips anything that could escape the tree.

**Known weakness, stated rather than hidden:** the directory is keyed on the *ruleset*
version, but the sheet can change without the ruleset changing — a reworded line, a layout
tweak — and those overwrite the previous file in the same directory. Git history is the
record, and reproducible bytes make that diff meaningful. If per-release immutability is ever
needed, the fix is a publication version of its own in the path, not a change to how the path
is derived.

## Goals / Non-Goals

**Goals:**

- One one-sided A4 PDF that is enough to play the 3v3 mode without the ruleset open.
- Every printed line traceable to the rule it condenses, verified at build time.
- Byte-identical output from repeated builds, proven in CI.
- Identical behaviour locally and on `ubuntu-latest`, with no system packages.

**Non-Goals:**

- An adapter registry. See *The pipeline* above for why the renderer side is a registry and
  the extractor side is not.
- Any output format other than PDF; any publishing to an external medium. The registry is
  what makes adding either cheap later.
- Images. Only two rules in the whole ruleset carry images (`CORE-001`, `CMP-018`) and
  neither is on this sheet.
- Melee. See *Decisions*.

## Decisions

### Feed: `parse_ruleset.py --json` only, not `build_index.py`

`parse_ruleset.py` writes nothing and prints to stdout; `build_index.py` writes
`.studcraft/index.json` into the clone as a side effect. For this sheet, the fields
`build_index.py` adds beyond the AST — `summary`, `cites`, `cited_by`, `images` — are not
needed: line text is authored in the spec file, and there are no images.

*Alternative considered:* run both and merge. Rejected as unused complexity plus a write into
a directory the build should treat as read-only. A later product that wants `summary` or
`images` can add it then.

*Invocation:* `subprocess.run([sys.executable, <clone>/scripts/parse_ruleset.py, "--json"], cwd=<clone>)`.

The script resolves `docs/` from **its own location**, not from the working directory: it
inserts its own directory on `sys.path` and imports `DOCS_DIR` from the clone's
`scripts/repo.py`. So the absolute path we hand it is what selects the ruleset, and `cwd`
is not load-bearing — it is set anyway, defensively, so a future upstream change to
cwd-relative resolution does not silently read the wrong tree.

One consequence for tests: pointing the real parser at a fixture `docs/` is impossible, since
it will always read its own repo's `docs/`. The fixture therefore ships a stub
`scripts/parse_ruleset.py` that prints captured JSON in upstream's exact schema. Tests still
exercise the real subprocess path, the schema validation, and the tree walk, without needing
the clone.

### Content: authored lines anchored to rule IDs, not extracted text

`data/quicksheet_3x3/spec.toml` holds the sheet's text. Each line names the rule it condenses:

```toml
[[section]]
id = "movement"
heading = "Movement"

[[section.line]]
rule = "INF-002"
text = "Forward: up to 4 UB. 1 AP per move action, one direction."
```

The generator resolves `rule` against the index, attaches the source document and line
number, and fails if the ID is gone. It never writes the text.

*Alternative considered:* extract the first sentence of each rule body mechanically. Rejected
as the shipping path — rule prose is written for a reference document, not for a two-column
A4, and mechanical extraction produces sentences that are correct but unusable at this
density. It is kept as a `--raw` bootstrap mode for drafting the first version of the spec
file, and its output is expected to be rewritten by hand.

**Fidelity is the real risk here, and it has already bitten once.** The handoff draft that
preceded this proposal stated the component states as "Healthy → Wounded → Down". The actual
rule (`DMG-002`) reads **Operational → Wounded → Dead**. Condensing rules by hand invents
plausible wrong words. Therefore: draft each line with `--raw`, then verify it against
`docs/` line by line. That verification is a task, not a review comment.

### Rule set for the sheet

All IDs below were confirmed present in the pinned clone at
`edd8aa4dfa512eee7662251948586f457c372012`.

| Section | Rules |
|---|---|
| Setup & victory | authored scenario preamble + `FLOW-001`, `FLOW-013`, `FLOW-010` |
| Turn flow | `FLOW-002`, `FLOW-003`, `FLOW-004`, `CORE-006`, `FLOW-007`, `FLOW-009` |
| Movement | `INF-002`, `INF-003`, `INF-004`, `INF-005`, `INF-012`, `INF-006`, `INF-007`, `INF-008`, `MOVE-003`, `MOVE-007` |
| Shooting | `CBT-001`, `CBT-002`, `CORE-009`, `CBT-003`, `WPN-005`, `CBT-004`, `WPN-002`, `CBT-005`, `WPN-006`, `CBT-015` |
| Damage | `DMG-008`, `WPN-021`, `DMG-003`, `DMG-013`, `DMG-014`, `DMG-002` |

Three additions over the original draft, each required for the sheet to be playable. All
three are the same kind of gap: the draft cited a rule that compares two quantities without
citing the rules that define them.

- **`DMG-003` (Geometry Defines Resistance).** `10-weapons.md` states the effect of an Impact
  depends on the target's Resistance *and* the Geometry Check. Without `DMG-003` the damage
  block references a value the sheet never defines.
- **`WPN-021` (Impact Strength).** Found while authoring: `DMG-013` compares Impact Strength
  against Resistance, and `WPN-021` is the only rule that says Impact Strength is muzzle size
  times three. Without it the Geometry Check cannot be performed from the sheet.
- **`CBT-015` (Attacking While Wounded).** With three models per side, Wounded is a common
  state. `INF-012` already covers the movement penalty; `CBT-015` is its shooting counterpart.

`CBT-003` and `CBT-004` from the original map were dropped as duplicates: they restate
`WPN-005` and `WPN-006` respectively, and one line per fact is the whole point of the sheet.

**Melee is excluded.** `12-melee.md` is a full document; a partial melee block on a sheet this
dense would be worse than none, and the whole of it does not fit. This is a deliberate scope
cut, not a page-fit accident.

### Glossary highlighting

The ruleset defines 47 terms in `docs/14-glossary.md`. The renderer sets them in bold
wherever they appear, so a reader can see which words carry an exact defined meaning.

Three decisions make this useful rather than noisy:

- **Found by heading, not filename.** The glossary is the document whose level-1 heading is
  `Glossary`; its level-2 headings that carry no rule ID are the terms. Hardcoding
  `14-glossary.md` would silently lose every highlight the day upstream renumbers it, and a
  silent loss is exactly the failure this project keeps designing against.
- **Case-sensitive.** StudCraft capitalises its defined terms. That is what separates "a Turn
  ends" from "turn the model", and "an Impact lands" from "it may impact". Case-insensitive
  matching would bold "Turn", "Unit", "Impact" and "AP" on nearly every line, which is a page
  of noise rather than a signal. A trailing `s` is allowed so "Impacts" still matches.
- **Longest first.** "Weapon Front Footprint" must win over "Weapon Front", and "Attack Roll"
  over a term sharing its first word.

*Rendering consequence:* a line can no longer be drawn with one `cell` call, because the font
changes mid-line. Text is tokenised into words, each word a sequence of (fragment, is-term)
runs, and drawn run by run. Two properties matter and are tested:

- Wrapping measures each fragment **in the style it will be drawn in** — bold Helvetica is
  wider than regular — so the measured height and the drawn height cannot disagree.
- A word is what whitespace separates, **not** what term matching separates. Splitting on the
  term boundary put a space before every full stop that followed a term ("Priority ."), which
  is what the first working version did.

### `fpdf2` over `weasyprint`

`fpdf2` is a pure-Python wheel: `pip install` only, zero system packages, so the install is
identical locally and on `ubuntu-latest`. `weasyprint` requires
`apt-get install libpango-1.0-0 libpangoft2-1.0-0 …` in the workflow and pulls in Cairo and
Pango, whose versions affect output bytes — which would make the reproducibility assertion a
function of the runner image rather than of our code. For a single two-column page, nothing
`weasyprint` offers is worth that.

`fpdf2` is pinned exactly, because a patch release that changes stream compression or object
ordering changes the output bytes.

### Determinism

Four layers, in the order they can fail:

1. **Source pinned.** `source/studcraft.lock.json` is tracked; builds verify the clone's
   `HEAD` matches it and refuse otherwise. Bumping the pin is a reviewed PR.
2. **Feed validated.** The index schema-checks `parse_ruleset.py --json` output on load, so
   an upstream format change fails loudly instead of yielding a silently thinner sheet.
3. **Extraction pure.** No clock, no network, no randomness; sorted iteration everywhere.
4. **PDF normalised.** Fixed creation and modification dates, fixed producer string, fixed
   document `/ID`, and a PDF core font (Helvetica) so no font file is embedded.

Layer 4 was the one not obviously under our control: `fpdf2` derives the trailer `/ID` from
values that are not all settable. A spike ran before any other implementation work and
**settled it — no normalisation pass is needed.**

Verified recipe, against `fpdf2==2.8.4` on CPython 3.9.6:

```python
pdf = FPDF(orientation="P", unit="mm", format="A4")
pdf.set_creation_date(datetime(2000, 1, 1, tzinfo=timezone.utc))
pdf.set_producer("publisher-quicksheet")
pdf.set_creator("publisher-quicksheet")
pdf.set_title(...)
pdf.set_font("Helvetica", ...)  # PDF core font, nothing embedded
```

Findings:

- `/ID` is derived from the document content, not from a clock or a random source. Two
  separate process invocations produce the same value.
- No `/ModDate` is emitted unless one is set, so there is nothing to pin there.
- Output is byte-identical across `PYTHONHASHSEED=1` and `PYTHONHASHSEED=99999`, so no
  dict-ordering nondeterminism reaches the file.

The exact pin on `fpdf2` is what keeps this true: the guarantee is empirical, verified against
one version, and re-verified by CI on every run.

### Ruleset version from document headers, not git

The clone is shallow (`--depth 1`), confirmed by `git rev-parse --is-shallow-repository`
returning `true`, and carries no tags. So `git describe` cannot supply a version. The docs
already declare one in their header (`**Version:** 0.2.0 Draft`), and every document must
agree — a disagreement is an upstream defect and fails the build.

*Alternative considered:* switch the clone to `--filter=blob:none` so refs and tags come
along. Rejected for now: it changes `sync` behaviour and download size to obtain something
the docs already state.

### Page-fit is a build-time failure, not a silent overflow

`fpdf2` will happily start a second page. The renderer therefore asserts a single page and
fails the build otherwise. A sheet that quietly became two pages is a worse outcome than a
red build, because nobody re-reads a PDF they have already approved.

## Risks / Trade-offs

- **Hand-condensed lines misstate a rule.** → `--raw` bootstrap, then line-by-line
  verification against `docs/` as an explicit task with the rule ID and source line printed
  next to each line being checked. The `DMG-002` error above is the worked example of why.
- **`fpdf2` output is not byte-stable out of the box.** → Spike first, before the rest of the
  implementation. A normalisation pass is the fallback; the library choice is not revisited
  mid-build.
- **Content does not fit one A4 page.** → Most likely risk in the whole change. Mitigated by
  excluding melee up front, and by the single-page assertion turning it into a visible
  failure during authoring rather than a surprise at the end. If it still does not fit, the
  next cut is terrain (`INF-006`/`007`/`008`).
- **Upstream changes `parse_ruleset.py`'s JSON shape.** → Schema validation on load; the
  build fails naming the missing field. The pin means this can only happen on a deliberate
  bump.
- **A hand-edited `document.json` can contradict its own rule anchors.** Nothing re-checks an
  edited line against the rule it cites. → The document records `source.commit`, and every
  line keeps its `rule`, `doc` and `source_line`, so the claim stays checkable. Re-running
  `extract` regenerates from the ruleset and overwrites hand edits, which is the intended
  recovery: hand edits are for layout and one-off outputs, the spec file is for content that
  must stay true.
- **One extractor means a second product may need to generalise it.** → Accepted. `Document`
  is deliberately general (content plus page, no 3v3 in it), so the likely change is a second
  extractor beside the first rather than a rewrite of the model or the renderers.
- **The build runs a script from a cloned repository.** → The clone is a repository this
  project owns, at a commit pinned in a tracked, reviewed file.
- **New runtime dependencies in a repo that had none.** → Two: `fpdf2` (pinned exactly) and
  `tomli` (only for Python < 3.11; `tomllib` is stdlib from 3.11 and the project targets 3.9).

## Open Questions

- **Letter support.** A4 is the default and the only size this change implements. A
  `--page letter` flag is deferred until someone needs it; the layout constants must not be
  written in a way that assumes A4 forever, but no second size is tested here.
- **Should `sheet.json` be an artefact at all?** The extraction stage's output is worth
  asserting on in tests as a golden fixture. Whether it is also written to `dist/` for humans
  to diff is left to implementation — `dist/` is git-ignored, so it costs nothing either way.
