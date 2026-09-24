import Foundation

public struct DesktopBridgeClient: Sendable {
    public static let helperEnvironmentKey = "ALLY_DESKTOP_BRIDGE"
    public static let maximumResponseBytes = 2 * 1024 * 1024
    public static let supportedProtocolVersion = 3

    public let executableURL: URL

    public init(executableURL: URL) throws {
        guard executableURL.path.hasPrefix("/") else {
            throw DesktopBridgeError.helperNotExecutable
        }
        guard FileManager.default.isExecutableFile(atPath: executableURL.path) else {
            throw DesktopBridgeError.helperNotExecutable
        }
        self.executableURL = executableURL
    }

    public init(environment: [String: String] = ProcessInfo.processInfo.environment) throws {
        self.executableURL = try Self.resolveHelper(environment: environment)
    }

    public static func resolveHelper(environment: [String: String]) throws -> URL {
        guard let configured = environment[helperEnvironmentKey], !configured.isEmpty else {
            throw DesktopBridgeError.helperNotFound
        }
        guard configured.hasPrefix("/") else {
            throw DesktopBridgeError.helperNotExecutable
        }
        let url = URL(fileURLWithPath: configured).standardizedFileURL
        guard FileManager.default.isExecutableFile(atPath: url.path) else {
            throw DesktopBridgeError.helperNotExecutable
        }
        return url
    }

    static func helperEnvironment(
        source: [String: String] = ProcessInfo.processInfo.environment
    ) -> [String: String] {
        let allowed = ["HOME", "TMPDIR", "LANG", "LC_ALL"]
        return Dictionary(
            uniqueKeysWithValues: allowed.compactMap { key in
                source[key].map { (key, $0) }
            }
        )
    }

    public func call<Result: Decodable & Sendable>(
        _ method: String,
        params: [String: JSONValue] = [:],
        as resultType: Result.Type = Result.self
    ) async throws -> Result {
        let executableURL = self.executableURL
        return try await Task.detached(priority: .userInitiated) {
            try Self.callSynchronously(
                executableURL: executableURL,
                method: method,
                params: params,
                as: resultType
            )
        }.value
    }

    static func callSynchronously<Result: Decodable & Sendable>(
        executableURL: URL,
        method: String,
        params: [String: JSONValue],
        as resultType: Result.Type
    ) throws -> Result {
        let process = Process()
        let input = Pipe()
        let output = Pipe()
        let errors = Pipe()
        process.executableURL = executableURL
        process.arguments = ["--once"]
        process.environment = helperEnvironment()
        process.standardInput = input
        process.standardOutput = output
        process.standardError = errors

        let encoder = JSONEncoder()
        let request = BridgeRequest(method: method, params: params)
        var payload = try encoder.encode(request)
        payload.append(0x0A)

        do {
            try process.run()
        } catch {
            throw DesktopBridgeError.launchFailed
        }

        do {
            try input.fileHandleForWriting.write(contentsOf: payload)
            try input.fileHandleForWriting.close()
        } catch {
            process.terminate()
            throw DesktopBridgeError.writeFailed
        }

        process.waitUntilExit()
        let data = try output.fileHandleForReading.readToEnd() ?? Data()
        if data.count > maximumResponseBytes {
            throw DesktopBridgeError.responseTooLarge
        }
        guard process.terminationStatus == 0 || !data.isEmpty else {
            throw DesktopBridgeError.launchFailed
        }

        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        guard let envelope = try? decoder.decode(BridgeEnvelope<Result>.self, from: data) else {
            throw DesktopBridgeError.invalidResponse
        }
        if envelope.ok, let result = envelope.result {
            return result
        }
        if let failure = envelope.error {
            throw DesktopBridgeError.requestFailed(
                code: failure.code,
                message: failure.message
            )
        }
        throw DesktopBridgeError.invalidResponse
    }
}
