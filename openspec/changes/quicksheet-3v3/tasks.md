## 1. Determinism spike (blocking — do this first)

- [x] 1.1 Add `fpdf2` pinned exactly to `pyproject.toml` dependencies and `requirements.txt`
- [x] 1.2 Write a throwaway script that emits a two-column A4 page with Helvetica, a fixed
      creation date, a fixed modification date, and a fixed producer string
- [x] 1.3 Emit it twice and `cmp` the files; record which fields, if any, still differ
- [x] 1.4 If bytes differ, implement and verify a normalisation pass over the emitted PDF —
      do not change PDF library at this point
- [x] 1.5 Record the working recipe in `design.md` under Decisions, then delete the spike
      script

## 2. Ruleset pin

- [x] 2.1 Add `read_ruleset_version(clone_root)` to `sync.py`: parse `**Version:**` from every
      `docs/*.md` header, fail on disagreement, fail when none is found
- [x] 2.2 Add `write_lock(path, repo, rev, commit, version)` writing
      `source/studcraft.lock.json` with sorted keys and a trailing newline
- [x] 2.3 Call both from `clone_source` so a successful clone writes the lock file, and leave
      the lock untouched when the clone fails
- [x] 2.4 Add `!studcraft.lock.json` to `source/.gitignore` so the lock file is tracked
- [x] 2.5 Tests: lock file contents after a clone, explicit `--rev` recorded verbatim,
      version disagreement fails, missing version fails, failed clone leaves the lock alone
- [x] 2.6 Run `python -m publisher.sync` and commit the resulting `source/studcraft.lock.json`

## 3. Index

- [x] 3.1 Create `src/publisher/quicksheet/__init__.py`
- [x] 3.2 `index.py`: run `parse_ruleset.py --json` via `subprocess.run` with
      `sys.executable` and an explicit `cwd` of the clone root; surface the script's stderr on
      failure
- [x] 3.3 Validate the parsed JSON against the expected shape; fail naming the missing field
- [x] 3.4 Expose `rule(id) -> Rule` with title, document, line, line_end, and typed blocks;
      raise a named error for an unknown ID
- [x] 3.5 Add `verify_pin(clone_root, lock_path)`: compare the clone's `HEAD` to the lock
      file's commit, fail naming both SHAs, fail when the clone is absent
- [x] 3.6 Add `tests/fixtures/mini-docs/` — a tiny hand-written `docs/` stand-in with its own
      `scripts/parse_ruleset.py` output captured as a fixture, so tests never need the real
      clone
- [x] 3.7 Tests: rule lookup, unknown ID, malformed feed, non-zero parser exit, pin match,
      pin mismatch, absent clone

## 4. Spec file and extraction

- [x] 4.1 `model.py`: frozen dataclasses `Sheet`, `Section`, `Line` carrying rule ID, text,
      source document, and source line
- [x] 4.2 Define the `quicksheet_spec.toml` shape and add a loader using `tomllib` on
      Python ≥ 3.11 and `tomli` below it; add the conditional dependency to `pyproject.toml`
- [x] 4.3 `extract.py`: pure `build_sheet(index, spec) -> Sheet` — resolve every cited rule
      ID, attach source document and line, sorted iteration, no clock, no network
- [x] 4.4 Fail the build naming the missing ID and its section when a cited rule is absent
- [x] 4.5 Fail the build naming the offending section when a section lacks a heading or a line
      lacks `rule` or `text`
- [x] 4.6 Add `--raw` mode: emit a draft spec file from each rule's first paragraph and any
      table blocks, for bootstrapping only
- [x] 4.7 Tests: golden `Sheet` from `fixtures/mini-docs/`, missing rule ID, malformed
      section, missing line field, and a purity check that two calls return equal results

## 5. Renderer

- [x] 5.1 `render.py`: `Sheet` -> one-sided A4 PDF, two columns, using the recipe from task 1
- [x] 5.2 Print the ruleset version and abbreviated commit SHA on the page
- [x] 5.3 Mark the authored scenario preamble (warband of three, eliminate all opposing
      models) visibly as scenario definition rather than core rules
- [x] 5.4 Assert the document is exactly one page; fail the build if content overflows
- [x] 5.5 Tests: page count is one, page size is A4, overflow fails, and two renders of the
      same `Sheet` produce byte-identical files

## 6. CLI

- [x] 6.1 `cli.py`: `python -m publisher.quicksheet build --out dist/`, creating the output
      directory when absent
- [x] 6.2 Call `verify_pin` before any work, so a drifted clone fails before the parser runs
- [x] 6.3 Tests: writes `dist/quicksheet.pdf` and exits zero; creates a missing output
      directory; exits non-zero on a drifted pin

## 7. Author the sheet content

- [x] 7.1 Generate the first draft of `quicksheet_spec.toml` with `--raw` over the rule map in
      `design.md`
- [x] 7.2 Rewrite every line by hand for two-column density, keeping its rule anchor
- [x] 7.3 Verify each line against `docs/` at its recorded source line — in particular confirm
      `DMG-002` reads **Operational → Wounded → Dead**
- [x] 7.4 Confirm `DMG-003` and `CBT-015` are present and that no melee rule is cited
- [x] 7.5 Iterate layout until the sheet fits one page and is legible in print, not just on
      screen
- [ ] 7.6 Print it and play one game of the 3v3 mode from the sheet alone, with the ruleset
      closed; fix whatever the game exposed
      NOT DONE - physical task, needs a person, bricks and a table.

## 8. Glossary highlighting

- [x] 8.1 `index.py`: `read_ruleset` returns rules and glossary terms from one parse; find the
      glossary by its level-1 `Glossary` heading, not by filename; return terms longest first
- [x] 8.2 Carry the terms on `Sheet`; `build_sheet` accepts them
- [x] 8.3 `render.py`: case-sensitive, longest-first, whole-word term matching with an
      optional trailing `s`
- [x] 8.4 Tokenise into words of (fragment, is-term) runs, wrap measuring each fragment in the
      style it will be drawn in, draw run by run
- [x] 8.5 Report the highlighted term count from the CLI, since zero is not an error the build
      can detect
- [x] 8.6 Add a glossary to `tests/fixtures/mini-docs/`
- [x] 8.7 Tests: extraction by heading, longest-first order, no-glossary case, longest term
      wins, case sensitivity, plurals, no partial-word match, punctuation stays attached,
      multi-word terms, highlighting changes the page, highlighting stays reproducible

## 9. Split the pipeline into stages

- [x] 9.1 `model.py`: `Document` with `Page` (size, margins, columns, type sizes) and
      `Source`; JSON round-trip with fixed key order; unknown keys rejected by name
- [x] 9.2 `document.py`: deterministic read/write of `document.json`
- [x] 9.3 `extract.py`: build a `Document`; page parameters come from the spec's `[page]`
      table, with defaults when absent
- [x] 9.4 `render/`: format registry; `render/pdf.py` takes every measurement from
      `document.page`, no geometry constants left in the module
- [x] 9.5 `cli.py`: `extract`, `render`, `build`; `render` takes only a document and a format
- [x] 9.6 Tests: round-trip, stable bytes, page parameters present in the file, hand-edited
      file renders, misspelled key rejected, unknown schema rejected, registry lookup,
      unknown format lists what exists
- [x] 9.7 Tests: `render` succeeds with the clone and lock file deleted; a hand edit reaches
      the output; page geometry from the document reaches the PDF `/MediaBox`
- [x] 9.8 Write `document.json` to a tracked path, not into git-ignored `dist/`
- [x] 9.9 CI: regenerate in place and fail on `git diff --exit-code`
- [x] 9.10 Tests: the document is not written into the render directory; every CLI test
      passes `--data` explicitly so none can read or overwrite the repository's real one
- [x] 9.11 Move product data to `data/quicksheet_3x3/{spec.toml,document.json}`; replace
      `--spec` and `--document` with one `--data` directory flag; add `data/README.md`

## 10. Publication layout

- [x] 10.1 Add `name` and `language` to `Document`; require `language` in `spec.toml`; default
      `name` to the data directory so the two cannot drift
- [x] 10.2 `publish.py`: derive `<root>/<name>/v<version>/<name>_<language>.<ext>`; slug the
      version to one token; refuse a document missing name, version or language
- [x] 10.3 Renderers declare an extension and write to an exact path; the registry derives
      the path and creates the tree, so no renderer chooses where it writes
- [x] 10.4 `--out` becomes the publication root, defaulting to `publish/`; `dist/` is gone
- [x] 10.5 Keep `publish/` out of `.gitignore` and say why in the file
- [x] 10.6 `publish/README.md`: the scheme, why the tree is committed, and the
      ruleset-version-keying weakness stated plainly
- [x] 10.7 Tests: path composition, language collision, version collision, formats sharing a
      directory, slugging, path traversal, and each missing-field refusal
- [x] 10.8 CI: fail on `git diff --exit-code -- publish/`; render twice and compare bytes

## 11. CI

- [x] 11.1 Add a `quicksheet` job to `.github/workflows/ci.yml`: sync, re-extract and fail
      on `git diff --exit-code`, render twice, `cmp` the two PDFs
- [x] 11.2 Upload the PDF with `actions/upload-artifact@v4`
- [ ] 11.3 Confirm the job passes on the PR, and that a deliberate determinism break fails it
      NOT DONE - needs the branch pushed. Verified locally instead: a build from a clone
      restored by `sync --pinned` into a fresh directory is byte-identical to the local one.

## 12. Wrap-up

- [x] 12.1 `ruff check .` and `ruff format --check .` clean; type hints on public signatures;
      docstrings on public modules, classes, and functions
- [x] 12.2 `pytest` green; report the actual test count
- [x] 12.3 Confirm is git-ignored and no build output is staged
- [ ] 12.4 Delete `delete-me-handoff.md`
      NOT DONE - the file is git-ignored, so deleting it is unrecoverable. Left for the
      author to remove; everything in it is superseded by this change's artifacts.
- [ ] 12.5 Open the PR; do not squash the branch or rewrite its history
      NOT DONE - nothing is committed yet; committing and pushing is the author's call.
