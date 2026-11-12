import FleetCore
import Foundation
import Network

/// A run host's settings: which server, what it's called, what it may use. agent.json in the fleet home.
struct AgentConfig: Codable {
    var server: String
    var port: UInt16
    var name: String?
    var policy: AgentPolicy
}

/// Whether the agent can reach its server right now. link.json in the fleet home, so `join` and `check`
/// on the host can tell, even when the server can't (it only hears from agents that get through).
struct AgentLink: Codable {
    enum State: String, Codable { case connecting, blocked, connected, disconnected }
    var state: State
    var detail: String?
    var at: Date

    static func load(_ home: FleetHome) -> AgentLink? { home.load(AgentLink.self, "link.json") }

    static func blockedHelp(server: String) -> String {
        """
        macOS is keeping the agent off the local network, so it can't reach \(server).
        This is macOS's Local Network privacy. It applies to a LaunchAgent like this one, but not to
        anything run in Terminal or over SSH, which is why joining worked.
        To allow it, on this Mac's own screen (or over Screen Sharing), either:
          - click Allow when macOS asks whether "ladder-fleet" may find and connect to devices on your
            local network, or
          - open System Settings > Privacy & Security > Local Network and turn on ladder-fleet.
        The agent is waiting and connects as soon as it's allowed; nothing needs restarting. macOS
        remembers the choice for this Developer ID signature, so updates shouldn't ask again.
        """
    }
}

/// Plays batches for the server. One connection at a time, reconnecting forever; one batch at a time.
actor FleetAgent {
    let home: FleetHome
    var config: AgentConfig
    let info: HostInfo
    var prov: Provisioner!
    var channel: SecureChannel?
    var state: AgentState = .provisioning
    var note: String?
    var busyBatch: String?
    var running: Process?
    var waiters: [String: [CheckedContinuation<URL, Error>]] = [:]
    var provisioned: String?                     // the image id provisioning finished for
    var provisioning = false
    var nextStream: UInt32 = 2                    // even: the agent's streams
    let sleepGuard = SleepGuard()
    let logFile: FileHandle?

    init(home: FleetHome, config: AgentConfig) {
        self.home = home
        self.config = config
        info = HostProbe.info(name: config.name)
        let url = home.logs.appendingPathComponent("games.log")
        if !FileManager.default.fileExists(atPath: url.path) { FileManager.default.createFile(atPath: url.path, contents: nil) }
        logFile = try? FileHandle(forWritingTo: url)
        _ = try? logFile?.seekToEnd()
    }

    func setUp() {
        prov = Provisioner(home: home) { line in Task { await self.log(line) } }
    }

    /// Prints here, and tells the server.
    func log(_ line: String) {
        say(line)
        if let channel { Task { try? await channel.send(.log(line)) } }
    }

    func setLink(_ state: AgentLink.State, _ detail: String? = nil) {
        try? home.save(AgentLink(state: state, detail: detail, at: Date()), "link.json")
    }

    func blockedByLocalNetwork() {
        guard AgentLink.load(home)?.state != .blocked else { return }    // said so already
        setLink(.blocked, "Local Network privacy")
        say("blocked: " + AgentLink.blockedHelp(server: config.server).replacingOccurrences(of: "\n", with: "\n    "))
    }

    func runForever() async {
        setUp()
        setLink(.connecting)
        var delay: UInt64 = 2
        while true {
            do {
                try await session()
                delay = 2
                setLink(.disconnected, "the connection closed")
            } catch is NWByteStream.LocalNetworkBlocked {
                // already said so; try again soon, since an Allow only helps a fresh connection
                try? await Task.sleep(nanoseconds: 2_000_000_000)
                continue
            } catch let e as NWError where e == .posix(.ENETDOWN) {
                // the connection failed outright rather than waiting: the same Local Network block
                blockedByLocalNetwork()
            } catch {
                say("server \(config.server):\(config.port): \(error)")
                setLink(.disconnected, "\(error)")
            }
            channel = nil
            failWaiters(FleetError.closed)
            try? await Task.sleep(nanoseconds: delay * 1_000_000_000)
            delay = min(delay * 2, 60)
        }
    }

    func session() async throws {
        guard let key = try Keychain.read(account: home.keyAccount) else {
            throw FleetError.failed("not paired: run `ladder-fleet join <server> <code>`")
        }
        if AgentLink.load(home)?.state != .blocked { setLink(.connecting) }
        let stream = try await NWByteStream.connect(host: config.server, port: config.port) {
            Task { await self.blockedByLocalNetwork() }
        }
        let ch = try await SecureChannel.client(stream, name: info.name, mode: "fleet", psk: key)
        try await ch.send(.hello(info: info, policy: config.policy, version: fleetVersion))
        guard case .message(.welcome(let server, _, let imageId)) = try await ch.receive() else {
            throw FleetError.protocolError("no welcome")
        }
        channel = ch
        setLink(.connected, server)
        say("connected to \(server)")
        Task { await self.statusLoop(ch) }
        Task { await self.provision(imageId: imageId) }
        Task { await self.uploadPending() }
        let sinks = FileSinks()
        defer { sinks.failAll(FleetError.closed) }
        while true {
            switch try await ch.receive() {
            case .message(let m):
                switch m {
                case .assign(let batch):
                    if busyBatch != nil {
                        try? await ch.send(.batchFailed(batchId: batch.id, error: "busy with \(busyBatch!)"))
                    } else {
                        busyBatch = batch.id
                        Task { await self.play(batch) }
                    }
                case .artifact(let kind, let id, let file):
                    let url = home.dir("artifacts").appendingPathComponent("\(kind.rawValue)-\(id.replacingOccurrences(of: ":", with: "_"))")
                    try sinks.open(file, at: url) { result in Task { await self.arrived(kind, id, result) } }
                case .artifactError(let kind, let id, let error):
                    arrived(kind, id, .failure(FleetError.failed(error)))
                case .ack(let batchId):
                    try? FileManager.default.removeItem(at: home.dir("out").appendingPathComponent(batchId))
                case .update(let sum, let port):
                    pendingUpdate = (sum, port)
                    await updateIfDue()
                case .cancel(let batchId):
                    if batchId == busyBatch, let p = running {
                        log("batch \(batchId) cancelled")
                        _ = try? await Shell.run("pkill", ["-TERM", "-P", "\(p.processIdentifier)"])
                        p.terminate()
                    }
                default:
                    break
                }
            case .chunk(let id, let data, let last):
                _ = sinks.write(stream: id, data: data, last: last)
            case .unknown(let m):
                say("skipped a message from a newer server: \(m)")
            }
        }
    }

    // MARK: offers

    func currentStatus() async -> AgentStatus {
        let vitals = HostProbe.vitals(disk: home.root)
        let readiness = await prov.readiness
        // our own colima VM is sized to the offer; only someone else's Docker limits it
        let cpus = readiness.docker == "existing" ? readiness.dockerCPUs : nil
        let (workers, reason) = OfferPolicy.offer(info: info, vitals: vitals, policy: config.policy, dockerCPUs: cpus)
        let st: AgentState = busyBatch != nil ? .busy : state
        return AgentStatus(state: st, offer: workers, reason: reason, vitals: vitals, readiness: readiness,
                           busyBatch: busyBatch, note: note)
    }

    func sendStatus() async {
        guard let channel else { return }
        let st = await currentStatus()
        try? await channel.send(.status(st))
    }

    func statusLoop(_ ch: SecureChannel) async {
        var ticks = 0
        while channel === ch {
            await sendStatus()
            try? await Task.sleep(nanoseconds: 10_000_000_000)
            ticks += 1
            if state == .error && ticks % 30 == 0 { Task { await self.provision(imageId: provisionedImageHint) } }
        }
    }

    var provisionedImageHint: String?

    // MARK: provisioning

    func provision(imageId: String?) async {
        if let imageId { provisionedImageHint = imageId }
        guard !provisioning else { return }
        if let target = provisionedImageHint, provisioned == target {
            state = .ready
            await sendStatus()
            return
        }
        provisioning = true
        defer { provisioning = false }
        state = .provisioning
        note = nil
        await sendStatus()
        do {
            try await prov.ensureUV()
            let (workers, _) = OfferPolicy.offer(info: info, vitals: HostProbe.vitals(disk: home.root),
                                                 policy: AgentPolicy(maxWorkers: config.policy.maxWorkers,
                                                                     reserveCores: config.policy.reserveCores,
                                                                     allowOnBattery: true, gbPerWorker: config.policy.gbPerWorker,
                                                                     minFreeDiskGB: 0),
                                                 dockerCPUs: nil)
            let memory = min(max(2, Int(info.memoryGB / 2)), 2 + workers)
            try await prov.ensureDocker(cpus: max(2, workers), memoryGB: memory)
            guard let imageId = provisionedImageHint else {
                throw FleetError.failed("the server has no DCSS image (\(dcssImageTag)); build it there first")
            }
            try await prov.ensureImage(imageId) { try await self.fetch(.image, imageId) }
            provisioned = imageId
            state = .ready
            log("ready: \(await prov.readiness.uv ?? "uv"), docker \(await prov.readiness.docker ?? "?"), DCSS on \(agentDCSSPort)")
        } catch {
            state = .error
            note = "\(error)"
            log("provisioning failed: \(error)")
        }
        await sendStatus()
    }

    func fetch(_ kind: ArtifactKind, _ id: String) async throws -> URL {
        guard let channel else { throw FleetError.closed }
        let key = "\(kind.rawValue)-\(id)"
        return try await withCheckedThrowingContinuation { c in
            let first = waiters[key] == nil
            waiters[key, default: []].append(c)
            if first { Task { try? await channel.send(.need(kind: kind, id: id)) } }
        }
    }

    func arrived(_ kind: ArtifactKind, _ id: String, _ result: Result<URL, Error>) {
        for c in waiters.removeValue(forKey: "\(kind.rawValue)-\(id)") ?? [] { c.resume(with: result) }
    }

    func failWaiters(_ error: Error) {
        let all = waiters
        waiters = [:]
        for cs in all.values { for c in cs { c.resume(throwing: error) } }
    }

    // MARK: playing

    func play(_ batch: Batch) async {
        let dir = home.dir("out").appendingPathComponent(batch.id)
        sleepGuard.hold("ladder-fleet: playing DCSS batch \(batch.id)")
        defer { sleepGuard.release() }
        await sendStatus()
        do {
            if provisioned != batch.imageId {
                await provision(imageId: batch.imageId)
                guard provisioned == batch.imageId else { throw FleetError.failed("not provisioned: \(note ?? "?")") }
            }
            try await prov.ensureDCSS(batch.imageId)
            let checkout = try await prov.ensureBundle(batch.bundleId) { try await self.fetch(.bundle, batch.bundleId) }
            try FileManager.default.createDirectory(at: dir, withIntermediateDirectories: true)
            let brain = dir.appendingPathComponent("brain")
            let tag = "\(info.name)-b\(batch.id.split(separator: "-").last ?? "0")"
            let spec: JSONValue = .object([
                "name": .string(batch.runName), "jobs": .array(batch.jobs), "play": batch.play,
                "workers": .int(batch.workers), "server": .string("ws://localhost:\(agentDCSSPort)/socket"),
                "out": .string(brain.path), "tag": .string(tag),
            ])
            let specURL = dir.appendingPathComponent("spec.json")
            try spec.data(pretty: true).write(to: specURL)
            log("batch \(batch.id): \(batch.jobs.count) games of \(batch.runName) on \(batch.workers) workers")
            let started = Date()
            let ch = channel, lf = logFile, id = batch.id
            let r = try await Shell.run("uv", ["run", "--no-sync", "ladder", "brain", "fleet-shard", specURL.path], cwd: checkout,
                                        onLine: { line in
                                            lf?.write(Data((line + "\n").utf8))
                                            if ProgressLine.isGame(line), let ch { Task { try? await ch.send(.progress(batchId: id, line: line)) } }
                                        },
                                        started: { p in Task { await self.setRunning(p) } })
            running = nil
            let shard = brain.appendingPathComponent(batch.runName).appendingPathComponent("shard-\(tag).json")
            guard r.ok, FileManager.default.fileExists(atPath: shard.path) else {
                let tail = (r.err + r.out).split(separator: "\n").suffix(5).joined(separator: " | ")
                throw FleetError.failed("fleet-shard exited \(r.status): \(tail)")
            }
            let results = try JSONValue.parse(Data(contentsOf: shard))["results"]?.array ?? []
            let games = results.map { g in
                GameOutcome(game: g["game"]?.gameKey ?? "?", endedBy: g["ended_by"]?.string ?? "?",
                            played: g["max_depth"] != nil, maxDepth: g["max_depth"]?.int)
            }
            try await Shell.check("tar", ["-czf", dir.appendingPathComponent("results.tgz").path, "-C", brain.path, batch.runName])
            let done = DoneBatch(batchId: batch.id, runName: batch.runName, games: games,
                                 seconds: Int(Date().timeIntervalSince(started)))
            try home.save(done, "out/\(batch.id)/done.json")
            try? FileManager.default.removeItem(at: brain)
            await upload(done)
        } catch {
            running = nil
            log("batch \(batch.id) failed: \(error)")
            try? await channel?.send(.batchFailed(batchId: batch.id, error: "\(error)"))
            try? FileManager.default.removeItem(at: dir)
        }
        busyBatch = nil
        await sendStatus()
        await updateIfDue()
    }

    // MARK: updating

    var pendingUpdate: (sha256: String, port: UInt16)?

    /// An installed agent (the LaunchAgent's copy) replaces itself with the server's binary between
    /// batches and exits; launchd starts the new one. The download is plain HTTP, checked against the
    /// SHA-256 the server sent over the authenticated channel.
    func updateIfDue() async {
        guard let (sum, port) = pendingUpdate, busyBatch == nil else { return }
        let exe = Bundle.main.executableURL!.resolvingSymlinksInPath()
        let installed = home.bin.appendingPathComponent("ladder-fleet")
        guard (try? FleetCrypto.sha256Hex(file: exe)) != sum else { pendingUpdate = nil; return }
        guard exe.path == installed.path else {
            pendingUpdate = nil
            log("the server runs a different ladder-fleet; this one isn't the installed agent, so it carries on")
            return
        }
        do {
            let (tmp, resp) = try await URLSession.shared.download(from: URL(string: "http://\(config.server):\(port)/ladder-fleet")!)
            guard (resp as? HTTPURLResponse)?.statusCode == 200, try FleetCrypto.sha256Hex(file: tmp) == sum else {
                throw FleetError.failed("downloaded binary doesn't match the server's checksum")
            }
            try FileManager.default.setAttributes([.posixPermissions: 0o755], ofItemAtPath: tmp.path)
            _ = try FileManager.default.replaceItemAt(installed, withItemAt: tmp)
            log("updated ladder-fleet to the server's (\(sum.prefix(12))); restarting")
            try? await Task.sleep(nanoseconds: 500_000_000)
            exit(0)
        } catch {
            pendingUpdate = nil
            log("update failed: \(error)")
        }
    }

    func setRunning(_ p: Process) { running = p }

    /// Results go to the server once it's there; a batch finished while disconnected waits in out/.
    func upload(_ done: DoneBatch) async {
        guard let channel else { return }
        let file = home.dir("out").appendingPathComponent(done.batchId).appendingPathComponent("results.tgz")
        do {
            let size = (try FileManager.default.attributesOfItem(atPath: file.path)[.size] as? NSNumber)?.int64Value ?? 0
            let header = FileHeader(size: size, sha256: try FleetCrypto.sha256Hex(file: file), stream: nextStream)
            nextStream += 2
            try await channel.send(.batchDone(batchId: done.batchId, runName: done.runName, games: done.games,
                                              seconds: done.seconds, file: header))
            try await channel.sendFile(file, stream: header.stream)
        } catch {
            say("upload of \(done.batchId) failed (kept for later): \(error)")
        }
    }

    func uploadPending() async {
        let out = home.dir("out")
        for id in (try? FileManager.default.contentsOfDirectory(atPath: out.path)) ?? [] where id != busyBatch {
            if let done = home.load(DoneBatch.self, "out/\(id)/done.json") { await upload(done) }
            else { try? FileManager.default.removeItem(at: out.appendingPathComponent(id)) }   // never finished
        }
    }
}

struct DoneBatch: Codable {
    var batchId: String
    var runName: String
    var games: [GameOutcome]
    var seconds: Int
}

// MARK: - joining a fleet

enum Join {
    /// Pair with the server using its invite code, keep the fleet key in the Keychain, write agent.json.
    static func pair(home: FleetHome, server: String, port: UInt16, code: String, name: String?) async throws -> String {
        let info = HostProbe.info(name: name)
        let stream = try await NWByteStream.connect(host: server, port: port)
        let ch = try await SecureChannel.client(stream, name: info.name, mode: "pair", psk: FleetCrypto.pairingKey(code: code))
        try await ch.send(.hello(info: info, policy: AgentPolicy(), version: fleetVersion))
        let reply: Incoming
        do { reply = try await ch.receive() } catch { throw FleetError.failed("the server refused the code (or it expired): \(error)") }
        guard case .message(.welcome(let serverName, let key?, _)) = reply else { throw FleetError.protocolError("no fleet key in welcome") }
        ch.close()
        do {
            try Keychain.set(key, account: home.keyAccount)
        } catch is Keychain.Locked {
            // It locked itself between the check before pairing and now: ask again.
            try unlockKeychain(server: server)
            try Keychain.set(key, account: home.keyAccount)
        }
        var cfg = home.load(AgentConfig.self, "agent.json") ?? AgentConfig(server: server, port: port, name: name, policy: AgentPolicy())
        cfg.server = server
        cfg.port = port
        cfg.name = name ?? cfg.name
        try home.save(cfg, "agent.json")
        return serverName
    }

    /// The fleet key goes in the login keychain. Over SSH that keychain is usually locked and macOS can't
    /// show its unlock dialog, so explain why and ask for the login password here. Called before pairing,
    /// so saying no (or a wrong password) leaves the invite and the server untouched.
    static func unlockKeychain(server: String) throws {
        guard Keychain.isLocked() else { return }
        let user = NSUserName()
        print("""

        This Mac's login keychain is locked.
          ladder-fleet keeps the fleet key there: 32 random bytes shared with \(server), which let
          this Mac and the server recognise each other. It is the only thing it stores in the keychain.
          The keychain is locked because you're connected over SSH: macOS unlocks it when someone
          logs in on this Mac's screen, and it can't show its usual unlock dialog in this terminal.

        To unlock it, type the login password of '\(user)' on this Mac.
          - Nothing appears as you type (echo is off).
          - ladder-fleet hands it directly to macOS to unlock the login keychain, the same as
            `security unlock-keychain`. It isn't saved, logged, put on a command line, or sent
            anywhere; \(server) never sees it.
          - The keychain then locks again as it normally would (on sleep or after its idle timeout).
          - To skip this, press Return on an empty line. Then log in on this Mac's screen and run
            the same join command in Terminal there; nothing will have changed.

        """)
        let outcome = Keychain.unlockAtTerminal(prompt: "Login password for \(user): ") { left in
            print("That password didn't unlock the login keychain. Try again (\(left) left).")
        }
        switch outcome {
        case .unlocked:
            print("Login keychain unlocked.\n")
        case .declined:
            throw FleetError.failed("skipped: nothing was changed. Log in on this Mac's screen and run the join command in Terminal there")
        case .noTerminal:
            throw FleetError.failed("this Mac's login keychain is locked and there's no terminal to ask for its password on. "
                + "Connect with `ssh -t` (or run the command in Terminal on this Mac) and try again")
        case .wrongPassword:
            throw FleetError.failed("that password didn't unlock the login keychain, so nothing was changed. If you've changed "
                + "this Mac's login password recently, the keychain may still use the old one; log in on its screen "
                + "and run the join command in Terminal there")
        case .failed(let status):
            throw FleetError.failed("macOS couldn't unlock the login keychain (\(status)); nothing was changed. "
                + "Log in on this Mac's screen and run the join command in Terminal there")
        }
    }

    /// After installing the agent: wait for it to reach the server, and say what's going on if it can't.
    /// While macOS's Local Network privacy holds it back, wait (up to `blockedWait`) for someone to allow it.
    static func watch(home: FleetHome, server: String, since: Date, quickWait: Double = 20,
                      blockedWait: Double = 300) async {
        print("waiting for the agent to reach \(server)...")
        var told = false
        let start = Date()
        while true {
            let link = AgentLink.load(home).flatMap { $0.at >= since.addingTimeInterval(-1) ? $0 : nil }
            switch link?.state {
            case .connected:
                if told { print("allowed.") }
                print("""
                + the agent is connected to \(server). It now sets itself up (uv, Docker, the DCSS image), which
                  can take a few minutes the first time; `ladder-fleet hosts` on \(server) shows how far it's got,
                  and `ladder-fleet check` here shows this end.
                """)
                return
            case .blocked:
                if !told {
                    print("\n" + AgentLink.blockedHelp(server: server) + "\n")
                    print("waiting up to \(Int(blockedWait / 60)) minutes for that (Ctrl-C stops waiting here; the agent keeps waiting by itself)...")
                    told = true
                }
            default:
                break
            }
            let waited = Date().timeIntervalSince(start)
            if told, waited > blockedWait {
                print("still not allowed. Once it is, the agent connects by itself; `ladder-fleet check` shows where it is.")
                return
            }
            if !told, waited > quickWait {
                let now = link.map { "\($0.state.rawValue)\($0.detail.map { ": " + $0 } ?? "")" } ?? "no word from it"
                print("""
                the agent hasn't reached \(server) yet (\(now)).
                It keeps trying by itself; `ladder-fleet check` shows where it is and the end of its log.
                """)
                return
            }
            try? await Task.sleep(nanoseconds: 1_000_000_000)
        }
    }

    /// Find a fleet server on the local network by Bonjour.
    static func browse(seconds: Double = 4) async -> [String] {
        let browser = NWBrowser(for: .bonjour(type: fleetServiceType, domain: nil), using: .tcp)
        let found = FoundNames()
        browser.browseResultsChangedHandler = { results, _ in
            for r in results { if case .service(let name, _, _, _) = r.endpoint { found.add(name) } }
        }
        browser.start(queue: .global())
        try? await Task.sleep(nanoseconds: UInt64(seconds * 1e9))
        browser.cancel()
        return found.all
    }
}

final class FoundNames: @unchecked Sendable {
    private let lock = NSLock()
    private var names: Set<String> = []
    func add(_ n: String) { lock.lock(); names.insert(n); lock.unlock() }
    var all: [String] { lock.lock(); defer { lock.unlock() }; return names.sorted() }
}

// MARK: - LaunchAgent

enum LaunchAgent {
    static let label = "com.dcss-ladder.fleet-agent"
    static let serverLabel = "com.dcss-ladder.fleet-server"

    static func plist(_ label: String) -> URL {
        FileManager.default.homeDirectoryForCurrentUser.appendingPathComponent("Library/LaunchAgents/\(label).plist")
    }

    /// Copy this binary into the fleet home and have launchd keep `ladder-fleet <arguments>` running.
    static func install(home: FleetHome, label: String = label, arguments: [String] = ["agent"],
                        log: String = "agent.log", workingDirectory: String? = nil) async throws -> URL {
        let exe = Bundle.main.executableURL!.resolvingSymlinksInPath()
        let dst = home.bin.appendingPathComponent("ladder-fleet")
        if exe.path != dst.path {
            try? FileManager.default.removeItem(at: dst)
            try FileManager.default.copyItem(at: exe, to: dst)
        }
        var dict: [String: Any] = [
            "Label": label,
            "ProgramArguments": [dst.path] + arguments,
            "RunAtLoad": true,
            "KeepAlive": true,
            "ProcessType": "Background",
            "StandardOutPath": home.logs.appendingPathComponent(log).path,
            "StandardErrorPath": home.logs.appendingPathComponent(log).path,
            "EnvironmentVariables": ["PATH": "\(home.bin.path):/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin"],
        ]
        if let workingDirectory { dict["WorkingDirectory"] = workingDirectory }
        let url = plist(label)
        try FileManager.default.createDirectory(at: url.deletingLastPathComponent(), withIntermediateDirectories: true)
        try PropertyListSerialization.data(fromPropertyList: dict, format: .xml, options: 0).write(to: url)
        let domain = "gui/\(getuid())"
        _ = try? await Shell.run("launchctl", ["bootout", "\(domain)/\(label)"])
        var r = try await Shell.run("launchctl", ["bootstrap", domain, url.path])
        for _ in 0..<5 where r.status == 5 {
            // error 5 (EIO) here usually means the old job is still on its way out: give it a moment
            try? await Task.sleep(nanoseconds: 1_000_000_000)
            r = try await Shell.run("launchctl", ["bootstrap", domain, url.path])
        }
        if !r.ok {
            // No GUI session for this user: nobody is logged in on the screen (typical over SSH to a
            // headless Mac). A LaunchAgent needs one, and so does the unlocked login keychain.
            let hasSession = (try? await Shell.run("launchctl", ["print", domain]))?.ok ?? false
            let why = (r.err.isEmpty ? r.out : r.err).trimmingCharacters(in: .whitespacesAndNewlines)
            throw FleetError.failed(hasSession
                ? "launchctl bootstrap \(domain) failed (\(r.status)): \(why)"
                : "nobody is logged in on this Mac's screen, so there is no session to run the agent in. "
                    + "Log in on it (or turn on automatic login), then run `\(dst.path) install`")
        }
        return dst
    }

    static func uninstall(_ label: String = label) async {
        _ = try? await Shell.run("launchctl", ["bootout", "gui/\(getuid())/\(label)"])
        try? FileManager.default.removeItem(at: plist(label))
    }
}
