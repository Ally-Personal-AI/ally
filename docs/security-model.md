# Security Model

Ally is intended to hold unusually sensitive information and eventually perform
consequential actions. Security therefore begins before agency.

## Initial trust boundaries

1. **Source code** — safe to publish.
2. **Configuration** — local, non-secret settings.
3. **Secrets** — credentials and keys; never committed.
4. **Personal data** — memory, conversations, files, indexes, and state; never committed.
5. **Model assets** — local or externally downloaded weights; never committed.
6. **Tools** — capabilities with explicit permission scopes.

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
