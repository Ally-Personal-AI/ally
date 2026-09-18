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
