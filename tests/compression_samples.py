"""Synthetic screenshots for repeatable tests. Never reads the user's clipboard."""
from pathlib import Path
import random

from PIL import Image, ImageDraw, ImageFont


def document_sample(width=1057, height=657):
    image = Image.new("RGB", (width, height), "white")
    draw = ImageDraw.Draw(image)
    font_path = Path("C:/Windows/Fonts/arial.ttf")
    font = ImageFont.truetype(str(font_path), 18) if font_path.exists() else ImageFont.load_default()
    for row in range(24):
        draw.text((20, 15 + row * 25), f"Section {row + 1}: Windows -> iPad clipboard / x = (a+b)/c", fill="#202020", font=font)
    # A photo-like smooth gradient panel beside high-contrast text.
    panel_width = max(1, width - 620)
    panel = Image.frombytes("RGB", (panel_width, height), bytes(
        value for y in range(height) for x in range(panel_width)
        for value in (int(x * 255 / panel_width), int(y * 255 / height), (x + y) % 256)
    ))
    image.paste(panel, (620, 0)); panel.close()
    return image


def noise_sample(width=401, height=301):
    return Image.frombytes("RGB", (width, height), random.Random(123).randbytes(width * height * 3))
