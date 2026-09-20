# ADR 0029: Database upgrades are atomic and recovery never replaces a destination

**Status:** Accepted

## Context

Editable and installed workflow tests covered successful persistence, but failure
tests exposed three gaps: SQLite DDL could survive a failed migration, an older
Ally version could accept a newer migration history, and an existence check followed
by file replacement could overwrite a concurrent writer's backup or database.

This decision strengthens the guarantees in ADR 0004 and ADR 0014 without changing
the database schema or backup archive format.

## Decision

- Acquire `BEGIN IMMEDIATE` before inspecting migration history. Commit all pending
  SQL and history rows together; roll back the entire batch on failure.
- Accept only the known prefix of migration version/name pairs. Refuse unknown,
  incomplete, renamed, and newer histories before running migration SQL. Refuse
  adoption of database objects that have no Ally history.
- Treat historical migration definitions as append-only. Pin their names and SQL
  fingerprints in tests; test upgrade and restore from every existing prefix.
- Validate backup schema names as well as versions, and run SQLite foreign-key
  checks alongside integrity/hash checks. Inspect extracted snapshots read-only.
- Migrate only a staged restore copy before publishing it. Backup/restore create
  the final name with a same-filesystem hard link, then remove the staging name.
  A collision fails; neither replacement nor a non-atomic copy is a fallback.
- Refuse symbolic-link destinations, including dangling links, and refuse restore
  destinations with leftover SQLite sidecars. Surface errors without private data.

## Consequences

Concurrent startup is serialized and may safely time out behind a long-running
writer. Failed upgrades remain retryable. A historical backup remains unchanged
even if its staged upgrade fails. Existing destination files remain untouched.

The default SQLite transaction mode is explicit because Python's default may
change. Filesystems without hard links cannot publish archives/restores directly;
use a supported local filesystem. Atomic publication does not guarantee recovery
from arbitrary hardware/storage failure, and archives still require private storage.

The [recovery runbook](../database-recovery.md) explains operator steps. Model
benchmarks and dedicated-machine acceptance remain separate gates.

## References

- [Python sqlite3 transaction control](https://docs.python.org/3.12/library/sqlite3.html#transaction-control)
- [SQLite transactions](https://www.sqlite.org/lang_transaction.html)
- [SQLite foreign-key checks](https://www.sqlite.org/pragma.html#pragma_foreign_key_check)
- [Python hard-link creation](https://docs.python.org/3/library/os.html#os.link)
