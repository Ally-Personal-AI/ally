import Foundation
import UserNotifications

public struct DesktopNotificationDeliveryOutcome: Sendable, Equatable {
    public let eventId: String
    public let deliveryKey: String
    public let succeeded: Bool

    public init(eventId: String, deliveryKey: String, succeeded: Bool) {
        self.eventId = eventId
        self.deliveryKey = deliveryKey
        self.succeeded = succeeded
    }
}

public struct DesktopNotificationDeliveryContext: Sendable, Equatable {
    public let canDeliver: Bool
    public let knownIdentifiers: Set<String>

    public init(canDeliver: Bool, knownIdentifiers: Set<String>) {
        self.canDeliver = canDeliver
        self.knownIdentifiers = knownIdentifiers
    }
}

public struct DesktopNotificationDeliveryClient {
    public init() {}

    public static func knownIdentifiers(
        delivered: [UNNotification],
        pending: [UNNotificationRequest]
    ) -> Set<String> {
        Set(delivered.map(\.request.identifier))
            .union(pending.map(\.identifier))
    }

    public func context() async -> DesktopNotificationDeliveryContext {
        let center = UNUserNotificationCenter.current()
        let settings = await center.notificationSettings()
        let canDeliver = settings.authorizationStatus == .authorized
            || settings.authorizationStatus == .provisional
        guard canDeliver else {
            return DesktopNotificationDeliveryContext(
                canDeliver: false,
                knownIdentifiers: []
            )
        }

        async let delivered = center.deliveredNotifications()
        async let pending = center.pendingNotificationRequests()
        return await DesktopNotificationDeliveryContext(
            canDeliver: true,
            knownIdentifiers: Self.knownIdentifiers(
                delivered: delivered,
                pending: pending
            )
        )
    }

    public func deliver(
        _ candidate: DesktopNotificationCandidate,
        context: DesktopNotificationDeliveryContext
    ) async -> DesktopNotificationDeliveryOutcome {
        if context.knownIdentifiers.contains(candidate.deliveryKey) {
            return DesktopNotificationDeliveryOutcome(
                eventId: candidate.eventId,
                deliveryKey: candidate.deliveryKey,
                succeeded: true
            )
        }

        guard context.canDeliver else {
            return DesktopNotificationDeliveryOutcome(
                eventId: candidate.eventId,
                deliveryKey: candidate.deliveryKey,
                succeeded: false
            )
        }

        let content = UNMutableNotificationContent()
        content.title = candidate.title
        content.body = candidate.body
        let request = UNNotificationRequest(
            identifier: candidate.deliveryKey,
            content: content,
            trigger: nil
        )

        do {
            try await UNUserNotificationCenter.current().add(request)
            return DesktopNotificationDeliveryOutcome(
                eventId: candidate.eventId,
                deliveryKey: candidate.deliveryKey,
                succeeded: true
            )
        } catch {
            return DesktopNotificationDeliveryOutcome(
                eventId: candidate.eventId,
                deliveryKey: candidate.deliveryKey,
                succeeded: false
            )
        }
    }
}
