import Foundation
import Testing
@testable import AllyDesktopCore

@Test func packagedReleaseHelperPersistsSyntheticStateThroughRealSwiftClient() async throws {
    let environment = ProcessInfo.processInfo.environment
    guard
        let helperPath = environment["ALLY_PACKAGED_HELPER_TEST_PATH"],
        let rootPath = environment["ALLY_PACKAGED_HELPER_TEST_ROOT"]
    else {
        return
    }

    let helper = URL(fileURLWithPath: helperPath).standardizedFileURL
    let root = URL(fileURLWithPath: rootPath, isDirectory: true)
        .standardizedFileURL
    #expect(FileManager.default.isExecutableFile(atPath: helper.path))
    #expect(environment["HOME"] == root.path)

    let client = try DesktopBridgeClient(executableURL: helper)

    let info: BridgeInfo = try await client.call("bridge.info")
    #expect(info.protocolVersion == DesktopBridgeClient.supportedProtocolVersion)
    #expect(info.transport == "stdio")
    #expect(info.capabilities.contains("bootstrap"))
    #expect(info.capabilities.contains("data.backup"))
    #expect(info.capabilities.contains("data.validate_backup"))

    let initial: BootstrapSnapshot = try await client.call("bootstrap")
    #expect(initial.runtime.state == "unavailable")
    #expect(initial.runtime.target == nil)

    let conversation: ConversationSummary = try await client.call(
        "conversation.create",
        params: ["title": .string("Synthetic packaged-helper conversation")]
    )
    let reloadedConversation: ConversationView = try await client.call(
        "conversation.get",
        params: ["conversation_id": .string(conversation.id)]
    )
    #expect(reloadedConversation.conversation.id == conversation.id)
    #expect(
        reloadedConversation.conversation.title
            == "Synthetic packaged-helper conversation"
    )
    #expect(reloadedConversation.messages.isEmpty)

    let conversationSearch: [ConversationSearchResult] = try await client.call(
        "conversation.search",
        params: [
            "query": .string("packaged-helper conversation"),
            "limit": .number(20),
        ]
    )
    #expect(
        conversationSearch.contains {
            $0.conversation.id == conversation.id
        }
    )

    let remembered: MemorySummary = try await client.call(
        "memory.remember",
        params: [
            "content": .string("Synthetic packaged-helper memory."),
            "kind": .string("semantic"),
            "confidence": .number(1),
            "importance": .number(0.5),
            "privacy": .string("private"),
        ]
    )
    let memories: [MemorySummary] = try await client.call(
        "memory.list",
        params: ["limit": .number(100)]
    )
    #expect(memories.contains(where: { $0.id == remembered.id }))
    #expect(
        memories.contains(
            where: { $0.content == "Synthetic packaged-helper memory." }
        )
    )

    let instruction: UserInstructionsSummary = try await client.call(
        "instructions.set",
        params: [
            "scope": .string("global"),
            "content": .string("Synthetic packaged-helper instruction."),
            "enabled": .bool(true),
        ]
    )
    #expect(instruction.scope == "global")
    #expect(instruction.content == "Synthetic packaged-helper instruction.")

    let instructionProfiles: [UserInstructionsSummary] = try await client.call(
        "instructions.list",
        params: ["include_disabled": .bool(true)]
    )
    #expect(
        instructionProfiles.contains {
            $0.scope == "global"
                && $0.content == "Synthetic packaged-helper instruction."
                && $0.enabled
        }
    )

    let resolvedInstructions: InstructionResolutionView = try await client.call(
        "instructions.resolve"
    )
    #expect(
        resolvedInstructions.contributions.contains {
            $0.scope == "global"
                && $0.content == "Synthetic packaged-helper instruction."
        }
    )
    #expect(
        resolvedInstructions.rendered?.contains(
            "Synthetic packaged-helper instruction."
        ) == true
    )

    let ingested: KnowledgeIngestResult = try await client.call(
        "knowledge.ingest_text",
        params: [
            "uri": .string("ally-test://packaged-helper/synthetic"),
            "title": .string("Synthetic packaged-helper knowledge"),
            "text": .string("Synthetic packaged-helper knowledge persists."),
            "media_type": .string("text/plain"),
        ]
    )
    let knowledge: [KnowledgeSourceSummary] = try await client.call(
        "knowledge.list",
        params: ["limit": .number(100)]
    )
    #expect(
        knowledge.contains(where: { $0.id == ingested.source.id })
    )

    let revised: KnowledgeIngestResult = try await client.call(
        "knowledge.ingest_text",
        params: [
            "uri": .string(ingested.source.uri),
            "title": .string(ingested.source.title),
            "text": .string(
                "Synthetic packaged-helper revised knowledge persists."
            ),
            "media_type": .string(ingested.source.mediaType),
        ]
    )
    #expect(revised.source.id == ingested.source.id)
    #expect(revised.revision.revision == 2)
    #expect(revised.source.currentRevision == 2)

    let revisedDetail: KnowledgeSourceView = try await client.call(
        "knowledge.get",
        params: ["source_id": .string(revised.source.id)]
    )
    #expect(revisedDetail.source.currentRevision == 2)
    #expect(revisedDetail.revisions.contains { $0.revision == 1 })
    #expect(revisedDetail.revisions.contains { $0.revision == 2 })
    #expect(
        revisedDetail.currentChunks.contains {
            $0.content.contains("revised knowledge")
        }
    )

    let refreshed: BootstrapSnapshot = try await client.call("bootstrap")
    #expect(
        refreshed.conversations.items.contains(
            where: { $0.id == conversation.id }
        )
    )

    let backupURL = root.appendingPathComponent(
        "packaged-helper.ally-backup",
        isDirectory: false
    )
    let createdBackup: BackupManifestSummary = try await client.call(
        "data.backup",
        params: ["path": .string(backupURL.path)]
    )
    #expect(FileManager.default.fileExists(atPath: backupURL.path))
    #expect(createdBackup.format == "ally-backup")

    let validatedBackup: BackupManifestSummary = try await client.call(
        "data.validate_backup",
        params: ["path": .string(backupURL.path)]
    )
    #expect(validatedBackup == createdBackup)

    let deletedKnowledge: Bool = try await client.call(
        "knowledge.delete",
        params: ["source_id": .string(revised.source.id)]
    )
    #expect(deletedKnowledge)
    let knowledgeAfterDeletion: [KnowledgeSourceSummary] = try await client.call(
        "knowledge.list",
        params: ["limit": .number(100)]
    )
    #expect(
        knowledgeAfterDeletion.contains {
            $0.id == revised.source.id
        } == false
    )

    let deletedConversation: Bool = try await client.call(
        "conversation.delete",
        params: ["conversation_id": .string(conversation.id)]
    )
    #expect(deletedConversation)
    let afterDeletion: BootstrapSnapshot = try await client.call("bootstrap")
    #expect(
        afterDeletion.conversations.items.contains {
            $0.id == conversation.id
        } == false
    )

    let rootPrefix = root.path.hasSuffix("/") ? root.path : root.path + "/"
    let enumerator = FileManager.default.enumerator(
        at: root,
        includingPropertiesForKeys: nil
    )
    var observedAllyDatabase = false
    while let item = enumerator?.nextObject() as? URL {
        let standardized = item.standardizedFileURL.path
        #expect(
            standardized == root.path
                || standardized.hasPrefix(rootPrefix)
        )
        if item.lastPathComponent == "ally.sqlite3" {
            observedAllyDatabase = true
        }
    }
    #expect(observedAllyDatabase)
}
