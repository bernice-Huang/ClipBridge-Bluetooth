"""First-install tests in isolated folders; never modify real startup or keys."""
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


class InstallerTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="clipbridge-install-")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.source = self.root / "release with spaces"
        self.source.mkdir()
        shutil.copyfile(ROOT / "Install-Desktop.ps1", self.source / "Install-Desktop.ps1")
        (self.source / "ClipBridgeBLE.exe").write_bytes(b"synthetic test binary, never executed")
        self.destination = self.root / "desktop with spaces"
        self.data = self.root / "private configuration"

    def install(self):
        result = subprocess.run([
            "powershell.exe", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass",
            "-File", str(self.source / "Install-Desktop.ps1"),
            "-Destination", str(self.destination), "-DataDirectory", str(self.data), "-NoStartup",
        ], capture_output=True, timeout=20)
        if result.returncode:
            self.failure = result.stderr.decode("utf-8", errors="replace")
        return result.returncode

    def test_first_install_without_legacy_configuration(self):
        self.assertEqual(self.install(), 0)
        config = json.loads((self.data / "session.json").read_text(encoding="utf-8"))
        self.assertEqual(len(bytes.fromhex(config["key"])), 16)
        self.assertEqual((self.destination / "ClipBridgeBLE.exe").read_bytes(),
                         (self.source / "ClipBridgeBLE.exe").read_bytes())

    def test_reinstall_preserves_generated_key(self):
        self.assertEqual(self.install(), 0)
        original = (self.data / "session.json").read_bytes()
        self.assertEqual(self.install(), 0, getattr(self, "failure", ""))
        self.assertEqual((self.data / "session.json").read_bytes(), original)

    def test_existing_invalid_configuration_not_overwritten(self):
        self.data.mkdir()
        path = self.data / "session.json"
        path.write_text('{"key":"invalid"}', encoding="utf-8")
        self.assertNotEqual(self.install(), 0)
        self.assertEqual(path.read_text(encoding="utf-8"), '{"key":"invalid"}')
        self.assertFalse((self.destination / "ClipBridgeBLE.exe").exists())

    def test_legacy_configuration_migrated(self):
        synthetic = "00112233445566778899aabbccddeeff"
        (self.source / "session.json").write_text(json.dumps({"key": synthetic}), encoding="utf-8")
        self.assertEqual(self.install(), 0)
        self.assertEqual(json.loads((self.data / "session.json").read_text())["key"], synthetic)

    def test_invalid_legacy_configuration_not_replaced(self):
        (self.source / "session.json").write_text('{"key":"invalid"}', encoding="utf-8")
        self.assertNotEqual(self.install(), 0)
        self.assertFalse((self.data / "session.json").exists())


if __name__ == "__main__":
    unittest.main()
