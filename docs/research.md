# Privacy-Gated Public Web Research

Ally can use public web search for current information without making private
conversation state eligible for external disclosure.

The initial concrete provider is Brave Search behind Ally's generic
controlled-egress boundary. The research service itself is provider-neutral.

## Privacy rule

A web-search query is `explicit_outbound`, not automatically `public`.

That distinction is deliberate. A field named `query` can contain private
details even when the destination is a public search engine. Ally does not try
to infer that arbitrary text is safe enough to disclose.

Before any search request:

1. Ally constructs an egress request containing exactly:
   - `query`
   - `count`
2. the trusted adapter classifies:
   - `query` as `explicit_outbound`
   - `count` as `public`
3. inspection exposes only field names/classes and the policy decision;
4. without explicit approval, execution stops before credential access or
   network I/O;
5. after approval, only those declared fields may reach the adapter.

Conversation history, memory, personal knowledge, user instructions, active
runtime profile state, hidden model context, and secrets are not research
request fields.

## Setup

The default Brave Search adapter resolves its API token from the operating
system secret store using this opaque reference:

```text
research.brave.api-key
```

On macOS:

```bash
uv run ally secrets set research.brave.api-key
```

The value is entered through the existing non-echoing Keychain path. It is not
stored in config, SQLite, logs, command arguments, or model context.

## Inspect before disclosure

Inspection performs no network request and does not require the API key:

```bash
uv run ally research inspect "OpenAI latest model release" --json
```

The response contains the service, operation, policy decision, and field
classifications, but not the query value.

## Execute an exact query

Without approval:

```bash
uv run ally research search "OpenAI latest model release"
```

Ally exits before the adapter is called.

After reviewing the exact query:

```bash
uv run ally research search \
  "OpenAI latest model release" \
  --approve
```

The initial interface requires approval per execution. There is no global
"trust all future search queries" switch.

## Result boundary

The Brave adapter normalizes only bounded public result fields:

- title;
- HTTP(S) URL; and
- description/snippet.

It returns at most the requested count, with a hard maximum of 20 results.
Queries are bounded to 600 characters and 75 words.

The adapter caps response bytes, rejects arbitrary non-loopback endpoint
overrides, ignores inherited proxy settings, does not follow redirects, and
reduces failures to safe error classes. Raw remote error bodies are discarded.

Egress audit remains payload-free. It records that a search disclosure happened,
which field classes were involved, the approval state, and the terminal status,
but never the query or returned results.

## Local reasoning after search

Public results return into the Ally process. Any later summarization,
personalization, comparison with memory, or planning should use Ally's local
validated model.

The search provider is not an inference provider and receives no personal model
context implicitly.

## Current limitations

Phase 1 intentionally does not include:

- autonomous multi-query research loops;
- page crawling or arbitrary URL fetching;
- automatic query generation/disclosure from private context;
- remote LLM summarization;
- task-planner integration;
- search-history persistence beyond payload-free egress audit.

Task integration should wait for an approval-aware external-tool execution
context so tool authorization and exact data-disclosure approval remain
independent gates.

## Provider replacement

`ResearchService` depends on the generic `EgressAdapter` contract. Brave is
the default initial transport, not an architectural dependency.

A future search adapter must preserve the same field-classification and
payload-minimization rules.
