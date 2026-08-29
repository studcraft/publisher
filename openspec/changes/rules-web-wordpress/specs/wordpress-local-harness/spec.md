## ADDED Requirements

### Requirement: A disposable WordPress runs locally

The repository SHALL provide a Docker Compose stack that brings up a WordPress site and its
database on the developer's machine, and a bootstrap script that installs and configures the
site. Both SHALL be safe to run repeatedly: a second run SHALL repair the site rather than
duplicate anything.

#### Scenario: A cold start

- **WHEN** `docker compose up -d` and `./bootstrap.sh` run against empty volumes
- **THEN** WordPress is installed, reachable, and configured, and the script reports the
  site URL and credentials

#### Scenario: Running bootstrap again

- **WHEN** `./bootstrap.sh` runs against an already-installed site
- **THEN** it completes without creating a second user or a second installation

#### Scenario: Starting over

- **WHEN** `docker compose down -v` runs
- **THEN** the database and WordPress files are discarded, and the next cold start yields a
  site with no history

### Requirement: The local site runs stock WordPress with no plugins

The harness SHALL install no plugin, must-use plugin or theme code. Every capability the
publication depends on SHALL be provided by WordPress core.

#### Scenario: The site is inspected

- **WHEN** the local site's plugin list is read
- **THEN** no plugin is active

#### Scenario: Publication needs something core does not provide

- **WHEN** publishing to the local site would require installing a plugin
- **THEN** that is recorded as a finding against the design rather than satisfied by
  installing one

### Requirement: The local site is configured for the published URL scheme

Bootstrap SHALL set the permalink structure to `/%postname%/`, because the publication is a
slug hierarchy that the default permalink cannot express. It SHALL create a user with the
editor role, so the staged publication can be reviewed by someone who is not an
administrator.

#### Scenario: A pretty permalink resolves

- **WHEN** a published page is requested at its slug path
- **THEN** the site returns it, rather than a 404

#### Scenario: An editor reviews the staged publication

- **WHEN** the editor user requests a page with status `private`
- **THEN** the page is served to them, while an anonymous request for it returns 404

### Requirement: The harness issues the credentials the publisher uses

Bootstrap SHALL issue a WordPress application password and write it, with the site URL and
user, to a git-ignored file that the publisher reads. The site's own login credentials SHALL
NOT be treated as secrets, and the harness SHALL NOT be presented as a model for the
production site's configuration.

#### Scenario: Credentials are written

- **WHEN** `./bootstrap.sh` completes
- **THEN** a git-ignored `.env` holds the site URL, the user and a freshly issued
  application password

### Requirement: The harness does not depend on a fixed port

The published port SHALL be configurable, and the site's stored URL SHALL follow it, so that
a port already in use on the developer's machine does not require editing tracked files.

#### Scenario: The default port is taken

- **WHEN** the stack is started with an overridden port
- **THEN** the site is reachable on that port and its stored URL matches it

### Requirement: The end-to-end run is documented, not gated

The Docker run SHALL be documented as a local command. It SHALL NOT be a required status
check, because it needs Docker and a database that the required job does not have.

#### Scenario: CI runs the required checks

- **WHEN** the required check runs on a pull request
- **THEN** it does not start Docker, and its result does not depend on the harness
