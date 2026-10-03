"""Publication audit tests: no live secrets, screenshots or network writes."""
import importlib.util
from pathlib import Path
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("package_release", ROOT / "scripts" / "package_release.py")
release = importlib.util.module_from_spec(spec)
spec.loader.exec_module(release)


class ReleaseTests(unittest.TestCase):
    def test_allowlist_excludes_private_and_generated_files(self):
        files = release.public_files()
        self.assertTrue(files)
        for path in files:
            self.assertNotIn(path.name, release.FORBIDDEN)
            self.assertTrue(path.is_relative_to(ROOT))
            self.assertFalse({"backups", ".venv", "build", "dist", "exports", "release"} & set(path.relative_to(ROOT).parts))

    def test_synthetic_private_secret_blocks_publication(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            key = "f1" * 16
            private = root / "session.json"
            private.write_text('{"key":"' + key + '"}', encoding="utf-8")
            source = root / "public.md"
            source.write_text("leaked " + key.upper(), encoding="utf-8")
            with self.assertRaises(ValueError):
                release.audit([source], [private])

    def test_clean_source_passes_secret_check(self):
        release.audit(release.public_files())


if __name__ == "__main__":
    unittest.main()
