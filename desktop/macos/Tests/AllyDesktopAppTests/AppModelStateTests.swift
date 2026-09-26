import Foundation
import Testing
@testable import AllyDesktop
@testable import AllyDesktopCore

private actor AsyncGate {
    private var isOpen = false
    private var waiters: [CheckedContinuation<Void, Never>] = []

    func wait() async {
        if isOpen {
            return
        }
        await withCheckedContinuation { continuation in
            waiters.append(continuation)
        }
    }

    func open() {
        guard !isOpen else {
            return
        }
        isOpen = true
        let pending = waiters
        waiters.removeAll()
        for waiter in pending {
            waiter.resume()
        }
    }
}

private enum FakeReply: Sendable {
    case json(String)
    case gatedJSON(String, AsyncGate)
    case gatedFailure(DesktopBridgeError, AsyncGate)
    case failure(DesktopBridgeError)
}

private struct RecordedBridgeCall: Sendable, Equatable {
    let method: String
    let params: [String: JSONValue]
}

private actor FakeBridgeClient: DesktopBridgeCalling {
    private var replies: [String: [FakeReply]]
    private var recordedCalls: [RecordedBridgeCall] = []

    init(replies: [String: [FakeReply]]) {
        self.replies = replies
    }

    func call<Result: Decodable & Sendable>(
        _ method: String,
        params: [String: JSONValue],
        as resultType: Result.Type
    ) async throws -> Result {
        recordedCalls.append(
            RecordedBridgeCall(method: method, params: params)
        )
        guard var queue = replies[method], !queue.isEmpty else {
            throw DesktopBridgeError.requestFailed(
                code: "missing_fake_reply",
                message: "Synthetic bridge reply is missing."
            )
        }
        let reply = queue.removeFirst()
        replies[method] = queue

        switch reply {
        case .failure(let error):
            throw error
        case .gatedFailure(let error, let gate):
            await gate.wait()
            throw error
        case .gatedJSON(let payload, let gate):
            await gate.wait()
            return try Self.decodeReply(
                payload,
                as: resultType
            )
        case .json(let payload):
            return try Self.decodeReply(
                payload,
                as: resultType
            )
        }
    }

    private static func decodeReply<Result: Decodable & Sendable>(
        _ payload: String,
        as resultType: Result.Type
    ) throws -> Result {
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        return try decoder.decode(
            Result.self,
            from: Data(payload.utf8)
        )
    }

    func calls() -> [RecordedBridgeCall] {
        recordedCalls
    }

    func callCount() -> Int {
        recordedCalls.count
    }

}

private func waitForCallCount(
    _ expected: Int,
    bridge: FakeBridgeClient
) async {
    for _ in 0..<2_000 {
        if await bridge.callCount() >= expected {
            return
        }
        await Task.yield()
    }
    Issue.record("Timed out waiting for synthetic bridge calls.")
}

private func waitForMethodCallCount(
    _ expected: Int,
    method: String,
    bridge: FakeBridgeClient
) async {
    for _ in 0..<2_000 {
        let count = await bridge.calls()
            .filter { $0.method == method }
            .count
        if count >= expected {
            return
        }
        await Task.yield()
    }
    Issue.record("Timed out waiting for synthetic \(method) calls.")
}

private let emptyBootstrapJSON = #"{"runtime":{"state":"unavailable","target":null,"error_code":"active_profile_unavailable"},"conversations":{"state":"available","items":[],"error_code":null},"tasks":{"state":"available","items":[],"error_code":null},"pending_attention":{"state":"available","items":[],"error_code":null},"attention_history":{"state":"available","items":[],"error_code":null},"service_history":{"state":"available","items":[],"error_code":null},"service_health":{"state":"available","report":{"status":"healthy","checks":[]},"error_code":null}}"#

private let conversationViewJSON = #"{"conversation":{"id":"00000000-0000-0000-0000-000000000001","title":"Synthetic conversation","created_at":"2026-09-25T00:00:00Z","updated_at":"2026-09-25T00:01:00Z"},"messages":[]}"#

private let newerConversationViewJSON = #"{"conversation":{"id":"00000000-0000-0000-0000-000000000003","title":"Newer synthetic conversation","created_at":"2026-09-25T00:02:00Z","updated_at":"2026-09-25T00:03:00Z"},"messages":[]}"#

private let firstMemoryJSON = #"{"id":"00000000-0000-0000-0000-000000000010","kind":"semantic","content":"Older synthetic memory.","source":{"type":"user","id":null,"uri":null},"confidence":1.0,"importance":0.5,"privacy":"private","created_at":"2026-09-25T00:00:00Z","updated_at":"2026-09-25T00:00:00Z","observed_at":"2026-09-25T00:00:00Z","valid_from":null,"valid_until":null,"supersedes":null,"superseded_at":null,"superseded_by":null,"retracted_at":null}"#

private let secondMemoryJSON = #"{"id":"00000000-0000-0000-0000-000000000011","kind":"semantic","content":"Newer synthetic memory.","source":{"type":"user","id":null,"uri":null},"confidence":1.0,"importance":0.5,"privacy":"private","created_at":"2026-09-25T00:01:00Z","updated_at":"2026-09-25T00:01:00Z","observed_at":"2026-09-25T00:01:00Z","valid_from":null,"valid_until":null,"supersedes":null,"superseded_at":null,"superseded_by":null,"retracted_at":null}"#

private let conversationSearchJSON = #"[{"conversation":{"id":"00000000-0000-0000-0000-000000000001","title":"Synthetic conversation","created_at":"2026-09-25T00:00:00Z","updated_at":"2026-09-25T00:01:00Z"},"score":1.0,"match_kind":"message","message_id":"00000000-0000-0000-0000-000000000002","message_position":0,"message_role":"user","snippet":"Synthetic result."}]"#

private let knowledgeSourceV1JSON = #"{"id":"00000000-0000-0000-0000-000000000020","uri":"ally-desktop://import/stable-source","title":"Synthetic notes.txt","media_type":"text/plain","current_revision":1,"created_at":"2026-09-25T00:00:00Z","updated_at":"2026-09-25T00:00:00Z"}"#

private let knowledgeSourceV2JSON = #"{"id":"00000000-0000-0000-0000-000000000020","uri":"ally-desktop://import/stable-source","title":"Synthetic notes.txt","media_type":"text/plain","current_revision":2,"created_at":"2026-09-25T00:00:00Z","updated_at":"2026-09-25T00:02:00Z"}"#

private let knowledgeIngestV2JSON = #"{"source":{"id":"00000000-0000-0000-0000-000000000020","uri":"ally-desktop://import/stable-source","title":"Synthetic notes.txt","media_type":"text/plain","current_revision":2,"created_at":"2026-09-25T00:00:00Z","updated_at":"2026-09-25T00:02:00Z"},"revision":{"id":"00000000-0000-0000-0000-000000000022","source_id":"00000000-0000-0000-0000-000000000020","revision":2,"sha256":"aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa","created_at":"2026-09-25T00:02:00Z"}}"#

private let knowledgeDetailV1JSON = #"{"source":{"id":"00000000-0000-0000-0000-000000000020","uri":"ally-desktop://import/stable-source","title":"Synthetic notes.txt","media_type":"text/plain","current_revision":1,"created_at":"2026-09-25T00:00:00Z","updated_at":"2026-09-25T00:00:00Z"},"revisions":[{"id":"00000000-0000-0000-0000-000000000023","source_id":"00000000-0000-0000-0000-000000000020","revision":1,"sha256":"bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb","created_at":"2026-09-25T00:00:00Z"}],"current_chunks":[]}"#

private let knowledgeDetailV2JSON = #"{"source":{"id":"00000000-0000-0000-0000-000000000020","uri":"ally-desktop://import/stable-source","title":"Synthetic notes.txt","media_type":"text/plain","current_revision":2,"created_at":"2026-09-25T00:00:00Z","updated_at":"2026-09-25T00:02:00Z"},"revisions":[{"id":"00000000-0000-0000-0000-000000000022","source_id":"00000000-0000-0000-0000-000000000020","revision":2,"sha256":"aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa","created_at":"2026-09-25T00:02:00Z"}],"current_chunks":[]}"#

private let secondKnowledgeDetailJSON = #"{"source":{"id":"00000000-0000-0000-0000-000000000024","uri":"ally-desktop://note/newer","title":"Newer synthetic note","media_type":"text/plain","current_revision":1,"created_at":"2026-09-25T00:03:00Z","updated_at":"2026-09-25T00:03:00Z"},"revisions":[],"current_chunks":[]}"#

private let knowledgeSearchJSON = #"[{"source":{"id":"00000000-0000-0000-0000-000000000020","uri":"ally-desktop://import/stable-source","title":"Synthetic notes.txt","media_type":"text/plain","current_revision":1,"created_at":"2026-09-25T00:00:00Z","updated_at":"2026-09-25T00:00:00Z"},"chunk":{"id":"00000000-0000-0000-0000-000000000021","source_id":"00000000-0000-0000-0000-000000000020","revision_id":"00000000-0000-0000-0000-000000000023","revision":1,"ordinal":0,"content":"Synthetic old content.","start_char":0,"end_char":22,"sha256":"bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb","created_at":"2026-09-25T00:00:00Z"},"score":1.0}]"#

private let backupManifestJSON = #"{"format":"ally-backup","schema_version":1,"created_at":"2026-09-25T22:00:00Z","ally_version":"0.1.0.dev0","database":{"filename":"ally.sqlite3","sha256":"aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa","size_bytes":4096,"schema_versions":[1,2,3,14]}}"#

private let taskProposalJSON = #"{"goal":"Inspect the local runtime","steps":[{"tool_name":"system.info","arguments":{}}]}"#

private let taskViewJSON = #"{"task":{"id":"00000000-0000-0000-0000-000000000030","goal":"Inspect the local runtime","status":"pending","failure":null,"created_at":"2026-09-25T00:00:00Z","updated_at":"2026-09-25T00:00:00Z"},"steps":[{"id":"00000000-0000-0000-0000-000000000031","task_id":"00000000-0000-0000-0000-000000000030","position":0,"tool_name":"system.info","arguments":{},"status":"pending","attempts":0,"last_output":null,"last_error":null,"created_at":"2026-09-25T00:00:00Z","updated_at":"2026-09-25T00:00:00Z"}]}"#

private let secondTaskViewJSON = #"{"task":{"id":"00000000-0000-0000-0000-000000000032","goal":"Inspect newer state","status":"pending","failure":null,"created_at":"2026-09-25T00:02:00Z","updated_at":"2026-09-25T00:02:00Z"},"steps":[]}"#

private let firstAttentionJSON = #"{"event":{"id":"00000000-0000-0000-0000-000000000040","type":"synthetic.old","source":"test","importance":"normal","attention":"notify","payload":{"summary":"Older synthetic attention."},"dedupe_key":"old","created_at":"2026-09-25T00:00:00Z","handled_at":null},"deliveries":[]}"#

private let secondAttentionJSON = #"{"event":{"id":"00000000-0000-0000-0000-000000000041","type":"synthetic.new","source":"test","importance":"normal","attention":"notify","payload":{"summary":"Newer synthetic attention."},"dedupe_key":"new","created_at":"2026-09-25T00:01:00Z","handled_at":null},"deliveries":[]}"#

private let researchResultsJSON = #"[{"title":"Synthetic result","url":"https://example.test/source","description":"Synthetic public snippet."}]"#

private let researchSynthesisJSON = #"{"answer":"Synthetic answer. [1]","cited_result_indices":[1],"insufficient_evidence":false}"#

private let newerConversationSearchJSON = #"[{"conversation":{"id":"00000000-0000-0000-0000-000000000003","title":"Newer synthetic conversation","created_at":"2026-09-25T00:02:00Z","updated_at":"2026-09-25T00:03:00Z"},"score":2.0,"match_kind":"message","message_id":"00000000-0000-0000-0000-000000000004","message_position":0,"message_role":"user","snippet":"Newer synthetic result."}]"#

private let firstMemorySearchJSON = #"[{"id":"00000000-0000-0000-0000-000000000010","kind":"semantic","content":"Older synthetic memory.","source":{"type":"user","id":null,"uri":null},"confidence":1.0,"importance":0.5,"privacy":"private","created_at":"2026-09-25T00:00:00Z","updated_at":"2026-09-25T00:00:00Z","observed_at":"2026-09-25T00:00:00Z","valid_from":null,"valid_until":null,"supersedes":null,"superseded_at":null,"superseded_by":null,"retracted_at":null}]"#

private let secondMemorySearchJSON = #"[{"id":"00000000-0000-0000-0000-000000000011","kind":"semantic","content":"Newer synthetic memory.","source":{"type":"user","id":null,"uri":null},"confidence":1.0,"importance":0.5,"privacy":"private","created_at":"2026-09-25T00:01:00Z","updated_at":"2026-09-25T00:01:00Z","observed_at":"2026-09-25T00:01:00Z","valid_from":null,"valid_until":null,"supersedes":null,"superseded_at":null,"superseded_by":null,"retracted_at":null}]"#

private let newerKnowledgeSearchJSON = #"[{"source":{"id":"00000000-0000-0000-0000-000000000024","uri":"ally-desktop://note/newer","title":"Newer synthetic note","media_type":"text/plain","current_revision":1,"created_at":"2026-09-25T00:03:00Z","updated_at":"2026-09-25T00:03:00Z"},"chunk":{"id":"00000000-0000-0000-0000-000000000025","source_id":"00000000-0000-0000-0000-000000000024","revision_id":"00000000-0000-0000-0000-000000000026","revision":1,"ordinal":0,"content":"Newer synthetic search content.","start_char":0,"end_char":31,"sha256":"cccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccc","created_at":"2026-09-25T00:03:00Z"},"score":2.0}]"#

private let instructionResolutionJSON = #"{"profiles":[{"scope":"global","scope_key":"","content":"Be concise.","enabled":true,"created_at":"2026-09-25T00:00:00Z","updated_at":"2026-09-25T00:00:00Z"}],"contributions":[{"scope":"global","scope_key":"","content":"Be concise."}],"rendered":"[global]\nBe concise."}"#

private let instructionProfileJSON = #"{"scope":"global","scope_key":"","content":"Prefer updated synthetic instructions.","enabled":true,"created_at":"2026-09-25T00:00:00Z","updated_at":"2026-09-25T00:02:00Z"}"#

private let instructionProfileListJSON = #"[{"scope":"global","scope_key":"","content":"Prefer updated synthetic instructions.","enabled":true,"created_at":"2026-09-25T00:00:00Z","updated_at":"2026-09-25T00:02:00Z"}]"#

private let researchInspectionJSON = #"{"request_id":"00000000-0000-0000-0000-000000000050","service":"synthetic.search","operation":"web.search","decision":"require_approval","fields":[{"name":"count","classification":"public"},{"name":"query","classification":"explicit_outbound"}],"error_class":null}"#

private let researchAnswerJSON = #"{"search":{"request_id":"00000000-0000-0000-0000-000000000060","service":"synthetic.search","operation":"web.search","decision":"allow","status":"succeeded","results":[{"title":"Newer synthetic source","url":"https://example.test/newer-source","description":"Newer synthetic snippet."}],"more_results_available":false,"error_class":null},"synthesis_status":"succeeded","synthesis":{"answer":"Newer synthetic answer. [1]","cited_result_indices":[1],"insufficient_evidence":false},"synthesis_error_class":null}"#

private let olderMemoryProposalJSON = #"{"schema_version":1,"generated_at":"2026-09-25T20:00:00Z","provider":"synthetic-local","model":"synthetic-model","source":{"type":"user","id":null,"uri":null},"privacy":"private","source_text_sha256":"aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa","memories":[{"kind":"preference","content":"Older synthetic proposal.","confidence":0.9,"importance":0.8}]}"#

private let newerMemoryProposalJSON = #"{"schema_version":1,"generated_at":"2026-09-25T20:01:00Z","provider":"synthetic-local","model":"synthetic-model","source":{"type":"user","id":null,"uri":null},"privacy":"private","source_text_sha256":"bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb","memories":[{"kind":"preference","content":"Newer synthetic proposal.","confidence":0.95,"importance":0.85}]}"#

private let newerTaskProposalJSON = #"{"goal":"Inspect newer synthetic state","steps":[{"tool_name":"system.info","arguments":{}}]}"#

private let bridgeInfoJSON = #"{"protocol_version":15,"ally_version":"0.1.0.dev0","transport":"stdio","capabilities":[]}"#

private let staleBootstrapJSON = #"{"runtime":{"state":"unavailable","target":null,"error_code":"active_profile_unavailable"},"conversations":{"state":"available","items":[{"id":"00000000-0000-0000-0000-000000000001","title":"Stale synthetic conversation","created_at":"2026-09-25T00:00:00Z","updated_at":"2026-09-25T00:01:00Z"}],"error_code":null},"tasks":{"state":"available","items":[],"error_code":null},"pending_attention":{"state":"available","items":[],"error_code":null},"attention_history":{"state":"available","items":[],"error_code":null},"service_history":{"state":"available","items":[],"error_code":null},"service_health":{"state":"available","report":{"status":"healthy","checks":[]},"error_code":null}}"#

private let emptyRuntimeCatalogJSON = #"{"items":[],"active_profile_id":null}"#

private let selectedRuntimeCatalogJSON = #"{"items":[],"active_profile_id":"aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"}"#

private let oldInstructionProfileListJSON = #"[{"scope":"global","scope_key":"","content":"Older synthetic instructions.","enabled":true,"created_at":"2026-09-25T00:00:00Z","updated_at":"2026-09-25T00:00:00Z"}]"#

private let oldAttentionEventListJSON = #"[{"id":"00000000-0000-0000-0000-000000000040","type":"synthetic.old","source":"test","importance":"normal","attention":"notify","payload":{"summary":"Older synthetic attention."},"dedupe_key":"old","created_at":"2026-09-25T00:00:00Z","handled_at":null}]"#

private let handledAttentionEventListJSON = #"[{"id":"00000000-0000-0000-0000-000000000040","type":"synthetic.old","source":"test","importance":"normal","attention":"notify","payload":{"summary":"Older synthetic attention."},"dedupe_key":"old","created_at":"2026-09-25T00:00:00Z","handled_at":"2026-09-25T00:02:00Z"}]"#

private let handledAttentionViewJSON = #"{"event":{"id":"00000000-0000-0000-0000-000000000040","type":"synthetic.old","source":"test","importance":"normal","attention":"notify","payload":{"summary":"Older synthetic attention."},"dedupe_key":"old","created_at":"2026-09-25T00:00:00Z","handled_at":"2026-09-25T00:02:00Z"},"deliveries":[]}"#

private let legacyConfiguredJSON = #"{"supported":true,"configured":true,"definition_state":"recognized_legacy","loaded":true,"running":false,"label":"ai.ally.proactive-service","can_retire":true}"#

private let legacyRetiredJSON = #"{"supported":true,"configured":false,"definition_state":"absent","loaded":false,"running":false,"label":"ai.ally.proactive-service","can_retire":false}"#

private func decode<T: Decodable>(_ type: T.Type, _ json: String) throws -> T {
    let decoder = JSONDecoder()
    decoder.keyDecodingStrategy = .convertFromSnakeCase
    return try decoder.decode(T.self, from: Data(json.utf8))
}

@MainActor
@Test func conversationDeletionClearsOwnedPresentationState() async throws {
    let bridge = FakeBridgeClient(
        replies: [
            "conversation.delete": [.json("true")],
            "bootstrap": [.json(emptyBootstrapJSON)],
        ]
    )
    let model = AppModel(client: bridge)
    model.selectedConversationID = "00000000-0000-0000-0000-000000000001"
    model.conversation = try decode(ConversationView.self, conversationViewJSON)
    model.composer = "stale draft"
    model.conversationSearchResults = try decode(
        [ConversationSearchResult].self,
        conversationSearchJSON
    )

    let deleted = await model.deleteConversation(
        "00000000-0000-0000-0000-000000000001"
    )

    #expect(deleted)
    #expect(model.selectedConversationID == nil)
    #expect(model.conversation == nil)
    #expect(model.composer.isEmpty)
    #expect(model.conversationSearchResults.isEmpty)
    #expect(model.snapshot != nil)
    #expect(model.errorMessage == nil)
    #expect(model.isBusy == false)

    let methods = await bridge.calls().map(\.method)
    #expect(methods == ["conversation.delete", "bootstrap"])
}

@MainActor
@Test func failedConversationDeletionPreservesLivePresentationState() async throws {
    let bridge = FakeBridgeClient(
        replies: [
            "conversation.delete": [
                .failure(
                    .requestFailed(
                        code: "not_found",
                        message: "Synthetic deletion failed."
                    )
                )
            ],
        ]
    )
    let model = AppModel(client: bridge)
    model.selectedConversationID = "00000000-0000-0000-0000-000000000001"
    model.conversation = try decode(ConversationView.self, conversationViewJSON)
    model.composer = "keep draft"
    model.conversationSearchResults = try decode(
        [ConversationSearchResult].self,
        conversationSearchJSON
    )

    let deleted = await model.deleteConversation(
        "00000000-0000-0000-0000-000000000001"
    )

    #expect(deleted == false)
    #expect(model.selectedConversationID != nil)
    #expect(model.conversation != nil)
    #expect(model.composer == "keep draft")
    #expect(model.conversationSearchResults.count == 1)
    #expect(model.errorMessage == "Synthetic deletion failed.")
    #expect(model.isBusy == false)
}

@MainActor
@Test func knowledgeUpdateRefreshesExactSourceAndClearsSearch() async throws {
    let bridge = FakeBridgeClient(
        replies: [
            "knowledge.ingest_text": [.json(knowledgeIngestV2JSON)],
            "knowledge.list": [.json("[\(knowledgeSourceV2JSON)]")],
            "knowledge.get": [
                .json(knowledgeDetailV1JSON),
                .json(knowledgeDetailV2JSON),
            ],
        ]
    )
    let model = AppModel(client: bridge)
    let source = try decode(KnowledgeSourceSummary.self, knowledgeSourceV1JSON)
    await model.selectKnowledgeSource(source.id)
    model.knowledgeSearchResults = try decode(
        [KnowledgeSearchResult].self,
        knowledgeSearchJSON
    )

    let updated = await model.updateKnowledgeSource(
        source,
        text: " Replacement synthetic knowledge. "
    )

    #expect(updated)
    #expect(model.knowledge.count == 1)
    #expect(model.knowledge[0].currentRevision == 2)
    #expect(model.knowledgeDetail?.source.id == source.id)
    #expect(model.knowledgeDetail?.source.currentRevision == 2)
    #expect(model.knowledgeSearchResults.isEmpty)
    #expect(model.errorMessage == nil)

    let calls = await bridge.calls()
    let ingest = try #require(
        calls.first(where: { $0.method == "knowledge.ingest_text" })
    )
    #expect(ingest.params["uri"] == .string(source.uri))
    #expect(ingest.params["title"] == .string(source.title))
    #expect(
        ingest.params["text"]
            == .string("Replacement synthetic knowledge.")
    )
}

@MainActor
@Test func knowledgeDeletionClearsDetailAndSearchThenRefreshesList() async throws {
    let bridge = FakeBridgeClient(
        replies: [
            "knowledge.get": [.json(knowledgeDetailV2JSON)],
            "knowledge.delete": [.json("true")],
            "knowledge.list": [.json("[]")],
        ]
    )
    let model = AppModel(client: bridge)
    await model.selectKnowledgeSource(
        "00000000-0000-0000-0000-000000000020"
    )
    model.knowledgeSearchResults = try decode(
        [KnowledgeSearchResult].self,
        knowledgeSearchJSON
    )
    model.knowledge = [
        try decode(KnowledgeSourceSummary.self, knowledgeSourceV2JSON)
    ]

    let deleted = await model.deleteKnowledgeSource(
        "00000000-0000-0000-0000-000000000020"
    )

    #expect(deleted)
    #expect(model.knowledgeDetail == nil)
    #expect(model.knowledgeSearchResults.isEmpty)
    #expect(model.knowledge.isEmpty)
    #expect(model.errorMessage == nil)
}

@MainActor
@Test func backupFailuresClearStaleSuccessState() async throws {
    let bridge = FakeBridgeClient(
        replies: [
            "data.backup": [
                .failure(
                    .requestFailed(
                        code: "invalid_state",
                        message: "Synthetic backup failure."
                    )
                )
            ],
            "data.validate_backup": [
                .failure(
                    .requestFailed(
                        code: "invalid_state",
                        message: "Synthetic validation failure."
                    )
                )
            ],
        ]
    )
    let model = AppModel(client: bridge)
    let stale = try decode(
        BackupManifestSummary.self,
        backupManifestJSON
    )
    model.portableBackupManifest = stale
    model.portableBackupStatus = "Old success"

    await model.exportPortableBackup(
        to: URL(fileURLWithPath: "/tmp/synthetic.ally-backup")
    )

    #expect(model.portableBackupManifest == nil)
    #expect(model.portableBackupStatus == nil)
    #expect(model.errorMessage == "Synthetic backup failure.")

    model.portableBackupManifest = stale
    model.portableBackupStatus = "Old validation"

    await model.validatePortableBackup(
        at: URL(fileURLWithPath: "/tmp/synthetic.ally-backup")
    )

    #expect(model.portableBackupManifest == nil)
    #expect(model.portableBackupStatus == nil)
    #expect(model.errorMessage == "Synthetic validation failure.")
}

@MainActor
@Test func failedTaskProposalClearsStaleProposal() async throws {
    let bridge = FakeBridgeClient(
        replies: [
            "task.propose": [
                .failure(
                    .requestFailed(
                        code: "inference_unavailable",
                        message: "Synthetic proposal failure."
                    )
                )
            ],
        ]
    )
    let model = AppModel(client: bridge)
    model.taskProposal = try decode(TaskPlanProposal.self, taskProposalJSON)

    await model.proposeTask("New synthetic goal")

    #expect(model.taskProposal == nil)
    #expect(model.errorMessage == "Synthetic proposal failure.")
    #expect(model.isBusy == false)
}

@MainActor
@Test func taskCreationClearsProposalAndRefreshesBootstrap() async throws {
    let bridge = FakeBridgeClient(
        replies: [
            "task.create": [.json(taskViewJSON)],
            "bootstrap": [.json(emptyBootstrapJSON)],
        ]
    )
    let model = AppModel(client: bridge)
    model.taskProposal = try decode(TaskPlanProposal.self, taskProposalJSON)

    let taskID = await model.createProposedTask()

    #expect(taskID == "00000000-0000-0000-0000-000000000030")
    #expect(model.taskProposal == nil)
    #expect(model.taskDetail?.task.id == taskID)
    #expect(model.snapshot != nil)
    #expect(model.errorMessage == nil)
}

@MainActor
@Test func researchFailureClearsStaleAnswerState() async throws {
    let bridge = FakeBridgeClient(
        replies: [
            "research.answer": [
                .failure(
                    .requestFailed(
                        code: "operation_failed",
                        message: "Synthetic research failure."
                    )
                )
            ],
        ]
    )
    let model = AppModel(client: bridge)
    model.researchResults = try decode(
        [WebSearchResult].self,
        researchResultsJSON
    )
    model.researchSynthesis = try decode(
        WebResearchSynthesis.self,
        researchSynthesisJSON
    )
    model.researchSynthesisStatus = "succeeded"
    model.researchStatus = "succeeded"
    model.researchMoreResultsAvailable = true

    await model.runApprovedResearch("synthetic public query")

    #expect(model.researchResults.isEmpty)
    #expect(model.researchSynthesis == nil)
    #expect(model.researchSynthesisStatus == nil)
    #expect(model.researchStatus == nil)
    #expect(model.researchMoreResultsAvailable == false)
    #expect(model.errorMessage == "Synthetic research failure.")
}


@MainActor
@Test func overlappingConversationLoadsKeepBusyAndNewestSelection() async {
    let olderGate = AsyncGate()
    let newerGate = AsyncGate()
    let bridge = FakeBridgeClient(
        replies: [
            "conversation.get": [
                .gatedJSON(conversationViewJSON, olderGate),
                .gatedJSON(newerConversationViewJSON, newerGate),
            ],
        ]
    )
    let model = AppModel(client: bridge)
    let olderID = "00000000-0000-0000-0000-000000000001"
    let newerID = "00000000-0000-0000-0000-000000000003"

    let olderTask = Task { await model.selectConversation(olderID) }
    await waitForCallCount(1, bridge: bridge)
    let newerTask = Task { await model.selectConversation(newerID) }
    await waitForCallCount(2, bridge: bridge)

    #expect(model.isBusy)
    await newerGate.open()
    await newerTask.value
    #expect(model.selectedConversationID == newerID)
    #expect(model.conversation?.conversation.id == newerID)
    #expect(model.isBusy)

    await olderGate.open()
    await olderTask.value
    #expect(model.selectedConversationID == newerID)
    #expect(model.conversation?.conversation.id == newerID)
    #expect(model.isBusy == false)
}

@MainActor
@Test func staleConversationFailureCannotOverwriteNewerSuccess() async {
    let olderGate = AsyncGate()
    let bridge = FakeBridgeClient(
        replies: [
            "conversation.get": [
                .gatedFailure(
                    .requestFailed(
                        code: "synthetic_old_failure",
                        message: "Older request failed."
                    ),
                    olderGate
                ),
                .json(newerConversationViewJSON),
            ],
        ]
    )
    let model = AppModel(client: bridge)

    let olderTask = Task {
        await model.selectConversation(
            "00000000-0000-0000-0000-000000000001"
        )
    }
    await waitForCallCount(1, bridge: bridge)
    await model.selectConversation(
        "00000000-0000-0000-0000-000000000003"
    )
    #expect(model.errorMessage == nil)

    await olderGate.open()
    await olderTask.value
    #expect(
        model.conversation?.conversation.id
            == "00000000-0000-0000-0000-000000000003"
    )
    #expect(model.errorMessage == nil)
}

@MainActor
@Test func staleMemoryDetailCannotOverwriteNewerSelection() async {
    let olderGate = AsyncGate()
    let newerGate = AsyncGate()
    let bridge = FakeBridgeClient(
        replies: [
            "memory.get": [
                .gatedJSON(firstMemoryJSON, olderGate),
                .gatedJSON(secondMemoryJSON, newerGate),
            ],
        ]
    )
    let model = AppModel(client: bridge)

    let olderTask = Task {
        await model.selectMemory(
            "00000000-0000-0000-0000-000000000010"
        )
    }
    await waitForCallCount(1, bridge: bridge)
    let newerTask = Task {
        await model.selectMemory(
            "00000000-0000-0000-0000-000000000011"
        )
    }
    await waitForCallCount(2, bridge: bridge)

    await newerGate.open()
    await newerTask.value
    await olderGate.open()
    await olderTask.value

    #expect(
        model.memoryDetail?.id
            == "00000000-0000-0000-0000-000000000011"
    )
}

@MainActor
@Test func staleKnowledgeDetailCannotOverwriteNewerSelection() async {
    let olderGate = AsyncGate()
    let newerGate = AsyncGate()
    let bridge = FakeBridgeClient(
        replies: [
            "knowledge.get": [
                .gatedJSON(knowledgeDetailV1JSON, olderGate),
                .gatedJSON(secondKnowledgeDetailJSON, newerGate),
            ],
        ]
    )
    let model = AppModel(client: bridge)

    let olderTask = Task {
        await model.selectKnowledgeSource(
            "00000000-0000-0000-0000-000000000020"
        )
    }
    await waitForCallCount(1, bridge: bridge)
    let newerTask = Task {
        await model.selectKnowledgeSource(
            "00000000-0000-0000-0000-000000000024"
        )
    }
    await waitForCallCount(2, bridge: bridge)

    await newerGate.open()
    await newerTask.value
    await olderGate.open()
    await olderTask.value

    #expect(
        model.knowledgeDetail?.source.id
            == "00000000-0000-0000-0000-000000000024"
    )
}

@MainActor
@Test func staleTaskDetailCannotOverwriteNewerSelection() async {
    let olderGate = AsyncGate()
    let newerGate = AsyncGate()
    let bridge = FakeBridgeClient(
        replies: [
            "task.get": [
                .gatedJSON(taskViewJSON, olderGate),
                .gatedJSON(secondTaskViewJSON, newerGate),
            ],
        ]
    )
    let model = AppModel(client: bridge)

    let olderTask = Task {
        await model.selectTask(
            "00000000-0000-0000-0000-000000000030"
        )
    }
    await waitForCallCount(1, bridge: bridge)
    let newerTask = Task {
        await model.selectTask(
            "00000000-0000-0000-0000-000000000032"
        )
    }
    await waitForCallCount(2, bridge: bridge)

    await newerGate.open()
    await newerTask.value
    await olderGate.open()
    await olderTask.value

    #expect(
        model.taskDetail?.task.id
            == "00000000-0000-0000-0000-000000000032"
    )
}

@MainActor
@Test func staleAttentionDetailCannotOverwriteNewerSelection() async {
    let olderGate = AsyncGate()
    let newerGate = AsyncGate()
    let bridge = FakeBridgeClient(
        replies: [
            "attention.get": [
                .gatedJSON(firstAttentionJSON, olderGate),
                .gatedJSON(secondAttentionJSON, newerGate),
            ],
        ]
    )
    let model = AppModel(client: bridge)

    let olderTask = Task {
        await model.selectAttention(
            "00000000-0000-0000-0000-000000000040"
        )
    }
    await waitForCallCount(1, bridge: bridge)
    let newerTask = Task {
        await model.selectAttention(
            "00000000-0000-0000-0000-000000000041"
        )
    }
    await waitForCallCount(2, bridge: bridge)

    await newerGate.open()
    await newerTask.value
    await olderGate.open()
    await olderTask.value

    #expect(
        model.attentionDetail?.event.id
            == "00000000-0000-0000-0000-000000000041"
    )
}

@MainActor
@Test func knowledgeMutationRefreshCannotOverwriteNewerNavigation() async throws {
    let refreshGate = AsyncGate()
    let bridge = FakeBridgeClient(
        replies: [
            "knowledge.get": [
                .json(knowledgeDetailV1JSON),
                .gatedJSON(knowledgeDetailV2JSON, refreshGate),
                .json(secondKnowledgeDetailJSON),
            ],
            "knowledge.ingest_text": [.json(knowledgeIngestV2JSON)],
            "knowledge.list": [.json("[\(knowledgeSourceV2JSON)]")],
        ]
    )
    let model = AppModel(client: bridge)
    let source = try decode(
        KnowledgeSourceSummary.self,
        knowledgeSourceV1JSON
    )
    await model.selectKnowledgeSource(source.id)

    let updateTask = Task {
        await model.updateKnowledgeSource(
            source,
            text: "Replacement synthetic knowledge."
        )
    }
    await waitForMethodCallCount(
        2,
        method: "knowledge.get",
        bridge: bridge
    )

    await model.selectKnowledgeSource(
        "00000000-0000-0000-0000-000000000024"
    )
    #expect(
        model.knowledgeDetail?.source.id
            == "00000000-0000-0000-0000-000000000024"
    )

    await refreshGate.open()
    _ = await updateTask.value
    #expect(
        model.knowledgeDetail?.source.id
            == "00000000-0000-0000-0000-000000000024"
    )
}


@MainActor
@Test func staleConversationSearchCannotOverwriteNewerQuery() async {
    let oldGate = AsyncGate()
    let newGate = AsyncGate()
    let bridge = FakeBridgeClient(
        replies: [
            "conversation.search": [
                .gatedJSON(conversationSearchJSON, oldGate),
                .gatedJSON(newerConversationSearchJSON, newGate),
            ],
        ]
    )
    let model = AppModel(client: bridge)

    let oldTask = Task { await model.searchConversations("old query") }
    await waitForCallCount(1, bridge: bridge)
    let newTask = Task { await model.searchConversations("new query") }
    await waitForCallCount(2, bridge: bridge)

    await newGate.open()
    await newTask.value
    #expect(
        model.conversationSearchResults.first?.conversation.id
            == "00000000-0000-0000-0000-000000000003"
    )

    await oldGate.open()
    await oldTask.value
    #expect(
        model.conversationSearchResults.first?.conversation.id
            == "00000000-0000-0000-0000-000000000003"
    )
}

@MainActor
@Test func clearingConversationSearchInvalidatesInFlightResult() async {
    let gate = AsyncGate()
    let bridge = FakeBridgeClient(
        replies: [
            "conversation.search": [
                .gatedJSON(conversationSearchJSON, gate),
            ],
        ]
    )
    let model = AppModel(client: bridge)

    let task = Task { await model.searchConversations("synthetic query") }
    await waitForCallCount(1, bridge: bridge)
    model.clearConversationSearch()
    #expect(model.conversationSearchResults.isEmpty)

    await gate.open()
    await task.value
    #expect(model.conversationSearchResults.isEmpty)
}

@MainActor
@Test func staleMemorySearchCannotOverwriteNewerQuery() async {
    let oldGate = AsyncGate()
    let newGate = AsyncGate()
    let bridge = FakeBridgeClient(
        replies: [
            "memory.search": [
                .gatedJSON(firstMemorySearchJSON, oldGate),
                .gatedJSON(secondMemorySearchJSON, newGate),
            ],
        ]
    )
    let model = AppModel(client: bridge)

    let oldTask = Task { await model.searchMemories("old memory") }
    await waitForCallCount(1, bridge: bridge)
    let newTask = Task { await model.searchMemories("new memory") }
    await waitForCallCount(2, bridge: bridge)

    await newGate.open()
    await newTask.value
    #expect(
        model.memorySearchResults.first?.id
            == "00000000-0000-0000-0000-000000000011"
    )

    await oldGate.open()
    await oldTask.value
    #expect(
        model.memorySearchResults.first?.id
            == "00000000-0000-0000-0000-000000000011"
    )
}

@MainActor
@Test func staleKnowledgeSearchCannotOverwriteNewerQuery() async {
    let oldGate = AsyncGate()
    let newGate = AsyncGate()
    let bridge = FakeBridgeClient(
        replies: [
            "knowledge.search": [
                .gatedJSON(knowledgeSearchJSON, oldGate),
                .gatedJSON(newerKnowledgeSearchJSON, newGate),
            ],
        ]
    )
    let model = AppModel(client: bridge)

    let oldTask = Task { await model.searchKnowledge("old knowledge") }
    await waitForCallCount(1, bridge: bridge)
    let newTask = Task { await model.searchKnowledge("new knowledge") }
    await waitForCallCount(2, bridge: bridge)

    await newGate.open()
    await newTask.value
    #expect(
        model.knowledgeSearchResults.first?.source.id
            == "00000000-0000-0000-0000-000000000024"
    )

    await oldGate.open()
    await oldTask.value
    #expect(
        model.knowledgeSearchResults.first?.source.id
            == "00000000-0000-0000-0000-000000000024"
    )
}

@MainActor
@Test func instructionMutationInvalidatesInFlightResolution() async {
    let gate = AsyncGate()
    let bridge = FakeBridgeClient(
        replies: [
            "instructions.resolve": [
                .gatedJSON(instructionResolutionJSON, gate),
            ],
            "instructions.set": [
                .json(instructionProfileJSON),
            ],
            "instructions.list": [
                .json(instructionProfileListJSON),
            ],
        ]
    )
    let model = AppModel(client: bridge)

    let resolutionTask = Task {
        await model.resolveInstructions(
            projectKey: "",
            conversationKey: "",
            taskKey: "",
            sessionInstructions: "Synthetic session preview."
        )
    }
    await waitForCallCount(1, bridge: bridge)

    await model.setInstructions(
        scope: "global",
        scopeKey: nil,
        content: "Prefer updated synthetic instructions.",
        enabled: true
    )
    #expect(model.instructionResolution == nil)

    await gate.open()
    await resolutionTask.value
    #expect(model.instructionResolution == nil)
    #expect(model.instructionProfiles.first?.content == "Prefer updated synthetic instructions.")
}

@MainActor
@Test func approvedResearchSupersedesOlderInspection() async {
    let inspectionGate = AsyncGate()
    let bridge = FakeBridgeClient(
        replies: [
            "research.inspect": [
                .gatedJSON(researchInspectionJSON, inspectionGate),
            ],
            "research.answer": [
                .json(researchAnswerJSON),
            ],
        ]
    )
    let model = AppModel(client: bridge)

    let inspectionTask = Task {
        await model.inspectResearch("older synthetic query")
    }
    await waitForCallCount(1, bridge: bridge)

    await model.runApprovedResearch("newer synthetic query")
    #expect(model.researchStatus == "succeeded")
    #expect(model.researchResults.first?.title == "Newer synthetic source")
    #expect(model.researchSynthesis?.answer == "Newer synthetic answer. [1]")

    await inspectionGate.open()
    await inspectionTask.value
    #expect(model.researchStatus == "succeeded")
    #expect(model.researchInspection == nil)
    #expect(model.researchResults.first?.title == "Newer synthetic source")
    #expect(model.researchSynthesis?.answer == "Newer synthetic answer. [1]")
}

@MainActor
@Test func clearingResearchInvalidatesInFlightInspection() async {
    let gate = AsyncGate()
    let bridge = FakeBridgeClient(
        replies: [
            "research.inspect": [
                .gatedJSON(researchInspectionJSON, gate),
            ],
        ]
    )
    let model = AppModel(client: bridge)

    let task = Task { await model.inspectResearch("synthetic query") }
    await waitForCallCount(1, bridge: bridge)
    model.clearResearch()

    await gate.open()
    await task.value
    #expect(model.researchInspection == nil)
    #expect(model.researchResults.isEmpty)
    #expect(model.researchStatus == nil)
}

@MainActor
@Test func staleMemoryProposalCannotOverwriteNewerProposal() async {
    let oldGate = AsyncGate()
    let newGate = AsyncGate()
    let bridge = FakeBridgeClient(
        replies: [
            "memory.propose": [
                .gatedJSON(olderMemoryProposalJSON, oldGate),
                .gatedJSON(newerMemoryProposalJSON, newGate),
            ],
        ]
    )
    let model = AppModel(client: bridge)

    let oldTask = Task {
        await model.proposeMemories(from: "Older synthetic source.")
    }
    await waitForCallCount(1, bridge: bridge)
    let newTask = Task {
        await model.proposeMemories(from: "Newer synthetic source.")
    }
    await waitForCallCount(2, bridge: bridge)

    await newGate.open()
    await newTask.value
    #expect(
        model.memoryProposal?.memories.first?.content
            == "Newer synthetic proposal."
    )

    await oldGate.open()
    await oldTask.value
    #expect(
        model.memoryProposal?.memories.first?.content
            == "Newer synthetic proposal."
    )
}

@MainActor
@Test func clearingMemoryProposalInvalidatesInFlightGeneration() async {
    let gate = AsyncGate()
    let bridge = FakeBridgeClient(
        replies: [
            "memory.propose": [
                .gatedJSON(olderMemoryProposalJSON, gate),
            ],
        ]
    )
    let model = AppModel(client: bridge)

    let task = Task {
        await model.proposeMemories(from: "Synthetic proposal source.")
    }
    await waitForCallCount(1, bridge: bridge)
    model.clearMemoryProposal()

    await gate.open()
    await task.value
    #expect(model.memoryProposal == nil)
}

@MainActor
@Test func staleTaskProposalCannotOverwriteNewerProposal() async {
    let oldGate = AsyncGate()
    let newGate = AsyncGate()
    let bridge = FakeBridgeClient(
        replies: [
            "task.propose": [
                .gatedJSON(taskProposalJSON, oldGate),
                .gatedJSON(newerTaskProposalJSON, newGate),
            ],
        ]
    )
    let model = AppModel(client: bridge)

    let oldTask = Task { await model.proposeTask("Older synthetic goal") }
    await waitForCallCount(1, bridge: bridge)
    let newTask = Task { await model.proposeTask("Newer synthetic goal") }
    await waitForCallCount(2, bridge: bridge)

    await newGate.open()
    await newTask.value
    #expect(model.taskProposal?.goal == "Inspect newer synthetic state")

    await oldGate.open()
    await oldTask.value
    #expect(model.taskProposal?.goal == "Inspect newer synthetic state")
}

@MainActor
@Test func clearingTaskProposalInvalidatesInFlightGeneration() async {
    let gate = AsyncGate()
    let bridge = FakeBridgeClient(
        replies: [
            "task.propose": [
                .gatedJSON(taskProposalJSON, gate),
            ],
        ]
    )
    let model = AppModel(client: bridge)

    let task = Task { await model.proposeTask("Synthetic goal") }
    await waitForCallCount(1, bridge: bridge)
    model.clearTaskProposal()

    await gate.open()
    await task.value
    #expect(model.taskProposal == nil)
}


@MainActor
@Test func oldWholeAppSnapshotCannotOverwriteNewerMutationRefresh() async {
    let oldSnapshotGate = AsyncGate()
    let bridge = FakeBridgeClient(
        replies: [
            "bridge.info": [.json(bridgeInfoJSON)],
            "bootstrap": [
                .gatedJSON(staleBootstrapJSON, oldSnapshotGate),
                .json(emptyBootstrapJSON),
            ],
            "memory.list": [.json("[]")],
            "knowledge.list": [.json("[]")],
            "instructions.list": [.json("[]")],
            "runtime.profiles": [.json(emptyRuntimeCatalogJSON)],
            "service.legacy_status": [.json(legacyRetiredJSON)],
            "conversation.delete": [.json("true")],
        ]
    )
    let model = AppModel(client: bridge)

    let refreshTask = Task { await model.refresh() }
    await waitForMethodCallCount(1, method: "bootstrap", bridge: bridge)

    let deleted = await model.deleteConversation(
        "00000000-0000-0000-0000-000000000001"
    )
    #expect(deleted)
    #expect(model.snapshot?.conversations.items.isEmpty == true)

    await oldSnapshotGate.open()
    await refreshTask.value
    #expect(model.snapshot?.conversations.items.isEmpty == true)
}

@MainActor
@Test func oldWholeAppMemoryListCannotOverwriteNewerMutationList() async {
    let oldMemoryGate = AsyncGate()
    let bridge = FakeBridgeClient(
        replies: [
            "bridge.info": [.json(bridgeInfoJSON)],
            "bootstrap": [.json(emptyBootstrapJSON)],
            "memory.list": [
                .gatedJSON("[\(firstMemoryJSON)]", oldMemoryGate),
                .json("[\(secondMemoryJSON)]"),
            ],
            "knowledge.list": [.json("[]")],
            "instructions.list": [.json("[]")],
            "runtime.profiles": [.json(emptyRuntimeCatalogJSON)],
            "service.legacy_status": [.json(legacyRetiredJSON)],
            "memory.remember": [.json(secondMemoryJSON)],
        ]
    )
    let model = AppModel(client: bridge)

    let refreshTask = Task { await model.refresh() }
    await waitForMethodCallCount(1, method: "memory.list", bridge: bridge)

    let remembered = await model.rememberMemory(
        content: "Newer synthetic memory.",
        kind: "semantic",
        confidence: 1.0,
        importance: 0.5,
        privacy: "private"
    )
    #expect(remembered)
    #expect(
        model.memories.first?.id
            == "00000000-0000-0000-0000-000000000011"
    )

    await oldMemoryGate.open()
    await refreshTask.value
    #expect(
        model.memories.first?.id
            == "00000000-0000-0000-0000-000000000011"
    )
}

@MainActor
@Test func oldKnowledgeListCannotOverwriteNewerIngestRefresh() async {
    let oldKnowledgeGate = AsyncGate()
    let bridge = FakeBridgeClient(
        replies: [
            "bridge.info": [.json(bridgeInfoJSON)],
            "bootstrap": [.json(emptyBootstrapJSON)],
            "memory.list": [.json("[]")],
            "knowledge.list": [
                .gatedJSON("[\(knowledgeSourceV1JSON)]", oldKnowledgeGate),
                .json("[\(knowledgeSourceV2JSON)]"),
            ],
            "instructions.list": [.json("[]")],
            "runtime.profiles": [.json(emptyRuntimeCatalogJSON)],
            "service.legacy_status": [.json(legacyRetiredJSON)],
            "knowledge.ingest_text": [.json(knowledgeIngestV2JSON)],
            "knowledge.get": [.json(knowledgeDetailV2JSON)],
        ]
    )
    let model = AppModel(client: bridge)

    let refreshTask = Task { await model.refresh() }
    await waitForMethodCallCount(1, method: "knowledge.list", bridge: bridge)

    await model.ingestKnowledge(
        title: "Synthetic notes.txt",
        text: "Newer synthetic knowledge."
    )
    #expect(model.knowledge.first?.currentRevision == 2)

    await oldKnowledgeGate.open()
    await refreshTask.value
    #expect(model.knowledge.first?.currentRevision == 2)
}

@MainActor
@Test func oldInstructionListCannotOverwriteNewerMutationRefresh() async {
    let oldInstructionGate = AsyncGate()
    let bridge = FakeBridgeClient(
        replies: [
            "instructions.list": [
                .gatedJSON(oldInstructionProfileListJSON, oldInstructionGate),
                .json(instructionProfileListJSON),
            ],
            "instructions.set": [.json(instructionProfileJSON)],
        ]
    )
    let model = AppModel(client: bridge)

    let refreshTask = Task { await model.refreshInstructions() }
    await waitForMethodCallCount(1, method: "instructions.list", bridge: bridge)

    await model.setInstructions(
        scope: "global",
        scopeKey: nil,
        content: "Prefer updated synthetic instructions.",
        enabled: true
    )
    #expect(
        model.instructionProfiles.first?.content
            == "Prefer updated synthetic instructions."
    )

    await oldInstructionGate.open()
    await refreshTask.value
    #expect(
        model.instructionProfiles.first?.content
            == "Prefer updated synthetic instructions."
    )
}

@MainActor
@Test func oldRuntimeCatalogCannotOverwriteNewerSelection() async {
    let oldRuntimeGate = AsyncGate()
    let bridge = FakeBridgeClient(
        replies: [
            "bridge.info": [.json(bridgeInfoJSON)],
            "bootstrap": [
                .json(emptyBootstrapJSON),
                .json(emptyBootstrapJSON),
            ],
            "memory.list": [.json("[]")],
            "knowledge.list": [.json("[]")],
            "instructions.list": [.json("[]")],
            "runtime.profiles": [
                .gatedJSON(emptyRuntimeCatalogJSON, oldRuntimeGate),
            ],
            "runtime.select_profile": [
                .json(selectedRuntimeCatalogJSON),
            ],
            "service.legacy_status": [.json(legacyRetiredJSON)],
        ]
    )
    let model = AppModel(client: bridge)

    let refreshTask = Task { await model.refresh() }
    await waitForMethodCallCount(1, method: "runtime.profiles", bridge: bridge)

    await model.selectRuntimeProfile(
        "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
    )
    #expect(
        model.runtimeProfiles?.activeProfileId
            == "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
    )

    await oldRuntimeGate.open()
    await refreshTask.value
    #expect(
        model.runtimeProfiles?.activeProfileId
            == "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
    )
}

@MainActor
@Test func oldAttentionRefreshCannotOverwriteNewerHandledList() async {
    let oldEventsGate = AsyncGate()
    let bridge = FakeBridgeClient(
        replies: [
            "attention.events": [
                .gatedJSON(oldAttentionEventListJSON, oldEventsGate),
                .json(handledAttentionEventListJSON),
            ],
            "attention.delivery_history": [.json("[]")],
            "attention.mark_handled": [.json(handledAttentionViewJSON)],
            "bootstrap": [.json(emptyBootstrapJSON)],
        ]
    )
    let model = AppModel(client: bridge)

    let refreshTask = Task { await model.refreshAttention() }
    await waitForMethodCallCount(1, method: "attention.events", bridge: bridge)

    await model.markAttentionHandled(
        "00000000-0000-0000-0000-000000000040"
    )
    #expect(model.attentionEvents.first?.handledAt != nil)

    await oldEventsGate.open()
    await refreshTask.value
    #expect(model.attentionEvents.first?.handledAt != nil)
}

@MainActor
@Test func oldLegacyStatusCannotOverwriteNewerRetirement() async {
    let oldStatusGate = AsyncGate()
    let bridge = FakeBridgeClient(
        replies: [
            "service.legacy_status": [
                .gatedJSON(legacyConfiguredJSON, oldStatusGate),
            ],
            "service.retire_legacy": [
                .json(legacyRetiredJSON),
            ],
        ]
    )
    let model = AppModel(client: bridge)

    let statusTask = Task {
        await model.refreshLegacyManagedServiceStatus()
    }
    await waitForMethodCallCount(
        1,
        method: "service.legacy_status",
        bridge: bridge
    )

    await model.retireLegacyManagedService()
    #expect(model.legacyManagedService?.configured == false)

    await oldStatusGate.open()
    await statusTask.value
    #expect(model.legacyManagedService?.configured == false)
}
