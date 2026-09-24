# ADR 0034: Private Ally intelligence is not eligible for external inference

**Status:** Accepted

**Supersedes:** the remote-inference opt-in portion of
[ADR 0003](0003-local-inference-over-http.md).

## Context

Ally stores unusually sensitive source data and derived personal intelligence.
A hosted inference provider must receive plaintext request content in order to
perform inference, regardless of whether transport is encrypted.

The previous architecture disabled remote inference by default but allowed an
explicit remote override, with a second override for private grounding. That
still permitted current prompts and conversation history to reach an external
provider and was weaker than Ally's intended privacy guarantee.

## Decision

Private model inference is restricted to the user-controlled Ally trust domain.

For the current implementation, the trust domain for HTTP inference is
loopback-only. The normal OpenAI-compatible provider has no remote override.
Chat, conversation history, memory extraction, planning, personal grounding,
and user instructions all use that private provider.

A separately named public-evaluation provider may contact a remote endpoint only
with explicit opt-in. Remote evaluation accepts only Ally's bundled
synthetic/public frozen suites; custom case files are rejected before any
network request.

Configuration rejects non-loopback private inference endpoints. Legacy
remote-private opt-in fields set to true fail closed; old false values are
accepted only for configuration compatibility.

External actions remain a separate policy domain. Explicitly authorized tools
may disclose the minimum data necessary to an external service without making
that service an Ally inference provider.

## Consequences

An external model vendor is not part of private Ally inference and should not
receive personal prompts, history, memory, documents, instructions, identifiers,
or derived private intelligence.

Future distributed Ally nodes require an explicit authenticated/encrypted trust
membership design before they may process private intelligence.

Loopback alone does not constrain outbound connections made independently by a
local model runtime. Production runtime qualification must therefore add
no-egress/telemetry validation and isolation before Ally claims end-to-end
private inference for a selected runtime.
