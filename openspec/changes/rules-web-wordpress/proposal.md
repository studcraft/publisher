## Why

The ruleset is published today as a PDF quick sheet. Everything else — the rule bodies, the
images that carry the spatial rules, the cross-references between documents — exists only in
a git repository and reaches a player only if they go and read Markdown on GitHub.

A rule is already the unit people cite: `CORE-001`, `FLOW-013`. It has no address. This
change gives every rule a URL on a WordPress site the project already owns, so a citation
can be a link.

WordPress is not a new source of truth. It is a fourth stage of the existing pipeline, and
this change deliberately stops at a local one in Docker: the whole publication is built,
pushed and reviewed against a throwaway site before anything is pointed at a live one.

## What Changes

- **A second product, `rules_web`.** `data/rules_web/spec.toml` names which ruleset
  documents are published and their slugs; `extract` builds a document carrying full rule
  bodies rather than the quick sheet's condensed lines.
- **A `wp` renderer writing one bundle file.** `publish/rules_web/v<version>/rules_web_en.wp.json`
  holds every page payload in order. One tracked file, one reviewable diff, and the existing
  determinism gate (render twice, compare bytes) applies to it unchanged.
- **Markdown rule bodies become HTML**, with cross-references rewritten to links. A
  reference to a rule ID that does not exist **fails the build** rather than rendering a
  dead link.
- **A page hierarchy of documents and rules.** A parent page per ruleset document
  (`02-core-rules.md` → `core-rules`) listing its rules; a child page per rule
  (`core-001`) carrying the body. Slugs are lowercase, which is what WordPress stores.
- **`publisher.wp push` and `publisher.wp promote`.** `push` creates or updates every page
  as `private` — the real URL, visible to editors only. `promote` flips them to `publish`.
  Nothing reaches the public in one step.
- **Images are published as WordPress media**, attached to the rule page that embeds them,
  carrying the alt text the Markdown already has. The bundle holds a placeholder and `push`
  substitutes the upload URL, because WordPress upload paths contain the upload month and
  baking one into the bundle would break render determinism.
- **A local WordPress in Docker**, `tools/wordpress-local/`, already built and verified on
  this branch. Stock core, no plugins, disposable.
- **Nothing is installed on WordPress.** Pages, Application Passwords, the REST API and the
  `/%postname%/` permalink structure are all core. Custom post types, post meta and
  translation plugins are each ruled out for needing code on the site.

Not breaking: the quick sheet pipeline, its data and its published PDF are untouched.

### Non-goals

- **No live publication.** No tag-triggered workflow, no production credentials, no
  promotion of anything outside the local harness. That is a separate change, and it is
  where the approval gate belongs.
- **No translations.** English only, and no language segment in the URL — the design keeps
  `/es/…` addable later without moving an English URL, but adds nothing for it now.
- **WordPress is not an editing surface.** `push` overwrites title and content
  unconditionally and makes no attempt to detect or merge a human edit.

## Capabilities

### New Capabilities

- `rules-web-document`: extracting the pinned ruleset into a document of web pages — rule
  bodies as HTML, document and rule slugs, cross-references resolved to links, and the
  images each rule embeds.
- `wordpress-publication`: the bundle format, and pushing it to a WordPress site over the
  REST API — page hierarchy, the `private` → `publish` two-phase publication, identifying
  pages and media without storing state on the site, and media upload.
- `wordpress-local-harness`: a reproducible throwaway WordPress in Docker, with stock core
  and no plugins, that the publication can be built against and reviewed in.

### Modified Capabilities

None. `openspec/specs/` is empty, and the quick sheet pipeline's behaviour does not change.

## Impact

- **New code**: `src/publisher/rules_web/` (extraction and the `wp` renderer),
  `src/publisher/wp/` (the REST client, `push`, `promote`).
- **New data**: `data/rules_web/spec.toml` and its generated `document.json`;
  `publish/rules_web/v<version>/rules_web_en.wp.json`.
- **New tooling**: `tools/wordpress-local/` — `docker-compose.yml`, `bootstrap.sh`,
  `README.md`, and a git-ignored `.env` holding local credentials.
- **New dependency**: a Markdown-to-HTML library, pinned in `pyproject.toml`. Its output
  must be deterministic; the render-twice gate will catch it if it is not.
- **Unchanged**: `publisher.sync`, `publisher.quicksheet`, and everything under
  `data/quicksheet_3x3/` and `publish/quicksheet_3x3/`.
- **Testing**: the REST client takes an injectable transport, so `push` and `promote` are
  tested with no network. The Docker end-to-end run is a documented local command, not a
  required check — it needs Docker and a database, which CI's required job does not have.
