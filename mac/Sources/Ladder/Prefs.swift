import AppKit

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

func jsString(_ s: String) -> String {
    let data = try! JSONSerialization.data(withJSONObject: [s])
    return String(decoding: data, as: UTF8.self).dropFirst().dropLast().description
}
