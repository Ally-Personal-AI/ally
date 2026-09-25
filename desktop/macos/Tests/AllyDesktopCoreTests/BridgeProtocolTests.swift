import Foundation
import ServiceManagement
import Testing
import UserNotifications
@testable import AllyDesktopCore

@Test func decodesBridgeInfoEnvelope() throws {
    let data = Data(#"{"id":"1","ok":true,"result":{"protocol_version":14,"ally_version":"0.1.0.dev0","transport":"stdio","capabilities":["bootstrap","conversation.search","conversation.delete","knowledge.delete","instructions.list","instructions.resolve","memory.remember","memory.propose","memory.accept_proposals","research.inspect","research.search","research.answer","task.propose","task.create"]}}"#.utf8)
    let decoder = JSONDecoder()
    decoder.keyDecodingStrategy = .convertFromSnakeCase
    let envelope = try decoder.decode(BridgeEnvelope<BridgeInfo>.self, from: data)

    #expect(envelope.ok)
    #expect(envelope.result?.protocolVersion == 14)
    #expect(envelope.result?.transport == "stdio")
    #expect(
        envelope.result?.capabilities == [
            "bootstrap",
            "conversation.search",
            "conversation.delete",
            "knowledge.delete",
            "instructions.list",
            "instructions.resolve",
            "memory.remember",
            "memory.propose",
            "memory.accept_proposals",
            "research.inspect",
            "research.search",
            "research.answer",
            "task.propose",
            "task.create",
        ]
    )
}

@Test func knowledgeUpdatePayloadReusesExistingSourceIdentity() throws {
    let data = Data(#"{"id":"00000000-0000-0000-0000-000000000020","uri":"ally-desktop://import/stable-source","title":"Synthetic notes.txt","media_type":"text/plain","current_revision":2,"created_at":"2026-09-25T00:00:00Z","updated_at":"2026-09-25T00:01:00Z"}"#.utf8)
    let decoder = JSONDecoder()
    decoder.keyDecodingStrategy = .convertFromSnakeCase
    let source = try decoder.decode(KnowledgeSourceSummary.self, from: data)
    let payload = KnowledgeSourceUpdatePayload(
        source: source,
        text: "Replacement synthetic knowledge."
    )
    let request = BridgeRequest(
        id: "synthetic-knowledge-update",
        method: "knowledge.ingest_text",
        params: payload.bridgeParams
    )
    let rendered = String(
        decoding: try JSONEncoder().encode(request),
        as: UTF8.self
    )

    #expect(rendered.contains("ally-desktop://import/stable-source"))
    #expect(rendered.contains("Synthetic notes.txt"))
    #expect(rendered.contains("Replacement synthetic knowledge."))
    #expect(rendered.contains("file:///private") == false)
    #expect(rendered.contains("path") == false)
}

@Test func decodesExactDeletionBoolean() throws {
    let data = Data(#"{"id":"1","ok":true,"result":true}"#.utf8)
    let decoder = JSONDecoder()
    let envelope = try decoder.decode(
        BridgeEnvelope<Bool>.self,
        from: data
    )

    #expect(envelope.result == true)
}

@Test func decodesConversationHistorySearchResult() throws {
    let data = Data(#"{"id":"1","ok":true,"result":[{"conversation":{"id":"00000000-0000-0000-0000-000000000010","title":"Synthetic orchard","created_at":"2026-09-25T00:00:00Z","updated_at":"2026-09-25T00:01:00Z"},"score":1.25,"match_kind":"message","message_id":"00000000-0000-0000-0000-000000000011","message_position":4,"message_role":"user","snippet":"The orchard marker is CEDAR-812."}]}"#.utf8)
    let decoder = JSONDecoder()
    decoder.keyDecodingStrategy = .convertFromSnakeCase
    let envelope = try decoder.decode(
        BridgeEnvelope<[ConversationSearchResult]>.self,
        from: data
    )

    #expect(envelope.result?.count == 1)
    #expect(envelope.result?[0].conversation.title == "Synthetic orchard")
    #expect(envelope.result?[0].matchKind == "message")
    #expect(envelope.result?[0].messagePosition == 4)
    #expect(envelope.result?[0].messageRole == "user")
    #expect(envelope.result?[0].snippet?.contains("CEDAR-812") == true)
}

@Test func decodesBootstrapWithoutRequiringPrivatePayloadFields() throws {
    let data = Data(#"{"id":"1","ok":true,"result":{"runtime":{"state":"unavailable","target":null,"error_code":"active_profile_unavailable"},"conversations":{"state":"available","items":[],"error_code":null},"tasks":{"state":"available","items":[],"error_code":null},"pending_attention":{"state":"available","items":[],"error_code":null},"attention_history":{"state":"available","items":[],"error_code":null},"service_history":{"state":"available","items":[],"error_code":null},"service_health":{"state":"available","report":{"status":"healthy","checks":[],"database_exists":true,"database_integrity_ok":true,"schema_current":true},"error_code":null}}}"#.utf8)
    let decoder = JSONDecoder()
    decoder.keyDecodingStrategy = .convertFromSnakeCase
    let envelope = try decoder.decode(BridgeEnvelope<BootstrapSnapshot>.self, from: data)

    #expect(envelope.result?.runtime.state == "unavailable")
    #expect(envelope.result?.conversations.items.isEmpty == true)
    #expect(envelope.result?.serviceHealth.report?.status == "healthy")
}

@Test func requestEncodingKeepsPrivateMessageInStdinPayloadModel() throws {
    let request = BridgeRequest(
        id: "synthetic",
        method: "conversation.send",
        params: [
            "conversation_id": .string("00000000-0000-0000-0000-000000000001"),
            "message": .string("synthetic private message"),
        ]
    )
    let encoded = try JSONEncoder().encode(request)
    let rendered = String(decoding: encoded, as: UTF8.self)

    #expect(rendered.contains("synthetic private message"))
    #expect(rendered.contains("conversation.send"))
}

@Test func decodesScopedInstructionsAndResolutionProvenance() throws {
    let profileData = Data(#"{"id":"1","ok":true,"result":{"scope":"project","scope_key":"synthetic-project","content":"Prefer metric units.","enabled":true,"created_at":"2026-09-25T00:00:00Z","updated_at":"2026-09-25T00:01:00Z"}}"#.utf8)
    let resolutionData = Data(#"{"id":"2","ok":true,"result":{"profiles":[{"scope":"global","scope_key":"","content":"Be concise.","enabled":true,"created_at":"2026-09-25T00:00:00Z","updated_at":"2026-09-25T00:00:00Z"},{"scope":"project","scope_key":"synthetic-project","content":"Prefer metric units.","enabled":true,"created_at":"2026-09-25T00:00:00Z","updated_at":"2026-09-25T00:01:00Z"}],"contributions":[{"scope":"global","scope_key":"","content":"Be concise."},{"scope":"project","scope_key":"synthetic-project","content":"Prefer metric units."},{"scope":"session","scope_key":"","content":"Answer briefly."}],"rendered":"[global]\\nBe concise.\\n\\n[project:synthetic-project]\\nPrefer metric units.\\n\\n[session]\\nAnswer briefly."}}"#.utf8)
    let decoder = JSONDecoder()
    decoder.keyDecodingStrategy = .convertFromSnakeCase

    let profile = try decoder.decode(
        BridgeEnvelope<UserInstructionsSummary>.self,
        from: profileData
    )
    let resolution = try decoder.decode(
        BridgeEnvelope<InstructionResolutionView>.self,
        from: resolutionData
    )

    #expect(profile.result?.displayScope == "Project: synthetic-project")
    #expect(profile.result?.enabled == true)
    #expect(resolution.result?.profiles.count == 2)
    #expect(resolution.result?.contributions.map(\.scope) == [
        "global",
        "project",
        "session",
    ])
    #expect(
        resolution.result?.contributions[1].displayScope
            == "Project: synthetic-project"
    )
    #expect(resolution.result?.rendered?.contains("[session]") == true)
}

@Test func encodesApprovedResearchAsExactLocalBridgePayload() throws {
    let request = BridgeRequest(
        id: "synthetic-research",
        method: "research.search",
        params: [
            "query": .string("synthetic public research query"),
            "count": .number(5),
            "approved": .bool(true),
        ]
    )
    let rendered = String(
        decoding: try JSONEncoder().encode(request),
        as: UTF8.self
    )

    #expect(rendered.contains("research.search"))
    #expect(rendered.contains("synthetic public research query"))
    #expect(rendered.contains("\"approved\":true"))
}

@Test func decodesResearchInspectionWithoutQueryPayload() throws {
    let data = Data(#"{"id":"1","ok":true,"result":{"request_id":"00000000-0000-0000-0000-000000000050","service":"synthetic.search","operation":"web.search","decision":"require_approval","fields":[{"name":"count","classification":"public"},{"name":"query","classification":"explicit_outbound"}],"error_class":null}}"#.utf8)
    let decoder = JSONDecoder()
    decoder.keyDecodingStrategy = .convertFromSnakeCase
    let envelope = try decoder.decode(
        BridgeEnvelope<EgressInspection>.self,
        from: data
    )

    #expect(envelope.result?.decision == "require_approval")
    #expect(envelope.result?.service == "synthetic.search")
    #expect(envelope.result?.fields.count == 2)
    #expect(envelope.result?.fields[1].classification == "explicit_outbound")
    #expect(String(decoding: data, as: UTF8.self).contains("synthetic public research query") == false)
}

@Test func decodesApprovedResearchResults() throws {
    let data = Data(#"{"id":"1","ok":true,"result":{"request_id":"00000000-0000-0000-0000-000000000051","service":"synthetic.search","operation":"web.search","decision":"allow","status":"succeeded","results":[{"title":"Synthetic public result","url":"https://example.test/research","description":"Synthetic public snippet."}],"more_results_available":false,"error_class":null}}"#.utf8)
    let decoder = JSONDecoder()
    decoder.keyDecodingStrategy = .convertFromSnakeCase
    let envelope = try decoder.decode(
        BridgeEnvelope<WebResearchExecution>.self,
        from: data
    )

    #expect(envelope.result?.status == "succeeded")
    #expect(envelope.result?.results.count == 1)
    #expect(envelope.result?.results[0].title == "Synthetic public result")
    #expect(envelope.result?.results[0].url == "https://example.test/research")
    #expect(envelope.result?.moreResultsAvailable == false)
}

@Test func decodesSourcedResearchAnswerExecution() throws {
    let data = Data(#"{"id":"1","ok":true,"result":{"search":{"request_id":"00000000-0000-0000-0000-000000000060","service":"synthetic.search","operation":"web.search","decision":"allow","status":"succeeded","results":[{"title":"Synthetic source","url":"https://example.test/source","description":"Synthetic snippet."}],"more_results_available":false,"error_class":null},"synthesis_status":"succeeded","synthesis":{"answer":"Synthetic answer. [1]","cited_result_indices":[1],"insufficient_evidence":false},"synthesis_error_class":null}}"#.utf8)
    let decoder = JSONDecoder()
    decoder.keyDecodingStrategy = .convertFromSnakeCase
    let envelope = try decoder.decode(
        BridgeEnvelope<WebResearchAnswerExecution>.self,
        from: data
    )

    #expect(envelope.result?.search.status == "succeeded")
    #expect(envelope.result?.search.results.count == 1)
    #expect(envelope.result?.synthesisStatus == "succeeded")
    #expect(envelope.result?.synthesis?.answer == "Synthetic answer. [1]")
    #expect(envelope.result?.synthesis?.citedResultIndices == [1])
    #expect(envelope.result?.synthesis?.insufficientEvidence == false)
}

@Test func helperEnvironmentDropsUnrelatedShellState() {
    let filtered = DesktopBridgeClient.helperEnvironment(
        source: [
            "HOME": "/tmp/synthetic-home",
            "TMPDIR": "/tmp/synthetic-tmp",
            "HTTP_PROXY": "http://example.invalid",
            "API_TOKEN": "synthetic-secret",
            "PATH": "/tmp/synthetic-path",
        ]
    )

    #expect(filtered["HOME"] == "/tmp/synthetic-home")
    #expect(filtered["TMPDIR"] == "/tmp/synthetic-tmp")
    #expect(filtered["HTTP_PROXY"] == nil)
    #expect(filtered["API_TOKEN"] == nil)
    #expect(filtered["PATH"] == nil)
}

@Test func decodesReviewedTaskPlanProposal() throws {
    let data = Data(#"{"id":"1","ok":true,"result":{"goal":"Inspect the local runtime","steps":[{"tool_name":"system.info","arguments":{}}]}}"#.utf8)
    let decoder = JSONDecoder()
    decoder.keyDecodingStrategy = .convertFromSnakeCase
    let envelope = try decoder.decode(
        BridgeEnvelope<TaskPlanProposal>.self,
        from: data
    )

    #expect(envelope.result?.goal == "Inspect the local runtime")
    #expect(envelope.result?.steps.count == 1)
    #expect(envelope.result?.steps[0].toolName == "system.info")
    #expect(envelope.result?.steps[0].argumentsText == "No arguments")
}

@Test func reviewedTaskPlanEncodesAsStrictCreatePayload() throws {
    let proposalData = Data(#"{"goal":"Inspect the local runtime","steps":[{"tool_name":"system.info","arguments":{}}]}"#.utf8)
    let decoder = JSONDecoder()
    decoder.keyDecodingStrategy = .convertFromSnakeCase
    let proposal = try decoder.decode(TaskPlanProposal.self, from: proposalData)
    let request = BridgeRequest(
        id: "synthetic-create",
        method: "task.create",
        params: ["plan": proposal.bridgeValue]
    )
    let rendered = String(
        decoding: try JSONEncoder().encode(request),
        as: UTF8.self
    )

    #expect(rendered.contains("task.create"))
    #expect(rendered.contains("Inspect the local runtime"))
    #expect(rendered.contains("system.info"))
    #expect(rendered.contains("approved") == false)
}

@Test func decodesTaskDetailWithExactApprovalState() throws {
    let data = Data(#"{"id":"1","ok":true,"result":{"task":{"id":"00000000-0000-0000-0000-000000000001","goal":"Synthetic task","status":"waiting_approval","failure":null,"created_at":"2026-01-01T00:00:00Z","updated_at":"2026-01-01T00:00:01Z"},"steps":[{"id":"00000000-0000-0000-0000-000000000002","task_id":"00000000-0000-0000-0000-000000000001","position":0,"tool_name":"test.reversible","arguments":{"value":"synthetic"},"status":"approval_required","attempts":1,"last_output":null,"last_error":null,"created_at":"2026-01-01T00:00:00Z","updated_at":"2026-01-01T00:00:01Z"}]}}"#.utf8)
    let decoder = JSONDecoder()
    decoder.keyDecodingStrategy = .convertFromSnakeCase
    let envelope = try decoder.decode(BridgeEnvelope<TaskView>.self, from: data)

    #expect(envelope.result?.task.status == "waiting_approval")
    #expect(envelope.result?.steps.count == 1)
    #expect(envelope.result?.steps[0].status == "approval_required")
    #expect(envelope.result?.steps[0].argumentsText == "value: synthetic")
}


@Test func decodesAndReencodesMemoryProposalBundle() throws {
    let data = Data(#"{"id":"1","ok":true,"result":{"schema_version":1,"generated_at":"2026-09-25T20:00:00Z","provider":"synthetic-local","model":"synthetic-model","source":{"type":"user","id":null,"uri":null},"privacy":"private","source_text_sha256":"aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa","memories":[{"kind":"preference","content":"Synthetic subject prefers oolong tea.","confidence":0.9,"importance":0.8}]}}"#.utf8)
    let decoder = JSONDecoder()
    decoder.keyDecodingStrategy = .convertFromSnakeCase
    let envelope = try decoder.decode(
        BridgeEnvelope<MemoryProposalBundleSummary>.self,
        from: data
    )

    #expect(envelope.result?.schemaVersion == 1)
    #expect(envelope.result?.memories.count == 1)
    #expect(envelope.result?.memories[0].kind == "preference")
    #expect(envelope.result?.memories[0].content == "Synthetic subject prefers oolong tea.")

    guard let bundle = envelope.result else {
        Issue.record("missing decoded memory proposal")
        return
    }
    let request = BridgeRequest(
        id: "synthetic-memory-accept",
        method: "memory.accept_proposals",
        params: [
            "bundle": bundle.bridgeValue,
            "indices": .array([.number(0)]),
        ]
    )
    let rendered = String(
        decoding: try JSONEncoder().encode(request),
        as: UTF8.self
    )

    #expect(rendered.contains("memory.accept_proposals"))
    #expect(rendered.contains("Synthetic subject prefers oolong tea."))
    #expect(rendered.contains("development_endpoint") == false)
    #expect(rendered.contains("development_model") == false)
}

@Test func decodesMemoryProvenanceAndInactiveState() throws {
    let data = Data(#"{"id":"1","ok":true,"result":{"id":"00000000-0000-0000-0000-000000000010","kind":"preference","content":"Synthetic preference.","source":{"type":"user","id":null,"uri":null},"confidence":1.0,"importance":0.8,"privacy":"private","created_at":"2026-01-01T00:00:00Z","updated_at":"2026-01-01T00:00:01Z","observed_at":"2026-01-01T00:00:00Z","valid_from":null,"valid_until":null,"supersedes":null,"superseded_at":"2026-01-01T00:00:01Z","superseded_by":"00000000-0000-0000-0000-000000000011","retracted_at":null}}"#.utf8)
    let decoder = JSONDecoder()
    decoder.keyDecodingStrategy = .convertFromSnakeCase
    let envelope = try decoder.decode(BridgeEnvelope<MemorySummary>.self, from: data)

    #expect(envelope.result?.source.type == "user")
    #expect(envelope.result?.supersededBy == "00000000-0000-0000-0000-000000000011")
    #expect(envelope.result?.isActive == false)
}

@Test func decodesKnowledgeDetailAndSearchModels() throws {
    let detailData = Data(#"{"id":"1","ok":true,"result":{"source":{"id":"00000000-0000-0000-0000-000000000020","uri":"ally-desktop://note/synthetic","title":"Synthetic note","media_type":"text/plain","current_revision":1,"created_at":"2026-01-01T00:00:00Z","updated_at":"2026-01-01T00:00:00Z"},"revisions":[{"id":"00000000-0000-0000-0000-000000000021","source_id":"00000000-0000-0000-0000-000000000020","revision":1,"sha256":"aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa","created_at":"2026-01-01T00:00:00Z"}],"current_chunks":[{"id":"00000000-0000-0000-0000-000000000022","source_id":"00000000-0000-0000-0000-000000000020","revision_id":"00000000-0000-0000-0000-000000000021","revision":1,"ordinal":0,"content":"Synthetic chunk.","start_char":0,"end_char":16,"sha256":"bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb","created_at":"2026-01-01T00:00:00Z"}]}}"#.utf8)
    let decoder = JSONDecoder()
    decoder.keyDecodingStrategy = .convertFromSnakeCase
    let detail = try decoder.decode(BridgeEnvelope<KnowledgeSourceView>.self, from: detailData)

    #expect(detail.result?.source.title == "Synthetic note")
    #expect(detail.result?.revisions.count == 1)
    #expect(detail.result?.currentChunks[0].content == "Synthetic chunk.")

    let searchData = Data(#"{"id":"2","ok":true,"result":{"source":{"id":"00000000-0000-0000-0000-000000000020","uri":"ally-desktop://note/synthetic","title":"Synthetic note","media_type":"text/plain","current_revision":1,"created_at":"2026-01-01T00:00:00Z","updated_at":"2026-01-01T00:00:00Z"},"chunk":{"id":"00000000-0000-0000-0000-000000000022","source_id":"00000000-0000-0000-0000-000000000020","revision_id":"00000000-0000-0000-0000-000000000021","revision":1,"ordinal":0,"content":"Synthetic chunk.","start_char":0,"end_char":16,"sha256":"bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb","created_at":"2026-01-01T00:00:00Z"},"score":0.75}}"#.utf8)
    let hit = try decoder.decode(BridgeEnvelope<KnowledgeSearchResult>.self, from: searchData)

    #expect(hit.result?.id == "00000000-0000-0000-0000-000000000022")
    #expect(hit.result?.score == 0.75)
}


@Test func decodesValidatedRuntimeProfileCatalog() throws {
    let data = Data(#"{"id":"1","ok":true,"result":{"items":[{"profile_id":"aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa","generated_at":"2026-09-24T00:00:00Z","ally_version":"0.1.0.dev0","model":"synthetic-model","runtime_name":"synthetic-runtime","runtime_version":"1.0","model_source":"synthetic-source","quantization":"Q4_K_M","precision":"mixed","model_size_bytes":null,"context_length":32768,"apple_model":"Mac17,1","apple_chip":"Apple M5 Max","total_memory_bytes":137438953472,"time_to_first_token_ms":120.0,"generation_tokens_per_second":40.0,"maximum_tested_context_tokens":16384,"capability_evidence_name":"capability.json","capability_evidence_sha256":"bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb","privacy_evidence_name":"privacy.json","privacy_evidence_sha256":"cccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccc","workflow_evidence_name":"workflows.json","workflow_evidence_sha256":"dddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddd","active":true}],"active_profile_id":"aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"}}"#.utf8)
    let decoder = JSONDecoder()
    decoder.keyDecodingStrategy = .convertFromSnakeCase
    let envelope = try decoder.decode(
        BridgeEnvelope<RuntimeProfileCatalogView>.self,
        from: data
    )

    #expect(envelope.result?.items.count == 1)
    #expect(envelope.result?.items[0].active == true)
    #expect(envelope.result?.items[0].model == "synthetic-model")
    #expect(envelope.result?.items[0].appleChip == "Apple M5 Max")
    #expect(envelope.result?.activeProfileId == String(repeating: "a", count: 64))
}


@Test func decodesAttentionEventWithLocalPayloadAndDeliveryHistory() throws {
    let data = Data(#"{"id":"1","ok":true,"result":{"event":{"id":"00000000-0000-0000-0000-000000000030","type":"synthetic.desktop-attention","source":"swift-test","importance":"urgent","attention":"notify","payload":{"summary":"Synthetic attention summary.","count":2},"dedupe_key":"synthetic:30","created_at":"2026-09-24T00:00:00Z","handled_at":null},"deliveries":[{"id":"00000000-0000-0000-0000-000000000031","event_id":"00000000-0000-0000-0000-000000000030","sink_id":"macos.notification","status":"succeeded","attempts":1,"last_error":null,"created_at":"2026-09-24T00:00:01Z","updated_at":"2026-09-24T00:00:01Z","delivered_at":"2026-09-24T00:00:01Z"}]}}"#.utf8)
    let decoder = JSONDecoder()
    decoder.keyDecodingStrategy = .convertFromSnakeCase
    let envelope = try decoder.decode(
        BridgeEnvelope<AttentionEventView>.self,
        from: data
    )

    #expect(envelope.result?.event.displayText == "Synthetic attention summary.")
    #expect(envelope.result?.event.dedupeKey == "synthetic:30")
    #expect(envelope.result?.deliveries.count == 1)
    #expect(envelope.result?.deliveries[0].sinkId == "macos.notification")
    #expect(envelope.result?.deliveries[0].status == "succeeded")
}

@Test func mapsModernNotificationAuthorizationStates() {
    #expect(
        DesktopNotificationAuthorizationClient.state(for: .authorized)
            == .authorized
    )
    #expect(
        DesktopNotificationAuthorizationClient.state(for: .denied)
            == .denied
    )
    #expect(
        DesktopNotificationAuthorizationClient.state(for: .notDetermined)
            == .notDetermined
    )
    #expect(
        DesktopNotificationAuthorizationClient.state(for: .provisional)
            == .provisional
    )
}


private func makeSyntheticReleaseBundle(
    bundleIdentifier: String = DesktopReleaseBundle.bundleIdentifier,
    bridgeProtocolVersion: Int = DesktopBridgeClient.supportedProtocolVersion,
    helperContents: String = "#!/bin/sh\necho synthetic\n"
) throws -> (root: URL, helper: URL) {
    let root = FileManager.default.temporaryDirectory
        .appendingPathComponent(UUID().uuidString, isDirectory: true)
        .appendingPathComponent("Ally.app", isDirectory: true)
    let helpers = root.appendingPathComponent("Contents/Helpers", isDirectory: true)
    let resources = root.appendingPathComponent("Contents/Resources", isDirectory: true)
    try FileManager.default.createDirectory(
        at: helpers,
        withIntermediateDirectories: true
    )
    try FileManager.default.createDirectory(
        at: resources,
        withIntermediateDirectories: true
    )

    let helper = helpers.appendingPathComponent("ally-desktop-bridge")
    try Data(helperContents.utf8).write(to: helper)
    try FileManager.default.setAttributes(
        [.posixPermissions: 0o755],
        ofItemAtPath: helper.path
    )
    let helperHash = try DesktopReleaseBundle.sha256(of: helper)
    let manifest: [String: Any] = [
        "schema_version": 2,
        "bundle_identifier": bundleIdentifier,
        "ally_version": "0.1.0.dev0",
        "build_version": 7,
        "bridge_protocol_version": bridgeProtocolVersion,
        "database_schema_version": 14,
        "helper_relative_path": DesktopReleaseBundle.helperRelativePath,
        "helper_sha256": helperHash,
        "source_revision": String(repeating: "a", count: 40),
    ]
    let manifestData = try JSONSerialization.data(
        withJSONObject: manifest,
        options: [.sortedKeys]
    )
    try manifestData.write(
        to: resources.appendingPathComponent("release-manifest.json")
    )
    return (root, helper)
}

@Test func releaseHelperResolutionIgnoresDevelopmentOverride() throws {
    let release = try makeSyntheticReleaseBundle()
    defer { try? FileManager.default.removeItem(at: release.root.deletingLastPathComponent()) }

    let resolved = try DesktopBridgeClient.resolveHelper(
        environment: [
            DesktopBridgeClient.helperEnvironmentKey: "/tmp/untrusted-helper",
        ],
        bundleURL: release.root,
        bundleIdentifier: DesktopReleaseBundle.bundleIdentifier,
        allowDevelopmentOverride: false
    )

    #expect(resolved.standardizedFileURL == release.helper.standardizedFileURL)
}

@Test func releaseHelperResolutionRejectsTampering() throws {
    let release = try makeSyntheticReleaseBundle()
    defer { try? FileManager.default.removeItem(at: release.root.deletingLastPathComponent()) }

    try Data("#!/bin/sh\necho tampered\n".utf8).write(to: release.helper)

    #expect(throws: DesktopBridgeError.helperIntegrityFailed) {
        _ = try DesktopBridgeClient.resolveHelper(
            environment: [:],
            bundleURL: release.root,
            bundleIdentifier: DesktopReleaseBundle.bundleIdentifier,
            allowDevelopmentOverride: false
        )
    }
}

@Test func releaseHelperResolutionRejectsWrongBundleIdentity() throws {
    let release = try makeSyntheticReleaseBundle()
    defer { try? FileManager.default.removeItem(at: release.root.deletingLastPathComponent()) }

    #expect(throws: DesktopBridgeError.releaseManifestInvalid) {
        _ = try DesktopBridgeClient.resolveHelper(
            environment: [:],
            bundleURL: release.root,
            bundleIdentifier: "invalid.synthetic.bundle",
            allowDevelopmentOverride: false
        )
    }
}

@Test func releaseHelperResolutionRejectsProtocolMismatch() throws {
    let release = try makeSyntheticReleaseBundle(
        bridgeProtocolVersion: DesktopBridgeClient.supportedProtocolVersion + 1
    )
    defer { try? FileManager.default.removeItem(at: release.root.deletingLastPathComponent()) }

    #expect(throws: DesktopBridgeError.releaseManifestInvalid) {
        _ = try DesktopBridgeClient.resolveHelper(
            environment: [:],
            bundleURL: release.root,
            bundleIdentifier: DesktopReleaseBundle.bundleIdentifier,
            allowDevelopmentOverride: false
        )
    }
}

@Test func developmentHelperOverrideStillRequiresAbsoluteExecutable() throws {
    let root = FileManager.default.temporaryDirectory
        .appendingPathComponent(UUID().uuidString, isDirectory: true)
    try FileManager.default.createDirectory(at: root, withIntermediateDirectories: true)
    defer { try? FileManager.default.removeItem(at: root) }

    let helper = root.appendingPathComponent("synthetic-helper")
    try Data("#!/bin/sh\nexit 0\n".utf8).write(to: helper)
    try FileManager.default.setAttributes(
        [.posixPermissions: 0o755],
        ofItemAtPath: helper.path
    )

    let resolved = try DesktopBridgeClient.resolveHelper(
        environment: [DesktopBridgeClient.helperEnvironmentKey: helper.path],
        bundleURL: root,
        bundleIdentifier: nil,
        allowDevelopmentOverride: true
    )
    #expect(resolved.standardizedFileURL == helper.standardizedFileURL)

    #expect(throws: DesktopBridgeError.helperNotExecutable) {
        _ = try DesktopBridgeClient.resolveHelper(
            environment: [DesktopBridgeClient.helperEnvironmentKey: "relative-helper"],
            bundleURL: root,
            bundleIdentifier: nil,
            allowDevelopmentOverride: true
        )
    }
}


@Test func decodesDesktopProactivePreparationWithoutPrivatePayload() throws {
    let data = Data(#"{"id":"1","ok":true,"result":{"run":{"id":"00000000-0000-0000-0000-000000000040","status":"succeeded","observed_at":"2026-09-25T00:00:00Z","started_at":"2026-09-25T00:00:00Z","finished_at":"2026-09-25T00:00:01Z","scheduled_events":1,"delivery_attempts":0,"delivery_failures":0,"error_class":null},"candidates":[{"event_id":"00000000-0000-0000-0000-000000000041","delivery_key":"attention:macos.notification:00000000-0000-0000-0000-000000000041","title":"Ally","body":"Synthetic reminder.","attention":"notify","created_at":"2026-09-25T00:00:00Z"}]}}"#.utf8)
    let decoder = JSONDecoder()
    decoder.keyDecodingStrategy = .convertFromSnakeCase
    let envelope = try decoder.decode(
        BridgeEnvelope<DesktopProactivePreparation>.self,
        from: data
    )

    #expect(envelope.result?.run.scheduledEvents == 1)
    #expect(envelope.result?.candidates.count == 1)
    #expect(envelope.result?.candidates[0].title == "Ally")
    #expect(envelope.result?.candidates[0].body == "Synthetic reminder.")
}

@Test func notificationIdentifierReconciliationIncludesPendingRequests() {
    let content = UNMutableNotificationContent()
    content.title = "Synthetic"
    let pending = UNNotificationRequest(
        identifier: "attention:macos.notification:synthetic",
        content: content,
        trigger: nil
    )

    let identifiers = DesktopNotificationDeliveryClient.knownIdentifiers(
        delivered: [],
        pending: [pending]
    )

    #expect(identifiers.contains("attention:macos.notification:synthetic"))
}

@Test func decodesPathFreeLegacyManagedServiceState() throws {
    let data = Data(#"{"id":"1","ok":true,"result":{"supported":true,"configured":true,"definition_state":"recognized_legacy","loaded":true,"running":false,"label":"ai.ally.proactive-service","can_retire":true}}"#.utf8)
    let decoder = JSONDecoder()
    decoder.keyDecodingStrategy = .convertFromSnakeCase
    let envelope = try decoder.decode(
        BridgeEnvelope<LegacyManagedServiceView>.self,
        from: data
    )

    #expect(envelope.result?.definitionState == "recognized_legacy")
    #expect(envelope.result?.canRetire == true)
    #expect(envelope.result?.label == "ai.ally.proactive-service")
}

@Test func mapsSMAppServiceStatesWithoutRegistering() {
    #expect(
        DesktopBackgroundServiceClient.state(for: .enabled) == .enabled
    )
    #expect(
        DesktopBackgroundServiceClient.state(for: .notRegistered)
            == .notRegistered
    )
    #expect(
        DesktopBackgroundServiceClient.state(for: .requiresApproval)
            == .requiresApproval
    )
    #expect(
        DesktopBackgroundServiceClient.state(for: .notFound) == .notFound
    )
}
