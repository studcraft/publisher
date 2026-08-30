# `rules_web` — the ruleset as web pages

Every rule gets a URL, under the document that holds it, under one page for the whole
ruleset:

```
/rules                          an index of the systems
/rules/core-rules               an index of the rules in 02-core-rules.md
/rules/core-rules/core-001      CORE-001, its body, its images, its citations linked
```

## What `spec.toml` says, and what it does not

It names the ruleset documents that are published and what they are called on the web. That
is all. Which rules a document holds, what order they come in and what each one says are
read from the pinned ruleset, and a second copy here would drift from it.

```toml
title = "StudCraft Rules"
language = "en"
base_path = ""

[root]
slug = "rules"
title = "Rules"

[[document]]
file = "02-core-rules.md"
slug = "core-rules"
title = "Core Rules"
intro = "The universal rules every StudCraft scenario uses."
```

| Key | Required | Default | What it does |
|---|---|---|---|
| `title` | no | empty | The edition's own title. Not published as a page. |
| `language` | no | `en` | Part of the published filename, so two languages never collide. |
| `base_path` | no | empty | The segment every page sits under. Empty for English. |
| `name` | no | `rules_web` | The product name, and the publish directory. |
| `[root].slug` | no | `rules` | The segment every document sits under. |
| `[root].title` | no | `Rules` | The root page's title, and the menu entry's label. |
| `[root].intro` | no | empty | Markdown shown above the list of systems. |
| `[[document]].file` | **yes** | — | The ruleset document, by filename as the ruleset writes it. |
| `[[document]].slug` | no | derived | The URL segment. Derived by stripping the numeric prefix and `.md`. |
| `[[document]].title` | no | derived | The document page's title. Derived from the filename. |
| `[[document]].intro` | no | empty | Markdown shown above the index. Authored, so it cites no rules and embeds no images. |

An unknown key fails the build. A misspelled `slug` that was silently ignored would look
exactly like slug overrides not working.

### Write the slug out even though it is derived

Derivation is what keeps a URL from being a list someone maintains by hand. Writing it out
anyway is what keeps a **published** URL from moving: if upstream renumbers `08-vehicles.md`,
the derived slug does not change — but the day it becomes `08-war-machines.md`, it would,
and `/vehicles/veh-003` would move with it. The explicit slug is where that promise is made.

## What fails the build

- **A citation to a rule that does not exist.** The ruleset writes `(03-game-flow.md,
  FLOW-013)` inline and those become links; an unknown ID would publish a dead link, so it
  stops the build instead.
- **A citation to a rule in a document this edition does not publish.** There is no page to
  link to. Publish the document, or the citation cannot be honoured.
- **An embedded image that is not in the clone.** The ruleset embeds an image only when the
  file exists, so an absent one means the clone is incomplete.
- **A document with no rules**, and **two documents sharing a slug**.

## Building and publishing

```bash
python -m publisher.rules_web build     # ruleset -> document.json -> the bundle
python -m publisher.wp check            # read-only: can this site be published to?
python -m publisher.wp push             # the bundle -> the site, as `private`
python -m publisher.wp menu             # the bundle -> the site's navigation menu
python -m publisher.wp promote          # `private` -> `publish`
```

`check` writes nothing and answers the questions publishing depends on: whether the REST API
answers, whether the application password authenticates and as whom, whether that user may
publish and upload, and which pages already on the site sit at a slug this bundle publishes.
Run it first against any site you have not published to before. What the failures mean is in
[`system/publishing-pipeline.md`](../../system/publishing-pipeline.md).

`--pace <seconds>` spaces the writes out. Locally it can be zero; against a hosted WordPress
it is the difference between publishing and being cut off by a firewall halfway through.

`push` reads the bundle and nothing else, and stages everything `private`: the real URL, the
real hierarchy, editors only. `promote` sends one thing per page, a status. Both read
`WP_BASE_URL`, `WP_USER` and `WP_APP_PASSWORD` from the environment.

Test against the local WordPress in
[`tools/wordpress-local/`](../../tools/wordpress-local/README.md), which writes those three
variables into a git-ignored `.env`. See
[`system/publishing-pipeline.md`](../../system/publishing-pipeline.md) for the whole
pipeline, and for why a published page must never be edited in WordPress.

## Images

An image is taken from what a rule actually embeds, never from the ruleset's
`assets/IMAGES.md` — that file specifies images that are wanted, some of which are not drawn
yet. The bundle carries a `{{media:<filename>}}` placeholder rather than a URL, because
WordPress stores an upload under a directory named for the month it arrived: a URL fixed at
render time would make the same ruleset render to different bytes in a different month, and
the determinism gate would be pinning a value that legitimately drifts. `push` substitutes
the real URL once it knows where the file landed.

## Reading the ruleset through

Every page carries a link to the page before and after it in reading order:

```
/rules                       →  Core Rules
/rules/core-rules            ←  Rules            →  CORE-001
/rules/core-rules/core-001   ←  Core Rules       →  CORE-002
/rules/core-rules/core-016   ←  CORE-014         →  Game Flow
/rules/infantry/inf-012      ←  INF-011
```

The sequence is the one the bundle already carries — the root, then each system followed by
its own rules — so **the page after the last rule of a system is the next system**, and there
is no second ordering to keep in step with the index pages and the menu.

Every link the edition writes is absolute and resolved through `base_path`. A relative link
resolves against the browser's current URL, which is right only while that URL ends in a
slash, and WordPress will happily serve one that does not.

## The order documents are listed in

The specification's order is the ruleset's own numbering, which is its reading order, and it
is written onto every page as WordPress's `menu_order`. This is not decoration: left at zero,
WordPress falls back to sorting by title, and the site presents the ruleset alphabetically —
Combat first, Core Rules third.

## The menu

`python -m publisher.wp menu` writes a `wp_navigation` post holding one entry, **Rules**, with
the thirteen systems under it in reading order. A block theme's navigation block falls back
to the most recent such post when it has no reference of its own, so this is enough and the
theme's templates are never touched.

It stops one level down on purpose. Without it, a block theme renders a **Page List**, which
walks the whole hierarchy: measured on a stock Twenty Twenty-Five, 194 menu entries in
alphabetical order. The rules are reached from the page that indexes them.

## Changing a published URL

Renaming the root, a document slug, or `base_path` moves every page under it. `push` creates
the pages at their new addresses and **cannot see the old ones** — they are no longer beneath
anything it manages, so they stay published at URLs nothing links to any more. Before the
first public promotion this costs nothing; after it, plan the move, and unpublish the old
tree by hand.
