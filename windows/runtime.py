"""Stable per-user configuration, private key migration and metadata-only logs."""
from dataclasses import asdict, dataclass
import json
import logging
from logging.handlers import RotatingFileHandler
import os
from pathlib import Path
import secrets
import sys
import tempfile
import threading

VERSION = "0.3.1-beta"
APP_NAME = "ClipBridge 蓝牙"


def data_folder():
    base = os.environ.get("LOCALAPPDATA")
    return (Path(base) if base else Path.home() / "AppData" / "Local") / "ClipBridgeBLE"


def legacy_session_path():
    # An installed/frozen EXE must NEVER store its key in its extraction folder.
    if getattr(sys, "frozen", False):
        return None
    return Path(__file__).resolve().parents[1] / "session.json"


def read_key(path):
    try:
        key = bytes.fromhex(json.loads(Path(path).read_text(encoding="utf-8"))["key"])
    except (OSError, ValueError, KeyError, TypeError) as error:
        raise ValueError("配对配置无效；未覆盖或重置密钥。请检查 session.json。") from error
    if len(key) != 16:
        raise ValueError("配对密钥长度无效；未重置密钥。")
    return key


def pairing_key(folder=None, legacy=None):
    folder = Path(folder) if folder is not None else data_folder()
    folder.mkdir(parents=True, exist_ok=True)
    destination = folder / "session.json"
    if destination.exists():
        return read_key(destination)
    source = Path(legacy) if legacy is not None else legacy_session_path()
    key = read_key(source) if source is not None and source.exists() else secrets.token_bytes(16)
    try:
        with destination.open("x", encoding="utf-8") as stream:
            json.dump({"protocol": 1, "key": key.hex()}, stream)
    except FileExistsError:
        # A second process may have initialized the same user's folder.
        return read_key(destination)
    return key


@dataclass(frozen=True)
class Settings:
    quality: str = "balanced"
    pipeline: int = 4
    target_kib: int = 32
    paused: bool = False

    def __post_init__(self):
        if self.quality not in ("balanced", "original"):
            raise ValueError("画质配置无效")
        if type(self.pipeline) is not int or self.pipeline not in (1, 2, 4, 8):
            raise ValueError("发送队列配置无效")
        if type(self.target_kib) is not int or not 16 <= self.target_kib <= 128:
            raise ValueError("压缩目标配置无效")
        if type(self.paused) is not bool:
            raise ValueError("暂停配置无效")

    @classmethod
    def load(cls, path):
        path = Path(path)
        if not path.exists():
            return cls()
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(raw, dict):
                raise ValueError("Settings must be an object")
            return cls(**{name: raw[name] for name in cls.__dataclass_fields__ if name in raw})
        except (OSError, ValueError, TypeError) as error:
            # Fail closed: a malformed pause setting must not silently start capture.
            raise ValueError("设置文件无效，已取消启动；原文件未修改。") from error

    def save(self, path):
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = None
        try:
            with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=path.parent,
                                             prefix="settings-", suffix=".tmp", delete=False) as stream:
                temporary = Path(stream.name)
                json.dump(asdict(self), stream, ensure_ascii=False, indent=2)
            temporary.replace(path)
        finally:
            if temporary is not None and temporary.exists():
                temporary.unlink()


class Status:
    def __init__(self):
        self.lock = threading.Lock()
        self.values = {"phase": "starting", "detail": "正在启动", "last_image": "暂无截图",
                       "last_receipt": "暂无回执", "paused": False, "pipeline": 4, "error": ""}

    def update(self, **values):
        with self.lock:
            self.values.update(values)

    def snapshot(self):
        with self.lock:
            return dict(self.values)


class SecretFilter(logging.Filter):
    def __init__(self, key):
        super().__init__()
        self.secret = key.hex()

    def filter(self, record):
        message = record.getMessage()
        record.msg = message.replace(self.secret, "[REDACTED]").replace(self.secret.upper(), "[REDACTED]")
        record.args = ()
        return True


def configure_logging(folder, key):
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    log = logging.getLogger("clipbridge")
    handler = RotatingFileHandler(folder / "app.log", maxBytes=1024 * 1024,
                                  backupCount=2, encoding="utf-8")
    handler.addFilter(SecretFilter(key))
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
    log.addHandler(handler)
    log.setLevel(logging.INFO)
    return handler
