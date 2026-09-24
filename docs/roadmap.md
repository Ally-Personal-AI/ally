# Roadmap

Ally is built in dependency order. A later layer should not become the hidden
implementation of an earlier one.

| Phase | Status | Current implementation |
| --- | --- | --- |
| Foundation | Implemented | local-first architecture, tested dependency boundaries, contributor map, locked dependencies, Linux quality CI + macOS portability smoke, coverage regression gate, automated dependency maintenance, security/data boundaries, ADRs |
| Data portability | Implemented V1 | versioned integrity-checked SQLite backup/restore archives |
| Configuration / secrets | Adapter implemented; machine acceptance pending | strict non-secret config, direct macOS Security-framework adapter, reference-only CLI, fail-closed tests |
| Local conversation | Implemented | provider-neutral private chat with active validated-profile resolution by default, loopback-only development override, and no remote escape hatch |
| Application facade | Implemented V1 + desktop proactive handshake | typed UI-neutral runtime/chat/conversation/memory/knowledge services plus task approval/execution, pending attention/history, read-only service health/history, bounded bootstrap, and an exact-ID prepare/ack/complete handshake for signed-app notification delivery; the facade still never calls OS notification APIs or accepts caller-supplied notification payloads |
| Native desktop shell | Daily-use + release foundation advancing; machine acceptance pending | SwiftUI shell over a bounded local stdio bridge to `AllyApplication`; full daily-use state surfaces plus app-owned `UNUserNotificationCenter` delivery, duplicate reconciliation, explicit notification permission, opt-in `SMAppService.mainApp` launch-at-login, stable-ID bundle/signing, and a self-contained frozen bridge; real Developer ID/notarization and installed-machine behavior remain |
| User instructions | Implemented V2 | global/project/conversation/task profiles, enable/disable, provenance-aware composition, and ephemeral session instructions |
| Behavioral model qualification | Implemented V1 | separate refusal, instruction-following, calibration, moralizing, and paired viewpoint-symmetry evidence integrated into local-model validation |
| Long-term memory | Implemented V1 | temporal/provenance-aware explicit memory and grounding |
| Personal knowledge | Implemented V1 | versioned plain-text ingestion, retrieval, grounding |
| Tools | Implemented V1 | typed capabilities, risk policy, local audit |
| Skills | Implemented V1 | declarative manifests, safe install lifecycle, explicit process-isolated Python execution |
| Reliable agency | Implemented core | persisted tasks, approval pauses, verification, retries |
| Model plan proposals | Implemented boundary | strict TaskPlan proposals; no persistence or execution authority |
| Model memory proposals | Implemented boundary | reviewable extraction bundles; explicit selected acceptance only |
| Private intelligence boundary | Core implemented; runtime evidence contract implemented; machine acceptance pending | private chat/planning/memory/grounding loopback-only; remote access limited to bundled synthetic/public evals; separate fail-closed runtime privacy artifact ties no-egress evidence to exact capability validation |
| Controlled external egress | Implemented foundation | trusted adapter-owned field classifications, explicit outbound approval, private/secret denial, payload-free audit, and network-import guard; concrete integrations deferred |
| Dedicated-hardware validation | Ready to run | resumable evidence-derived validation sessions, read-only first-machine readiness preflight, source-bound disposable workflow evidence, versioned capability evidence, path-free model/runtime artifact fingerprints, separate runtime privacy qualification, cryptographically verified three-artifact candidate comparison, immutable validated runtime profiles, Ally-owned profile catalog/active selection, daily active-profile inference resolution, behavioral qualification, and first-machine runbook |
| Proactivity | Implemented substrate + app-owned macOS delivery path; machine acceptance pending | persisted events, deterministic scheduling/attention, payload-minimized rendering, exact stable delivery IDs, retry/interruption lifecycle accounting, modern signed-app `UNUserNotificationCenter` delivery, and explicit `SMAppService` launch-at-login; deprecated Python Notification Center/LaunchAgent paths remain legacy CLI compatibility only |
| Voice | Not started | local ASR/TTS and conversational voice |
| Multi-user households | Not started | identities, shared/private state, permissions |
| Extension ecosystem | Implemented local foundation | local lifecycle + isolated execution; signing, mediated tool requests, and registry deferred |
| Computer control | Not started | GUI perception/action behind tool policy |
| Physical-world integration | Not started | devices, sensors, automation |
| Distributed Ally | Not started | coordinated compute/storage nodes |

## Ally 0.1

The first meaningful release target is a completely local, model-independent
personal AI with:

- persistent conversations;
- inspectable long-term memory;
- personal document knowledge;
- explicit privacy boundaries;
- permissioned tool execution;
- restart-safe task execution;
- behavioral evaluations, including unnecessary-refusal and viewpoint-symmetry qualification;
- user-owned portable backups;
- a reproducible local-model validation path.

The repository now contains the deterministic substrate for that target plus
the first native SwiftUI desktop shell over the interface-neutral application
and bootstrap contracts. Hardware evidence will inform real model/runtime
selection while desktop packaging, workflow, security, and product architecture
continue to advance independently.

## Pre-hardware hardening

The repository pins the complete Python dependency graph in `uv.lock`. CI
installs only that locked graph on Linux and macOS, enforces a project-wide
coverage regression floor, and groups weekly Python and GitHub Actions updates
for review.

Distribution gates on both platforms build an sdist and wheel, check packaged
modules and frozen evaluations, and exercise installed workflows in a fresh
environment outside the checkout. Synthetic loopback inference, persisted state,
skill subprocesses, and backup/restore can be verified before hardware arrives.

Recovery tests cover every existing schema prefix, atomic rollback, simultaneous
startup, invalid history, foreign-key corruption, and backup/restore destination
collisions. These checks protect persistent state before first-machine usage.

The macOS managed-service definition and lifecycle are testable without the
dedicated machine. Installation remains disabled by default, Linux inspection
is non-mutating, and mocked launchd tests cover install/start/stop/uninstall,
idempotency, rollback, races, and definition ownership. Real login and restart
acceptance remains hardware-gated.

These controls keep the first-machine evidence comparable over time: a model or
runtime comparison should not silently change because unrelated dependencies
floated between runs.

Validation artifacts also fingerprint the frozen evaluation inputs and record
the exact runtime/model configuration plus optional runtime-native performance
observations. The comparison command reports Ally-version, hardware, or suite
mismatches and does not choose a default on the user's behalf.

## Hardware handoff

Before selecting hardware-specific model adapters, default models, context budgets,
or enabling any automatic model-driven planning or memory behavior, run the
first-machine procedure in [hardware/apple-silicon-validation.md](hardware/apple-silicon-validation.md).

The safe proposal boundaries for planning and memory formation are already in
place; the hardware session now measures whether candidate local models are good
enough to use those boundaries reliably.

The initial hardware session should compare real local runtime/model pairs using
the frozen evaluation and validation tooling already in the repository.

## Later dependency order

After hardware/runtime validation:

1. create and select the first validated runtime profile from measured evidence;
2. decide whether direct MLX or other hardware-specific adapters are justified;
3. calibrate planning and memory proposal quality thresholds;
4. upgrade retrieval/embeddings only where measured need justifies it;
5. validate the macOS service/native notification adapters and add calendar/email/weather source adapters on the persisted proactivity substrate;
6. add voice;
7. add multi-user household boundaries;
8. add skill signing and remote registry on top of the local installation boundary;
9. add computer control;
10. add physical-world integration;
11. add distributed Ally.

The first engineering priority remains reliability and compounding usefulness,
not autonomy for its own sake.
