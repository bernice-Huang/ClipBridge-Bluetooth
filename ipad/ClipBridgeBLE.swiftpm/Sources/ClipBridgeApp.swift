import SwiftUI

@main
struct ClipBridgeApp: App {
    @StateObject private var bridge = BLEBridge()
    var body: some Scene {
        WindowGroup { ContentView(bridge: bridge) }
    }
}

struct ContentView: View {
    @ObservedObject var bridge: BLEBridge
    var body: some View {
        NavigationStack {
            ScrollView {
                VStack(alignment: .leading, spacing: 18) {
                    Text("蓝牙可行性原型 · 不是已验收的后台应用")
                        .font(.headline).foregroundStyle(.orange)
                    Text("先验证前台接收，再切到 Goodnotes 测试后台。‘尝试写入剪贴板’不等于粘贴成功；是否可用需要你实际粘贴确认。")
                    TextField("Dell 窗口中的 32 位配对密钥", text: $bridge.keyText)
                        .textInputAutocapitalization(.never).autocorrectionDisabled()
                        .font(.system(.body, design: .monospaced))
                        .textFieldStyle(.roundedBorder)
                    HStack {
                        Button("连接 Dell") { bridge.connect() }.buttonStyle(.borderedProminent)
                        Button("停止") { bridge.stop() }.buttonStyle(.bordered)
                        Button("接收最新截图") { bridge.receiveLatest() }
                            .disabled(!bridge.ready).buttonStyle(.bordered)
                    }
                    LabeledContent("连接", value: bridge.status)
                    LabeledContent("后台模式配置", value: bridge.backgroundConfigured ? "bluetooth-central 已读到（仍需实测）" : "未生效：当前不能验证后台接收")
                        .foregroundStyle(bridge.backgroundConfigured ? Color.primary : Color.red)
                    LabeledContent("最近传输", value: bridge.duration)
                    LabeledContent("完成时运行状态", value: bridge.deliveryState)
                    LabeledContent("剪贴板", value: bridge.clipboardState)
                    ProgressView(value: bridge.progress)
                    if let image = bridge.image {
                        Image(uiImage: image).resizable().scaledToFit().frame(maxHeight: 350)
                        Button("重新复制这张图片（前台）") { bridge.copyLatest() }
                            .buttonStyle(.bordered)
                    }
                    Text("诊断记录（不含图片内容）").font(.headline)
                    ForEach(Array(bridge.events.enumerated()), id: \.offset) { _, event in
                        Text(event).font(.system(.caption, design: .monospaced)).textSelection(.enabled)
                    }
                    Text("本原型不写入相册或图片文件，不使用互联网。配对密钥保存在本机钥匙串。不要强制划掉接收程序；锁屏、系统终止、Playgrounds 的运行容器都可能影响后台能力。")
                        .font(.footnote).foregroundStyle(.secondary)
                }.padding()
            }.navigationTitle("ClipBridge BLE")
        }
    }
}
