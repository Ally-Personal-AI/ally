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

public struct DesktopNotificationDeliveryClient {
    public init() {}

    public static func knownIdentifiers(
        delivered: [UNNotification],
        pending: [UNNotificationRequest]
    ) -> Set<String> {
        Set(delivered.map(\.request.identifier))
            .union(pending.map(\.identifier))
    }

    public func deliver(
        _ candidates: [DesktopNotificationCandidate]
    ) async -> [DesktopNotificationDeliveryOutcome] {
        guard !candidates.isEmpty else { return [] }

        let center = UNUserNotificationCenter.current()
        let settings = await center.notificationSettings()
        guard settings.authorizationStatus == .authorized
                || settings.authorizationStatus == .provisional
        else {
            return []
        }

        let delivered = await center.deliveredNotifications()
        let pending = await center.pendingNotificationRequests()
        var known = Self.knownIdentifiers(
            delivered: delivered,
            pending: pending
        )

        var outcomes: [DesktopNotificationDeliveryOutcome] = []
        outcomes.reserveCapacity(candidates.count)

        for candidate in candidates {
            if known.contains(candidate.deliveryKey) {
                outcomes.append(
                    DesktopNotificationDeliveryOutcome(
                        eventId: candidate.eventId,
                        deliveryKey: candidate.deliveryKey,
                        succeeded: true
                    )
                )
                continue
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
                try await center.add(request)
                known.insert(candidate.deliveryKey)
                outcomes.append(
                    DesktopNotificationDeliveryOutcome(
                        eventId: candidate.eventId,
                        deliveryKey: candidate.deliveryKey,
                        succeeded: true
                    )
                )
            } catch {
                outcomes.append(
                    DesktopNotificationDeliveryOutcome(
                        eventId: candidate.eventId,
                        deliveryKey: candidate.deliveryKey,
                        succeeded: false
                    )
                )
            }
        }

        return outcomes
    }
}
