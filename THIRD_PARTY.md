# Third-party components

ClipBridge's own code is MIT licensed. Dependencies and bundled runtime components keep their original licenses; the project license does not replace them.

| Component | Use | Upstream |
| --- | --- | --- |
| Python / Tcl / Tk | Runtime and status UI | https://www.python.org/ , https://www.tcl.tk/ |
| Pillow | PNG processing and tray icon | https://github.com/python-pillow/Pillow |
| cryptography | AES-GCM | https://github.com/pyca/cryptography |
| PyWinRT | Windows Bluetooth APIs | https://github.com/pywinrt/pywinrt |
| pystray / six | Windows tray UI | https://github.com/moses-palmer/pystray , https://github.com/benjaminp/six |
| PyInstaller | Build and embedded bootloader | https://github.com/pyinstaller/pyinstaller |

The release packager copies available distribution license files and installed runtime license files into `third_party/`. Refer to those complete texts, not just this summary. pystray is unmodified and uses LGPLv3; Python source, dependency pins and rebuild instructions are provided so its replacement version can be used in a new build. PyInstaller includes its licensing exception in its bundled license text.

To rebuild after replacing an unmodified dependency, use a separate Python 3.12 environment, adjust its version in `requirements.txt`, install `requirements-build.txt`, run the tests, and run `Build-Desktop.ps1`. Prefer a source run for debugging replacement modules. Do not strip third-party notices when redistributing.

Apple SDK frameworks are system-provided; this repository distributes Swift source, not Apple's frameworks or a signed iPad binary. Installed dependency metadata and copied full notices are the authoritative source for bundled component details.
