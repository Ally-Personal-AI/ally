# Roadmap

Ally is built in dependency order. A later layer should not become the hidden
implementation of an earlier one.

| Phase | Status | Current implementation |
| --- | --- | --- |
| Foundation | Implemented | local-first architecture, tested dependency boundaries, contributor map, locked dependencies, Linux quality CI + macOS portability smoke, coverage regression gate, automated dependency maintenance, security/data boundaries, ADRs |
| Data portability | Implemented V1 | versioned integrity-checked SQLite backup/restore archives |
| Configuration / secrets | Adapter implemented; machine acceptance pending | strict non-secret config, direct macOS Security-framework adapter, reference-only CLI, fail-closed tests |
| Local conversation | Implemented | provider-neutral private chat with active validated-profile resolution by default, loopback-only development override, and no remote escape hatch |
| Application facade | Implemented V1 + desktop proactive/research services | typed UI-neutral runtime/chat/conversation/memory/knowledge services plus privacy-gated public web research, task approval/execution, pending attention/history, read-only service health/history, bounded bootstrap, and an exact-ID prepare/ack/complete handshake for signed-app notification delivery; the facade still never calls OS notification APIs or accepts caller-supplied notification payloads |
| Native desktop shell | Daily-use + release foundation advancing; machine acceptance pending | SwiftUI shell over a bounded local stdio bridge to `AllyApplication`; conversations, memory, knowledge, privacy-gated public research, tasks, attention, scoped instruction Settings, runtime selection, and system state plus app-owned `UNUserNotificationCenter` delivery, duplicate reconciliation, explicit notification permission, opt-in `SMAppService.mainApp` launch-at-login, stable-ID bundle/signing, self-contained frozen bridge, offline forward-only update trust, schema-aware update preparation, and a CI-exercised local release orchestrator; real Developer ID/notarization and installed-machine replacement behavior remain |
| User instructions | Implemented V2 + native Settings | global/project/conversation/task profiles, enable/disable, provenance-aware composition, ephemeral session instructions, and native editing/visibility/resolution preview |
| Behavioral model qualification | Implemented V1 | separate refusal, instruction-following, calibration, moralizing, and paired viewpoint-symmetry evidence integrated into local-model validation |
| Long-term memory | Implemented V1.1 | temporal/provenance-aware explicit memory and grounding with deterministic BM25 retrieval; semantic/hybrid retrieval remains future |
| Personal knowledge | Implemented V1.1 | versioned plain-text ingestion plus deterministic BM25 chunk retrieval/grounding; semantic/hybrid retrieval remains future |
| Tools | Implemented V1 | typed capabilities, risk policy, local audit |
| Skills | Implemented V1 | declarative manifests, safe install lifecycle, explicit process-isolated Python execution |
| Reliable agency | Implemented core + native reviewed creation | local-model TaskPlan proposal remains untrusted until native review and explicit creation; persisted tasks retain separate run, exact-step approval, verification, and retry boundaries |
| Model plan proposals | Implemented boundary + native review flow | strict local TaskPlan proposals over the same reviewed tool registry used by execution; native review can explicitly persist the exact plan but never executes or approves it |
| Model memory proposals | Implemented boundary | reviewable extraction bundles; explicit selected acceptance only |
| Private intelligence boundary | Core implemented; runtime evidence contract implemented; machine acceptance pending | private chat/planning/memory/grounding loopback-only; remote access limited to bundled synthetic/public evals; separate fail-closed runtime privacy artifact ties no-egress evidence to exact capability validation |
| Controlled external egress | Implemented foundation + first concrete lookup | trusted adapter-owned field classifications, explicit outbound approval, private/secret denial, payload-free audit, network-import guard, and a Brave Search adapter whose exact query is approval-gated |
| Public web research | Implemented V1.1 + local sourced synthesis | provider-neutral exact-query research, approval-gated Brave Search adapter, Keychain credential reference, bounded normalized results, payload-free audit, native review/approval UI, and strict local-only answer synthesis with machine-validated source indices; autonomous multi-query research and page retrieval remain future |
| Dedicated-hardware validation | Ready to run | resumable evidence-derived validation sessions, read-only first-machine readiness preflight, source-bound capability/privacy/workflow evidence, immutable validated runtime profiles, hash-bound active selection, machine acceptance evidence, and a final release-readiness artifact cryptographically binding both evidence chains to the exact current version/source/hardware/profile state |
| Proactivity | Implemented substrate + app-owned macOS delivery path; machine acceptance pending | persisted events, deterministic scheduling/attention, payload-minimized rendering, exact stable delivery IDs, retry/interruption lifecycle accounting, modern signed-app `UNUserNotificationCenter` delivery, explicit `SMAppService` launch-at-login, and fail-closed migration from the historical LaunchAgent; deprecated Python Notification Center/LaunchAgent paths remain legacy CLI compatibility only |
| Voice | Local substrate implemented; engines/UI pending | bounded PCM16/WAV handling, local-only ASR/TTS provider contracts, and a UI-neutral ASR -> existing private chat -> TTS turn coordinator; concrete speech engines and desktop microphone/playback await dedicated-machine evaluation |
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
- optional privacy-gated public web research;
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

The historical macOS LaunchAgent definition and lifecycle remain testable
without the dedicated machine for compatibility and migration. New signed-app
installations use `SMAppService.mainApp` instead. Linux inspection is
non-mutating, and deterministic tests cover legacy recognition, modified/symlink
refusal, retirement identity races, and the existing launchd lifecycle. Real
Login Items, migration, login, and restart acceptance remains hardware-gated.

Release manifest v2 also binds each desktop build to its build number, bridge
protocol, supported database schema, helper digest, and source revision.
Hardware-independent update policy rejects rollback/same-build candidates and
flags schema-raising updates for a pre-migration backup. Hosted CI proves
ad-hoc signing is insufficient for production update trust.

These controls keep the first-machine evidence comparable over time: a model or
runtime comparison should not silently change because unrelated dependencies
floated between runs.

Validation artifacts also fingerprint the frozen evaluation inputs and record
the exact runtime/model configuration plus optional runtime-native performance
observations. The comparison command reports Ally-version, hardware, or suite
mismatches and does not choose a default on the user's behalf.

The final dedicated-machine gates are now representable as a separate immutable,
payload-free acceptance artifact. It binds empirical Keychain, recovery,
background-service, notification, signed-release/update, replacement, and
integrated-use observations to the exact Ally version/source revision, hardware
profile, and hash-bound active validated runtime profile.

A final release-readiness artifact then binds that machine evidence to the exact
capability/privacy/workflow/validated-profile chain from the candidate validation
session. It remains evidence-only.

The local macOS release orchestrator consumes that verified boundary in
production mode, requires clean exact-source provenance, composes helper build,
bundle assembly, Developer ID signing, notarization, archive verification, and
path-free artifact metadata, and still has no tag/upload/publish or installed-app
replacement authority.

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
5. validate signed-app Login Items, legacy-service migration, and native notifications, then add calendar/email/weather source adapters on the persisted proactivity substrate;
6. use measured daily needs to extend V1 web lookup into approval-preserving multi-query research/page retrieval;
7. qualify local ASR/TTS engines, then add desktop microphone/playback on the existing voice substrate;
8. add multi-user household boundaries;
9. add skill signing and remote registry on top of the local installation boundary;
10. add computer control;
11. add physical-world integration;
12. add distributed Ally.

The first engineering priority remains reliability and compounding usefulness,
not autonomy for its own sake.
