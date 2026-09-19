# ADR 0027: macOS secrets use Keychain and a reference-only CLI

**Status:** Accepted; dedicated-machine acceptance pending

## Context

Ally integrations need credentials, but secret material must stay outside
ordinary configuration, SQLite state, portable backups, logs, process
arguments, and model context. The first target machine runs macOS, whose native
credential facility is Keychain. Hosted CI cannot safely validate a real user's
login Keychain or its interactive access prompts.

## Decision

`MacOSKeychainSecretStore` implements the existing `SecretStore` contract using
generic-password items in the current user's default Keychain. The opaque
`SecretRef` name is the item account and an Ally-owned versioned identifier is
the service.

Values are UTF-8 encoded into a versioned, single-line representation before
being supplied to `/usr/bin/security` through the password-prompt input. The
value—raw or encoded—is never a process argument. A separate Keychain item
stores only the sorted reference names so listing does not require dumping the
Keychain or reading every value.

Reference-index changes and value changes are treated as one logical mutation.
If the second change fails, Ally attempts to restore the previous item. A
failed or unconfirmed rollback, malformed Ally item, locked Keychain, denied
access, timeout, or tool failure is an unavailable-store error. Raw backend
diagnostics are not propagated.

The CLI supports `set`, `list`, `check`, and `delete`. `set` uses a non-echoing
interactive prompt; the other commands display only names and status. There is
no value-printing or secret-export command. Unsupported operating systems fail
closed.

## Consequences

Secrets remain under the operating system's credential lifecycle and outside
Ally's database and backup format. Simulated command-boundary tests can cover
round trips, denial, corruption, rollback, redaction, and argument safety on
all CI platforms.

The reference index and value are separate Keychain items, so no true
cross-item transaction exists. Ally restores the prior state on observed
failures, but abrupt process termination between writes may leave an orphaned
value or stale index entry. Direct lookup and deletion remain possible by the
known reference, and a future native Security-framework adapter may provide a
stronger transaction/reconciliation mechanism.

Actual password-prompt transport, OS access prompts, cross-process
persistence, and locked-login-Keychain behavior must pass the dedicated-machine
runbook before this adapter is considered fully accepted for production use.
