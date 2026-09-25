# ADR 0046: macOS release building is local and fail-closed

## Status

Accepted

## Context

Ally already has individually reviewed boundaries for the frozen desktop helper,
application bundle assembly, Developer ID signing, notarization, update trust,
machine acceptance, and final release-readiness evidence.

The remaining release-build procedure required an operator to invoke those
pieces manually in the correct order. That creates avoidable risk immediately
before a release: wrong source revision, dirty checkout, incorrect helper
signing order, skipped readiness verification, stale output replacement, or an
archive that was never re-opened and checked.

Combining the steps must not grant publication or update authority to the build
layer.

## Decision

Add one local macOS release orchestrator with separate `adhoc` and
`production` modes.

Both modes require a clean checkout bound to the supplied full Git revision and
produce output outside the repository.

Production additionally requires the current immutable final release-readiness
artifact to verify before any build output is created.

The orchestrator composes the existing helper, bundle, signing, and notarization
boundaries rather than reimplementing them.

Production outputs are never overwritten. The final archive is extracted and
re-verified, and a path-free metadata file records its SHA-256 plus the exact
release-readiness digest.

The orchestrator has no network publication, Git tag, GitHub release, updater,
runtime-selection, or installed-app replacement authority. The only network
operation in production is Apple's existing notarization submission boundary.

## Consequences

- the reviewed release order becomes deterministic and CI-exercised;
- production builds fail before mutation when readiness/source/checkout
  prerequisites are not satisfied;
- embedded PyInstaller native payloads receive the real Developer ID identity at
  helper-build time;
- published artifacts can later be matched to the exact readiness evidence that
  authorized their build;
- ad-hoc CI remains explicitly non-production; and
- publication remains a separate future/operator action.
