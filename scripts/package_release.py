"""Allowlisted public artifacts. No clipboard, credentials or private config."""
import argparse
import hashlib
from importlib import metadata
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys
import zipfile

ROOT = Path(__file__).resolve().parents[1]
VERSION = "0.3.1-beta"
PUBLIC_ROOT = (
    ".gitignore", "README.md", "LICENSE", "CHANGELOG.md", "TESTING.md", "THIRD_PARTY.md",
    "iPad操作说明.md", "简单使用说明.md", "requirements.txt", "requirements-build.txt",
    "launcher.py", "Setup.ps1", "Build-Desktop.ps1", "Install-Desktop.ps1",
    "Start-ClipBridge-BLE.cmd", "Start-ClipBridge-BLE-Compatible.cmd", "ClipBridgeBLE.spec",
)
PUBLIC_TREES = {"windows": {".py"}, "tests": {".py"}, "scripts": {".py"},
                "ipad": {".swift", ".plist"}}
FORBIDDEN = {"session.json", "settings.json", ".env", "app.log", "验证记录.md"}


def public_files():
    files = [ROOT / name for name in PUBLIC_ROOT]
    for folder, suffixes in PUBLIC_TREES.items():
        files.extend(path for path in sorted((ROOT / folder).rglob("*"))
                     if path.is_file() and path.suffix in suffixes and "__pycache__" not in path.parts)
    for path in files:
        if not path.is_file() or path.is_symlink() or path.name in FORBIDDEN:
            raise ValueError(f"Unexpected public input: {path.name}")
    return files


def audit(files, private_configs=(), *, staged=False):
    secrets = []
    for config in private_configs:
        config = Path(config)
        if config.is_file():
            key = json.loads(config.read_text(encoding="utf-8"))["key"]
            if re.fullmatch(r"[0-9a-fA-F]{32}", key):
                secrets.extend((key.encode(), key.upper().encode(), key.lower().encode()))
            else:
                raise ValueError("Invalid private configuration; audit cancelled")
    for path in files:
        content = (subprocess.check_output(["git", "show", ":" + path.relative_to(ROOT).as_posix()], cwd=ROOT)
                   if staged else path.read_bytes())
        if any(secret in content for secret in secrets):
            raise ValueError(f"Private pairing key found in {path.name}; publication cancelled")
        if re.search(rb"(?:gh[pousr]_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{30,}|-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----)", content):
            raise ValueError(f"Possible credential found in {path.name}; publication cancelled")


def collect_notices(output):
    """Mechanically copy installed component licenses; don't change their text."""
    folder = output / "third_party"
    folder.mkdir(parents=True, exist_ok=True)
    dependencies = set()
    for line in (ROOT / "requirements.txt").read_text(encoding="utf-8").splitlines():
        if "==" in line:
            dependencies.add(line.split("==")[0])
    dependencies.update(("six", "cffi", "pycparser", "typing_extensions", "PyInstaller", "pyinstaller-hooks-contrib"))
    records = []
    for name in sorted(dependencies):
        dist = metadata.distribution(name)
        copied = []
        for entry in dist.files or ():
            if not entry.name.upper().startswith(("LICENSE", "COPYING", "NOTICE", "AUTHORS")):
                continue
            source = Path(dist.locate_file(entry))
            if source.is_file():
                if ".." in Path(entry).parts:
                    raise ValueError("Unexpected license metadata path")
                relative = Path(name) / Path(entry)
                destination = folder / relative
                destination.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(source, destination)
                copied.append(relative.as_posix())
        # The installed PyWinRT wheel can omit a license file. Supply the
        # upstream project notice checked into the repository for those wheels.
        if not copied and name.lower().startswith("winrt"):
            source = ROOT / "third_party" / "pywinrt-LICENSE.txt"
            destination = folder / name / "LICENSE.txt"
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, destination)
            copied.append(destination.relative_to(folder).as_posix())
        if not copied:
            raise ValueError(f"No license text found for bundled dependency {name}")
        records.append({"component": name, "version": dist.version, "notices": copied})
    runtime_notices = [Path(sys.base_prefix) / "LICENSE.txt"]
    runtime_notices.extend((Path(sys.base_prefix) / "tcl").rglob("license.terms"))
    for source in runtime_notices:
        if source.is_file():
            destination = folder / "Python-runtime" / source.relative_to(sys.base_prefix)
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, destination)
    (folder / "components.json").write_text(json.dumps(records, indent=2), encoding="utf-8")
    # Include the unmodified LGPL library's Python source with its full notices.
    tray = Path(metadata.distribution("pystray").locate_file("pystray"))
    for source in tray.rglob("*.py"):
        destination = folder / "pystray-source" / source.relative_to(tray)
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, destination)
    return sorted(path for path in folder.rglob("*") if path.is_file())


def archive(destination, entries):
    with zipfile.ZipFile(destination, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as target:
        for source, name in entries:
            if Path(name).name in FORBIDDEN or source.is_symlink():
                raise ValueError("Forbidden archive entry")
            target.write(source, name)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--private-config", action="append", default=[])
    parser.add_argument("--audit-only", action="store_true")
    parser.add_argument("--audit-index", action="store_true")
    options = parser.parse_args()
    files = public_files()
    # Include upstream license files explicitly, rather than arbitrary folders.
    files.extend(sorted((ROOT / "third_party").glob("*-LICENSE.txt")))
    if options.audit_index:
        actual = set(subprocess.check_output(["git", "ls-files", "-z"], cwd=ROOT).decode("utf-8").strip("\0").split("\0"))
        expected = {path.relative_to(ROOT).as_posix() for path in files}
        if actual != expected:
            raise ValueError("Git index differs from the public file allowlist; publication cancelled")
    audit(files, options.private_config, staged=options.audit_index)
    print(f"Public source audit passed: {len(files)} allowlisted files; no key printed")
    if options.audit_only:
        return
    binary = ROOT / "dist" / "ClipBridgeBLE.exe"
    if not binary.is_file():
        raise ValueError("Build the Windows EXE first")
    output = ROOT / "release"
    output.mkdir(exist_ok=True)
    notices = collect_notices(output)
    windows = output / f"ClipBridgeBLE-v{VERSION}-windows-x64.zip"
    windows_docs = ("README.md", "简单使用说明.md", "iPad操作说明.md", "LICENSE", "THIRD_PARTY.md", "TESTING.md", "CHANGELOG.md", "Install-Desktop.ps1")
    archive(windows, [(binary, "ClipBridgeBLE.exe")] + [(ROOT / name, name) for name in windows_docs]
            + [(path, path.relative_to(output).as_posix()) for path in notices])
    ipad = output / f"ClipBridgeBLE-v{VERSION}-ipad.zip"
    archive(ipad, [(path, path.relative_to(ROOT / "ipad").as_posix()) for path in files if "ipad" in path.relative_to(ROOT).parts]
            + [(ROOT / "iPad操作说明.md", "iPad操作说明.md"), (ROOT / "LICENSE", "LICENSE")])
    source = output / f"ClipBridgeBLE-v{VERSION}-source.zip"
    archive(source, [(path, f"ClipBridge-Bluetooth/{path.relative_to(ROOT).as_posix()}") for path in files])
    checksums = output / "SHA256SUMS.txt"
    checksums.write_text("".join(f"{hashlib.sha256(path.read_bytes()).hexdigest()}  {path.name}\n"
                                 for path in (windows, ipad, source)), encoding="utf-8")
    for path in (windows, ipad, source, checksums):
        print(f"Artifact: {path.name} ({path.stat().st_size} bytes)")


if __name__ == "__main__":
    main()
