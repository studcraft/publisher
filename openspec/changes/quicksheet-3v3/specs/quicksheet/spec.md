## ADDED Requirements

### Requirement: The ruleset is read through upstream's own parser

The generator SHALL obtain the ruleset structure by running the cloned repository's
`scripts/parse_ruleset.py --json` and consuming its stdout. It SHALL NOT implement its own
Markdown parser for the ruleset.

The parser's output SHALL be validated on load. An output that does not match the expected
shape SHALL fail the build rather than produce a partially populated sheet.

#### Scenario: Index built from the pinned clone

- **WHEN** the generator runs against a valid pinned clone
- **THEN** it exposes a lookup from rule ID to that rule's title, source document, line range,
  and body blocks

#### Scenario: Upstream parser output changes shape

- **WHEN** `parse_ruleset.py --json` returns output missing an expected field
- **THEN** the build fails with an error naming the missing field, and no PDF is written

#### Scenario: Upstream parser fails

- **WHEN** `parse_ruleset.py` exits non-zero or writes invalid JSON
- **THEN** the build fails and surfaces the parser's own error output

### Requirement: Every sheet line is anchored to a rule ID

Sheet content SHALL be authored in a tracked specification file, `spec.toml`, as an ordered
list of sections. Each product's specification file and generated document SHALL live
together in one directory under `data/`, selected as a unit, so that a specification can
never be paired with another product's document. Each section has a heading, an optional authored intro, and a
list of lines. Every line SHALL carry the rule ID it condenses.

The generator SHALL NOT generate rules text. For each line its only jobs are to confirm the
cited rule ID resolves in the pinned ruleset, to attach that rule's source document and line
number for traceability, and to fail the build when the ID is absent.

#### Scenario: A product's files are selected as a unit

- **WHEN** a stage is pointed at a product's data directory
- **THEN** it reads that directory's specification file and writes that directory's document,
  with no way to name one without the other

#### Scenario: All cited rules resolve

- **WHEN** every rule ID cited in the specification file exists in the pinned ruleset
- **THEN** the build proceeds and each output line carries its rule ID and source location

#### Scenario: A cited rule was removed upstream

- **WHEN** the specification file cites a rule ID absent from the pinned ruleset
- **THEN** the build fails with an error naming the missing ID and the section citing it

#### Scenario: Specification file is malformed

- **WHEN** a section is missing a heading, or a line is missing its `rule` or `text` field
- **THEN** the build fails with an error naming the offending section

### Requirement: The sheet covers the 3v3 mode on one side of A4

The generator SHALL produce a single one-sided A4 page laid out in two columns.

Its content SHALL cover setup and victory, turn flow, movement, shooting, and damage. It
SHALL NOT include melee, which does not fit alongside the rest.

Because the ruleset leaves scenario definition open, the warband size of three minifigures
and the "eliminate all opposing models" victory condition SHALL be authored in the
specification file rather than extracted from the ruleset.

Such lines SHALL be visually distinguishable from rules, and the sheet SHALL state how.
They SHALL NOT carry a rule ID, because there is none to carry. They SHALL NOT carry a
literal per-line marker: on a one-page play aid that is a third copy of what the section
heading and its intro already say, and it costs more in noise than it buys in clarity.

The sheet SHALL identify the ruleset version and commit it was generated from.

#### Scenario: Output is exactly one page

- **WHEN** the sheet is built
- **THEN** the resulting PDF has exactly one page, of A4 size

#### Scenario: Content overflows the page

- **WHEN** the specification file contains more content than fits on one A4 page
- **THEN** the build fails with an error rather than emitting a second page or silently
  truncating content

#### Scenario: A scenario choice is not mistaken for a rule

- **WHEN** the sheet contains both an authored scenario line and a rule-anchored line
- **THEN** the authored one prints without a rule ID and in a distinct style, and the page
  states what that style means

#### Scenario: Provenance is printed on the sheet

- **WHEN** the sheet is built from a pinned ruleset
- **THEN** the page shows the ruleset version and the abbreviated commit SHA it was built
  from

### Requirement: Glossary terms are highlighted

The generator SHALL set the ruleset's glossary terms in bold wherever they appear in the
sheet's text, so a reader can tell at a glance which words are defined terms with an exact
meaning and which are ordinary prose.

The terms SHALL be read from the ruleset itself, identified by the glossary document's
heading rather than by its filename, so renumbering that document does not silently drop
every highlight.

Matching SHALL be case-sensitive, because the ruleset capitalises its defined terms and the
lowercase word is ordinary prose. The longest matching term SHALL win. A term SHALL NOT
match inside a longer word.

A ruleset with no glossary SHALL render an unhighlighted sheet rather than fail, and the
build SHALL report how many terms it highlighted.

#### Scenario: Defined terms are set in bold

- **WHEN** a sheet line contains a term the ruleset's glossary defines
- **THEN** that term is drawn in bold and the surrounding prose is not

#### Scenario: The lowercase word is not the defined term

- **WHEN** a line contains "Turn" as the defined term and "turn" as an ordinary verb
- **THEN** only the capitalised one is highlighted

#### Scenario: The longest term wins

- **WHEN** a line contains a term that has a shorter glossary term as its prefix
- **THEN** the whole longer term is highlighted, not just its prefix

#### Scenario: A term inside a longer word is not that term

- **WHEN** a line contains a longer word that begins with a glossary term
- **THEN** nothing in that word is highlighted

#### Scenario: Punctuation stays attached

- **WHEN** a highlighted term is immediately followed by punctuation
- **THEN** the punctuation is drawn against the term with no space inserted before it

#### Scenario: Ruleset without a glossary

- **WHEN** the ruleset has no glossary document
- **THEN** the sheet is rendered without highlighting and the build reports zero terms

### Requirement: The build is byte-reproducible

Two builds of the same specification file against the same pinned ruleset commit SHALL
produce byte-identical PDF files, on the same machine and across machines.

The extraction stage SHALL be a pure function: no clock, no network, no randomness, and
deterministic ordering of any iteration over unordered collections.

The PDF SHALL be emitted with a fixed creation date, a fixed modification date, a fixed
producer string, a fixed document identifier, and a PDF core font, so that no varying value
reaches the output.

#### Scenario: Repeated build produces identical bytes

- **WHEN** the sheet is built twice into different output directories from an unchanged
  working tree
- **THEN** the two PDF files are byte-identical

#### Scenario: Rebuild after a rules change differs

- **WHEN** the pinned commit is bumped to a ruleset in which a cited rule's content changed
- **THEN** the rebuilt PDF differs from the previous one

### Requirement: The pipeline has a separable, editable middle stage

The generator SHALL be three separable stages: reading the ruleset into a document, writing
that document to a file, and rendering that file to an output.

The document file SHALL carry both the content and the presentation parameters — page size,
margins, column count and type sizes — so that changing the page is editing data rather than
editing code.

The document file SHALL be written to a tracked path inside its product's `data/`
directory, separate from the directory rendered outputs go to, so that a change to it is
reviewable. CI SHALL fail when regenerating the document changes the committed file.

The rendering stage SHALL read only the document file. It SHALL NOT read the ruleset, the
specification file, or the lock file.

Renderers SHALL be selected by an output format name from a registry, so that adding a
format does not modify the stages before it.

#### Scenario: Extracting stops at the document

- **WHEN** the extract stage runs
- **THEN** the document file is written and no rendered output is produced

#### Scenario: The document does not live among the rendered outputs

- **WHEN** a build writes both the document and a rendered output
- **THEN** the document is at its own tracked path and the render directory holds only the
  rendered file

#### Scenario: A stale committed document fails CI

- **WHEN** the committed document differs from one freshly extracted from the pinned ruleset
- **THEN** CI fails, naming the command that regenerates it

#### Scenario: Rendering needs nothing but the document

- **WHEN** the document file exists and the ruleset clone and lock file have been deleted
- **THEN** rendering succeeds

#### Scenario: A hand-edited document changes the output

- **WHEN** a person edits the document's page parameters and renders again
- **THEN** the output reflects the edit, with no change to any code and no re-extraction

#### Scenario: The document round-trips without loss

- **WHEN** a document is written and read back
- **THEN** the result equals the original

#### Scenario: A misspelled parameter is rejected

- **WHEN** an edited document contains a key the page does not define
- **THEN** reading it fails, naming the unknown key, rather than ignoring it

#### Scenario: An unknown format names what exists

- **WHEN** rendering is asked for a format with no registered renderer
- **THEN** it fails, listing the formats that are registered

#### Scenario: Both stages are reproducible

- **WHEN** extract and render each run twice from unchanged inputs
- **THEN** both document files and both rendered outputs are byte-identical

### Requirement: Rendered artefacts are published on a derived path

A rendered artefact SHALL be written to a path derived from the document — its product name,
its ruleset version, and its language — under a publication root:

    <root>/<name>/v<ruleset version>/<name>_<language>.<extension>

The caller SHALL choose only the root. Every other part SHALL come from the document, so
that the tree can be pushed to a single source of truth and compared across versions.

A document that records no name, no ruleset version, or no language SHALL be refused rather
than published to a path that could collide with another artefact.

The published tree SHALL be tracked, and CI SHALL fail when re-rendering changes it.

#### Scenario: The path states what the artefact is

- **WHEN** a document named `quicksheet_3x3`, in English, from ruleset version `0.2.0 Draft`
  is rendered to PDF
- **THEN** it is written to `<root>/quicksheet_3x3/v0.2.0draft/quicksheet_3x3_en.pdf`

#### Scenario: Two languages do not collide

- **WHEN** the same sheet is rendered in two languages
- **THEN** they are two files in the same version directory

#### Scenario: Two ruleset versions do not collide

- **WHEN** the same sheet is rendered against two ruleset versions
- **THEN** they are in different version directories

#### Scenario: Formats of one document stay together

- **WHEN** one document is rendered to two formats
- **THEN** both land in the same version directory, differing only by extension

#### Scenario: An unpublishable document is refused

- **WHEN** a document records no language, no name, or no ruleset version
- **THEN** rendering fails, naming what is missing

#### Scenario: A stale publication fails CI

- **WHEN** the committed publication differs from one freshly rendered from the document
- **THEN** CI fails, naming the command that regenerates it

### Requirement: The sheet is buildable locally and in CI

The generator SHALL be invocable as `python -m publisher.quicksheet extract`,
`... render` and `... build`, each accepting an output directory, and SHALL run identically
on a developer machine and on
`ubuntu-latest` with no system packages beyond a Python interpreter and the project's pinned
Python dependencies.

CI SHALL build the sheet twice and compare the results, so a determinism regression fails the
pipeline rather than being discovered later.

#### Scenario: Local build

- **WHEN** a developer runs `python -m publisher.quicksheet build --out dist/` against a
  synced, pinned clone
- **THEN** `dist/document.json` and `dist/quicksheet.pdf` are written and the command exits
  zero

#### Scenario: CI proves determinism

- **WHEN** the CI job runs both stages into two directories and compares them
- **THEN** the job passes only if both the documents and the PDFs are byte-identical, and
  both are uploaded as workflow artifacts

#### Scenario: Output directory does not exist

- **WHEN** the given output directory does not exist
- **THEN** the generator creates it and writes the PDF
