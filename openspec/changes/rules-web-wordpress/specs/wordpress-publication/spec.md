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
