import Foundation
import ServiceManagement
import Testing
import UserNotifications
@testable import AllyDesktopCore

@Test func decodesBridgeInfoEnvelope() throws {
    let data = Data(#"{"id":"1","ok":true,"result":{"protocol_version":6,"ally_version":"0.1.0.dev0","transport":"stdio","capabilities":["bootstrap"]}}"#.utf8)
    let decoder = JSONDecoder()
    decoder.keyDecodingStrategy = .convertFromSnakeCase
    let envelope = try decoder.decode(BridgeEnvelope<BridgeInfo>.self, from: data)

    #expect(envelope.ok)
    #expect(envelope.result?.protocolVersion == 6)
    #expect(envelope.result?.transport == "stdio")
    #expect(envelope.result?.capabilities == ["bootstrap"])
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
        "schema_version": 1,
        "bundle_identifier": bundleIdentifier,
        "ally_version": "0.1.0.dev0",
        "bridge_protocol_version": bridgeProtocolVersion,
        "helper_relative_path": DesktopReleaseBundle.helperRelativePath,
        "helper_sha256": helperHash,
        "source_revision": "synthetic",
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
