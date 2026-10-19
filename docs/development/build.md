# 开发与构建

只想使用程序，请回到[首页](../../README.md)下载发布包；以下是给修改源码、调试或自己构建的开发者的说明。

## 仓库布局

```text
ClipBridge-Bluetooth/
├── README.md                 # 使用者入口
├── CHANGELOG.md              # 版本记录
├── Install-Desktop.ps1       # 发布包/本地构建的桌面安装脚本
├── requirements*.txt         # 运行和构建依赖
├── docs/
│   ├── user/                 # 安装、日常使用、升级和排错
│   └── development/          # 本指南、协议、测试和许可
├── windows/                  # Windows 发送端，含 launcher.py
├── ipad/                     # Swift Playgrounds 接收工程
├── scripts/                  # 环境、构建、调试启动及打包
├── tests/                    # 合成数据自动测试
└── third_party/              # 上游许可原文
```

`.venv/`、`dist/`、`build/`、`release/`、`exports/` 和本机配对配置是本地生成数据，不提交。主目录中的 `LICENSE` 是本项目许可证。

## 环境与测试

需要 Windows 11、Python 3.12 x64。以下命令都从**仓库根目录**运行：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\Setup.ps1
.\.venv\Scripts\python.exe -X utf8 -m unittest discover -s tests -v
.\.venv\Scripts\python.exe -m pip check
```

Setup 会安装运行依赖并短暂创建 BLE 诊断广播；运行前请退出发送端。单元测试使用合成数据，安装测试在临时目录中运行，不修改真实启动项。详见[测试与兼容性](testing.md)。

## 运行与构建

源码托盘入口：

```powershell
.\.venv\Scripts\python.exe -X utf8 windows\launcher.py
```

命令行诊断入口为 `scripts/Start-ClipBridge-BLE.cmd`；逐包兼容入口为 `scripts/Start-ClipBridge-BLE-Compatible.cmd`。这些入口不能和已安装桌面版同时运行。

构建单文件 EXE：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\Build-Desktop.ps1
```

结果为 `dist/ClipBridgeBLE.exe`，spec 位于 `scripts/ClipBridgeBLE.spec`。构建脚本先执行测试，失败时不继续构建。没有 Apple SDK 的 Windows 环境不能编译或验收 iPad 接收端，必须在 iPad 的 Playgrounds 中验证。

## 打包与隐私审计

```powershell
.\.venv\Scripts\python.exe -X utf8 scripts\package_release.py --audit-only
.\.venv\Scripts\python.exe -X utf8 scripts\package_release.py
```

输出 Windows ZIP、iPad 工程 ZIP、源码 ZIP 和 SHA-256 校验值到 `release/v<版本>/`，只打包白名单文件，不自动上传 GitHub。首次需要先完成 EXE 构建；发布前还要测试实际设备。

为避免覆盖本地发布包，可在验证目录中试打包：

```powershell
.\.venv\Scripts\python.exe -X utf8 scripts\package_release.py --output-dir exports\package-check
```

正式提交前先仅暂存白名单文件，再用 `--audit-index --audit-only` 检查索引与白名单一致。可用重复的 `--private-config <本机session.json路径>` 检查真实密钥是否意外混入；不要把密钥值写在命令行或提交到仓库。

文档与开发入口已经整理到 `docs/`、`scripts/`，旧发布标签和下载包保持原布局。不要为了更新文档重写已有发布标签、二进制或校验文件。

## 技术与参考

- [协议与文字协商](protocol.md)
- [第三方许可与依赖替换](third-party.md)
- [Microsoft GATT server](https://learn.microsoft.com/en-us/windows/apps/develop/devices-sensors/gatt-server)
- [Windows 剪贴板读取](https://learn.microsoft.com/en-us/windows/win32/api/winuser/nf-winuser-getclipboarddata)
- [BLE peripheral 能力检测](https://learn.microsoft.com/en-us/uwp/api/windows.devices.bluetooth.bluetoothadapter.isperipheralrolesupported)
- [Apple UIPasteboard 写入](https://developer.apple.com/documentation/uikit/uipasteboard/setitems(_:options:))
- [Apple Playgrounds 能力](https://developer.apple.com/documentation/swift-playgrounds/project-capabilities)
- [Apple Core Bluetooth 后台说明](https://developer.apple.com/library/archive/documentation/NetworkingInternetWeb/Conceptual/CoreBluetooth_concepts/CoreBluetoothBackgroundProcessingForIOSApps/PerformingTasksWhileYourAppIsInTheBackground.html)
