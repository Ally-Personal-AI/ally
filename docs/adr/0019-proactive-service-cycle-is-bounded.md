# ADR 0019: The proactive service cycle is bounded and daemon-independent

**Status:** Accepted

## Context

Ally now has persisted schedules, events, attention policy, and reliable
attention delivery. Operating systems will eventually need a background service
that invokes those components.

Embedding an infinite loop or platform-specific service manager inside Ally Core
would make scheduling semantics harder to test and couple the runtime to one
deployment environment.

## Decision

Ally exposes one bounded proactive service-cycle operation.

Each cycle:

1. evaluates due schedules;
2. persists resulting events through `EventRuntime`;
3. delivers pending user-facing attention through an explicit ordered set of
   sinks;
4. returns a structured report.

Schedules run before attention delivery so events created in the current cycle
may be delivered immediately.

The caller supplies:

- an explicit timezone-aware evaluation timestamp;
- a schedule evaluation limit;
- a per-sink delivery limit;
- an explicit sink set.

Duplicate sink IDs are rejected.

The cycle has no sleep, retry loop, daemonization, process supervision, or
operating-system integration.

Scheduler consistency failures propagate to the caller rather than being hidden
inside a partial-success report. Individual sink delivery failures remain
persisted through the existing attention delivery subsystem and appear in the
cycle report.

## Consequences

A future macOS launch agent, Linux systemd service, Windows service, test
harness, or manual CLI command can call the same deterministic operation.

Platform service lifecycle code remains outside Ally's scheduling, event, and
attention semantics.
