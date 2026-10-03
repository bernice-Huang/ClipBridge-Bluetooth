import Foundation
import Combine
import CoreBluetooth
import CryptoKit
import Security
import UIKit
import UniformTypeIdentifiers

private enum Wire {
    static let service = CBUUID(string: "8D6B3F00-E815-4C55-B109-45BDFFB271F0")
    static let info = CBUUID(string: "8D6B3F01-E815-4C55-B109-45BDFFB271F0")
    static let control = CBUUID(string: "8D6B3F02-E815-4C55-B109-45BDFFB271F0")
    static let data = CBUUID(string: "8D6B3F03-E815-4C55-B109-45BDFFB271F0")
    static let maxBytes = 2 * 1024 * 1024 + 48
    static let window = 32
    static let aad = Data("ClipBridge/1".utf8)
    static let auth = Data("ClipBridge/auth/1".utf8)
}

private extension Data {
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

private enum WireSelfTest {
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
    }
    enum Failure: Error { case vector }
}

private enum PairingKey {
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

// CoreBluetooth callbacks use the main queue. Swift 5 mode avoids importing
// Swift 6 strict-concurrency assumptions into this Playgrounds prototype.
final class BLEBridge: NSObject, ObservableObject, CBCentralManagerDelegate, CBPeripheralDelegate {
    @Published var keyText = PairingKey.load()
    @Published var status = "未连接"
    @Published var ready = false
    @Published var progress = 0.0
    @Published var duration = "尚未接收"
    @Published var deliveryState = "尚未接收"
    @Published var clipboardState = "尚未尝试"
    @Published var image: UIImage?
    @Published var events = [String]()
    let backgroundConfigured = (Bundle.main.object(forInfoDictionaryKey: "UIBackgroundModes") as? [String] ?? []).contains("bluetooth-central")
    private var central: CBCentralManager?
    private var peripheral: CBPeripheral?
    private var control: CBCharacteristic?
    private var dataChar: CBCharacteristic?
    private var info: CBCharacteristic?
    private var key: SymmetricKey?
    private var manualStop = true
    private var retry: DispatchWorkItem?
    private var deadline: DispatchWorkItem?
    private var reconnectDelay = 1.0
    private var transfer: UInt32?
    private var total = 0
    private var payload = Data()
    private var packets = 0
    private var began: TimeInterval = 0
    private var latestPNG: Data?
    private var backgroundTask: UIBackgroundTaskIdentifier = .invalid

    func log(_ message: String) {
        let stamp = DateFormatter.localizedString(from: Date(), dateStyle: .none, timeStyle: .medium)
        events.insert("\(stamp) \(message)", at: 0)
        if events.count > 18 { events.removeLast(events.count - 18) }
    }

    func connect() {
        let text = keyText.filter { !$0.isWhitespace }.lowercased()
        guard let bytes = Data(hex: text) else {
            status = "请输入 Dell 显示的 32 位十六进制密钥"; return
        }
        do { try WireSelfTest.run() }
        catch { status = "加密协议自测失败"; log(error.localizedDescription); return }
        log("Python ↔ CryptoKit 固定向量自测通过")
        // Changing the key requires ending the old session, not authenticating it twice.
        stop()
        keyText = text; key = SymmetricKey(data: bytes)
        if !PairingKey.save(text) { log("钥匙串保存失败；这次连接仍可测试") }
        manualStop = false
        if central == nil {
            central = CBCentralManager(delegate: self, queue: .main,
                options: [CBCentralManagerOptionShowPowerAlertKey: true])
        } else if central?.state == .poweredOn {
            // Wait for didDisconnect if an old connection is still being closed.
            if peripheral == nil { scan() }
        } else { status = "等待蓝牙开启或授权" }
    }

    func stop() {
        manualStop = true
        retry?.cancel(); retry = nil
        central?.stopScan()
        if let p = peripheral {
            if ready { write(Data([20])) }
            central?.cancelPeripheralConnection(p)
        }
        ready = false; resetTransfer()
        status = "已停止"
    }

    private func scan() {
        guard !manualStop, central?.state == .poweredOn else { return }
        status = "搜索 Dell 的 ClipBridge 蓝牙服务…"
        central?.scanForPeripherals(withServices: [Wire.service],
            options: [CBCentralManagerScanOptionAllowDuplicatesKey: false])
    }

    func centralManagerDidUpdateState(_ central: CBCentralManager) {
        switch central.state {
        case .poweredOn: scan()
        case .poweredOff: status = "蓝牙未开启"; ready = false
        case .unauthorized: status = "蓝牙权限被拒绝，请到设置允许"; ready = false
        case .unsupported: status = "设备不支持此蓝牙功能"; ready = false
        default: status = "蓝牙正在初始化"; ready = false
        }
    }

    func centralManager(_ central: CBCentralManager, didDiscover p: CBPeripheral,
                        advertisementData: [String: Any], rssi RSSI: NSNumber) {
        guard !manualStop, peripheral == nil else { return }
        central.stopScan(); peripheral = p; p.delegate = self
        status = "正在连接 \(p.name ?? "Dell")…"
        central.connect(p, options: nil)
        let timeout = DispatchWorkItem { [weak self, weak p] in
            guard let self, let p, !self.ready else { return }
            self.log("连接或认证超过 12 秒，重试")
            self.central?.cancelPeripheralConnection(p)
        }
        retry = timeout; DispatchQueue.main.asyncAfter(deadline: .now() + 12, execute: timeout)
    }

    func centralManager(_ central: CBCentralManager, didConnect p: CBPeripheral) {
        status = "发现服务与特征…"
        p.discoverServices([Wire.service])
    }
    func centralManager(_ central: CBCentralManager, didFailToConnect p: CBPeripheral, error: Error?) {
        disconnected(error)
    }
    func centralManager(_ central: CBCentralManager, didDisconnectPeripheral p: CBPeripheral, error: Error?) {
        disconnected(error)
    }
    private func disconnected(_ error: Error?) {
        ready = false; peripheral = nil; info = nil; control = nil; dataChar = nil
        retry?.cancel(); resetTransfer()
        if manualStop { return }
        status = "连接中断，等待重连"
        if let error { log(error.localizedDescription) }
        let work = DispatchWorkItem { [weak self] in self?.scan() }
        retry = work; DispatchQueue.main.asyncAfter(deadline: .now() + reconnectDelay, execute: work)
        reconnectDelay = min(reconnectDelay * 2, 15)
    }

    func peripheral(_ p: CBPeripheral, didDiscoverServices error: Error?) {
        guard error == nil, let service = p.services?.first(where: { $0.uuid == Wire.service }) else {
            fail("找不到 ClipBridge 服务：\(error?.localizedDescription ?? "未知")"); return
        }
        p.discoverCharacteristics([Wire.info, Wire.control, Wire.data], for: service)
    }
    func peripheral(_ p: CBPeripheral, didDiscoverCharacteristicsFor service: CBService, error: Error?) {
        guard error == nil else { fail(error!.localizedDescription); return }
        info = service.characteristics?.first { $0.uuid == Wire.info }
        control = service.characteristics?.first { $0.uuid == Wire.control }
        dataChar = service.characteristics?.first { $0.uuid == Wire.data }
        guard let info, control != nil, let dataChar else { fail("蓝牙特征不完整"); return }
        if dataChar.isNotifying { p.readValue(for: info) }
        else { p.setNotifyValue(true, for: dataChar) }
    }
    func peripheral(_ p: CBPeripheral, didUpdateNotificationStateFor c: CBCharacteristic, error: Error?) {
        guard error == nil, c.isNotifying, let info else {
            fail("无法订阅图片通知：\(error?.localizedDescription ?? "未开启")"); return
        }
        status = "校验配对密钥…"; p.readValue(for: info)
    }
    func peripheral(_ p: CBPeripheral, didUpdateValueFor c: CBCharacteristic, error: Error?) {
        guard error == nil, let raw = c.value else { fail(error?.localizedDescription ?? "蓝牙数据为空"); return }
        if c.uuid == Wire.info {
            guard raw.count == 19, raw.prefix(3) == Data("CB1".utf8), let key else {
                fail("握手格式不匹配"); return
            }
            let proof = HMAC<SHA256>.authenticationCode(for: Wire.auth + raw.dropFirst(3), using: key)
            write(Data([16]) + Data(proof.prefix(16)))
        } else if c.uuid == Wire.data { receive(raw) }
    }
    func peripheral(_ p: CBPeripheral, didWriteValueFor c: CBCharacteristic, error: Error?) {
        if let error { fail("控制请求失败（检查配对密钥）：\(error.localizedDescription)") }
    }

    private func write(_ data: Data) {
        guard let peripheral, let control else { return }
        peripheral.writeValue(data, for: control, type: .withResponse)
    }
    private func fail(_ reason: String) {
        status = reason; log(reason); manualStop = true; ready = false
        retry?.cancel(); central?.stopScan(); resetTransfer()
        if let peripheral { central?.cancelPeripheralConnection(peripheral) }
    }
    func receiveLatest() { if ready { write(Data([19])) } }

    private func ack(_ id: UInt32) {
        var value = Data([17]); value.appendU32(id); value.appendU32(UInt32(payload.count))
        write(value)
    }
    private func receive(_ raw: Data) {
        guard raw.count >= 9 else { fail("通知长度错误"); return }
        let kind = raw[raw.startIndex], id = raw.u32(1), value = Int(raw.u32(5))
        if kind == 4 {
            ready = true; status = "已连接 · 等待 Dell 新截图"
            retry?.cancel(); reconnectDelay = 1; log("密钥认证成功，无需 IP 地址")
            return
        }
        guard ready else { return }
        if kind == 1 {
            guard raw.count == 9, value > 48, value <= Wire.maxBytes else {
                fail("图片超过 2 MiB 限制或帧格式错误"); return
            }
            resetTransfer(); transfer = id; total = value
            payload.reserveCapacity(value); began = ProcessInfo.processInfo.systemUptime
            progress = 0; status = "接收截图…"
            backgroundTask = UIApplication.shared.beginBackgroundTask(withName: "ClipBridge receive") { [weak self] in
                self?.log("系统后台执行时间到期，接收未完成")
                self?.resetTransfer()
            }
            let timeout = DispatchWorkItem { [weak self] in
                guard let self, self.transfer == id else { return }
                self.log("接收超过 20 秒，请重新连接或接收最新截图")
                self.resetTransfer(); self.status = "接收超时"
            }
            deadline = timeout; DispatchQueue.main.asyncAfter(deadline: .now() + 20, execute: timeout)
        } else if kind == 2 {
            guard transfer == id, value == payload.count, raw.count > 9,
                  payload.count + raw.count - 9 <= total else { fail("图片分片不连续，已放弃本次传输"); return }
            payload.append(raw.dropFirst(9)); packets += 1
            if packets % Wire.window == 0 || payload.count == total {
                progress = Double(payload.count) / Double(total); ack(id)
            }
        } else if kind == 3 {
            guard transfer == id, raw.count == 9, value == total, payload.count == total, let key else {
                fail("图片未传完整，不会写入剪贴板"); return
            }
            do {
                let box = try AES.GCM.SealedBox(combined: payload)
                let plain = try AES.GCM.open(box, using: key, authenticating: Wire.aad)
                guard plain.count > 20, plain.prefix(4) == Data("CBP1".utf8) else { throw ReceiveError.invalidImage }
                let width = Int(plain.u32(4)), height = Int(plain.u32(8))
                guard width > 0, height > 0, width <= 8192, height <= 8192,
                      width * height <= 32_000_000 else { throw ReceiveError.invalidImage }
                let png = Data(plain.dropFirst(20))
                guard let decoded = UIImage(data: png), let pixels = decoded.cgImage,
                      pixels.width == width, pixels.height == height else { throw ReceiveError.invalidImage }
                latestPNG = png; image = decoded
                let inBackground = UIApplication.shared.applicationState == .background
                deliveryState = inBackground ? "后台（需到 Goodnotes 验证粘贴）" : "前台或正在切换"
                copyLatest()
                let elapsed = ProcessInfo.processInfo.systemUptime - began
                duration = String(format: "%.3f 秒 · %.1f KiB（iPad 收到首帧至写入尝试）", elapsed, Double(png.count) / 1024)
                log("完整接收 \(width)×\(height)，完成时\(inBackground ? "后台" : "前台/切换中")；仅确认写入调用已执行")
                var receipt = Data([18]); receipt.appendU32(id)
                receipt.append(UInt8((inBackground ? 1 : 0) | 2))
                write(receipt); resetTransfer(); progress = 1
                status = "已接收 · 请在 Goodnotes 实际粘贴验证"
            } catch { fail("图片解密或完整性检查失败：\(error.localizedDescription)") }
        } else { fail("不支持的协议帧") }
    }

    func copyLatest() {
        guard let latestPNG else { return }
        UIPasteboard.general.setItems([[UTType.png.identifier: latestPNG]], options: [
            .localOnly: true, .expirationDate: Date().addingTimeInterval(600)
        ])
        // UIKit does not return a success boolean. Never label a background call as verified paste success.
        clipboardState = "已尝试写入；请实际粘贴确认（10 分钟过期）"
    }
    private func resetTransfer() {
        deadline?.cancel(); deadline = nil
        transfer = nil; total = 0; packets = 0; payload.removeAll(keepingCapacity: false)
        if backgroundTask != .invalid {
            UIApplication.shared.endBackgroundTask(backgroundTask); backgroundTask = .invalid
        }
    }
    private enum ReceiveError: Error { case invalidImage }
}
