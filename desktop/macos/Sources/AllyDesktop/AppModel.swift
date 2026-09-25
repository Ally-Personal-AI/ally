#if os(macOS)
import Foundation
import SwiftUI
import AllyDesktopCore

@MainActor
final class AppModel: ObservableObject {
    @Published var snapshot: BootstrapSnapshot?
    @Published var runtimeProfiles: RuntimeProfileCatalogView?
    @Published var portableBackupManifest: BackupManifestSummary?
    @Published var portableBackupStatus: String?
    @Published var memories: [MemorySummary] = []
    @Published var memoryDetail: MemorySummary?
    @Published var memorySearchResults: [MemorySummary] = []
    @Published var memoryProposal: MemoryProposalBundleSummary?
    @Published var knowledge: [KnowledgeSourceSummary] = []
    @Published var knowledgeDetail: KnowledgeSourceView?
    @Published var knowledgeSearchResults: [KnowledgeSearchResult] = []
    @Published var instructionProfiles: [UserInstructionsSummary] = []
    @Published var instructionResolution: InstructionResolutionView?
    @Published var researchInspection: EgressInspection?
    @Published var researchResults: [WebSearchResult] = []
    @Published var researchSynthesis: WebResearchSynthesis?
    @Published var researchSynthesisStatus: String?
    @Published var researchStatus: String?
    @Published var researchMoreResultsAvailable = false
    @Published var selectedConversationID: String?
    @Published var conversation: ConversationView?
    @Published var conversationSearchResults: [ConversationSearchResult] = []
    @Published var taskDetail: TaskView?
    @Published var taskProposal: TaskPlanProposal?
    @Published var attentionEvents: [EventSummary] = []
    @Published var attentionDetail: AttentionEventView?
    @Published var attentionDeliveryHistory: [AttentionDeliverySummary] = []
    @Published var notificationAuthorization: DesktopNotificationAuthorizationState = .unknown
    @Published var backgroundServiceState: DesktopBackgroundServiceState = .unknown
    @Published var legacyManagedService: LegacyManagedServiceView?
    @Published var lastProactiveCycleAt: Date?
    @Published var proactiveCycleError: String?
    @Published var composer = ""
    @Published var isBusy = false
    @Published var errorMessage: String?

    private let client: (any DesktopBridgeCalling)?
    private let notificationAuthorizationClient = DesktopNotificationAuthorizationClient()
    private let backgroundServiceClient = DesktopBackgroundServiceClient()
    private var proactiveLoopTask: Task<Void, Never>?
    private var proactiveCycleRunning = false
    private var activeBusyOperations = 0
    private var conversationSelectionToken: UUID?
    private var memorySelectionToken: UUID?
    private var knowledgeSelectionToken: UUID?
    private var taskSelectionToken: UUID?
    private var attentionSelectionToken: UUID?
    private var selectedMemoryID: String?
    private var selectedKnowledgeSourceID: String?
    private var selectedTaskID: String?
    private var selectedAttentionID: String?

    init() {
        do {
            self.client = try DesktopBridgeClient()
        } catch {
            self.client = nil
            self.errorMessage = error.localizedDescription
        }
        beginProactiveLoop()
    }

    init(
        client: any DesktopBridgeCalling,
        startProactiveLoop: Bool = false
    ) {
        self.client = client
        if startProactiveLoop {
            beginProactiveLoop()
        }
    }

    private func beginBusy() {
        activeBusyOperations += 1
        beginBusy()
    }

    private func endBusy() {
        activeBusyOperations = max(0, activeBusyOperations - 1)
        isBusy = activeBusyOperations > 0
    }

    private func beginProactiveLoop() {
        proactiveLoopTask = Task { [weak self] in
            while !Task.isCancelled {
                guard self != nil else { return }
                if let model = self {
                    await model.runProactiveCycleIfEnabled()
                }
                do {
                    try await Task.sleep(for: .seconds(60))
                } catch {
                    return
                }
            }
        }
    }

    func refresh() async {
        guard let client else { return }
        beginBusy()
        defer { endBusy() }
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
            async let instructions: [UserInstructionsSummary] = client.call(
                "instructions.list",
                params: ["include_disabled": .bool(true)]
            )
            self.snapshot = try await snapshot
            self.memories = try await memories
            self.knowledge = try await knowledge
            self.instructionProfiles = try await instructions
            do {
                self.runtimeProfiles = try await client.call("runtime.profiles")
                self.errorMessage = nil
            } catch {
                self.runtimeProfiles = nil
                self.errorMessage = error.localizedDescription
            }
            do {
                self.legacyManagedService = try await client.call("service.legacy_status")
            } catch {
                self.legacyManagedService = nil
            }
        } catch {
            self.errorMessage = error.localizedDescription
        }
    }

    func exportPortableBackup(to url: URL) async {
        guard let client else { return }
        portableBackupManifest = nil
        portableBackupStatus = nil
        guard let path = portableBackupPath(url) else {
            errorMessage = "Portable backups require an absolute .ally-backup file path."
            return
        }
        beginBusy()
        defer { endBusy() }
        do {
            portableBackupManifest = try await client.call(
                "data.backup",
                params: ["path": .string(path)]
            )
            portableBackupStatus = "Backup created"
            errorMessage = nil
        } catch {
            errorMessage = error.localizedDescription
        }
    }

    func validatePortableBackup(at url: URL) async {
        guard let client else { return }
        portableBackupManifest = nil
        portableBackupStatus = nil
        guard let path = portableBackupPath(url) else {
            errorMessage = "Portable backups require an absolute .ally-backup file path."
            return
        }
        beginBusy()
        defer { endBusy() }
        do {
            portableBackupManifest = try await client.call(
                "data.validate_backup",
                params: ["path": .string(path)]
            )
            portableBackupStatus = "Backup validated"
            errorMessage = nil
        } catch {
            errorMessage = error.localizedDescription
        }
    }

    private func portableBackupPath(_ url: URL) -> String? {
        guard url.isFileURL else { return nil }
        let path = url.path
        guard path.hasPrefix("/"), url.pathExtension == "ally-backup" else {
            return nil
        }
        return path
    }

    func selectRuntimeProfile(_ profileID: String) async {
        guard let client else { return }
        beginBusy()
        defer { endBusy() }
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
        beginBusy()
        defer { endBusy() }
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
        let token = UUID()
        conversationSelectionToken = token
        selectedConversationID = id
        beginBusy()
        defer { endBusy() }
        do {
            let loaded: ConversationView = try await client.call(
                "conversation.get",
                params: ["conversation_id": .string(id)]
            )
            guard
                conversationSelectionToken == token,
                selectedConversationID == id
            else {
                return
            }
            conversation = loaded
            errorMessage = nil
        } catch {
            guard
                conversationSelectionToken == token,
                selectedConversationID == id
            else {
                return
            }
            errorMessage = error.localizedDescription
        }
    }

    func createConversation() async {
        guard let client else { return }
        let selectionTokenAtStart = conversationSelectionToken
        let selectedIDAtStart = selectedConversationID
        beginBusy()
        defer { endBusy() }
        do {
            let created: ConversationSummary = try await client.call(
                "conversation.create"
            )
            let shouldSelectCreated =
                conversationSelectionToken == selectionTokenAtStart
                && selectedConversationID == selectedIDAtStart
            if shouldSelectCreated {
                let token = UUID()
                conversationSelectionToken = token
                selectedConversationID = created.id
                let loaded: ConversationView = try await client.call(
                    "conversation.get",
                    params: ["conversation_id": .string(created.id)]
                )
                if
                    conversationSelectionToken == token,
                    selectedConversationID == created.id
                {
                    conversation = loaded
                }
            }
            snapshot = try await client.call("bootstrap")
            errorMessage = nil
        } catch {
            errorMessage = error.localizedDescription
        }
    }

    func searchConversations(_ query: String) async {
        guard let client else { return }
        let compact = query.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !compact.isEmpty else {
            conversationSearchResults = []
            return
        }
        conversationSearchResults = []
        beginBusy()
        defer { endBusy() }
        do {
            conversationSearchResults = try await client.call(
                "conversation.search",
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

    func clearConversationSearch() {
        conversationSearchResults = []
    }

    func deleteConversation(_ id: String) async -> Bool {
        guard let client else { return false }
        beginBusy()
        defer { endBusy() }
        do {
            let deleted: Bool = try await client.call(
                "conversation.delete",
                params: ["conversation_id": .string(id)]
            )
            guard deleted else { return false }
            if selectedConversationID == id {
                conversationSelectionToken = nil
                selectedConversationID = nil
                conversation = nil
                composer = ""
            }
            conversationSearchResults = []
            snapshot = try await client.call("bootstrap")
            errorMessage = nil
            return true
        } catch {
            errorMessage = error.localizedDescription
            return false
        }
    }

    func selectMemory(_ id: String) async {
        guard let client else { return }
        let token = UUID()
        memorySelectionToken = token
        selectedMemoryID = id
        beginBusy()
        defer { endBusy() }
        do {
            let loaded: MemorySummary = try await client.call(
                "memory.get",
                params: ["memory_id": .string(id)]
            )
            guard
                memorySelectionToken == token,
                selectedMemoryID == id
            else {
                return
            }
            memoryDetail = loaded
            errorMessage = nil
        } catch {
            guard
                memorySelectionToken == token,
                selectedMemoryID == id
            else {
                return
            }
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
        beginBusy()
        defer { endBusy() }
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

    func rememberMemory(
        content: String,
        kind: String,
        confidence: Double,
        importance: Double,
        privacy: String
    ) async -> Bool {
        guard let client else { return false }
        let compact = content.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !compact.isEmpty else { return false }
        beginBusy()
        defer { endBusy() }
        do {
            let _: MemorySummary = try await client.call(
                "memory.remember",
                params: [
                    "content": .string(compact),
                    "kind": .string(kind),
                    "confidence": .number(confidence),
                    "importance": .number(importance),
                    "privacy": .string(privacy),
                ]
            )
            memories = try await client.call(
                "memory.list",
                params: ["limit": .number(100)]
            )
            memorySearchResults = []
            errorMessage = nil
            return true
        } catch {
            errorMessage = error.localizedDescription
            return false
        }
    }

    func proposeMemories(
        from text: String,
        privacy: String = "private"
    ) async {
        guard let client else { return }
        let compact = text.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !compact.isEmpty else {
            memoryProposal = nil
            return
        }
        beginBusy()
        defer { endBusy() }
        do {
            memoryProposal = try await client.call(
                "memory.propose",
                params: [
                    "text": .string(compact),
                    "source_type": .string("user"),
                    "privacy": .string(privacy),
                ]
            )
            errorMessage = nil
        } catch {
            memoryProposal = nil
            errorMessage = error.localizedDescription
        }
    }

    func acceptMemoryProposals(indices: [Int]) async -> Bool {
        guard let client, let proposal = memoryProposal, !indices.isEmpty else {
            return false
        }
        beginBusy()
        defer { endBusy() }
        do {
            let values = indices.sorted().map { JSONValue.number(Double($0)) }
            let _: [MemorySummary] = try await client.call(
                "memory.accept_proposals",
                params: [
                    "bundle": proposal.bridgeValue,
                    "indices": .array(values),
                ]
            )
            memories = try await client.call(
                "memory.list",
                params: ["limit": .number(100)]
            )
            memorySearchResults = []
            memoryProposal = nil
            errorMessage = nil
            return true
        } catch {
            errorMessage = error.localizedDescription
            return false
        }
    }

    func clearMemoryProposal() {
        memoryProposal = nil
    }

    func correctMemory(memoryID: String, content: String) async {
        guard let client else { return }
        let compact = content.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !compact.isEmpty else { return }
        let selectionToken = memorySelectionToken
        beginBusy()
        defer { endBusy() }
        do {
            let _: MemorySummary = try await client.call(
                "memory.supersede",
                params: [
                    "memory_id": .string(memoryID),
                    "content": .string(compact),
                ]
            )
            memories = try await client.call(
                "memory.list",
                params: ["limit": .number(100)]
            )
            if
                memorySelectionToken == selectionToken,
                selectedMemoryID == memoryID
            {
                let original: MemorySummary = try await client.call(
                    "memory.get",
                    params: ["memory_id": .string(memoryID)]
                )
                if
                    memorySelectionToken == selectionToken,
                    selectedMemoryID == memoryID
                {
                    memoryDetail = original
                }
            }
            memorySearchResults = []
            errorMessage = nil
        } catch {
            errorMessage = error.localizedDescription
        }
    }

    func retractMemory(_ memoryID: String) async {
        guard let client else { return }
        let selectionToken = memorySelectionToken
        beginBusy()
        defer { endBusy() }
        do {
            let updated: MemorySummary = try await client.call(
                "memory.retract",
                params: ["memory_id": .string(memoryID)]
            )
            if
                memorySelectionToken == selectionToken,
                selectedMemoryID == memoryID
            {
                memoryDetail = updated
            }
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
        let token = UUID()
        knowledgeSelectionToken = token
        selectedKnowledgeSourceID = id
        beginBusy()
        defer { endBusy() }
        do {
            let loaded: KnowledgeSourceView = try await client.call(
                "knowledge.get",
                params: ["source_id": .string(id)]
            )
            guard
                knowledgeSelectionToken == token,
                selectedKnowledgeSourceID == id
            else {
                return
            }
            knowledgeDetail = loaded
            errorMessage = nil
        } catch {
            guard
                knowledgeSelectionToken == token,
                selectedKnowledgeSourceID == id
            else {
                return
            }
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
        beginBusy()
        defer { endBusy() }
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

    func deleteKnowledgeSource(_ id: String) async -> Bool {
        guard let client else { return false }
        beginBusy()
        defer { endBusy() }
        do {
            let deleted: Bool = try await client.call(
                "knowledge.delete",
                params: ["source_id": .string(id)]
            )
            guard deleted else { return false }
            if selectedKnowledgeSourceID == id {
                knowledgeSelectionToken = nil
                selectedKnowledgeSourceID = nil
                knowledgeDetail = nil
            }
            knowledgeSearchResults = []
            knowledge = try await client.call(
                "knowledge.list",
                params: ["limit": .number(100)]
            )
            errorMessage = nil
            return true
        } catch {
            errorMessage = error.localizedDescription
            return false
        }
    }

    func updateKnowledgeSource(
        _ source: KnowledgeSourceSummary,
        text: String
    ) async -> Bool {
        guard let client else { return false }
        let compact = text.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !compact.isEmpty else { return false }
        let payload = KnowledgeSourceUpdatePayload(
            source: source,
            text: compact
        )
        let selectionToken = knowledgeSelectionToken

        beginBusy()
        defer { endBusy() }
        do {
            let result: KnowledgeIngestResult = try await client.call(
                "knowledge.ingest_text",
                params: payload.bridgeParams
            )
            knowledge = try await client.call(
                "knowledge.list",
                params: ["limit": .number(100)]
            )
            if
                knowledgeSelectionToken == selectionToken,
                selectedKnowledgeSourceID == result.source.id
            {
                let detail: KnowledgeSourceView = try await client.call(
                    "knowledge.get",
                    params: ["source_id": .string(result.source.id)]
                )
                if
                    knowledgeSelectionToken == selectionToken,
                    selectedKnowledgeSourceID == result.source.id
                {
                    knowledgeDetail = detail
                }
            }
            knowledgeSearchResults = []
            errorMessage = nil
            return true
        } catch {
            errorMessage = error.localizedDescription
            return false
        }
    }

    func ingestKnowledge(title: String, text: String) async {
        let compactTitle = title.trimmingCharacters(in: .whitespacesAndNewlines)
        let compactText = text.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !compactTitle.isEmpty, !compactText.isEmpty else { return }
        await ingestKnowledgePayload(
            title: compactTitle,
            text: compactText,
            sourceKind: "note"
        )
    }

    func ingestImportedKnowledge(_ imported: KnowledgeFileImport) async {
        let compactTitle = imported.title.trimmingCharacters(
            in: .whitespacesAndNewlines
        )
        guard !compactTitle.isEmpty else { return }
        await ingestKnowledgePayload(
            title: compactTitle,
            text: imported.text,
            sourceKind: "import"
        )
    }

    private func ingestKnowledgePayload(
        title: String,
        text: String,
        sourceKind: String
    ) async {
        guard let client else { return }
        beginBusy()
        defer { endBusy() }
        do {
            let uri = "ally-desktop://\(sourceKind)/\(UUID().uuidString.lowercased())"
            let result: KnowledgeIngestResult = try await client.call(
                "knowledge.ingest_text",
                params: [
                    "uri": .string(uri),
                    "title": .string(title),
                    "text": .string(text),
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

    func refreshInstructions() async {
        guard let client else { return }
        beginBusy()
        defer { endBusy() }
        do {
            instructionProfiles = try await client.call(
                "instructions.list",
                params: ["include_disabled": .bool(true)]
            )
            errorMessage = nil
        } catch {
            errorMessage = error.localizedDescription
        }
    }

    func setInstructions(
        scope: String,
        scopeKey: String?,
        content: String,
        enabled: Bool
    ) async {
        guard let client else { return }
        let compactContent = content.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !compactContent.isEmpty else { return }
        var params: [String: JSONValue] = [
            "scope": .string(scope),
            "content": .string(compactContent),
            "enabled": .bool(enabled),
        ]
        if let scopeKey, !scopeKey.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty {
            params["scope_key"] = .string(
                scopeKey.trimmingCharacters(in: .whitespacesAndNewlines)
            )
        }
        beginBusy()
        defer { endBusy() }
        do {
            let _: UserInstructionsSummary = try await client.call(
                "instructions.set",
                params: params
            )
            instructionProfiles = try await client.call(
                "instructions.list",
                params: ["include_disabled": .bool(true)]
            )
            instructionResolution = nil
            errorMessage = nil
        } catch {
            errorMessage = error.localizedDescription
        }
    }

    func setInstructionsEnabled(
        _ profile: UserInstructionsSummary,
        enabled: Bool
    ) async {
        guard let client else { return }
        var params: [String: JSONValue] = [
            "scope": .string(profile.scope),
            "enabled": .bool(enabled),
        ]
        if profile.scope != "global" {
            params["scope_key"] = .string(profile.scopeKey)
        }
        beginBusy()
        defer { endBusy() }
        do {
            let _: UserInstructionsSummary = try await client.call(
                "instructions.set_enabled",
                params: params
            )
            instructionProfiles = try await client.call(
                "instructions.list",
                params: ["include_disabled": .bool(true)]
            )
            instructionResolution = nil
            errorMessage = nil
        } catch {
            errorMessage = error.localizedDescription
        }
    }

    func clearInstructions(_ profile: UserInstructionsSummary) async {
        guard let client else { return }
        var params: [String: JSONValue] = [
            "scope": .string(profile.scope),
        ]
        if profile.scope != "global" {
            params["scope_key"] = .string(profile.scopeKey)
        }
        beginBusy()
        defer { endBusy() }
        do {
            let _: Bool = try await client.call(
                "instructions.clear",
                params: params
            )
            instructionProfiles = try await client.call(
                "instructions.list",
                params: ["include_disabled": .bool(true)]
            )
            instructionResolution = nil
            errorMessage = nil
        } catch {
            errorMessage = error.localizedDescription
        }
    }

    func resolveInstructions(
        projectKey: String,
        conversationKey: String,
        taskKey: String,
        sessionInstructions: String
    ) async {
        guard let client else { return }
        var params: [String: JSONValue] = [:]
        for (name, value) in [
            ("project_key", projectKey),
            ("conversation_key", conversationKey),
            ("task_key", taskKey),
            ("session_instructions", sessionInstructions),
        ] {
            let compact = value.trimmingCharacters(in: .whitespacesAndNewlines)
            if !compact.isEmpty {
                params[name] = .string(compact)
            }
        }
        beginBusy()
        defer { endBusy() }
        do {
            instructionResolution = try await client.call(
                "instructions.resolve",
                params: params
            )
            errorMessage = nil
        } catch {
            instructionResolution = nil
            errorMessage = error.localizedDescription
        }
    }

    func inspectResearch(_ query: String, count: Int = 5) async {
        guard let client else { return }
        let compact = query.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !compact.isEmpty else {
            researchInspection = nil
            researchResults = []
            researchSynthesis = nil
            researchSynthesisStatus = nil
            researchStatus = nil
            researchMoreResultsAvailable = false
            return
        }
        researchResults = []
        researchSynthesis = nil
        researchSynthesisStatus = nil
        researchMoreResultsAvailable = false
        beginBusy()
        defer { endBusy() }
        do {
            researchInspection = try await client.call(
                "research.inspect",
                params: [
                    "query": .string(compact),
                    "count": .number(Double(count)),
                ]
            )
            researchStatus = researchInspection?.decision
            errorMessage = nil
        } catch {
            researchInspection = nil
            researchStatus = nil
            errorMessage = error.localizedDescription
        }
    }

    func runApprovedResearch(_ query: String, count: Int = 5) async {
        guard let client else { return }
        let compact = query.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !compact.isEmpty else { return }
        beginBusy()
        defer { endBusy() }
        do {
            let execution: WebResearchAnswerExecution = try await client.call(
                "research.answer",
                params: [
                    "query": .string(compact),
                    "count": .number(Double(count)),
                    "approved": .bool(true),
                ]
            )
            researchStatus = execution.search.status
            researchMoreResultsAvailable = execution.search.moreResultsAvailable
            researchSynthesis = execution.synthesis
            researchSynthesisStatus = execution.synthesisStatus
            if execution.search.status == "succeeded" {
                researchResults = execution.search.results
                errorMessage = nil
            } else {
                researchResults = []
                researchSynthesis = nil
                researchSynthesisStatus = nil
                if execution.search.status == "failed" {
                    errorMessage = "Web research failed safely: \(execution.search.errorClass ?? "ExternalResearchError")"
                }
            }
        } catch {
            researchResults = []
            researchSynthesis = nil
            researchSynthesisStatus = nil
            researchStatus = nil
            researchMoreResultsAvailable = false
            errorMessage = error.localizedDescription
        }
    }

    func clearResearch() {
        researchInspection = nil
        researchResults = []
        researchSynthesis = nil
        researchSynthesisStatus = nil
        researchStatus = nil
        researchMoreResultsAvailable = false
    }

    func refreshAttention() async {
        guard let client else { return }
        beginBusy()
        defer { endBusy() }
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
        let token = UUID()
        attentionSelectionToken = token
        selectedAttentionID = id
        beginBusy()
        defer { endBusy() }
        do {
            let loaded: AttentionEventView = try await client.call(
                "attention.get",
                params: ["event_id": .string(id)]
            )
            guard
                attentionSelectionToken == token,
                selectedAttentionID == id
            else {
                return
            }
            attentionDetail = loaded
            errorMessage = nil
        } catch {
            guard
                attentionSelectionToken == token,
                selectedAttentionID == id
            else {
                return
            }
            errorMessage = error.localizedDescription
        }
    }

    func markAttentionHandled(_ id: String) async {
        guard let client else { return }
        let selectionToken = attentionSelectionToken
        beginBusy()
        defer { endBusy() }
        do {
            let updated: AttentionEventView = try await client.call(
                "attention.mark_handled",
                params: ["event_id": .string(id)]
            )
            if
                attentionSelectionToken == selectionToken,
                selectedAttentionID == id
            {
                attentionDetail = updated
            }
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
        beginBusy()
        defer { endBusy() }
        do {
            notificationAuthorization = try await notificationAuthorizationClient.requestAuthorization()
            errorMessage = nil
            if notificationAuthorization.canPresentNotifications {
                await runProactiveCycleIfEnabled()
            }
        } catch {
            errorMessage = "Notification authorization request failed."
        }
    }

    func refreshLegacyManagedServiceStatus() async {
        guard let client else {
            legacyManagedService = nil
            return
        }
        do {
            legacyManagedService = try await client.call("service.legacy_status")
        } catch {
            legacyManagedService = nil
        }
    }

    func retireLegacyManagedService() async {
        guard let client else { return }
        beginBusy()
        defer { endBusy() }
        do {
            legacyManagedService = try await client.call("service.retire_legacy")
            errorMessage = nil
        } catch {
            await refreshLegacyManagedServiceStatus()
            errorMessage = "The legacy Ally background service could not be retired safely."
        }
    }

    func refreshBackgroundServiceState() {
        backgroundServiceState = backgroundServiceClient.currentState()
    }

    func enableBackgroundService() async {
        await refreshLegacyManagedServiceStatus()
        guard let legacyManagedService else {
            errorMessage = "Legacy service state is unavailable. Background proactivity remains disabled."
            return
        }
        guard !legacyManagedService.configured else {
            errorMessage = legacyManagedService.canRetire
                ? "Retire the legacy Ally background service before enabling the signed app login item."
                : "A modified legacy service definition requires manual review before background proactivity can be enabled."
            return
        }
        do {
            backgroundServiceState = try backgroundServiceClient.register()
            errorMessage = nil
            if backgroundServiceState == .enabled {
                await runProactiveCycleIfEnabled()
            }
        } catch {
            refreshBackgroundServiceState()
            errorMessage = "Background proactivity could not be enabled."
        }
    }

    func disableBackgroundService() {
        do {
            backgroundServiceState = try backgroundServiceClient.unregister()
            errorMessage = nil
        } catch {
            refreshBackgroundServiceState()
            errorMessage = "Background proactivity could not be disabled."
        }
    }

    func openBackgroundServiceSettings() {
        backgroundServiceClient.openSystemSettings()
    }

    func runProactiveCycleIfEnabled() async {
        refreshBackgroundServiceState()
        guard backgroundServiceState == .enabled else { return }
        await refreshLegacyManagedServiceStatus()
        guard let legacyManagedService else {
            proactiveCycleError = "Legacy service state is unavailable; automatic proactivity is paused."
            return
        }
        guard !legacyManagedService.configured else {
            proactiveCycleError = "Automatic proactivity is paused until the legacy Ally background service is retired."
            return
        }
        await runProactiveCycle()
    }

    private func runProactiveCycle() async {
        guard let client, !proactiveCycleRunning else { return }
        proactiveCycleRunning = true
        defer { proactiveCycleRunning = false }

        do {
            let prepared: DesktopProactivePreparation = try await client.call(
                "service.prepare_proactive"
            )
            let deliveryContext = await DesktopNotificationDeliveryClient.context()
            var knownIdentifiers = deliveryContext.knownIdentifiers
            var outcomes: [DesktopNotificationDeliveryOutcome] = []
            outcomes.reserveCapacity(prepared.candidates.count)

            for candidate in prepared.candidates {
                let outcome = await DesktopNotificationDeliveryClient.deliver(
                    candidate,
                    context: DesktopNotificationDeliveryContext(
                        canDeliver: deliveryContext.canDeliver,
                        knownIdentifiers: knownIdentifiers
                    )
                )
                let _: AttentionDeliverySummary = try await client.call(
                    "attention.notification_result",
                    params: [
                        "run_id": .string(prepared.run.id),
                        "event_id": .string(outcome.eventId),
                        "delivery_key": .string(outcome.deliveryKey),
                        "succeeded": .bool(outcome.succeeded),
                    ]
                )
                outcomes.append(outcome)
                if outcome.succeeded {
                    knownIdentifiers.insert(outcome.deliveryKey)
                }
            }

            var completedRun = prepared.run
            if prepared.run.status == "running" {
                completedRun = try await client.call(
                    "service.complete_proactive",
                    params: ["run_id": .string(prepared.run.id)]
                )
            }

            lastProactiveCycleAt = Date()
            proactiveCycleError = completedRun.status == "degraded"
                ? "The proactive cycle completed with notification delivery failures."
                : nil

            if completedRun.scheduledEvents > 0 || !outcomes.isEmpty {
                async let snapshot: BootstrapSnapshot = client.call("bootstrap")
                async let events: [EventSummary] = client.call(
                    "attention.events",
                    params: ["limit": .number(100)]
                )
                async let history: [AttentionDeliverySummary] = client.call(
                    "attention.delivery_history",
                    params: ["limit": .number(100)]
                )
                self.snapshot = try await snapshot
                attentionEvents = try await events
                attentionDeliveryHistory = try await history
            }
        } catch {
            proactiveCycleError = "The proactive cycle failed."
        }
    }

    func proposeTask(_ goal: String) async {
        guard let client else { return }
        let compact = goal.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !compact.isEmpty else {
            taskProposal = nil
            return
        }
        beginBusy()
        defer { endBusy() }
        do {
            taskProposal = try await client.call(
                "task.propose",
                params: ["goal": .string(compact)]
            )
            errorMessage = nil
        } catch {
            taskProposal = nil
            errorMessage = error.localizedDescription
        }
    }

    func createProposedTask() async -> String? {
        guard let client, let proposal = taskProposal else { return nil }
        beginBusy()
        defer { endBusy() }
        do {
            let created: TaskView = try await client.call(
                "task.create",
                params: ["plan": proposal.bridgeValue]
            )
            taskDetail = created
            snapshot = try await client.call("bootstrap")
            taskProposal = nil
            errorMessage = nil
            return created.task.id
        } catch {
            errorMessage = error.localizedDescription
            return nil
        }
    }

    func clearTaskProposal() {
        taskProposal = nil
    }

    func selectTask(_ id: String) async {
        guard let client else { return }
        let token = UUID()
        taskSelectionToken = token
        selectedTaskID = id
        beginBusy()
        defer { endBusy() }
        do {
            let loaded: TaskView = try await client.call(
                "task.get",
                params: ["task_id": .string(id)]
            )
            guard
                taskSelectionToken == token,
                selectedTaskID == id
            else {
                return
            }
            taskDetail = loaded
            errorMessage = nil
        } catch {
            guard
                taskSelectionToken == token,
                selectedTaskID == id
            else {
                return
            }
            errorMessage = error.localizedDescription
        }
    }

    func runTask(_ id: String) async {
        guard let client else { return }
        let selectionToken = taskSelectionToken
        beginBusy()
        defer { endBusy() }
        do {
            let updated: TaskView = try await client.call(
                "task.run",
                params: ["task_id": .string(id)]
            )
            if
                taskSelectionToken == selectionToken,
                selectedTaskID == id
            {
                taskDetail = updated
            }
            snapshot = try await client.call("bootstrap")
            errorMessage = nil
        } catch {
            errorMessage = error.localizedDescription
        }
    }

    func approveTaskStep(taskID: String, stepID: String) async {
        guard let client else { return }
        let selectionToken = taskSelectionToken
        beginBusy()
        defer { endBusy() }
        do {
            let updated: TaskView = try await client.call(
                "task.approve_step",
                params: [
                    "task_id": .string(taskID),
                    "step_id": .string(stepID),
                ]
            )
            if
                taskSelectionToken == selectionToken,
                selectedTaskID == taskID
            {
                taskDetail = updated
            }
            snapshot = try await client.call("bootstrap")
            errorMessage = nil
        } catch {
            let message = error.localizedDescription
            if
                taskSelectionToken == selectionToken,
                selectedTaskID == taskID
            {
                await selectTask(taskID)
            }
            errorMessage = message
        }
    }

    func retryTaskStep(taskID: String, stepID: String) async {
        guard let client else { return }
        let selectionToken = taskSelectionToken
        beginBusy()
        defer { endBusy() }
        do {
            let updated: TaskView = try await client.call(
                "task.retry_step",
                params: [
                    "task_id": .string(taskID),
                    "step_id": .string(stepID),
                ]
            )
            if
                taskSelectionToken == selectionToken,
                selectedTaskID == taskID
            {
                taskDetail = updated
            }
            snapshot = try await client.call("bootstrap")
            errorMessage = nil
        } catch {
            let message = error.localizedDescription
            if
                taskSelectionToken == selectionToken,
                selectedTaskID == taskID
            {
                await selectTask(taskID)
            }
            errorMessage = message
        }
    }

    func sendMessage() async {
        guard let client, let id = selectedConversationID else { return }
        let text = composer.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !text.isEmpty else { return }
        let selectionToken = conversationSelectionToken
        composer = ""
        beginBusy()
        defer { endBusy() }
        do {
            let _: ChatTurnResult = try await client.call(
                "conversation.send",
                params: [
                    "conversation_id": .string(id),
                    "message": .string(text),
                ]
            )
            let loaded: ConversationView = try await client.call(
                "conversation.get",
                params: ["conversation_id": .string(id)]
            )
            if
                conversationSelectionToken == selectionToken,
                selectedConversationID == id
            {
                conversation = loaded
            }
            snapshot = try await client.call("bootstrap")
            errorMessage = nil
        } catch {
            errorMessage = error.localizedDescription
        }
    }
}
#endif
