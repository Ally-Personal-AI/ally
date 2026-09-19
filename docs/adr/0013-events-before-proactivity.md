# ADR 0013: Proactivity begins with persisted deterministic events

**Status:** Accepted

## Context

A proactive assistant needs to notice changes without turning every event into a
model call, notification, or autonomous action. Attention decisions must remain
inspectable and conservative before model-based classification is introduced.

## Decision

Ally represents observed changes as typed persisted events.

Each event has:

- a stable event type;
- an explicit source;
- an explicit importance class;
- JSON payload data;
- a deterministic attention decision;
- creation and optional handled timestamps.

The initial importance-to-attention mapping is:

| Importance | Attention |
| --- | --- |
| noise | ignore |
| routine | remember |
| important | mention_later |
| urgent | notify |
| critical | interrupt |

The `act` attention class exists in the domain model for future programmable
policy, but the default policy never emits it.

Events are persisted before any registered handler is called. Ignored events are
still auditable but are not dispatched.

## Consequences

Future schedulers, integrations, sensors, tools, and model classifiers can all
produce the same event type without changing the attention or persistence
boundary. Proactivity can evolve independently from inference quality.
