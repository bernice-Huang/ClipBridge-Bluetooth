# Changelog

## Unreleased — repository organization

- User-first README with direct Windows/iPad downloads and a three-step setup path.
- User and developer guides grouped under `docs/`, including a documentation index and troubleshooting guide.
- Build/setup/console scripts and the PyInstaller spec grouped under `scripts/`; source launcher moved to `windows/` with paths updated.
- Future packages preserve README/documentation links; local preview output can be selected with `--output-dir`.
- Documentation-link and repository-layout regression checks added. Application behavior, private settings, published v0.4.0-beta tags and download assets are unchanged.

## v0.4.0-beta — 2026-10-19 (pre-release; iPad acceptance pending)

- Windows-to-iPad plain-text sync: Unicode, line breaks, tabs and Emoji over the existing encrypted BLE transport.
- New CBT1 payload with a 64 KiB UTF-8 byte limit; no silent truncation, rich-text formatting or file transfer.
- Authenticated capability negotiation before text transmission; existing CBP1 image format, UUIDs and pairing key are preserved. New iPad builds can still receive images from older senders.
- Persistent text-sync switch, type-aware latest-content resend, iPad text preview and full-content recopy.
- Bounded read-only Win32 clipboard access, clipboard-change race handling, and exclusion of the sender's pairing key from automatic text transmission.
- Metadata-only logging; sensitive text requires pausing capture or disabling text sync.

Developed locally on 2026-10-08 and prepared for public pre-release on 2026-10-19. Both Windows and the iPad Swift Playgrounds project must be updated for text. Windows automated checks do not substitute for iPad compilation or foreground/background paste tests. No GitHub upload is performed by building or packaging.

## v0.3.1-beta — 2026-10-03

First public experimental release. Windows sender with an existing Swift Playgrounds iPad receiver.

- BLE GATT transport, per-user pairing key, challenge authentication and AES-GCM image encryption.
- In-memory PNG encoding, bounded compression and ordered notification pipeline; sequential fallback.
- Windows tray, connection status, pause, quality selection, resend, logs and optional sign-in startup.
- First-install script creates a unique pairing key without requiring an old session; preserves valid existing keys and rejects malformed configuration.
- Portable ZIPs, allowlisted packaging, third-party notices and SHA-256 checksums.
- Generalized setup and explicit compatibility/privacy boundaries.

Image wire protocol and existing iPad receive path are unchanged. Existing users do not need a new pairing key or iPad import. Background paste and latency remain environment-dependent; this is not a universally verified product.

Earlier local iterations: v0.1 feasibility prototype, v0.2 compression/notification optimization, v0.3 Windows tray packaging. Personal logs and local configuration are intentionally not published.
