import Foundation
import CryptoKit

enum WireSelfTest {
    // Synthetic interoperability vector; NOT the user's real pairing key or image.
    static func run() throws {
        let key = SymmetricKey(data: Data((0..<16).map { UInt8($0) }))
        let hex = "000102030405060708090a0bd02ef7ff641bf75448d2618a76417108b3261ae625889e828953daadb109ad40ed852a69f99c05ce7ebd"
        guard let wire = Data(hex: hex, expectedCount: 54) else { throw Failure.vector }
        let box = try AES.GCM.SealedBox(combined: wire)
        let plain = try AES.GCM.open(box, using: key, authenticating: Wire.aad)
        guard plain.count == 26, plain.prefix(4) == Data("CBP1".utf8),
              plain.u32(4) == 2, plain.u32(8) == 3, plain.u64(12) == 123456,
              plain.dropFirst(20) == Data("vector".utf8) else { throw Failure.vector }
        let proof = HMAC<SHA256>.authenticationCode(for: Wire.auth + Data((0..<16).map { UInt8($0) }), using: key)
        guard Data(proof.prefix(16)) == Data(hex: "4d06a2c8ab55783e7134fe072b02c7f2") else { throw Failure.vector }
        let textHex = "000102030405060708090a0bd02ef3ff661bf7544bd2618a76417108b3261ae6b7505d13439c1e919807ce05f5e6a99e90e7d2c24dfe458eaeecf7a0c56f8b69862b34a991f0311617bed155762aa85d67"
        guard let textWire = Data(hex: textHex, expectedCount: 81) else { throw Failure.vector }
        let textBox = try AES.GCM.SealedBox(combined: textWire)
        let textPlain = try AES.GCM.open(textBox, using: key, authenticating: Wire.aad)
        guard textPlain.prefix(4) == Data("CBT1".utf8), textPlain.u32(4) == 0,
              textPlain.u32(8) == 0, textPlain.u64(12) == 123456,
              String(data: textPlain.dropFirst(20), encoding: .utf8) == "你好，ClipBridge!\r\nLine 2\t🙂" else { throw Failure.vector }
    }
    enum Failure: Error { case vector }
}
