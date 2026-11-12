import Foundation
import IOKit
import IOKit.ps
import IOKit.pwr_mgt
import Security
import SystemConfiguration

// MARK: - where the fleet keeps things

/// ~/Library/Application Support/LadderFleet, or $LADDER_FLEET_HOME (tests, a second agent on one Mac).
public struct FleetHome: Sendable {
    public let root: URL

    public init(root: URL? = nil) {
        if let root {
            self.root = root
        } else if let env = ProcessInfo.processInfo.environment["LADDER_FLEET_HOME"], !env.isEmpty {
            self.root = URL(fileURLWithPath: (env as NSString).expandingTildeInPath)
        } else {
            self.root = FileManager.default.homeDirectoryForCurrentUser
                .appendingPathComponent("Library/Application Support/LadderFleet")
        }
    }

    public func dir(_ name: String) -> URL {
        let u = root.appendingPathComponent(name)
        try? FileManager.default.createDirectory(at: u, withIntermediateDirectories: true)
        return u
    }

    public func file(_ name: String) -> URL {
        _ = dir("")
        return root.appendingPathComponent(name)
    }

    public var bin: URL { dir("bin") }
    public var logs: URL { dir("logs") }
    public var controlSocket: String { file("control.sock").path }

    /// Keychain account names are per home, so a test fleet doesn't take the real fleet's key.
    public var keyAccount: String {
        ProcessInfo.processInfo.environment["LADDER_FLEET_HOME"].map { _ in
            FleetCrypto.fleetKeyAccount + "-" + FleetCrypto.sha256Hex(Data(root.path.utf8)).prefix(8)
        } ?? FleetCrypto.fleetKeyAccount
    }

    public func load<T: Decodable>(_ type: T.Type, _ name: String) -> T? {
        guard let d = try? Data(contentsOf: file(name)) else { return nil }
        let dec = JSONDecoder()
        dec.dateDecodingStrategy = .iso8601
        return try? dec.decode(type, from: d)
    }

    public func save<T: Encodable>(_ value: T, _ name: String) throws {
        let enc = JSONEncoder()
        enc.outputFormatting = [.prettyPrinted, .sortedKeys]
        enc.dateEncodingStrategy = .iso8601
        try enc.encode(value).write(to: file(name), options: .atomic)
    }
}

// MARK: - Keychain (service dcss-ladder, like every other secret in this project)

public enum Keychain {
    /// The login keychain is locked and macOS may not ask (an SSH session, or nobody logged in on the
    /// screen): SecItem calls fail with errSecInteractionNotAllowed (-25308).
    public struct Locked: Error, CustomStringConvertible {
        public init() {}
        public var description: String {
            "this Mac's login keychain is locked (-25308). Over SSH, unlock it first with `security unlock-keychain`; "
                + "for the agent, someone must be logged in on this Mac's screen (or automatic login turned on)"
        }
    }

    public static func get(service: String = FleetCrypto.keychainService, account: String) -> Data? {
        try? read(service: service, account: account)
    }

    /// nil if there is no such item; throws Locked if the keychain can't be read right now.
    public static func read(service: String = FleetCrypto.keychainService, account: String) throws -> Data? {
        let q: [String: Any] = [kSecClass as String: kSecClassGenericPassword, kSecAttrService as String: service,
                                kSecAttrAccount as String: account, kSecReturnData as String: true,
                                kSecMatchLimit as String: kSecMatchLimitOne]
        var out: CFTypeRef?
        let status = SecItemCopyMatching(q as CFDictionary, &out)
        if status == errSecInteractionNotAllowed { throw Locked() }
        guard status == errSecSuccess else { return nil }
        return out as? Data
    }

    // SecKeychainGetStatus and SecKeychainUnlock are deprecated, but they are still the only API for the
    // file-based login keychain, which is where SecItem puts a generic password like the fleet key.

    /// Whether this user's default (login) keychain is locked right now.
    public static func isLocked() -> Bool {
        var status: SecKeychainStatus = 0
        guard SecKeychainGetStatus(nil, &status) == errSecSuccess else { return false }
        return status & SecKeychainStatus(kSecUnlockStateStatus) == 0
    }

    public enum UnlockOutcome: Equatable { case unlocked, declined, noTerminal, wrongPassword, failed(OSStatus) }

    /// Read the login password from the terminal with echo off (readpassphrase, straight from /dev/tty)
    /// and unlock the default keychain with it in this process. The password is never on a command line,
    /// never in another process, and its buffer is zeroed before returning. An empty line means "no".
    public static func unlockAtTerminal(prompt: String, attempts: Int = 3,
                                        retry: (Int) -> Void = { _ in }) -> UnlockOutcome {
        let size = 1024
        let buf = UnsafeMutablePointer<CChar>.allocate(capacity: size)
        defer { memset_s(buf, size, 0, size); buf.deallocate() }
        for attempt in 1...max(1, attempts) {
            memset_s(buf, size, 0, size)
            guard let pw = readpassphrase(prompt, buf, size, RPP_REQUIRE_TTY) else { return .noTerminal }
            let len = strlen(pw)
            if len == 0 { return .declined }
            let status = SecKeychainUnlock(nil, UInt32(len), pw, true)
            memset_s(buf, size, 0, size)
            if status == errSecSuccess { return .unlocked }
            guard status == errSecAuthFailed else { return .failed(status) }
            if attempt < attempts { retry(attempts - attempt) }
        }
        return .wrongPassword
    }

    public static func set(_ value: Data, service: String = FleetCrypto.keychainService, account: String) throws {
        let q: [String: Any] = [kSecClass as String: kSecClassGenericPassword, kSecAttrService as String: service,
                                kSecAttrAccount as String: account]
        let status = SecItemUpdate(q as CFDictionary, [kSecValueData as String: value] as CFDictionary)
        if status == errSecInteractionNotAllowed { throw Locked() }
        if status == errSecItemNotFound {
            var add = q
            add[kSecValueData as String] = value
            add[kSecAttrLabel as String] = "\(service) (\(account))"
            let s = SecItemAdd(add as CFDictionary, nil)
            if s == errSecInteractionNotAllowed { throw Locked() }
            guard s == errSecSuccess else { throw FleetError.failed("Keychain add failed: \(s)") }
        } else if status != errSecSuccess {
            throw FleetError.failed("Keychain update failed: \(status)")
        }
    }

    public static func delete(service: String = FleetCrypto.keychainService, account: String) {
        let q: [String: Any] = [kSecClass as String: kSecClassGenericPassword, kSecAttrService as String: service,
                                kSecAttrAccount as String: account]
        SecItemDelete(q as CFDictionary)
    }
}

// MARK: - what this Mac is and how it's doing

public enum HostProbe {
    public static func sysctlInt(_ name: String) -> Int? {
        var v: Int64 = 0
        var size = MemoryLayout<Int64>.size
        guard sysctlbyname(name, &v, &size, nil, 0) == 0 else { return nil }
        return Int(v)
    }

    public static func sysctlString(_ name: String) -> String? {
        var size = 0
        guard sysctlbyname(name, nil, &size, nil, 0) == 0, size > 0 else { return nil }
        var buf = [CChar](repeating: 0, count: size)
        guard sysctlbyname(name, &buf, &size, nil, 0) == 0 else { return nil }
        return String(cString: buf)
    }

    /// The Bonjour name ("Eugene-M5"), which is also how the fleet names this host.
    public static func localName() -> String {
        if let n = SCDynamicStoreCopyLocalHostName(nil) as String? { return n }
        return ProcessInfo.processInfo.hostName.replacingOccurrences(of: ".local", with: "")
    }

    public static func info(name: String? = nil) -> HostInfo {
        var u = utsname()
        uname(&u)
        let arch = withUnsafeBytes(of: &u.machine) { String(cString: $0.bindMemory(to: CChar.self).baseAddress!) }
        let perf = sysctlInt("hw.perflevel0.physicalcpu") ?? sysctlInt("hw.physicalcpu") ?? 1
        let eff = sysctlInt("hw.perflevel1.physicalcpu") ?? 0
        let v = ProcessInfo.processInfo.operatingSystemVersion
        return HostInfo(name: name ?? localName(), model: sysctlString("hw.model") ?? "?",
                        chip: sysctlString("machdep.cpu.brand_string") ?? "?", arch: arch,
                        perfCores: perf, effCores: eff,
                        memoryGB: Double(ProcessInfo.processInfo.physicalMemory) / 1_073_741_824,
                        os: "macOS \(v.majorVersion).\(v.minorVersion).\(v.patchVersion)")
    }

    public static func vitals(disk: URL) -> Vitals {
        Vitals(onAC: onAC(), thermal: thermal(), idleSeconds: idleSeconds(), freeDiskGB: freeGB(disk), load: load())
    }

    public static func onAC() -> Bool {
        guard let snap = IOPSCopyPowerSourcesInfo()?.takeRetainedValue(),
              let type = IOPSGetProvidingPowerSourceType(snap)?.takeUnretainedValue() as String? else { return true }
        return type == kIOPMACPowerKey
    }

    public static func thermal() -> String {
        switch ProcessInfo.processInfo.thermalState {
        case .nominal: return "nominal"
        case .fair: return "fair"
        case .serious: return "serious"
        case .critical: return "critical"
        @unknown default: return "unknown"
        }
    }

    public static func idleSeconds() -> Double {
        let service = IOServiceGetMatchingService(kIOMainPortDefault, IOServiceMatching("IOHIDSystem"))
        guard service != 0 else { return 0 }
        defer { IOObjectRelease(service) }
        guard let prop = IORegistryEntryCreateCFProperty(service, "HIDIdleTime" as CFString, kCFAllocatorDefault, 0)?
            .takeRetainedValue() else { return 0 }
        if let n = prop as? NSNumber { return n.doubleValue / 1e9 }
        if let d = prop as? Data, d.count >= 8 { return Double(d.withUnsafeBytes { $0.loadUnaligned(as: UInt64.self) }) / 1e9 }
        return 0
    }

    public static func freeGB(_ url: URL) -> Double {
        let v = try? url.resourceValues(forKeys: [.volumeAvailableCapacityForImportantUsageKey])
        return Double(v?.volumeAvailableCapacityForImportantUsage ?? 0) / 1e9
    }

    public static func load() -> Double {
        var l = [Double](repeating: 0, count: 3)
        return getloadavg(&l, 3) > 0 ? l[0] : 0
    }
}

/// Keeps the Mac awake while games are being played (an asleep Mac loses its games).
public final class SleepGuard: @unchecked Sendable {
    private var id: IOPMAssertionID = 0
    private var held = false
    public init() {}

    public func hold(_ reason: String) {
        guard !held else { return }
        held = IOPMAssertionCreateWithName(kIOPMAssertionTypePreventUserIdleSystemSleep as CFString,
                                           IOPMAssertionLevel(kIOPMAssertionLevelOn), reason as CFString, &id) == kIOReturnSuccess
    }

    public func release() {
        guard held else { return }
        IOPMAssertionRelease(id)
        held = false
    }
}
