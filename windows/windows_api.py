"""Pointer-safe Win32 declarations shared by capture and both entry points."""
import ctypes
from ctypes import wintypes

MUTEX_NAME = "Local\\ClipBridgeBluetoothPrototype"

# Windows handles are pointer-sized. ctypes defaults to a 32-bit return value.
ctypes.windll.kernel32.CreateMutexW.argtypes = [ctypes.c_void_p, wintypes.BOOL, wintypes.LPCWSTR]
ctypes.windll.kernel32.CreateMutexW.restype = wintypes.HANDLE
ctypes.windll.kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
ctypes.windll.kernel32.CloseHandle.restype = wintypes.BOOL
ctypes.windll.kernel32.GetLastError.restype = wintypes.DWORD
ctypes.windll.user32.GetClipboardSequenceNumber.restype = wintypes.DWORD


def clipboard_sequence():
    return ctypes.windll.user32.GetClipboardSequenceNumber()
