# ClipBridge Bluetooth

考研党/无纸化福音！笨人日常记文献笔记时喜欢电脑阅读平板记录，苦于无法及时传递想Mark的内容，故而制作此小项目。

* 无需复杂快捷指令设定！
* 无需每次登录更新地址！
* 点对点传输安全性高！
* easy go

Windows → iPad 的实验性蓝牙剪贴板桥接工具。支持把局部截图、图片和纯文本复制到 iPad 笔记应用中。

An experimental Windows-to-iPad image and plain-text clipboard bridge over Bluetooth Low Energy. No shared Wi-Fi, hotspot, IP configuration or cloud relay is needed.

**当前版本：v0.4.0-beta，实验性预发布。** [下载 Windows 程序及 iPad 工程](https://github.com/bernice-Huang/ClipBridge-Bluetooth/releases/tag/v0.4.0-beta)。旧 v0.3.1-beta 发布包仅支持图片。面向单台电脑与单台 iPad 的个人使用。图片后台接收在一套设备上已有用户实测反馈；新增文字功能仍需 iPad 编译与前后台实际粘贴验收，不代表所有环境兼容，也不保证三秒内传完所有内容。

## 功能

- 检测 Windows 剪贴板中的新图片或纯文本，通过 BLE GATT 分片发送。
- 中文、英文、换行、制表符、Emoji 按 UTF-8 同步；不传富文本格式、字体或文件。
- iPad 收齐、解密并校验后，尝试写入本机图片或文字剪贴板，可预览并重新复制最新内容。
- 两端协商文字能力；未更新的 iPad 不接收文字，原有图片协议不变。
- Windows 托盘、状态窗口、暂停、画质切换、重发、兼容模式与可选登录自启动。
- 小图保持原像素；较大截图可适度减少颜色、必要时缩小，优先保持文字可读性。
- 每个用户独立生成配对密钥，挑战认证与 AES-128-GCM 内容加密。
- 图片、文字由程序在内存中处理，不写入相册、内容文件或云端。配置和元数据日志会保存到本机。

它同步的是**剪贴板新图片和新文字**，不只来自截图快捷键。文字同步默认开启；复制密码、验证码或私人文字前，请在托盘暂停捕获或取消“同步文字”。本机配对密钥不会自动当作文字发送，但这不是通用的敏感信息识别器。

## 下载与快速开始

从 [Releases](https://github.com/bernice-Huang/ClipBridge-Bluetooth/releases) 下载：

- `ClipBridgeBLE-v<版本>-windows-x64.zip`：Windows 程序及可选安装脚本。
- `ClipBridgeBLE-v<版本>-ipad.zip`：Swift Playgrounds 源码工程，不是 IPA。文字功能要求两端均为 v0.4.0-beta 或更新兼容版本。
- `SHA256SUMS.txt`：发布包的 SHA-256 校验值。

### Windows

1. 解压 Windows ZIP，双击 `ClipBridgeBLE.exe`。不需要额外安装 Python。
2. 从任务栏右下角托盘右击“显示状态”，等到“等待 iPad 连接”。
3. 点“显示密钥”，将这台电脑自己的 32 位密钥输入到 iPad 接收工程。不要分享密钥。
4. 如希望复制程序到桌面并启用登录自启动，在**解压后的文件夹**打开 PowerShell，运行：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\Install-Desktop.ps1
```

不想启用自启动，加上 `-NoStartup`。脚本只管理本应用的启动项，不启动程序，不修改其他应用、Wi-Fi 或系统蓝牙服务。更新程序前请从旧托盘“退出”；已有密钥会保留。

EXE 是本地未签名构建，Windows 可能提示未知发布者。仅使用你信任的来源并核对校验值，不要关闭系统安全功能。首次运行自动生成密钥；若配置损坏，程序停止启动而不会偷偷换密钥。

### iPad

1. 安装 Apple 的 Swift Playgrounds。
2. 在“文件”App 中解压 iPad ZIP，打开 `ClipBridgeBLE.swiftpm` 并运行。
3. 输入 Windows 显示的密钥，允许蓝牙访问，点“连接 Dell”（现有接收界面的文字；并不限 Dell 品牌）。
4. 先测试前台收到新图、新文字并能粘贴，再切到 Goodnotes 等待至少 60 秒，分别截图、复制文字并直接粘贴测试后台能力。文字应粘到文本框编辑状态中。

已有用户必须更新 iPad 工程才能收文字，密钥不变。见 [文字同步升级说明](文字同步升级说明.md)、[iPad 操作说明](iPad操作说明.md)及[简单使用说明](简单使用说明.md)。

## 环境与兼容性

| 项目 | 当前要求或状态 |
| --- | --- |
| Windows 程序 | Windows 11 x64；其他版本和 Windows ARM 未验证 |
| 蓝牙硬件 | 必须支持 BLE peripheral / GATT server，只有“蓝牙可用”不够 |
| iPad 工程 | 声明 iPadOS 17+；需可运行此工程的 Swift Playgrounds |
| 已有用户实测 | 一台 Windows 11 电脑与 iPad Air M3；前台收图、Goodnotes 前台时后台小图粘贴 |
| 其他品牌电脑、iPad、系统版本 | 待社区验证，不能从单套设备外推 |
| 笔记软件 | Goodnotes 图片粘贴已有用户反馈；新增文字粘贴及其他软件需单独测试 |
| 多人、多设备、Android、Mac、反向同步 | 不在首发范围内 |

没有 Mac 也可以在 iPad 的 Swift Playgrounds 中运行本工程。微信或其他工具只是传输源码 ZIP 的手段，不会把它变成可直接安装的应用。

## 已知限制

- iPad 后台模式、系统内存压力、Playgrounds 容器、锁屏、强制退出均可能影响接收。当前没有系统终止后的蓝牙状态恢复。
- “收到回执 / 尝试写剪贴板”不等于粘贴成功；以目标应用粘出**刚刚的新图或新文字**为准。
- Windows/iPad 重启、电脑休眠或关闭蓝牙后，可能需重新打开接收工程并连接。Windows 自启动不等于 iPad 自启动。
- 传输默认有 20 秒截止时间；PNG 上限 2 MiB、单边 8192 像素、3200 万像素。不保证大图、照片或细节复杂的图片三秒内完成。
- 均衡模式的 32 KiB 是软目标；最多缩小至约 75% 边长。对照片颜色或细小文字有要求时选择原图，传输可能更慢。
- 文字上限为 64 KiB **UTF-8 字节**；超限、空文字及无效 Unicode 不发送，不截断正文。富文本仅发送其纯文本表示；同时含图片和文字时图片优先，文件列表忽略。
- 仅保留最新内容；快速连续复制可能覆盖待发送内容。相邻相同图片去重；再次复制相同文字仍可重新发送。不发送启动前或暂停期间的旧剪贴板内容。
- iPad 剪贴板内容设为本机使用，10 分钟后过期。预览只显示前 2000 字符，重新复制仍为全文。
- “不保存内容”仅描述本项目行为。系统剪贴板历史、截图工具自动保存、操作系统换页及笔记保存不受本项目控制。
- 认证和加密是安全基础，不代表经过独立安全审计。

## 配置与隐私

Windows 配置目录：`%LOCALAPPDATA%\ClipBridgeBLE`。

- `session.json`：本机私密配对密钥，**禁止提交或公开分享**。
- `settings.json`：画质、队列、暂停和 `sync_text` 文字同步开关；暂停会保持到下次运行。
- `app.log`：尺寸、字节数、时间、连接与错误元数据；每份最多 1 MiB，最多三份，不保存图片、文字正文或配对密钥。

iPad 密钥保存在本机钥匙串。更新不会要求所有用户共用某个“默认密钥”。项目不要求 GitHub 账号或互联网才能传图。

## 从源码构建

需要 Windows 11、Python 3.12 x64。以下命令在克隆或解压后的项目目录运行：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\Setup.ps1
.\.venv\Scripts\python.exe -X utf8 -m unittest discover -s tests -v
powershell -NoProfile -ExecutionPolicy Bypass -File .\Build-Desktop.ps1
```

构建结果在 `dist\ClipBridgeBLE.exe`。调试入口 `Start-ClipBridge-BLE.cmd` / `Start-ClipBridge-BLE-Compatible.cmd` 不能与桌面版同时运行。单元测试只使用合成数据；安装测试在临时目录运行且不修改真实自启动。

适配器诊断：

```powershell
.\.venv\Scripts\python.exe -X utf8 windows\diagnose.py --advertise
```

此命令会短暂创建实际 BLE 服务和广播，请先退出发送端。不要同时诊断并发送。

打包发布文件：

```powershell
.\.venv\Scripts\python.exe -X utf8 scripts\package_release.py
```

该脚本在 `release/v<版本>/` 生成白名单包、第三方许可证及校验值；不收集密钥、日志、虚拟环境或历史备份，不自动上传 GitHub。Windows 无 Apple SDK，不能替代 iPad 上的 Swift 编译和实际粘贴验收。

## 项目结构

- `windows/`：剪贴板监听、PNG 编码、BLE 协议、托盘与配置。
- `ipad/ClipBridgeBLE.swiftpm/`：SwiftUI 接收工程。
- `tests/`：协议、编码、配置、安装和桌面线程测试。
- `scripts/`：发布白名单与第三方许可收集。
- `CHANGELOG.md`：版本说明。
- `TESTING.md`：验证方法及已验证范围。
- `THIRD_PARTY.md`：第三方依赖与许可说明。
- `PROTOCOL.md`：图片兼容性、文字格式及能力协商。

## 反馈与贡献

欢迎通过 [Issues](https://github.com/bernice-Huang/ClipBridge-Bluetooth/issues) 反馈系统版本、蓝牙芯片、图片尺寸、是否后台、耗时及能否实际粘贴。不要上传密钥、私人截图或未经检查的配置。

这是一个源于个人笔记需求、采用 AI 辅助开发的实验性项目。首发优先保持已验证的单设备传输路径，不扩展多人选择或跨平台接收。

## 许可证与参考

本项目代码使用 [MIT License](LICENSE)。第三方组件保留各自许可证，MIT 不替代它们。

- [Microsoft GATT server](https://learn.microsoft.com/en-us/windows/apps/develop/devices-sensors/gatt-server)
- [Windows 剪贴板数据读取](https://learn.microsoft.com/en-us/windows/win32/api/winuser/nf-winuser-getclipboarddata)
- [Apple UIPasteboard 写入](https://developer.apple.com/documentation/uikit/uipasteboard/setitems(_:options:))
- [BLE peripheral 能力检测](https://learn.microsoft.com/en-us/uwp/api/windows.devices.bluetooth.bluetoothadapter.isperipheralrolesupported)
- [Apple Playgrounds 能力](https://developer.apple.com/documentation/swift-playgrounds/project-capabilities)
- [Apple Core Bluetooth 后台说明](https://developer.apple.com/library/archive/documentation/NetworkingInternetWeb/Conceptual/CoreBluetooth_concepts/CoreBluetoothBackgroundProcessingForIOSApps/PerformingTasksWhileYourAppIsInTheBackground.html)
