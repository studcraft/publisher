# `data/`

One directory per published product. Each holds that product's two tracked files:

```
data/<product>/
  spec.toml        authored — what the document says, every line anchored to a rule ID
  document.json    generated — what a renderer consumes, content plus page parameters
```

Rendered outputs go to [`publish/`](../publish/), on a path derived from the document.

**The `spec.toml` format is documented in [SPEC-FORMAT.md](SPEC-FORMAT.md)** — every key,
every default, everything that fails the build, and how to write a line without misstating
the rule it cites. Read it before writing or editing one.

Today there is one: [`quicksheet_3x3/`](quicksheet_3x3/), the one-page A4 quick-play sheet
for the 3-minifigure-per-warband mode.

## Why both files are tracked

`spec.toml` is the source a person edits. `document.json` is generated from it and the
pinned ruleset — and it is tracked anyway, because it is the review surface:

- A ruleset bump arrives as a readable diff. `git diff data/<product>/document.json` shows
  which lines of the sheet changed, not just that the PDF is different.
- A hand edit to `document.json` is a reviewable change rather than something the next
  build erases silently.
- CI re-extracts and fails when the committed document differs from a fresh one, so the
  data can never drift from the ruleset it names.

Rendered outputs are tracked too, but they live under `publish/` rather than here — see
[`publish/README.md`](../publish/README.md).

## Working with a product

```bash
python -m publisher.quicksheet extract --data data/quicksheet_3x3
python -m publisher.quicksheet render  --data data/quicksheet_3x3 --format pdf
python -m publisher.quicksheet build   --data data/quicksheet_3x3   # both
```

`--data` defaults to `data/quicksheet_3x3`, so plain `build` does the above.

`--data` names the directory; the file names inside it are fixed. That is what stops one
product's `spec.toml` being paired with another's `document.json`.

## Adding a product

Create `data/<product>/spec.toml` and run `extract` against it. Nothing under
`src/publisher/quicksheet/` needs to change for a new document of the same shape; a new
*output format* is a new renderer in `src/publisher/quicksheet/render/`.
