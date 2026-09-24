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

## 10. Managed proactive service acceptance (#64)

Inspect before installing:

```bash
uv run ally service managed inspect
```

As the intended login user, not with `sudo`:

```bash
uv run ally service managed install
uv run ally service managed status --json
uv run ally service health --json
```

Verify:

1. the expected interpreter/log paths;
2. successful bounded cycles;
3. logout/login recovery;
4. full Mac restart recovery;
5. recovery after a synthetic cycle failure;
6. overlapping cycles are rejected by the runtime lease;
7. log growth/retention policy is acceptable; and
8. uninstall leaves data/logs intact.

### Stop condition

Managed-service failure blocks desktop/release acceptance.

Detailed procedure:
[Managed macOS Service](../macos-managed-service.md).

---

## 11. Native Notification Center acceptance (#63)

Run:

```bash
uv run ally attention health --sink macos
```

Emit synthetic events covering mention-later, notify, and interrupt classes,
then deliver them through the native sink.

Verify:

- one visible notification per event;
- retries do not duplicate a successful delivery;
- notification previews expose only the intended synthetic summary/message;
- denied/unobservable authorization behavior is understood;
- failures persist only safe exception classes;
- logout/login and restart preserve managed delivery behavior.

### Stop condition

Notification acceptance failure blocks desktop/release acceptance.

Detailed procedure:
[macOS Native Attention](../macos-notifications.md).

---

## 12. Final integrated acceptance

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
- notification permission/visibility/restart observations.

Do not store private prompts, credentials, personal documents, raw packet
captures containing private payloads, or secret-bearing logs in validation
artifacts.
