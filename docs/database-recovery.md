# Database upgrades and recovery

For the first dedicated-machine acceptance sequence, including when to perform
the recovery drill relative to runtime/privacy and OS integration gates, start
with [Unified First-Machine Acceptance](hardware/first-machine-acceptance.md).

Ally's conversation, memory, knowledge, task, and audit state lives in the core
SQLite database. Migration and recovery must preserve that state independently
of the model, runtime, or dedicated hardware.

On POSIX systems, Ally creates or tightens every SQLite database inode to
owner-only `0600` before SQLite opens it. The final database path is opened with
no-follow semantics so a symbolic link cannot redirect that permission boundary.
Ally does not recursively chmod a user-selected parent directory. SQLite
journal/WAL sidecars are expected to inherit a private database mode and are
covered by portability tests.

## Before upgrading Ally

1. Finish or stop running Ally commands and service processes.
2. With the currently installed version, create an archive at a new private path:

   ```bash
   ally --version
   ally data backup /absolute/private/path/before-upgrade.ally-backup
   ally data validate /absolute/private/path/before-upgrade.ally-backup
   ```

3. Keep that validated archive when installing the newer version. Commands from
   a source checkout can use the same arguments after `uv run`.

Backup archives contain personal database state and are not encrypted. Keep them
outside the repository. On POSIX systems Ally creates new backup archives with
owner-only `0600` permissions before any database bytes are written; restored
database destinations use the same owner-only staging/publication rule. Ally does
not change the permissions of an existing destination because existing paths are
never overwritten. Configuration, Keychain secrets, model weights, and the
disposable service lease database are not included.

## Upgrade behavior

Opening a persistent store checks the recorded migration versions **and names**.
Only an exact prefix of the migrations supported by that Ally version is accepted.
Newer versions, gaps, renamed entries, and existing database objects without Ally
history are refused. Ally does not guess a repair or rewrite historical entries.

One SQLite write transaction covers the history check, every pending schema/data
change, and the new history records. A failed upgrade rolls the transaction back,
including `CREATE TABLE` and `ALTER TABLE` changes. Concurrent starters serialize
before checking history. SQLite's bounded lock timeout can still cause a safe
failure when another process holds the database busy; finish that process and retry.

Historical migrations are append-only. A schema change belongs in a new migration,
even before the first tagged release. Tests pin the existing migration names/SQL
and exercise upgrade and restore from every supported prefix using synthetic data.

## If an upgrade is refused or fails

1. Stop repeated automatic retries and preserve the original database. Do not edit
   `ally_schema_migrations`, delete tables, or copy only part of an active database.
2. For an unsupported history, use the compatible Ally version that wrote it, or
   choose a validated backup. Older code cannot downgrade a newer schema.
3. For a migration failure, check directory access, free disk space, and competing
   Ally processes. If it persists, keep the database and archive for diagnosis.
   The CLI returns a safe error with exit code 2 without printing stored payloads.

## Restore a backup

Validate first, then restore to a new path on a local filesystem:

```bash
ally data validate /absolute/private/path/before-upgrade.ally-backup
ally data restore /absolute/private/path/before-upgrade.ally-backup \
  --destination /absolute/private/path/recovered-ally.sqlite3
```

Restore checks archive members, size/hash, SQLite integrity, foreign-key integrity,
and supported migration history. It upgrades a staged copy before publishing the
destination. The input archive is unchanged. A failed validation or upgrade does
not create the destination; normal error cleanup removes staging files.

Backup and restore publish complete files with an atomic create operation. An
existing file, directory, or symbolic link is never overwritten, including a file
created by another writer after the initial check. Restore also refuses leftover
SQLite `-wal`, `-shm`, or `-journal` files at the requested database path. Publication
requires hard-link support on the destination filesystem (tested on Linux and
macOS); unsupported filesystems fail without falling back to an overwrite or a
partial copy. Use a supported local filesystem, then copy a completed archive if
needed. This does not promise survival of arbitrary storage hardware failure.

An explicit `--destination` does not switch Ally's active database. To resume with
the restored state at the default path:

1. Stop every Ally process and use `ally doctor` to find the data directory.
2. Preserve its existing `ally.sqlite3` and any matching SQLite sidecars together
   in a separate private recovery directory. Keep them; do not discard sidecars.
3. Once the default database path and its sidecars are absent, run
   `ally data restore /absolute/private/path/before-upgrade.ally-backup` without
   `--destination`.
4. Inspect `ally conversations list`, `ally memory list`, and `ally service health`
   before resuming normal use. Health may report missing configuration or disposable
   runtime state; those are outside the backup boundary.

For the implementation contract, see [ADR 0029](adr/0029-atomic-database-recovery.md).
