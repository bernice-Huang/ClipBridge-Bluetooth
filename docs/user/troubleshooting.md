# 遇到问题，先看这里

[返回首页](../../README.md) · [日常使用](quick-start.md) · [iPad 安装说明](ipad-setup.md)

## 下载了一堆文件，找不到 EXE

你可能下载了源码。请到 [v0.4.0-beta 下载页](https://github.com/bernice-Huang/ClipBridge-Bluetooth/releases/tag/v0.4.0-beta) 的 **Assets** 下载 `windows-x64.zip`，解压后运行 `ClipBridgeBLE.exe`。无需 Git 或 Python。

iPad 下载 `ipad.zip`，在“文件”App 解压、用 Swift Playgrounds 打开 `ClipBridgeBLE.swiftpm`。源码 ZIP 不能像 IPA 一样安装。

## 电脑提示未知发布者

EXE 尚未签名。确认来自本项目发布页，并校验 SHA-256；如果来源不明或校验不一致，不要运行。不要关闭防病毒或系统安全功能。

## iPad 找不到电脑，或一直连接失败

1. 两端开启蓝牙，电脑托盘状态应为“等待 iPad 连接”。不需要连接同一 Wi-Fi，也不需要在系统蓝牙列表中手动配对。
2. 电脑蓝牙硬件必须支持 BLE peripheral / GATT server；仅能使用蓝牙耳机不能证明满足要求。
3. 只保留一个 Windows 发送端和一个 iPad 接收端，退出重复运行的命令行或旧版本。
4. 核对本机密钥，允许 Playgrounds 蓝牙权限，重新运行工程并连接。休眠、重启或切换蓝牙后可能需要重新连接。
5. 不要删除 `session.json` 试图修复问题，这会影响原配对。其他步骤见 [iPad 安装说明](ipad-setup.md)。

## 图片可以接收，文字不行

两端都须为 v0.4.0-beta 或更新兼容版本；检查电脑“同步文字”已勾选，捕获未暂停。iPad 的“文字能力”应显示发送端支持文字。

连接完成后重新复制一段新文字，例如 `中文测试 123 🙂`，先在备忘录正文编辑区粘贴。文字超过 64 KiB UTF-8 字节会跳过；文件列表不发送。见[升级指南](upgrade-v0.4.md)。

## 显示收到，但 Goodnotes 粘不出来

文字要在 **Goodnotes 文本框的编辑状态**中粘贴，可先到备忘录验证。图片按图片方式粘贴。确认粘出的是这次的新内容，而不是旧剪贴板。

“回执”“已尝试写入”只表示程序调用过剪贴板写入，不能证明目标应用一定能粘贴。内容 10 分钟后过期；可切回接收端点“重新复制最新内容”，再粘贴。

## 前台可以，切到后台就不行

不要从多任务列表划掉接收程序。检查 `bluetooth-central 已读到`，然后按 [iPad 前后台验证步骤](ipad-setup.md)测试。锁屏、内存压力、系统终止和 Playgrounds 容器都可能影响后台；当前不能保证所有环境可用。只能切回后粘贴时，请明确反馈“仅前台可用”。

## 大图很慢或超时

先试小区域截图、均衡画质；分片错误可尝试“逐包兼容”后重连。传输有 20 秒截止时间，复杂图片和长文字不保证三秒内完成。不要连续复制多项期待形成队列：程序只保留最新内容。

PNG 上限 2 MiB、单边 8192 像素、总计 3200 万像素。均衡模式的 32 KiB 是软目标，必要时最多缩小到约 75% 边长，优先保证文字可读；要求原图细节时可切换原图，但传输可能更慢。

## 校验下载文件

从同一发布页下载 `SHA256SUMS.txt`。在下载文件夹打开 PowerShell，例如：

```powershell
Get-FileHash -Algorithm SHA256 -LiteralPath .\ClipBridgeBLE-v0.4.0-beta-windows-x64.zip
```

把结果与校验文件中该 ZIP 对应的完整 64 位值比较；iPad ZIP 同样操作。如当前 PowerShell 提示找不到 `Get-FileHash`，可用 Windows 自带命令：

```powershell
certutil -hashfile .\ClipBridgeBLE-v0.4.0-beta-windows-x64.zip SHA256
```

## 需要反馈时

到 [Issues](https://github.com/bernice-Huang/ClipBridge-Bluetooth/issues) 说明两端版本、设备、系统、图片或文字、前台或后台，以及是否能实际粘贴。编译问题请提供第一条错误；其他问题可从电脑托盘打开诊断日志，检查后仅提供必要片段。

不要公开密钥、私人截图、文字正文或配置文件。
