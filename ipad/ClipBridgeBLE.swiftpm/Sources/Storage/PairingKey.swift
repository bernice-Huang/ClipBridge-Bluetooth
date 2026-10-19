import Foundation
import Security

enum PairingKey {
    static let service = "local.clipbridge.ble.prototype"
    static var query: [String: Any] {
        [kSecClass as String: kSecClassGenericPassword,
         kSecAttrService as String: service, kSecAttrAccount as String: "pairing"]
    }
    static func load() -> String {
        var q = query
        q[kSecReturnData as String] = true
        q[kSecMatchLimit as String] = kSecMatchLimitOne
        var result: CFTypeRef?
        guard SecItemCopyMatching(q as CFDictionary, &result) == errSecSuccess,
              let data = result as? Data else { return "" }
        return String(data: data, encoding: .utf8) ?? ""
    }
    static func save(_ text: String) -> Bool {
        let data = Data(text.utf8)
        let update = [kSecValueData as String: data]
        var result = SecItemUpdate(query as CFDictionary, update as CFDictionary)
        if result == errSecItemNotFound {
            var q = query
            q[kSecValueData as String] = data
            q[kSecAttrAccessible as String] = kSecAttrAccessibleAfterFirstUnlockThisDeviceOnly
            result = SecItemAdd(q as CFDictionary, nil)
        }
        return result == errSecSuccess
    }
}
