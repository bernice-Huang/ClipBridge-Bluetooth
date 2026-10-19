"""Synthetic Win32 memory/handle tests. No real clipboard reads or writes."""
import ctypes
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "windows"))
import clipboard.text as c
from ble.protocol import MAX_TEXT


class ClipboardTextTests(unittest.TestCase):
    def test_unicode_whitespace_and_terminator(self):
        for text in ("你好🙂", "English\r\n第二行\t✅", "  \n\t ", ""):
            raw = (text + "\0").encode("utf-16-le") + b"\xff"
            self.assertEqual(c.decode_text(raw), text)

    def test_invalid_or_unterminated_unicode_is_rejected(self):
        for raw in (b"", b"x", b"x\0", b"\x00\xd8\0\0"):
            with self.subTest(raw=raw), self.assertRaises(ValueError):
                c.decode_text(raw)

    def test_utf8_byte_limit_not_character_count(self):
        self.assertEqual(c.decode_text(("x" * MAX_TEXT + "\0").encode("utf-16-le")), "x" * MAX_TEXT)
        with self.assertRaises(ValueError):
            c.decode_text(("中" * (MAX_TEXT // 3 + 1) + "\0").encode("utf-16-le"))

    def api(self, raw, formats=(c.CF_UNICODETEXT,)):
        memory = ctypes.create_string_buffer(raw)
        user = SimpleNamespace(OpenClipboard=Mock(return_value=True), CloseClipboard=Mock(),
            IsClipboardFormatAvailable=Mock(side_effect=lambda fmt: fmt in formats),
            GetClipboardData=Mock(return_value=123))
        kernel = SimpleNamespace(GlobalSize=Mock(return_value=len(raw)),
            GlobalLock=Mock(return_value=ctypes.addressof(memory)), GlobalUnlock=Mock())
        return memory, user, kernel

    def test_handles_are_unlocked_and_clipboard_closed(self):
        memory, user, kernel = self.api("你好🙂\0".encode("utf-16-le"))
        with patch.object(c, "user32", user), patch.object(c, "kernel32", kernel):
            self.assertEqual(c.read_text(), "你好🙂")
        user.GetClipboardData.assert_called_once_with(c.CF_UNICODETEXT)
        kernel.GlobalUnlock.assert_called_once_with(123)
        user.CloseClipboard.assert_called_once()

    def test_file_list_or_unsupported_formats_are_ignored(self):
        for formats in ((), (c.CF_HDROP, c.CF_UNICODETEXT)):
            memory, user, kernel = self.api(b"\0\0", formats)
            with patch.object(c, "user32", user), patch.object(c, "kernel32", kernel):
                self.assertIsNone(c.read_text())
            user.GetClipboardData.assert_not_called()
            user.CloseClipboard.assert_called_once()

    def test_busy_clipboard_is_retried_without_close(self):
        user = SimpleNamespace(OpenClipboard=Mock(return_value=False), CloseClipboard=Mock())
        with patch.object(c, "user32", user), self.assertRaises(OSError):
            c.read_text()
        user.CloseClipboard.assert_not_called()

    def test_unavailable_handle_or_lock_always_closes(self):
        for failure in ("handle", "lock", "size"):
            memory, user, kernel = self.api(b"\0\0")
            if failure == "handle": user.GetClipboardData.return_value = 0
            if failure == "lock": kernel.GlobalLock.return_value = 0
            if failure == "size": kernel.GlobalSize.return_value = 0
            with patch.object(c, "user32", user), patch.object(c, "kernel32", kernel):
                with self.assertRaises((OSError, ValueError)):
                    c.read_text()
            kernel.GlobalUnlock.assert_not_called()
            user.CloseClipboard.assert_called_once()

    def test_malformed_content_releases_all_handles(self):
        memory, user, kernel = self.api(b"x\0")
        with patch.object(c, "user32", user), patch.object(c, "kernel32", kernel):
            with self.assertRaises(ValueError):
                c.read_text()
        kernel.GlobalUnlock.assert_called_once_with(123)
        user.CloseClipboard.assert_called_once()

    def test_native_memory_read_is_bounded(self):
        memory, user, kernel = self.api(b"\0\0")
        kernel.GlobalSize.return_value = 100_000_000
        with patch.object(c, "user32", user), patch.object(c, "kernel32", kernel), \
                patch.object(c.ctypes, "string_at", return_value=b"\0\0") as read:
            self.assertEqual(c.read_text(), "")
        self.assertEqual(read.call_args.args[1], 2 * MAX_TEXT + 2)
