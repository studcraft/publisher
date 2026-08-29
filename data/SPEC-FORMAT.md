# `spec.toml` reference

The one file in this pipeline a person writes. Everything downstream — `document.json`, the
rendered PDF — is generated from it and the pinned ruleset.

```
spec.toml  ──extract──▶  document.json  ──render──▶  publish/…/<name>_<lang>.pdf
   you                      generated                     generated
```

Unknown keys are rejected everywhere, at every level. A misspelled `intro` that was silently
ignored would look exactly like a renderer that does not print intros, which is a far more
expensive thing to debug than a failed build.

---

## Top level

| Key | Required | Default | Meaning |
|---|---|---|---|
| `language` | **yes** | — | Language tag. Becomes part of the publish filename, so translations cannot collide. |
| `title` | no | `"StudCraft Quick Sheet"` | Printed at the top of the page. |
| `name` | no | the directory name | Product identifier. Becomes part of the publish path. Leave it out so it cannot drift from the directory. |
| `[page]` | no | see below | Presentation parameters. |
| `[[section]]` | **yes**, ≥1 | — | The content. |

```toml
language = "en"
title = "StudCraft — 3v3 Quick Sheet"
```

---

## `[[section]]`

One headed group. Order in the file is order on the page.

| Key | Required | Default | Meaning |
|---|---|---|---|
| `id` | **yes** | — | Stable identifier. Appears in error messages, so make it say something. |
| `heading` | **yes** | — | Printed heading. |
| `intro` | no | `""` | One line of context under the heading, printed in italic. |
| `[[section.line]]` | **yes**, ≥1 | — | The lines. |

```toml
[[section]]
id = "movement"
heading = "Movement"
intro = "Every move costs 1 AP."
```

A section with a heading and no lines is a mistake, not an empty column — it fails.

---

## `[[section.line]]`

One printed line. Exactly two kinds, and a line must be one or the other.

| Key | Required | Meaning |
|---|---|---|
| `text` | **yes** | What the sheet prints. Written by you, condensed for a narrow column. |
| `rule` | one of the two | The rule ID this line condenses. |
| `authored` | one of the two | `true` for a line that comes from no rule. |

### Rule-anchored — almost every line

```toml
[[section.line]]
rule = "INF-002"
text = "Forward: up to 4 UB (12 studs). 1 AP."
```

`extract` resolves `rule` against the pinned ruleset and **fails the build if the ID is
gone**. It then attaches that rule's source document and line number to the document, so any
printed line can be checked against what it claims to say. The rule ID is printed on the
page in parentheses.

The generator never writes the text. Its only jobs here are: does the ID resolve, where does
it live, and fail if it does not.

### Authored — the scenario, and nothing else

```toml
[[section.line]]
authored = true
text = "Three minifigures per warband. Two or more players."
```

For content the ruleset deliberately leaves open — scenario definition (`FLOW-013`). These
print in italic and without a rule ID, and the page footer says what italic means.

Setting both `authored = true` and `rule` fails: the `rule` would be silently ignored, and a
line that looks anchored but is not is the worst outcome available.

---

## `[page]`

Optional. Every key has a default; give only what you are changing. Unknown keys fail.

| Key | Default | Meaning |
|---|---|---|
| `format` | `"A4"` | Label only. Printed in error messages; does not set the size. |
| `width_mm` | `210.0` | Page width. |
| `height_mm` | `297.0` | Page height. |
| `margin_mm` | `10.0` | All four margins. |
| `columns` | `2` | Column count. |
| `gutter_mm` | `6.0` | Space between columns. |
| `header_mm` | `11.0` | Space reserved under the title. |
| `footer_mm` | `6.0` | Space reserved for the provenance line. |
| `title_pt` | `15.0` | Title type size. |
| `footer_pt` | `6.0` | Footer type size. |
| `body_pt` | `[11.0, 10.5, … 6.0]` | Body sizes to try, largest first. The first that fits wins. |
| `heading_ratio` | `1.3` | Heading size, as a multiple of the chosen body size. |
| `line_height_ratio` | `0.425` | Line height, as a multiple of body size. |
| `heading_lead_ratio` | `0.42` | Space above a heading. |
| `section_gap_ratio` | `0.3` | Space between sections. |

`width_mm` and `height_mm` set the real size; `format` is only a label. Swap them for
landscape:

```toml
[page]
width_mm = 297.0
height_mm = 210.0
columns = 3
```

**`body_pt` is how overflow behaves.** A list lets the renderer shrink until the content
fits. A single entry pins the size, and content that does not fit becomes a build failure
instead:

```toml
[page]
body_pt = [10.0]   # this size or nothing
```

Content never spills onto a second page. It either fits or the build fails.

---

## What fails the build

Each of these is a test, not a promise:

- A cited rule ID absent from the pinned ruleset — named, with the section citing it.
- A line with no `text`, or with neither `rule` nor `authored`.
- A line with both `authored = true` and `rule`.
- A section with no `id`, no `heading`, or no lines.
- No sections at all.
- No `language`.
- An unknown key at any level — top, `[page]`, `[[section]]`, `[[section.line]]`.
- Content that does not fit on one page at the smallest `body_pt`.
- A character no PDF core font can print, unless it is in the renderer's substitution table.

---

## Writing lines: the part that is not mechanical

`extract` guarantees the rule you cite **exists**. It cannot guarantee your sentence says
what that rule says. That check is human, and it has failed here before: an early draft
stated the damage states as "Healthy → Wounded → Down" when `DMG-002` reads
**Operational → Wounded → Dead**. Condensing a rule by hand invents plausible wrong words.

So:

1. Bootstrap mechanically, then rewrite. `python -m publisher.quicksheet draft INF-002
   INF-003 …` prints a draft file built from each rule's first paragraph. It is correct and
   unusable at column width — that is the point. Rewrite every line.
2. Read the rule before you write the line. The document records `doc` and `source_line` for
   exactly this: `data/<product>/document.json` tells you where to look.
3. Cite the rules a line depends on. Three gaps in the first draft of this sheet were all
   the same shape: a rule that compares two quantities, cited without the rules that define
   them (`DMG-013` without `DMG-003` and `WPN-021`).

## After editing

```bash
python -m publisher.quicksheet build
git diff data/<product>/document.json    # exactly which lines changed
```

CI fails if the committed `document.json` or `publish/` tree does not match what the spec and
the pinned ruleset produce, so a spec edit without a rebuild cannot merge.
