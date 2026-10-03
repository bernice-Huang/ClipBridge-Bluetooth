"""Only this application's HKCU auto-start registration is managed here."""
from pathlib import Path
import winreg

RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
APPROVED_KEY = r"Software\Microsoft\Windows\CurrentVersion\Explorer\StartupApproved\Run"
VALUE_NAME = "ClipBridgeBLE"


def enabled():
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as key:
            value, _ = winreg.QueryValueEx(key, VALUE_NAME)
        return bool(value)
    except FileNotFoundError:
        return False


def set_enabled(value, executable):
    executable = Path(executable).resolve()
    if value and (executable.suffix.lower() != ".exe" or not executable.is_file()):
        raise ValueError("找不到独立 EXE，未设置开机启动")
    with winreg.CreateKeyEx(winreg.HKEY_CURRENT_USER, RUN_KEY, access=winreg.KEY_SET_VALUE) as key:
        if value:
            winreg.SetValueEx(key, VALUE_NAME, 0, winreg.REG_SZ, f'"{executable}" --startup')
        else:
            try:
                winreg.DeleteValue(key, VALUE_NAME)
            except FileNotFoundError:
                pass
    if value:
        # Explicitly enabling OUR entry should also undo its Task Manager disable.
        # Do not alter other applications or machine-wide startup registrations.
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, APPROVED_KEY, 0, winreg.KEY_SET_VALUE) as key:
                winreg.DeleteValue(key, VALUE_NAME)
        except FileNotFoundError:
            pass
