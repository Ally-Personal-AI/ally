import Foundation
import Testing
@testable import AllyDesktopCore

@Test func decodesBridgeInfoEnvelope() throws {
    let data = Data(#"{"id":"1","ok":true,"result":{"protocol_version":2,"ally_version":"0.1.0.dev0","transport":"stdio","capabilities":["bootstrap"]}}"#.utf8)
    let decoder = JSONDecoder()
    decoder.keyDecodingStrategy = .convertFromSnakeCase
    let envelope = try decoder.decode(BridgeEnvelope<BridgeInfo>.self, from: data)

    #expect(envelope.ok)
    #expect(envelope.result?.protocolVersion == 2)
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
