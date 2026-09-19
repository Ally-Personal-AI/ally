# ADR 0015: Ordinary configuration never contains secret material

**Status:** Accepted

## Context

Ally will eventually integrate with APIs, accounts, devices, and services that
require credentials. Allowing tokens or passwords into ordinary JSON
configuration would make it easy for them to leak through support bundles,
backups, logs, model context, or source control.

## Decision

Ally configuration and Ally secrets are separate domains.

The versioned configuration document is a strict schema containing only
non-secret values. Unknown fields are rejected.

Where future configuration needs a credential, it stores a `SecretRef` name,
not the secret value.

Secret values are accessed through the `SecretStore` protocol. The first
implementation is an ephemeral in-memory backend for tests and development.
Operating-system secure storage (for example macOS Keychain) will implement the
same interface after validation on the target platform.

Secret-store APIs expose secret names separately from values. A secret value is
represented as Pydantic `SecretStr`, whose ordinary string/repr rendering is
redacted.

## Consequences

Config files can be inspected and versioned without containing credentials.
Data backup V1 remains intentionally separate from both config and secrets.
Platform secret storage can evolve without changing integrations that depend on
the `SecretStore` contract.
