"""Background BLE worker lifecycle, settings handoff and orderly shutdown."""
import asyncio
import logging
import threading

from winrt.runtime import ApartmentType, init_apartment, uninit_apartment

from ble.sender import Sender

LOG = logging.getLogger("clipbridge")


class Controller:
    """Bridge Tk actions to a dedicated WinRT/asyncio worker without blocking UI."""

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
                            target_bytes=settings.target_kib * 1024, sync_text=settings.sync_text,
                            on_status=self.status.update)
            self.sender = sender
            sender.set_capture_paused(settings.paused)
            monitor = None
            task = None
            failed = False
            self.restart_requested = False
            self.status.update(phase="starting", detail="正在启动蓝牙服务", error="")
            try:
                await sender.start()
                monitor = threading.Thread(target=sender.capture.run, name="clipboard-monitor", daemon=True)
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
                                      target_bytes=settings.target_kib * 1024, sync_text=settings.sync_text)
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
            if self.sender is not None and not self.sender.capture.paused.is_set():
                self.sender.pending.set()
        self.call(apply)

    def close(self):
        self.stop.set()
        self.call(lambda: self.wake.set() if self.wake is not None else None)
        self.thread.join(timeout=6)
