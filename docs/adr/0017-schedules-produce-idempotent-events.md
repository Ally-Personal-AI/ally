# ADR 0017: Schedules produce idempotent events

**Status:** Accepted

## Context

Ally needs time-based proactivity, but scheduling must not become a parallel
automation engine that bypasses persisted events, attention policy, task
permissions, or audit boundaries.

A local machine may also sleep or reboot for long periods. Naively replaying
every missed interval after restart could create notification storms.

## Decision

The first scheduler supports:

- one-shot schedules;
- fixed-interval schedules;
- timezone-aware first-run timestamps;
- explicit event type, importance, and JSON payload;
- persisted enable/disable and next/last-run state.

The scheduler is only an event source. A due schedule is converted into a
`NewEvent` and published through the existing `EventRuntime`.

There is no background daemon in this phase. An explicit deterministic
`scheduler tick` operation evaluates due schedules.

### Missed intervals

If an interval schedule is overdue for multiple occurrences, one event is
emitted. Its metadata records the number of coalesced occurrences. The next run
is advanced to the first interval strictly after the tick timestamp.

This avoids event storms after downtime while preserving evidence that multiple
occurrences elapsed.

### Crash/retry behavior

Scheduled events carry a stable dedupe key derived from:

- schedule ID;
- the schedule's due timestamp.

SQLite enforces uniqueness for non-null event dedupe keys.

If an event is persisted and Ally stops before the schedule state advances, a
later tick reuses the existing event and then advances the schedule. This makes
that retry path idempotent.

Schedule advancement uses compare-and-set against the expected due timestamp.
If another process or state change advances the schedule first, stale
advancement fails closed.

### One-shot completion

A one-shot schedule disables itself and clears `next_run_at` after it fires.
Completed one-shot schedules cannot simply be re-enabled; a new schedule must be
created.

## Consequences

Time-based proactivity now has a persisted deterministic substrate independent
of model quality or hardware-specific inference.

Future OS launch agents, service daemons, calendar integrations, and other event
sources may call the same scheduler/event boundaries rather than inventing new
execution paths.

Cron-like calendars, timezone recurrence rules, automatic tool execution, and
model-driven attention remain out of scope.
