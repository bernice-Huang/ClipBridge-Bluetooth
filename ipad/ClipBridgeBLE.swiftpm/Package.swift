// swift-tools-version: 5.9
import PackageDescription
import AppleProductTypes

let package = Package(
    name: "ClipBridge BLE",
    platforms: [.iOS("17.0")],
    products: [
        .iOSApplication(
            name: "ClipBridge BLE",
            targets: ["AppModule"],
            bundleIdentifier: "local.clipbridge.ble.prototype",
            displayVersion: "0.1",
            bundleVersion: "1",
            supportedDeviceFamilies: [.pad],
            supportedInterfaceOrientations: [.portrait, .landscapeLeft, .landscapeRight],
            additionalInfoPlistContentFilePath: "Info.plist"
        )
    ],
    targets: [.executableTarget(name: "AppModule", path: "Sources")],
    swiftLanguageVersions: [.v5]
)
