"""Windows BLE prototype. Captures NEW clipboard images only; no image files."""
import argparse
import asyncio
import ctypes
from ctypes import wintypes
import hashlib
import hmac
import json
import logging
from pathlib import Path
import secrets
import threading
import time

from PIL import Image, ImageGrab
from winrt.windows.devices.bluetooth import BluetoothAdapter, BluetoothError
from winrt.windows.devices.bluetooth.genericattributeprofile import (
    GattCharacteristicProperties as Properties,
    GattCommunicationStatus,
    GattLocalCharacteristicParameters,
    GattProtectionLevel,
    GattServiceProvider,
    GattServiceProviderAdvertisingParameters,
    GattServiceProviderAdvertisementStatus,
    GattWriteOption,
)
from winrt.windows.storage.streams import DataReader, DataWriter

import protocol as p
from image_codec import DEFAULT_TARGET_BYTES, encode_image
from runtime import pairing_key, VERSION

LOG = logging.getLogger("clipbridge")

# Windows handles are pointer-sized. ctypes defaults to a 32-bit return value.
ctypes.windll.kernel32.CreateMutexW.argtypes = [ctypes.c_void_p, wintypes.BOOL, wintypes.LPCWSTR]
ctypes.windll.kernel32.CreateMutexW.restype = wintypes.HANDLE
ctypes.windll.kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
ctypes.windll.kernel32.CloseHandle.restype = wintypes.BOOL
ctypes.windll.kernel32.GetLastError.restype = wintypes.DWORD
ctypes.windll.user32.GetClipboardSequenceNumber.restype = wintypes.DWORD


def as_buffer(data):
    writer = DataWriter()
    try:
        writer.write_bytes(data)
        return writer.detach_buffer()
    finally:
        writer.close()


def as_bytes(buffer):
    reader = DataReader.from_buffer(buffer)
    try:
        data = bytearray(buffer.length)
        reader.read_bytes(data)
        return bytes(data)
    finally:
        reader.close()


def device_id(session):
    return session.device_id.id


def load_key(path):
    if path.exists():
        key = bytes.fromhex(json.loads(path.read_text(encoding="utf-8"))["key"])
        if len(key) != 16:
            raise ValueError("Invalid session key; do not overwrite the existing session.json")
        return key
    key = secrets.token_bytes(16)
    # Only a pairing secret is persisted; PNG bytes are never written to disk.
    with path.open("x", encoding="utf-8") as target:
        json.dump({"protocol": 1, "key": key.hex()}, target)
    return key


class Sender:
    def __init__(self, key, *, pipeline=4, quality="balanced", target_bytes=DEFAULT_TARGET_BYTES, on_status=None):
        if pipeline not in (1, 2, 4, 8):
            raise ValueError("Pipeline must be 1, 2, 4 or 8")
        self.key = key
        self.pipeline = pipeline
        self.quality = quality
        self.target_bytes = target_bytes
        self.on_status = on_status
        self.pending_configuration = None
        self.loop = asyncio.get_running_loop()
        self.provider = self.info = self.control = self.data = None
        self.tokens = []
        self.tasks = set()
        self.challenges = {}
        self.client_id = None
        self.authenticated = set()
        self.latest = None
        self.pending = asyncio.Event()
        self.progress = asyncio.Event()
        self.received = asyncio.Event()
        self.acked = 0
        self.sent_offset = 0
        self.active_id = None
        self.early_receipt = False
        self.stop_monitor = threading.Event()
        self.capture_paused = threading.Event()
        self.capture_lock = threading.Lock()
        self.capture_epoch = 0
        self.capture_baseline = None

    def report(self, **values):
        if self.on_status is not None:
            try:
                self.on_status(**values)
            except Exception:
                LOG.exception("Status callback failed")

    def configure(self, *, quality, pipeline, target_bytes):
        if quality not in ("balanced", "original") or pipeline not in (1, 2, 4, 8) or not 16 * 1024 <= target_bytes <= 128 * 1024:
            raise ValueError("Invalid sender settings")
        self.pending_configuration = (quality, pipeline, target_bytes)
        if self.active_id is None:
            self.apply_pending_configuration()

    def apply_pending_configuration(self):
        if self.pending_configuration is not None:
            self.quality, self.pipeline, self.target_bytes = self.pending_configuration
            self.pending_configuration = None
            self.report(pipeline=self.pipeline)

    def set_capture_paused(self, value):
        with self.capture_lock:
            if bool(value) != self.capture_paused.is_set():
                self.capture_epoch += 1
                if value:
                    self.capture_paused.set()
                    self.latest = None
                    self.pending.clear()
                else:
                    # Also exclude images captured during a pause shorter than
                    # the monitor's polling interval, and discard queued work.
                    self.capture_baseline = ctypes.windll.user32.GetClipboardSequenceNumber()
                    self.capture_paused.clear()
        self.report(paused=bool(value))

    def schedule(self, coroutine):
        task = self.loop.create_task(coroutine)
        self.tasks.add(task)
        task.add_done_callback(self.tasks.discard)

    async def characteristic(self, uuid, properties, description):
        options = GattLocalCharacteristicParameters()
        options.characteristic_properties = properties
        # Payload is encrypted at application level; Windows Bluetooth pairing is not required.
        options.read_protection_level = GattProtectionLevel.PLAIN
        options.write_protection_level = GattProtectionLevel.PLAIN
        options.user_description = description
        result = await self.provider.service.create_characteristic_async(uuid, options)
        if result.error != BluetoothError.SUCCESS:
            raise RuntimeError(f"Characteristic {description}: {result.error.name}")
        return result.characteristic

    async def start(self):
        adapter = await BluetoothAdapter.get_default_async()
        if adapter is None or not adapter.is_peripheral_role_supported:
            raise RuntimeError("This Bluetooth adapter does not support BLE peripheral mode")
        result = await GattServiceProvider.create_async(p.SERVICE)
        if result.error != BluetoothError.SUCCESS:
            raise RuntimeError(f"GATT service creation failed: {result.error.name}")
        self.provider = result.service_provider
        self.info = await self.characteristic(p.INFO, Properties.READ, "ClipBridge challenge")
        self.control = await self.characteristic(p.CONTROL, Properties.WRITE, "ClipBridge control")
        self.data = await self.characteristic(p.DATA, Properties.NOTIFY, "ClipBridge encrypted image")
        self.tokens.extend([
            (self.info, "read_requested", self.info.add_read_requested(self.on_read)),
            (self.control, "write_requested", self.control.add_write_requested(self.on_write)),
            (self.data, "subscribed_clients_changed", self.data.add_subscribed_clients_changed(self.on_clients)),
        ])
        options = GattServiceProviderAdvertisingParameters()
        options.is_connectable = True
        options.is_discoverable = True
        self.provider.start_advertising_with_parameters(options)
        await asyncio.sleep(1)
        status = self.provider.advertisement_status
        if status != GattServiceProviderAdvertisementStatus.STARTED:
            raise RuntimeError(f"BLE advertisement failed: {status.name}")
        LOG.info("BLE advertisement started; waiting for iPad (no IP address required).")
        self.report(phase="waiting", detail="等待 iPad 连接", error="")

    def on_read(self, _sender, args):
        deferral = args.get_deferral()
        self.loop.call_soon_threadsafe(self.schedule, self.read_request(args, deferral))

    async def read_request(self, args, deferral):
        try:
            request = await args.get_request_async()
            if request is None:
                return
            if request.offset:
                request.respond_with_protocol_error(7)
                return
            identity = device_id(args.session)
            if len(self.challenges) >= 16:
                self.challenges.clear()
            challenge = secrets.token_bytes(16)
            self.challenges[identity] = (challenge, time.monotonic())
            request.respond_with_value(as_buffer(b"CB1" + challenge))
        except Exception:
            LOG.exception("GATT challenge read failed")
        finally:
            deferral.complete()

    def on_write(self, _sender, args):
        deferral = args.get_deferral()
        self.loop.call_soon_threadsafe(self.schedule, self.write_request(args, deferral))

    async def write_request(self, args, deferral):
        try:
            request = await args.get_request_async()
            if request is None:
                return
            raw = as_bytes(request.value)
            if request.offset or not (1 <= len(raw) <= 20):
                if request.option == GattWriteOption.WRITE_WITH_RESPONSE:
                    request.respond_with_protocol_error(13)
                return
            identity = device_id(args.session)
            accepted = self.accept_control(identity, raw)
            if request.option == GattWriteOption.WRITE_WITH_RESPONSE:
                if accepted:
                    request.respond()
                else:
                    request.respond_with_protocol_error(8)
        except Exception:
            LOG.exception("GATT control write failed")
        finally:
            deferral.complete()

    def accept_control(self, identity, raw):
        command = raw[0]
        if command == p.AUTH and len(raw) == 17:
            item = self.challenges.pop(identity, None)
            if item is None or time.monotonic() - item[1] > 30:
                return False
            if not hmac.compare_digest(raw[1:], p.auth_proof(self.key, item[0])):
                LOG.warning("iPad pairing key rejected")
                return False
            # Never replace an actively subscribed receiver with a different device.
            if self.client_id and self.client_id != identity and self.subscribed(self.client_id):
                return False
            if not self.subscribed(identity):
                return False
            self.client_id = identity
            self.authenticated.add(identity)
            self.schedule(self.ready(identity))
            return True
        if identity != self.client_id or identity not in self.authenticated:
            return False
        if command == p.ACK and len(raw) == p.HEADER.size:
            _, transfer_id, offset = p.HEADER.unpack(raw)
            if transfer_id == self.active_id and self.acked <= offset <= self.sent_offset:
                self.acked = offset
                self.progress.set()
                return True
            return False
        if command == p.RECEIPT and len(raw) == 6:
            transfer_id = int.from_bytes(raw[1:5], "little")
            if transfer_id != self.active_id or not self.early_receipt:
                return False
            flags = raw[5]
            if flags & ~3:
                return False
            LOG.info("iPad receipt: background=%s clipboard_write_attempt=%s (paste needs manual verification)", bool(flags & 1), bool(flags & 2))
            self.report(last_receipt=f"{'后台' if flags & 1 else '前台/切换中'}收到；{'已尝试写剪贴板' if flags & 2 else '未报告写入'}")
            self.received.set()
            return True
        if command == p.LATEST and len(raw) == 1:
            self.pending.set()
            return True
        if command == p.STOP and len(raw) == 1:
            self.authenticated.discard(identity)
            self.client_id = None
            self.report(phase="waiting", detail="iPad 已停止接收，等待连接")
            self.progress.set()
            self.received.set()
            return True
        return False

    def subscribed(self, identity):
        return next((c for c in self.data.subscribed_clients if device_id(c.session) == identity), None)

    async def ready(self, identity):
        try:
            client = self.subscribed(identity)
            if client is not None and identity == self.client_id:
                await self.notify(client, p.HEADER.pack(p.READY, 0, p.WINDOW))
                LOG.info("iPad authenticated; max notification value = %s bytes", client.max_notification_size)
                self.report(phase="connected", detail="iPad 已连接", error="", pipeline=self.pipeline)
                self.pending.set()
        except Exception:
            LOG.exception("Unable to send ready response")

    def on_clients(self, _sender, _args):
        self.loop.call_soon_threadsafe(self.refresh_clients)

    def refresh_clients(self):
        if self.client_id and self.subscribed(self.client_id) is None:
            LOG.info("iPad disconnected; will require a fresh authentication on reconnect")
            self.authenticated.discard(self.client_id)
            self.client_id = None
            self.report(phase="waiting", detail="iPad 已断开，等待重新连接")
            self.progress.set()
            self.received.set()

    @staticmethod
    async def notification_completed(operation):
        result = await operation
        if result.status != GattCommunicationStatus.SUCCESS:
            raise ConnectionError(f"Notification failed: {result.status.name}")

    async def notify(self, client, data):
        operation = self.data.notify_value_for_subscribed_client_async(as_buffer(data), client)
        await asyncio.wait_for(self.notification_completed(operation), 4)

    async def notify_batch(self, client, frames):
        """Issue native calls in frame order; keep at most pipeline operations alive.

        START and END are still sent serially. The existing 32-packet receiver
        window remains unchanged. Completion order does not determine data order.
        """
        if len(frames) > self.pipeline:
            raise ValueError("Notification batch exceeds pipeline limit")
        if self.pipeline == 1:
            for frame in frames:
                await self.notify(client, frame)
            return
        operations = []
        try:
            for frame in frames:
                # Start the WinRT operation NOW, not in unordered worker threads.
                operation = self.data.notify_value_for_subscribed_client_async(as_buffer(frame), client)
                operations.append(asyncio.create_task(self.notification_completed(operation)))
            await asyncio.wait_for(asyncio.gather(*operations), 4)
        except TimeoutError as error:
            raise ConnectionError("Notification pipeline completion timed out") from error
        finally:
            for operation in operations:
                if not operation.done():
                    operation.cancel()
            if operations:
                await asyncio.gather(*operations, return_exceptions=True)

    def publish(self, snapshot, epoch=None):
        if self.capture_paused.is_set() or (epoch is not None and epoch != self.capture_epoch):
            return
        self.latest = snapshot
        self.report(last_image=f"{snapshot[1]} × {snapshot[2]}，{len(snapshot[0]) / 1024:.1f} KiB")
        self.pending.set()

    def monitor(self):
        sequence = ctypes.windll.user32.GetClipboardSequenceNumber()
        last_digest = None
        previous_epoch = self.capture_epoch
        while not self.stop_monitor.wait(0.15):
            with self.capture_lock:
                current = ctypes.windll.user32.GetClipboardSequenceNumber()
                if self.capture_baseline is not None:
                    sequence = self.capture_baseline
                    self.capture_baseline = None
                epoch = self.capture_epoch
                if epoch != previous_epoch:
                    last_digest = None
                    previous_epoch = epoch
                if self.capture_paused.is_set():
                    sequence = current
                    continue
            if current == sequence:
                continue
            detected = time.monotonic()
            captured_ms = int(time.time() * 1000)
            try:
                image = ImageGrab.grabclipboard()
                if not isinstance(image, Image.Image):
                    sequence = current
                    continue
                source_width, source_height = image.size
                if source_width > 8192 or source_height > 8192 or source_width * source_height > 32_000_000:
                    image.close()
                    LOG.warning("Screenshot dimensions exceed prototype bounds: %sx%s", source_width, source_height)
                    sequence = current
                    continue
                encode_started = time.monotonic()
                with image:
                    encoded = encode_image(image, quality=self.quality, target_bytes=self.target_bytes)
                encode_ms = (time.monotonic() - encode_started) * 1000
                png, width, height = encoded.png, encoded.width, encoded.height
                digest = hashlib.sha256(png).digest()
                if digest != last_digest:
                    # Validate bounds before queuing or encrypting.
                    if len(png) > p.MAX_PNG or width > 8192 or height > 8192 or width * height > 32_000_000:
                        LOG.warning("Screenshot too large: %sx%s, %s bytes; use a smaller region", width, height, len(png))
                    else:
                        self.loop.call_soon_threadsafe(self.publish, (png, width, height, captured_ms, detected), epoch)
                        LOG.info("New screenshot: %sx%s -> %sx%s; original=%.1f KiB, send=%.1f KiB; mode=%s; encode=%.0fms (memory only)",
                                 source_width, source_height, width, height, encoded.original_bytes / 1024,
                                 len(png) / 1024, encoded.method, encode_ms)
                        if not encoded.target_met:
                            LOG.info("PNG remains above %.1f KiB target to preserve legibility; under-3s is not guaranteed", self.target_bytes / 1024)
                        last_digest = digest
                sequence = current
            except Exception as error:
                # Clipboard locks are transient. Retry the SAME sequence later.
                LOG.debug("Clipboard temporarily unavailable: %s", error)

    async def transfer(self, snapshot, identity):
        png, width, height, captured_ms, detected = snapshot
        client = self.subscribed(identity)
        if client is None:
            raise ConnectionError("Receiver is no longer subscribed")
        transfer_id = secrets.randbits(32)
        wire = p.seal_image(self.key, png, width, height, captured_ms)
        self.active_id = transfer_id
        self.acked = self.sent_offset = 0
        self.early_receipt = False
        self.progress.clear()
        self.received.clear()
        started = time.monotonic()
        packets = 0
        notify_seconds = 0.0
        ack_seconds = 0.0
        batch = []
        last_progress = started
        LOG.info("Transfer start: %.1f KiB, max_notification=%s, pipeline=%s", len(wire) / 1024, client.max_notification_size, self.pipeline)
        self.report(phase="sending", detail="正在发送截图", error="", pipeline=self.pipeline)
        try:
            for frame in p.frames(transfer_id, wire, int(client.max_notification_size)):
                if self.client_id != identity or identity not in self.authenticated:
                    raise ConnectionError("Receiver disconnected or stopped")
                kind, _, offset = p.HEADER.unpack_from(frame)
                if kind == p.CHUNK:
                    batch.append(frame)
                    packets += 1
                    if len(batch) < self.pipeline and packets % p.WINDOW != 0 and offset + len(frame) - p.HEADER.size < len(wire):
                        continue
                    # An ACK can arrive before queued native operations complete.
                    self.sent_offset = offset + len(frame) - p.HEADER.size
                    notify_started = time.monotonic()
                    try:
                        await self.notify_batch(client, batch)
                    finally:
                        notify_seconds += time.monotonic() - notify_started
                    batch.clear()
                    if packets % p.WINDOW == 0 or self.sent_offset == len(wire):
                        ack_started = time.monotonic()
                        try:
                            while self.acked < self.sent_offset:
                                self.progress.clear()
                                if self.client_id != identity:
                                    raise ConnectionError("Receiver disconnected during ACK wait")
                                await asyncio.wait_for(self.progress.wait(), 4)
                        finally:
                            ack_seconds += time.monotonic() - ack_started
                        now = time.monotonic()
                        if now - last_progress >= 1:
                            LOG.info("Transfer progress: acknowledged %.1f/%.1f KiB, %.1fs, %.1f KiB/s",
                                     self.acked / 1024, len(wire) / 1024, now - started,
                                     self.acked / 1024 / max(now - started, 0.001))
                            last_progress = now
                else:
                    if kind == p.END:
                        self.early_receipt = True
                    notify_started = time.monotonic()
                    try:
                        await self.notify(client, frame)
                    finally:
                        notify_seconds += time.monotonic() - notify_started
                if time.monotonic() - started > 20:
                    raise TimeoutError("Transfer exceeded the prototype's 20-second limit")
            await asyncio.wait_for(self.received.wait(), 4)
            if self.client_id != identity:
                raise ConnectionError("Receiver disconnected before receipt")
            elapsed = time.monotonic() - detected
            LOG.info("Receipt %.3fs after clipboard detection; BLE transfer %.3fs; under-3s=%s (not proof of successful paste)", elapsed, time.monotonic() - started, elapsed <= 3)
            self.report(phase="connected", detail=f"已收到回执，用时 {elapsed:.2f} 秒（请实际粘贴确认）", last_seconds=elapsed)
        finally:
            elapsed_transfer = time.monotonic() - started
            LOG.info("Transfer stats: submitted=%.1f/%.1f KiB, acknowledged=%.1f KiB, notify_wait=%.3fs, ack_wait=%.3fs, elapsed=%.3fs, rate=%.1f KiB/s, pipeline=%s",
                     self.sent_offset / 1024, len(wire) / 1024, self.acked / 1024,
                     notify_seconds, ack_seconds, elapsed_transfer,
                     self.acked / 1024 / max(elapsed_transfer, 0.001), self.pipeline)
            self.active_id = None
            self.early_receipt = False
            self.apply_pending_configuration()

    async def run(self):
        while True:
            await self.pending.wait()
            self.pending.clear()
            if self.latest is None or self.client_id is None or self.capture_paused.is_set():
                continue
            snapshot, identity = self.latest, self.client_id
            try:
                await self.transfer(snapshot, identity)
            except Exception as error:
                LOG.warning("Transfer not completed: %s. Reconnect or tap Receive latest on iPad.", error)
                self.report(phase="error", detail="传输未完成，请检查 iPad 或重试", error=str(error))
                if isinstance(error, ConnectionError) and self.pipeline > 1:
                    self.pipeline = 1
                    LOG.warning("Switched to sequential compatibility mode for this run. Reconnect iPad and try again.")
                    self.report(pipeline=1)

    async def close(self):
        self.stop_monitor.set()
        if self.provider is not None:
            self.provider.stop_advertising()
        for obj, event, token in self.tokens:
            getattr(obj, "remove_" + event)(token)
        for task in list(self.tasks):
            task.cancel()
        if self.tasks:
            await asyncio.gather(*self.tasks, return_exceptions=True)
        self.latest = None


async def main(options):
    key = pairing_key()
    print(f"\nClipBridge Bluetooth {VERSION} — adaptive PNG / ordered notification pipeline.")
    print(f"Quality={options.quality}, target={options.target_kib} KiB, pipeline={options.pipeline}. Keep the pairing key private.")
    if not options.smoke:
        print(f"Pairing key for iPad: {key.hex()}\n", flush=True)
    print("Enable Bluetooth on iPad, open the supplied Swift Playgrounds project, paste the key and tap Connect.")
    print("Only screenshots taken AFTER this program starts are captured. Ctrl+C exits.\n", flush=True)
    sender = Sender(key, pipeline=options.pipeline, quality=options.quality, target_bytes=options.target_kib * 1024)
    thread = None
    try:
        await sender.start()
        if options.smoke:
            await asyncio.sleep(options.smoke)
            return
        thread = threading.Thread(target=sender.monitor, name="clipboard-monitor", daemon=True)
        thread.start()
        await sender.run()
    finally:
        await sender.close()
        if thread is not None:
            thread.join(timeout=2)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--smoke", type=float, default=0, help="Test GATT setup for N seconds without reading the clipboard")
    parser.add_argument("--quality", choices=("balanced", "original"), default="balanced", help="Balanced allows moderate palette/size reduction; original keeps pixels")
    parser.add_argument("--pipeline", type=int, choices=(1, 2, 4, 8), default=4, help="Maximum outstanding ordered notifications; 1 is compatibility mode")
    parser.add_argument("--target-kib", type=int, choices=range(16, 129), default=32, metavar="16..128", help="Soft PNG size target; legibility limits take priority")
    options = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    # Different mutex from network V2. Never run two Bluetooth prototype senders.
    mutex = ctypes.windll.kernel32.CreateMutexW(None, False, "Local\\ClipBridgeBluetoothPrototype")
    if not mutex or ctypes.windll.kernel32.GetLastError() == 183:
        print("A Bluetooth prototype is already running. Close that window first.")
        raise SystemExit(2)
    try:
        asyncio.run(main(options))
    except KeyboardInterrupt:
        print("\nClipBridge Bluetooth stopped; no screenshot files were saved.")
    except Exception as error:
        LOG.exception("Startup/runtime failure: %s", error)
        raise SystemExit(1)
    finally:
        ctypes.windll.kernel32.CloseHandle(mutex)
