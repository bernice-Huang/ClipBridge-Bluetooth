"""Print synthetic compression figures; no screenshot files are read or saved."""
import io
import json
from pathlib import Path
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "windows"))
from image_codec import encode_image
from compression_samples import document_sample, noise_sample


for name, factory in (("synthetic-document", document_sample), ("synthetic-noise", noise_sample)):
    with factory() as image, io.BytesIO() as original:
        image.save(original, format="PNG", compress_level=3)
        started = time.monotonic()
        result = encode_image(image)
        elapsed = (time.monotonic() - started) * 1000
        print(json.dumps({
            "sample": name, "original_dimensions": image.size,
            "sent_dimensions": (result.width, result.height),
            "old_png_kib": round(len(original.getvalue()) / 1024, 2),
            "sent_png_kib": round(len(result.png) / 1024, 2),
            "method": result.method, "encode_ms": round(elapsed, 1),
            "target_met": result.target_met,
        }))
