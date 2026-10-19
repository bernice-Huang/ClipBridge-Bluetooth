# 源码地图：从哪里开始读、到哪里修改

[开发与构建](build.md) · [协议](protocol.md) · [测试范围](testing.md)

这是源码结构整理，不是新增功能发布。现有软件版本号、已发布标签和下载包不变；普通用户不需要更新。

## 两条主线

Windows 的数据路径：

```text
clipboard.monitor → clipboard.models.Snapshot → ble.sender → ble.protocol/蓝牙
       ↑                                            ↑
       └──────── app.controller 启动和管理 ──────────┘
                         ↑
                    app.desktop 托盘
```

采集线程只产出快照，由事件循环接收；蓝牙认证、流控、发送在专用 asyncio 工作线程；Tk 只通过控制器下发用户操作。暂停/文字开关的 epoch 防止旧采集结果在恢复后误发。

iPad 的数据路径：

```text
App/ContentView → Bluetooth/BLEBridge → Protocol/Wire + CryptoKit → UIPasteboard
                         ↑
                  Storage/PairingKey
```

SwiftUI 负责展示和按钮；蓝牙接收器负责连接与完整性检查后写剪贴板；协议常量、自测向量、钥匙串各有独立文件。CoreBluetooth 主队列与原有后台配置不变。

## 想修改什么，先看哪里

| 修改目的 | Windows 模块 | 相关检查 |
| --- | --- | --- |
| 采集时机、暂停、文字开关 | `clipboard/monitor.py`、`ble/sender.py` 的发布入口 | `test_text_protocol.py`、`test_protocol.py` |
| 文字读取和 Unicode 限额 | `clipboard/text.py`、`ble/protocol.py` | `test_clipboard_text.py`、`test_text_protocol.py` |
| 图片清晰度或压缩 | `clipboard/image_codec.py` | `test_image_codec.py`、`bench_compression.py` |
| 蓝牙认证、ACK、通知队列 | `ble/sender.py`、`ble/protocol.py` | `test_protocol.py`、`test_text_protocol.py` |
| 托盘菜单、状态文案 | `app/desktop.py` | EXE 托盘 smoke；不必修改线协议 |
| 工作线程启动、重试、退出 | `app/controller.py` | `test_desktop_controller.py` |
| 设置、密钥路径、日志 | `app/runtime.py` | `test_runtime.py`、`test_source_boundaries.py` |
| 源码布局、入口和打包 | `scripts/`、`windows/launcher.py`、`windows/console.py` | `test_repository_layout.py`、`test_release.py` |

iPad 中界面改动放在 `App/ContentView.swift`，连接与收包放在 `Bluetooth/BLEBridge.swift`，钥匙串放在 `Storage/PairingKey.swift`。改协议时必须同时核对 Python 与 Swift 两端，并更新合成互操作向量。

## 保持这些边界

- `ble/protocol.py` 只处理协议数据，不导入 UI、图像库或 WinRT。
- `clipboard/` 不启动蓝牙；`app/desktop.py` 不直接运行采集循环。
- 包的 `__init__.py` 不触发设备、磁盘或注册表操作。
- 密钥读取统一由 `app/runtime.py` 负责；源码工程根目录的旧密钥迁移位置仍保持不变，冻结 EXE 不向解压目录写密钥。
- 不把正文、截图、配对密钥写入日志或源码。收到回执只代表一次写剪贴板尝试，不代表真实粘贴成功。

## 阅读和运行

GitHub 上直接打开 `windows/` 或 `ipad/` 会显示对应的源码导读。下载源码后，运行命令仍从仓库根目录执行；托盘入口为 `windows/launcher.py`，命令行入口为 `windows/console.py`。详见[构建步骤](build.md)。
