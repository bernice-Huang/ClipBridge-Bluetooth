# Changelog

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
