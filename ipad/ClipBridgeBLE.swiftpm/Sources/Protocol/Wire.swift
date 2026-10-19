import Foundation
import CoreBluetooth

enum Wire {
    static let service = CBUUID(string: "8D6B3F00-E815-4C55-B109-45BDFFB271F0")
    static let info = CBUUID(string: "8D6B3F01-E815-4C55-B109-45BDFFB271F0")
    static let control = CBUUID(string: "8D6B3F02-E815-4C55-B109-45BDFFB271F0")
    static let data = CBUUID(string: "8D6B3F03-E815-4C55-B109-45BDFFB271F0")
    static let maxBytes = 2 * 1024 * 1024 + 48
    static let maxText = 64 * 1024
    static let readyText: UInt32 = 1 << 16
    static let window = 32
    static let aad = Data("ClipBridge/1".utf8)
    static let auth = Data("ClipBridge/auth/1".utf8)
}

extension Data {
    func u32(_ at: Int) -> UInt32 {
        (0..<4).reduce(UInt32(0)) { $0 | (UInt32(self[startIndex + at + $1]) << ($1 * 8)) }
    }
    func u64(_ at: Int) -> UInt64 {
        (0..<8).reduce(UInt64(0)) { $0 | (UInt64(self[startIndex + at + $1]) << ($1 * 8)) }
    }
    mutating func appendU32(_ value: UInt32) {
        for shift in stride(from: 0, to: 32, by: 8) { append(UInt8((value >> shift) & 255)) }
    }
    init?(hex: String, expectedCount: Int = 16) {
        guard hex.count == expectedCount * 2 else { return nil }
        var bytes = [UInt8]()
        var index = hex.startIndex
        for _ in 0..<expectedCount {
            let end = hex.index(index, offsetBy: 2)
            guard let byte = UInt8(hex[index..<end], radix: 16) else { return nil }
            bytes.append(byte); index = end
        }
        self.init(bytes)
    }
}
