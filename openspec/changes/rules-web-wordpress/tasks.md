## 1. The local harness

- [x] 1.1 Commit `tools/wordpress-local/` — `docker-compose.yml`, `bootstrap.sh`, `README.md` — already built and verified on this branch
- [x] 1.2 Confirm `.env` is git-ignored and that no credential is tracked
- [x] 1.3 Verify a cold start from empty volumes: `docker compose down -v`, `up -d`, `./bootstrap.sh`, site reachable
- [x] 1.4 Verify `bootstrap.sh` is repeatable — a second run creates no second user and no second install
- [x] 1.5 Verify an overridden `WP_PORT` moves both the published port and the site's stored URL

## 2. The `rules_web` product

- [x] 2.1 Add `data/rules_web/spec.toml`: which ruleset documents are published, with optional slug and title overrides
- [x] 2.2 Derive a document slug from its filename (numeric prefix and extension stripped) and a rule slug from its ID, lowercased, with the spec overriding either
- [x] 2.3 Extract full rule bodies from the pinned ruleset through upstream's parser, reusing `publisher.quicksheet.index`
- [x] 2.4 Fail extraction when the clone is not at the pinned commit, naming both commits
- [x] 2.5 Build the page set: one index page per document listing and linking its rules, one child page per rule
- [x] 2.6 Write `data/rules_web/document.json` with a fixed key order so it diffs cleanly

## 3. Markdown to HTML

- [x] 3.1 Pin a Markdown library in `pyproject.toml` and confirm its output is deterministic across two runs
- [x] 3.2 Render paragraphs, lists, tables, blockquotes, emphasis and code spans from rule bodies
- [x] 3.3 Rewrite cross-references such as `(03-game-flow.md, FLOW-013)` into links to the referenced rule's page
- [x] 3.4 Fail extraction on a reference to a rule ID absent from the pinned ruleset, naming the citing rule and the unknown ID
- [x] 3.5 Resolve link targets through the bundle's `base_path`, so a future language tree links inside itself

## 4. Images

- [x] 4.1 Recognise the Markdown image embed inside a rule's `paragraph` blocks — it is not typed `image` by the parser
- [x] 4.2 Replace each `src` with a `{{media:<filename>}}` placeholder in the page HTML
- [x] 4.3 List each referenced image in the document's media set with filename, alt text, the page that embeds it, and a content hash
- [x] 4.4 Fail extraction when an embedded image file is absent from the clone, naming the rule and the path
- [x] 4.5 Take the media set from what `docs/` actually embeds, never from `assets/IMAGES.md`, which specifies images that may not exist yet

## 5. The `wp` renderer

- [x] 5.1 Register a `wp` renderer writing one bundle to the derived publish path
- [x] 5.2 Serialise pages in a fixed order with a fixed key order, carrying `language` and `base_path`
- [x] 5.3 Verify rendering twice into different destinations produces byte-identical bundles
- [x] 5.4 Generate and commit `data/rules_web/document.json` and the bundle together with the spec

## 6. The WordPress client

- [x] 6.1 Define a `Transport` protocol with one `request()` method and a real implementation over the standard library
- [x] 6.2 Authenticate with an application password over HTTP Basic, reading site URL, user and password from the environment
- [x] 6.3 Refuse to send credentials to a non-HTTPS URL unless the host is a loopback address
- [x] 6.4 Redact the authorization header from every error and log line the client produces
- [x] 6.5 Raise errors that name the endpoint and status, and carry the site's message when there is one

## 7. `push`

- [x] 7.1 Read only the bundle — never the ruleset, never the spec file
- [x] 7.2 Look up each page by slug and parent; create when absent, update in place when present
- [x] 7.3 Write every page with status `private`, overwriting title and content unconditionally
- [x] 7.4 Create document pages before their rule pages, so a child always has its parent's ID
- [x] 7.5 Upload each referenced image not already on the site, identified by filename, with its alt text and attached to its rule's page
- [x] 7.6 Substitute every `{{media:…}}` placeholder with the uploaded file's URL, failing on one that cannot be resolved
- [x] 7.7 Set orphaned pages to `private` and report them; never delete
- [x] 7.8 Fail without modifying anything when orphans exceed the threshold
- [x] 7.9 Print a summary: created, updated, unchanged, orphaned, media uploaded

## 8. `promote`

- [x] 8.1 Flip every page in the bundle from `private` to `publish`, sending nothing but the status
- [x] 8.2 Report what was promoted, and what was already published
- [x] 8.3 Refuse to promote pages the current bundle does not contain

## 9. Tests

- [x] 9.1 Test slug derivation for documents and rules, including the spec override
- [x] 9.2 Test cross-reference rewriting, and that an unknown rule ID fails the build
- [x] 9.3 Test image extraction: placeholder substitution, alt text, missing file failure
- [x] 9.4 Test bundle determinism — render twice, compare bytes
- [x] 9.5 Test `push` against a substitute transport: create, update, unchanged, orphan, orphan threshold
- [x] 9.6 Test media lookup-before-upload, so no duplicate is created on a second run
- [x] 9.7 Test the non-HTTPS refusal and the credential redaction
- [x] 9.8 Run `pytest --cov` and confirm the coverage floor holds

## 10. End to end, against the local site

- [x] 10.1 `push` the real bundle to the local WordPress and confirm the page hierarchy and slugs
- [x] 10.2 Confirm an anonymous request for a rule page returns 404 while staged
- [x] 10.3 Confirm the editor user can read a staged page
- [x] 10.4 `promote`, then confirm the same URL returns 200 and the images render
- [x] 10.5 Run `push` a second time and confirm nothing is created, duplicated or renamed
- [x] 10.6 Remove a rule from the spec, `push`, and confirm the page is unpublished rather than deleted
- [x] 10.7 Confirm the local site still has no plugin active

## 11. Documentation

- [x] 11.1 Add the fourth stage to `system/publishing-pipeline.md`, including that WordPress is generated and not an editing surface
- [x] 11.2 Document `push` and `promote` in `data/rules_web/` alongside the spec format
- [x] 11.3 Record in `system/testing.md` that the Docker end-to-end run is deliberately not a required check
- [x] 11.4 Run `ruff check .` and `ruff format --check .`
- [x] 11.5 Delete the scratch file `delete-me-wordpress.md`

## 12. One root, reading order, and a menu

- [x] 12.1 Add a `[root]` table to `spec.toml` and publish every document under one root page
- [x] 12.2 Set `menu_order` from the specification's document order and the ruleset's rule order
- [x] 12.3 Send `menu_order` on create and update, and treat a change to it as a change to publish
- [x] 12.4 Order `push` and `promote` by depth so an arbitrarily deep hierarchy still works
- [x] 12.5 Make the orphan scan descend, so a removed document takes its rules with it
- [x] 12.6 Add `python -m publisher.wp menu`, writing a `wp_navigation` post and no template
- [x] 12.7 Address menu entries by URL, never by page ID, so one bundle suits two sites
- [x] 12.8 Test the menu, the ordering, and the descending orphan scan
- [x] 12.9 Verify against the local site: the header shows Rules and 13 systems in reading order
- [x] 12.10 Document the root table, the menu command, and what changing a published URL costs

## 13. Publishing to a site that is not local

- [x] 13.1 Add `python -m publisher.wp check`: reachable, authenticated, capable, and what it would overwrite
- [x] 13.2 List the site's pages in pages of a hundred, so the check is two requests rather than two hundred
- [x] 13.3 Add `--pace` and `--attempts`, with a doubling backoff that honours `Retry-After`
- [x] 13.4 Retry only transient statuses; never retry a refusal
- [x] 13.5 Explain 401, 403 and 429 in the error itself, since on a hosted site the cause is infrastructure
- [x] 13.6 Add `.github/workflows/publish.yml`: stage on a tag, promote behind a reviewed environment
- [x] 13.7 Record in the workflow why neither job may be made a required check
- [x] 13.8 Test the check, the pacing and the retries with no network
- [x] 13.9 Document the remote failure modes and their fixes

## 14. Review: ownership, recovery, and what gets documented

- [x] 14.1 Fix `find_page`: a top-level lookup means the top level, not any parent
- [x] 14.2 Test that a page elsewhere sharing a managed slug is never adopted or overwritten
- [x] 14.3 Verify it against the real local site with a page at `/handbook/rules`
- [x] 14.4 Report orphans from `check`, so a push's effect is known before the push
- [x] 14.5 Report same-slug pages outside the subtree as safe rather than as a risk
- [x] 14.6 Test that a `push` interrupted partway converges when it is run again
- [x] 14.7 Document the ownership boundary, the orphan table, recovery, and the URL policy
- [x] 14.8 Say plainly that the default pace is a guess, never measured against a host
