## Context

A reviewer played from the published 3v3 sheet and reported it as working but slow to
consult: "more like a compact rules summary than a quick reference". Their recommendation was
explicit — do not add content, convert roughly 15–20% of the explanatory prose into visual
structure.

The sheet could not do that. `Line` had one content field, `text`, so a renderer could only
ever draw a paragraph. Every dice table, every threshold list and every procedure was a
sentence containing numbers, and finding an answer meant reading one.

## Goals / Non-Goals

**Goals:**

- A player finds a dice result, a threshold or a cost by scanning, not by reading.
- The same 33 rules, the same page, the same reproducibility.
- Shapes expressed as data, so a second product gets them for free.

**Non-Goals:**

- New rules. The reviewer found no coverage gaps and this change adds none.
- Markup inside `text`. See *Decisions*.
- A general table type. See *Decisions*.

## Decisions

### Three shapes, not markup

`text`, `outcome`, `steps` — three fields, exactly one per entry.

*Alternative considered:* a mini-markup inside `text` (`**bold**`, `|` for columns) parsed by
the renderer. Rejected for the same reason page parameters are fields rather than constants:
markup is a language to define, parse, escape and get wrong, and it hides structure from
everything except the renderer that parses it. A field is inspectable in `document.json`, and
a second renderer gets the structure rather than a string it must re-parse.

*Alternative considered:* one general `table` with arbitrary columns. Rejected as more than
the problem needs. Every case the reviewer raised is two columns — a condition and what it
produces — and a two-column shape can be aligned automatically. An n-column table cannot,
without column-width rules that would be the beginning of a layout language.

**Exactly one shape per entry**, enforced. Allowing two would raise a question with no good
answer: does the lookup come before or after the sentence, and is the sentence part of the
label or of the rows? Two entries answer it clearly.

### Alignment is the requirement, not decoration

A lookup computes one column position from the widest condition it contains, and every
result starts there. Results that each began where their own condition ended would read as
sentences with extra spaces, which is what the shape exists to stop. The renderer test
asserts on drawn x positions rather than on the presence of text, because the alignment *is*
the feature.

The column is per entry, not per section: `Str >= Res` and `1-3` want different widths, and
forcing them to share one would indent short conditions away from their label for no gain.

### Forced-bold segments

A label must be bold without being a glossary term. Wrapping previously took a string and
found glossary terms in it; it now takes segments, each either forced bold or searched for
terms. That keeps one measuring-and-drawing path — bold Helvetica is wider than regular, and
a second path would eventually measure in one style and draw in another.

### Labels carry the rule ID, rows do not

On a lookup or a sequence the label line carries `(RULE-001)`; the rows stay clean. On an
unlabelled lookup the ID attaches to the first result, because it has to go somewhere and a
row is the only thing there. Traceability is unchanged: every entry still prints its ID.

## Risks / Trade-offs

- **The reviewer asked for fewer words; more structure can mean more lines.** → Watched
  directly: the sheet is still one page, and the auto-fit still chose a body size in the
  same range. If structure ever costs more than it buys, the single-page assertion fails the
  build rather than letting the sheet quietly grow.
- **A label invites restating what the value already says** (`Range: Range = …`). → Nothing
  enforces this; it is an authoring habit, called out in `SPEC-FORMAT.md`.
- **Three shapes are three things to keep working in every future renderer.** → Accepted.
  The alternative was a string every renderer re-parses, which is the same cost paid worse.
- **Column alignment assumes conditions are short.** A long condition pushes results far
  right and leaves little room. → The wrap still works, only tighter; and a long condition is
  a sign the row should have been a statement.

## Open Questions

- Whether the sequence separator should stay `>` or become something heavier. `>` is
  latin-1, which the PDF core font needs; anything else is a substitution.
- Whether column balancing should split *within* a section rather than only between
  sections. The two columns are uneven because a section is the smallest unit that can move,
  which is a layout limit rather than a content one.
