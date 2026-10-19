"""BLE service, authentication, flow control and encrypted clipboard delivery."""
import asyncio
import hmac
import logging
import secrets
import time

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

from ble import protocol as p
from ble.buffers import as_buffer, as_bytes, device_id
from clipboard.image_codec import DEFAULT_TARGET_BYTES
from clipboard.monitor import ClipboardMonitor
from clipboard.models import Snapshot

LOG = logging.getLogger("clipbridge")


class Sender:
    """Coordinate one authenticated iPad and the latest in-memory snapshot.

    Clipboard polling belongs to ``capture``; all GATT/session state below is
    confined to the asyncio worker. No UI or clipboard API calls live here.
    """

    def __init__(
        self, key, *, pipeline=4, quality="balanced", target_bytes=DEFAULT_TARGET_BYTES,
        sync_text=True, on_status=None,
    ):
        if pipeline not in (1, 2, 4, 8):
            raise ValueError("Pipeline must be 1, 2, 4 or 8")
        self.key = key
        self.pipeline = pipeline
        self.quality = quality
        self.target_bytes = target_bytes
        if type(sync_text) is not bool:
            raise ValueError("Text sync setting must be boolean")
        self.on_status = on_status
        self.pending_configuration = None
        self.loop = asyncio.get_running_loop()
        self.provider = self.info = self.control = self.data = None
        self.tokens = []
        self.tasks = set()
        self.challenges = {}
        self.client_id = None
        self.authenticated = set()
        self.text_clients = set()
        self.latest = None
        self.pending = asyncio.Event()
        self.progress = asyncio.Event()
        self.received = asyncio.Event()
        self.acked = 0
        self.sent_offset = 0
        self.active_id = None
        self.early_receipt = False
        self.capture = ClipboardMonitor(
            key, self.loop, self.publish, lambda: (self.quality, self.target_bytes), sync_text=sync_text
        )

    def report(self, **values):
        if self.on_status is not None:
            try:
                self.on_status(**values)
            except Exception:
                LOG.exception("Status callback failed")

    def configure(self, *, quality, pipeline, target_bytes, sync_text=None):
        if quality not in ("balanced", "original") or pipeline not in (1, 2, 4, 8) or not 16 * 1024 <= target_bytes <= 128 * 1024:
            raise ValueError("Invalid sender settings")
        if sync_text is not None and type(sync_text) is not bool:
            raise ValueError("Text sync setting must be boolean")
        self.pending_configuration = (quality, pipeline, target_bytes)
        if sync_text is not None and self.capture.set_text_enabled(sync_text):
            if self.latest is not None and self.latest.kind == "text":
                self.latest = None
                self.pending.clear()
        if self.active_id is None:
            self.apply_pending_configuration()

    def apply_pending_configuration(self):
        if self.pending_configuration is not None:
            self.quality, self.pipeline, self.target_bytes = self.pending_configuration
            self.pending_configuration = None
            self.report(pipeline=self.pipeline)

    def set_capture_paused(self, value):
        self.capture.set_paused(value)
        if value:
            self.latest = None
            self.pending.clear()
        self.report(paused=bool(value))

    def schedule(self, coroutine):
        task = self.loop.create_task(coroutine)
        self.tasks.add(task)
        task.add_done_callback(self.tasks.discard)

    # Service lifecycle and native callback handoff.

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
        self.data = await self.characteristic(p.DATA, Properties.NOTIFY, "ClipBridge encrypted clipboard")
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

    # Authenticated control frames: capability, ACK, receipt, resend and stop.

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
            self.text_clients.discard(identity)
            self.schedule(self.ready(identity))
            return True
        if identity != self.client_id or identity not in self.authenticated:
            return False
        if command == p.CAPABILITIES:
            if len(raw) != 2 or raw[1] != p.TEXT_CAPABILITY or not self.subscribed(identity):
                return False
            self.text_clients.add(identity)
            LOG.info("iPad text capability negotiated")
            if self.latest is not None and self.latest.kind == "text":
                self.pending.set()
            return True
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
            self.text_clients.discard(identity)
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
                await self.notify(client, p.HEADER.pack(p.READY, 0, p.WINDOW | p.READY_TEXT))
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
            self.text_clients.discard(self.client_id)
            self.client_id = None
            self.report(phase="waiting", detail="iPad 已断开，等待重新连接")
            self.progress.set()
            self.received.set()

    # Ordered notification pipeline; completion order never changes wire order.

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

    # Capture-to-transport handoff and one-payload-at-a-time delivery.

    def publish(self, snapshot: Snapshot, epoch: int | None = None):
        """Accept capture-thread output only if its pause/settings epoch is current."""
        if self.capture.paused.is_set() or (epoch is not None and epoch != self.capture.epoch):
            return
        if snapshot.kind == "text" and not self.capture.sync_text:
            return
        self.latest = snapshot
        if snapshot.kind == "text":
            summary = f"文字，{len(snapshot.data)} 字节（不显示正文）"
        else:
            summary = f"图片 {snapshot.width} × {snapshot.height}，{len(snapshot.data) / 1024:.1f} KiB"
        self.report(last_content=summary)
        self.pending.set()

    async def transfer(self, snapshot: Snapshot, identity):
        """Encrypt one snapshot, deliver ordered frames, and await a write-attempt receipt."""
        if snapshot.kind == "text" and identity not in self.text_clients:
            raise ValueError("Receiver has not negotiated text support; update the iPad receiver")
        client = self.subscribed(identity)
        if client is None:
            raise ConnectionError("Receiver is no longer subscribed")
        transfer_id = secrets.randbits(32)
        if snapshot.kind == "text":
            wire = p.seal_text(self.key, snapshot.data.decode("utf-8"), snapshot.captured_ms)
        else:
            wire = p.seal_image(self.key, snapshot.data, snapshot.width, snapshot.height, snapshot.captured_ms)
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
        self.report(phase="sending", detail="正在发送文字" if snapshot.kind == "text" else "正在发送截图", error="", pipeline=self.pipeline)
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
            elapsed = time.monotonic() - snapshot.detected
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
            if self.latest is None or self.client_id is None or self.capture.paused.is_set():
                continue
            snapshot, identity = self.latest, self.client_id
            if snapshot.kind == "text" and identity not in self.text_clients:
                self.report(phase="connected", detail="文字待发送：请更新 iPad 接收端并连接", error="")
                continue
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
        self.capture.stop.set()
        if self.provider is not None:
            self.provider.stop_advertising()
        for obj, event, token in self.tokens:
            getattr(obj, "remove_" + event)(token)
        for task in list(self.tasks):
            task.cancel()
        if self.tasks:
            await asyncio.gather(*self.tasks, return_exceptions=True)
        self.latest = None
