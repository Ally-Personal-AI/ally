import Darwin
import Foundation

private final class BridgeIOState: @unchecked Sendable {
    private let lock = NSLock()
    private var response = Data()
    private var responseTooLarge = false
    private var responseReadFailed = false
    private var requestWriteFailed = false

    func appendResponse(_ chunk: Data, limit: Int) {
        lock.lock()
        defer { lock.unlock() }

        guard !responseTooLarge else {
            return
        }
        let remaining = max(0, limit - response.count)
        if chunk.count > remaining {
            if remaining > 0 {
                response.append(contentsOf: chunk.prefix(remaining))
            }
            responseTooLarge = true
            return
        }
        response.append(chunk)
    }

    func markResponseReadFailed() {
        lock.lock()
        responseReadFailed = true
        lock.unlock()
    }

    func markRequestWriteFailed() {
        lock.lock()
        requestWriteFailed = true
        lock.unlock()
    }

    func status() -> (
        responseTooLarge: Bool,
        responseReadFailed: Bool,
        requestWriteFailed: Bool
    ) {
        lock.lock()
        defer { lock.unlock() }
        return (
            responseTooLarge,
            responseReadFailed,
            requestWriteFailed
        )
    }

    func responseData() -> Data {
        lock.lock()
        defer { lock.unlock() }
        return response
    }
}

public struct DesktopBridgeClient: Sendable {
    public static let helperEnvironmentKey = "ALLY_DESKTOP_BRIDGE"
    public static let maximumResponseBytes = 2 * 1024 * 1024
    public static let supportedProtocolVersion = 15
    public static let defaultRequestTimeoutSeconds: TimeInterval = 300

    private static let ioDrainGraceSeconds: TimeInterval = 1
    private static let terminationGraceSeconds: TimeInterval = 1
    private static let pollIntervalSeconds: TimeInterval = 0.01
    private static let responseReadChunkBytes = 64 * 1024

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
        self.executableURL = try Self.resolveHelper(
            environment: environment,
            bundleURL: Bundle.main.bundleURL,
            bundleIdentifier: Bundle.main.bundleIdentifier
        )
    }

    #if DEBUG
    public static let developmentHelperOverrideEnabled = true
    #else
    public static let developmentHelperOverrideEnabled = false
    #endif

    public static func resolveHelper(
        environment: [String: String],
        bundleURL: URL = Bundle.main.bundleURL,
        bundleIdentifier: String? = Bundle.main.bundleIdentifier,
        allowDevelopmentOverride: Bool = developmentHelperOverrideEnabled
    ) throws -> URL {
        if allowDevelopmentOverride,
           let configured = environment[helperEnvironmentKey],
           !configured.isEmpty {
            guard configured.hasPrefix("/") else {
                throw DesktopBridgeError.helperNotExecutable
            }
            let url = URL(fileURLWithPath: configured).standardizedFileURL
            guard FileManager.default.isExecutableFile(atPath: url.path) else {
                throw DesktopBridgeError.helperNotExecutable
            }
            return url
        }

        return try DesktopReleaseBundle.resolveVerifiedHelper(
            bundleURL: bundleURL,
            bundleIdentifier: bundleIdentifier
        )
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
        let worker = Task.detached(priority: .userInitiated) {
            try Self.callSynchronously(
                executableURL: executableURL,
                method: method,
                params: params,
                as: resultType
            )
        }
        return try await withTaskCancellationHandler {
            try await worker.value
        } onCancel: {
            worker.cancel()
        }
    }

    static func callSynchronously<Result: Decodable & Sendable>(
        executableURL: URL,
        method: String,
        params: [String: JSONValue],
        as resultType: Result.Type,
        timeoutSeconds: TimeInterval = defaultRequestTimeoutSeconds,
        requestID: String = UUID().uuidString
    ) throws -> Result {
        guard timeoutSeconds.isFinite, timeoutSeconds > 0 else {
            throw DesktopBridgeError.invalidResponse
        }
        if currentTaskIsCancelled {
            throw DesktopBridgeError.cancelled
        }

        let process = Process()
        let input = Pipe()
        let output = Pipe()
        process.executableURL = executableURL
        process.arguments = ["--once"]
        process.environment = helperEnvironment()
        process.standardInput = input
        process.standardOutput = output
        // stderr is deliberately discarded rather than piped. Bridge errors are
        // sanitized protocol values; arbitrary helper diagnostics may contain
        // private state and must not block the child or reach the desktop UI.
        process.standardError = FileHandle.nullDevice

        let encoder = JSONEncoder()
        let request = BridgeRequest(
            id: requestID,
            method: method,
            params: params
        )
        var payload = try encoder.encode(request)
        payload.append(0x0A)

        do {
            try process.run()
        } catch {
            throw DesktopBridgeError.launchFailed
        }

        let ioState = BridgeIOState()
        let ioGroup = DispatchGroup()
        let inputHandle = input.fileHandleForWriting
        let outputHandle = output.fileHandleForReading

        ioGroup.enter()
        DispatchQueue.global(qos: .userInitiated).async {
            defer {
                try? inputHandle.close()
                ioGroup.leave()
            }
            do {
                try inputHandle.write(contentsOf: payload)
            } catch {
                ioState.markRequestWriteFailed()
            }
        }

        ioGroup.enter()
        DispatchQueue.global(qos: .userInitiated).async {
            defer { ioGroup.leave() }
            do {
                while let chunk = try outputHandle.read(
                    upToCount: responseReadChunkBytes
                ), !chunk.isEmpty {
                    ioState.appendResponse(
                        chunk,
                        limit: maximumResponseBytes
                    )
                }
            } catch {
                ioState.markResponseReadFailed()
            }
        }

        let timeoutNanoseconds = UInt64(
            min(
                timeoutSeconds * 1_000_000_000,
                Double(UInt64.max)
            )
        )
        let startedAt = DispatchTime.now().uptimeNanoseconds
        let deadline = startedAt &+ timeoutNanoseconds
        var terminalError: DesktopBridgeError?

        while process.isRunning {
            let status = ioState.status()
            if status.requestWriteFailed {
                terminalError = .writeFailed
                break
            }
            if status.responseTooLarge {
                terminalError = .responseTooLarge
                break
            }
            if currentTaskIsCancelled {
                terminalError = .cancelled
                break
            }
            if DispatchTime.now().uptimeNanoseconds >= deadline {
                terminalError = .timedOut
                break
            }
            Thread.sleep(forTimeInterval: pollIntervalSeconds)
        }

        if terminalError != nil {
            stopAndReap(process)
            try? inputHandle.close()
        }

        let ioDeadline = DispatchTime.now() + ioDrainGraceSeconds
        if ioGroup.wait(timeout: ioDeadline) == .timedOut {
            try? inputHandle.close()
            try? outputHandle.close()
            stopAndReap(process)
            _ = ioGroup.wait(
                timeout: DispatchTime.now() + ioDrainGraceSeconds
            )
            if terminalError == nil {
                terminalError = .invalidResponse
            }
        }

        if let terminalError {
            throw terminalError
        }

        let status = ioState.status()
        if status.requestWriteFailed {
            throw DesktopBridgeError.writeFailed
        }
        if status.responseTooLarge {
            throw DesktopBridgeError.responseTooLarge
        }
        if status.responseReadFailed {
            throw DesktopBridgeError.invalidResponse
        }

        let data = ioState.responseData()
        guard process.terminationStatus == 0 || !data.isEmpty else {
            throw DesktopBridgeError.launchFailed
        }

        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        guard let envelope = try? decoder.decode(
            BridgeEnvelope<Result>.self,
            from: data
        ) else {
            throw DesktopBridgeError.invalidResponse
        }
        guard envelope.id == request.id else {
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

    private static var currentTaskIsCancelled: Bool {
        withUnsafeCurrentTask { task in
            task?.isCancelled ?? false
        }
    }

    private static func stopAndReap(_ process: Process) {
        guard process.isRunning else {
            process.waitUntilExit()
            return
        }

        process.terminate()
        let terminateDeadline =
            DispatchTime.now().uptimeNanoseconds
            &+ UInt64(terminationGraceSeconds * 1_000_000_000)
        while process.isRunning,
              DispatchTime.now().uptimeNanoseconds < terminateDeadline {
            Thread.sleep(forTimeInterval: pollIntervalSeconds)
        }

        if process.isRunning {
            _ = Darwin.kill(process.processIdentifier, SIGKILL)
            let killDeadline =
                DispatchTime.now().uptimeNanoseconds
                &+ UInt64(terminationGraceSeconds * 1_000_000_000)
            while process.isRunning,
                  DispatchTime.now().uptimeNanoseconds < killDeadline {
                Thread.sleep(forTimeInterval: pollIntervalSeconds)
            }
        }

        if !process.isRunning {
            process.waitUntilExit()
        }
    }
}
