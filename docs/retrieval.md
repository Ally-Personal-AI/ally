# Deterministic Retrieval

Ally's first retrieval layer is deliberately local, inspectable, and free of
embedding/model dependencies.

## Current ranking

Memory and personal-knowledge retrieval use a shared deterministic BM25 scorer.

The scorer:

- lowercases and tokenizes ASCII alphanumeric terms;
- removes a small fixed stop-word set;
- preserves repeated document terms for term-frequency scoring;
- computes inverse document frequency from only the bounded candidate corpus;
- applies BM25 document-length normalization; and
- performs no network access, model inference, hidden indexing, or persistent
  side effects.

Knowledge results are ordered by BM25 relevance first, then stable source/chunk
tie-breakers.

Memory results are ordered by BM25 relevance first. Memory importance,
confidence, recency, and ID are tie-breakers only. This prevents a highly
important but weakly related memory from outranking a more query-specific
memory.

## Why BM25 before embeddings

Ally eventually needs semantic/hybrid retrieval, but semantic retrieval should
not silently become another external inference path or introduce an unqualified
embedding model into the private-intelligence boundary.

BM25 improves V1 retrieval immediately while remaining:

- deterministic;
- offline;
- model-independent;
- explainable;
- cheap enough to recompute over the current bounded candidate sets; and
- compatible with future hybrid ranking.

A future embedding layer should add evidence-backed local embedding providers
and combine them with this lexical score rather than deleting the deterministic
fallback.

## Privacy

Retrieval operates only on Ally-owned local memory/knowledge content already
eligible for private context use. No query, memory, chunk, score, or derived
token statistics leave the process.

The scorer has no persistence boundary of its own.
