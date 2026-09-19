# ADR 0007: Personal knowledge sources are versioned and provenance-preserving

**Status:** Accepted

## Context

Ally will ingest user-controlled documents that can change over time. Overwriting a document's prior chunks would make it impossible to explain which version informed an earlier answer or to reason about historical state.

## Decision

Knowledge V1 stores three separate concepts:

- a stable source identity
- immutable source revisions
- immutable chunks belonging to a revision

Re-ingesting unchanged content reuses the current revision. Re-ingesting changed content creates a new revision and makes it current.

Plain-text ingestion is deterministic and stores character offsets plus SHA-256 hashes for source and chunk integrity.

Retrieved knowledge enters model prompts through the same untrusted-reference context boundary used by memory grounding.

## Consequences

Knowledge storage is slightly more complex than a flat vector index, but source history remains explicit and later embedding indexes can be rebuilt without becoming the source of truth.
