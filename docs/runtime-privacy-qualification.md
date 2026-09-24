# Runtime Privacy Qualification

Ally separates model capability evidence from runtime privacy evidence.

A local model can pass every behavioral and functional evaluation while its
runtime still makes outbound connections, requires cloud authorization, sends
telemetry, or silently delegates work to a hosted service. For that reason,
`ally validate local-model` is necessary but not sufficient for production
private inference.

## Two required artifacts

A candidate intended for private daily use needs:

1. a successful local-model validation report; and
2. a qualified runtime privacy report tied to that exact validation artifact.

Create the first artifact normally:

```bash
uv run ally validate local-model \
  --model <model-id> \
  --runtime <runtime-name> \
  --runtime-version <version> \
  --output validation/<candidate>.json
```

After completing the no-egress checks on the dedicated machine, create the
privacy artifact:

```bash
uv run ally validate runtime-privacy \
  validation/<candidate>.json \
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
  --output validation/<candidate>-privacy.json
```

Every check defaults to `not_run`. A missing check never counts as a pass.

Inspect the result:

```bash
uv run ally validate runtime-privacy-show \
  validation/<candidate>-privacy.json
```

Use `--json` for machine-readable inspection.

## Qualification rule

A runtime privacy artifact is qualified only when all of these are true:

- the source local-model report itself passed;
- the source report was produced by the same Ally version creating the privacy
  artifact;
- the privacy artifact is cryptographically tied to the exact source report by
  SHA-256;
- an explicit isolation mode is recorded;
- an explicit network-observation method is recorded; and
- every required privacy check is `pass`.

A failed capability report cannot become qualified by passing privacy checks,
and a capable model cannot become qualified while privacy checks remain
unverified.

## Isolation modes

The V1 evidence schema supports:

- `unverified` — development only; cannot qualify;
- `host_offline` — the host's external network connectivity is unavailable
  during the synthetic test;
- `process_egress_denied` — the runtime process is explicitly prevented from
  initiating external connections by a reviewed mechanism; and
- `system_content_filter` — a reviewed system content-filter policy prevents
  runtime egress.

The schema records evidence; it does not itself implement a firewall.

For the first dedicated-machine session, `host_offline` is the simplest
high-confidence acceptance method because Ally does not yet own the lifecycle
of the eventual model runtime. The machine should download all model/runtime
assets first, disconnect or otherwise remove external network access, and then
run the complete synthetic inference workflow.

A future bundled macOS component may enforce more granular egress controls.
Apple's supported App Sandbox network entitlements apply to sandboxed app
targets, while Network Extension content filters are the system API for
allowing or denying network flows. Do not rely on undocumented/deprecated
process-sandbox tricks as the production privacy boundary.

## Required checks

The privacy artifact records:

- inference succeeds while egress is blocked;
- synthetic persistent chat succeeds;
- synthetic planning succeeds;
- synthetic memory proposal generation succeeds;
- synthetic grounding succeeds;
- normal inference requires no cloud authentication;
- no cloud fallback is observed;
- no prompt-bearing telemetry is observed; and
- no unexpected outbound runtime connection is observed.

These are operator-observed acceptance checks, not claims inferred from model
quality or provider configuration.

## Evidence boundary

Privacy artifacts contain runtime/model identifiers, non-sensitive hardware
metadata copied from the validation report, check states, isolation mode, and
the source report digest.

They do not contain prompts, private documents, credentials, packet captures,
raw network logs, private file paths, or arbitrary operator notes.

Existing evidence is immutable: Ally refuses to overwrite an existing privacy
report. Repeat a test with a new output file.

## Production gate

Until both capability and privacy artifacts pass, a runtime/model pair is
development-only.

No default private runtime should be selected merely because:

- its endpoint is loopback;
- the model is open-weight;
- the runtime vendor advertises local execution; or
- a model validation report passed.

End-to-end private inference requires evidence that the runtime actually keeps
normal inference local.
