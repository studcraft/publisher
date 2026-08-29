## 1. Model

- [x] 1.1 Add `Outcome` (a condition and what it produces)
- [x] 1.2 Give `Line` `label`, `outcomes`, `steps`, and a `kind` property; make `text` optional
- [x] 1.3 Omit unused shapes from the JSON, so a prose entry does not carry `"outcomes": []`
- [x] 1.4 Read entries back, failing on no shape, more than one shape, or half a lookup row

## 2. Extraction

- [x] 2.1 Accept `label`, `outcome` and `steps` in `spec.toml`; reject unknown keys inside an
      outcome row as at every other level
- [x] 2.2 Fail on no shape, more than one shape, an empty step, or a missing `when`/`then`
- [x] 2.3 Tests: each shape read back, both failure modes, and the outcome-row failures

## 3. Rendering

- [x] 3.1 Make wrapping take segments that may be forced bold, so a label is bold without
      being a glossary term, measured in the style it is drawn in
- [x] 3.2 Draw entries as rows: prose inline, lookups and sequences indented under a label
- [x] 3.3 Align every result of a lookup into one column, clear of the widest condition
- [x] 3.4 Tests: rows drawn, sequence flows, label separated, and drawn x positions equal
      across a lookup's results
- [x] 3.5 Let a lookup row cite its own rule; print every rule an entry cites in one place

## 4. Content

- [x] 4.1 Rewrite `data/quicksheet_3x3/spec.toml` to the reviewer's recommendations:
      attack roll, damage roll, geometry check, states and obstacles as lookups; shooting,
      damage, setup and end of turn as sequences; movement as labelled values
- [x] 4.2 Diff the cited rules against `origin/main` and account for every difference:
      nothing added; `FLOW-010` deliberately removed on the reviewer's advice
- [x] 4.3 Regenerate `document.json` and the published PDF
- [x] 4.4 Confirm one page, and that rendering twice still gives identical bytes

## 5. Documentation

- [x] 5.1 `data/SPEC-FORMAT.md`: the three shapes, when each applies, `label`, and the new
      failures
- [x] 5.2 Header comment in `spec.toml` pointing at the shapes

## 6. Wrap-up

- [x] 6.1 `ruff check .` and `ruff format --check .` clean
- [x] 6.2 `pytest` green; report the actual count
- [ ] 6.3 Show the rebuilt sheet to the reviewer and confirm it answers what they raised
      NOT DONE - needs the reviewer.
- [ ] 6.4 Print it and play a game from it, still open from the previous change
      NOT DONE - physical task.
