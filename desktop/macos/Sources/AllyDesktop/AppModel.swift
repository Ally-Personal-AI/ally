#if os(macOS)
import Foundation
import SwiftUI
import AllyDesktopCore

@MainActor
final class AppModel: ObservableObject {
    @Published var snapshot: BootstrapSnapshot?
    @Published var runtimeProfiles: RuntimeProfileCatalogView?
    @Published var memories: [MemorySummary] = []
    @Published var memoryDetail: MemorySummary?
    @Published var memorySearchResults: [MemorySummary] = []
    @Published var knowledge: [KnowledgeSourceSummary] = []
    @Published var knowledgeDetail: KnowledgeSourceView?
    @Published var knowledgeSearchResults: [KnowledgeSearchResult] = []
    @Published var selectedConversationID: String?
    @Published var conversation: ConversationView?
    @Published var taskDetail: TaskView?
    @Published var attentionEvents: [EventSummary] = []
    @Published var attentionDetail: AttentionEventView?
    @Published var attentionDeliveryHistory: [AttentionDeliverySummary] = []
    @Published var notificationAuthorization: DesktopNotificationAuthorizationState = .unknown
    @Published var composer = ""
    @Published var isBusy = false
    @Published var errorMessage: String?

    private let client: DesktopBridgeClient?
    private let notificationAuthorizationClient = DesktopNotificationAuthorizationClient()

    init() {
        do {
            self.client = try DesktopBridgeClient()
        } catch {
            self.client = nil
            self.errorMessage = error.localizedDescription
        }
    }

    func refresh() async {
        guard let client else { return }
        isBusy = true
        defer { isBusy = false }
        do {
            let info: BridgeInfo = try await client.call("bridge.info")
            guard info.protocolVersion == DesktopBridgeClient.supportedProtocolVersion else {
                throw DesktopBridgeError.invalidResponse
            }
            async let snapshot: BootstrapSnapshot = client.call("bootstrap")
            async let memories: [MemorySummary] = client.call(
                "memory.list",
                params: ["limit": .number(100)]
            )
            async let knowledge: [KnowledgeSourceSummary] = client.call(
                "knowledge.list",
                params: ["limit": .number(100)]
            )
            self.snapshot = try await snapshot
            self.memories = try await memories
            self.knowledge = try await knowledge
            do {
                self.runtimeProfiles = try await client.call("runtime.profiles")
                self.errorMessage = nil
            } catch {
                self.runtimeProfiles = nil
                self.errorMessage = error.localizedDescription
            }
        } catch {
            self.errorMessage = error.localizedDescription
        }
    }

    func selectRuntimeProfile(_ profileID: String) async {
        guard let client else { return }
        isBusy = true
        defer { isBusy = false }
        do {
            let updated: RuntimeProfileCatalogView = try await client.call(
                "runtime.select_profile",
                params: ["profile_id": .string(profileID)]
            )
            runtimeProfiles = updated
            snapshot = try await client.call("bootstrap")
            errorMessage = nil
        } catch {
            errorMessage = error.localizedDescription
        }
    }

    func deselectRuntimeProfile() async {
        guard let client else { return }
        isBusy = true
        defer { isBusy = false }
        do {
            let updated: RuntimeProfileCatalogView = try await client.call(
                "runtime.deselect_profile"
            )
            runtimeProfiles = updated
            snapshot = try await client.call("bootstrap")
            errorMessage = nil
        } catch {
            errorMessage = error.localizedDescription
        }
    }

    func selectConversation(_ id: String) async {
        guard let client else { return }
        selectedConversationID = id
        isBusy = true
        defer { isBusy = false }
        do {
            conversation = try await client.call(
                "conversation.get",
                params: ["conversation_id": .string(id)]
            )
            errorMessage = nil
        } catch {
            errorMessage = error.localizedDescription
        }
    }

    func createConversation() async {
        guard let client else { return }
        isBusy = true
        defer { isBusy = false }
        do {
            let created: ConversationSummary = try await client.call("conversation.create")
            selectedConversationID = created.id
            conversation = try await client.call(
                "conversation.get",
                params: ["conversation_id": .string(created.id)]
            )
            let refreshed: BootstrapSnapshot = try await client.call("bootstrap")
            snapshot = refreshed
            errorMessage = nil
        } catch {
            errorMessage = error.localizedDescription
        }
    }

    func selectMemory(_ id: String) async {
        guard let client else { return }
        isBusy = true
        defer { isBusy = false }
        do {
            memoryDetail = try await client.call(
                "memory.get",
                params: ["memory_id": .string(id)]
            )
            errorMessage = nil
        } catch {
            errorMessage = error.localizedDescription
        }
    }

    func searchMemories(_ query: String) async {
        guard let client else { return }
        let compact = query.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !compact.isEmpty else {
            memorySearchResults = []
            return
        }
        isBusy = true
        defer { isBusy = false }
        do {
            memorySearchResults = try await client.call(
                "memory.search",
                params: [
                    "query": .string(compact),
                    "limit": .number(100),
                ]
            )
            errorMessage = nil
        } catch {
            errorMessage = error.localizedDescription
        }
    }

    func correctMemory(memoryID: String, content: String) async {
        guard let client else { return }
        let compact = content.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !compact.isEmpty else { return }
        isBusy = true
        defer { isBusy = false }
        do {
            let _: MemorySummary = try await client.call(
                "memory.supersede",
                params: [
                    "memory_id": .string(memoryID),
                    "content": .string(compact),
                ]
            )
            async let refreshedMemories: [MemorySummary] = client.call(
                "memory.list",
                params: ["limit": .number(100)]
            )
            async let original: MemorySummary = client.call(
                "memory.get",
                params: ["memory_id": .string(memoryID)]
            )
            memories = try await refreshedMemories
            memoryDetail = try await original
            memorySearchResults = []
            errorMessage = nil
        } catch {
            errorMessage = error.localizedDescription
        }
    }

    func retractMemory(_ memoryID: String) async {
        guard let client else { return }
        isBusy = true
        defer { isBusy = false }
        do {
            let updated: MemorySummary = try await client.call(
                "memory.retract",
                params: ["memory_id": .string(memoryID)]
            )
            memoryDetail = updated
            memories = try await client.call(
                "memory.list",
                params: ["limit": .number(100)]
            )
            memorySearchResults = []
            errorMessage = nil
        } catch {
            errorMessage = error.localizedDescription
        }
    }

    func selectKnowledgeSource(_ id: String) async {
        guard let client else { return }
        isBusy = true
        defer { isBusy = false }
        do {
            knowledgeDetail = try await client.call(
                "knowledge.get",
                params: ["source_id": .string(id)]
            )
            errorMessage = nil
        } catch {
            errorMessage = error.localizedDescription
        }
    }

    func searchKnowledge(_ query: String) async {
        guard let client else { return }
        let compact = query.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !compact.isEmpty else {
            knowledgeSearchResults = []
            return
        }
        isBusy = true
        defer { isBusy = false }
        do {
            knowledgeSearchResults = try await client.call(
                "knowledge.search",
                params: [
                    "query": .string(compact),
                    "limit": .number(50),
                ]
            )
            errorMessage = nil
        } catch {
            errorMessage = error.localizedDescription
        }
    }

    func ingestKnowledge(title: String, text: String) async {
        guard let client else { return }
        let compactTitle = title.trimmingCharacters(in: .whitespacesAndNewlines)
        let compactText = text.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !compactTitle.isEmpty, !compactText.isEmpty else { return }
        isBusy = true
        defer { isBusy = false }
        do {
            let uri = "ally-desktop://note/\(UUID().uuidString.lowercased())"
            let result: KnowledgeIngestResult = try await client.call(
                "knowledge.ingest_text",
                params: [
                    "uri": .string(uri),
                    "title": .string(compactTitle),
                    "text": .string(compactText),
                    "media_type": .string("text/plain"),
                ]
            )
            async let refreshedKnowledge: [KnowledgeSourceSummary] = client.call(
                "knowledge.list",
                params: ["limit": .number(100)]
            )
            async let detail: KnowledgeSourceView = client.call(
                "knowledge.get",
                params: ["source_id": .string(result.source.id)]
            )
            knowledge = try await refreshedKnowledge
            knowledgeDetail = try await detail
            knowledgeSearchResults = []
            errorMessage = nil
        } catch {
            errorMessage = error.localizedDescription
        }
    }

    func refreshAttention() async {
        guard let client else { return }
        isBusy = true
        defer { isBusy = false }
        do {
            async let events: [EventSummary] = client.call(
                "attention.events",
                params: ["limit": .number(100)]
            )
            async let history: [AttentionDeliverySummary] = client.call(
                "attention.delivery_history",
                params: ["limit": .number(100)]
            )
            attentionEvents = try await events
            attentionDeliveryHistory = try await history
            errorMessage = nil
        } catch {
            errorMessage = error.localizedDescription
        }
    }

    func selectAttention(_ id: String) async {
        guard let client else { return }
        isBusy = true
        defer { isBusy = false }
        do {
            attentionDetail = try await client.call(
                "attention.get",
                params: ["event_id": .string(id)]
            )
            errorMessage = nil
        } catch {
            errorMessage = error.localizedDescription
        }
    }

    func markAttentionHandled(_ id: String) async {
        guard let client else { return }
        isBusy = true
        defer { isBusy = false }
        do {
            let updated: AttentionEventView = try await client.call(
                "attention.mark_handled",
                params: ["event_id": .string(id)]
            )
            attentionDetail = updated
            async let events: [EventSummary] = client.call(
                "attention.events",
                params: ["limit": .number(100)]
            )
            async let snapshot: BootstrapSnapshot = client.call("bootstrap")
            attentionEvents = try await events
            self.snapshot = try await snapshot
            errorMessage = nil
        } catch {
            errorMessage = error.localizedDescription
        }
    }

    func refreshNotificationAuthorization() async {
        notificationAuthorization = await notificationAuthorizationClient.currentState()
    }

    func requestNotificationAuthorization() async {
        isBusy = true
        defer { isBusy = false }
        do {
            notificationAuthorization = try await notificationAuthorizationClient.requestAuthorization()
            errorMessage = nil
        } catch {
            errorMessage = "Notification authorization request failed."
        }
    }

    func selectTask(_ id: String) async {
        guard let client else { return }
        isBusy = true
        defer { isBusy = false }
        do {
            taskDetail = try await client.call(
                "task.get",
                params: ["task_id": .string(id)]
            )
            errorMessage = nil
        } catch {
            errorMessage = error.localizedDescription
        }
    }

    func runTask(_ id: String) async {
        guard let client else { return }
        isBusy = true
        defer { isBusy = false }
        do {
            let updated: TaskView = try await client.call(
                "task.run",
                params: ["task_id": .string(id)]
            )
            taskDetail = updated
            snapshot = try await client.call("bootstrap")
            errorMessage = nil
        } catch {
            errorMessage = error.localizedDescription
        }
    }

    func approveTaskStep(taskID: String, stepID: String) async {
        guard let client else { return }
        isBusy = true
        defer { isBusy = false }
        do {
            let updated: TaskView = try await client.call(
                "task.approve_step",
                params: [
                    "task_id": .string(taskID),
                    "step_id": .string(stepID),
                ]
            )
            taskDetail = updated
            snapshot = try await client.call("bootstrap")
            errorMessage = nil
        } catch {
            let message = error.localizedDescription
            await selectTask(taskID)
            errorMessage = message
        }
    }

    func retryTaskStep(taskID: String, stepID: String) async {
        guard let client else { return }
        isBusy = true
        defer { isBusy = false }
        do {
            let updated: TaskView = try await client.call(
                "task.retry_step",
                params: [
                    "task_id": .string(taskID),
                    "step_id": .string(stepID),
                ]
            )
            taskDetail = updated
            snapshot = try await client.call("bootstrap")
            errorMessage = nil
        } catch {
            let message = error.localizedDescription
            await selectTask(taskID)
            errorMessage = message
        }
    }

    func sendMessage() async {
        guard let client, let id = selectedConversationID else { return }
        let text = composer.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !text.isEmpty else { return }
        composer = ""
        isBusy = true
        defer { isBusy = false }
        do {
            let _: ChatTurnResult = try await client.call(
                "conversation.send",
                params: [
                    "conversation_id": .string(id),
                    "message": .string(text),
                ]
            )
            conversation = try await client.call(
                "conversation.get",
                params: ["conversation_id": .string(id)]
            )
            snapshot = try await client.call("bootstrap")
            errorMessage = nil
        } catch {
            errorMessage = error.localizedDescription
        }
    }
}
#endif
