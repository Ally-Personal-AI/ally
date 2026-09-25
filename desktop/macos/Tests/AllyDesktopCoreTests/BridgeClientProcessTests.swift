import Foundation
import Testing
@testable import AllyDesktopCore

private func makeBridgeHelper(
    _ body: String
) throws -> (root: URL, helper: URL) {
    let root = FileManager.default.temporaryDirectory
        .appendingPathComponent(UUID().uuidString, isDirectory: true)
    try FileManager.default.createDirectory(
        at: root,
        withIntermediateDirectories: true
    )
    let helper = root.appendingPathComponent("synthetic-bridge-helper")
    let script = """
    #!/bin/sh
    set -eu
    \(body)
    """
    try Data(script.utf8).write(to: helper)
    try FileManager.default.setAttributes(
        [.posixPermissions: 0o755],
        ofItemAtPath: helper.path
    )
    return (root, helper)
}

private func expectBridgeError<T>(
    _ expected: DesktopBridgeError,
    operation: () throws -> T
) {
    do {
        _ = try operation()
        Issue.record("Expected bridge error \(expected)")
    } catch let error as DesktopBridgeError {
        #expect(error == expected)
    } catch {
        Issue.record("Unexpected error type: \(error)")
    }
}

@Test func bridgeClientAcceptsExactCorrelatedResponse() throws {
    let fixture = try makeBridgeHelper(
        """
        cat >/dev/null
        printf '%s\n' '{"id":"synthetic","ok":true,"result":"bridge-ok"}'
        """
    )
    defer { try? FileManager.default.removeItem(at: fixture.root) }

    let result: String = try DesktopBridgeClient.callSynchronously(
        executableURL: fixture.helper,
        method: "synthetic",
        params: [:],
        as: String.self,
        timeoutSeconds: 1,
        requestID: "synthetic"
    )

    #expect(result == "bridge-ok")
}

@Test func bridgeClientRejectsMismatchedResponseID() throws {
    let fixture = try makeBridgeHelper(
        """
        cat >/dev/null
        printf '%s\n' '{"id":"wrong","ok":true,"result":"bridge-ok"}'
        """
    )
    defer { try? FileManager.default.removeItem(at: fixture.root) }

    expectBridgeError(.invalidResponse) {
        let _: String = try DesktopBridgeClient.callSynchronously(
            executableURL: fixture.helper,
            method: "synthetic",
            params: [:],
            as: String.self,
            timeoutSeconds: 1,
            requestID: "synthetic"
        )
    }
}

@Test func bridgeClientRejectsMalformedResponse() throws {
    let fixture = try makeBridgeHelper(
        """
        cat >/dev/null
        printf 'not-json\n'
        """
    )
    defer { try? FileManager.default.removeItem(at: fixture.root) }

    expectBridgeError(.invalidResponse) {
        let _: String = try DesktopBridgeClient.callSynchronously(
            executableURL: fixture.helper,
            method: "synthetic",
            params: [:],
            as: String.self,
            timeoutSeconds: 1,
            requestID: "synthetic"
        )
    }
}

@Test func bridgeClientRejectsEmptyFailedHelper() throws {
    let fixture = try makeBridgeHelper(
        """
        cat >/dev/null
        exit 7
        """
    )
    defer { try? FileManager.default.removeItem(at: fixture.root) }

    expectBridgeError(.launchFailed) {
        let _: String = try DesktopBridgeClient.callSynchronously(
            executableURL: fixture.helper,
            method: "synthetic",
            params: [:],
            as: String.self,
            timeoutSeconds: 1,
            requestID: "synthetic"
        )
    }
}

@Test func bridgeClientTimesOutAndReapsHungHelper() throws {
    let fixture = try makeBridgeHelper(
        """
        cat >/dev/null
        sleep 10
        """
    )
    defer { try? FileManager.default.removeItem(at: fixture.root) }
    let started = Date()

    expectBridgeError(.timedOut) {
        let _: String = try DesktopBridgeClient.callSynchronously(
            executableURL: fixture.helper,
            method: "synthetic",
            params: [:],
            as: String.self,
            timeoutSeconds: 0.1,
            requestID: "synthetic"
        )
    }

    #expect(Date().timeIntervalSince(started) < 3)
}

@Test func bridgeClientTimeoutAlsoBoundsBlockedRequestWrite() throws {
    let fixture = try makeBridgeHelper(
        """
        sleep 10
        """
    )
    defer { try? FileManager.default.removeItem(at: fixture.root) }
    let started = Date()
    let largeRequest = String(repeating: "x", count: 512 * 1024)

    expectBridgeError(.timedOut) {
        let _: String = try DesktopBridgeClient.callSynchronously(
            executableURL: fixture.helper,
            method: "synthetic",
            params: ["payload": .string(largeRequest)],
            as: String.self,
            timeoutSeconds: 0.1,
            requestID: "synthetic"
        )
    }

    #expect(Date().timeIntervalSince(started) < 3)
}

@Test func bridgeClientStopsOversizedStreamingResponse() throws {
    let fixture = try makeBridgeHelper(
        """
        cat >/dev/null
        dd if=/dev/zero bs=1048576 count=3 2>/dev/null
        sleep 10
        """
    )
    defer { try? FileManager.default.removeItem(at: fixture.root) }
    let started = Date()

    expectBridgeError(.responseTooLarge) {
        let _: String = try DesktopBridgeClient.callSynchronously(
            executableURL: fixture.helper,
            method: "synthetic",
            params: [:],
            as: String.self,
            timeoutSeconds: 5,
            requestID: "synthetic"
        )
    }

    #expect(Date().timeIntervalSince(started) < 3)
}

@Test func bridgeClientDoesNotDeadlockOnLargeStderr() throws {
    let fixture = try makeBridgeHelper(
        """
        cat >/dev/null
        dd if=/dev/zero bs=1048576 count=4 1>&2 2>/dev/null
        printf '%s\n' '{"id":"synthetic","ok":true,"result":"bridge-ok"}'
        """
    )
    defer { try? FileManager.default.removeItem(at: fixture.root) }

    let result: String = try DesktopBridgeClient.callSynchronously(
        executableURL: fixture.helper,
        method: "synthetic",
        params: [:],
        as: String.self,
        timeoutSeconds: 1,
        requestID: "synthetic"
    )

    #expect(result == "bridge-ok")
}

@Test func bridgeClientCancellationStopsHungHelper() async throws {
    let fixture = try makeBridgeHelper(
        """
        cat >/dev/null
        sleep 10
        """
    )
    defer { try? FileManager.default.removeItem(at: fixture.root) }
    let client = try DesktopBridgeClient(executableURL: fixture.helper)
    let task = Task { () throws -> String in
        try await client.call("synthetic")
    }

    try await Task.sleep(for: .milliseconds(100))
    task.cancel()

    do {
        _ = try await task.value
        Issue.record("Expected cancelled bridge request")
    } catch let error as DesktopBridgeError {
        #expect(error == .cancelled)
    } catch {
        Issue.record("Unexpected error type: (error)")
    }
}
