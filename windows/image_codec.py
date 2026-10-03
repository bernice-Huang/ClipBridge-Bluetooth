"""Bounded, adaptive PNG encoding. No files and no wire-protocol changes."""
from dataclasses import dataclass
import io
import math

from PIL import Image

SMALL_IMAGE_BYTES = 24 * 1024
DEFAULT_TARGET_BYTES = 32 * 1024
MIN_SCALE = 0.75


@dataclass(frozen=True)
class EncodedImage:
    png: bytes
    width: int
    height: int
    original_bytes: int
    method: str
    target_bytes: int

    @property
    def target_met(self):
        return len(self.png) <= self.target_bytes


def png_bytes(image):
    with io.BytesIO() as stream:
        image.save(stream, format="PNG", compress_level=6)
        return stream.getvalue()


def encode_image(image, *, quality="balanced", target_bytes=DEFAULT_TARGET_BYTES):
    """Keep small screenshots pixel-exact; never shrink below 75% per side.

    A target is a preference, NOT permission to destroy legibility. If bounded
    candidates do not reach it, return the smallest one and report that fact.
    Palette PNG also keeps the original receiver's UTType.png declaration valid.
    """
    if quality not in ("balanced", "original"):
        raise ValueError("Unknown image quality profile")
    if target_bytes <= 0:
        raise ValueError("Target size must be positive")
    width, height = image.size
    if not (0 < width <= 8192 and 0 < height <= 8192 and width * height <= 32_000_000):
        raise ValueError("Screenshot dimensions exceed prototype bounds")
    # Avoid mutating caller-owned clipboard images or closing their storage.
    with image.copy() as source:
        if source.mode not in ("RGB", "RGBA"):
            normalized = source.convert("RGBA" if "transparency" in source.info else "RGB")
        elif source.mode == "RGBA" and source.getchannel("A").getextrema() == (255, 255):
            # Removing a fully opaque alpha channel does not change pixels.
            normalized = source.convert("RGB")
        else:
            normalized = source.copy()
        with normalized:
            original = png_bytes(normalized)
            best = EncodedImage(original, width, height, len(original), "original-pixels", target_bytes)
            if quality == "original" or len(original) <= max(SMALL_IMAGE_BYTES, target_bytes):
                return best
            # Prefer keeping resolution, then gradually reduce it. No dithering:
            # dithering creates pixel noise and makes screenshots larger.
            for scale, colors in ((1.0, 256), (1.0, 128), (0.85, 128), (MIN_SCALE, 128)):
                size = (max(1, math.ceil(width * scale)), max(1, math.ceil(height * scale)))
                with normalized.resize(size, Image.Resampling.LANCZOS) as candidate:
                    with candidate.convert("RGB") as rgb:
                        with rgb.quantize(colors=colors, method=Image.Quantize.FASTOCTREE,
                                          dither=Image.Dither.NONE) as palette:
                            if candidate.mode == "RGBA":
                                # Quantizing RGBA directly averages alpha too. Keep
                                # the candidate's alpha plane rather than making
                                # completely transparent areas partly opaque.
                                with palette.convert("RGBA") as merged:
                                    with candidate.getchannel("A") as alpha:
                                        merged.putalpha(alpha)
                                    encoded = png_bytes(merged)
                            else:
                                encoded = png_bytes(palette)
                if len(encoded) < len(best.png):
                    best = EncodedImage(encoded, *size, len(original),
                                        f"palette-{colors}@{scale:.0%}", target_bytes)
                if best.target_met:
                    break
            return best
