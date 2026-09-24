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
- exact desktop bridge protocol version;
- fixed relative helper path;
- SHA-256 of the **signed helper bytes**; and
- optional source revision.

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

Hosted CI currently exercises the bundle structure and ad-hoc signing path only.
Ad-hoc signing is test evidence for layout/signing mechanics; it is not a
distributable or notarized release.

## Standalone helper requirement

The bundle assembler accepts a prebuilt executable
`ally-desktop-bridge`.

A production release is not complete until that helper is a self-contained,
single-file (or equivalently self-contained signed nested-code) artifact that
does not depend on:

- the repository checkout;
- a developer virtual environment;
- `PATH`;
- Homebrew;
- an externally installed Python interpreter; or
- mutable dependencies outside the signed app bundle.

The current release-foundation CI uses a Mach-O stand-in at the helper location
to validate app-bundle and code-signing mechanics. It does **not** claim that the
final standalone Python helper packaging is solved.

## User-owned data boundary

Application state must remain outside `Ally.app`.

The bundle verifier rejects known Ally user-data/runtime directory names such as
`.ally`, `data`, `backups`, `models`, and `secrets` if they appear inside
the assembled application.

Installing or updating the app must replace code, not personal data.

## Update threat model

No automatic updater is enabled yet.

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

Therefore a future updater must:

- inspect schema compatibility before allowing code rollback;
- create/validate the existing Ally backup artifact before a migration that may
  break backward compatibility;
- restore data only through Ally's existing integrity-checked restore boundary;
- never silently downgrade or rewrite the database to satisfy an older app; and
- present rollback as an explicit recovery action when data restoration is
  required.

The updater itself must not become a second migration engine.

## Release acceptance still requiring the dedicated Mac

CI can validate structure, hashing, protocol binding, Swift release compilation,
and ad-hoc signature mechanics.

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
