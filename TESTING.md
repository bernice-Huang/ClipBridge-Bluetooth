# Testing and compatibility

## Evidence boundary

User feedback on one Windows 11 PC and one iPad Air M3 reports successful pairing, foreground paste, and new-image paste while Goodnotes stayed foreground for at least 60 seconds. The user also accepted improved speed and clarity after PNG compression. These are user-reported observations, not a device-farm compatibility guarantee.

The pre-compression prototype logs showed small images around 13 KiB arriving in roughly 2 seconds and images around 150–180 KiB reaching the 20-second deadline. No post-compression distribution of timings has been supplied. Do not advertise all images as under 3 seconds.

Windows builds are x64. The iPad manifest declares iPadOS 17+, but this declaration is not a test result. Other PCs, adapters, iPads, OS releases, notebook apps and ARM systems remain unverified.

## Local automated checks

On Windows with Python 3.12, install requirements and run:

```powershell
.\.venv\Scripts\python.exe -X utf8 -m unittest discover -s tests -v
.\.venv\Scripts\python.exe -m pip check
```

Tests cover image coding, transparency/bounds, authentication, AES-GCM, fragmentation, flow control, queued notification order, configuration, pause/resume and desktop-worker lifecycle. Installer tests use synthetic binaries/keys in temporary directories with `-NoStartup`; they do not run the binary, change real startup entries or access real screenshots.

First-public-release local check (2026-10-03): 56 tests passed; dependency check passed. Frozen EXE crypto/PNG/WinRT capability self-test and tray event-loop smoke test passed. These checks do not expand the single-pair device evidence above.

Package-only checks:

```powershell
.\dist\ClipBridgeBLE.exe --self-test .\exports\package-test.json
.\dist\ClipBridgeBLE.exe --ui-smoke .\exports\ui-test.json
```

Create the `exports` output folder first. Self-test uses synthetic image/key data and reads adapter capability. UI smoke creates tray/Tk event loops, then exits, without broadcasting or monitoring the clipboard. Neither is proof of actual iPad paste.

## Device acceptance

1. Pair and paste a different small image in the foreground.
2. Leave Goodnotes as the sole foreground app for 60 seconds, then 5 minutes; capture and paste new images without returning to the receiver.
3. Test typical text/table/chart screenshots and record detection-to-receipt latency and readability.
4. Restart Windows, toggle Bluetooth and sleep/resume; document when manual iPad reconnection is needed.
5. Report large-image failures and compare balanced/original, queue/sequential modes.

Only pasting the latest image demonstrates clipboard success. `clipboard_write_attempt=True` and receipts do not prove it. Do not upload pairing secrets, private screenshots or unchecked logs when reporting results.
