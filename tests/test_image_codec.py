import io
import math
from pathlib import Path
import random
import sys
import unittest

from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "windows"))
from image_codec import encode_image, png_bytes, MIN_SCALE
from compression_samples import document_sample, noise_sample


class CodecTests(unittest.TestCase):
    def decode(self, result):
        image = Image.open(io.BytesIO(result.png))
        self.assertEqual(image.format, "PNG")
        self.assertEqual(image.size, (result.width, result.height))
        return image

    def test_small_screenshot_keeps_pixels(self):
        with Image.new("RGBA", (364, 80), (180, 40, 70, 200)) as image:
            image.putpixel((3, 4), (12, 13, 14, 0))
            original = image.tobytes()
            result = encode_image(image)
            self.assertEqual(result.method, "original-pixels")
            with self.decode(result) as decoded:
                self.assertEqual(decoded.convert("RGBA").tobytes(), original)
            self.assertEqual(image.tobytes(), original)

    def test_original_profile_never_quantizes_or_resizes(self):
        with noise_sample() as image:
            result = encode_image(image, quality="original")
            self.assertEqual(result.method, "original-pixels")
            with self.decode(result) as decoded:
                self.assertEqual(decoded.tobytes(), image.tobytes())

    def test_document_compression_is_smaller_and_valid(self):
        with document_sample() as image:
            result = encode_image(image)
            self.assertLess(len(result.png), result.original_bytes)
            self.assertGreaterEqual(result.width, math.ceil(image.width * MIN_SCALE))
            self.assertGreaterEqual(result.height, math.ceil(image.height * MIN_SCALE))
            with self.decode(result) as decoded:
                rgb = decoded.convert("RGB")
                # The sample's untouched left margin must remain close to white.
                self.assertTrue(all(value > 240 for value in rgb.getpixel((2, 2))))

    def test_size_target_does_not_override_quality_floor(self):
        with noise_sample() as image:
            result = encode_image(image, target_bytes=1024)
            self.assertFalse(result.target_met)
            self.assertGreaterEqual(result.width, math.ceil(image.width * MIN_SCALE))
            self.assertGreaterEqual(result.height, math.ceil(image.height * MIN_SCALE))
            self.assertLessEqual(len(result.png), result.original_bytes)
            with self.decode(result):
                pass

    def test_palette_png_keeps_transparency(self):
        with Image.frombytes("RGBA", (240, 180), random.Random(5).randbytes(240 * 180 * 4)) as image:
            # Keep two common exact alpha levels, plus a complex colored middle.
            image.paste((255, 0, 0, 0), (0, 0, 80, 180))
            image.paste((0, 0, 255, 255), (160, 0, 240, 180))
            result = encode_image(image, target_bytes=24 * 1024)
            with self.decode(result) as decoded:
                alpha = decoded.convert("RGBA").getchannel("A")
                self.assertEqual(alpha.getextrema(), (0, 255))

    def test_invalid_options(self):
        with Image.new("RGB", (10, 10)) as image:
            with self.assertRaises(ValueError):
                encode_image(image, quality="unknown")
            with self.assertRaises(ValueError):
                encode_image(image, target_bytes=0)

    def test_dimension_limit_before_encoding(self):
        with Image.new("RGB", (8193, 1)) as image:
            with self.assertRaises(ValueError):
                encode_image(image)

    def test_soft_target_keeps_original_if_it_already_fits(self):
        with noise_sample(200, 100) as image:
            original = png_bytes(image)
            result = encode_image(image, target_bytes=len(original) + 1)
            self.assertEqual(result.png, original)
            self.assertEqual(result.method, "original-pixels")


if __name__ == "__main__":
    unittest.main()
