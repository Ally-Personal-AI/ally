import Foundation
import Testing
@testable import AllyDesktop
@testable import AllyDesktopCore

private enum SyntheticOSFailure: Error, Sendable {
    case failed
}

private actor OSAsyncGate {
    private var isOpen = false
    private var waiters: [CheckedContinuation<Void, Never>] = []

    func wait() async {
        if isOpen { return }
        await withCheckedContinuation { continuation in
            waiters.append(continuation)
        }
    }

    func open() {
        guard !isOpen else { return }
        isOpen = true
        let pending = waiters
        waiters.removeAll()
        for waiter in pending {
            waiter.resume()
        }
    }
}

private actor GatedNotificationAuthorizationClient:
    DesktopNotificationAuthorizing
{
    private let gate: OSAsyncGate
    private let delayedCurrent: DesktopNotificationAuthorizationState
    private let requestResult:
        Result<DesktopNotificationAuthorizationState, SyntheticOSFailure>
    private var currentCalls = 0

    init(
        gate: OSAsyncGate,
        delayedCurrent: DesktopNotificationAuthorizationState,
        requestResult:
            Result<DesktopNotificationAuthorizationState, SyntheticOSFailure>
    ) {
        self.gate = gate
        self.delayedCurrent = delayedCurrent
        self.requestResult = requestResult
    }

    func currentState() async -> DesktopNotificationAuthorizationState {
        currentCalls += 1
        await gate.wait()
        return delayedCurrent
    }

    func requestAuthorization() async throws
        -> DesktopNotificationAuthorizationState
    {
        try requestResult.get()
    }

    func currentCallCount() -> Int {
        currentCalls
    }
}

private struct FakeNotificationAuthorizationClient:
    DesktopNotificationAuthorizing
{
    let current: DesktopNotificationAuthorizationState
    let requestResult:
        Result<DesktopNotificationAuthorizationState, SyntheticOSFailure>

    func currentState() async -> DesktopNotificationAuthorizationState {
        current
    }

    func requestAuthorization() async throws
        -> DesktopNotificationAuthorizationState
    {
        try requestResult.get()
    }
}

private final class FakeBackgroundServiceClient:
    DesktopBackgroundServiceManaging,
    @unchecked Sendable
{
    private let lock = NSLock()
    private var state: DesktopBackgroundServiceState
    private let registerResult:
        Result<DesktopBackgroundServiceState, SyntheticOSFailure>
    private let unregisterResult:
        Result<DesktopBackgroundServiceState, SyntheticOSFailure>
    private var registerCalls = 0
    private var unregisterCalls = 0

    init(
        state: DesktopBackgroundServiceState,
        registerResult:
            Result<DesktopBackgroundServiceState, SyntheticOSFailure> =
                .success(.enabled),
        unregisterResult:
            Result<DesktopBackgroundServiceState, SyntheticOSFailure> =
                .success(.notRegistered)
    ) {
        self.state = state
        self.registerResult = registerResult
        self.unregisterResult = unregisterResult
    }

    func currentState() -> DesktopBackgroundServiceState {
        lock.withLock { state }
    }

    func register() throws -> DesktopBackgroundServiceState {
        try lock.withLock {
            registerCalls += 1
            let next = try registerResult.get()
            state = next
            return next
        }
    }

    func unregister() throws -> DesktopBackgroundServiceState {
        try lock.withLock {
            unregisterCalls += 1
            let next = try unregisterResult.get()
            state = next
            return next
        }
    }

    func openSystemSettings() {}

    func counts() -> (register: Int, unregister: Int) {
        lock.withLock { (registerCalls, unregisterCalls) }
    }
}

private struct FakeNotificationDeliveryClient:
    DesktopNotificationDelivering
{
    let contextValue: DesktopNotificationDeliveryContext
    let succeeded: Bool

    func context() async -> DesktopNotificationDeliveryContext {
        contextValue
    }

    func deliver(
        _ candidate: DesktopNotificationCandidate,
        context: DesktopNotificationDeliveryContext
    ) async -> DesktopNotificationDeliveryOutcome {
        DesktopNotificationDeliveryOutcome(
            eventId: candidate.eventId,
            deliveryKey: candidate.deliveryKey,
            succeeded: succeeded
        )
    }
}

private struct OSRecordedBridgeCall: Sendable, Equatable {
    let method: String
    let params: [String: JSONValue]
}

private actor GatedLegacyBridgeClient: DesktopBridgeCalling {
    private let gate: OSAsyncGate
    private var recorded: [OSRecordedBridgeCall] = []

    init(gate: OSAsyncGate) {
        self.gate = gate
    }

    func call<Result: Decodable & Sendable>(
        _ method: String,
        params: [String: JSONValue],
        as resultType: Result.Type
    ) async throws -> Result {
        recorded.append(
            OSRecordedBridgeCall(method: method, params: params)
        )
        guard method == "service.legacy_status" else {
            throw DesktopBridgeError.requestFailed(
                code: "unexpected_synthetic_call",
                message: "Unexpected synthetic bridge call."
            )
        }
        await gate.wait()
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        return try decoder.decode(
            Result.self,
            from: Data(osLegacyCleanJSON.utf8)
        )
    }

    func calls() -> [OSRecordedBridgeCall] {
        recorded
    }
}

private actor OSFakeBridgeClient: DesktopBridgeCalling {
    private var replies: [String: [String]]
    private var recorded: [OSRecordedBridgeCall] = []

    init(replies: [String: [String]]) {
        self.replies = replies
    }

    func call<Result: Decodable & Sendable>(
        _ method: String,
        params: [String: JSONValue],
        as resultType: Result.Type
    ) async throws -> Result {
        recorded.append(
            OSRecordedBridgeCall(method: method, params: params)
        )
        guard var queue = replies[method], !queue.isEmpty else {
            throw DesktopBridgeError.requestFailed(
                code: "missing_fake_reply",
                message: "Synthetic OS bridge reply is missing."
            )
        }
        let payload = queue.removeFirst()
        replies[method] = queue
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        return try decoder.decode(
            Result.self,
            from: Data(payload.utf8)
        )
    }

    func calls() -> [OSRecordedBridgeCall] {
        recorded
    }
}

private func waitForAuthorizationRead(
    _ client: GatedNotificationAuthorizationClient
) async {
    for _ in 0..<2_000 {
        if await client.currentCallCount() > 0 {
            return
        }
        await Task.yield()
    }
    Issue.record("Timed out waiting for synthetic authorization read.")
}

private func waitForLegacyStatusCall(
    _ bridge: GatedLegacyBridgeClient
) async {
    for _ in 0..<2_000 {
        if await bridge.calls().contains(where: {
            $0.method == "service.legacy_status"
        }) {
            return
        }
        await Task.yield()
    }
    Issue.record("Timed out waiting for synthetic legacy-service read.")
}

private let osLegacyCleanJSON =
    #"{"supported":true,"configured":false,"definition_state":"absent","loaded":false,"running":false,"label":"ai.ally.proactive-service","can_retire":false}"#

private let osLegacyConfiguredJSON =
    #"{"supported":true,"configured":true,"definition_state":"recognized_legacy","loaded":true,"running":false,"label":"ai.ally.proactive-service","can_retire":true}"#

private let osPreparedCycleJSON =
    #"{"run":{"id":"00000000-0000-0000-0000-000000000070","status":"running","observed_at":"2026-09-26T00:00:00Z","started_at":"2026-09-26T00:00:00Z","finished_at":null,"scheduled_events":1,"delivery_attempts":0,"delivery_failures":0,"error_class":null},"candidates":[{"event_id":"00000000-0000-0000-0000-000000000071","delivery_key":"attention:macos.notification:00000000-0000-0000-0000-000000000071","title":"Ally","body":"Synthetic reminder.","attention":"notify","created_at":"2026-09-26T00:00:00Z"}]}"#

private let osDeliverySuccessJSON =
    #"{"id":"00000000-0000-0000-0000-000000000072","event_id":"00000000-0000-0000-0000-000000000071","sink_id":"macos.notification","status":"succeeded","attempts":1,"last_error":null,"created_at":"2026-09-26T00:00:00Z","updated_at":"2026-09-26T00:00:01Z","delivered_at":"2026-09-26T00:00:01Z"}"#

private let osDeliveryFailureJSON =
    #"{"id":"00000000-0000-0000-0000-000000000072","event_id":"00000000-0000-0000-0000-000000000071","sink_id":"macos.notification","status":"failed","attempts":1,"last_error":"SyntheticDeliveryFailure","created_at":"2026-09-26T00:00:00Z","updated_at":"2026-09-26T00:00:01Z","delivered_at":null}"#

private let osCompletedCycleJSON =
    #"{"id":"00000000-0000-0000-0000-000000000070","status":"succeeded","observed_at":"2026-09-26T00:00:00Z","started_at":"2026-09-26T00:00:00Z","finished_at":"2026-09-26T00:00:02Z","scheduled_events":1,"delivery_attempts":1,"delivery_failures":0,"error_class":null}"#

private let osDegradedCycleJSON =
    #"{"id":"00000000-0000-0000-0000-000000000070","status":"degraded","observed_at":"2026-09-26T00:00:00Z","started_at":"2026-09-26T00:00:00Z","finished_at":"2026-09-26T00:00:02Z","scheduled_events":1,"delivery_attempts":1,"delivery_failures":1,"error_class":"SyntheticDeliveryFailure"}"#

private let osBootstrapJSON =
    #"{"runtime":{"state":"unavailable","target":null,"error_code":"active_profile_unavailable"},"conversations":{"state":"available","items":[],"error_code":null},"tasks":{"state":"available","items":[],"error_code":null},"pending_attention":{"state":"available","items":[],"error_code":null},"attention_history":{"state":"available","items":[],"error_code":null},"service_history":{"state":"available","items":[],"error_code":null},"service_health":{"state":"available","report":{"status":"healthy","checks":[]},"error_code":null}}"#

private let osAttentionEventsJSON = #"[]"#
private let osAttentionHistoryJSON = #"[]"#

@MainActor
@Test func notificationAuthorizationRefreshUsesInjectedOSState() async {
    let bridge = OSFakeBridgeClient(replies: [:])
    let authorization = FakeNotificationAuthorizationClient(
        current: .provisional,
        requestResult: .success(.provisional)
    )
    let model = AppModel(
        client: bridge,
        notificationAuthorizationClient: authorization
    )

    await model.refreshNotificationAuthorization()

    #expect(model.notificationAuthorization == .provisional)
}

@MainActor
@Test func notificationAuthorizationFailureIsSanitized() async {
    let bridge = OSFakeBridgeClient(replies: [:])
    let authorization = FakeNotificationAuthorizationClient(
        current: .notDetermined,
        requestResult: .failure(.failed)
    )
    let model = AppModel(
        client: bridge,
        notificationAuthorizationClient: authorization
    )

    await model.requestNotificationAuthorization()

    #expect(model.notificationAuthorization == .unknown)
    #expect(
        model.errorMessage
            == "Notification authorization request failed."
    )
    #expect(model.isBusy == false)
}

@MainActor
@Test func backgroundEnableStopsAtConfiguredLegacyService() async {
    let bridge = OSFakeBridgeClient(
        replies: ["service.legacy_status": [osLegacyConfiguredJSON]]
    )
    let background = FakeBackgroundServiceClient(state: .notRegistered)
    let model = AppModel(
        client: bridge,
        backgroundServiceClient: background
    )

    await model.enableBackgroundService()

    #expect(background.counts().register == 0)
    #expect(model.backgroundServiceState == .unknown)
    #expect(
        model.errorMessage
            == "Retire the legacy Ally background service before enabling the signed app login item."
    )
}

@MainActor
@Test func cleanLegacyStateAllowsBackgroundRegistration() async {
    let bridge = OSFakeBridgeClient(
        replies: ["service.legacy_status": [osLegacyCleanJSON]]
    )
    let background = FakeBackgroundServiceClient(
        state: .notRegistered,
        registerResult: .success(.requiresApproval)
    )
    let model = AppModel(
        client: bridge,
        backgroundServiceClient: background
    )

    await model.enableBackgroundService()

    #expect(background.counts().register == 1)
    #expect(model.backgroundServiceState == .requiresApproval)
    #expect(model.errorMessage == nil)
}

@MainActor
@Test func backgroundUnregisterFailureRefreshesObservedState() {
    let bridge = OSFakeBridgeClient(replies: [:])
    let background = FakeBackgroundServiceClient(
        state: .enabled,
        unregisterResult: .failure(.failed)
    )
    let model = AppModel(
        client: bridge,
        backgroundServiceClient: background
    )

    model.disableBackgroundService()

    #expect(background.counts().unregister == 1)
    #expect(model.backgroundServiceState == .enabled)
    #expect(
        model.errorMessage
            == "Background proactivity could not be disabled."
    )
}

@MainActor
@Test func disabledBackgroundStateSkipsProactiveBridgeWork() async {
    let bridge = OSFakeBridgeClient(replies: [:])
    let background = FakeBackgroundServiceClient(state: .notRegistered)
    let model = AppModel(
        client: bridge,
        backgroundServiceClient: background
    )

    await model.runProactiveCycleIfEnabled()

    #expect(await bridge.calls().isEmpty)
    #expect(model.backgroundServiceState == .notRegistered)
}

@MainActor
@Test func successfulProactiveDeliveryAcknowledgesExactCandidate() async {
    let bridge = OSFakeBridgeClient(
        replies: [
            "service.legacy_status": [osLegacyCleanJSON],
            "service.prepare_proactive": [osPreparedCycleJSON],
            "attention.notification_result": [osDeliverySuccessJSON],
            "service.complete_proactive": [osCompletedCycleJSON],
            "bootstrap": [osBootstrapJSON],
            "attention.events": [osAttentionEventsJSON],
            "attention.delivery_history": [osAttentionHistoryJSON],
        ]
    )
    let background = FakeBackgroundServiceClient(state: .enabled)
    let delivery = FakeNotificationDeliveryClient(
        contextValue: DesktopNotificationDeliveryContext(
            canDeliver: true,
            knownIdentifiers: []
        ),
        succeeded: true
    )
    let model = AppModel(
        client: bridge,
        backgroundServiceClient: background,
        notificationDeliveryClient: delivery
    )

    await model.runProactiveCycleIfEnabled()

    let calls = await bridge.calls()
    let acknowledgement = try? #require(
        calls.first {
            $0.method == "attention.notification_result"
        }
    )
    #expect(
        acknowledgement?.params["event_id"]
            == .string(
                "00000000-0000-0000-0000-000000000071"
            )
    )
    #expect(
        acknowledgement?.params["delivery_key"]
            == .string(
                "attention:macos.notification:00000000-0000-0000-0000-000000000071"
            )
    )
    #expect(acknowledgement?.params["succeeded"] == .bool(true))
    #expect(
        calls.contains { $0.method == "service.complete_proactive" }
    )
    #expect(model.proactiveCycleError == nil)
    #expect(model.lastProactiveCycleAt != nil)
}

@MainActor
@Test func failedProactiveDeliverySurfacesDegradedCycle() async {
    let bridge = OSFakeBridgeClient(
        replies: [
            "service.legacy_status": [osLegacyCleanJSON],
            "service.prepare_proactive": [osPreparedCycleJSON],
            "attention.notification_result": [osDeliveryFailureJSON],
            "service.complete_proactive": [osDegradedCycleJSON],
            "bootstrap": [osBootstrapJSON],
            "attention.events": [osAttentionEventsJSON],
            "attention.delivery_history": [osAttentionHistoryJSON],
        ]
    )
    let background = FakeBackgroundServiceClient(state: .enabled)
    let delivery = FakeNotificationDeliveryClient(
        contextValue: DesktopNotificationDeliveryContext(
            canDeliver: false,
            knownIdentifiers: []
        ),
        succeeded: false
    )
    let model = AppModel(
        client: bridge,
        backgroundServiceClient: background,
        notificationDeliveryClient: delivery
    )

    await model.runProactiveCycleIfEnabled()

    let acknowledgement = await bridge.calls().first {
        $0.method == "attention.notification_result"
    }
    #expect(acknowledgement?.params["succeeded"] == .bool(false))
    #expect(
        model.proactiveCycleError
            == "The proactive cycle completed with notification delivery failures."
    )
    #expect(model.lastProactiveCycleAt != nil)
}
 
@MainActor
@Test func staleAuthorizationRefreshCannotOverwriteNewerRequest() async {
    let gate = OSAsyncGate()
    let authorization = GatedNotificationAuthorizationClient(
        gate: gate,
        delayedCurrent: .notDetermined,
        requestResult: .success(.authorized)
    )
    let bridge = OSFakeBridgeClient(replies: [:])
    let background = FakeBackgroundServiceClient(state: .notRegistered)
    let model = AppModel(
        client: bridge,
        notificationAuthorizationClient: authorization,
        backgroundServiceClient: background
    )

    let refreshTask = Task {
        await model.refreshNotificationAuthorization()
    }
    await waitForAuthorizationRead(authorization)

    await model.requestNotificationAuthorization()
    #expect(model.notificationAuthorization == .authorized)

    await gate.open()
    await refreshTask.value

    #expect(model.notificationAuthorization == .authorized)
    #expect(model.errorMessage == nil)
}

@MainActor
@Test func disableInvalidatesInFlightBackgroundEnable() async {
    let gate = OSAsyncGate()
    let bridge = GatedLegacyBridgeClient(gate: gate)
    let background = FakeBackgroundServiceClient(state: .enabled)
    let model = AppModel(
        client: bridge,
        backgroundServiceClient: background
    )

    let enableTask = Task {
        await model.enableBackgroundService()
    }
    await waitForLegacyStatusCall(bridge)
    #expect(model.isBusy)

    model.disableBackgroundService()
    #expect(model.backgroundServiceState == .notRegistered)

    await gate.open()
    await enableTask.value

    let counts = background.counts()
    #expect(counts.unregister == 1)
    #expect(counts.register == 0)
    #expect(model.backgroundServiceState == .notRegistered)
    #expect(model.isBusy == false)
}

@MainActor
@Test func proactivePreflightStopsAfterBackgroundDisable() async {
    let gate = OSAsyncGate()
    let bridge = GatedLegacyBridgeClient(gate: gate)
    let background = FakeBackgroundServiceClient(state: .enabled)
    let model = AppModel(
        client: bridge,
        backgroundServiceClient: background
    )

    let cycleTask = Task {
        await model.runProactiveCycleIfEnabled()
    }
    await waitForLegacyStatusCall(bridge)

    model.disableBackgroundService()
    await gate.open()
    await cycleTask.value

    let calls = await bridge.calls()
    #expect(
        calls.filter { $0.method == "service.legacy_status" }.count == 1
    )
    #expect(
        calls.contains { $0.method == "service.prepare_proactive" } == false
    )
    #expect(model.backgroundServiceState == .notRegistered)
}

