# Memory Model

Memory is a first-class Ally subsystem, not a transcript search feature.

## Planned memory classes

- **Working memory** — temporary context for the current task.
- **Episodic memory** — events, conversations, outcomes, and experiences.
- **Semantic memory** — durable facts about the user's world.
- **Procedural memory** — learned ways of performing recurring work.
- **Preference memory** — user-specific choices and interaction preferences.
- **Relational memory** — connections among people, places, projects, assets, and events.

## Required metadata

Durable memory records should be capable of retaining:

- source/provenance
- creation time
- observed/effective time
- confidence
- importance
- privacy classification
- related entities
- validity interval
- supersession/correction history

## Temporal correctness

Ally must distinguish “was true” from “is true.” Contradictory observations
should not simply accumulate as timeless facts.

## User control

Users must be able to inspect, correct, remove, export, and explain important
memories.


## Model-assisted formation

Model-assisted memory formation is a review workflow, not an automatic write
path.

`ModelMemoryProposer` receives explicit source text plus caller-controlled
provenance and privacy. The model may propose only:

- memory kind
- content
- confidence
- importance

The resulting proposal bundle records the provider/model identity and a SHA-256
digest of the reviewed source text. It does not store the raw source text.

Proposal generation never writes to `MemoryStore`. A user must explicitly
accept one or more proposal indices before those candidates become
`NewMemory` records.

This separation lets Ally evaluate and improve memory extraction quality without
allowing model mistakes or prompt injection to silently become durable state.
