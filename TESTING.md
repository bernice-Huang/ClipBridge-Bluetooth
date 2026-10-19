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

The v0.4.0-beta additions cover bounded Win32 text reads and handle release with synthetic memory, Unicode/Emoji/whitespace preservation, size/encoding rejection, clipboard-change races, capability negotiation and revocation, text/image priority, toggling, metadata-only logs and pairing-key exclusion. Text flow-control tests mock notifications at multiple MTUs/pipeline depths; existing image tests still exercise ordered native-call submission and asynchronous completion. A fixed text ciphertext is shared with the iPad CryptoKit self-test; Python checking that fixture is **not** running or compiling Swift.

First-public-release local check (2026-10-03): 56 tests passed; dependency check passed. Frozen EXE crypto/PNG/WinRT capability self-test and tray event-loop smoke test passed. These checks do not expand the single-pair device evidence above.

Text development check (2026-10-08): 89 automated tests passed. iPad source compilation, actual foreground text paste and background text paste remain **pending device validation**. Historical image feedback must not be presented as validation of new text behavior.

Pre-release recheck (2026-10-19): all 89 automated tests passed again, and `pip check` reported no broken requirements. This recheck does not add iPad device evidence.

The v0.4.0-beta Windows x64 EXE also passed its frozen AES-GCM/PNG/Unicode-text/WinRT self-test and tray/Tk event-loop smoke. A 2-second GATT advertising smoke succeeded without reading clipboard contents. The local desktop binary was updated with an old-EXE backup; private key, settings and existing startup registration were checked unchanged. These are Windows checks, not end-to-end iPad validation.

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
6. With both ends updated, copy new Chinese/English/multiline/Emoji text and paste in Notes, then a Goodnotes text editor; repeat with the receiver backgrounded for 60 seconds and 5 minutes. Check text toggle off/on, same-text recopy, and image/text alternation.

Only pasting the latest image demonstrates clipboard success. `clipboard_write_attempt=True` and receipts do not prove it. Do not upload pairing secrets, private screenshots or unchecked logs when reporting results.
