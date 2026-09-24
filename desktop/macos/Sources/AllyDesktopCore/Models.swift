import Foundation

public struct RuntimeTarget: Decodable, Sendable, Equatable {
    public let source: String
    public let endpoint: String
    public let model: String
    public let profileId: String?
    public let runtimeName: String?
    public let runtimeVersion: String?
}

public struct RuntimeStatus: Decodable, Sendable, Equatable {
    public let state: String
    public let target: RuntimeTarget?
    public let errorCode: String?
}

public struct ConversationSummary: Decodable, Sendable, Equatable, Identifiable {
    public let id: String
    public let title: String?
    public let createdAt: String
    public let updatedAt: String
}

public struct ConversationMessage: Decodable, Sendable, Equatable, Identifiable {
    public let id: String
    public let conversationId: String
    public let position: Int
    public let role: String
    public let content: String
    public let createdAt: String
}

public struct ConversationView: Decodable, Sendable, Equatable {
    public let conversation: ConversationSummary
    public let messages: [ConversationMessage]
}

public struct ChatResponse: Decodable, Sendable, Equatable {
    public let content: String
    public let model: String
    public let provider: String
}

public struct ChatTurnResult: Decodable, Sendable, Equatable {
    public let conversation: ConversationSummary
    public let response: ChatResponse
    public let target: RuntimeTarget
}

public struct TaskSummary: Decodable, Sendable, Equatable, Identifiable {
    public let id: String
    public let goal: String
    public let status: String
    public let failure: String?
    public let createdAt: String
    public let updatedAt: String
}

public struct EventSummary: Decodable, Sendable, Equatable, Identifiable {
    public let id: String
    public let type: String
    public let source: String
    public let importance: String
    public let attention: String
    public let createdAt: String
    public let handledAt: String?
}

public struct AttentionDeliverySummary: Decodable, Sendable, Equatable, Identifiable {
    public let id: String
    public let eventId: String
    public let sinkId: String
    public let status: String
    public let attempts: Int
    public let lastError: String?
    public let createdAt: String
    public let updatedAt: String
    public let deliveredAt: String?
}

public struct ServiceCycleSummary: Decodable, Sendable, Equatable, Identifiable {
    public let id: String
    public let status: String
    public let observedAt: String
    public let startedAt: String
    public let finishedAt: String?
    public let scheduledEvents: Int
    public let deliveryAttempts: Int
    public let deliveryFailures: Int
    public let errorClass: String?
}

public struct ServiceHealthCheck: Decodable, Sendable, Equatable, Identifiable {
    public let id: String
    public let severity: String
    public let summary: String
}

public struct ServiceHealthReport: Decodable, Sendable, Equatable {
    public let status: String
    public let checks: [ServiceHealthCheck]
}

public struct ItemSection<Item: Decodable & Sendable & Equatable>: Decodable, Sendable, Equatable {
    public let state: String
    public let items: [Item]
    public let errorCode: String?
}

public struct ServiceHealthSection: Decodable, Sendable, Equatable {
    public let state: String
    public let report: ServiceHealthReport?
    public let errorCode: String?
}

public struct BootstrapSnapshot: Decodable, Sendable, Equatable {
    public let runtime: RuntimeStatus
    public let conversations: ItemSection<ConversationSummary>
    public let tasks: ItemSection<TaskSummary>
    public let pendingAttention: ItemSection<EventSummary>
    public let attentionHistory: ItemSection<AttentionDeliverySummary>
    public let serviceHistory: ItemSection<ServiceCycleSummary>
    public let serviceHealth: ServiceHealthSection
}

public struct MemorySummary: Decodable, Sendable, Equatable, Identifiable {
    public let id: String
    public let kind: String
    public let content: String
    public let confidence: Double
    public let importance: Double
    public let privacy: String
    public let createdAt: String
    public let updatedAt: String
    public let retractedAt: String?
    public let supersededBy: String?
}

public struct KnowledgeSourceSummary: Decodable, Sendable, Equatable, Identifiable {
    public let id: String
    public let uri: String
    public let title: String
    public let mediaType: String
    public let currentRevision: Int
    public let createdAt: String
    public let updatedAt: String
}
