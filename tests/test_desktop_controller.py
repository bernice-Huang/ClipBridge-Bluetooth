"""Desktop lifecycle tests without Bluetooth advertising or clipboard access."""
from dataclasses import replace
from pathlib import Path
import queue
import sys
import threading
from types import SimpleNamespace
import unittest
from unittest.mock import patch
import asyncio

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "windows"))
from desktop_app import Controller
from runtime import Settings, Status


class FakeSender:
    instances = queue.Queue()
    fail_start = False

    def __init__(self, key, *, quality, pipeline, target_bytes, on_status):
        self.quality, self.pipeline, self.target_bytes = quality, pipeline, target_bytes
        self.capture_paused = threading.Event()
        self.stop_monitor = threading.Event()
        self.started = threading.Event()
        self.configured = threading.Event()
        self.closed = threading.Event()
        self.pending = asyncio.Event()
        self.provider = SimpleNamespace(advertisement_status=SimpleNamespace(name="STARTED"))
        self.fail_start = type(self).fail_start

    def set_capture_paused(self, value):
        self.capture_paused.set() if value else self.capture_paused.clear()
        self.configured.set()

    def configure(self, *, quality, pipeline, target_bytes):
        self.quality, self.pipeline, self.target_bytes = quality, pipeline, target_bytes

    async def start(self):
        self.instances.put(self)
        if self.fail_start:
            raise RuntimeError("synthetic radio unavailable")

    def monitor(self):
        self.started.set()
        self.stop_monitor.wait(5)

    async def run(self):
        await asyncio.Event().wait()

    async def close(self):
        self.stop_monitor.set()
        self.closed.set()


class ErrorStatus(Status):
    def __init__(self):
        super().__init__()
        self.error_seen = threading.Event()

    def update(self, **values):
        super().update(**values)
        if values.get("phase") == "error":
            self.error_seen.set()


class ControllerTests(unittest.TestCase):
    def setUp(self):
        FakeSender.instances = queue.Queue()
        FakeSender.fail_start = False

    def test_background_worker_configure_restart_and_close(self):
        controller = Controller(bytes(16), Settings(), Status())
        with patch("desktop_app.Sender", FakeSender):
            controller.start()
            try:
                first = FakeSender.instances.get(timeout=3)
                self.assertTrue(first.started.wait(2))
                first.configured.clear()
                controller.configure(replace(Settings(), quality="original", pipeline=1, paused=True))
                self.assertTrue(first.configured.wait(2))
                self.assertTrue(first.capture_paused.is_set())
                self.assertEqual((first.quality, first.pipeline), ("original", 1))
                controller.restart()
                second = FakeSender.instances.get(timeout=3)
                self.assertTrue(first.closed.wait(2))
                self.assertTrue(second.started.wait(2))
                self.assertTrue(second.capture_paused.is_set())
                self.assertEqual(second.pipeline, 1)
            finally:
                controller.close()
            self.assertFalse(controller.thread.is_alive())
            self.assertTrue(second.closed.is_set())

    def test_persisted_pause_applies_before_monitor_starts(self):
        controller = Controller(bytes(16), Settings(paused=True), Status())
        with patch("desktop_app.Sender", FakeSender):
            controller.start()
            try:
                sender = FakeSender.instances.get(timeout=3)
                self.assertTrue(sender.started.wait(2))
                self.assertTrue(sender.capture_paused.is_set())
            finally:
                controller.close()
            self.assertFalse(controller.thread.is_alive())

    def test_radio_failure_reports_and_can_exit_during_retry(self):
        FakeSender.fail_start = True
        status = ErrorStatus()
        controller = Controller(bytes(16), Settings(), status)
        with patch("desktop_app.Sender", FakeSender):
            controller.start()
            try:
                sender = FakeSender.instances.get(timeout=3)
                self.assertTrue(status.error_seen.wait(2))
                self.assertTrue(sender.closed.wait(2))
                self.assertIn("synthetic radio", status.snapshot()["error"])
            finally:
                controller.close()
            self.assertFalse(controller.thread.is_alive())


if __name__ == "__main__":
    unittest.main()
