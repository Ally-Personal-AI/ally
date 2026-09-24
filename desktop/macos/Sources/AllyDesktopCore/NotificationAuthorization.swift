import Foundation
import UserNotifications

public enum DesktopNotificationAuthorizationState: String, Sendable, Equatable {
    case authorized
    case denied
    case notDetermined
    case provisional
    case unknown

    public var canRequestAuthorization: Bool {
        self == .notDetermined
    }

    public var canPresentNotifications: Bool {
        self == .authorized || self == .provisional
    }
}

public enum DesktopNotificationAuthorizationError: Error, Sendable {
    case requestFailed
}

public struct DesktopNotificationAuthorizationClient: Sendable {
    public init() {}

    public static func state(
        for status: UNAuthorizationStatus
    ) -> DesktopNotificationAuthorizationState {
        switch status {
        case .authorized:
            return .authorized
        case .denied:
            return .denied
        case .notDetermined:
            return .notDetermined
        case .provisional:
            return .provisional
        @unknown default:
            return .unknown
        }
    }

    public func currentState() async -> DesktopNotificationAuthorizationState {
        await withCheckedContinuation { continuation in
            UNUserNotificationCenter.current().getNotificationSettings { settings in
                continuation.resume(
                    returning: Self.state(for: settings.authorizationStatus)
                )
            }
        }
    }

    public func requestAuthorization() async throws -> DesktopNotificationAuthorizationState {
        try await withCheckedThrowingContinuation {
            (continuation: CheckedContinuation<Void, Error>) in
            UNUserNotificationCenter.current().requestAuthorization(
                options: [.alert, .sound]
            ) { _, error in
                if error != nil {
                    continuation.resume(
                        throwing: DesktopNotificationAuthorizationError.requestFailed
                    )
                } else {
                    continuation.resume(returning: ())
                }
            }
        }
        return await currentState()
    }
}
