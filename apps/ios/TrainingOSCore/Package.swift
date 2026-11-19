// swift-tools-version: 6.0

import PackageDescription

let package = Package(
    name: "TrainingOSCore",
    platforms: [
        .iOS(.v17),
        .macOS(.v14),
    ],
    products: [
        .library(name: "TrainingOSCore", targets: ["TrainingOSCore"]),
    ],
    targets: [
        .target(name: "TrainingOSCore"),
        .testTarget(name: "TrainingOSCoreTests", dependencies: ["TrainingOSCore"]),
    ]
)
