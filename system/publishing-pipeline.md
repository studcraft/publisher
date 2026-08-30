# Publishing Pipeline

Published documents are produced by a three-stage pipeline. Each stage reads only the stage
before it.

```
ruleset AST  ──extract──▶  document.json  ──render──▶  publish/…/<name>_<lang>.<ext>
```

| Path | Written by | Tracked | Edit by hand? |
|---|---|---|---|
| `data/<product>/spec.toml` | a person | yes | **yes — this is the source** |
| `data/<product>/document.json` | `extract` | yes | only for a one-off; `extract` overwrites it |
| `publish/<product>/v<version>/…` | `render` | yes | never |

## Products

Two, and they share every stage but the last:

- **`quicksheet_3x3`** — the printed quick sheet. `render --format pdf` writes a PDF.
- **`rules_web`** — the ruleset as web pages. `render` writes one JSON bundle holding every
  page, which a fourth stage publishes to WordPress.

```bash
python -m publisher.quicksheet build     # the sheet
python -m publisher.rules_web build      # the web edition
```

## The fourth stage: WordPress

```
… ──render──▶ publish/rules_web/v<version>/rules_web_en.wp.json ──push──▶ WordPress
                                                                ──promote──▶ public
```

`push` reads the bundle and **nothing else** — not the ruleset, not the spec. The bytes
reviewed in a pull request are the bytes the site receives. It writes every page `private`:
the real URL, the real hierarchy, visible to editors only. `promote` sends one thing per
page, a status, so making a publication public cannot introduce a change nobody reviewed.

```bash
python -m publisher.wp push       # stage as `private`
python -m publisher.wp menu       # write the site's navigation menu
python -m publisher.wp promote    # make public
```

`menu` is the one command that writes something other than the pages: a `wp_navigation` post
holding **Rules** and the ruleset's systems in reading order. Without it a block theme
renders a Page List of all 194 pages, alphabetically. It writes no template and no theme
file — those stay the site owner's.

Both read `WP_BASE_URL`, `WP_USER` and `WP_APP_PASSWORD` from the environment; the local
harness in [`tools/wordpress-local/`](../tools/wordpress-local/README.md) writes all three
into a git-ignored `.env`. Test against that, never against a live site.

**Nothing is installed on WordPress.** Pages, the REST API, application passwords and the
`/%postname%/` permalink structure are all core. A change that needs a plugin is a finding
about the design, not a missing step.

## Publishing to a real site

`.github/workflows/publish.yml` does it. A tag `v*` runs `stage`, which restores the pinned
ruleset, rebuilds, refuses to continue if that changed a tracked file, runs the preflight,
then stages and writes the menu. Going public is a separate `workflow_dispatch` behind the
`wordpress-production` environment, which is where the required reviewer lives. Neither job
is a required status check, and neither may be made one — see [Testing](testing.md).

Three secrets, on both environments: `WP_BASE_URL`, `WP_USER`, `WP_APP_PASSWORD`.

**Run the preflight before anything else**, including by hand the first time:

```bash
python -m publisher.wp check
```

It writes nothing. It establishes that `/wp-json` answers, that the application password
authenticates and as whom, that the user may publish pages and upload files, and — the part
no error message would ever say — **which pages already on the site sit at a slug this
bundle publishes**. `push` adopts a page by its slug, so a page somebody made at `/movement`
is a page `push` will overwrite. Better seen in a read-only run than afterwards.

What goes wrong on someone else's WordPress, and what each one actually is:

| Symptom | Cause | Fix |
|---|---|---|
| 401, password known good | The server drops the `Authorization` header before PHP sees it — usual under CGI/FastCGI | Host-side: `CGIPassAuth On`, or `SetEnvIf Authorization "(.*)" HTTP_AUTHORIZATION=$1` |
| 401 | Application passwords disabled, or the site is not HTTPS | WordPress requires SSL for them; the client refuses plain HTTP anyway, except on loopback |
| 403 on `/wp-json` | A firewall or security plugin blocking REST writes | Allow the route, or the address publishing from |
| 403 after a few dozen writes | **Rate limiting.** ~200 pages at loop speed is the burst a WAF reads as an attack | `--pace 0.3`, and raise it. The workflow already does |
| 403 `rest_cannot_create` on the menu | `menu` writes a `wp_navigation`, which needs `edit_theme_options` | Publish as an administrator; an editor can do everything else |

429, 502, 503 and 504 are retried with a doubling wait, honouring `Retry-After`. Everything
else fails once, because a rejected slug or a missing capability fails identically however
many times it is sent.

**The default pace is a conservative guess, not a validated figure.** It has never been run
against a hosted WordPress: 0.3 seconds was chosen to be slow enough to be unremarkable, not
because any host was measured. Treat it as a starting point — some hosts need more, most
would tolerate less, and the right value is whatever that site stops objecting to.

### What the publisher owns, and what it never touches

```
StudCraft repository  →  deterministic bundle  →  WordPress
   source of truth         reviewed artefact      deployment target
```

The publisher owns **exactly one subtree**: the root page the specification names, and
everything under it. A page belongs to it when its slug *and* its parent both agree — never
the slug alone. A slug is unique among siblings in WordPress, not across a site, so a page
somebody made at `/movement` is untouched by a publication whose own page is
`/rules/movement`. Everything outside that subtree, and the theme, the templates and the
site's other pages, belong to whoever put them there.

**Publisher-managed pages are generated artefacts. Change them in the StudCraft source and
publish through the pipeline.** An editor who fixes a typo in wp-admin loses it at the next
`push`, silently — `push` overwrites title and content and makes no attempt to detect a human
edit, because detecting one would invite treating WordPress as a source. Editors review while
it is `private` and report; the fix goes in `spec.toml` or upstream in the ruleset.

### When a rule or a document goes away

Deterministic, and it never deletes:

| What happened | What `push` does |
|---|---|
| A rule leaves the ruleset | Its page is set to `private`, and named in the run summary |
| A whole document leaves | Its page **and every rule page under it** are set to `private` |
| More pages than the limit disappear at once | `push` fails and changes nothing — that scale of loss is a broken extraction, not a ruleset that shrank |
| A page outside the published subtree | Never examined, never touched |

`python -m publisher.wp check` lists the orphans before a push creates them, so the answer to
"what would this change?" comes before the change.

### Recovering from a publication that stopped halfway

Run it again. `push` is idempotent: it locates each page by slug and parent, compares the
stored title and content against the bundle, and writes only what differs. A run interrupted
by a network failure leaves some pages written and the rest absent; the next run creates what
is missing, reports the rest as unchanged, and the site converges on the bundle. Nothing has
to be undone first, and nothing is written twice.

### URL structure is a public interface

Renaming the root, a document slug, or `base_path` moves every page under it. `push` creates
the pages at their new addresses and **cannot see the old ones** — they are no longer beneath
anything it manages, so they stay published at URLs nothing links to any more.

**Once a URL structure has been publicly promoted, changing it is a migration, not an
edit.** There is no `migrate` command today; until there is, a structural change means
planning the move and unpublishing the old tree by hand. Before the first public promotion it
costs nothing.

## The ruleset is pinned

The pipeline reads a clone of the StudCraft ruleset in git-ignored `source/studcraft/`, at
exactly the commit `source/studcraft.lock.json` records. That lock file **is** tracked, and
every build verifies the clone matches it before doing anything.

```bash
python -m publisher.sync --pinned    # restore the clone to the pinned commit — do this
python -m publisher.sync             # clone whatever `main` is now AND rewrite the pin
```

Those two are not interchangeable, and the second is the trap. Without `--pinned`, `sync`
resolves the branch to wherever it is today and overwrites the lock file, so the sheet
silently starts describing a ruleset nobody reviewed. Bumping the pinned ruleset is a
deliberate change: run it, rebuild, and let the `document.json` diff show which lines of the
sheet the new rules changed.

## Two rules follow, and CI enforces both

- **Never edit a generated file to fix a problem in its source.** A wrong line on the sheet
  is fixed in `spec.toml`, not in `document.json` and not in the PDF.
- **Regenerate and commit in the same change.** `python -m publisher.quicksheet build` and
  `python -m publisher.rules_web build`, then commit `data/` and `publish/` together with the
  spec edit. CI fails on `git diff --exit-code` against either. A ruleset bump touches both
  products, so build both.

Reference documentation, not restated here:

- **[`data/SPEC-FORMAT.md`](../data/SPEC-FORMAT.md)** — every key of `spec.toml`, its
  defaults, what fails the build, and how to write a line without misstating the rule it
  cites. **Read this before writing or editing a spec.**
- [`data/README.md`](../data/README.md) — the product directory layout.
- [`publish/README.md`](../publish/README.md) — how a publish path is derived, and why the
  tree is committed.
