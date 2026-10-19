"""Module boundaries and capture state; synthetic inputs, no devices or user data."""
import ast
import asyncio
from dataclasses import FrozenInstanceError
from pathlib import Path
import re
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "windows"))
from app import runtime
from ble import protocol
from clipboard.models import Snapshot
from clipboard.monitor import ClipboardMonitor

ROOT = Path(__file__).resolve().parents[1]


def imports(path):
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Import):
            yield from (alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            yield node.module


class SourceBoundaryTests(unittest.TestCase):
    def test_source_migration_path_remains_at_project_root(self):
        self.assertEqual(runtime.legacy_session_path(), ROOT / "session.json")
        with patch.object(runtime.sys, "frozen", True, create=True):
            self.assertIsNone(runtime.legacy_session_path())

    def test_protocol_is_independent_of_devices_and_ui(self):
        modules = set(imports(ROOT / "windows/ble/protocol.py"))
        for name in modules:
            self.assertNotIn(name.split(".")[0], {"app", "clipboard", "tkinter", "PIL", "winrt", "ctypes"})

    def test_capture_does_not_import_sender_or_ui(self):
        for path in (ROOT / "windows/clipboard").glob("*.py"):
            for name in imports(path):
                with self.subTest(module=path.name, dependency=name):
                    self.assertNotEqual(name, "ble.sender")
                    self.assertNotIn(name.split(".")[0], {"app", "tkinter", "winrt"})

    def test_package_initializers_have_no_startup_side_effects(self):
        for path in (ROOT / "windows").rglob("__init__.py"):
            nodes = ast.parse(path.read_text(encoding="utf-8")).body
            self.assertTrue(all(isinstance(node, ast.Expr) and isinstance(node.value, ast.Constant)
                                and isinstance(node.value.value, str) for node in nodes))

    def test_snapshot_is_immutable(self):
        snapshot = Snapshot(b"hello", 0, 0, 123, 1.5, "text")
        with self.assertRaises(FrozenInstanceError):
            snapshot.kind = "image"

    def test_swift_types_are_declared_once_in_their_own_modules(self):
        sources = ROOT / "ipad/ClipBridgeBLE.swiftpm/Sources"
        expected = {"ClipBridgeApp": "App/ClipBridgeApp.swift", "ContentView": "App/ContentView.swift",
                    "BLEBridge": "Bluetooth/BLEBridge.swift", "Wire": "Protocol/Wire.swift",
                    "WireSelfTest": "Protocol/WireSelfTest.swift", "PairingKey": "Storage/PairingKey.swift"}
        declarations = {}
        for path in sources.rglob("*.swift"):
            source = path.read_text(encoding="utf-8")
            for name in re.findall(r"^(?:final )?(?:struct|enum|class) (\w+)", source, re.MULTILINE):
                self.assertNotIn(name, declarations)
                declarations[name] = path.relative_to(sources).as_posix()
        self.assertEqual(declarations, expected)
        manifest = (sources.parent / "Package.swift").read_text(encoding="utf-8")
        self.assertIn('path: "Sources"', manifest)
        self.assertIn('swiftLanguageVersions: [.v5]', manifest)

    def test_swift_image_and_auth_fixtures_remain_interoperable(self):
        source = (ROOT / "ipad/ClipBridgeBLE.swiftpm/Sources/Protocol/WireSelfTest.swift").read_text(encoding="utf-8")
        vector = bytes.fromhex(re.search(r'let hex = "([0-9a-f]+)"', source).group(1))
        key = bytes(range(16))
        self.assertEqual(protocol.open_image(key, vector), (b"vector", 2, 3, 123456))
        self.assertEqual(protocol.auth_proof(key, key).hex(), "4d06a2c8ab55783e7134fe072b02c7f2")


class CaptureStateTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.published = []
        self.capture = ClipboardMonitor(bytes(range(16)), asyncio.get_running_loop(),
            lambda *values: self.published.append(values), lambda: ("balanced", 32 * 1024))

    async def test_text_toggle_only_advances_epoch_when_changed(self):
        with patch("clipboard.monitor.clipboard_sequence", return_value=42):
            self.assertFalse(self.capture.set_text_enabled(True))
            self.assertEqual(self.capture.epoch, 0)
            self.assertTrue(self.capture.set_text_enabled(False))
            self.assertEqual((self.capture.epoch, self.capture.baseline), (1, 42))
            self.assertFalse(self.capture.set_text_enabled(False))
            self.assertEqual(self.capture.epoch, 1)
        with self.assertRaises(ValueError):
            self.capture.set_text_enabled("false")

    async def test_pause_resume_preserves_baseline_policy(self):
        self.capture.set_paused(True)
        self.assertTrue(self.capture.paused.is_set())
        self.assertEqual(self.capture.epoch, 1)
        self.capture.set_paused(True)
        self.assertEqual(self.capture.epoch, 1)
        with patch("clipboard.monitor.clipboard_sequence", return_value=73):
            self.capture.set_paused(False)
        self.assertFalse(self.capture.paused.is_set())
        self.assertEqual((self.capture.epoch, self.capture.baseline), (2, 73))

    async def test_capture_can_publish_without_any_sender(self):
        with patch("clipboard.monitor.clipboard_sequence", side_effect=(0, 1, 1)), \
                patch.object(self.capture.stop, "wait", side_effect=(False, True)), \
                patch("clipboard.monitor.ImageGrab.grabclipboard", return_value=None), \
                patch("clipboard.monitor.read_text", return_value="独立采集 🙂"):
            self.capture.run()
        await asyncio.sleep(0)
        self.assertEqual(len(self.published), 1)
        snapshot, epoch = self.published[0]
        self.assertEqual(snapshot.data.decode("utf-8"), "独立采集 🙂")
        self.assertEqual((snapshot.kind, epoch), ("text", 0))
