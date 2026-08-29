## Why

A reviewer used the published 3v3 sheet and reported that it works, but reads "more like a
compact rules summary than a quick reference". Their conclusion, which this change adopts
verbatim: **do not add content — make the existing content faster to find.**

The concrete problem is that everything on the sheet is a sentence. A player looking up a
dice result reads "Attack Roll, per die: 4-6 scores one Impact, 1-3 nothing" and extracts
two numbers from it. A player checking an obstacle reads three separate sentences and
compares their thresholds. At a table, mid-turn, that is slow — and it is slow because of
how the sheet is built, not because of what it says: the document model has exactly one
shape, a string of prose, so prose is the only thing a renderer can draw.

## What Changes

- **An entry takes one of three shapes**, chosen by how it is read rather than by how much
  it says:
  - `text` — a statement to read. What every entry is today.
  - `outcome` — a lookup to scan: rows of condition and result, aligned into a column.
  - `steps` — a sequence to follow, drawn as a flow.
- **An entry may carry a `label`** — the word a player's eye searches for (`Forward`,
  `Range`, `Damage Roll`), set in bold and apart from its value, so finding it does not
  mean reading the entry.
- **The renderer draws all three.** Lookup results share one column across every row of an
  entry, which is what makes them scan rather than read. Labelled sequences and lookups
  indent under their label.
- **A lookup row may cite its own rule.** The first attempt at this change lost two
  citations: the three obstacle thresholds are three rules (`INF-006`, `INF-007`,
  `INF-008`), and an entry that could cite only one printed a table whose other rows were
  anchored to nothing. An entry now prints every rule it and its rows cite, in one place.
- **The 3v3 sheet is rewritten to use them**, following the reviewer's specific
  recommendations: the attack roll, damage roll, geometry check, component states and
  obstacle thresholds become lookups; the shooting sequence, the damage resolution, the
  pre-game setup and the end of turn become sequences; movement distances and costs become
  labelled values.

Not breaking: `text` remains the default shape and every existing entry keeps working.

### Non-goals

- **No new rules.** The reviewer was explicit that content coverage is good and no gaps are
  apparent; this change would be wrong to widen scope on the back of that. Nothing is added.

  One rule is **removed**: `FLOW-010`, "end condition says when the game stops; victory
  condition says who wins". The reviewer questioned whether a player needs that conceptual
  distinction mid-game and suggested stating this scenario's answer directly instead, which
  the sheet now does. The general principle is gone; what a player needs to know is not.
  32 rules remain cited, all of them as before.
- No change to the pipeline's stages, the publish layout, or the reproducibility guarantees.
- No markup inside `text`. A shape is a field, not a syntax to parse — the same reason page
  parameters are data rather than constants.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `quicksheet`: how an entry is expressed and drawn. The requirement that content be
  anchored to rule IDs gains the shapes an anchored entry may take; a new requirement covers
  what the renderer must do with them.

## Impact

**Code**

- `src/publisher/quicksheet/model.py` — `Outcome`; `Line` gains `label`, `outcomes`,
  `steps` and a `kind`; JSON round-trip omits the shapes an entry does not use.
- `src/publisher/quicksheet/extract.py` — reads and validates the shapes; rejects an entry
  with none or more than one.
- `src/publisher/quicksheet/render/pdf.py` — wrapping takes segments that may be forced
  bold, so a label is bold without being a glossary term; drawing is row-based, with a
  second column for lookup results.

**Data**

- `data/quicksheet_3x3/spec.toml` rewritten; `document.json` and the published PDF
  regenerated.

**Documentation**

- `data/SPEC-FORMAT.md` — the shapes, when to use each, and what fails.

**Not affected**

The ruleset pin, the publish path scheme, byte-reproducibility, and the CI gates.
