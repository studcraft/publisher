# `publish/`

Rendered artefacts, one path per product, ruleset version, format and language:

```
publish/<product>/v<ruleset version>/<product>_<language>.<extension>
```

Today:

```
publish/quicksheet_3x3/v0.2.0draft/quicksheet_3x3_en.pdf
```

## The path is derived, never chosen

It comes from the document's `name`, `source.ruleset_version` and `language` — not from an
argument someone types. A published artefact has to be findable from what it *is*, so that
this tree can be pushed to a single source of truth and compared across versions without a
manifest to keep in sync.

Three consequences the code enforces rather than documents:

- Two languages of one sheet are two files in the same version directory.
- A sheet built against a newer ruleset lands beside the old one, never on top of it.
- Every format of one document shares its version directory, so a version is one directory.

A document that records no version, name or language is refused rather than published to a
path that would collide with something else.

## These files are committed

Builds are byte-reproducible, so a diff here means the content really changed. Committing
them is what makes "which PDF did we publish for ruleset 0.2.0 Draft" answerable from the
repository alone, a year later, without rebuilding anything. CI regenerates and fails on
`git diff --exit-code`, so what is committed always matches the document it came from.

## The one weakness, stated plainly

The version directory is keyed on the **ruleset** version. The sheet can change without the
ruleset changing — a reworded line, a layout tweak — and those land in the same directory,
overwriting the previous file. Git history is the record of that, and the reproducible bytes
make the diff meaningful.

If a published artefact ever needs to be immutable per release rather than per ruleset
version, the fix is a publication version of its own in the path, not a change to how the
path is derived.
