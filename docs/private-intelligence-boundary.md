# Private Intelligence Boundary

Ally treats personal intelligence as non-exportable inference data.

## Invariant

Private Ally intelligence must not be transmitted to an external inference
provider.

Today, private inference is allowed only through loopback HTTP endpoints on the
same machine. Daily chat, planning, and memory proposal commands resolve the
explicitly selected validated runtime profile before inference. There is
intentionally no CLI, config, or provider-level override that permits private
chat, planning, memory extraction, grounding, or user instructions to use a
non-loopback model endpoint.

Raw model coordinates are available only as an explicit paired development
override for local candidate testing; they remain loopback-only and do not claim
validated-profile provenance.

Future user-controlled nodes may join the Ally trust domain only after Ally has
an explicit authenticated, encrypted trust-domain membership protocol. An
arbitrary LAN host is not trusted merely because it is nearby.

## Protected private intelligence

The protected set includes source data and derived intelligence, including:

- current user prompts;
- persistent conversation history;
- memories and memory proposals;
- personal documents, retrieved chunks, and private indexes;
- durable and session user instructions;
- identity/profile information and personal identifiers;
- embeddings, preference models, relationship graphs, summaries, and other
  derived personal intelligence;
- private task goals, plans, and model-generated proposals; and
- any other data whose meaning depends on the user's private Ally state.

Credentials and secrets are protected even more strictly through the SecretStore
boundary and should not enter ordinary model context.

## External inference versus external actions

This policy does not mean that no information can ever leave Ally.

An explicitly authorized external action may disclose the minimum information
required to perform that action. Sending an email necessarily discloses its
recipient and body to the email service. Fetching a public web page discloses a
network request to that site.

Those are controlled egress operations, not inference.

The intended flow is:

```text
PRIVATE ALLY TRUST DOMAIN

memory ─┐
docs ───┤
history ├──> local model reasoning
profile ┤            │
tasks ──┘            │
                     v
              minimum necessary
                tool request
                     │
──────────── trust boundary ────────────
                     │
                 web / APIs
              email / calendar
```

External services should receive only the data needed for the explicitly
authorized operation, not Ally's hidden memory/profile/context.

## Public remote model evaluation

Ally retains a separately named public-evaluation provider so an operator may
benchmark an external model using the bundled synthetic/public evaluation
fixtures.

Remote public evaluation:

- requires an explicit `--allow-remote-public` flag;
- may use only Ally's bundled frozen provider/behavior suites;
- rejects custom case files before contacting the endpoint; and
- is not used by chat, memory extraction, planning, validation, or private
  grounding.

This path is evidence tooling, not a private inference escape hatch.

## Local runtime caveat

Loopback prevents Ally itself from transmitting prompts to a remote inference
endpoint, but a separately installed model runtime is still software running on
the machine. If that runtime contains telemetry or makes its own outbound
connections, it could undermine the privacy goal independently of Ally.

Therefore a production-qualified Ally runtime must also demonstrate that it can
operate without external network access and must be isolated from unnecessary
egress. Runtime provenance and network isolation are part of the hardware
acceptance/security roadmap.

Until that isolation is validated, the strongest accurate claim is:

> Ally Core sends private inference data only to loopback providers; production
> runtime qualification must additionally verify that the local runtime itself
> does not export that data.

## Design direction

Future network integrations should converge on a controlled egress broker that:

- classifies the destination and operation;
- sends the minimum necessary fields;
- never automatically attaches memory, conversation history, profile, or
  instructions;
- keeps credentials outside model context;
- requires the existing deterministic action-policy path where appropriate; and
- records payload-minimized audit metadata rather than private content.
