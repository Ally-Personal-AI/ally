# Architecture Decision Records

Significant, hard-to-reverse architectural choices are recorded here.

Each ADR includes context, a decision, consequences, and status. Changes should
supersede previous ADRs rather than silently rewriting project history.

## Decision log

1. [Model-independent core](0001-model-independent-core.md)
2. [Personal data stays outside the repository](0002-personal-data-outside-repository.md)
3. [Local inference over HTTP](0003-local-inference-over-http.md)
4. [SQLite local persistence](0004-sqlite-local-persistence.md)
5. [Temporal, provenance-aware memory](0005-temporal-provenance-memory.md)
6. [Retrieved context is untrusted data](0006-retrieved-context-is-untrusted-data.md)
7. [Versioned personal knowledge](0007-versioned-personal-knowledge.md)
8. [Permissioned tool execution](0008-permissioned-tool-execution.md)
9. [Declarative skill packages](0009-declarative-skill-packages.md)
10. [Persisted task state](0010-persisted-task-state.md)
11. [Model plan proposals are data](0011-model-plan-proposals-are-data.md)
12. [Memory extraction is reviewable](0012-memory-extraction-is-reviewable.md)
13. [Events before proactivity](0013-events-before-proactivity.md)
14. [Versioned portable backups](0014-versioned-portable-backups.md)
15. [Configuration never contains secrets](0015-config-never-contains-secrets.md)
16. [Local skill installation is non-executing](0016-local-skill-installation-is-nonexecuting.md)
17. [Schedules produce idempotent events](0017-schedules-produce-idempotent-events.md)
18. [Attention delivery is separate from handling](0018-attention-delivery-is-separate-from-handling.md)
19. [The proactive service cycle is bounded](0019-proactive-service-cycle-is-bounded.md)
20. [Event sources use cursors and dedupe](0020-event-sources-use-cursors-and-dedupe.md)
21. [Service coordination leases are ephemeral runtime state](0021-service-leases-are-ephemeral.md)
22. [Service lifecycle history is portable and payload-free](0022-service-lifecycle-is-portable-and-payload-free.md)
23. [Service health is structured read-only readiness](0023-service-health-is-read-only-readiness.md)
24. [Executable skills run outside Ally Core](0024-executable-skills-run-outside-core.md)
25. [Package dependency direction is tested](0025-package-dependency-direction-is-tested.md)
26. [Filesystem observation is metadata-only and explicitly rooted](0026-filesystem-observation-is-metadata-only.md)
27. [macOS secrets use Keychain and a reference-only CLI](0027-macos-keychain-secret-store.md)
28. [Model validation evidence is versioned and comparison is neutral](0028-model-validation-evidence-is-versioned.md)
29. [Database upgrades are atomic and recovery never replaces a destination](0029-atomic-database-recovery.md)
30. [The macOS managed service is explicit and bounded](0030-macos-managed-service-is-explicit-and-bounded.md)
31. [Behavior and user instructions are separate from authority](0031-behavior-and-user-instructions-are-separate-from-authority.md)
32. [User instructions compose by explicit scope](0032-user-instructions-compose-by-explicit-scope.md)
33. [Behavioral model qualification is multidimensional evidence](0033-behavioral-model-qualification-is-multidimensional-evidence.md)
34. [Private Ally intelligence never uses external inference](0034-private-intelligence-never-uses-external-inference.md)
35. [External egress is classified and payload-minimized](0035-external-egress-is-classified-and-payload-minimized.md)
36. [Runtime privacy qualification is separate fail-closed evidence](0036-runtime-privacy-qualification-is-separate-fail-closed-evidence.md)
37. [Model and runtime artifacts are fingerprinted in validation evidence](0037-model-runtime-artifacts-are-fingerprinted.md)
38. [Production candidates require functional workflow evidence](0038-production-candidates-require-functional-workflow-evidence.md)
39. [Production runtime selection uses validated runtime profiles](0039-production-runtime-selection-uses-validated-profiles.md)
40. [Validation sessions derive state from evidence](0040-validation-sessions-derive-state-from-evidence.md)
41. [Daily runtime selection resolves from an installed validated profile](0041-daily-runtime-selection-resolves-installed-validated-profile.md)
42. [Daily private inference resolves the active validated runtime profile](0042-daily-private-inference-resolves-active-validated-profile.md)
43. [Presentation adapters share a UI-neutral application facade](0043-presentation-adapters-share-application-facade.md)
44. [Dedicated-machine acceptance is versioned, payload-free evidence](0044-machine-acceptance-is-versioned-evidence.md)
45. [Final release readiness derives from exact evidence chains](0045-release-readiness-derives-from-evidence.md)
46. [macOS release building is local and fail-closed](0046-macos-release-build-is-local-fail-closed.md)
47. [Lexical retrieval uses deterministic BM25 relevance](0047-lexical-retrieval-uses-bm25.md)
48. [Voice is local-only and audio is ephemeral by default](0048-voice-is-local-and-ephemeral.md)
49. [Web research requires exact-query disclosure approval](0049-web-research-requires-query-approval.md)

## Adding an ADR

Use the next four-digit sequence number and a short kebab-case filename. Record
the decision before or with the implementation that depends on it. If a later
decision replaces an earlier one, mark the earlier ADR superseded and link both
directions rather than deleting history.
