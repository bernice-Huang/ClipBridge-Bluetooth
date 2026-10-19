"""Repository and packaged documentation stay navigable after file moves."""
import importlib.util
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import unittest
from urllib.parse import unquote, urlsplit
import zipfile

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("layout_packager", ROOT / "scripts/package_release.py")
release = importlib.util.module_from_spec(spec)
spec.loader.exec_module(release)


def local_links(markdown):
    # These docs use inline links without spaces; ignore external URLs/anchors.
    for target in re.findall(r"\]\(([^()\s]+)\)", markdown):
        parsed = urlsplit(target)
        if not parsed.scheme and not parsed.netloc and parsed.path:
            yield unquote(parsed.path)


class RepositoryLayoutTests(unittest.TestCase):
    def test_adjacent_chinese_links_do_not_merge(self):
        self.assertEqual(list(local_links("[许可](LICENSE)。[版本](CHANGELOG.md)，[文档](docs/README.md)")),
                         ["LICENSE", "CHANGELOG.md", "docs/README.md"])

    def test_all_relative_document_links_exist(self):
        docs = [ROOT / "README.md", ROOT / "CHANGELOG.md", *sorted((ROOT / "docs").rglob("*.md"))]
        for doc in docs:
            for link in local_links(doc.read_text(encoding="utf-8")):
                with self.subTest(document=doc.name, link=link):
                    target = (doc.parent / link).resolve()
                    self.assertTrue(target.is_relative_to(ROOT))
                    self.assertTrue(target.exists())

    def test_root_keeps_only_public_entrypoints(self):
        root_files = {path.name for path in release.public_files() if path.parent == ROOT}
        self.assertEqual(root_files, {".gitignore", "README.md", "LICENSE", "CHANGELOG.md",
                                     "Install-Desktop.ps1", "requirements.txt", "requirements-build.txt"})

    def test_development_scripts_and_docs_are_allowlisted(self):
        files = set(release.public_files())
        for name in ("Setup.ps1", "Build-Desktop.ps1", "Start-ClipBridge-BLE.cmd",
                     "Start-ClipBridge-BLE-Compatible.cmd", "ClipBridgeBLE.spec"):
            self.assertIn(ROOT / "scripts" / name, files)
        for doc in (ROOT / "docs").rglob("*.md"):
            self.assertIn(doc, files)
        self.assertIn(ROOT / "windows/launcher.py", files)

    def test_user_package_docs_links_survive_extraction(self):
        entries = release.documentation_entries(release.public_files())
        names = [name for _, name in entries]
        self.assertEqual(len(names), len(set(names)))
        with tempfile.TemporaryDirectory(prefix="clipbridge-docs-") as folder:
            archive = Path(folder) / "docs.zip"
            release.archive(archive, entries)
            with zipfile.ZipFile(archive) as packaged:
                packaged.extractall(Path(folder) / "unpacked")
            for name in names:
                doc = Path(folder) / "unpacked" / name
                if doc.suffix != ".md":
                    continue
                for link in local_links(doc.read_text(encoding="utf-8")):
                    with self.subTest(document=name, link=link):
                        self.assertTrue((doc.parent / link).resolve().exists())

    def test_launchers_resolve_the_project_not_scripts_folder(self):
        for name in ("Start-ClipBridge-BLE.cmd", "Start-ClipBridge-BLE-Compatible.cmd"):
            script = (ROOT / "scripts" / name).read_text(encoding="utf-8")
            self.assertIn('cd /d "%~dp0.."', script)
        for name in ("Setup.ps1", "Build-Desktop.ps1"):
            self.assertIn("Split-Path -Parent $PSScriptRoot", (ROOT / "scripts" / name).read_text(encoding="utf-8"))
        spec = (ROOT / "scripts/ClipBridgeBLE.spec").read_text(encoding="utf-8")
        self.assertIn("root = Path(SPECPATH).parent", spec)
        self.assertIn("root / 'windows' / 'launcher.py'", spec)

    def test_source_entrypoint_can_import_from_other_working_directory(self):
        # --help exits before clipboard capture, configuration or BLE setup.
        with tempfile.TemporaryDirectory(prefix="clipbridge-entry-") as folder:
            result = subprocess.run([sys.executable, "-X", "utf8", str(ROOT / "windows/launcher.py"), "--help"],
                                    cwd=folder, capture_output=True, timeout=30)
        self.assertEqual(result.returncode, 0, result.stderr.decode("utf-8", errors="replace"))
        self.assertIn(b"--self-test", result.stdout)
