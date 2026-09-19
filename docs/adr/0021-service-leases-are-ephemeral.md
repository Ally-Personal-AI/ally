# ADR 0021: Service coordination leases are ephemeral runtime state

**Status:** Accepted

## Context

Future background service invocations may overlap because of retries, scheduler
configuration, manual commands, or operating-system service managers.

Ally's event and schedule paths are designed to recover safely, but concurrent
attention delivery can still produce duplicate external side effects when a
sink cannot enforce the provided idempotency key.

Coordination state is not personal history and should not become part of
portable backups.

## Decision

Bounded service operations use short-lived named leases before producing side
effects.

Leases are stored in a separate disposable runtime SQLite database:

```text
<data-dir>/runtime/service.sqlite3
```

They are not stored in `ally.sqlite3` and therefore are not included in Ally
backup V1.

A lease contains:

- stable lease name;
- random owner UUID;
- acquisition timestamp;
- expiry timestamp;
- update timestamp.

Acquisition runs under SQLite `BEGIN IMMEDIATE`.

A non-expired lease owned by another process blocks acquisition. Expired leases
may be taken over atomically. Renewal is allowed only by the current owner while
the lease remains unexpired.

Release deletes only a matching name/owner pair, so an expired process cannot
accidentally release a lease that a new process has taken over.

The first protected operation is the proactive service cycle.

## Consequences

Future launchd/systemd/Windows wrappers can safely invoke the same bounded
service command without deliberately overlapping work.

The lease database may be deleted without losing personal state. A crashed
process recovers automatically after lease expiry.

Long-running future services may add heartbeat renewal without changing the
lease ownership model.
