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

public struct TaskStepSummary: Decodable, Sendable, Equatable, Identifiable {
    public let id: String
    public let taskId: String
    public let position: Int
    public let toolName: String
    public let arguments: [String: JSONValue]
    public let status: String
    public let attempts: Int
    public let lastOutput: JSONValue?
    public let lastError: String?
    public let createdAt: String
    public let updatedAt: String

    public var argumentsText: String {
        if arguments.isEmpty {
            return "No arguments"
        }
        return arguments.keys.sorted().map { key in
            "\(key): \(arguments[key]?.displayText ?? "null")"
        }.joined(separator: "\n")
    }
}

public struct TaskView: Decodable, Sendable, Equatable {
    public let task: TaskSummary
    public let steps: [TaskStepSummary]
}

public struct EventSummary: Decodable, Sendable, Equatable, Identifiable {
    public let id: String
    public let type: String
    public let source: String
    public let importance: String
    public let attention: String
    public let payload: [String: JSONValue]
    public let dedupeKey: String?
    public let createdAt: String
    public let handledAt: String?

    public var displayText: String {
        for key in ["summary", "message"] {
            if case let .string(value)? = payload[key], !value.isEmpty {
                return value
            }
        }
        return type
    }
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

public struct AttentionEventView: Decodable, Sendable, Equatable {
    public let event: EventSummary
    public let deliveries: [AttentionDeliverySummary]
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

public struct MemorySourceSummary: Decodable, Sendable, Equatable {
    public let type: String
    public let id: String?
    public let uri: String?
}

public struct MemorySummary: Decodable, Sendable, Equatable, Identifiable {
    public let id: String
    public let kind: String
    public let content: String
    public let source: MemorySourceSummary
    public let confidence: Double
    public let importance: Double
    public let privacy: String
    public let createdAt: String
    public let updatedAt: String
    public let observedAt: String?
    public let validFrom: String?
    public let validUntil: String?
    public let supersedes: String?
    public let supersededAt: String?
    public let supersededBy: String?
    public let retractedAt: String?

    public var isActive: Bool {
        supersededAt == nil && retractedAt == nil
    }
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


public struct KnowledgeRevisionSummary: Decodable, Sendable, Equatable, Identifiable {
    public let id: String
    public let sourceId: String
    public let revision: Int
    public let sha256: String
    public let createdAt: String
}

public struct KnowledgeChunkSummary: Decodable, Sendable, Equatable, Identifiable {
    public let id: String
    public let sourceId: String
    public let revisionId: String
    public let revision: Int
    public let ordinal: Int
    public let content: String
    public let startChar: Int
    public let endChar: Int
    public let sha256: String
    public let createdAt: String
}

public struct KnowledgeSourceView: Decodable, Sendable, Equatable {
    public let source: KnowledgeSourceSummary
    public let revisions: [KnowledgeRevisionSummary]
    public let currentChunks: [KnowledgeChunkSummary]
}

public struct KnowledgeSearchResult: Decodable, Sendable, Equatable, Identifiable {
    public let source: KnowledgeSourceSummary
    public let chunk: KnowledgeChunkSummary
    public let score: Double

    public var id: String {
        chunk.id
    }
}

public struct KnowledgeIngestResult: Decodable, Sendable, Equatable {
    public let source: KnowledgeSourceSummary
    public let revision: KnowledgeRevisionSummary
}


public struct EgressFieldManifest: Decodable, Sendable, Equatable, Identifiable {
    public let name: String
    public let classification: String

    public var id: String {
        name
    }
}

public struct EgressInspection: Decodable, Sendable, Equatable {
    public let requestId: String
    public let service: String
    public let operation: String
    public let decision: String
    public let fields: [EgressFieldManifest]
    public let errorClass: String?
}

public struct WebSearchResult: Decodable, Sendable, Equatable, Identifiable {
    public let title: String
    public let url: String
    public let description: String

    public var id: String {
        url
    }
}

public struct WebResearchExecution: Decodable, Sendable, Equatable {
    public let requestId: String
    public let service: String
    public let operation: String
    public let decision: String
    public let status: String
    public let results: [WebSearchResult]
    public let moreResultsAvailable: Bool
    public let errorClass: String?
}


public struct RuntimeProfileSummary: Decodable, Sendable, Equatable, Identifiable {
    public let profileId: String
    public let generatedAt: String
    public let allyVersion: String
    public let model: String
    public let runtimeName: String
    public let runtimeVersion: String
    public let modelSource: String?
    public let quantization: String?
    public let precision: String?
    public let modelSizeBytes: Int?
    public let contextLength: Int?
    public let appleModel: String?
    public let appleChip: String?
    public let totalMemoryBytes: Int?
    public let timeToFirstTokenMs: Double?
    public let generationTokensPerSecond: Double?
    public let maximumTestedContextTokens: Int?
    public let capabilityEvidenceName: String
    public let capabilityEvidenceSha256: String
    public let privacyEvidenceName: String
    public let privacyEvidenceSha256: String
    public let workflowEvidenceName: String
    public let workflowEvidenceSha256: String
    public let active: Bool

    public var id: String {
        profileId
    }
}

public struct RuntimeProfileCatalogView: Decodable, Sendable, Equatable {
    public let items: [RuntimeProfileSummary]
    public let activeProfileId: String?
}


public struct DesktopNotificationCandidate: Decodable, Sendable, Equatable, Identifiable {
    public let eventId: String
    public let deliveryKey: String
    public let title: String
    public let body: String
    public let attention: String
    public let createdAt: String

    public var id: String { eventId }
}

public struct DesktopProactivePreparation: Decodable, Sendable, Equatable {
    public let run: ServiceCycleSummary
    public let candidates: [DesktopNotificationCandidate]
}

public struct LegacyManagedServiceView: Decodable, Sendable, Equatable {
    public let supported: Bool
    public let configured: Bool
    public let definitionState: String
    public let loaded: Bool
    public let running: Bool
    public let label: String
    public let canRetire: Bool
}
