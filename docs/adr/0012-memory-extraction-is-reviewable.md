# ADR 0012: Model memory extraction produces reviewable proposals

**Status:** Accepted

## Context

Long-term memory is one of Ally's highest-trust subsystems. Automatically
writing model-inferred memories would let extraction errors, prompt injection,
or transient statements silently become durable personal state.

## Decision

Model-based extraction produces a serializable proposal bundle only.

The caller fixes source provenance and privacy before inference. The model may
propose only memory kind, content, confidence, and importance. The proposal
bundle records the provider/model identity and a SHA-256 digest of the source
text.

Proposing memory never writes to the memory store.

A separate human-invoked acceptance command may write explicitly selected
proposal indices. Accepted records use the caller-supplied source provenance
and privacy classification.

Source text is presented to the model as untrusted reference data, not
instructions.

## Consequences

Memory quality can be evaluated against real local models without granting
automatic memory authority. Users can inspect exactly what would become
durable state before accepting it.
