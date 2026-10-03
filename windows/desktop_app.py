"""Windows desktop shell. The validated BLE/image wire protocol stays unchanged."""
import argparse
import asyncio
from dataclasses import replace
import json
import logging
import os
from pathlib import Path
import queue
import sys
import tempfile
import threading
import tkinter as tk
from tkinter import messagebox, ttk

from PIL import Image, ImageDraw
import pystray
from winrt.runtime import ApartmentType, init_apartment, uninit_apartment
from winrt.windows.devices.bluetooth import BluetoothAdapter

from runtime import APP_NAME, VERSION, Settings, Status, data_folder, pairing_key, configure_logging
from sender import Sender, as_buffer, as_bytes, ctypes
from image_codec import encode_image
import protocol
import startup

LOG = logging.getLogger("clipbridge")
MUTEX_NAME = "Local\\ClipBridgeBluetoothPrototype"  # Shared with the old console sender.


def icon_image(color="#1976d2"):
    image = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    draw.rounded_rectangle((3, 3, 61, 61), radius=15, fill=color)
    draw.line([(31, 10), (31, 54), (45, 42), (19, 21)], fill="white", width=4)
    draw.line([(19, 44), (45, 22), (31, 10)], fill="white", width=4)
    return image


class Controller:
    def __init__(self, key, settings, status):
        self.key, self.settings, self.status = key, settings, status
        self.stop = threading.Event()
        self.loop = self.sender = self.wake = None
        self.restart_requested = False
        self.lock = threading.Lock()
        self.thread = threading.Thread(target=self.worker, name="ble-worker", daemon=True)

    def start(self):
        self.thread.start()

    def worker(self):
        initialized = False
        try:
            init_apartment(ApartmentType.MULTI_THREADED)
            initialized = True
            asyncio.run(self.run())
        except Exception as error:
            LOG.exception("BLE worker stopped")
            self.status.update(phase="error", detail="发送线程停止，请从托盘重启程序", error=str(error))
        finally:
            if initialized:
                uninit_apartment()

    async def run(self):
        self.loop = asyncio.get_running_loop()
        self.wake = asyncio.Event()
        while not self.stop.is_set():
            with self.lock:
                settings = self.settings
            sender = Sender(self.key, quality=settings.quality, pipeline=settings.pipeline,
                            target_bytes=settings.target_kib * 1024, on_status=self.status.update)
            self.sender = sender
            sender.set_capture_paused(settings.paused)
            monitor = None
            task = None
            failed = False
            self.restart_requested = False
            self.status.update(phase="starting", detail="正在启动蓝牙服务", error="")
            try:
                await sender.start()
                monitor = threading.Thread(target=sender.monitor, name="clipboard-monitor", daemon=True)
                monitor.start()
                task = asyncio.create_task(sender.run())
                while not self.stop.is_set() and not self.restart_requested:
                    self.wake.clear()
                    if task.done():
                        await task
                        raise RuntimeError("Sender loop stopped unexpectedly")
                    try:
                        await asyncio.wait_for(self.wake.wait(), 3)
                    except TimeoutError:
                        # A radio toggle can silently stop advertising. Recreate
                        # our service; never restart the OS Bluetooth service.
                        if sender.provider.advertisement_status.name != "STARTED":
                            raise RuntimeError("Bluetooth advertisement stopped")
            except Exception as error:
                failed = True
                LOG.warning("Bluetooth session unavailable: %s; retry in 10 seconds", error)
                self.status.update(phase="error", detail="蓝牙未就绪，10 秒后自动重试", error=str(error))
            finally:
                if task is not None:
                    task.cancel()
                    await asyncio.gather(task, return_exceptions=True)
                try:
                    await sender.close()
                except Exception:
                    LOG.exception("BLE cleanup failed")
                if monitor is not None:
                    monitor.join(timeout=2)
                self.sender = None
            if failed and not self.stop.is_set():
                self.wake.clear()
                if not self.restart_requested:
                    try:
                        await asyncio.wait_for(self.wake.wait(), 10)
                    except TimeoutError:
                        pass
        self.status.update(phase="stopped", detail="已停止")
        self.loop = None

    def call(self, action):
        loop = self.loop
        if loop is not None and not loop.is_closed():
            loop.call_soon_threadsafe(action)

    def configure(self, settings):
        with self.lock:
            self.settings = settings
        self.status.update(paused=settings.paused)
        def apply():
            if self.sender is not None:
                self.sender.configure(quality=settings.quality, pipeline=settings.pipeline,
                                      target_bytes=settings.target_kib * 1024)
                self.sender.set_capture_paused(settings.paused)
        self.call(apply)

    def restart(self):
        def apply():
            self.restart_requested = True
            if self.wake is not None:
                self.wake.set()
        if not self.thread.is_alive():
            self.stop.clear()
            self.thread = threading.Thread(target=self.worker, name="ble-worker", daemon=True)
            self.thread.start()
        else:
            self.call(apply)

    def resend(self):
        def apply():
            if self.sender is not None and not self.sender.capture_paused.is_set():
                self.sender.pending.set()
        self.call(apply)

    def close(self):
        self.stop.set()
        self.call(lambda: self.wake.set() if self.wake is not None else None)
        self.thread.join(timeout=6)


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
        self.root.geometry("540x440")
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
        ttk.Label(panel, text="复制密钥会覆盖 Windows 剪贴板；日志不包含密钥。", wraplength=490).pack(anchor="w")
        buttons = ttk.Frame(panel); buttons.pack(anchor="w", pady=14)
        self.pause_button = ttk.Button(buttons, command=self.toggle_pause)
        self.pause_button.pack(side="left", padx=(0, 8))
        ttk.Button(buttons, text="重启蓝牙发送端", command=self.controller.restart).pack(side="left", padx=(0, 8))
        ttk.Button(buttons, text="打开诊断日志", command=self.open_log).pack(side="left")
        ttk.Label(panel, text="关闭此窗口只隐藏到托盘。\n图片仍仅在内存中；请到 Goodnotes 实际粘贴确认。", wraplength=490).pack(anchor="w")
        item = pystray.MenuItem
        def action(fn):
            return lambda _icon, _item: self.commands.put(fn)
        self.icon = pystray.Icon("ClipBridgeBLE", icon_image(), APP_NAME, menu=pystray.Menu(
            item("显示状态", action(self.show), default=True),
            item("暂停截图捕获", action(self.toggle_pause), checked=lambda _item: self.settings.paused),
            item("画质", pystray.Menu(
                item("均衡（已验证的适度压缩）", action(lambda: self.change(quality="balanced")), checked=lambda _item: self.settings.quality == "balanced", radio=True),
                item("原图（可能较慢）", action(lambda: self.change(quality="original")), checked=lambda _item: self.settings.quality == "original", radio=True))),
            item("发送模式", pystray.Menu(
                item("快速队列", action(lambda: self.change(pipeline=4)), checked=lambda _item: self.settings.pipeline == 4, radio=True),
                item("逐包兼容", action(lambda: self.change(pipeline=1)), checked=lambda _item: self.settings.pipeline == 1, radio=True))),
            item("重新发送最新图", action(self.controller.resend)),
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
                             f"最近截图：{status['last_image']}\n最近回执：{status['last_receipt']}\n"
                             f"画质：{'均衡' if self.settings.quality == 'balanced' else '原图'}；实际发送：{mode}\n"
                             f"{('错误：' + status['error']) if status['error'] else '不需要 Wi-Fi、热点或修改 IP 地址。'}")
            self.pause_button.configure(text="恢复截图捕获" if paused else "暂停截图捕获")
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
    assert as_bytes(as_buffer(b"package-test")) == b"package-test"
    adapter = await BluetoothAdapter.get_default_async()
    return {"version": VERSION, "frozen": bool(getattr(sys, "frozen", False)),
            "crypto": "ok", "png": "ok", "winrt_buffer": "ok", "tk": tk.TkVersion,
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
