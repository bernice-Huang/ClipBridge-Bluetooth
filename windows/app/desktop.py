"""Windows desktop shell for image and negotiated plain-text clipboard sync."""
import argparse
import asyncio
import ctypes
from dataclasses import replace
import json
import logging
import os
from pathlib import Path
import queue
import sys
import tempfile
import tkinter as tk
from tkinter import messagebox, ttk

from PIL import Image, ImageDraw
import pystray
from winrt.windows.devices.bluetooth import BluetoothAdapter

from app import startup
from app.controller import Controller
from app.runtime import (
    APP_NAME,
    VERSION,
    Settings,
    Status,
    configure_logging,
    data_folder,
    pairing_key,
)
from ble import protocol
from ble.buffers import as_buffer, as_bytes
from clipboard.image_codec import encode_image
from windows_api import MUTEX_NAME

LOG = logging.getLogger("clipbridge")


def icon_image(color="#1976d2"):
    image = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    draw.rounded_rectangle((3, 3, 61, 61), radius=15, fill=color)
    draw.line([(31, 10), (31, 54), (45, 42), (19, 21)], fill="white", width=4)
    draw.line([(19, 44), (45, 22), (31, 10)], fill="white", width=4)
    return image


class DesktopApp:
    def __init__(self, key, settings, folder, *, smoke=False):
        self.key, self.settings, self.folder, self.smoke = key, settings, Path(folder), smoke
        self.commands = queue.SimpleQueue()
        self.status = Status()
        self.status.update(paused=settings.paused, pipeline=settings.pipeline)
        self.controller = Controller(key, settings, self.status)
        self.root = tk.Tk()
        self.root.withdraw()
        self.root.title(f"{APP_NAME} {VERSION}")
        self.root.geometry("540x490")
        self.root.protocol("WM_DELETE_WINDOW", self.root.withdraw)
        self.details = tk.StringVar()
        self.key_text = tk.StringVar(value="点击‘显示密钥’后查看")
        panel = ttk.Frame(self.root, padding=20)
        panel.pack(fill="both", expand=True)
        ttk.Label(panel, text=f"{APP_NAME} {VERSION}", font=("Microsoft YaHei UI", 16, "bold")).pack(anchor="w")
        ttk.Label(panel, textvariable=self.details, justify="left", wraplength=490).pack(anchor="w", pady=15)
        ttk.Entry(panel, textvariable=self.key_text, state="readonly", width=52).pack(fill="x")
        row = ttk.Frame(panel); row.pack(anchor="w", pady=8)
        ttk.Button(row, text="显示密钥", command=self.show_key).pack(side="left", padx=(0, 8))
        ttk.Button(row, text="复制密钥", command=self.copy_key, state="disabled" if smoke else "normal").pack(side="left")
        ttk.Label(panel, text="复制密钥会覆盖 Windows 剪贴板；含本机密钥的文字不会自动发送。", wraplength=490).pack(anchor="w")
        buttons = ttk.Frame(panel); buttons.pack(anchor="w", pady=14)
        self.pause_button = ttk.Button(buttons, command=self.toggle_pause)
        self.pause_button.pack(side="left", padx=(0, 8))
        ttk.Button(buttons, text="重启蓝牙发送端", command=self.controller.restart).pack(side="left", padx=(0, 8))
        ttk.Button(buttons, text="打开诊断日志", command=self.open_log).pack(side="left")
        ttk.Label(panel, text="关闭此窗口只隐藏到托盘。\n图片、文字仅在内存中；复制密码等敏感内容前请暂停捕获或关闭文字同步。", wraplength=490).pack(anchor="w")
        item = pystray.MenuItem
        def action(fn):
            return lambda _icon, _item: self.commands.put(fn)
        self.icon = pystray.Icon("ClipBridgeBLE", icon_image(), APP_NAME, menu=pystray.Menu(
            item("显示状态", action(self.show), default=True),
            item("暂停剪贴板捕获", action(self.toggle_pause), checked=lambda _item: self.settings.paused),
            item("同步文字", action(lambda: self.change(sync_text=not self.settings.sync_text)), checked=lambda _item: self.settings.sync_text),
            item("画质", pystray.Menu(
                item("均衡（已验证的适度压缩）", action(lambda: self.change(quality="balanced")), checked=lambda _item: self.settings.quality == "balanced", radio=True),
                item("原图（可能较慢）", action(lambda: self.change(quality="original")), checked=lambda _item: self.settings.quality == "original", radio=True))),
            item("发送模式", pystray.Menu(
                item("快速队列", action(lambda: self.change(pipeline=4)), checked=lambda _item: self.settings.pipeline == 4, radio=True),
                item("逐包兼容", action(lambda: self.change(pipeline=1)), checked=lambda _item: self.settings.pipeline == 1, radio=True))),
            item("重新发送最新内容", action(self.controller.resend)),
            item("重启蓝牙发送端", action(self.controller.restart)),
            item("开机自启动", action(self.toggle_startup), checked=lambda _item: startup.enabled(), enabled=getattr(sys, "frozen", False) and not smoke),
            item("打开诊断日志", action(self.open_log)),
            item("打开配置目录", action(lambda: os.startfile(str(self.folder)))),
            item("退出", action(self.quit)),
        ))
        self.last_icon_state = None
        self.closing = False

    def run(self):
        self.icon.run_detached()
        if not self.smoke:
            self.controller.start()
        else:
            self.status.update(phase="waiting", detail="托盘测试：没有监听剪贴板或启动广播")
            self.root.after(1500, self.quit)
        self.root.after(100, self.tick)
        self.root.mainloop()

    def tick(self):
        if self.closing:
            return
        try:
            while not self.commands.empty():
                try:
                    self.commands.get_nowait()()
                except Exception as error:
                    LOG.exception("Desktop action failed")
                    messagebox.showerror(APP_NAME, str(error), parent=self.root)
            if self.closing:
                return
            status = self.status.snapshot()
            paused = status["paused"]
            mode = "逐包兼容" if status["pipeline"] == 1 else f"队列 {status['pipeline']}"
            self.details.set(f"状态：{'捕获已暂停；' if paused else ''}{status['detail']}\n"
                             f"最近内容：{status['last_content']}\n最近回执：{status['last_receipt']}\n"
                             f"文字同步：{'开启（需新版 iPad 接收端）' if self.settings.sync_text else '关闭'}\n"
                             f"画质：{'均衡' if self.settings.quality == 'balanced' else '原图'}；实际发送：{mode}\n"
                             f"{('错误：' + status['error']) if status['error'] else '不需要 Wi-Fi、热点或修改 IP 地址。'}")
            self.pause_button.configure(text="恢复剪贴板捕获" if paused else "暂停剪贴板捕获")
            icon_state = (status["phase"], paused, status["detail"])
            if icon_state != self.last_icon_state:
                colors = {"connected": "#1d9b55", "sending": "#ef8c12", "error": "#ca3342"}
                self.icon.icon = icon_image("#777777" if paused else colors.get(status["phase"], "#1976d2"))
                self.icon.title = f"{APP_NAME} - {'捕获已暂停' if paused else status['detail']}"[:120]
                self.icon.update_menu()
                self.last_icon_state = icon_state
        finally:
            if not self.closing:
                self.root.after(250, self.tick)

    def show(self):
        self.root.deiconify(); self.root.lift()

    def show_key(self):
        self.key_text.set(self.key.hex())

    def copy_key(self):
        if self.smoke:
            return
        self.root.clipboard_clear(); self.root.clipboard_append(self.key.hex())
        self.root.update_idletasks()
        self.show_key()

    def change(self, **values):
        self.settings = replace(self.settings, **values)
        self.controller.configure(self.settings)
        try:
            self.settings.save(self.folder / "settings.json")
        except OSError as error:
            messagebox.showwarning(APP_NAME, f"本次设置已生效，但无法保存：{error}", parent=self.root)
        self.icon.update_menu()

    def toggle_pause(self):
        self.change(paused=not self.settings.paused)

    def toggle_startup(self):
        if self.smoke:
            return
        startup.set_enabled(not startup.enabled(), sys.executable)
        self.icon.update_menu()

    def open_log(self):
        path = self.folder / "app.log"
        if path.exists():
            os.startfile(str(path))

    def quit(self):
        if self.closing:
            return
        self.closing = True
        if not self.smoke:
            self.controller.close()
        self.icon.stop()
        self.root.destroy()


async def self_test():
    with Image.new("RGB", (40, 20), "white") as sample:
        encoded = encode_image(sample)
    key = bytes(range(16))  # Synthetic test key, never the user's pairing secret.
    wire = protocol.seal_image(key, encoded.png, encoded.width, encoded.height, 0)
    assert protocol.open_image(key, wire)[0] == encoded.png
    text = "ClipBridge 中文\r\nEmoji 🙂"
    assert protocol.open_text(key, protocol.seal_text(key, text, 0)) == (text, 0)
    assert as_bytes(as_buffer(b"package-test")) == b"package-test"
    adapter = await BluetoothAdapter.get_default_async()
    return {"version": VERSION, "frozen": bool(getattr(sys, "frozen", False)),
            "crypto": "ok", "png": "ok", "text": "ok", "winrt_buffer": "ok", "tk": tk.TkVersion,
            "adapter_found": adapter is not None,
            "peripheral_supported": adapter.is_peripheral_role_supported if adapter else None}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--startup", action="store_true")
    parser.add_argument("--self-test", type=Path)
    parser.add_argument("--ui-smoke", type=Path)
    options = parser.parse_args()
    if options.self_test:
        try:
            result = asyncio.run(self_test())
            options.self_test.write_text(json.dumps(result, indent=2), encoding="utf-8")
            return 0
        except Exception as error:
            options.self_test.write_text(json.dumps({"error": str(error)}), encoding="utf-8")
            return 1
    if options.ui_smoke:
        with tempfile.TemporaryDirectory(prefix="clipbridge-ui-") as folder:
            app = DesktopApp(bytes(16), Settings(), folder, smoke=True)
            app.run()
            options.ui_smoke.write_text(json.dumps({"version": VERSION, "tray_and_tk": "ok",
                                                    "clipboard_monitored": False}), encoding="utf-8")
        return 0
    mutex = ctypes.windll.kernel32.CreateMutexW(None, False, MUTEX_NAME)
    if not mutex or ctypes.windll.kernel32.GetLastError() == 183:
        if mutex:
            ctypes.windll.kernel32.CloseHandle(mutex)
        if not options.startup:
            ctypes.windll.user32.MessageBoxW(0, "蓝牙发送端已经在运行。请先退出旧命令行窗口，或从现有托盘打开状态。", APP_NAME, 0x40)
        return 0
    handler = None
    try:
        folder = data_folder()
        key = pairing_key(folder)
        handler = configure_logging(folder, key)
        settings = Settings.load(folder / "settings.json")
        LOG.info("Desktop %s started; quality=%s pipeline=%s paused=%s", VERSION, settings.quality, settings.pipeline, settings.paused)
        DesktopApp(key, settings, folder).run()
        return 0
    except Exception as error:
        LOG.exception("Desktop startup failed")
        ctypes.windll.user32.MessageBoxW(0, f"无法启动：{error}\n配置目录：{data_folder()}", APP_NAME, 0x10)
        return 1
    finally:
        if handler is not None:
            logging.getLogger("clipbridge").removeHandler(handler)
            handler.close()
        ctypes.windll.kernel32.CloseHandle(mutex)


if __name__ == "__main__":
    raise SystemExit(main())
