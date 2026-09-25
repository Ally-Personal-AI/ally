# macOS Release Security and Update Trust Model

Ally's macOS release must preserve the same local/private trust boundary as the
rest of the system. Packaging is therefore part of the security model, not only
a distribution concern.

## Stable application identity

The desktop bundle identifier is:

`ai.ally.personal`

That identifier is treated as stable release identity because macOS associates
system permissions, including notification authorization, with the installed
application identity and signature.

Changing it later is a migration, not a cosmetic rename.

## Release bundle layout

The current release contract is:

```text
Ally.app/
  Contents/
    Info.plist
    MacOS/
      AllyDesktop
    Helpers/
      ally-desktop-bridge
    Resources/
      release-manifest.json
```

The Swift executable never searches `PATH` for its release helper.

Debug/development builds may use the explicit absolute
`ALLY_DESKTOP_BRIDGE` override. Release-mode helper resolution ignores that
environment variable and resolves only the helper inside the application bundle.

## Signed helper binding

The release manifest is part of the signed outer application bundle and records:

- manifest schema version;
- stable bundle identifier;
- exact Ally package version;
- positive monotonically comparable build number;
- exact desktop bridge protocol version;
- supported Ally database schema version;
- fixed relative helper path;
- SHA-256 of the **signed helper bytes**; and
- optional full Git source revision.

The signing order is deliberate:

1. assemble the unsigned app bundle;
2. validate bundle structure and manifest contract;
3. sign the embedded helper;
4. recompute the helper SHA-256 from the signed bytes;
5. update the release manifest with that digest;
6. validate the manifest again;
7. sign the outer application bundle; and
8. verify the complete code signature.

At runtime, release-mode Swift verifies the manifest and helper hash before the
helper is launched.

The main application executable is protected by the outer Apple code signature.
It is not hashed into its own manifest because code signing changes executable
bytes and a self-referential post-sign hash would not be stable.

## Code-signing boundary

A distributable build must use an Apple Developer ID Application certificate and
the hardened runtime.

The repository does not contain signing certificates, private keys, passwords,
Apple IDs, App Store Connect API secrets, or notarization credentials.

The signing helper accepts only the public signing identity name.

Notarization accepts only a pre-existing `notarytool` Keychain profile. The
script intentionally has no command-line options for Apple ID passwords or API
private-key material.

A future CI release workflow may import signing credentials into an ephemeral
macOS Keychain through protected release-environment secrets, but must still
invoke the repository signing/notarization boundary without putting those
secrets into process arguments, logs, manifests, or artifacts.

## Notarization boundary

After Developer ID signing:

1. verify the local code signature;
2. archive the full `.app` with `ditto`;
3. submit with `xcrun notarytool --keychain-profile ... --wait`;
4. staple the notarization ticket;
5. validate the staple; and
6. run Gatekeeper assessment with `spctl`.

Hosted CI now exercises the real frozen helper, bundle structure, and ad-hoc
signing path. Ad-hoc signing is test evidence for helper/bundle mechanics; it is
not a distributable or notarized release.

## Standalone helper

The bundle assembler accepts the prebuilt executable
`ally-desktop-bridge`.

The release path now builds that helper as a self-contained one-file macOS
executable using the minimal
`scripts/ally_desktop_bridge_entry.py` entry point and
`scripts/build_macos_desktop_helper.py`.

Hosted macOS CI currently pins PyInstaller 6.22.3 and
`pyinstaller-hooks-contrib` 2026.7, then verifies the resulting binary by
running `bridge.info` and `bootstrap` with a sanitized environment and a
working directory outside the repository checkout.

The verified helper does not depend on:

- the repository checkout;
- a developer virtual environment;
- `PATH`;
- Homebrew; or
- an externally installed Python interpreter.

PyInstaller one-file helpers contain embedded native binaries. A real Developer
ID release must therefore pass the Developer ID Application identity to the
helper builder itself. Post-processing only the outer one-file executable is not
a substitute for signing its embedded binary payload correctly.

The helper SHA-256 is still refreshed after final top-level helper signing and
bound into the outer signed release manifest.

## Notification and background-service identity

The same stable signed bundle identity `ai.ally.personal` owns modern desktop
notification authorization and delivery.

The release desktop uses `UNUserNotificationCenter`; the deprecated Python
`NSUserNotificationCenter` adapter is legacy CLI compatibility and is not a
release dependency.

Continuous proactivity is currently an explicit
`SMAppService.mainApp` launch-at-login registration. This avoids installing a
second notification-owning process before dedicated-machine identity behavior
can be validated.

Notification permission and launch-at-login registration are independent.
Neither is silently enabled by installation or first launch.

A future separate launch agent is acceptable only if its cross-process
responsible-code, notification, signing, and user-control semantics are
validated without weakening the stable main-app identity.

## User-owned data boundary

Application state must remain outside `Ally.app`.

The bundle verifier rejects known Ally user-data/runtime directory names such as
`.ally`, `data`, `backups`, `models`, and `secrets` if they appear inside
the assembled application.

Installing or updating the app must replace code, not personal data.

## Update threat model

No automatic updater is enabled yet.

The hardware-independent **candidate trust boundary is implemented** in
`scripts/macos_update_trust.py`. It compares already-staged full app bundles,
rejects rollback/same-build candidates, rejects bridge/database-schema
regression, requires release-grade source provenance, and can require the exact
Developer ID TeamIdentifier, hardened runtime, signing timestamp, notarization
staple, and Gatekeeper acceptance on macOS.

It deliberately performs no fetch and no replacement. See
[macOS Update Candidate Trust](macos-update-trust.md).

Before any updater may fetch or execute code, it must enforce all of the
following:

- accept only a full application bundle for the first updater version; do not
  begin with binary/delta patching;
- require the expected bundle identifier;
- require a valid Apple code signature from the expected Developer ID team;
- require successful notarization/Gatekeeper validation;
- require a valid Ally release manifest whose bridge protocol and helper path
  match the application code;
- require the helper digest to match the signed helper bytes;
- reject version rollback by default;
- stage the candidate outside the live app and outside Ally user-data
  directories;
- verify the candidate completely before replacement;
- use an atomic application-code replacement strategy where supported;
- never let model output, skills, or the helper choose/update executable code;
  and
- never reuse update transport as an inference or private-data egress channel.

HTTPS is useful transport protection but is not sufficient release
authentication by itself. The signed application identity is authoritative.

## Rollback model

Application-code rollback and persistent-data rollback are separate operations.

A previous app version may be reinstalled safely only when it understands the
current database schema. If an update performs a forward-only schema migration,
rolling back code alone may be unsafe.

The candidate verifier already rejects code rollback by default and reports
whether a forward candidate raises the database schema contract. Therefore a
future updater must:

- preserve the default no-rollback rule;
- inspect schema compatibility before any explicit recovery rollback;
- create/validate the existing Ally backup artifact before a migration that may
  break backward compatibility;
- restore data only through Ally's existing integrity-checked restore boundary;
- never silently downgrade or rewrite the database to satisfy an older app; and
- present rollback as an explicit recovery action when data restoration is
  required.

The updater itself must not become a second migration engine.

## Release acceptance still requiring the dedicated Mac

CI can validate structure, hashing, protocol/database-schema binding, Swift
release compilation, forward-only candidate comparison, ad-hoc signature
mechanics, and rejection of ad-hoc builds by the production update-trust path.

The dedicated Mac is still required to validate:

- real Developer ID signing and notarization;
- first launch through Gatekeeper;
- stable notification permission identity;
- Keychain access under the signed application identity;
- launchd/background behavior with the installed bundle;
- closing/reopening with real user-owned state;
- restart behavior;
- app replacement while preserving state; and
- final daily-use recovery behavior.

## Machine acceptance evidence

After the real dedicated-machine gates are exercised, Ally can record the
results in a versioned, immutable, payload-free machine acceptance artifact.

The artifact is bound to the exact Ally version, Git source revision,
hardware/OS profile, and hash-bound active validated runtime profile. It records
only fixed pass/fail/not-run gate statuses and contains no free-form private
payloads.

Synthetic CI may test this artifact's lifecycle, but cannot satisfy the real
machine gates. See [Dedicated-Machine Acceptance Evidence](machine-acceptance.md).

## Final release-readiness binding

Machine acceptance alone does not prove that the accepted machine is using the
same exact runtime candidate that passed Ally's capability, privacy, and
functional workflow qualification.

The final `ally release-readiness` evidence layer binds the validation-session
manifest and exact capability/privacy/workflow/profile digests to the exact
machine-acceptance artifact and current hash-bound active profile.

This coordinator lives outside the narrow update-trust package. It has no
signing credential, Git tag, publishing, network-fetch, update, or replacement
authority.

A future release workflow should require a currently verified
`qualified_for_release=true` artifact before tagging or distribution. See
[Final Release Readiness Evidence](release-readiness.md).

## Local release build orchestration

The repository now provides `scripts/macos_release_pipeline.py` as the canonical
ordering layer for macOS release construction.

Hosted macOS CI exercises its ad-hoc mode end-to-end. Production mode is stricter:
it refuses to create output until the exact final release-readiness artifact
verifies against the current validation session, machine acceptance, source
revision, hardware, and active profile.

The builder also requires a clean checkout whose exact `HEAD` matches the
release source revision, places output outside the repository, never overwrites a
production output, builds PyInstaller embedded code with the Developer ID
identity, signs/notarizes/staples/assesses the app, extracts and re-verifies the
final ZIP, and writes path-free artifact metadata bound to the release-readiness
SHA-256.

It deliberately has no Git tag, GitHub release, upload, updater, or installed-app
replacement authority. See
[macOS Release Build Orchestration](macos-release-build.md).
