import Foundation
import Testing
@testable import AllyDesktopCore

private func temporaryKnowledgeImportDirectory() throws -> URL {
    let root = FileManager.default.temporaryDirectory
        .appendingPathComponent(UUID().uuidString, isDirectory: true)
    try FileManager.default.createDirectory(
        at: root,
        withIntermediateDirectories: true
    )
    return root
}

@Test func knowledgeFileImporterReturnsOnlyTitleAndUTF8Text() throws {
    let root = try temporaryKnowledgeImportDirectory()
    defer { try? FileManager.default.removeItem(at: root) }

    let file = root.appendingPathComponent("synthetic-notes.txt")
    let expected = "Synthetic greenhouse marker ROOT-519.\n"
    try Data(expected.utf8).write(to: file)

    let imported = try KnowledgeFileImporter.load(file)

    #expect(imported.title == "synthetic-notes.txt")
    #expect(imported.text == expected)
    let labels = Set(
        Mirror(reflecting: imported).children.compactMap(\.label)
    )
    #expect(labels == Set(["title", "text"]))
    #expect(String(reflecting: imported).contains(root.path) == false)
}

@Test func knowledgeFileImporterRejectsOversizedFile() throws {
    let root = try temporaryKnowledgeImportDirectory()
    defer { try? FileManager.default.removeItem(at: root) }

    let file = root.appendingPathComponent("oversized.txt")
    try Data(
        repeating: 0x61,
        count: KnowledgeFileImporter.maximumBytes + 1
    ).write(to: file)

    #expect(throws: KnowledgeFileImportError.tooLarge) {
        _ = try KnowledgeFileImporter.load(file)
    }
}

@Test func knowledgeFileImporterRejectsNonUTF8File() throws {
    let root = try temporaryKnowledgeImportDirectory()
    defer { try? FileManager.default.removeItem(at: root) }

    let file = root.appendingPathComponent("binary.txt")
    try Data([0xff, 0xfe, 0xfd]).write(to: file)

    #expect(throws: KnowledgeFileImportError.invalidUTF8) {
        _ = try KnowledgeFileImporter.load(file)
    }
}

@Test func knowledgeFileImporterRejectsWhitespaceOnlyFile() throws {
    let root = try temporaryKnowledgeImportDirectory()
    defer { try? FileManager.default.removeItem(at: root) }

    let file = root.appendingPathComponent("empty.txt")
    try Data("  \n\t  ".utf8).write(to: file)

    #expect(throws: KnowledgeFileImportError.empty) {
        _ = try KnowledgeFileImporter.load(file)
    }
}

@Test func knowledgeFileImporterRejectsSymbolicLink() throws {
    let root = try temporaryKnowledgeImportDirectory()
    defer { try? FileManager.default.removeItem(at: root) }

    let target = root.appendingPathComponent("target.txt")
    let link = root.appendingPathComponent("link.txt")
    try Data("Synthetic local text.".utf8).write(to: target)
    try FileManager.default.createSymbolicLink(
        at: link,
        withDestinationURL: target
    )

    #expect(throws: KnowledgeFileImportError.symbolicLink) {
        _ = try KnowledgeFileImporter.load(link)
    }
}
