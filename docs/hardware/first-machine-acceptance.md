# Unified First-Machine Acceptance

This is the canonical operator checklist for the first dedicated Apple-silicon
Ally machine.

Use it to coordinate the remaining empirical gates after hardware-independent
development is complete. It does not replace the detailed subsystem runbooks;
it defines their order, stop conditions, and evidence handoff.

## Ground rules

Until runtime capability and privacy qualification are complete:

- use only synthetic/public validation data;
- do not import personal documents, memories, email, credentials, or other
  private user data;
- keep private inference endpoints bound to loopback;
- do not select a default runtime/model from raw endpoint/model strings;
- do not enable automatic model writes or consequential tools;
- do not treat a successful model response as privacy qualification.

Preserve every generated validation artifact. Existing evidence files are
immutable and should never be overwritten.

Recommended per-candidate directory:

```text
validation/
  candidate-a/
    session.json
    capability.json
    workflows.json
    privacy.json
    profile.json
```

## Gate summary

| Gate | Blocks runtime selection? | Blocks desktop/release acceptance? |
| --- | --- | --- |
| Baseline/readiness | yes | yes |
| Login-Keychain acceptance | no | yes |
| Capability + behavioral validation | yes | yes |
| Functional workflow evidence | yes | yes |
| Runtime privacy/no-egress qualification | yes | yes |
| Candidate comparison + validated profile | yes | yes |
| Backup/restore recovery drill | no | yes |
| Managed launchd service acceptance | no | yes |
| Native notification acceptance | no | yes |
| Final integrated health check | yes | yes |

A runtime profile may be selected only after capability, workflow, and privacy
evidence all qualify and verify against the same source capability artifact.

Ally 0.1 release/desktop acceptance additionally requires the OS integration and
recovery gates below.

---

## 1. Baseline and read-only readiness

Clone/sync the intended Ally revision and record it:

```bash
git rev-parse HEAD
uv sync --extra dev
uv run ally --version
uv run ally doctor
uv run ally validate hardware --json
```

Run deterministic repository checks:

```bash
uv run ruff check .
uv run pyright
uv run pytest
uv run ally eval run
```

Run the non-mutating first-machine readiness preflight:

```bash
uv run ally validate readiness
uv run ally validate readiness --json
```

### Stop condition

Do not continue to candidate validation while readiness reports any `error`, or
while deterministic repository checks fail.

Warnings that explicitly represent unperformed machine acceptance—such as
notification authorization not yet confirmed—may remain until their later gate.

Detailed model/hardware procedure:
[Apple Silicon First-Machine Validation](apple-silicon-validation.md).

---

## 2. Login-Keychain acceptance (#62)

Use a synthetic value that is not a real credential:

```bash
uv run ally secrets set validation.synthetic
uv run ally secrets check validation.synthetic
uv run ally secrets list
```

Close the shell/process, start a new shell, and repeat:

```bash
uv run ally secrets check validation.synthetic
uv run ally secrets list
```

Verify:

- the reference survives process restart;
- no command prints the secret value;
- a normal Ally backup still contains only `manifest.json` and `ally.sqlite3`;
- locked-Keychain behavior produces either the OS unlock path or a safe generic
  failure, never raw secret/OS diagnostic output;
- unlocking restores normal access;
- deletion works and missing status returns the documented result.

Finish:

```bash
uv run ally secrets delete validation.synthetic
uv run ally secrets check validation.synthetic
```

### Stop condition

A Keychain failure does not by itself invalidate model capability evidence, but
it blocks desktop/release acceptance.

Detailed contract:
[Configuration and Secrets](../configuration-secrets.md).

---

## 3. Initialize one validation session per candidate

Create a directory/session before running mutable candidate validation:

```bash
uv run ally validation-session init candidate-a \
  --directory validation/candidate-a
```

Inspect live derived progress at any time:

```bash
uv run ally validation-session refresh \
  validation/candidate-a/session.json
```

Do not use cached operator checkboxes as authority. Session state must be derived
from current evidence.

Detailed contract:
[Validation Sessions](../validation-sessions.md).

---

## 4. Capability and behavioral validation (#29)

Start exactly one local OpenAI-compatible candidate runtime, bound to
`127.0.0.1`.

Record the exact runtime/model version, quantization/precision, context length,
runtime parameters, and local model/runtime artifact inputs needed for
fingerprinting.

Run:

```bash
uv run ally validate local-model \
  --model <model-id> \
  --runtime <runtime-name> \
  --runtime-version <exact-version> \
  --model-source <public-model-id> \
  --quantization <quantization> \
  --model-artifact <local-weight-or-shard> \
  --runtime-artifact <local-runtime-binary-or-package> \
  --context-length <tokens> \
  --output validation/candidate-a/capability.json
```

Record runtime-native performance observations when available instead of
estimating them.

Review the behavioral dimensions separately, including:

- unnecessary refusal;
- instruction following;
- calibration;
- unsolicited moralizing;
- paired viewpoint symmetry;
- planning proposal quality;
- memory proposal quality.

### Stop condition

A failed capability report blocks production eligibility and runtime selection.

---

## 5. Source-bound functional workflow evidence (#29)

While the same candidate runtime remains active:

```bash
uv run ally validate workflows \
  validation/candidate-a/capability.json \
  --output validation/candidate-a/workflows.json
```

Verify the binding when desired:

```bash
uv run ally validate workflows-verify \
  validation/candidate-a/workflows.json \
  validation/candidate-a/capability.json
```

The workflow must remain disposable and synthetic. It must not use the future
personal-state database.

### Stop condition

A failed or mismatched workflow artifact blocks production eligibility and
runtime selection.

Detailed contract:
[Functional Workflow Validation](../functional-workflow-validation.md).

---

## 6. Runtime privacy/no-egress qualification (#85)

Download all required model/runtime assets first.

Then remove external connectivity from the host or apply the reviewed
process/system isolation method being tested. For the first machine,
`host_offline` is the simplest high-confidence path.

Confirm synthetic inference still works while egress is unavailable and inspect
for unexpected runtime connections/telemetry.

Create the privacy evidence:

```bash
uv run ally validate runtime-privacy \
  validation/candidate-a/capability.json \
  --isolation-mode host_offline \
  --network-observation system_tools \
  --inference-with-egress-blocked pass \
  --synthetic-chat pass \
  --synthetic-planning pass \
  --synthetic-memory-proposal pass \
  --synthetic-grounding pass \
  --no-cloud-auth-required pass \
  --no-cloud-fallback-observed pass \
  --no-prompt-telemetry-observed pass \
  --no-unexpected-outbound-connections pass \
  --output validation/candidate-a/privacy.json
```

Verify:

```bash
uv run ally validate runtime-privacy-verify \
  validation/candidate-a/privacy.json \
  validation/candidate-a/capability.json
```

### Stop condition

Any `fail`, `not_run`, source mismatch, required cloud authorization,
observed cloud fallback, prompt-bearing telemetry, or unexpected outbound
runtime connection blocks production eligibility and runtime selection.

Detailed contract:
[Runtime Privacy Qualification](../runtime-privacy-qualification.md).

---

## 7. Verify and compare complete candidates

Inspect the exact evidence set:

```bash
uv run ally validate candidate \
  validation/candidate-a/capability.json \
  validation/candidate-a/privacy.json \
  validation/candidate-a/workflows.json
```

For multiple candidates:

```bash
uv run ally validate compare-candidates \
  --candidate validation/candidate-a/capability.json validation/candidate-a/privacy.json validation/candidate-a/workflows.json \
  --candidate validation/candidate-b/capability.json validation/candidate-b/privacy.json validation/candidate-b/workflows.json
```

Do not choose from one composite score. Review qualification, behavior,
performance, context capacity, memory headroom, runtime stability,
reproducibility, and privacy evidence together.

### Stop condition

Do not create a production profile for a candidate unless all three artifacts
qualify and cryptographically verify against the same capability report.

---

## 8. Create, install, and select the first validated runtime profile

After the operator chooses a production-eligible candidate from the evidence:

```bash
uv run ally profiles create \
  validation/candidate-a/capability.json \
  validation/candidate-a/privacy.json \
  validation/candidate-a/workflows.json \
  --output validation/candidate-a/profile.json

uv run ally profiles verify \
  validation/candidate-a/profile.json \
  validation/candidate-a/capability.json \
  validation/candidate-a/privacy.json \
  validation/candidate-a/workflows.json

uv run ally profiles install \
  validation/candidate-a/profile.json \
  validation/candidate-a/capability.json \
  validation/candidate-a/privacy.json \
  validation/candidate-a/workflows.json
```

Select the installed profile:

```bash
uv run ally profiles select <profile-id>
uv run ally profiles active --json
```

Re-derive the validation-session state:

```bash
uv run ally validation-session verify \
  validation/candidate-a/session.json
```

### Stop condition

If the active profile cannot be resolved exactly, daily private inference must
remain unavailable. Never fall back to arbitrary raw model coordinates.

---

## 9. Backup/restore recovery drill

Before personal data is introduced, create representative synthetic Ally state
and run the documented recovery procedure.

At minimum:

```bash
uv run ally data backup /absolute/private/path/acceptance.ally-backup
uv run ally data validate /absolute/private/path/acceptance.ally-backup
uv run ally data restore /absolute/private/path/acceptance.ally-backup \
  --destination /absolute/private/path/recovered-ally.sqlite3
```

Verify the restored state contains the expected synthetic conversations,
memories, tasks, and portable service lifecycle history.

Also exercise the documented default-path recovery procedure with Ally processes
stopped and sidecars preserved.

### Stop condition

Recovery failure does not invalidate the selected runtime evidence, but blocks
release/desktop acceptance.

Detailed procedure:
[Database Upgrades and Recovery](../database-recovery.md).

---

## 10. Signed-app background service and legacy migration acceptance (#64)

For a new desktop installation, do **not** install the historical launch-agent
scheduler. It remains available only for legacy CLI compatibility.

Before enabling background proactivity in the signed app, inspect whether an
older installation left the historical service behind:

```bash
uv run ally service managed status --json
```

If it is absent, enable **Background Proactivity** in the signed app and verify
`SMAppService.mainApp` reaches the expected Login Items state.

If it is present, verify the app:

1. reports the legacy service without exposing its filesystem or executable path;
2. refuses to enable the modern login item while legacy state remains configured;
3. retires an exact/recognized Ally historical definition only after explicit confirmation;
4. refuses automatic retirement of a modified definition or symlink; and
5. resumes signed-app proactive cycles only after migration state is clean.

Then verify successful bounded cycles, logout/login recovery, full Mac restart
recovery, recovery after a synthetic cycle failure, lease rejection of overlap,
and that disabling the login item leaves Ally data intact.

### Stop condition

Unknown or modified legacy-service state, failed migration, or failed signed-app
login/restart behavior blocks desktop/release acceptance.

Detailed procedure:
[Managed macOS Service](../macos-managed-service.md).

---

## 11. Native Notification Center acceptance (#63)

Exercise the **signed Ally app**, not the deprecated CLI Notification Center
adapter, as the acceptance authority.

Emit synthetic events covering mention-later, notify, and interrupt classes and
allow the app-owned proactive cycle to deliver them through
`UNUserNotificationCenter`.

Verify:

- the signed `ai.ally.personal` identity owns notification authorization;
- one visible notification appears per event;
- retries/restart reconciliation do not duplicate a successful delivery;
- notification previews expose only the intended synthetic summary/message;
- denied authorization becomes a safe durable failed attempt;
- successful delivery does not mark the event handled; and
- logout/login and restart preserve signed-app delivery behavior.

### Stop condition

Notification acceptance failure blocks desktop/release acceptance.

Detailed procedure:
[macOS Native Attention](../macos-notifications.md).

---

## 12. Signed release and update-candidate acceptance

Using synthetic Ally state only, build/sign/notarize two full app bundles with
the real Developer ID identity and increasing build numbers.

Verify the newer staged candidate before any replacement:

```bash
uv run python scripts/macos_update_trust.py verify-update \
  --current /Applications/Ally.app \
  --candidate /private/staging/Ally.app \
  --team-id <APPLE-DEVELOPER-TEAM-ID>
```

Then exercise the pre-install preparation boundary. For a schema-raising
candidate, provide a fresh private backup destination:

```bash
uv run python scripts/macos_update_prepare.py \
  --current /Applications/Ally.app \
  --candidate /private/staging/Ally.app \
  --team-id <APPLE-DEVELOPER-TEAM-ID> \
  --backup-output /absolute/private/path/before-update.ally-backup
```

Verify:

- both installed and candidate identities resolve to `ai.ally.personal`;
- both signatures use the expected Developer ID TeamIdentifier;
- hardened runtime, signing timestamp, staple validation, and Gatekeeper pass;
- the newer build is accepted;
- equal/older builds are rejected;
- a differently signed candidate is rejected;
- an unstapled candidate is rejected;
- source revision is present in the accepted result;
- any database-schema increase reports
  `requires_pre_migration_backup=true`;
- schema-raising preparation refuses to proceed without a fresh backup;
- the preparation result hash-binds the revalidated archive/database and
  contains no local paths; and
- manual replacement preserves user-owned state outside `Ally.app`.

### Stop condition

Do not enable automatic update fetching or replacement until these checks pass.
If a candidate raises database schema compatibility, require
`macos_update_prepare.py` to create and revalidate Ally's backup artifact before
testing replacement/migration.

Detailed contract:
[macOS Update Candidate Trust](../macos-update-trust.md).

---

## 13. Final integrated acceptance

With the selected validated profile active:

```bash
uv run ally profiles active --json
uv run ally service health --json
uv run ally attention health --sink macos --json
```

Exercise only synthetic/local state first:

- create/resume private chat;
- inspect memory and knowledge;
- run a read-only task;
- confirm a reversible task pauses for explicit approval;
- inspect pending attention/history;
- verify the desktop bootstrap contract can load even if inference is
  temporarily unavailable.

The application bootstrap first-call contract is:

```python
snapshot = build_default_application().bootstrap()
```

Do not introduce real personal data until the operator is satisfied that the
runtime, privacy, recovery, secrets, service, and notification paths behave as
documented.

---

## 14. Create machine-readable acceptance evidence

After the active validated runtime profile is selected and every empirical gate
above has actually been exercised, record the results in one immutable,
payload-free artifact:

```bash
SOURCE_REVISION="$(git rev-parse HEAD)"

uv run ally machine-acceptance create \
  --source-revision "$SOURCE_REVISION" \
  --keychain pass \
  --recovery pass \
  --background-service pass \
  --notifications pass \
  --signed-release pass \
  --update-preparation pass \
  --app-replacement pass \
  --integrated-daily-use pass \
  --output validation/machine-acceptance.json \
  --json

uv run ally machine-acceptance verify \
  validation/machine-acceptance.json \
  --source-revision "$SOURCE_REVISION" \
  --json
```

The report binds the observations to the exact Ally version, Git source
revision, hardware/OS profile, active validated runtime profile ID, and the
profile SHA-256 recorded by Ally's active selection.

A failed or unfinished gate may be recorded as `fail` or `not_run`, but the
report is not release-qualified. Do not rewrite prior evidence after a failure;
create a new artifact after the issue is corrected.

### Stop condition

Do not treat the machine as Ally 0.1 release-accepted unless verification exits
successfully with every gate passed. Synthetic hosted-CI acceptance artifacts
test only serialization/verification mechanics and are never machine evidence.

Detailed contract:
[Dedicated-Machine Acceptance Evidence](../machine-acceptance.md).

---

## 15. Re-verify the complete release evidence chain

Immediately before creating an Ally 0.1 tagged pre-release, use the exact
candidate artifacts that produced the selected validated profile:

```bash
uv run ally release readiness \
  validation/candidate-a/capability.json \
  validation/candidate-a/privacy.json \
  validation/candidate-a/workflows.json \
  validation/machine-acceptance.json \
  --source-revision "$SOURCE_REVISION" \
  --json
```

This read-only gate verifies the active profile against its exact
capability/privacy/workflow source evidence and verifies the machine-acceptance
artifact against the live Ally version, source revision, hardware profile, and
hash-bound active selection.

### Stop condition

Do not create a tagged pre-release unless the command exits `0` and reports
`ready_for_tagged_prerelease=true`. The command does not create the tag,
publish a release, sign code, or perform an update.

Detailed contract:
[Ally 0.1 Release Readiness](../release-readiness.md).

## Handoff to desktop shell (#66)

The native desktop shell may begin after:

- at least one runtime/model candidate is production-eligible and selected;
- runtime privacy/no-egress evidence qualifies;
- Keychain acceptance passes;
- backup/recovery drill passes;
- managed service acceptance passes; and
- native notification acceptance passes.

The shell should remain a thin presentation layer over `AllyApplication` and
`bootstrap()`. It must not reimplement storage, model routing, memory,
permissions, task execution, or privacy policy.

## Evidence to retain

Keep, outside the repository as appropriate:

- exact Ally commit/version used;
- macOS/hardware profile;
- each candidate's capability/workflow/privacy/profile artifacts;
- validation session manifests;
- selected profile ID;
- non-secret command transcript/checklist results;
- Keychain prompt/locked-state observations;
- recovery drill result;
- managed-service login/restart/failure observations;
- notification permission/visibility/restart observations;
- immutable dedicated-machine acceptance evidence.

Do not store private prompts, credentials, personal documents, raw packet
captures containing private payloads, or secret-bearing logs in validation
artifacts.
