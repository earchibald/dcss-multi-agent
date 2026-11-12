import FleetCore
import Foundation

let usage = """
ladder-fleet: play the brain's games on other Macs.

On the driving Mac (the server):
  ladder-fleet server [install|uninstall] [--repo DIR] [--out DIR] [--port 8091] [--download-port 8092]
      run the fleet server (foreground), or install it as a LaunchAgent. --repo: the checkout whose code
      hosts play (default: this git checkout); --out: where games land (default: <repo>/runs/brain)
  ladder-fleet invite [--minutes 30]       open pairing and print the command to run on a new host
  ladder-fleet hosts                       run hosts, what they offer and what they're doing
  ladder-fleet runs                        runs and their progress
  ladder-fleet selfplay --games N [--seed 1] [--model M] [--epsilon 0.2] [--name X]
  ladder-fleet eval MODEL... [--games 30] [--fresh]          MODEL may be 'baseline'
  ladder-fleet forks [ROOT...] [--points 200] [--alternatives 3] [--horizon 0] [--model M] [--fork-seed 0]
      each also takes: --style KEY=VALUE..., --hosts a,b, --max-per-host N, --per-worker 3, --wait
  ladder-fleet cancel RUN
  ladder-fleet forget HOST

On a run host:
  ladder-fleet join [SERVER] CODE [--name N] [--port 8091] [--no-install]
      pair with the server (found by Bonjour if SERVER is left out) and install the agent as a LaunchAgent
  ladder-fleet agent                       run the agent in the foreground (what the LaunchAgent runs)
  ladder-fleet check                       is the agent running, and can it reach its server? (and its log)
  ladder-fleet install                     (re)install the agent's LaunchAgent on a host that has joined
  ladder-fleet uninstall                   stop and remove the LaunchAgent (keeps the fleet folder)

The fleet folder is ~/Library/Application Support/LadderFleet ($LADDER_FLEET_HOME overrides).
An agent's limits live in its agent.json "policy": maxWorkers, reserveCores, allowOnBattery,
idleOnlyMinutes, gbPerWorker, minFreeDiskGB.
"""

struct Args {
    var positional: [String] = []
    var options: [String: [String]] = [:]
    var flags: Set<String> = []
    static let valueless: Set<String> = ["wait", "fresh", "no-install", "help"]

    init(_ argv: [String]) {
        var i = 0
        var lastMulti: String?
        while i < argv.count {
            let a = argv[i]
            if a.hasPrefix("--") {
                let key = String(a.dropFirst(2))
                lastMulti = nil
                if Self.valueless.contains(key) { flags.insert(key) }
                else if i + 1 < argv.count { options[key, default: []].append(argv[i + 1]); i += 1; lastMulti = key }
            } else if let k = lastMulti, k == "style" {
                options[k, default: []].append(a)       // --style a=1 b=2
            } else {
                positional.append(a)
            }
            i += 1
        }
    }

    func value(_ k: String) -> String? { options[k]?.last }
    func int(_ k: String) -> Int? { value(k).flatMap(Int.init) }
    func double(_ k: String) -> Double? { value(k).flatMap(Double.init) }
}

func fail(_ s: String) -> Never {
    FileHandle.standardError.write(Data("ladder-fleet: \(s)\n".utf8))
    exit(1)
}

func control(_ req: ControlRequest, home: FleetHome) async -> ControlResponse {
    do {
        let stream = try await NWByteStream.connect(unixPath: home.controlSocket)
        defer { stream.close() }
        let frames = Frames(stream)
        try await frames.send(try JSONEncoder().encode(req))
        let dec = JSONDecoder()
        dec.dateDecodingStrategy = .iso8601
        return try dec.decode(ControlResponse.self, from: try await frames.receive())
    } catch {
        fail("no fleet server on this Mac (start one with `ladder-fleet server`): \(error)")
    }
}

func ago(_ d: Date?) -> String {
    guard let d else { return "never" }
    let s = Int(-d.timeIntervalSinceNow)
    return s < 90 ? "\(s)s ago" : s < 5400 ? "\(s / 60)m ago" : "\(s / 3600)h ago"
}

func printHosts(_ rows: [HostRow]) {
    if rows.isEmpty { print("no run hosts paired yet: `ladder-fleet invite`"); return }
    for h in rows {
        let i = h.info
        let spec = i.map { "\($0.chip), \($0.perfCores)P+\($0.effCores)E, \(Int($0.memoryGB)) GB" } ?? "?"
        print("\(h.connected ? "●" : "○") \(h.name)  \(spec)  \(h.batches) batches, \(h.games) games")
        if let s = h.status {
            let v = s.vitals
            print("    \(s.state.rawValue), offers \(s.offer) (\(s.reason)); \(v.onAC ? "on power" : "on battery"), \(v.thermal),"
                  + " load \(String(format: "%.1f", v.load)), idle \(Int(v.idleSeconds))s, \(Int(v.freeDiskGB)) GB free")
            let r = s.readiness
            print("    uv \(r.uv?.replacingOccurrences(of: "uv ", with: "") ?? "-"), docker \(r.docker ?? "-")"
                  + "\(r.dockerCPUs.map { " (\($0) CPUs)" } ?? ""), DCSS \(r.dcss ? "up" : "down"), code \(r.bundleId ?? "-")")
            if let n = s.note { print("    note: \(n)") }
        } else if !h.connected, h.lastSeen == nil {
            print("    paired, but its agent hasn't connected yet: on that Mac, `~/ladder-fleet check` says why")
        } else if !h.connected {
            print("    offline, last seen \(ago(h.lastSeen))")
        }
        if let c = h.current { print("    playing \(c)") }
    }
}

func runLine(_ r: RunRow) -> String {
    let state = r.cancelled ? "cancelled" : r.finishedAt != nil ? "finished" : "running"
    var s = "\(r.id)  \(r.name)  \(state)  \(r.done)/\(r.total) played"
    if r.lost > 0 { s += ", \(r.lost) lost" }
    if r.inFlight > 0 || r.pending > 0 { s += ", \(r.inFlight) playing, \(r.pending) waiting" }
    if !r.byHost.isEmpty { s += "  [" + r.byHost.sorted { $0.key < $1.key }.map { "\($0.key) \($0.value)" }.joined(separator: ", ") + "]" }
    if let m = r.summary {
        s += String(format: "  mean depth %.2f, died %d", m["mean_depth"]?.double ?? 0, m["died"]?.int ?? 0)
    }
    if let n = r.note { s += "  (\(n))" }
    return s
}

func startRun(_ request: [String: JSONValue], _ a: Args, home: FleetHome) async {
    var req = request
    if let s = a.options["style"] { req["style"] = .array(s.map { .string($0) }) }
    let rr = RunRequest(request: .object(req), hosts: a.value("hosts")?.split(separator: ",").map(String.init),
                        maxPerHost: a.int("max-per-host"), gamesPerWorker: a.int("per-worker") ?? 3)
    guard case .runs(let rows) = await control(.run(rr), home: home) else {
        if case .error(let e) = await control(.runs, home: home) { fail(e) }
        fail("the server refused the run")
    }
    for r in rows { print(runLine(r)) }
    guard a.flags.contains("wait") else { return }
    let ids = Set(rows.filter { $0.finishedAt == nil }.map(\.id))
    var last: [String: String] = [:]
    while true {
        try? await Task.sleep(nanoseconds: 3_000_000_000)
        guard case .runs(let now) = await control(.runs, home: home) else { continue }
        let mine = now.filter { ids.contains($0.id) }
        for r in mine {
            let line = runLine(r)
            if last[r.id] != line { print("\(stamp()) \(line)"); last[r.id] = line }
        }
        if mine.allSatisfy({ $0.finishedAt != nil }) { break }
    }
}

let argv = Array(CommandLine.arguments.dropFirst())
guard let command = argv.first, command != "--help", command != "help" else { print(usage); exit(0) }
let args = Args(Array(argv.dropFirst()))
let home = FleetHome()

switch command {
case "server":
    let gitTop = try? await Shell.check("git", ["rev-parse", "--show-toplevel"])
    let repo = URL(fileURLWithPath: args.value("repo") ?? gitTop ?? FileManager.default.currentDirectoryPath).standardizedFileURL
    guard FileManager.default.fileExists(atPath: repo.appendingPathComponent("src/ladder/brain/fleet.py").path) else {
        fail("\(repo.path) has no src/ladder/brain/fleet.py: point --repo at a checkout with the fleet's Python side")
    }
    let out = URL(fileURLWithPath: args.value("out") ?? repo.appendingPathComponent("runs/brain").path).standardizedFileURL
    if args.positional.first == "uninstall" {
        await LaunchAgent.uninstall(LaunchAgent.serverLabel)
        print("removed LaunchAgent \(LaunchAgent.serverLabel)")
        exit(0)
    }
    if args.positional.first == "install" {
        var rest = ["server", "--repo", repo.path, "--out", out.path]
        for k in ["port", "download-port"] { if let v = args.value(k) { rest += ["--\(k)", v] } }
        do {
            let bin = try await LaunchAgent.install(home: home, label: LaunchAgent.serverLabel, arguments: rest,
                                                    log: "server.log", workingDirectory: repo.path)
            print("installed \(bin.path) as LaunchAgent \(LaunchAgent.serverLabel): it runs now and at every login")
            print("log: \(home.logs.appendingPathComponent("server.log").path)")
        } catch {
            fail("\(error)")
        }
        exit(0)
    }
    let cfg = ServerConfig(name: HostProbe.localName(), repo: repo, out: out,
                           port: UInt16(args.int("port") ?? Int(defaultFleetPort)),
                           downloadPort: UInt16(args.int("download-port") ?? Int(defaultDownloadPort)))
    do {
        let server = try FleetServer(cfg: cfg, home: home)
        try await server.start()
    } catch {
        fail("\(error)")
    }
    while true { try? await Task.sleep(nanoseconds: 3_600_000_000_000) }

case "invite":
    guard case .invite(let inv) = await control(.invite(minutes: args.int("minutes") ?? 30), home: home) else { fail("no invite") }
    print("""
    Invite code \(inv.code), open until \(DateFormatter.localizedString(from: inv.expires, dateStyle: .none, timeStyle: .short)).
    It pairs any number of hosts until then (5 wrong codes close it). On each run host:

      \(inv.command)

    The binary's SHA-256 is \(inv.sha256) (check with `shasum -a 256 ~/ladder-fleet`).
    """)

case "hosts":
    if case .hosts(let rows) = await control(.hosts, home: home) { printHosts(rows) }

case "runs", "status":
    if case .runs(let rows) = await control(.runs, home: home) {
        if rows.isEmpty { print("no runs yet") }
        for r in rows { print(runLine(r)) }
    }

case "selfplay":
    guard let games = args.int("games") else { fail("selfplay needs --games N") }
    var req: [String: JSONValue] = ["kind": .string("selfplay"), "games": .int(games), "seed": .int(args.int("seed") ?? 1),
                                    "epsilon": .double(args.double("epsilon") ?? 0.2)]
    if let m = args.value("model") { req["model"] = .string(m) }
    if let n = args.value("name") { req["name"] = .string(n) }
    await startRun(req, args, home: home)

case "eval", "versus":
    guard !args.positional.isEmpty else { fail("eval needs at least one model (or 'baseline')") }
    var req: [String: JSONValue] = ["kind": .string("eval"), "models": .array(args.positional.map { .string($0) }),
                                    "games": .int(args.int("games") ?? 30)]
    if args.flags.contains("fresh") { req["fresh"] = .bool(true) }
    await startRun(req, args, home: home)

case "forks":
    var req: [String: JSONValue] = ["kind": .string("forks"), "points": .int(args.int("points") ?? 200),
                                    "alternatives": .int(args.int("alternatives") ?? 3), "horizon": .int(args.int("horizon") ?? 0),
                                    "fork_seed": .int(args.int("fork-seed") ?? 0)]
    if !args.positional.isEmpty { req["roots"] = .array(args.positional.map { .string($0) }) }
    if let m = args.value("model") { req["model"] = .string(m) }
    if let n = args.value("name") { req["name"] = .string(n) }
    await startRun(req, args, home: home)

case "cancel":
    guard let id = args.positional.first else { fail("cancel needs a run id (see `ladder-fleet runs`)") }
    switch await control(.cancel(runId: id), home: home) {
    case .ok(let s): print(s)
    case .error(let e): fail(e)
    default: break
    }

case "forget":
    guard let name = args.positional.first else { fail("forget needs a host name") }
    switch await control(.forget(agent: name), home: home) {
    case .ok(let s): print(s)
    case .error(let e): fail(e)
    default: break
    }

case "join":
    // `join Eugene-M5.local ABCD-EFGH`, or `join ABCD EFGH` (server found by Bonjour)
    var pos = args.positional
    var server: String?
    if let first = pos.first, pos.count > 1, first.contains(".") || first.contains(":") || first == "localhost" {
        server = first
        pos.removeFirst()
    }
    let code = pos.joined()
    guard !code.isEmpty else { fail("join needs the invite code from `ladder-fleet invite`") }
    if server == nil {
        print("looking for a fleet server on the local network...")
        let found = await Join.browse()
        guard found.count == 1 else { fail(found.isEmpty ? "none found: give its name, e.g. Eugene-M5.local" : "several found (\(found.joined(separator: ", "))): name one") }
        server = "\(found[0]).local"
    }
    let port = UInt16(args.int("port") ?? Int(defaultFleetPort))
    do {
        try Join.unlockKeychain(server: server!)
        let serverName = try await Join.pair(home: home, server: server!, port: port, code: code, name: args.value("name"))
        print("+ paired with \(serverName); the fleet key is in this Mac's Keychain (dcss-ladder / \(home.keyAccount))")
        if args.flags.contains("no-install") {
            print("run `ladder-fleet agent` to start playing")
        } else {
            let since = Date()
            let bin = try await LaunchAgent.install(home: home)
            print("installed \(bin.path) as LaunchAgent \(LaunchAgent.label); it is starting now")
            print("log: \(home.logs.appendingPathComponent("agent.log").path); limits: \(home.file("agent.json").path)")
            await Join.watch(home: home, server: server!, since: since)
        }
    } catch {
        fail("\(error)")
    }

case "agent":
    guard let cfg = home.load(AgentConfig.self, "agent.json") else { fail("not joined to a fleet: run `ladder-fleet join`") }
    let agent = FleetAgent(home: home, config: cfg)
    say("* fleet agent \(HostProbe.info(name: cfg.name).name) for \(cfg.server):\(cfg.port)")
    await agent.runForever()

case "install":
    guard let cfg = home.load(AgentConfig.self, "agent.json") else { fail("not joined to a fleet: run `ladder-fleet join`") }
    do {
        let since = Date()
        let bin = try await LaunchAgent.install(home: home)
        print("installed \(bin.path) as LaunchAgent \(LaunchAgent.label); it is starting now")
        print("log: \(home.logs.appendingPathComponent("agent.log").path)")
        await Join.watch(home: home, server: cfg.server, since: since)
    } catch { fail("\(error)") }

case "check":
    // On a run host: is the agent running, and can it reach its server?
    guard let cfg = home.load(AgentConfig.self, "agent.json") else { fail("not joined to a fleet: run `ladder-fleet join`") }
    let job = try? await Shell.run("/bin/launchctl", ["print", "gui/\(getuid())/\(LaunchAgent.label)"])
    let running = job?.status == 0 && (job?.out.contains("state = running") ?? false)
    print("agent \(HostProbe.info(name: cfg.name).name) for \(cfg.server):\(cfg.port): LaunchAgent "
          + (job?.status == 0 ? (running ? "running" : "loaded, not running") : "not installed (`ladder-fleet install`)"))
    if let link = AgentLink.load(home) {
        print("link: \(link.state.rawValue)\(link.detail.map { " (\($0))" } ?? ""), since \(ago(link.at))")
        if link.state == .blocked { print("\n" + AgentLink.blockedHelp(server: cfg.server) + "\n") }
        if link.state == .connected { print("setup and offers: `ladder-fleet hosts` on \(cfg.server)") }
    } else {
        print("link: no word from the agent yet")
    }
    let logURL = home.logs.appendingPathComponent("agent.log")
    if let text = try? String(contentsOf: logURL, encoding: .utf8) {
        print("last lines of \(logURL.path):")
        for line in text.split(separator: "\n").suffix(8) { print("  \(line)") }
    }

case "uninstall":
    await LaunchAgent.uninstall(LaunchAgent.label)
    print("removed LaunchAgent \(LaunchAgent.label); the fleet folder \(home.root.path) and its Keychain item are kept")

default:
    print(usage)
    exit(2)
}
