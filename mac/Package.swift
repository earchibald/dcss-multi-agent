// swift-tools-version:5.10
import PackageDescription

let package = Package(
    name: "Ladder",
    platforms: [.macOS(.v14)],
    targets: [.executableTarget(name: "Ladder", path: "Sources/Ladder")]
)
