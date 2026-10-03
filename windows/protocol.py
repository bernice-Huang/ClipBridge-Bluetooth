"""ClipBridge BLE/1: small control frames, encrypted in-memory image payloads."""
import hashlib
import hmac
import secrets
import struct
from uuid import UUID

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

SERVICE = UUID("8d6b3f00-e815-4c55-b109-45bdffb271f0")
INFO = UUID("8d6b3f01-e815-4c55-b109-45bdffb271f0")
CONTROL = UUID("8d6b3f02-e815-4c55-b109-45bdffb271f0")
DATA = UUID("8d6b3f03-e815-4c55-b109-45bdffb271f0")
AAD = b"ClipBridge/1"
AUTH_CONTEXT = b"ClipBridge/auth/1"
HEADER = struct.Struct("<BII")
IMAGE_HEADER = struct.Struct("<4sIIQ")
MAX_PNG = 2 * 1024 * 1024
MAX_WIRE = MAX_PNG + IMAGE_HEADER.size + 28
START, CHUNK, END, READY = 1, 2, 3, 4
AUTH, ACK, RECEIPT, LATEST, STOP = 16, 17, 18, 19, 20
WINDOW = 32


def auth_proof(key, challenge):
    return hmac.new(key, AUTH_CONTEXT + challenge, hashlib.sha256).digest()[:16]


def seal_image(key, png, width, height, captured_ms):
    if not png or len(png) > MAX_PNG:
        raise ValueError("PNG must contain 1..2097152 bytes")
    if not (0 < width <= 8192 and 0 < height <= 8192 and width * height <= 32_000_000):
        raise ValueError("Image dimensions exceed the prototype limit")
    plain = IMAGE_HEADER.pack(b"CBP1", width, height, captured_ms) + png
    nonce = secrets.token_bytes(12)
    # CryptoKit AES.GCM.SealedBox.combined uses nonce(12) + ciphertext + tag(16).
    return nonce + AESGCM(key).encrypt(nonce, plain, AAD)


def open_image(key, wire):
    if not (IMAGE_HEADER.size + 29 <= len(wire) <= MAX_WIRE):
        raise ValueError("Invalid encrypted payload size")
    plain = AESGCM(key).decrypt(wire[:12], wire[12:], AAD)
    magic, width, height, captured_ms = IMAGE_HEADER.unpack_from(plain)
    if magic != b"CBP1":
        raise ValueError("Invalid image payload")
    return plain[IMAGE_HEADER.size:], width, height, captured_ms


def frames(transfer_id, wire, mtu):
    """MTU here means maximum notification VALUE length, not ATT PDU length."""
    if mtu < 20 or not wire or len(wire) > MAX_WIRE:
        raise ValueError("Invalid notification size or payload")
    size = min(mtu, 512) - HEADER.size
    yield HEADER.pack(START, transfer_id, len(wire))
    for offset in range(0, len(wire), size):
        yield HEADER.pack(CHUNK, transfer_id, offset) + wire[offset:offset + size]
    yield HEADER.pack(END, transfer_id, len(wire))
