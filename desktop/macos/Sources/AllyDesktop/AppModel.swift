#if os(macOS)
import Foundation
import SwiftUI
import AllyDesktopCore

@MainActor
final class AppModel: ObservableObject {
    @Published var snapshot: BootstrapSnapshot?
    @Published var memories: [MemorySummary] = []
    @Published var knowledge: [KnowledgeSourceSummary] = []
    @Published var selectedConversationID: String?
    @Published var conversation: ConversationView?
    @Published var composer = ""
    @Published var isBusy = false
    @Published var errorMessage: String?

    private let client: DesktopBridgeClient?

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
            self.errorMessage = nil
        } catch {
            self.errorMessage = error.localizedDescription
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
