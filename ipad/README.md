# iPad 源码导读

这里是 Swift Playgrounds 工程源码，**不是 IPA 安装包**。使用方法见 [iPad 安装说明](../docs/user/ipad-setup.md)。

```text
ClipBridgeBLE.swiftpm/
├── Package.swift             # iPad App 清单，编译 Sources 下的源码
├── Info.plist                # 蓝牙用途说明与后台模式配置
└── Sources/
    ├── App/
    │   ├── ClipBridgeApp.swift  # 唯一 @main 入口和接收器状态对象
    │   └── ContentView.swift    # SwiftUI：配对输入、状态、预览、复制按钮
    ├── Bluetooth/
    │   └── BLEBridge.swift      # 连接、发现、认证、重组、解密及剪贴板写入
    ├── Protocol/
    │   ├── Wire.swift          # UUID、限额、二进制读写与十六进制解码
    │   └── WireSelfTest.swift  # Python/CryptoKit 合成互操作向量
    └── Storage/
        └── PairingKey.swift    # 钥匙串读取/保存；不写图片或文字文件
```

建议依次看 [App 入口](ClipBridgeBLE.swiftpm/Sources/App/ClipBridgeApp.swift)、[界面](ClipBridgeBLE.swiftpm/Sources/App/ContentView.swift)、[蓝牙接收器](ClipBridgeBLE.swiftpm/Sources/Bluetooth/BLEBridge.swift)，最后对照[协议常量](ClipBridgeBLE.swiftpm/Sources/Protocol/Wire.swift)与 [Windows 发送协议](../windows/ble/protocol.py)。

CoreBluetooth 回调沿用主队列。`BLEBridge` 内的 `MARK` 按连接、发现、认证、收包和剪贴板输出分组；协议、自测和钥匙串代码不再混在接收器中。

这次仅拆分文件、明确模块职责，不修改 UUID、密钥服务名、加密格式或剪贴板过期策略。新增文件须完整保留在工程的 `Sources` 目录内，不要只复制 `BLEBridge.swift` 一个文件。

Windows 上只能做文本结构和互操作向量检查，**不能替代 iPad 编译、前台/后台粘贴实测**。不要为了验证源码结构改动而覆盖现有工程；若要试运行新源码，请先保留原工程作为备份。
