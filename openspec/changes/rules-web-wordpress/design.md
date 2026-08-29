## Context

The pipeline today is three stages, and each reads only the one before it:

```
ruleset AST ──extract──▶ document.json ──render──▶ publish/<name>/v<version>/<file>
```

That shape is what makes a ruleset bump reviewable: `git diff data/…/document.json` shows
which lines of the sheet the new rules changed, before anything is rendered.

WordPress is the first destination that is not a file. It is a live system with its own
state — post IDs, upload paths, statuses — and the risk is that its statefulness leaks
backwards into stages that are currently pure.

Several questions were settled by measurement against a local WordPress rather than by
reasoning, and the measurements are recorded in the decisions below. Two of them contradicted
what this design originally assumed.

## Goals / Non-Goals

**Goals:**

- Every rule has a URL, under the document that holds it.
- The whole publication is reviewable as one diff before it touches any site.
- Nothing reaches the public without a second, explicit step.
- The same artefact publishes identically to a throwaway local site and, later, to a
  production one.
- Nothing is installed on the WordPress side.

**Non-Goals:**

- Publishing to a live site, and the approval gate that belongs with it.
- Translations. The design keeps them addable without moving an English URL; it builds
  nothing for them.
- Editing rules in WordPress.
- Preserving old ruleset versions as pages. The repository is the archive.

## Decisions

### Publication is a fourth stage, not part of `render`

`render` stays pure and offline, and `push` reads only the rendered bundle. So the exact
bytes reviewed in a pull request are the bytes the site receives, a failed upload is retried
without re-reading the ruleset, and the existing determinism gate keeps working unchanged.

*Alternative rejected:* rendering straight to the REST API. It would make the publication
unreviewable and would put network failure inside a stage whose whole value is being
reproducible.

### One bundle file, not a tree of files

`publish.relative_path()` derives exactly one path per document. Rather than break that for
a many-page output, the `wp` renderer writes one JSON bundle holding every page payload in
order.

One tracked file gives one reviewable diff and one `cmp` for the render-twice gate. The
alternative — a directory of HTML files — would need a second path-derivation scheme and
would spread the "is this stale?" question across a tree.

### Pages, not a custom post type

Pages are hierarchical and REST-enabled in core. A custom post type would need
`hierarchical`, `show_in_rest` and a rewrite rule — all of it PHP living on the site, outside
any CI this repository has.

The cost is that ~100 entries appear in the site's page list. Accepted. If it becomes a real
complaint, moving to a custom post type later changes the push stage only; the bundle format
does not change.

### Slugs are lowercase — measured, and the measurement changed the design

WordPress runs `sanitize_title()` on every slug, so a slug submitted as `CORE-001` is stored
as `core-001`. Measured on stock `wordpress:latest`:

| Check | Result |
|---|---|
| Slug stored, submitted as `CORE-001` | `core-001` |
| `GET /core-rules/core-001/` | `200` |
| `GET /core-rules/CORE-001/` | `200`, no redirect |
| Canonical link on the uppercase URL | `…/core-rules/core-001/` |
| `wp_posts` collation | `utf8mb4_unicode_520_ci` |

This design originally assumed uppercase URLs would 404 and sketched a redirect plugin for
them. They do not: WordPress resolves a page path with a SQL comparison against `post_name`,
and the default collation is case-insensitive. The plugin is dropped.

Lowercase is still what gets generated, because uppercase working is a property of the
database collation rather than a WordPress guarantee — a case-sensitive collation would
404. The rule ID stays uppercase in the page title and body, which is the form people cite.

### `private` for staging, not `draft`

`private` publishes a page at its real URL, visible only to logged-in editors. `draft` is
reachable only through a preview link, which exercises none of the slug hierarchy this
change exists to get right.

Measured: a `private` page returns 404 to an anonymous request and 200 once published.

`promote` sends only a status change per page. It is not atomic — WordPress has no
transaction — so there is a short window where the site is half-promoted. Stated rather than
hidden.

### Identity by slug and parent, never by stored IDs

Post IDs differ between the local site and any production one, so a tracked ID map would be
wrong by construction. `push` looks up each page by slug and parent on every run.

Storing a content hash in post meta was the obvious alternative for skipping unchanged
pages; it needs `register_post_meta`, which is a plugin. Instead, change detection compares
the bundle against the previously published bundle already tracked in `publish/` — reusing
the mechanism the repository relies on rather than adding state to the site.

### Media URLs are resolved at push time

WordPress stores uploads under a dated directory:

```
/wp-content/uploads/2026/08/core-001-unit-base-volume.png
```

Baking that into the bundle would make the same ruleset render to different bytes in a
different month, and the render-twice gate would be pinning a value that legitimately
drifts. So the bundle carries `{{media:<filename>}}` and `push` substitutes.

Media identity uses the filename, which upstream's naming convention already makes unique
and stable (`<rule-id-lowercase>-<slug>.png`, and their linter rejects a stale name when a
rule is renumbered). Looking up before uploading is what prevents WordPress storing a
renamed duplicate as `…-1.png` and leaving a permanently wrong URL behind.

Verified: upstream's parser returns the Markdown embed inside the rule's blocks, typed
`paragraph`. So extraction gets images without an upstream change — but because the block is
not typed `image`, the extractor must recognise the Markdown syntax itself. A naive
Markdown-to-HTML pass would emit `<img src="../assets/images/…">`, which is a dead link that
looks like working code.

### A document page indexes its rules; rule pages carry the bodies

A rule ID is already the citation unit everywhere in this project. Making the rule the
canonical page matches how the content is referenced and avoids publishing the same text
twice.

*Alternatives rejected:* the document page carrying the full linear text with the rule pages
repeating it (duplicate content, two places to be wrong); or rule URLs redirecting to
anchors in one long page (no per-rule page to link or index, and the redirect needs a
plugin). Linear reading is served by the PDF, which already exists.

**This decision is the one most likely to change** — see Open Questions.

### Cross-references fail the build when unresolvable

The ruleset writes `(03-game-flow.md, FLOW-013)` inline, and turning those into links is the
largest single gain of publishing to the web. The rule index already knows every ID, so an
unknown one is a bug in the ruleset or the extractor. Rendering a dead link instead would
publish it.

### The transport is injectable

The REST client takes its transport as a dependency, so create-versus-update, orphan
handling, media lookup, the HTTPS refusal and header redaction are all tested with no
network. This is what lets the change meet the coverage floor without a Docker-dependent
test in the required job.

### Nothing is installed on WordPress

Everything used is core: Pages with `parent`, the REST API, Application Passwords, `private`
status, `/wp/v2/media`, and the `/%postname%/` permalink structure. Verified on stock
`wordpress:latest`: pretty permalinks resolve with no Apache configuration of our own — an
earlier draft mounted an `AllowOverride All` fragment on an assumption that turned out to be
wrong, and it was removed.

Ruled out for needing site-side code: custom post types, post meta, uppercase redirects,
Polylang/WPML, and `noindex` via an SEO plugin.

## Risks / Trade-offs

- **`promote` is not atomic** → It sends only a status change, so the half-promoted window
  is short. Accepted and documented rather than engineered around.
- **A broken extraction could unpublish most of the site** → `push` fails instead of
  unpublishing when orphans exceed a threshold, and never deletes.
- **A Markdown library's output could change between versions** → The dependency is pinned,
  and the render-twice gate plus the tracked bundle make any change visible as a diff.
- **An editor's change in WordPress is silently lost at the next push** → Stated in the
  spec, and each page carries a footer saying it is generated and where to fix it.
- **Uppercase URLs work by collation, not by guarantee** → Lowercase is always generated, so
  the tolerance is never depended on.
- **An SVG appearing upstream would break the pluginless constraint**, since WordPress
  rejects SVG uploads by default → `push` reports it as an unsupported format rather than
  surfacing a raw REST error. Nothing upstream ships SVG today.
- **Credentials could reach a CI log through an error path** → The client refuses non-HTTPS
  for non-loopback hosts and redacts the authorization header from every error it raises.

## Migration Plan

Nothing to migrate: this adds a product alongside the quick sheet and touches none of its
data. The local site is disposable — `docker compose down -v` is the rollback.

The first production publication is a later change, and its rollback is `promote`'s inverse:
setting pages back to `private` removes them from public view without deleting anything.

## Open Questions

1. **The document page's shape.** It is specified as an index of its rules. `assets/IMAGES.md`
   has a second image naming convention for images belonging to an unnumbered heading rather
   than a rule (`17-terrain-thresholds.png`, for "Terrain (INF-006 – INF-008)"). Under the
   index model there is no page for a heading, so such an image has nowhere to go. The
   likely answer is that the index page carries some prose and those images — which means it
   is not a bare list. No such image is drawn yet, so this can be settled when one appears.
2. **Which documents are published.** The spec file names them, and the initial set is not
   yet decided — the glossary and the changelog probably want different handling from the
   rule documents.
3. **The orphan threshold.** Ten is a guess. It wants to be set once the real page count is
   known.
