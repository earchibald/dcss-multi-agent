import Foundation

typealias JSON = [String: Any]

/// The cockpit's event stream, held once for the whole app. Browsers open at most six HTTP/1.1
/// connections to a host, so a window per panel can't each keep its own EventSource: the app
/// reads `/events` here and relays every event to the panels (`Panel.send`).
@MainActor
final class Cockpit {
    var port: Int { Prefs.port }
    var base: URL { URL(string: "http://127.0.0.1:\(port)/")! }

    private(set) var up = false
    private(set) var boot: String?
    private(set) var settings: JSON = [:]
    private(set) var status: JSON = [:]
    private(set) var run: JSON = [:]
    private(set) var links: JSON = [:]
    private(set) var pending: JSON?

    /// Every event but the hello, parsed and as the server sent it.
    var onEvent: ((JSON, String) -> Void)?
    /// The stream connected (true) or dropped (false).
    var onUp: ((Bool) -> Void)?
    /// A new decision is waiting (or none is): fires when the decision's id changes.
    var onPending: ((_ new: JSON?, _ old: JSON?) -> Void)?
    var onGameEnd: ((JSON) -> Void)?
    var onChange: (() -> Void)?

    private var task: Task<Void, Never>?
    private let session: URLSession = {
        let c = URLSessionConfiguration.ephemeral
        c.timeoutIntervalForRequest = 60           // the server pings every 15 s
        c.timeoutIntervalForResource = .infinity
        c.requestCachePolicy = .reloadIgnoringLocalCacheData
        return URLSession(configuration: c)
    }()

    func start() {
        task?.cancel()
        task = Task { [weak self] in
            while !Task.isCancelled {
                await self?.listen()
                self?.dropped()
                try? await Task.sleep(for: .seconds(1.5))
            }
        }
    }

    private func listen() async {
        var req = URLRequest(url: base.appending(path: "events"))
        req.setValue("text/event-stream", forHTTPHeaderField: "Accept")
        do {
            let (bytes, resp) = try await session.bytes(for: req)
            guard (resp as? HTTPURLResponse)?.statusCode == 200 else { return }
            for try await line in bytes.lines {
                guard line.hasPrefix("data: ") else { continue }     // ": ping" keeps the line alive
                let raw = String(line.dropFirst(6))
                guard let e = try? JSONSerialization.jsonObject(with: Data(raw.utf8)) as? JSON else { continue }
                handle(e, raw)
            }
        } catch {}
    }

    private func dropped() {
        guard up else { return }
        up = false
        onUp?(false)
        onChange?()
    }

    private func handle(_ e: JSON, _ raw: String) {
        let ev = e["ev"] as? String
        switch ev {
        case "hello":
            boot = e["boot"] as? String
            settings = e["settings"] as? JSON ?? [:]
            status = e["status"] as? JSON ?? [:]
            run = e["run"] as? JSON ?? [:]
            links = e["links"] as? JSON ?? [:]
            up = true
            setPending(e["pending"] as? JSON)
            onUp?(true)
        case "settings": settings = e["settings"] as? JSON ?? settings
        case "status": status = e["status"] as? JSON ?? status
        case "run": run = e["run"] as? JSON ?? run
        case "pending": setPending(e["pending"] as? JSON)
        case "game_end": onGameEnd?(e)
        default: break
        }
        if ev != "hello" { onEvent?(e, raw) }
        onChange?()
    }

    private func setPending(_ p: JSON?) {
        let old = pending
        pending = p
        if (old?["id"] as? String) != (p?["id"] as? String) { onPending?(p, old) }
    }

    // MARK: reading

    /// The hello a panel starts from: what `/events` sends a new subscriber.
    func hello() async -> String? {
        guard let (data, resp) = try? await session.data(from: base.appending(path: "api/state")),
              (resp as? HTTPURLResponse)?.statusCode == 200,
              var state = try? JSONSerialization.jsonObject(with: data) as? JSON else { return nil }
        state["ev"] = "hello"
        guard let out = try? JSONSerialization.data(withJSONObject: state) else { return nil }
        return String(decoding: out, as: UTF8.self)
    }

    var runState: String { up ? (run["state"] as? String ?? "connecting") : "offline" }
    var running: Bool { up && ["starting", "running", "stopping"].contains(runState) }
    var snapshot: JSON { status["snapshot"] as? JSON ?? [:] }
    var held: Bool { settings["held"] as? Bool ?? false }
    var paused: Bool { settings["paused"] as? Bool ?? false }
    var delay: Double { (settings["delay"] as? NSNumber)?.doubleValue ?? 0 }
    var mode: String { settings["mode"] as? String ?? "assisted" }

    /// The pending decision's options, split into choices (numbered) and exits.
    var choices: [JSON] { (pending?["options"] as? [JSON] ?? []).filter { !($0["exit"] as? Bool ?? false) } }
    var exits: [JSON] { (pending?["options"] as? [JSON] ?? []).filter { $0["exit"] as? Bool ?? false } }

    /// "D:3 · turn 1204 · HP 24/30"
    var placeLine: String {
        let s = snapshot
        guard let place = s["place"] as? String, !place.isEmpty else { return "" }
        return "\(place) · turn \(s["turn"] ?? "–") · HP \(s["hp"] ?? "–")/\(s["hp_max"] ?? "–")"
    }

    // MARK: acting

    @discardableResult
    func post(_ path: String, _ body: JSON) async -> String? {
        var req = URLRequest(url: base.appending(path: path))
        req.httpMethod = "POST"
        req.setValue("application/json", forHTTPHeaderField: "Content-Type")
        req.httpBody = try? JSONSerialization.data(withJSONObject: body)
        guard let (data, _) = try? await session.data(for: req) else { return "the cockpit isn't running" }
        return (try? JSONSerialization.jsonObject(with: data) as? JSON)?["error"] as? String
    }

    func act(_ path: String, _ body: JSON = [:]) {
        Task { if let err = await post(path, body) { Alerts.toast(err) } }
    }

    func decide(_ choice: String, id: String? = nil) {
        guard let id = id ?? pending?["id"] as? String else { return }
        act("api/decide", ["id": id, "choice": choice])
    }

    func toggleHold() { act("api/hold", ["hold": !held]) }
    func step(_ n: Int = 1) { act("api/step", ["n": n]) }
    func takeWheel() { act("api/stop") }
    func setMode(_ m: String) { act("api/mode", ["mode": m]) }
    func setDelay(_ d: Double) { act("api/speed", ["delay": d]) }

    static let speeds: [Double] = [0, 0.25, 0.5, 1, 2, 3, 5]

    func slower() { setDelay(Self.speeds.first { $0 > delay + 0.001 } ?? delay) }
    func faster() { setDelay(Self.speeds.last { $0 < delay - 0.001 } ?? 0) }
}
