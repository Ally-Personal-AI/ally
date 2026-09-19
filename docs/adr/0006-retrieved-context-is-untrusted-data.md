# ADR 0006: Retrieved context is reference data, not instructions

**Status:** Accepted

## Context

Ally will retrieve memories, documents, web results, and tool outputs to ground model responses. Retrieved content can contain stale instructions, quoted prompts, malicious text, or ordinary sentences that resemble commands.

## Decision

All retrieved context crosses an explicit trust boundary before it is supplied to a model.

Context providers return provenance-labelled `ContextBlock` values. Ally renders those blocks inside a system message that states the blocks are reference data and must not be treated as instructions.

Memory V1 uses deterministic lexical retrieval as the first retriever. Embeddings and rerankers may replace or augment ranking later without changing the context contract.

## Consequences

Prompt injection cannot be solved by delimiters alone, but the architecture no longer implicitly treats retrieved text as trusted policy. Future tool, web, and document retrieval can reuse the same context boundary.
