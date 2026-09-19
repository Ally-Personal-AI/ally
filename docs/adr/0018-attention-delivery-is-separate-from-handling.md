# ADR 0018: Attention delivery is separate from event handling

**Status:** Accepted

## Context

Ally needs to surface proactive events through multiple future interfaces:
terminal, desktop notifications, mobile, voice, and others.

Displaying an event is not the same as the user acknowledging or resolving it.
Delivery also has its own reliability problem: an external notification API may
succeed immediately before Ally crashes, leaving local state uncertain.

## Decision

Persisted events remain the source of truth.

User-facing attention delivery is a separate subsystem. The initial delivery
classes are:

- `mention_later`
- `notify`
- `interrupt`

`ignore` and `remember` are not user-facing delivery classes. `act`
belongs to the action/permission subsystem and is explicitly excluded from this
delivery runtime.

Each sink has a validated stable sink ID and declares which user-facing
attention classes it accepts.

Ally persists at most one delivery record for each `(event_id, sink_id)` pair.

- failed delivery attempts increment an attempt counter and may retry;
- successful delivery is terminal for that sink and is not sent again;
- successful delivery does **not** mark the event handled.

A sink receives a stable delivery key:

```text
attention:<sink-id>:<event-id>
```

External sinks should use that key for their own idempotency when the underlying
platform permits it. Ally cannot guarantee exactly-once external side effects
when a platform provides no idempotency mechanism.

Pending event queries are paged so successfully delivered-but-unhandled events
cannot permanently hide newer events.

For privacy, persisted delivery failures record only the exception class rather
than arbitrary exception text, which could contain credentials or personal
data.

## Initial implementation

The first sink is a development-only console sink.

There is no operating-system notification integration, mobile delivery, or
voice delivery yet. Those interfaces must implement this sink boundary rather
than reading and mutating event state directly.

## Consequences

Attention policy, event persistence, interface delivery, and user
acknowledgement remain independently inspectable.

A notification can be delivered on several interfaces without changing whether
the user has handled it, while each interface retains its own durable retry
history.
