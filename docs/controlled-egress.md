# Controlled External Egress

Ally separates private reasoning from data that is deliberately disclosed to an
external service.

The controlled-egress boundary exists so a future email, calendar, web, API, or
device integration cannot casually serialize model context or Ally's private
state into a network request.

## Two independent gates

Network-capable external actions must pass two separate controls:

1. the existing tool/action policy decides whether the operation is authorized;
2. the egress policy decides whether the declared data is eligible to leave.

A future tool that sends email, changes a calendar, or otherwise creates an
external consequence must use the existing `external_consequence` tool risk
class and the controlled-egress boundary. Passing one gate never bypasses the
other.

## Trusted classification

The caller/model does not classify its own values.

Each reviewed external adapter declares an `EgressOperationSpec` containing
the only allowed field names and their classifications. An `EgressRequest`
contains values only. The executor rejects undeclared fields, missing required
fields, unknown operations, and service mismatches before calling the adapter.

This prevents a model from taking private data and simply labeling it
`public`.

## Data classes

- `public` — non-private data that may cross the boundary without a separate
  data-disclosure approval, subject to the enclosing tool/action policy.
- `explicit_outbound` — content the user intends to disclose, such as an email
  recipient/body. Egress requires explicit approval.
- `private_internal` — Ally-private state. Egress is denied even when approved.
- `secret` — credentials/secret material. Egress fields are denied. Credentials
  must instead be resolved through `SecretStore` inside the trusted adapter
  implementation at the point the external service requires them.

The whole request is denied if any provided field is classified
`private_internal` or `secret`.

## Inspection

`EgressExecutor.inspect()` returns the destination service, operation,
decision, and field names/classifications without field values.

This is intended to support future UI such as:

```text
External action: email.send
Fields leaving Ally:
- recipient    explicit_outbound
- subject      explicit_outbound
- body         explicit_outbound
Decision: approval required
```

## Payload-free audit

Every execution attempt records:

- request ID;
- service and operation;
- policy decision and terminal status;
- whether explicit approval was supplied;
- field names and classifications;
- timestamps; and
- a bounded safe error class when relevant.

The audit table never stores outbound values, remote responses, arbitrary
exception messages, credentials, prompts, memories, documents, or hidden model
context.

## Network architecture guardrail

A static repository test rejects imports of common network transport libraries
outside two reviewed package areas:

- `ally.models.providers`; and
- `ally.egress.adapters`.

The egress models, policy, executor, inspection, and audit packages remain
transport-independent. Concrete email/calendar/web/API transports must live
under `ally.egress.adapters`.

This is a defense against network access gradually appearing in unrelated
commands, tools, skills, memory code, or domain packages.

The guard is not an operating-system sandbox. Executable skills and third-party
native code require their own isolation. It is a source-architecture constraint
for Ally Core.

## External inference remains prohibited

The egress boundary is not an alternate model-provider path.

Private Ally intelligence remains ineligible for external model inference.
Remote model benchmarking remains confined to the separate synthetic/public
evaluation provider described in the private-intelligence boundary.

## Examples

### Public lookup

A reviewed search adapter may declare:

```text
query -> public
```

A locally derived public search phrase can leave Ally. Returned public results
come back to the local model for private personalization.

### Email

A reviewed mail adapter may declare:

```text
recipient -> explicit_outbound
subject   -> explicit_outbound
body      -> explicit_outbound
```

The user must approve disclosure. Memory, profile, instructions, and unrelated
conversation history are not declared fields and are rejected if a caller tries
to add them.

### Credentials

An API token is never declared as an egress field. The adapter receives an
opaque secret reference through trusted configuration and resolves the actual
value from `SecretStore` only inside the transport boundary.
