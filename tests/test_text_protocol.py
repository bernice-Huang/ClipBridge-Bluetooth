"""Text wire, capability negotiation and monitoring use synthetic data only."""
import asyncio
from pathlib import Path
import re
import sys
from types import SimpleNamespace
import time
import unittest
from unittest.mock import AsyncMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "windows"))
from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from PIL import Image
import protocol as p
from sender import Sender, Snapshot

KEY = bytes(range(16))
TEXT = "你好，ClipBridge!\r\nLine 2\t🙂"


class TextWireTests(unittest.TestCase):
    def test_roundtrip_unicode_and_whitespace(self):
        for text in ("a", TEXT, " \t\n", "👩🏽‍💻e\u0301", "x" * p.MAX_TEXT):
            wire = p.seal_text(KEY, text, 123456)
            self.assertEqual(p.open_text(KEY, wire), (text, 123456))
            self.assertEqual(len(wire), 48 + len(text.encode("utf-8")))

    def test_empty_oversized_nul_or_surrogate_text_is_rejected(self):
        for text in ("", "x" * (p.MAX_TEXT + 1), "中" * (p.MAX_TEXT // 3 + 1), "a\0b", "\ud800"):
            with self.subTest(size=len(text)), self.assertRaises(ValueError):
                p.seal_text(KEY, text, 0)

    def test_authentication_and_nonces(self):
        wire = p.seal_text(KEY, TEXT, 0)
        self.assertNotEqual(wire, p.seal_text(KEY, TEXT, 0))
        with self.assertRaises(InvalidTag):
            p.open_text(bytes(16), wire)
        changed = bytearray(wire); changed[-1] ^= 1
        with self.assertRaises(InvalidTag):
            p.open_text(KEY, bytes(changed))

    def test_invalid_sizes_and_cross_type_rejected(self):
        for wire in (b"", bytes(48), bytes(p.MAX_TEXT + 49), p.seal_image(KEY, b"png", 1, 1, 0)):
            with self.assertRaises(ValueError):
                p.open_text(KEY, wire)
        with self.assertRaises(ValueError):
            p.open_image(KEY, p.seal_text(KEY, TEXT, 0))

    def test_invalid_text_headers_and_encoding_are_rejected(self):
        for magic, width, height, body in ((b"CBT1", 1, 0, b"a"), (b"CBT1", 0, 1, b"a"),
                (b"NOPE", 0, 0, b"a"), (b"CBT1", 0, 0, b"\xff"), (b"CBT1", 0, 0, b"a\0b")):
            nonce = bytes(12)
            plain = p.IMAGE_HEADER.pack(magic, width, height, 0) + body
            wire = nonce + AESGCM(KEY).encrypt(nonce, plain, p.AAD)
            with self.assertRaises(ValueError):
                p.open_text(KEY, wire)

    def test_swift_self_test_vector_matches_python(self):
        swift = (Path(__file__).resolve().parents[1] / "ipad/ClipBridgeBLE.swiftpm/Sources/BLEBridge.swift").read_text(encoding="utf-8")
        hex_value = re.search(r'let textHex = "([0-9a-f]+)"', swift).group(1)
        self.assertEqual(p.open_text(KEY, bytes.fromhex(hex_value)), (TEXT, 123456))
        self.assertIn("static let maxText = 64 * 1024", swift)
        self.assertIn("UTType.utf8PlainText.identifier: text", swift)
        self.assertIn("write(Data([21, 1]))", swift)


class TextSenderTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.sender = Sender(KEY, pipeline=1)
        self.sender.data = SimpleNamespace(subscribed_clients=[SimpleNamespace(
            session=SimpleNamespace(device_id=SimpleNamespace(id="ipad")), max_notification_size=185)])
        self.sender.ready = AsyncMock()

    async def asyncTearDown(self):
        await asyncio.gather(*self.sender.tasks, return_exceptions=True)

    def authenticate(self):
        self.sender.challenges["ipad"] = (bytes(16), time.monotonic())
        self.assertTrue(self.sender.accept_control("ipad", bytes([p.AUTH]) + p.auth_proof(KEY, bytes(16))))

    def snapshot(self, text=TEXT):
        return Snapshot(text.encode("utf-8"), 0, 0, 123456, time.monotonic(), "text")

    async def monitor_once(self, *, image=None, text=TEXT, sequence=(0, 1, 1), loops=1):
        with patch("sender.ctypes.windll.user32.GetClipboardSequenceNumber", side_effect=sequence), \
                patch.object(self.sender.stop_monitor, "wait", side_effect=[False] * loops + [True]), \
                patch("sender.ImageGrab.grabclipboard", return_value=image), \
                patch("sender.read_text", return_value=text) as read:
            self.sender.monitor()
        await asyncio.sleep(0)
        return read

    async def test_capabilities_require_auth_and_reset_after_auth_or_stop(self):
        caps = bytes([p.CAPABILITIES, p.TEXT_CAPABILITY])
        self.assertFalse(self.sender.accept_control("ipad", caps))
        self.authenticate()
        for invalid in (bytes([p.CAPABILITIES]), bytes([p.CAPABILITIES, 0]), bytes([p.CAPABILITIES, 3])):
            self.assertFalse(self.sender.accept_control("ipad", invalid))
        self.assertTrue(self.sender.accept_control("ipad", caps))
        self.assertIn("ipad", self.sender.text_clients)
        self.authenticate()
        self.assertNotIn("ipad", self.sender.text_clients)
        self.assertTrue(self.sender.accept_control("ipad", caps))
        self.assertTrue(self.sender.accept_control("ipad", bytes([p.STOP])))
        self.assertNotIn("ipad", self.sender.text_clients)

    async def test_disconnect_clears_capabilities(self):
        self.authenticate()
        self.sender.text_clients.add("ipad")
        self.sender.data.subscribed_clients = []
        self.sender.refresh_clients()
        self.assertFalse(self.sender.text_clients)

    async def test_capabilities_require_current_subscription(self):
        self.authenticate()
        self.sender.data.subscribed_clients = []
        self.assertFalse(self.sender.accept_control("ipad", bytes([p.CAPABILITIES, 1])))
        self.assertFalse(self.sender.text_clients)

    async def test_ready_preserves_window_and_announces_text(self):
        self.authenticate()
        self.sender.notify = AsyncMock()
        await Sender.ready(self.sender, "ipad")
        kind, transfer_id, value = p.HEADER.unpack(self.sender.notify.call_args.args[1])
        self.assertEqual((kind, transfer_id, value & 0xffff), (p.READY, 0, p.WINDOW))
        self.assertEqual(value & p.READY_TEXT, p.READY_TEXT)

    async def test_old_receiver_never_gets_text_frames(self):
        self.authenticate()
        self.sender.notify = AsyncMock()
        with self.assertRaises(ValueError):
            await self.sender.transfer(self.snapshot(), "ipad")
        self.sender.notify.assert_not_called()
        self.assertIsNone(self.sender.active_id)

    async def test_capability_wakes_waiting_text_not_image(self):
        self.authenticate()
        self.sender.publish(self.snapshot())
        self.sender.pending.clear()
        self.assertTrue(self.sender.accept_control("ipad", bytes([p.CAPABILITIES, 1])))
        self.assertTrue(self.sender.pending.is_set())
        self.sender.latest = Snapshot(b"png", 1, 1, 0, time.monotonic())
        self.sender.pending.clear()
        self.assertTrue(self.sender.accept_control("ipad", bytes([p.CAPABILITIES, 1])))
        self.assertFalse(self.sender.pending.is_set())

    async def test_text_fragmentation_ack_receipt_at_all_pipeline_depths(self):
        self.authenticate()
        self.sender.text_clients.add("ipad")
        for mtu in (20, 185, 524):
            for depth in (1, 2, 4, 8):
                self.sender.pipeline = depth
                self.sender.data.subscribed_clients[0].max_notification_size = mtu
                received = bytearray(); total = count = 0
                async def notify(_client, frame):
                    nonlocal total, count
                    kind, transfer_id, value = p.HEADER.unpack_from(frame)
                    if kind == p.START:
                        total = value
                    elif kind == p.CHUNK:
                        self.assertEqual(value, len(received))
                        received.extend(frame[9:]); count += 1
                        if count % p.WINDOW == 0 or len(received) == total:
                            self.assertTrue(self.sender.accept_control("ipad", p.HEADER.pack(p.ACK, transfer_id, len(received))))
                    elif kind == p.END:
                        self.assertEqual(len(received), total)
                        self.assertTrue(self.sender.accept_control("ipad", bytes([p.RECEIPT]) + transfer_id.to_bytes(4, "little") + bytes([2])))
                async def batch(_client, frames):
                    for frame in frames:
                        await notify(_client, frame)
                self.sender.notify, self.sender.notify_batch = notify, batch
                await self.sender.transfer(self.snapshot(TEXT * 50), "ipad")
                self.assertEqual(p.open_text(KEY, bytes(received)), (TEXT * 50, 123456))
                self.assertIsNone(self.sender.active_id)

    async def test_text_monitor_preserves_content_without_logging_body(self):
        with self.assertLogs("clipbridge", level="INFO") as logs:
            await self.monitor_once()
        self.assertEqual(self.sender.latest.data.decode("utf-8"), TEXT)
        self.assertEqual(self.sender.latest.kind, "text")
        self.assertNotIn(TEXT, " ".join(logs.output))

    async def test_new_copy_of_same_text_is_resent(self):
        values = []; self.sender.on_status = lambda **value: values.append(value)
        await self.monitor_once(sequence=(0, 1, 1, 2, 2), loops=2)
        self.assertEqual(len(values), 2)

    async def test_pairing_key_is_never_auto_sent(self):
        for text in (KEY.hex(), "session " + KEY.hex().upper()):
            await self.monitor_once(text=text)
            self.assertIsNone(self.sender.latest)

    async def test_empty_or_file_clipboard_is_ignored(self):
        for text in (None, ""):
            await self.monitor_once(text=text)
            self.assertIsNone(self.sender.latest)
        read = await self.monitor_once(image=["private-file.txt"], sequence=(0, 1))
        read.assert_not_called()
        self.assertIsNone(self.sender.latest)

    async def test_text_toggle_keeps_images_but_excludes_old_queued_text(self):
        epoch = self.sender.capture_epoch
        self.sender.publish(self.snapshot())
        with patch("sender.ctypes.windll.user32.GetClipboardSequenceNumber", return_value=42):
            self.sender.configure(quality="balanced", pipeline=1, target_bytes=32 * 1024, sync_text=False)
            self.assertIsNone(self.sender.latest)
            self.sender.publish(self.snapshot())
            self.assertIsNone(self.sender.latest)
            self.sender.publish(Snapshot(b"png", 1, 1, 0, time.monotonic()))
            self.assertEqual(self.sender.latest.kind, "image")
            self.sender.configure(quality="balanced", pipeline=1, target_bytes=32 * 1024, sync_text=True)
            self.sender.publish(self.snapshot(), epoch)
            self.assertEqual(self.sender.latest.kind, "image")

    async def test_disabled_text_reader_is_not_called(self):
        self.sender.sync_text = False
        read = await self.monitor_once(sequence=(0, 1))
        read.assert_not_called()

    async def test_image_takes_priority_when_text_is_also_available(self):
        with Image.new("RGB", (20, 10), "white") as image:
            read = await self.monitor_once(image=image)
        read.assert_not_called()
        self.assertEqual(self.sender.latest.kind, "image")

    async def test_clipboard_change_during_read_is_discarded(self):
        await self.monitor_once(sequence=(0, 1, 2))
        self.assertIsNone(self.sender.latest)

    async def test_busy_read_retries_same_sequence(self):
        with patch("sender.ctypes.windll.user32.GetClipboardSequenceNumber", side_effect=(0, 1, 1, 1)), \
                patch.object(self.sender.stop_monitor, "wait", side_effect=(False, False, True)), \
                patch("sender.ImageGrab.grabclipboard", return_value=None), \
                patch("sender.read_text", side_effect=(OSError("busy"), TEXT)) as read:
            self.sender.monitor()
        await asyncio.sleep(0)
        self.assertEqual(read.call_count, 2)
        self.assertEqual(self.sender.latest.data.decode("utf-8"), TEXT)

    async def test_paused_capture_drops_text(self):
        self.sender.set_capture_paused(True)
        self.sender.publish(self.snapshot())
        self.assertIsNone(self.sender.latest)
