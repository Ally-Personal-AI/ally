# ADR 0014: User data backups are versioned and self-validating

**Status:** Accepted

## Context

Ally's memory, conversations, knowledge, task state, event history, and audit
records are user-owned state. Portability cannot depend on a vendor service or
an undocumented filesystem copy.

## Decision

Backup archive V1 is a ZIP file containing exactly:

- `manifest.json`
- `ally.sqlite3`

The database file is a consistent SQLite backup snapshot. The manifest records
the archive schema version, Ally version, creation time, database byte size,
SHA-256 digest, and applied Ally database schema versions.

Validation checks:

- exact V1 archive members;
- manifest schema;
- database size and SHA-256;
- SQLite `PRAGMA integrity_check`;
- schema versions against the manifest;
- rejection of database schema versions newer than the running Ally supports.

Restore refuses to overwrite an existing database. Older supported backups are
migrated forward only after validation and before atomic placement at the target
path.

Backup V1 intentionally excludes model weights, caches, logs, configuration,
and secrets. Those have separate ownership and security lifecycles.

## Consequences

Users can preserve and move core Ally state without the Ally company or a cloud
service. The archive is inspectable with standard ZIP and SQLite tooling, and
future archive versions can evolve explicitly.
