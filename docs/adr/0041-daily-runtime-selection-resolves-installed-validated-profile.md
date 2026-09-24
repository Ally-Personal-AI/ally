# ADR 0041: Daily runtime selection resolves from an installed validated profile

**Status:** Accepted

## Context

Validated runtime profiles turn qualification evidence into one immutable
Ally-owned runtime/model object. Future daily-use composition still needs a safe
way to retain more than one validated profile and explicitly choose which one is
active.

Storing raw endpoint/model values as the production selection would recreate a
path around qualification. Simply storing a profile filename would also be
insufficient because the installed profile could be modified after selection.

## Decision

Ally maintains a non-secret runtime-profile catalog under its configuration
directory.

A profile may be installed only after it re-verifies against its exact
capability, privacy, and functional-workflow evidence.

Installed profile filenames are deterministic from the profile ID. Active
selection stores only:

- the profile ID;
- SHA-256 of the exact installed profile bytes; and
- the selection timestamp.

Resolving the active profile requires:

1. a valid active-selection document;
2. an installed profile with the selected ID;
3. a valid strict `ValidatedRuntimeProfile`; and
4. an exact SHA-256 match with the bytes that were selected.

Selection and catalog operations never contact a model or mutate personal
conversation/memory/knowledge state.

An active profile cannot be removed until it is explicitly deselected.

## Consequences

Future production chat, planning, UI, background services, and model routing can
depend on one reusable active-profile resolver rather than accepting arbitrary
production endpoint/model strings.

Development and validation commands may continue to accept explicit loopback
endpoint/model values because they are the mechanism by which new candidates
are tested before qualification.

The catalog is not a substitute for OS account security. A local attacker able
to rewrite both the catalog and its selection state is outside this integrity
check; the purpose here is to prevent accidental/stale/tampered selection
inside Ally's normal trust boundary.
