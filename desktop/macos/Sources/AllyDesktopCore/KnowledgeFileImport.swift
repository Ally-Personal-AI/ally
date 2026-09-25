import Foundation

public struct KnowledgeFileImport: Sendable, Equatable {
    public let title: String
    public let text: String

    public init(title: String, text: String) {
        self.title = title
        self.text = text
    }
}

public enum KnowledgeFileImportError: Error, LocalizedError, Equatable, Sendable {
    case notRegularFile
    case symbolicLink
    case tooLarge
    case invalidUTF8
    case empty
    case unreadable

    public var errorDescription: String? {
        switch self {
        case .notRegularFile:
            return "Ally can import only one regular text file."
        case .symbolicLink:
            return "Ally does not import symbolic links."
        case .tooLarge:
            return "The selected text file exceeds Ally's native import size limit."
        case .invalidUTF8:
            return "Ally currently imports UTF-8 text files only."
        case .empty:
            return "The selected text file contains no non-whitespace text."
        case .unreadable:
            return "The selected text file could not be read safely."
        }
    }
}

public enum KnowledgeFileImporter {
    public static let maximumBytes = 128 * 1024

    public static func load(_ url: URL) throws -> KnowledgeFileImport {
        guard url.isFileURL else {
            throw KnowledgeFileImportError.notRegularFile
        }

        let hasSecurityScope = url.startAccessingSecurityScopedResource()
        defer {
            if hasSecurityScope {
                url.stopAccessingSecurityScopedResource()
            }
        }

        let keys: Set<URLResourceKey> = [
            .isRegularFileKey,
            .isSymbolicLinkKey,
            .fileSizeKey,
        ]
        let before: URLResourceValues
        do {
            before = try url.resourceValues(forKeys: keys)
        } catch {
            throw KnowledgeFileImportError.unreadable
        }
        try validate(values: before)

        let data: Data
        do {
            data = try Data(contentsOf: url, options: [.mappedIfSafe])
        } catch {
            throw KnowledgeFileImportError.unreadable
        }
        guard data.count <= maximumBytes else {
            throw KnowledgeFileImportError.tooLarge
        }

        let after: URLResourceValues
        do {
            after = try url.resourceValues(forKeys: keys)
        } catch {
            throw KnowledgeFileImportError.unreadable
        }
        try validate(values: after)

        guard let text = String(data: data, encoding: .utf8) else {
            throw KnowledgeFileImportError.invalidUTF8
        }
        guard !text.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty else {
            throw KnowledgeFileImportError.empty
        }

        let title = url.lastPathComponent.trimmingCharacters(
            in: .whitespacesAndNewlines
        )
        guard !title.isEmpty else {
            throw KnowledgeFileImportError.unreadable
        }
        return KnowledgeFileImport(title: title, text: text)
    }

    private static func validate(values: URLResourceValues) throws {
        if values.isSymbolicLink == true {
            throw KnowledgeFileImportError.symbolicLink
        }
        guard values.isRegularFile == true else {
            throw KnowledgeFileImportError.notRegularFile
        }
        if let size = values.fileSize, size > maximumBytes {
            throw KnowledgeFileImportError.tooLarge
        }
    }
}
