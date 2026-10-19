# BLE/1 image and negotiated text extension

Developer reference. For installation, start with the [user guide](../user/quick-start.md).

The service/characteristic UUIDs, challenge HMAC, AES-128-GCM AAD (`ClipBridge/1`), 9-byte little-endian frame header, 32-packet ACK window and receipt remain unchanged. Pairing configuration stays `protocol: 1`; no key rotation is required.

## Text negotiation

After normal authentication the Windows sender emits `READY(4, id=0, value=32 | (1 << 16))`. The lower 16 bits remain the ACK window. Bit 16 announces text support; older iPad receivers ignore this value.

A new receiver seeing bit 16 writes the two bytes `[21, 1]` (CAPABILITIES, TEXT). The sender accepts this only from the currently authenticated, subscribed identity. Capability state is cleared on fresh authentication, STOP or disconnect. Text is never sent before negotiation. A new receiver connected to an old sender (READY value 32) does not send command 21 and remains image-only.

## Decrypted payloads

The common header is `<4sIIQ` (20 bytes, little endian): magic, two 32-bit fields, capture timestamp in Unix milliseconds. Encryption is nonce(12) + AES-GCM ciphertext + tag(16), authenticated by the unchanged AAD.

- `CBP1`: existing width/height fields and PNG bytes, unchanged.
- `CBT1`: both 32-bit fields must be zero; body is strict UTF-8, 1..65536 bytes, no NUL. Invalid encoding/header/size is rejected before clipboard writes; data is never truncated.

Both types reuse START/CHUNK/END, ordered notifications, ACK and receipt. Text limits apply to UTF-8 bytes rather than character count. Content is encrypted as one payload, not per fragment. Receipts report a clipboard **write attempt**, not verified paste success.

Windows prioritizes actual clipboard images; otherwise it reads CF_UNICODETEXT with bounded HGLOBAL access. CF_HDROP, empty/invalid/oversized text, and text containing the sender's own key are not sent. Rich-text formatting is not transferred. Only new clipboard changes are observed; repeated text copies can resend, and only the latest pending content is retained.

The iPad uses `UTType.png` or `UTType.utf8PlainText` in `UIPasteboard.setItems`, local-only with a 10-minute expiry. The app's latest-content cache and preview are in memory. Background availability still depends on iPadOS and the runtime container; the extension does not grant new background execution privileges.
