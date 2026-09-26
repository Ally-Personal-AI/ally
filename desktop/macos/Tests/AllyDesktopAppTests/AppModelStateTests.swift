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
