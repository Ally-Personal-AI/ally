# ADR 0045: Final release readiness derives from exact evidence chains

## Status

Accepted

## Context

Ally now has two independently important evidence chains.

The runtime-candidate chain proves capability, functional workflows, runtime
privacy, and a validated runtime profile. The dedicated-machine chain records
empirical Keychain, recovery, signed-app service, notification, release/update,
replacement, and integrated-use acceptance.

A human can compare those artifacts manually, but a tagged release should not
depend on remembering that they belong to the same Ally version, machine, and
selected runtime profile. Conversely, combining them must not create a new
authority capable of selecting a model, signing code, publishing releases, or
replacing applications.

## Decision

Add a final immutable, payload-free release-readiness artifact that is derived
from and cryptographically binds the exact existing evidence.

Creation and verification require:

- current Ally version;
- caller-supplied full Git source revision;
- current hardware/OS profile;
- current hash-bound active validated profile;
- an exact validation session whose candidate artifacts and profile verify; and
- an exact dedicated-machine acceptance artifact bound to the same current
  source/hardware/profile context.

The report records SHA-256 digests of the validation-session manifest,
capability, privacy, workflow, validated-profile, and machine-acceptance
artifacts.

Qualification is conjunctive: the validation session must be currently complete
and machine acceptance must be currently qualified.

The coordinator belongs to diagnostics/evidence code, not the narrow
`ally.release` update-trust package. Code-signing and update verification
therefore do not gain transitive dependencies on runtime validation or profile
state.

## Consequences

- one artifact can answer whether the exact current evidence chain is ready for
  a release gate;
- source changes, profile changes, hardware changes, readiness regressions, and
  evidence tampering fail verification;
- unqualified but internally consistent machine evidence can be retained for
  diagnosis without granting release eligibility;
- no private payloads are needed in the final report;
- hosted CI can test mechanics without becoming machine acceptance; and
- tagging, publishing, signing, downloading, and replacement remain separate
  future authorities.
