## ADDED Requirements

### Requirement: Sync records the resolved ruleset pin

`publisher.sync` SHALL write a lock file recording exactly which upstream ruleset a clone
produced, so that any later build can be reproduced and any output can be traced back to its
source.

The lock file SHALL be written to `source/studcraft.lock.json`, SHALL be tracked in git, and
SHALL contain at least: the repository URL, the requested revision, the resolved commit SHA,
and the ruleset version.

#### Scenario: Lock file written on a successful clone

- **WHEN** `python -m publisher.sync` completes a clone
- **THEN** `source/studcraft.lock.json` exists and contains the repository URL, the requested
  revision, the resolved 40-character commit SHA, and the ruleset version

#### Scenario: Lock file reflects an explicit revision

- **WHEN** `python -m publisher.sync --rev v0.2.0` completes
- **THEN** the lock file's requested revision is `v0.2.0` and its commit SHA is the commit
  that revision resolved to

#### Scenario: Clone failure leaves no stale pin

- **WHEN** the clone fails
- **THEN** the lock file is not rewritten and the command exits non-zero

### Requirement: Ruleset version is read from the documents

The ruleset version SHALL be read from the `**Version:**` header of the ruleset documents,
not from git tags. The clone is shallow and carries no tags, so git-based version discovery
is not available.

Every ruleset document SHALL agree on the version. A disagreement is an upstream defect and
SHALL fail rather than be resolved silently.

#### Scenario: Version extracted from document headers

- **WHEN** the pinned clone's documents all declare `**Version:** 0.2.0 Draft`
- **THEN** the lock file records the ruleset version `0.2.0 Draft`

#### Scenario: Documents disagree on the version

- **WHEN** two documents in the clone declare different `**Version:**` values
- **THEN** the command fails with an error naming the conflicting documents and versions

#### Scenario: No version header found

- **WHEN** no document in the clone declares a `**Version:**` header
- **THEN** the command fails with an error rather than recording an empty version

### Requirement: Builds read the pin, never the working clone's HEAD

Any build that consumes the ruleset SHALL verify that the clone on disk is at the commit
recorded in the lock file, and SHALL refuse to run when it is not.

This makes a bump of the pinned ruleset a reviewed change to a tracked file, rather than a
side effect of whenever someone last ran `sync`.

#### Scenario: Clone matches the pin

- **WHEN** a build runs and the clone's `HEAD` equals the lock file's commit SHA
- **THEN** the build proceeds

#### Scenario: Clone drifted from the pin

- **WHEN** a build runs and the clone's `HEAD` differs from the lock file's commit SHA
- **THEN** the build fails with an error naming both SHAs and telling the operator to re-run
  `publisher.sync`

#### Scenario: No clone present

- **WHEN** a build runs and `source/studcraft/` does not exist
- **THEN** the build fails with an error telling the operator to run `publisher.sync`
