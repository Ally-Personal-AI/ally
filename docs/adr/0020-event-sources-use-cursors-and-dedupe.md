# ADR 0020: External event sources use persisted cursors and stable dedupe IDs

**Status:** Accepted

## Context

Calendar, email, filesystem, weather, deployment, and device integrations will
eventually observe changes outside Ally.

If each integration owns event persistence, checkpoints, retries, and crash
recovery, proactive behavior becomes inconsistent and difficult to audit.

## Decision

External integrations implement a pull-based `EventSource` protocol.

A source has a stable validated source ID. Each poll receives:

- the source's last successful opaque cursor;
- a bounded observation limit.

It returns validated observations and the next opaque cursor.

Every observation contains a stable external ID plus Ally event type,
importance, and JSON data.

`EventSourceRuntime` owns publication. It converts each observation into an
ordinary `NewEvent` and publishes through `EventRuntime`.

The persisted event dedupe key is:

```text
source:<source-id>:<external-id>
```

The source checkpoint advances only after all returned observations have been
published.

If Ally stops after event persistence but before cursor advancement, the next
poll receives the old cursor. The source may return the same observations;
event dedupe reuses the existing event records and checkpoint advancement can
then complete safely.

A source that returns observations must advance its cursor. Duplicate external
IDs within one poll are rejected.

Source failures do not advance the checkpoint.

## Reference implementation

A local JSONL source is provided only as a deterministic development/reference
adapter. It treats the explicit file as append-only test data and uses the
consumed physical line count as its opaque cursor. It rejects a cursor beyond a
truncated file but does not attempt to detect edits to already-consumed lines.

It executes no file content.

## Consequences

Future integrations implement observation retrieval only. They do not write
Ally database tables directly and do not bypass attention or task policy.

Push/webhook sources can later adapt inbound messages into the same observation
and dedupe semantics without changing the event model.
