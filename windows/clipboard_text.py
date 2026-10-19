"""Bounded, read-only CF_UNICODETEXT access. Never modify the clipboard."""
import ctypes
from ctypes import wintypes

from protocol import MAX_TEXT

CF_UNICODETEXT = 13
CF_HDROP = 15
user32 = ctypes.windll.user32
kernel32 = ctypes.windll.kernel32
user32.OpenClipboard.argtypes = [wintypes.HWND]
user32.OpenClipboard.restype = wintypes.BOOL
user32.CloseClipboard.argtypes = []
user32.CloseClipboard.restype = wintypes.BOOL
user32.IsClipboardFormatAvailable.argtypes = [wintypes.UINT]
user32.IsClipboardFormatAvailable.restype = wintypes.BOOL
user32.GetClipboardData.argtypes = [wintypes.UINT]
user32.GetClipboardData.restype = wintypes.HANDLE
kernel32.GlobalLock.argtypes = [wintypes.HANDLE]
kernel32.GlobalLock.restype = ctypes.c_void_p
kernel32.GlobalUnlock.argtypes = [wintypes.HANDLE]
kernel32.GlobalUnlock.restype = wintypes.BOOL
kernel32.GlobalSize.argtypes = [wintypes.HANDLE]
kernel32.GlobalSize.restype = ctypes.c_size_t


def decode_text(raw):
    """Require a UTF-16LE terminator and valid UTF-8; never truncate content."""
    end = next((i for i in range(0, len(raw) - 1, 2) if raw[i:i + 2] == b"\0\0"), None)
    if end is None:
        raise ValueError("Clipboard text is unterminated or exceeds the size limit")
    try:
        text = raw[:end].decode("utf-16-le")
        encoded = text.encode("utf-8")
    except UnicodeError:
        raise ValueError("Clipboard text has invalid Unicode") from None
    if len(encoded) > MAX_TEXT:
        raise ValueError("Clipboard text exceeds the 64 KiB UTF-8 limit")
    return text


def read_text():
    """Return plain text/None, or OSError for a transient clipboard lock.

    File copies (CF_HDROP) are not interpreted as text paths. The HGLOBAL is
    clipboard-owned: copy while locked, unlock before CloseClipboard, never free.
    """
    if not user32.OpenClipboard(None):
        raise OSError("Clipboard is busy")
    try:
        if user32.IsClipboardFormatAvailable(CF_HDROP):
            return None
        if not user32.IsClipboardFormatAvailable(CF_UNICODETEXT):
            return None
        handle = user32.GetClipboardData(CF_UNICODETEXT)
        if not handle:
            raise OSError("Clipboard text is temporarily unavailable")
        size = kernel32.GlobalSize(handle)
        if size < 2:
            raise ValueError("Clipboard text allocation is invalid")
        pointer = kernel32.GlobalLock(handle)
        if not pointer:
            raise OSError("Clipboard text cannot be locked")
        try:
            # Any text within the UTF-8 budget fits within twice that budget in
            # UTF-16LE. Bound reads even if another application supplies huge data.
            raw = ctypes.string_at(pointer, min(size, 2 * MAX_TEXT + 2))
        finally:
            kernel32.GlobalUnlock(handle)
        return decode_text(raw)
    finally:
        user32.CloseClipboard()
