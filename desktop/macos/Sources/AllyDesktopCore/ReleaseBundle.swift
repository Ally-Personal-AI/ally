import CryptoKit
import Foundation

public struct DesktopReleaseManifest: Decodable, Sendable, Equatable {
    public let schemaVersion: Int
    public let bundleIdentifier: String
    public let allyVersion: String
    public let buildVersion: Int
    public let bridgeProtocolVersion: Int
    public let databaseSchemaVersion: Int
    public let helperRelativePath: String
    public let helperSha256: String
    public let sourceRevision: String?
}

public enum DesktopReleaseBundle {
    public static let bundleIdentifier = "ai.ally.personal"
    public static let helperRelativePath = "Contents/Helpers/ally-desktop-bridge"
    public static let manifestRelativePath = "Contents/Resources/release-manifest.json"

    public static func resolveVerifiedHelper(
        bundleURL: URL,
        bundleIdentifier actualBundleIdentifier: String?
    ) throws -> URL {
        let manifestURL = bundleURL.appendingPathComponent(manifestRelativePath)
        guard FileManager.default.isReadableFile(atPath: manifestURL.path) else {
            throw DesktopBridgeError.releaseManifestMissing
        }

        let manifest: DesktopReleaseManifest
        do {
            let data = try Data(contentsOf: manifestURL)
            let decoder = JSONDecoder()
            decoder.keyDecodingStrategy = .convertFromSnakeCase
            manifest = try decoder.decode(DesktopReleaseManifest.self, from: data)
        } catch {
            throw DesktopBridgeError.releaseManifestInvalid
        }

        guard
            manifest.schemaVersion == 2,
            manifest.bundleIdentifier == Self.bundleIdentifier,
            actualBundleIdentifier == manifest.bundleIdentifier,
            manifest.bridgeProtocolVersion == DesktopBridgeClient.supportedProtocolVersion,
            manifest.helperRelativePath == helperRelativePath,
            manifest.buildVersion > 0,
            manifest.databaseSchemaVersion >= 0,
            isLowercaseSHA256(manifest.helperSha256),
            !manifest.allyVersion.isEmpty
        else {
            throw DesktopBridgeError.releaseManifestInvalid
        }

        let helperURL = bundleURL.appendingPathComponent(helperRelativePath).standardizedFileURL
        guard FileManager.default.isExecutableFile(atPath: helperURL.path) else {
            throw DesktopBridgeError.helperNotExecutable
        }

        let digest: String
        do {
            digest = try sha256(of: helperURL)
        } catch {
            throw DesktopBridgeError.helperIntegrityFailed
        }
        guard digest == manifest.helperSha256 else {
            throw DesktopBridgeError.helperIntegrityFailed
        }
        return helperURL
    }

    static func sha256(of url: URL) throws -> String {
        let handle = try FileHandle(forReadingFrom: url)
        defer {
            try? handle.close()
        }

        var hasher = SHA256()
        while true {
            guard let data = try handle.read(upToCount: 1024 * 1024), !data.isEmpty else {
                break
            }
            hasher.update(data: data)
        }
        return hasher.finalize().map { String(format: "%02x", $0) }.joined()
    }

    static func isLowercaseSHA256(_ value: String) -> Bool {
        value.count == 64 && value.allSatisfy {
            $0.isNumber || ("a"..."f").contains(String($0))
        }
    }
}
