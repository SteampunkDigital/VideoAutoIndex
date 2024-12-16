// swift-tools-version:5.9
import PackageDescription

let package = Package(
    name: "VideoAutoIndexApp",
    platforms: [
        .macOS(.v13)
    ],
    products: [
        .executable(name: "VideoAutoIndexApp", targets: ["VideoAutoIndexApp"])
    ],
    dependencies: [],
    targets: [
        .executableTarget(
            name: "VideoAutoIndexApp",
            dependencies: [],
            path: "VideoAutoIndexApp",
            resources: [
                .process("Info.plist")
            ]
        )
    ]
)
