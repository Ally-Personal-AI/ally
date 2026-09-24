import Foundation

public enum JSONValue: Codable, Sendable, Equatable {
    case string(String)
    case number(Double)
    case bool(Bool)
    case object([String: JSONValue])
    case array([JSONValue])
    case null

    public init(from decoder: Decoder) throws {
        let container = try decoder.singleValueContainer()
        if container.decodeNil() {
            self = .null
        } else if let value = try? container.decode(Bool.self) {
            self = .bool(value)
        } else if let value = try? container.decode(Double.self) {
            self = .number(value)
        } else if let value = try? container.decode(String.self) {
            self = .string(value)
        } else if let value = try? container.decode([String: JSONValue].self) {
            self = .object(value)
        } else if let value = try? container.decode([JSONValue].self) {
            self = .array(value)
        } else {
            throw DecodingError.dataCorruptedError(
                in: container,
                debugDescription: "Unsupported JSON value"
            )
        }
    }

    public func encode(to encoder: Encoder) throws {
        var container = encoder.singleValueContainer()
        switch self {
        case .string(let value):
            try container.encode(value)
        case .number(let value):
            try container.encode(value)
        case .bool(let value):
            try container.encode(value)
        case .object(let value):
            try container.encode(value)
        case .array(let value):
            try container.encode(value)
        case .null:
            try container.encodeNil()
        }
    }
}

public extension JSONValue {
    var displayText: String {
        switch self {
        case .string(let value):
            return value
        case .number(let value):
            return value.formatted()
        case .bool(let value):
            return value ? "true" : "false"
        case .object(let value):
            return value.keys.sorted().map { key in
                "\(key): \(value[key]?.displayText ?? "null")"
            }.joined(separator: "\n")
        case .array(let value):
            return value.map(\.displayText).joined(separator: ", ")
        case .null:
            return "null"
        }
    }
}

public struct BridgeRequest: Encodable, Sendable {
    public let id: String
    public let method: String
    public let params: [String: JSONValue]

    public init(
        id: String = UUID().uuidString,
        method: String,
        params: [String: JSONValue] = [:]
    ) {
        self.id = id
        self.method = method
        self.params = params
    }
}

public struct BridgeFailure: Decodable, Sendable, Equatable {
    public let code: String
    public let message: String
}

public struct BridgeEnvelope<Result: Decodable & Sendable>: Decodable, Sendable {
    public let id: String?
    public let ok: Bool
    public let result: Result?
    public let error: BridgeFailure?
}

public struct BridgeInfo: Decodable, Sendable, Equatable {
    public let protocolVersion: Int
    public let allyVersion: String
    public let transport: String
    public let capabilities: [String]
}

public enum DesktopBridgeError: Error, LocalizedError, Sendable, Equatable {
    case helperNotFound
    case helperNotExecutable
    case launchFailed
    case writeFailed
    case responseTooLarge
    case invalidResponse
    case requestFailed(code: String, message: String)

    public var errorDescription: String? {
        switch self {
        case .helperNotFound:
            return "The Ally desktop bridge helper was not found."
        case .helperNotExecutable:
            return "The configured Ally desktop bridge helper is not executable."
        case .launchFailed:
            return "The Ally desktop bridge helper could not be launched."
        case .writeFailed:
            return "The Ally desktop bridge request could not be written."
        case .responseTooLarge:
            return "The Ally desktop bridge returned an oversized response."
        case .invalidResponse:
            return "The Ally desktop bridge returned an invalid response."
        case .requestFailed(_, let message):
            return message
        }
    }
}
