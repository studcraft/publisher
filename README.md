# publisher

Turns the [StudCraft](https://github.com/studcraft/studcraft) ruleset into printable
documents — starting with a one-page quick-play sheet — without letting them drift from the
rules they claim to state.

```
ruleset AST  ──extract──▶  document.json  ──render──▶  publish/…/<name>_<lang>.pdf
```

## What it produces today

**[`publish/quicksheet_3x3/v0.2.0draft/quicksheet_3x3_en.pdf`](publish/quicksheet_3x3/v0.2.0draft/quicksheet_3x3_en.pdf)**
— one side of A4, two columns, enough to play the 3-minifigure-per-warband mode with the
ruleset closed. 37 entries citing 32 rules.

## The idea

StudCraft's rules are ~181 numbered rules across 15 documents. A printable summary of them
is easy to write once and impossible to keep true: the day upstream renumbers a rule or
rewrites a threshold, the sheet is quietly wrong and nothing says so.

So every line on the sheet **names the rule it condenses**, and the build resolves that ID
against a pinned copy of the ruleset. A rule that disappears fails the build. A rule that
changes shows up as a diff in a tracked file, before anyone prints anything.

What the build cannot do is check that a sentence *says* what its rule says. That stays
human, and the tooling is arranged to make it easy — every entry records the document and
line it came from — rather than to pretend otherwise. It has caught a real error already:
an early draft stated the damage states as "Healthy → Wounded → Down" when the rule reads
**Operational → Wounded → Dead**.

## Try it

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt -e .

python -m publisher.sync --pinned          # fetch the ruleset at its pinned commit
python -m publisher.quicksheet build       # extract, then render
```

The result lands in `publish/`. Building twice gives byte-identical files.

## The three stages

Each reads only the one before it, and each is a separate command.

| | Command | Reads | Writes |
|---|---|---|---|
| 1 | `extract` | pinned ruleset + `spec.toml` | `data/<product>/document.json` |
| 2 | `render` | `document.json` **only** | `publish/<product>/v<version>/…` |
| — | `build` | both stages | both |

The middle stage earns its place by being a real file rather than a variable:

- **It is the review surface.** `git diff data/quicksheet_3x3/document.json` shows which
  lines of the sheet a ruleset bump changed — not just that the PDF is different.
- **It carries its own presentation.** Page size, margins, columns and type sizes live in
  the document, so changing the page is editing data, not editing Python.
- **It is enough on its own.** Copy it to an empty directory with no repository, no ruleset
  and no spec, run `render`, and you get the same PDF byte for byte. A test deletes the
  clone and the lock file to prove it.

Renderers are a registry keyed by format, so a second output target never touches stages 1
and 2.

## Repository layout

```
data/<product>/spec.toml        authored — what the document says (SPEC-FORMAT.md)
data/<product>/document.json    generated — what a renderer consumes
publish/<product>/v<version>/   generated — the artefacts, versioned and committed
src/publisher/                  sync (the ruleset pin) and quicksheet (the pipeline)
source/studcraft/               the ruleset clone, git-ignored, pinned by a tracked lock file
system/                         project rules, one topic per file
openspec/                       change proposals
```

Generated files are committed on purpose. CI regenerates them and fails on
`git diff --exit-code`, so a document can never drift from the ruleset it names, and
"which sheet did we publish for ruleset 0.2.0 Draft" is answerable from the repository
alone.

## Guarantees, and what backs them

| Guarantee | What enforces it |
|---|---|
| The sheet cannot cite a rule that no longer exists | `extract` fails, naming the ID and its section |
| A build cannot use an unreviewed ruleset | Builds verify the clone against a tracked lock file |
| An upstream format change cannot thin the sheet silently | The parser's output is schema-checked on load |
| The sheet never spills to a second page | The renderer shrinks to fit, then fails |
| Two builds give identical bytes | Fixed dates and a PDF core font; CI builds twice and compares |
| Committed data and artefacts are current | CI regenerates and fails on any diff |
| Code the suite does not reach cannot land | A coverage floor inside the required check |

## Writing or changing a sheet

Edit `data/<product>/spec.toml`, run `python -m publisher.quicksheet build`, and commit the
regenerated files with it.

**[`data/SPEC-FORMAT.md`](data/SPEC-FORMAT.md)** is the reference: every key, every default,
everything that fails the build, and how to write a line without misstating the rule it
cites. Read it before writing one.

An entry takes one of three shapes, chosen by how it is read at a table — a statement to
read, a lookup to scan, or a sequence to follow — because a player looking up a dice result
should find it by scanning a column, not by reading a sentence and pulling the numbers out.

## Adding a product

Create `data/<name>/spec.toml` and run `extract` against it. Nothing under
`src/publisher/quicksheet/` changes for a new document of the same shape; a new *output
format* is a new renderer in `src/publisher/quicksheet/render/`.

## Development

Python 3.9+. [Ruff](https://docs.astral.sh/ruff/) for lint and formatting, pytest for tests.

```bash
ruff check . && ruff format --check . && pytest --cov
```

Tests are a hard constraint, not a habit: a pull request that fails the suite does not
merge, and neither does one that drops coverage below its floor. Both run inside the
required check. See [Testing](system/testing.md).

See [CONTRIBUTING.md](CONTRIBUTING.md) for the workflow, and [`system/`](system/) for the
project rules — [git strategy](system/git-strategy.md) (history only grows; never
force-push or rebase), [code style](system/code-style.md), the
[publishing pipeline](system/publishing-pipeline.md), and the
[OpenSpec branch policy](system/openspec-workflow.md).

## Licence

[MIT](LICENSE).
