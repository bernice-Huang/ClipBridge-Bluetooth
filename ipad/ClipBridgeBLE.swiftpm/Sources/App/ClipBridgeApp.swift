import SwiftUI

@main
struct ClipBridgeApp: App {
    @StateObject private var bridge = BLEBridge()
    var body: some Scene {
        WindowGroup { ContentView(bridge: bridge) }
    }
}
