## ADDED Requirements

### Requirement: The web document is extracted from the pinned ruleset

Extraction SHALL read the ruleset clone at the commit `source/studcraft.lock.json` records,
through upstream's own parser, and SHALL refuse to run when the clone is at any other
commit. The extracted document SHALL record the ruleset version and commit it came from.

#### Scenario: The clone is at the pinned commit

- **WHEN** `extract` runs against a clone at the pinned commit
- **THEN** it writes `data/rules_web/document.json` recording that commit and the ruleset
  version

#### Scenario: The clone has drifted

- **WHEN** `extract` runs against a clone at any other commit
- **THEN** it fails, naming both the commit on disk and the pinned commit, and writes
  nothing

### Requirement: Documents and rules have derived, stable slugs

A ruleset document's slug SHALL be its filename with the numeric prefix and extension
removed. A rule's slug SHALL be its rule ID lowercased. Both SHALL be overridable per
document in `data/rules_web/spec.toml`, so that a renumbering upstream never silently moves
a published URL.

#### Scenario: A document slug is derived

- **WHEN** `02-core-rules.md` is extracted
- **THEN** its page slug is `core-rules`

#### Scenario: A rule slug is derived

- **WHEN** rule `CORE-001` is extracted
- **THEN** its page slug is `core-001`

#### Scenario: A slug is overridden

- **WHEN** `spec.toml` gives `02-core-rules.md` the slug `core`
- **THEN** its page slug is `core`, and its rules remain children of that page

### Requirement: A rule body is rendered as HTML

A rule's Markdown body SHALL be rendered to HTML. Rendering SHALL be deterministic: the same
document rendered twice SHALL produce identical bytes.

#### Scenario: A rule body becomes HTML

- **WHEN** a rule whose body contains paragraphs, a list and a blockquote is rendered
- **THEN** the page HTML contains the corresponding elements and no Markdown syntax

#### Scenario: Rendering is deterministic

- **WHEN** the same document is rendered twice into different destinations
- **THEN** the two outputs are byte-identical

### Requirement: Cross-references become links, and an unknown reference fails the build

A reference to another rule in a rule body SHALL be rewritten to a link to that rule's page.
A reference to a rule ID that is not in the pinned ruleset SHALL fail extraction.

#### Scenario: A known reference is linked

- **WHEN** a rule body cites `(03-game-flow.md, FLOW-013)`
- **THEN** the rendered HTML links that citation to the `flow-013` page under the
  `game-flow` document

#### Scenario: An unknown reference fails

- **WHEN** a rule body cites a rule ID absent from the pinned ruleset
- **THEN** extraction fails, naming the citing rule and the unknown ID, and writes nothing

### Requirement: Embedded images are carried into the document

An image embedded in a rule body SHALL appear in the document as a media reference carrying
the image's filename, its alt text, and the page that embeds it. The image `src` in the page
HTML SHALL be a placeholder resolved at publication time, never a site URL.

#### Scenario: A rule embeds an image

- **WHEN** `CORE-001` embeds `../assets/images/core-001-unit-base-volume.png`
- **THEN** the document lists that file as media attached to the `core-001` page, with the
  alt text from the Markdown, and the page HTML carries a placeholder in place of the `src`

#### Scenario: An embedded file is missing from the clone

- **WHEN** a rule body embeds an image that does not exist in the clone
- **THEN** extraction fails, naming the rule and the missing path

### Requirement: A document page indexes its rules

Each ruleset document SHALL produce one page listing every rule it contains, in ruleset
order, each entry linking to that rule's page. Each rule SHALL produce one page carrying its
body, as a child of its document's page.

#### Scenario: A document page is built

- **WHEN** a document containing three rules is extracted
- **THEN** one page is produced for the document, listing and linking all three, and three
  rule pages are produced as its children
