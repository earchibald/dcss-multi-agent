import AppKit
import Security

enum Prefs {
    static let d = UserDefaults.standard

    /// The repo the app was built from (build.sh writes it into Info.plist).
    static var builtRepo: String {
        let s = Bundle.main.object(forInfoDictionaryKey: "LadderRepo") as? String ?? ""
        return s.hasPrefix("__") ? FileManager.default.currentDirectoryPath : s
    }

    static func register() {
        d.register(defaults: [
            "repo": builtRepo,
            "port": 8090,
            "cockpitArgs": "--idle-minutes 10 --jev",
            "webtiles": "http://localhost:8080/",
            "startOnLaunch": false,
            "notify": true,
            "followDecisions": true,
        ])
    }

    static var repo: String { d.string(forKey: "repo") ?? builtRepo }
    static var port: Int { d.integer(forKey: "port") }
    static var cockpitArgs: String { d.string(forKey: "cockpitArgs") ?? "" }
    static var webtiles: String { d.string(forKey: "webtiles") ?? "http://localhost:8080/" }
    static var startOnLaunch: Bool { d.bool(forKey: "startOnLaunch") }
    static var notify: Bool { d.bool(forKey: "notify") }
    /// Bring the "Your call" window to the front when a decision arrives.
    static var followDecisions: Bool { d.bool(forKey: "followDecisions") }
}

/// Errors from a cockpit action: shown where the page shows its own (the Control panel's toast).
enum Alerts {
    static var show: ((String) -> Void)?
    static func toast(_ text: String) {
        NSSound.beep()
        show?(text)
    }
}

enum Keychain {
    /// A generic password, read when needed and never kept. The cockpit stores the webtiles
    /// account's password under service `dcss-ladder`, account `dcss-account/<user>`.
    static func password(service: String, account: String) -> String? {
        let q: [String: Any] = [
            kSecClass as String: kSecClassGenericPassword,
            kSecAttrService as String: service,
            kSecAttrAccount as String: account,
            kSecReturnData as String: true,
            kSecMatchLimit as String: kSecMatchLimitOne,
        ]
        var out: CFTypeRef?
        guard SecItemCopyMatching(q as CFDictionary, &out) == errSecSuccess, let data = out as? Data else { return nil }
        return String(data: data, encoding: .utf8)
    }
}

func jsString(_ s: String) -> String {
    let data = try! JSONSerialization.data(withJSONObject: [s])
    return String(decoding: data, as: UTF8.self).dropFirst().dropLast().description
}
