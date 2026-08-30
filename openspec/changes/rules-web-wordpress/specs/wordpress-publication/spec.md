## ADDED Requirements

### Requirement: The publication is one rendered bundle

The `wp` renderer SHALL write a single file holding every page payload in order, at the
publish path derived from the document's name, ruleset version and language. The push stage
SHALL read that bundle and nothing else — not the ruleset, not the specification file.

#### Scenario: The bundle is rendered

- **WHEN** `render --format wp` runs on the `rules_web` document
- **THEN** it writes `publish/rules_web/v<version>/rules_web_en.wp.json` containing every
  document page and rule page

#### Scenario: Rendering twice is identical

- **WHEN** the same document is rendered to two destinations
- **THEN** the two bundles are byte-identical

### Requirement: Publication is two-phase, and nothing reaches the public in one step

`push` SHALL write status `private` on every page it creates or changes. It SHALL leave the
status of a page it finds unchanged exactly as it is, so that pushing does not take an
already-published site out of public view between `push` and `promote`. `promote` SHALL
change page status to `publish` and SHALL change nothing else.

#### Scenario: Pushing stages a new publication

- **WHEN** `push` runs against a site that does not yet hold the pages
- **THEN** every page exists at its final URL with status `private`, and an anonymous
  request for one returns 404

#### Scenario: Promoting publishes it

- **WHEN** `promote` runs after `push`
- **THEN** every page has status `publish`, an anonymous request returns 200, and no page
  title or content was modified by the promotion

#### Scenario: Pushing an unchanged bundle over a published site

- **WHEN** `push` runs against a site whose pages are already published and match the bundle
- **THEN** no page changes status, and the site stays publicly readable throughout

#### Scenario: Pushing a changed page over a published site

- **WHEN** a page's content differs from what the site holds
- **THEN** that page is written as `private`, so the change is reviewed before it is public,
  while every unchanged page stays as it was

### Requirement: Pages are identified by slug and parent, never by stored state

`push` SHALL locate an existing page by its slug and parent on every run, and SHALL NOT read
or write any record of post IDs, in the repository or on the site. A page that is absent
SHALL be created; a page that is present SHALL be updated in place, keeping its URL.

#### Scenario: A first push creates pages

- **WHEN** `push` runs against a site with none of the pages present
- **THEN** every page is created, and the run reports each as created

#### Scenario: A second push updates in place

- **WHEN** `push` runs again against the same site with an unchanged bundle
- **THEN** no page is created, no page's slug or parent changes, and the run reports the
  pages as unchanged

#### Scenario: The same bundle pushes to a different site

- **WHEN** the same bundle is pushed to a site whose post IDs differ entirely
- **THEN** the result is the same page hierarchy, with no step depending on an ID from the
  other site

### Requirement: Generated pages are overwritten, not merged

`push` SHALL overwrite the title and content of a page it manages, without attempting to
detect or preserve a change made in WordPress.

#### Scenario: A page was edited in WordPress

- **WHEN** a managed page's content was changed in WordPress and `push` runs
- **THEN** the page's content is replaced by the bundle's content

### Requirement: A rule removed from the ruleset is unpublished, never deleted

A page under the published hierarchy that the bundle no longer contains SHALL be set to
`private` and reported. `push` SHALL NOT delete a page. When orphans exceed a configured
threshold, `push` SHALL fail rather than unpublish them, because that scale of loss
indicates a broken extraction rather than deleted rules.

#### Scenario: One rule is removed

- **WHEN** the bundle no longer contains a page that exists on the site
- **THEN** that page is set to `private` and named in the run summary, and it is not deleted

#### Scenario: Most of the ruleset disappears

- **WHEN** the number of orphaned pages exceeds the threshold
- **THEN** `push` fails without modifying any page, and reports the count

### Requirement: Images are uploaded once and their URLs resolved at push time

`push` SHALL upload each referenced image that is not already present on the site,
identifying an existing upload by filename so that WordPress never stores a renamed
duplicate. It SHALL set the image's alt text and attach it to the page that embeds it. It
SHALL replace each media placeholder in the page HTML with the uploaded file's URL, and
SHALL fail on a placeholder it cannot resolve.

#### Scenario: A new image is uploaded

- **WHEN** `push` runs and a referenced image is not on the site
- **THEN** the image is uploaded with its alt text, attached to its rule's page, and the
  page HTML carries the uploaded URL

#### Scenario: An image is already present

- **WHEN** `push` runs again with the same image
- **THEN** no upload occurs, no duplicate is created, and the page HTML carries the existing
  file's URL

#### Scenario: A placeholder cannot be resolved

- **WHEN** a page references a media filename absent from the bundle's media list
- **THEN** `push` fails, naming the page and the filename, and publishes nothing

### Requirement: Credentials are never sent in the clear or written to output

The client SHALL authenticate with an application password over HTTP Basic. It SHALL refuse
to send credentials to a URL that is not HTTPS unless the host is a loopback address. It
SHALL NOT include the authorization header in any log line or error message.

#### Scenario: A plain HTTP production URL

- **WHEN** the configured site URL is `http://` and the host is not a loopback address
- **THEN** the client refuses to make the request, and explains why

#### Scenario: A local site

- **WHEN** the configured site URL is `http://localhost:8080`
- **THEN** the client proceeds

#### Scenario: A request fails

- **WHEN** the site returns an error response
- **THEN** the raised error names the endpoint and status, and contains no credentials

### Requirement: The client is testable without a network

The HTTP client SHALL take its transport as an injectable dependency, so that push and
promote behaviour can be tested against a substitute transport with no network access.

#### Scenario: Push is tested offline

- **WHEN** the test suite runs with no network available
- **THEN** creating, updating, orphaning, media upload and the credential refusal are all
  exercised

### Requirement: The published hierarchy hangs from one root page

Every ruleset document SHALL be published as a page under one root page, and every rule as a
page under its document. `push` SHALL write a page only after the page it sits under exists,
whatever order the bundle lists them in.

#### Scenario: The hierarchy is created

- **WHEN** `push` runs against a site that holds none of the pages
- **THEN** the root exists, each document page is a child of it, and each rule page is a
  child of its document

#### Scenario: The bundle names a parent it does not contain

- **WHEN** a page sits under a slug the bundle has no page for
- **THEN** `push` fails, naming the missing parent, and publishes nothing

### Requirement: Published pages carry the ruleset's reading order

Each page SHALL be published with the ordering value that puts documents in the order the
specification lists them and rules in the order the ruleset gives them. A page whose order
has changed SHALL be updated.

#### Scenario: Order reaches the site

- **WHEN** `push` writes the pages
- **THEN** each page's `menu_order` is its position in reading order, not zero

#### Scenario: Only the order changed

- **WHEN** a page's content is unchanged but its position is not
- **THEN** `push` updates that page and reports it as updated

### Requirement: A removed subtree is unpublished with its descendants

When a bundle no longer contains a page that had children, `push` SHALL unpublish that page
and every page beneath it, none of which the bundle still names.

#### Scenario: A whole ruleset document stops being published

- **WHEN** the bundle no longer contains a document page or any of its rules
- **THEN** the document page and all its rule pages are set to `private` and reported

### Requirement: The site's navigation is written from the bundle

A command SHALL write a navigation menu holding one entry for the root page with the ruleset
documents beneath it, in reading order. It SHALL address entries by URL rather than by page
ID, SHALL update the menu it wrote before rather than adding a second one, and SHALL NOT
write any theme template or template part.

#### Scenario: The menu is written

- **WHEN** the menu command runs
- **THEN** a navigation exists holding the root entry and one entry per document, in reading
  order, and no rule appears in it

#### Scenario: The menu is written again

- **WHEN** the command runs a second time
- **THEN** the same navigation is updated, and the site holds exactly one

#### Scenario: A translated edition

- **WHEN** the bundle declares a base path
- **THEN** every menu entry's URL is inside that path

### Requirement: A site is checked before it is written to

A read-only command SHALL establish, without changing anything, that the REST API answers,
that the application password authenticates and as which user, that the user holds the
capabilities publishing needs, and which pages already on the site sit at a slug the bundle
publishes. It SHALL exit non-zero when any of that would prevent publishing, so an automated
run stops rather than half publishing.

#### Scenario: A healthy site

- **WHEN** the check runs against a site that can be published to
- **THEN** it reports each answer, exits zero, and has written nothing

#### Scenario: The REST API is closed

- **WHEN** `/wp-json` cannot be read
- **THEN** the check reports that alone and stops, rather than reporting every later
  question as failed too

#### Scenario: The user cannot publish

- **WHEN** the authenticated user lacks a capability publishing needs
- **THEN** the check names the capability and exits non-zero

#### Scenario: Only the menu is out of reach

- **WHEN** the user may publish pages but not edit theme options
- **THEN** the check passes, and says the navigation command needs an administrator

#### Scenario: A page already exists at a slug the bundle publishes

- **WHEN** the site holds a page with that slug somewhere else in its hierarchy
- **THEN** the check warns that pushing would adopt and overwrite it, and names its URL

### Requirement: Writes are paced and transient failures retried

The client SHALL support a minimum interval between requests, and SHALL retry a request the
site answered with a transient status, waiting longer each time and honouring `Retry-After`
when the site sends one. It SHALL NOT retry a status that means refusal, and SHALL explain
what causes a refusal on a hosted site.

#### Scenario: The site asks for less

- **WHEN** a request is answered 429
- **THEN** it is tried again after a wait, and the wait doubles on each further attempt

#### Scenario: The site says when to come back

- **WHEN** a transient response carries `Retry-After`
- **THEN** that is waited instead of the calculated backoff

#### Scenario: A refusal

- **WHEN** a request is answered 403
- **THEN** it is not retried, and the error explains that a firewall, a rate limit or a
  missing capability causes this

#### Scenario: Publishing gently

- **WHEN** a pace is configured
- **THEN** every request after the first waits that long before it is sent
