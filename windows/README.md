# Windows 源码导读

这里是源码，不是下载文件夹。只想使用，请回到[项目首页](../README.md)下载 Windows ZIP。

## 按职责找代码

```text
windows/
├── launcher.py          # 托盘程序入口（也供 PyInstaller 使用）
├── console.py           # 命令行诊断入口
├── diagnose.py          # 蓝牙适配器能力检查
├── windows_api.py       # 共享 Win32 句柄声明、单实例锁名、剪贴板序号
├── app/                 # 界面、线程生命周期与本机配置
│   ├── desktop.py       # Tk/托盘、用户操作、启动与自测
│   ├── controller.py    # 后台 WinRT/asyncio 工作线程和重试/退出
│   ├── runtime.py       # 设置、配对密钥迁移、状态快照与日志
│   └── startup.py       # 仅本应用的登录启动项
├── clipboard/           # 只负责采集与编码，不调用 GATT
│   ├── monitor.py       # 新内容监听、暂停边界、图片优先与去重
│   ├── models.py        # 不可变 Snapshot：图片或 UTF-8 文字
│   ├── text.py          # 有界读取 Windows 纯文本
│   └── image_codec.py   # 有界 PNG 编码与适度压缩
└── ble/                 # 蓝牙、认证和传输，不创建界面
    ├── sender.py        # GATT 服务、认证、发送队列、ACK 和回执
    ├── protocol.py      # UUID、帧、限额、HMAC 与 AES-GCM
    └── buffers.py       # WinRT 缓冲区转换与设备标识
```

`__init__.py` 只声明包，不在导入时开启蓝牙、读取剪贴板或修改配置。

## 建议阅读顺序

1. [Snapshot 模型](clipboard/models.py)：先看两端传输的内容在发送端如何表示。
2. [监听器](clipboard/monitor.py)：如何只采集新内容、如何排除暂停期间的内容。
3. [协议](ble/protocol.py)和[发送器](ble/sender.py)：如何加密、认证、分片并等待回执。
4. [后台控制器](app/controller.py)：采集线程与异步传输如何启动、重试和退出。
5. [桌面界面](app/desktop.py)：托盘如何调用控制器，而不直接处理传输。

界面在 Tk 主线程；GATT 状态在专用 asyncio 工作线程；采集在独立轮询线程，通过 `call_soon_threadsafe` 提交不可变快照。不要从采集线程直接调用 GATT 或更新 Tk。

## 改动后如何验证

从仓库根目录运行自动测试和构建，步骤见[开发指南](../docs/development/build.md)。[源码地图](../docs/development/source-map.md)列出了常见修改对应的模块与测试。

原命令行发送入口已从 `windows/sender.py` 整理为 `windows/console.py`；桌面入口仍是 `windows/launcher.py`。已安装的 EXE 和配对配置不受源码目录调整影响。
