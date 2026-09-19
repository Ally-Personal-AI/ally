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
