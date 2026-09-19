# ADR 0022: Service lifecycle history is portable and payload-free

**Status:** Accepted

## Context

ADR 0021 establishes that cross-process service coordination leases are
ephemeral runtime state. Ally also needs durable answers to different questions:

- did the last proactive cycle finish;
- did delivery degrade;
- did a cycle raise;
- was a previous process interrupted;
- is the user-owned database structurally healthy.

Those answers should survive restart and backup, but they must not turn
coordination state into portable personal state or duplicate private event data.

## Decision

The two concerns remain separate.

### Ephemeral coordination

The proactive command first acquires the ADR 0021 lease from the disposable
runtime database. The lease is the authority for overlap protection.

### Portable lifecycle history

Only after the lease is acquired, `ProactiveServiceRunner` records lifecycle
history in `ally.sqlite3`.

A lifecycle record contains only:

- run ID;
- status;
- requested observation timestamp;
- start/finish timestamps;
- schedule and delivery counts;
- a safe exception class for failed/interrupted runs.

It never copies event payloads, prompts, document contents, notification bodies,
arbitrary exception messages, credentials, or model output.

Statuses are:

- `running`
- `succeeded`
- `degraded`
- `failed`
- `interrupted`

If a newly lease-protected process finds a previous portable `running` record,
it may mark that record `interrupted` before starting its own history record.
This repair is safe because ephemeral lease acquisition has already established
the caller as the current coordinator.

The portable table also enforces at most one `running` row. That is a data
consistency guard, not the cross-process locking mechanism.

### Health

Health inspection is read-only. It checks:

- SQLite `quick_check` for the user-owned database;
- applied migrations against the schema expected by the code;
- the latest portable lifecycle record;
- whether the separate runtime database is readable;
- whether the `proactive-cycle` lease is currently active.

A portable `running` record with an active lease can be healthy. A portable
`running` record without an active lease is degraded.

A valid, current database with no lifecycle history is `uninitialized`.

## Consequences

Portable backups include service lifecycle history because it is user-owned
operational history. They continue to exclude ephemeral lease state.

Future launchd/systemd/Windows wrappers can use the same lease-protected service
command and read-only health contract without inventing new lifecycle semantics.
