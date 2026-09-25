# ADR 0049: Web research requires exact-query disclosure approval

## Status

Accepted

## Context

Ally needs current public information to fulfill the Ally 0.1 research promise,
but web search necessarily discloses a query to an external service.

A search query cannot safely be classified as public merely because it is sent
to a public search engine. Arbitrary query text may contain names, private
facts, personal plans, document content, or other private Ally intelligence.

Automatically deriving and sending search queries from private model context
would therefore violate the rule that private intelligence is not eligible for
implicit external disclosure.

## Decision

Implement web research through the existing controlled-egress boundary.

The trusted search adapter declares:

- `query` -> `explicit_outbound`
- `count` -> `public`

Every search execution requires explicit approval of the disclosure. Inspection
must be possible before credential access or network I/O and must remain
payload-free.

The research service accepts only an exact bounded query and result count. It
does not accept conversation history, memory, personal knowledge, instructions,
profile state, or hidden model context.

Credentials are resolved from `SecretStore` only inside the concrete network
adapter after egress approval.

The first concrete adapter uses Brave Search, but the application research
service remains provider-neutral.

Returned search results are public inputs for subsequent local reasoning. The
external search provider is never treated as a model provider.

## Consequences

- Ally gains current-information lookup without permitting silent context
  leakage;
- searches are less frictionless initially because each query is approval-gated;
- a model may eventually propose a query, but it cannot authorize disclosure;
- payload-free egress audit records the act of disclosure without storing query
  text or results;
- task integration must preserve separate action and data-disclosure approval;
- future adapters can replace Brave without changing the application contract;
  and
- autonomous research loops remain deferred until exact-query privacy controls
  can be preserved across multi-step planning.
