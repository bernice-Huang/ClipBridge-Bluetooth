import asyncio
from pathlib import Path
import struct
import sys
from types import SimpleNamespace
import time
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "windows"))
from cryptography.exceptions import InvalidTag
import protocol as p
from sender import Sender, as_buffer, as_bytes
from winrt.windows.devices.bluetooth.genericattributeprofile import GattCommunicationStatus

KEY = bytes(range(16))


class ProtocolTests(unittest.TestCase):
    def test_roundtrip(self):
        wire = p.seal_image(KEY, b"synthetic-png", 100, 50, 123456)
        self.assertEqual(p.open_image(KEY, wire), (b"synthetic-png", 100, 50, 123456))

    def test_random_nonces(self):
        self.assertNotEqual(p.seal_image(KEY, b"x", 1, 1, 0), p.seal_image(KEY, b"x", 1, 1, 0))

    def test_modified_payload_is_rejected(self):
        wire = bytearray(p.seal_image(KEY, b"x", 1, 1, 0))
        wire[-1] ^= 1
        with self.assertRaises(InvalidTag):
            p.open_image(KEY, bytes(wire))

    def test_wrong_key_is_rejected(self):
        with self.assertRaises(InvalidTag):
            p.open_image(bytes(16), p.seal_image(KEY, b"x", 1, 1, 0))

    def test_png_limit(self):
        for image in (b"", bytes(p.MAX_PNG + 1)):
            with self.assertRaises(ValueError):
                p.seal_image(KEY, image, 1, 1, 0)

    def test_dimension_limit(self):
        for width, height in ((0, 1), (1, 0), (9000, 1), (8192, 8192)):
            with self.assertRaises(ValueError):
                p.seal_image(KEY, b"x", width, height, 0)

    def test_fragmentation_at_different_mtus(self):
        wire = p.seal_image(KEY, bytes(range(256)) * 7, 100, 50, 7)
        for mtu in (20, 185, 244, 512, 1000):
            frames = list(p.frames(123, wire, mtu))
            self.assertEqual(p.HEADER.unpack(frames[0]), (p.START, 123, len(wire)))
            self.assertEqual(p.HEADER.unpack(frames[-1]), (p.END, 123, len(wire)))
            received = bytearray()
            for frame in frames[1:-1]:
                kind, transfer_id, offset = p.HEADER.unpack_from(frame)
                self.assertEqual((kind, transfer_id, offset), (p.CHUNK, 123, len(received)))
                self.assertLessEqual(len(frame), min(mtu, 512))
                received.extend(frame[9:])
            self.assertEqual(bytes(received), wire)

    def test_invalid_mtu(self):
        with self.assertRaises(ValueError):
            list(p.frames(1, b"x", 19))

    def test_winrt_buffer_conversion(self):
        value = bytes(range(256))
        self.assertEqual(as_bytes(as_buffer(value)), value)

    def test_auth_changes_with_challenge(self):
        self.assertEqual(len(p.auth_proof(KEY, bytes(16))), 16)
        self.assertNotEqual(p.auth_proof(KEY, bytes(16)), p.auth_proof(KEY, bytes([1]) * 16))


class ControlTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.sender = Sender(KEY, pipeline=1)
        self.sender.data = SimpleNamespace(subscribed_clients=[
            SimpleNamespace(session=SimpleNamespace(device_id=SimpleNamespace(id="ipad")))
        ])
        async def ready(_identity):
            pass
        self.sender.ready = ready

    async def asyncTearDown(self):
        await asyncio.gather(*self.sender.tasks, return_exceptions=True)

    def authenticate(self, identity="ipad"):
        self.sender.challenges[identity] = (bytes(16), time.monotonic())
        return self.sender.accept_control(identity, bytes([p.AUTH]) + p.auth_proof(KEY, bytes(16)))

    async def test_valid_auth_and_replay_rejection(self):
        self.assertTrue(self.authenticate())
        self.assertFalse(self.sender.accept_control("ipad", bytes([p.AUTH]) + p.auth_proof(KEY, bytes(16))))

    async def test_wrong_auth(self):
        self.sender.challenges["ipad"] = (bytes(16), time.monotonic())
        self.assertFalse(self.sender.accept_control("ipad", bytes([p.AUTH]) + bytes(16)))
        self.assertIsNone(self.sender.client_id)

    async def test_expired_auth(self):
        self.sender.challenges["ipad"] = (bytes(16), time.monotonic() - 31)
        self.assertFalse(self.sender.accept_control("ipad", bytes([p.AUTH]) + p.auth_proof(KEY, bytes(16))))

    async def test_second_receiver_cannot_replace_active_client(self):
        self.assertTrue(self.authenticate())
        self.sender.data.subscribed_clients.append(SimpleNamespace(session=SimpleNamespace(device_id=SimpleNamespace(id="other"))))
        self.assertFalse(self.authenticate("other"))
        self.assertEqual(self.sender.client_id, "ipad")

    async def test_unauthenticated_control_is_rejected(self):
        self.assertFalse(self.sender.accept_control("ipad", bytes([p.LATEST])))

    async def test_ack_must_match_transfer_and_bounds(self):
        self.assertTrue(self.authenticate())
        self.sender.active_id = 7
        self.sender.sent_offset = 100
        self.assertFalse(self.sender.accept_control("ipad", p.HEADER.pack(p.ACK, 8, 50)))
        self.assertFalse(self.sender.accept_control("ipad", p.HEADER.pack(p.ACK, 7, 101)))
        self.assertTrue(self.sender.accept_control("ipad", p.HEADER.pack(p.ACK, 7, 100)))

    async def test_receipt_requires_end_of_correct_transfer(self):
        self.assertTrue(self.authenticate())
        self.sender.active_id = 7
        receipt = bytes([p.RECEIPT]) + struct.pack("<I", 7) + bytes([3])
        self.assertFalse(self.sender.accept_control("ipad", receipt))
        self.sender.early_receipt = True
        self.assertTrue(self.sender.accept_control("ipad", receipt))

    async def test_stop_revokes_authorization(self):
        self.assertTrue(self.authenticate())
        self.assertTrue(self.sender.accept_control("ipad", bytes([p.STOP])))
        self.assertIsNone(self.sender.client_id)
        self.assertFalse(self.sender.accept_control("ipad", bytes([p.LATEST])))

    async def test_transfer_flow_control_and_receipt(self):
        self.assertTrue(self.authenticate())
        client = self.sender.data.subscribed_clients[0]
        client.max_notification_size = 20
        received = bytearray()
        count = 0
        total = 0
        async def notify(target, frame):
            nonlocal count, total
            self.assertIs(target, client)
            self.assertLessEqual(len(frame), 20)
            kind, transfer_id, value = p.HEADER.unpack_from(frame)
            if kind == p.START:
                total = value
            elif kind == p.CHUNK:
                self.assertEqual(value, len(received))
                received.extend(frame[9:])
                count += 1
                if count % p.WINDOW == 0 or len(received) == total:
                    self.assertTrue(self.sender.accept_control("ipad", p.HEADER.pack(p.ACK, transfer_id, len(received))))
            elif kind == p.END:
                self.assertEqual(len(received), total)
                receipt = bytes([p.RECEIPT]) + struct.pack("<I", transfer_id) + bytes([2])
                self.assertTrue(self.sender.accept_control("ipad", receipt))
        self.sender.notify = notify
        png = bytes(range(256)) * 4
        await self.sender.transfer((png, 40, 30, 123, time.monotonic()), "ipad")
        self.assertEqual(p.open_image(KEY, bytes(received)), (png, 40, 30, 123))
        self.assertIsNone(self.sender.active_id)

    async def test_disconnect_clears_active_transfer(self):
        self.assertTrue(self.authenticate())
        self.sender.data.subscribed_clients[0].max_notification_size = 185
        async def notify(_client, _frame):
            self.sender.client_id = None
        self.sender.notify = notify
        with self.assertRaises(ConnectionError):
            await self.sender.transfer((b"x", 1, 1, 0, time.monotonic()), "ipad")
        self.assertIsNone(self.sender.active_id)

    async def test_native_pipeline_order_window_and_completion(self):
        self.assertTrue(self.authenticate())
        client = self.sender.data.subscribed_clients[0]
        for mtu in (20, 185, 524):
            for depth in (1, 2, 4, 8):
                self.sender.pipeline = depth
                client.max_notification_size = mtu
                received = bytearray()
                total = count = outstanding = peak = 0
                kinds = []
                def notify(buffer, target):
                    nonlocal total, count, outstanding, peak
                    self.assertIs(target, client)
                    frame = as_bytes(buffer)
                    self.assertLessEqual(len(frame), min(mtu, 512))
                    kind, transfer_id, value = p.HEADER.unpack_from(frame)
                    kinds.append(kind)
                    if kind == p.START:
                        self.assertEqual(outstanding, 0)
                        total = value
                    elif kind == p.CHUNK:
                        self.assertEqual(value, len(received))
                        received.extend(frame[9:]); count += 1
                        if count % p.WINDOW == 0 or len(received) == total:
                            self.assertTrue(self.sender.accept_control("ipad", p.HEADER.pack(p.ACK, transfer_id, len(received))))
                    elif kind == p.END:
                        self.assertEqual(outstanding, 0)
                        self.assertEqual(len(received), total)
                        receipt = bytes([p.RECEIPT]) + struct.pack("<I", transfer_id) + bytes([2])
                        self.assertTrue(self.sender.accept_control("ipad", receipt))
                    outstanding += 1; peak = max(peak, outstanding)
                    future = asyncio.get_running_loop().create_future()
                    def complete():
                        nonlocal outstanding
                        outstanding -= 1
                        future.set_result(SimpleNamespace(status=GattCommunicationStatus.SUCCESS))
                    # Vary completion order. Native INVOCATION order must remain unchanged.
                    asyncio.get_running_loop().call_later(0.0001 * (depth - (count % depth)), complete)
                    return future
                self.sender.data.notify_value_for_subscribed_client_async = notify
                png = bytes(range(256)) * 9
                await self.sender.transfer((png, 100, 50, 123, time.monotonic()), "ipad")
                self.assertEqual(p.open_image(KEY, bytes(received)), (png, 100, 50, 123))
                self.assertEqual((kinds[0], kinds[-1]), (p.START, p.END))
                self.assertLessEqual(peak, depth)
                if depth > 1:
                    self.assertEqual(peak, min(depth, count))

    async def test_pipeline_failure_cancels_remaining_waiters(self):
        self.sender.pipeline = 4
        futures = []
        def notify(_buffer, _client):
            future = asyncio.get_running_loop().create_future()
            if not futures:
                future.set_result(SimpleNamespace(status=GattCommunicationStatus.UNREACHABLE))
            futures.append(future)
            return future
        self.sender.data.notify_value_for_subscribed_client_async = notify
        frames = [p.HEADER.pack(p.CHUNK, 7, i) + b"x" for i in range(4)]
        with self.assertRaises(ConnectionError):
            await self.sender.notify_batch(self.sender.data.subscribed_clients[0], frames)
        self.assertTrue(all(future.done() for future in futures))
        self.assertTrue(all(future.cancelled() for future in futures[1:]))

    async def test_pipeline_rejects_oversized_batch(self):
        with self.assertRaises(ValueError):
            await self.sender.notify_batch(None, [b"x", b"y"])

    async def test_settings_deferred_until_transfer_finishes(self):
        self.sender.active_id = 7
        self.sender.configure(quality="original", pipeline=4, target_bytes=40 * 1024)
        self.assertEqual(self.sender.pipeline, 1)
        self.sender.active_id = None
        self.sender.apply_pending_configuration()
        self.assertEqual((self.sender.quality, self.sender.pipeline, self.sender.target_bytes), ("original", 4, 40 * 1024))

    async def test_paused_capture_drops_latest_and_new_publication(self):
        self.sender.latest = (b"x", 1, 1, 0, time.monotonic())
        self.sender.set_capture_paused(True)
        self.assertIsNone(self.sender.latest)
        self.sender.publish((b"y", 1, 1, 0, time.monotonic()))
        self.assertIsNone(self.sender.latest)
        self.sender.set_capture_paused(False)
        self.sender.publish((b"z", 1, 1, 0, time.monotonic()))
        self.assertIsNotNone(self.sender.latest)

    async def test_status_updates_do_not_expose_key(self):
        values = []
        self.sender.on_status = lambda **status: values.append(status)
        self.sender.publish((b"x", 1, 1, 0, time.monotonic()))
        self.assertTrue(values)
        self.assertNotIn(KEY.hex(), str(values))

    async def test_quick_pause_resume_excludes_paused_clipboard(self):
        with patch('sender.ctypes.windll.user32.GetClipboardSequenceNumber', return_value=42):
            self.sender.set_capture_paused(True)
            self.sender.set_capture_paused(False)
            with patch.object(self.sender.stop_monitor, 'wait', side_effect=[False, True]):
                with patch('sender.ImageGrab.grabclipboard') as grab:
                    self.sender.monitor()
                    grab.assert_not_called()
        self.assertIsNone(self.sender.capture_baseline)

    async def test_capture_before_pause_cannot_publish_after_resume(self):
        epoch = self.sender.capture_epoch
        self.sender.set_capture_paused(True)
        with patch('sender.ctypes.windll.user32.GetClipboardSequenceNumber', return_value=42):
            self.sender.set_capture_paused(False)
        self.sender.publish((b'x', 1, 1, 0, time.monotonic()), epoch)
        self.assertIsNone(self.sender.latest)
        self.assertFalse(self.sender.pending.is_set())

    async def test_oversized_image_does_not_leave_active_transfer(self):
        self.assertTrue(self.authenticate())
        client = self.sender.data.subscribed_clients[0]
        client.max_notification_size = 185
        with self.assertRaises(ValueError):
            await self.sender.transfer((bytes(p.MAX_PNG + 1), 1, 1, 0, time.monotonic()), "ipad")
        self.assertIsNone(self.sender.active_id)


if __name__ == "__main__":
    unittest.main()
