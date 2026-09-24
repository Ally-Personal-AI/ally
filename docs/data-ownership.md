# Data Ownership

Ally's personal data belongs to the user.

## Commitments

- Core operation must not upload personal prompts, conversation history, memory, documents, instructions, identifiers, or derived private intelligence to an external AI inference provider.
- Local-only operation must remain a supported mode.
- Personal runtime data is stored outside the source repository.
- Core database state can be exported without a cloud service.
- Backup formats are versioned, documented, and based on standard ZIP, JSON, and SQLite.
- Backup validation verifies hashes, SQLite integrity, and schema compatibility before restore.
- Restore refuses to overwrite an existing database.
- Database upgrades commit together and refuse incompatible migration history.
- Replacing a model provider must not require replacing personal memory.
- Removing an optional integration must not make core personal data inaccessible.
- External services may add explicitly authorized tools or data sources, but they are not permitted to become processors of private Ally model context.

## Backup boundary

Archive V1 contains only the consistent Ally SQLite snapshot and its manifest.
It intentionally excludes secrets, downloaded model weights, caches, logs, and
ordinary configuration. Those assets have separate portability and security
lifecycles.

Ordinary configuration is intentionally non-secret. Secret material is stored
through a separate `SecretStore` backend and is never part of the database
backup format.

The project should prefer user portability over artificial lock-in.

See the [database recovery runbook](database-recovery.md) for upgrade preparation,
safe failure handling, and restoring to a new path.
