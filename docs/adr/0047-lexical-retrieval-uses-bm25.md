# ADR 0047: Lexical retrieval uses deterministic BM25 relevance

## Status

Accepted

## Context

Ally's initial memory and knowledge retrieval ranked candidates by unique-token
overlap. Memory retrieval also added a fixed importance bonus to that overlap.

That approach is simple, but it cannot distinguish rare terms from common terms,
ignores repeated evidence within a document, ignores document length, and can
allow importance to compensate for weak lexical relevance.

Ally needs better retrieval before long-term memory grows substantially, but a
semantic embedding stack would introduce model/runtime choices that have not yet
been qualified on the dedicated machine.

## Decision

Use one shared, in-process BM25 scorer for both memory and knowledge retrieval.

The implementation keeps the existing bounded candidate scans and tokenization
privacy boundary. It adds term frequency, inverse document frequency, and
document-length normalization without adding persistence, network access, model
inference, or external dependencies.

For memory retrieval, BM25 relevance is authoritative. Importance, confidence,
recency, and ID are deterministic tie-breakers only.

The existing `lexical_tokens` API remains available for callers that need
unique normalized terms; a separate ordered term API preserves repeated terms
for BM25.

## Consequences

- query-specific memories/documents rank more accurately as corpora grow;
- rare query terms receive more weight than ubiquitous terms;
- highly important but weakly relevant memories cannot outrank stronger lexical
  matches merely because of importance;
- retrieval remains reproducible and explainable;
- frozen/local tests can exercise the exact scorer without a model; and
- future local semantic retrieval can be layered as hybrid evidence rather than
  replacing the deterministic fallback.
