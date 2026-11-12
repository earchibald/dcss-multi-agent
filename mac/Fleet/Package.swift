// swift-tools-version:5.10
// ladder-fleet: plays the brain's self-play and evaluation games on other Macs. See README.md.
import PackageDescription

let package = Package(
    name: "LadderFleet",
    platforms: [.macOS(.v14)],
    products: [.executable(name: "ladder-fleet", targets: ["ladder-fleet"])],
    targets: [
        .target(name: "FleetCore", path: "Sources/FleetCore"),
        .executableTarget(name: "ladder-fleet", dependencies: ["FleetCore"], path: "Sources/ladder-fleet"),
        .testTarget(name: "FleetCoreTests", dependencies: ["FleetCore"], path: "Tests/FleetCoreTests"),
    ]
)
