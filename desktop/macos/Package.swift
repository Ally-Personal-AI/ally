// swift-tools-version: 6.0
import PackageDescription

let package = Package(
    name: "AllyDesktop",
    platforms: [
        .macOS(.v14)
    ],
    products: [
        .library(name: "AllyDesktopCore", targets: ["AllyDesktopCore"]),
        .executable(name: "AllyDesktop", targets: ["AllyDesktop"]),
    ],
    targets: [
        .target(name: "AllyDesktopCore"),
        .executableTarget(
            name: "AllyDesktop",
            dependencies: ["AllyDesktopCore"]
        ),
        .testTarget(
            name: "AllyDesktopCoreTests",
            dependencies: ["AllyDesktopCore"]
        ),
    ]
)
