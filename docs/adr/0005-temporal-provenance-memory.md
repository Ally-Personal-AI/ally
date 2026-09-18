# ADR 0005: Durable memories are temporal and provenance-aware

**Status:** Accepted

## Context

A personal AI will accumulate facts that change over time, corrections to earlier beliefs, and information from sources with different reliability. Treating memory as timeless text fragments would make stale or incorrect information difficult to detect and correct.

## Decision

Every durable Ally memory is a structured record with:

- a memory kind
- source provenance
- confidence and importance
- privacy classification
- creation and observation time
- optional validity interval
- explicit supersession history
- explicit retraction history

Memory stores must support historical `as_of` queries so Ally can distinguish what was believed or valid in the past from what is active now.

Automatic LLM-based memory extraction is deliberately excluded from Memory V1.

## Consequences

The memory model is more complex than a vector store, but corrections and changing facts remain inspectable. Future embeddings and graph structures can index these records without becoming the source of truth.
