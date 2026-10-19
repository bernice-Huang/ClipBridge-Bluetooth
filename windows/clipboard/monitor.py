"""Polling, pause boundaries and in-memory clipboard encoding (no BLE calls)."""
import hashlib
import logging
import threading
import time

from PIL import Image, ImageGrab

from ble import protocol as p
from clipboard.image_codec import encode_image
from clipboard.models import Snapshot
from clipboard.text import read_text
from windows_api import clipboard_sequence

LOG = logging.getLogger("clipbridge")


class ClipboardMonitor:
    """Own capture-thread state; publish immutable snapshots onto the event loop."""

    def __init__(self, key, loop, publish, image_options, *, sync_text=True):
        if type(sync_text) is not bool:
            raise ValueError("Text sync setting must be boolean")
        self.key = key
        self.loop = loop
        self.publish = publish
        self.image_options = image_options
        self.sync_text = sync_text
        self.stop = threading.Event()
        self.paused = threading.Event()
        self.lock = threading.Lock()
        self.epoch = 0
        self.baseline = None

    def set_paused(self, value):
        with self.lock:
            if bool(value) != self.paused.is_set():
                self.epoch += 1
                if value:
                    self.paused.set()
                else:
                    # Do not capture clipboard contents copied while paused.
                    self.baseline = clipboard_sequence()
                    self.paused.clear()

    def set_text_enabled(self, value):
        if type(value) is not bool:
            raise ValueError("Text sync setting must be boolean")
        with self.lock:
            if value == self.sync_text:
                return False
            self.sync_text = value
            self.epoch += 1
            self.baseline = clipboard_sequence()
            return True

    def run(self):
        sequence = clipboard_sequence()
        last_digest = None
        previous_epoch = self.epoch
        while not self.stop.wait(0.15):
            with self.lock:
                current = clipboard_sequence()
                if self.baseline is not None:
                    sequence = self.baseline
                    self.baseline = None
                epoch = self.epoch
                if epoch != previous_epoch:
                    last_digest = None
                    previous_epoch = epoch
                if self.paused.is_set():
                    sequence = current
                    continue
            if current == sequence:
                continue
            detected = time.monotonic()
            captured_ms = int(time.time() * 1000)
            try:
                image = ImageGrab.grabclipboard()
                if not isinstance(image, Image.Image):
                    if not isinstance(image, list) and self.sync_text:
                        text = read_text()
                        if clipboard_sequence() != current:
                            continue
                        if text:
                            if self.key.hex() in text.lower():
                                LOG.info("Text containing the pairing key was not sent")
                            else:
                                encoded_text = text.encode("utf-8")
                                self.loop.call_soon_threadsafe(self.publish,
                                    Snapshot(encoded_text, 0, 0, captured_ms, detected, "text"), epoch)
                                LOG.info("New clipboard text: %s UTF-8 bytes (memory only; content not logged)", len(encoded_text))
                    last_digest = None
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
                    quality, target_bytes = self.image_options()
                    encoded = encode_image(image, quality=quality, target_bytes=target_bytes)
                encode_ms = (time.monotonic() - encode_started) * 1000
                png, width, height = encoded.png, encoded.width, encoded.height
                if clipboard_sequence() != current:
                    continue
                digest = hashlib.sha256(png).digest()
                if digest != last_digest:
                    # Validate bounds before queuing or encrypting.
                    if len(png) > p.MAX_PNG or width > 8192 or height > 8192 or width * height > 32_000_000:
                        LOG.warning("Screenshot too large: %sx%s, %s bytes; use a smaller region", width, height, len(png))
                    else:
                        self.loop.call_soon_threadsafe(self.publish, Snapshot(png, width, height, captured_ms, detected), epoch)
                        LOG.info("New screenshot: %sx%s -> %sx%s; original=%.1f KiB, send=%.1f KiB; mode=%s; encode=%.0fms (memory only)",
                                 source_width, source_height, width, height, encoded.original_bytes / 1024,
                                 len(png) / 1024, encoded.method, encode_ms)
                        if not encoded.target_met:
                            LOG.info("PNG remains above %.1f KiB target to preserve legibility; under-3s is not guaranteed", target_bytes / 1024)
                        last_digest = digest
                sequence = current
            except ValueError:
                LOG.warning("Clipboard content is invalid or exceeds supported limits; not sent")
                sequence = current
                last_digest = None
            except Exception as error:
                # Clipboard locks are transient. Retry the SAME sequence later.
                LOG.debug("Clipboard temporarily unavailable: %s", type(error).__name__)
