# ClipBridge Bluetooth

把 Windows 电脑上的截图和文字，通过蓝牙送到 iPad 剪贴板，再粘贴到 Goodnotes 或备忘录。

不需要同一 Wi-Fi、热点、IP 地址或云端中转。适合电脑阅读、iPad 记笔记的场景。

**[下载 v0.4.0-beta](https://github.com/bernice-Huang/ClipBridge-Bluetooth/releases/tag/v0.4.0-beta) · [全部版本](https://github.com/bernice-Huang/ClipBridge-Bluetooth/releases) · [使用说明](docs/user/quick-start.md) · [遇到问题](docs/user/troubleshooting.md)**

> 当前是实验性 Beta。图片功能已有单套设备使用反馈；新增文字的 iPad 编译、前后台粘贴仍待实测。不保证所有设备兼容或三秒内完成传输。

## 第一次使用，从这里开始

**只想使用，不用下载整个代码仓库，也不用安装 Git 或 Python。** 打开下载页，在 **Assets** 中下载下面两个文件：

| 在哪台设备使用 | 下载文件 | 用途 |
| --- | --- | --- |
| Windows 电脑 | [Windows 程序 ZIP](https://github.com/bernice-Huang/ClipBridge-Bluetooth/releases/download/v0.4.0-beta/ClipBridgeBLE-v0.4.0-beta-windows-x64.zip) | 解压后运行 `ClipBridgeBLE.exe` |
| iPad | [iPad 工程 ZIP](https://github.com/bernice-Huang/ClipBridge-Bluetooth/releases/download/v0.4.0-beta/ClipBridgeBLE-v0.4.0-beta-ipad.zip) | 解压后用 Swift Playgrounds 打开、运行 |

`source.zip` 和 GitHub 自动生成的 `Source code` 是给开发者的，初次使用无需下载。`SHA256SUMS.txt` 用于[校验下载文件](docs/user/troubleshooting.md)。

### 1. 电脑端

解压 Windows ZIP → 双击 `ClipBridgeBLE.exe` → 右下角托盘右击“显示状态” → “显示密钥”。

需要 **Windows 11 x64**，蓝牙适配器须支持 **BLE peripheral / GATT server**；不是所有能连接蓝牙耳机的电脑都支持。程序未签名，请核对来源，不要关闭系统安全功能。

### 2. iPad 端

安装 Apple 的 **Swift Playgrounds** → 在“文件”中解压 iPad ZIP → 打开 `ClipBridgeBLE.swiftpm` 并运行 → 输入电脑显示的密钥 → 允许蓝牙 → 点“连接 Dell”（不限 Dell 品牌）。

不需要 Mac。**这不是 IPA，也不是双击就能安装的 App**；需在 Playgrounds 中运行。工程声明 iPadOS 17+，其他环境兼容性仍待验证。详细步骤见 [iPad 安装说明](docs/user/ipad-setup.md)。

### 3. 开始复制粘贴

- 图片：电脑 `Win + Shift + S` 截图 → 等待接收 → iPad Goodnotes 粘贴。
- 文字：电脑选中文字 `Ctrl + C` → 等待接收 → 在 iPad 备忘录正文或 Goodnotes 文本框编辑状态中粘贴。

先测试前台，再把接收端留在后台测试。不要划掉 iPad 接收程序；“已尝试写入”不等于粘贴成功，以目标应用粘出刚复制的新内容为准。

## 在哪里找不同版本的文件？

**首页文件列表展示的是 `main` 分支的最新源码，不会为每个版本重复建立文件夹。** 历史版本及其下载文件保存在 [Releases／全部版本](https://github.com/bernice-Huang/ClipBridge-Bluetooth/releases)。

| 已发布版本 | 功能 | 下载入口 |
| --- | --- | --- |
| v0.4.0-beta | 图片＋纯文本同步 | [新版下载](https://github.com/bernice-Huang/ClipBridge-Bluetooth/releases/tag/v0.4.0-beta) |
| v0.3.1-beta | 图片同步 | [历史版下载](https://github.com/bernice-Huang/ClipBridge-Bluetooth/releases/tag/v0.3.1-beta) |

进入对应版本页面，展开 **Assets**，即可看到该版本的 Windows 程序、iPad 工程、源码 ZIP 和校验文件。两端请使用同一版本的发布包；以上两个版本均为实验性 Beta。

需要浏览某个版本的源码或当时的说明文档，可在 [Tags／版本标签](https://github.com/bernice-Huang/ClipBridge-Bluetooth/tags) 中选择对应标签。**目录和说明的整理不一定增加软件版本号，也不会替换已经发布的历史下载包。**

## 已经安装过？

从旧图片版升级到文字版，**Windows 和 iPad 都要更新，密钥不变**。按 [v0.4 升级指南](docs/user/upgrade-v0.4.md) 操作。

希望 Windows 开机自启动？在**解压后的 Windows 发布包**中运行下面命令（可选）：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\Install-Desktop.ps1
```

脚本会把程序复制到桌面并管理本应用的登录启动项；更新前先退出旧托盘。直接运行 EXE 也能使用，无需执行安装脚本。

## 使用前请注意

- 自动同步新图片和新文字；复制密码、验证码或其他敏感内容前，先暂停捕获或关闭托盘中的“同步文字”。
- 仅 Windows → iPad、单台电脑与单台 iPad。文字是纯文本（支持中文、换行和 Emoji），不保留字体排版、不传文件。
- 文字上限 64 KiB UTF-8 字节，图片上限 2 MiB。大图和长文字可能较慢；只保留最新内容，iPad 剪贴板项 10 分钟过期。
- 程序在内存中处理内容，不保存图片或文字正文，不写正文日志。系统剪贴板历史、截图自动保存及笔记保存不受本项目控制。
- 后台接收受 iPadOS 和 Playgrounds 运行容器限制；重启、休眠或断开蓝牙后，可能需要重新连接。

## 想继续了解

| 你想做什么 | 从哪里看 |
| --- | --- |
| 查托盘操作、日常使用 | [使用说明](docs/user/quick-start.md) |
| 在 iPad 导入和运行 | [iPad 安装说明](docs/user/ipad-setup.md) |
| 升级图片＋文字版本 | [升级指南](docs/user/upgrade-v0.4.md) |
| 连接不上、无法粘贴 | [故障排查](docs/user/troubleshooting.md) |
| 修改源码、构建 EXE | [开发指南](docs/development/build.md) |
| 看懂源码、找到要改的模块 | [源码地图](docs/development/source-map.md) |
| 查看全部文档 | [文档目录](docs/README.md) |

普通用户只需要下载发布包；仓库中的 `windows/`、`ipad/` 是源码，`scripts/` 是开发脚本，`tests/` 是自动测试，`docs/` 是说明文档。

## 为什么做这个项目

> 考研党/无纸化福音！笨人日常记文献笔记时喜欢电脑阅读平板记录，苦于无法及时传递想 Mark 的内容，故而制作此小项目。

保留这个简单的初衷：减少电脑和平板之间来回传截图的步骤，也希望帮助有相同需求的人。这是采用 AI 辅助开发的实验性个人项目。

欢迎到 [Issues](https://github.com/bernice-Huang/ClipBridge-Bluetooth/issues) 反馈设备、系统、内容类型、前后台状态及实际粘贴结果。请勿上传配对密钥、私人正文或未经检查的日志。

Windows-to-iPad image and plain-text clipboard bridge over Bluetooth Low Energy. No shared Wi-Fi, IP setup or cloud relay required.

本项目使用 [MIT 许可证](LICENSE)。[版本记录](CHANGELOG.md) · [第三方许可](docs/development/third-party.md) · [测试范围](docs/development/testing.md)
