## 1. The local harness

- [x] 1.1 Commit `tools/wordpress-local/` — `docker-compose.yml`, `bootstrap.sh`, `README.md` — already built and verified on this branch
- [x] 1.2 Confirm `.env` is git-ignored and that no credential is tracked
- [x] 1.3 Verify a cold start from empty volumes: `docker compose down -v`, `up -d`, `./bootstrap.sh`, site reachable
- [x] 1.4 Verify `bootstrap.sh` is repeatable — a second run creates no second user and no second install
- [x] 1.5 Verify an overridden `WP_PORT` moves both the published port and the site's stored URL

## 2. The `rules_web` product

- [ ] 2.1 Add `data/rules_web/spec.toml`: which ruleset documents are published, with optional slug and title overrides
- [ ] 2.2 Derive a document slug from its filename (numeric prefix and extension stripped) and a rule slug from its ID, lowercased, with the spec overriding either
- [ ] 2.3 Extract full rule bodies from the pinned ruleset through upstream's parser, reusing `publisher.quicksheet.index`
- [ ] 2.4 Fail extraction when the clone is not at the pinned commit, naming both commits
- [ ] 2.5 Build the page set: one index page per document listing and linking its rules, one child page per rule
- [ ] 2.6 Write `data/rules_web/document.json` with a fixed key order so it diffs cleanly

## 3. Markdown to HTML

- [ ] 3.1 Pin a Markdown library in `pyproject.toml` and confirm its output is deterministic across two runs
- [ ] 3.2 Render paragraphs, lists, tables, blockquotes, emphasis and code spans from rule bodies
- [ ] 3.3 Rewrite cross-references such as `(03-game-flow.md, FLOW-013)` into links to the referenced rule's page
- [ ] 3.4 Fail extraction on a reference to a rule ID absent from the pinned ruleset, naming the citing rule and the unknown ID
- [ ] 3.5 Resolve link targets through the bundle's `base_path`, so a future language tree links inside itself

## 4. Images

- [ ] 4.1 Recognise the Markdown image embed inside a rule's `paragraph` blocks — it is not typed `image` by the parser
- [ ] 4.2 Replace each `src` with a `{{media:<filename>}}` placeholder in the page HTML
- [ ] 4.3 List each referenced image in the document's media set with filename, alt text, the page that embeds it, and a content hash
- [ ] 4.4 Fail extraction when an embedded image file is absent from the clone, naming the rule and the path
- [ ] 4.5 Take the media set from what `docs/` actually embeds, never from `assets/IMAGES.md`, which specifies images that may not exist yet

## 5. The `wp` renderer

- [ ] 5.1 Register a `wp` renderer writing one bundle to the derived publish path
- [ ] 5.2 Serialise pages in a fixed order with a fixed key order, carrying `language` and `base_path`
- [ ] 5.3 Verify rendering twice into different destinations produces byte-identical bundles
- [ ] 5.4 Generate and commit `data/rules_web/document.json` and the bundle together with the spec

## 6. The WordPress client

- [ ] 6.1 Define a `Transport` protocol with one `request()` method and a real implementation over the standard library
- [ ] 6.2 Authenticate with an application password over HTTP Basic, reading site URL, user and password from the environment
- [ ] 6.3 Refuse to send credentials to a non-HTTPS URL unless the host is a loopback address
- [ ] 6.4 Redact the authorization header from every error and log line the client produces
- [ ] 6.5 Raise errors that name the endpoint and status, and carry the site's message when there is one

## 7. `push`

- [ ] 7.1 Read only the bundle — never the ruleset, never the spec file
- [ ] 7.2 Look up each page by slug and parent; create when absent, update in place when present
- [ ] 7.3 Write every page with status `private`, overwriting title and content unconditionally
- [ ] 7.4 Create document pages before their rule pages, so a child always has its parent's ID
- [ ] 7.5 Upload each referenced image not already on the site, identified by filename, with its alt text and attached to its rule's page
- [ ] 7.6 Substitute every `{{media:…}}` placeholder with the uploaded file's URL, failing on one that cannot be resolved
- [ ] 7.7 Set orphaned pages to `private` and report them; never delete
- [ ] 7.8 Fail without modifying anything when orphans exceed the threshold
- [ ] 7.9 Print a summary: created, updated, unchanged, orphaned, media uploaded

## 8. `promote`

- [ ] 8.1 Flip every page in the bundle from `private` to `publish`, sending nothing but the status
- [ ] 8.2 Report what was promoted, and what was already published
- [ ] 8.3 Refuse to promote pages the current bundle does not contain

## 9. Tests

- [ ] 9.1 Test slug derivation for documents and rules, including the spec override
- [ ] 9.2 Test cross-reference rewriting, and that an unknown rule ID fails the build
- [ ] 9.3 Test image extraction: placeholder substitution, alt text, missing file failure
- [ ] 9.4 Test bundle determinism — render twice, compare bytes
- [ ] 9.5 Test `push` against a substitute transport: create, update, unchanged, orphan, orphan threshold
- [ ] 9.6 Test media lookup-before-upload, so no duplicate is created on a second run
- [ ] 9.7 Test the non-HTTPS refusal and the credential redaction
- [ ] 9.8 Run `pytest --cov` and confirm the coverage floor holds

## 10. End to end, against the local site

- [ ] 10.1 `push` the real bundle to the local WordPress and confirm the page hierarchy and slugs
- [ ] 10.2 Confirm an anonymous request for a rule page returns 404 while staged
- [ ] 10.3 Confirm the editor user can read a staged page
- [ ] 10.4 `promote`, then confirm the same URL returns 200 and the images render
- [ ] 10.5 Run `push` a second time and confirm nothing is created, duplicated or renamed
- [ ] 10.6 Remove a rule from the spec, `push`, and confirm the page is unpublished rather than deleted
- [ ] 10.7 Confirm the local site still has no plugin active

## 11. Documentation

- [ ] 11.1 Add the fourth stage to `system/publishing-pipeline.md`, including that WordPress is generated and not an editing surface
- [ ] 11.2 Document `push` and `promote` in `data/rules_web/` alongside the spec format
- [ ] 11.3 Record in `system/testing.md` that the Docker end-to-end run is deliberately not a required check
- [ ] 11.4 Run `ruff check .` and `ruff format --check .`
- [ ] 11.5 Delete the scratch file `delete-me-wordpress.md`
