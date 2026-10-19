"""Command-line diagnostic sender; desktop users should run launcher.py."""
import argparse
import asyncio
import ctypes
import logging
import threading

from app.runtime import pairing_key, VERSION
from ble.sender import Sender
from windows_api import MUTEX_NAME

LOG = logging.getLogger("clipbridge")


async def main(options):
    key = pairing_key()
    print(f"\nClipBridge Bluetooth {VERSION} — adaptive PNG / ordered notification pipeline.")
    print(f"Quality={options.quality}, target={options.target_kib} KiB, pipeline={options.pipeline}. Keep the pairing key private.")
    if not options.smoke:
        print(f"Pairing key for iPad: {key.hex()}\n", flush=True)
    print("Enable Bluetooth on iPad, open the supplied Swift Playgrounds project, paste the key and tap Connect.")
    print("Only NEW clipboard images/plain text are captured. Text requires the updated iPad receiver. Ctrl+C exits.\n", flush=True)
    sender = Sender(key, pipeline=options.pipeline, quality=options.quality, target_bytes=options.target_kib * 1024)
    thread = None
    try:
        await sender.start()
        if options.smoke:
            await asyncio.sleep(options.smoke)
            return
        thread = threading.Thread(target=sender.capture.run, name="clipboard-monitor", daemon=True)
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
    mutex = ctypes.windll.kernel32.CreateMutexW(None, False, MUTEX_NAME)
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
