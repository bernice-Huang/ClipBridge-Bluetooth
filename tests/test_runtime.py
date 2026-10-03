from dataclasses import replace
import io
import json
import logging
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "windows"))
from runtime import Settings, Status, SecretFilter, pairing_key


class RuntimeTests(unittest.TestCase):
    def test_migrate_key_and_keep_existing_destination(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder); legacy = root / "legacy.json"; target = root / "data"
            original = bytes(range(16))
            legacy.write_text(json.dumps({"key": original.hex()}), encoding="utf-8")
            self.assertEqual(pairing_key(target, legacy), original)
            legacy.write_text(json.dumps({"key": bytes(16).hex()}), encoding="utf-8")
            self.assertEqual(pairing_key(target, legacy), original)

    def test_invalid_existing_key_is_not_overwritten(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "session.json"; path.write_text("invalid", encoding="utf-8")
            with self.assertRaises(ValueError):
                pairing_key(folder)
            self.assertEqual(path.read_text(encoding="utf-8"), "invalid")

    def test_key_is_stable_when_new_folder_initialized(self):
        with tempfile.TemporaryDirectory() as folder:
            missing = Path(folder) / "missing.json"
            first = pairing_key(folder, missing)
            self.assertEqual(len(first), 16)
            self.assertEqual(first, pairing_key(folder, missing))

    def test_settings_save_and_load(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "settings.json"
            expected = Settings(quality="original", pipeline=1, target_kib=40, paused=True)
            expected.save(path)
            self.assertEqual(Settings.load(path), expected)
            self.assertEqual(list(Path(folder).glob("*.tmp")), [])

    def test_settings_invalid_values_rejected(self):
        for values in ({"quality": "bad"}, {"pipeline": 3}, {"pipeline": True}, {"paused": "false"}, {"target_kib": 1}):
            with self.assertRaises(ValueError):
                Settings(**values)

    def test_bad_settings_do_not_silently_enable_capture(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "settings.json"; path.write_text("bad", encoding="utf-8")
            with self.assertRaises(ValueError):
                Settings.load(path)
            self.assertEqual(path.read_text(encoding="utf-8"), "bad")

    def test_snapshot_is_independent(self):
        status = Status(); status.update(phase="connected")
        first = status.snapshot(); first["phase"] = "wrong"
        self.assertEqual(status.snapshot()["phase"], "connected")

    def test_log_secret_is_redacted(self):
        key = bytes(range(16)); record = logging.LogRecord("test", 20, "", 0, "key=%s %s", (key.hex(), key.hex().upper()), None)
        self.assertTrue(SecretFilter(key).filter(record))
        self.assertNotIn(key.hex(), record.getMessage())
        self.assertEqual(record.getMessage().count("[REDACTED]"), 2)
