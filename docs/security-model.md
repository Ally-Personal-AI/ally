# Security Model

Ally is intended to hold unusually sensitive information and eventually perform
consequential actions. Security therefore begins before agency.

## Initial trust boundaries

1. **Source code** — safe to publish.
2. **Configuration** — local, non-secret settings.
3. **Secrets** — credentials and keys; never committed and never stored in ordinary config.
4. **Personal data** — memory, conversations, files, indexes, and state; never committed.
5. **Model assets** — local or externally downloaded weights; never committed.
6. **Tools** — capabilities with explicit permission scopes.

## Configuration and secret separation

The versioned Ally config document is a strict non-secret schema. Unknown
fields are rejected rather than silently retained.

Integrations refer to credentials by opaque `SecretRef` names and
resolve the values through the `SecretStore` interface only when needed.

The macOS adapter stores values in the current user's default Keychain through
Apple's modern Security-framework item APIs. Its CLI
accepts values only through a non-echoing prompt and exposes set, reference
list, availability check, and delete operations—never value retrieval. Secret
payloads do not enter subprocess arguments, ordinary configuration, SQLite,
logs, backend-derived exception output, or model context. Non-macOS systems and
unavailable, locked, denied, or malformed Keychain state fail closed.

Deterministic tests use a simulated Keychain boundary, while macOS CI exercises
a synthetic item through the real framework on an ephemeral runner. Actual
login-Keychain persistence and OS access-prompt behavior remain a
dedicated-machine acceptance gate; hosted macOS CI is not treated as that
evidence.

Backup V1 excludes both ordinary config and secret material.

## Inference transport

Private inference endpoints are loopback-only and have no remote override.
Chat, conversation history, memory extraction, planning, retrieved personal
context, and user instructions use the private provider.

A separately named public-evaluation provider may contact a remote endpoint only
for Ally's bundled synthetic/public frozen evaluation suites and only after an
explicit `--allow-remote-public` opt-in. Custom case files are rejected for
remote evaluation before network access.

The HTTP adapters ignore inherited proxy and certificate environment settings;
shell configuration cannot silently forward local prompts through a proxy.
Installed-package CI exercises real loopback requests with proxy variables
deliberately present.

Loopback constrains Ally's request destination, but a local model runtime is
still independently executing software. Production runtime qualification must
verify that the selected runtime can operate without external network access and
does not export prompts through telemetry or other egress. That evidence is
stored separately from model-capability results and fails closed when any check
is missing. See [Private Intelligence Boundary](private-intelligence-boundary.md)
and [Runtime Privacy Qualification](runtime-privacy-qualification.md).

## Validation evidence

Local-model validation artifacts contain only synthetic evaluation results,
non-sensitive machine metadata, public model/runtime identifiers, and explicit
operator-supplied settings. Ally does not capture raw process arguments or
environment variables. Runtime parameter names associated with common secret
material are rejected, values are bounded single-line text, and generated
reports stay outside version control by default. Operators must not supply
credentials, private paths, personal prompts, or access-bearing URLs as report
metadata.

## Local filesystem observation

Filesystem observation is explicit and metadata-only. The user selects one
allowlisted directory root per source. The adapter does not read file contents,
does not follow symbolic links, ignores hidden entries by default, and rejects a
symbolic-link root. Relative paths, sizes, and modification times may enter
event payloads; filesystem identity is restricted to the opaque checkpoint for
rename detection.

Scan failures fail closed without advancing the source checkpoint. See
[Local filesystem event source](filesystem-source.md) and
[ADR 0026](adr/0026-filesystem-observation-is-metadata-only.md).

## Controlled external egress

External network actions are a separate security boundary from inference.

Reviewed adapters declare fixed field names and classifications. Callers provide
values but cannot self-classify them. Public fields may cross subject to action
policy; explicitly outbound fields require approval; private-internal and secret
fields are denied as egress payloads.

Credentials are resolved through SecretStore at a trusted adapter edge rather
than copied into model context or egress request fields. Egress audit is
payload-free and records only destination/operation, policy outcome, approval
state, field names/classifications, timestamps, and safe error classes.

Common network transport imports are statically confined to model-provider and
egress packages. See [Controlled External Egress](controlled-egress.md).

Public web research is the first concrete egress integration. Its exact query is
classified `explicit_outbound`, so it cannot leave Ally until explicitly
approved. The research request schema contains no conversation history, memory,
personal knowledge, instructions, runtime profile state, or hidden model
context. The search credential is resolved from Keychain only inside the
network adapter after approval, and egress audit stores neither the query nor
returned results. See [Privacy-Gated Public Web Research](research.md).

## Action classes

Future actions will be classified at minimum as:

- read-only
- reversible
- externally consequential
- high consequence

The policy engine, not a model prompt, is the final authority on whether an
action may execute.

The initial policy is intentionally conservative:

- read-only: allowed
- reversible: explicit approval required
- externally consequential: explicit approval required
- high consequence: denied

Every attempted tool execution is written to a local append-only audit table,
including unknown, denied, approval-required, failed, and successful attempts.

## Design requirements

- least privilege
- auditable actions
- secrets separated from model context unless explicitly required
- sandboxing for untrusted/generated code
- deny-by-default for new consequential capabilities
- data provenance and deletion semantics
- no silent network dependency in local-only operation
