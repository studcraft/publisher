## ADDED Requirements

### Requirement: An entry takes the shape of how it is read

The specification file SHALL let an entry take exactly one of three shapes, chosen by how a
player reads it at a table rather than by how much it says:

- a **statement**, read as a sentence;
- a **lookup**, scanned as rows of condition and result;
- a **sequence**, followed in order.

An entry with none of the three SHALL fail, because it would print nothing. An entry with
more than one SHALL fail: two shapes at once is not a richer entry, it is an unanswered
question about how to draw it.

An entry MAY carry a label — the word a player's eye searches for. A label SHALL be drawn
set apart from the value, so that finding the entry does not require reading it. A label
with no shape under it SHALL fail.

Shapes SHALL be expressed as fields, never as markup inside the text. The generator still
writes no content of its own.

#### Scenario: A lookup keeps its rows

- **WHEN** an entry declares rows of condition and result
- **THEN** the document carries them in the order given, as a lookup

#### Scenario: A sequence keeps its order

- **WHEN** an entry declares steps
- **THEN** the document carries them in the order given, as a sequence

#### Scenario: Two shapes at once fails

- **WHEN** an entry declares both a statement and a lookup
- **THEN** the build fails, naming both

#### Scenario: A label alone fails

- **WHEN** an entry carries a label and no shape
- **THEN** the build fails, because a label with nothing under it is a heading without an
  answer beneath it

#### Scenario: Half a lookup row fails

- **WHEN** a lookup row gives a condition with no result, or the reverse
- **THEN** the build fails, naming the missing half

### Requirement: Lookup results are aligned into a column

Every result of one lookup SHALL be drawn starting at the same horizontal position, and
that position SHALL be clear of the widest condition in that lookup.

Alignment is the whole point of the shape: a column can be scanned, whereas results that
each begin wherever their condition ended must be read. A lookup drawn as running text
would satisfy nothing this requirement exists for.

#### Scenario: Results share one column

- **WHEN** a lookup with rows of differing condition widths is drawn
- **THEN** every result begins at the same horizontal position, and no result begins at the
  position the conditions use

#### Scenario: A sequence is drawn as a flow

- **WHEN** an entry declares steps
- **THEN** they are drawn in order as one flow rather than as separate statements
