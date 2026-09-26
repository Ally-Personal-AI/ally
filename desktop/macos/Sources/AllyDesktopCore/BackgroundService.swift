import Foundation
import ServiceManagement

public enum DesktopBackgroundServiceState: String, Sendable, Equatable {
    case enabled
    case notRegistered
    case requiresApproval
    case notFound
    case unknown
}

public protocol DesktopBackgroundServiceManaging: Sendable {
    func currentState() -> DesktopBackgroundServiceState
    func register() throws -> DesktopBackgroundServiceState
    func unregister() throws -> DesktopBackgroundServiceState
    func openSystemSettings()
}

public struct DesktopBackgroundServiceClient: DesktopBackgroundServiceManaging, Sendable {
    public init() {}

    public static func state(
        for status: SMAppService.Status
    ) -> DesktopBackgroundServiceState {
        switch status {
        case .enabled:
            return .enabled
        case .notRegistered:
            return .notRegistered
        case .requiresApproval:
            return .requiresApproval
        case .notFound:
            return .notFound
        @unknown default:
            return .unknown
        }
    }

    public func currentState() -> DesktopBackgroundServiceState {
        Self.state(for: SMAppService.mainApp.status)
    }

    public func register() throws -> DesktopBackgroundServiceState {
        try SMAppService.mainApp.register()
        return currentState()
    }

    public func unregister() throws -> DesktopBackgroundServiceState {
        try SMAppService.mainApp.unregister()
        return currentState()
    }

    public func openSystemSettings() {
        SMAppService.openSystemSettingsLoginItems()
    }
}
