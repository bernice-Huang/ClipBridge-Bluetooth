"""Immutable clipboard item passed from capture to the async BLE sender."""
from dataclasses import dataclass


@dataclass(frozen=True)
class Snapshot:
    data: bytes
    width: int
    height: int
    captured_ms: int  # Unix wall-clock milliseconds, included in the encrypted header.
    detected: float  # Monotonic seconds, used only for local latency measurements.
    kind: str = "image"
