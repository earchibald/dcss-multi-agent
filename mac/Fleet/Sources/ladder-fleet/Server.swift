import FleetCore
import Foundation
import Network

func stamp() -> String {
    let f = DateFormatter()
    f.dateFormat = "HH:mm:ss"
    return f.string(from: Date())
}

func say(_ s: String) {
    print("\(stamp()) \(s)")
    fflush(stdout)
}

struct ServerConfig {
    var name: String
    var repo: URL               // the checkout whose code run hosts play, and whose uv runs fleet-jobs/merge
    var out: URL                // where games land (runs/brain)
    var port: UInt16
    var downloadPort: UInt16
}

/// A run host the server has paired with. Kept in agents.json.
struct KnownAgent: Codable {
    var name: String
    var info: HostInfo?
    var pairedAt: Date
    var lastSeen: Date?
    var batches = 0
    var games = 0
}

final class AgentSession: @unchecked Sendable {
    let name: String
    let channel: SecureChannel
    var info: HostInfo
    var policy: AgentPolicy
    var status: AgentStatus?
    var lastSeen = Date()

    init(name: String, channel: SecureChannel, info: HostInfo, policy: AgentPolicy) {
        self.name = name; self.channel = channel; self.info = info; self.policy = policy
    }
}

actor FleetServer {
    let cfg: ServerConfig
    let home: FleetHome
    let fleetKey: Data
    var scheduler: Scheduler
    var known: [String: KnownAgent]
    var sessions: [String: AgentSession] = [:]
    var invite: (code: String, expires: Date, failures: Int)?
    var progress: [String: Int] = [:]               // batch id -> games finished so far
    var nextStream: UInt32 = 1                       // odd: the server's streams
    var artifactTasks: [String: Task<URL, Error>] = [:]
    var merging: Set<String> = []
    var mergeAgain: Set<String> = []
    var imageId: String?
    var listeners: [NWListener] = []

    init(cfg: ServerConfig, home: FleetHome) throws {
        self.cfg = cfg
        self.home = home
        if let k = Keychain.get(account: home.keyAccount) {
            fleetKey = k
        } else {
            fleetKey = FleetCrypto.newFleetKey()
            try Keychain.set(fleetKey, account: home.keyAccount)
        }
        var s = home.load(Scheduler.self, "scheduler.json") ?? Scheduler()
        s.requeueInFlight()
        scheduler = s
        known = home.load([String: KnownAgent].self, "agents.json") ?? [:]
    }

    // MARK: start

    func start() async throws {
        imageId = try? await currentImageId()
        let fleet = try NWListener(using: .tcp, on: NWEndpoint.Port(rawValue: cfg.port)!)
        fleet.service = NWListener.Service(name: cfg.name, type: fleetServiceType)
        fleet.newConnectionHandler = { conn in Task { await self.acceptAgent(conn) } }
        fleet.stateUpdateHandler = { state in
            if case .failed(let e) = state { say("fleet listener failed: \(e)"); exit(1) }
        }
        fleet.start(queue: .global())

        try? FileManager.default.removeItem(atPath: home.controlSocket)
        let cp = NWParameters.tcp
        cp.requiredLocalEndpoint = .unix(path: home.controlSocket)
        let control = try NWListener(using: cp)
        control.newConnectionHandler = { conn in Task { await self.acceptControl(conn) } }
        control.start(queue: .global())

        let http = try NWListener(using: .tcp, on: NWEndpoint.Port(rawValue: cfg.downloadPort)!)
        http.newConnectionHandler = { conn in BinaryDownload.serve(conn) }
        http.start(queue: .global())
        listeners = [fleet, control, http]

        say("✦ fleet server \(cfg.name) on port \(cfg.port) (Bonjour \(fleetServiceType)), binary on \(cfg.downloadPort)")
        say("  code from \(cfg.repo.path), games into \(cfg.out.path)")
        say("  image \(imageId ?? "not found: run `docker compose build` in the repo")")
        if known.isEmpty { say("  no run hosts yet: `ladder-fleet invite` prints the command to run on each") }
        let open = scheduler.runs.filter { !$0.finished }
        if !open.isEmpty { say("  resuming \(open.count) run(s): \(open.map(\.name).joined(separator: ", "))") }
        Task { await self.tickForever() }
    }

    func tickForever() async {
        while true {
            try? await Task.sleep(nanoseconds: 2_000_000_000)
            tick()
        }
    }

    /// Hand out work, and give up on hosts that went quiet.
    func tick() {
        for (name, s) in sessions where Date().timeIntervalSince(s.lastSeen) > 90 {
            say("\(name): no word for 90 s, dropping it")
            s.channel.close()
            dropped(s)
        }
        for (name, s) in sessions.sorted(by: { $0.key < $1.key }) {
            guard let st = s.status, st.state == .ready, st.offer > 0,
                  !scheduler.owner.values.contains(name) else { continue }
            guard let batch = scheduler.assign(agent: name, offer: st.offer) else { continue }
            progress[batch.id] = 0
            say("\(name): batch \(batch.id) of \(batch.runName), \(batch.jobs.count) games on \(batch.workers) workers")
            persist()
            Task {
                do { try await s.channel.send(.assign(batch)) }
                catch { await self.batchFailed(batch.id, agent: name, error: "send failed: \(error)") }
            }
        }
    }

    func persist() {
        try? home.save(scheduler, "scheduler.json")
        try? home.save(known, "agents.json")
    }

    // MARK: agents

    func psk(mode: String, client: String) -> Data? {
        switch mode {
        case "fleet":
            return fleetKey
        case "pair":
            guard let inv = invite, inv.expires > Date() else { return nil }
            return FleetCrypto.pairingKey(code: inv.code)
        default:
            return nil
        }
    }

    func authFailed(mode: String, from: String) {
        say("refused \(from): \(mode == "pair" ? "wrong invite code" : "wrong fleet key")")
        guard mode == "pair", var inv = invite else { return }
        inv.failures += 1
        invite = inv.failures >= 5 ? nil : inv
        if invite == nil { say("  invite closed after 5 wrong codes") }
    }

    nonisolated func acceptAgent(_ conn: NWConnection) async {
        let stream = NWByteStream(conn)
        do { try await stream.start() } catch { return }
        let from = stream.remote
        let channel: SecureChannel, mode: String
        do {
            (channel, mode) = try await SecureChannel.server(stream, name: cfg.name) { mode, client in
                await self.psk(mode: mode, client: client)
            }
        } catch {
            say("handshake with \(from) failed: \(error)")
            stream.close()
            return
        }
        let first: Incoming
        do { first = try await channel.receive() } catch {
            await authFailed(mode: mode, from: "\(channel.peer) at \(from)")
            channel.close()
            return
        }
        guard case .message(.hello(let info, let policy, _)) = first else { channel.close(); return }
        if mode == "pair" {
            await paired(info)
            try? await channel.send(.welcome(server: cfg.name, fleetKey: fleetKey, imageId: nil))
            try? await Task.sleep(nanoseconds: 500_000_000)
            channel.close()
            return
        }
        guard let session = await connected(info: info, policy: policy, channel: channel) else { channel.close(); return }
        try? await channel.send(.welcome(server: cfg.name, fleetKey: nil, imageId: await imageId))
        if let sum = try? FleetCrypto.sha256Hex(file: Bundle.main.executableURL!) {
            try? await channel.send(.update(sha256: sum, downloadPort: cfg.downloadPort))
        }
        let sinks = FileSinks()
        do {
            while true {
                switch try await channel.receive() {
                case .message(let m): await handle(m, from: session, sinks: sinks)
                case .chunk(let id, let data, let last):
                    if !sinks.write(stream: id, data: data, last: last) { say("\(session.name): data for unknown stream \(id)") }
                case .unknown(let m): say("\(session.name) sent a message this server doesn't know: \(m)")
                }
            }
        } catch {
            say("\(session.name) disconnected: \(error)")
        }
        sinks.failAll(FleetError.closed)
        await dropped(session)
    }

    func paired(_ info: HostInfo) {
        known[info.name] = KnownAgent(name: info.name, info: info, pairedAt: Date())
        persist()
        say("+ paired with \(info.name): \(info.chip), \(info.perfCores)P+\(info.effCores)E, \(Int(info.memoryGB)) GB")
    }

    func connected(info: HostInfo, policy: AgentPolicy, channel: SecureChannel) -> AgentSession? {
        guard known[info.name] != nil else {
            say("refused \(info.name): not paired here (or forgotten); run `ladder-fleet invite`")
            return nil
        }
        if let old = sessions[info.name] { old.channel.close() }
        let s = AgentSession(name: info.name, channel: channel, info: info, policy: policy)
        sessions[info.name] = s
        known[info.name]?.info = info
        known[info.name]?.lastSeen = Date()
        persist()
        say("\(info.name) connected (\(info.chip), \(info.perfCores)P+\(info.effCores)E, \(Int(info.memoryGB)) GB)")
        return s
    }

    func dropped(_ s: AgentSession) {
        guard sessions[s.name] === s else { return }       // a newer connection replaced it
        sessions[s.name] = nil
        let lost = scheduler.agentLost(s.name)
        if !lost.isEmpty { say("  \(s.name)'s batches \(lost.joined(separator: ", ")) go back in the queue") }
        persist()
    }

    func handle(_ m: Message, from s: AgentSession, sinks: FileSinks) {
        s.lastSeen = Date()
        known[s.name]?.lastSeen = s.lastSeen
        switch m {
        case .status(let st):
            let before = s.status
            s.status = st
            if before?.state != st.state || before?.offer != st.offer || before?.note != st.note {
                say("\(s.name): \(st.state.rawValue), offers \(st.offer) (\(st.reason))" + (st.note.map { " - \($0)" } ?? ""))
            }
            tick()
        case .need(let kind, let id):
            Task { await self.sendArtifact(kind, id, to: s) }
        case .progress(let batchId, let line):
            if ProgressLine.isGame(line) { progress[batchId, default: 0] += 1 }
        case .batchDone(let batchId, let runName, let games, let seconds, let file):
            let url = home.dir("incoming").appendingPathComponent("\(batchId).tgz")
            do {
                try sinks.open(file, at: url) { result in
                    Task { await self.ingest(batchId, runName: runName, games: games, seconds: seconds, from: s, file: result) }
                }
            } catch {
                say("\(s.name): can't take batch \(batchId)'s results: \(error)")
            }
        case .batchFailed(let batchId, let error):
            batchFailed(batchId, agent: s.name, error: error)
        case .log(let line):
            say("  \(s.name)| \(line)")
        default:
            break
        }
    }

    func batchFailed(_ batchId: String, agent: String, error: String) {
        say("\(agent): batch \(batchId) failed: \(error)")
        scheduler.fail(batch: batchId)
        progress[batchId] = nil
        persist()
    }

    func ingest(_ batchId: String, runName: String, games: [GameOutcome], seconds: Int, from s: AgentSession,
                file: Result<URL, Error>) async {
        guard case .success(let url) = file else {
            if case .failure(let e) = file { say("\(s.name): batch \(batchId)'s results didn't arrive: \(e)") }
            return
        }
        do {
            try FileManager.default.createDirectory(at: cfg.out, withIntermediateDirectories: true)
            try await Shell.check("tar", ["-xzf", url.path, "-C", cfg.out.path])
            try? FileManager.default.removeItem(at: url)
        } catch {
            say("\(s.name): batch \(batchId)'s results didn't unpack: \(error)")
            batchFailed(batchId, agent: s.name, error: "results didn't unpack")
            return
        }
        try? await s.channel.send(.ack(batchId: batchId))
        let played = games.filter(\.played).count
        known[s.name]?.batches += 1
        known[s.name]?.games += played
        let idx = scheduler.complete(batch: batchId, outcomes: games, agent: s.name)
        progress[batchId] = nil
        persist()
        let depths = games.compactMap(\.maxDepth)
        let mean = depths.isEmpty ? "-" : String(format: "%.2f", Double(depths.reduce(0, +)) / Double(depths.count))
        say("\(s.name): batch \(batchId) back, \(played)/\(games.count) played in \(seconds) s, mean depth \(mean)")
        if let idx { await merge(scheduler.runs[idx].id) }
    }

    /// `ladder brain fleet-merge`, one at a time per run, once more if batches came in meanwhile.
    func merge(_ runId: String) async {
        guard let run = scheduler.run(runId) else { return }
        if merging.contains(run.name) { mergeAgain.insert(run.name); return }
        merging.insert(run.name)
        defer { merging.remove(run.name) }
        repeat {
            mergeAgain.remove(run.name)
            do {
                let out = try await Shell.check("uv", ["run", "--quiet", "ladder", "brain", "fleet-merge", run.name,
                                                       "--out", cfg.out.path], cwd: cfg.repo)
                if let i = scheduler.runs.firstIndex(where: { $0.id == runId }) {
                    scheduler.runs[i].summary = try? JSONValue.parse(Data(out.utf8))
                    persist()
                }
            } catch {
                say("merging \(run.name) failed: \(error)")
            }
        } while mergeAgain.contains(run.name)
        if let r = scheduler.run(runId), r.finished, let s = r.summary {
            say("✦ \(r.name) finished: \(s["games"]?.int ?? 0) games, mean depth \(s["mean_depth"]?.double ?? 0), "
                + "died \(s["died"]?.int ?? 0), lost \(r.lost.count), by host \(r.byHost)")
        }
    }

    // MARK: artifacts

    func allocStream() -> UInt32 {
        defer { nextStream += 2 }
        return nextStream
    }

    func sendArtifact(_ kind: ArtifactKind, _ id: String, to s: AgentSession) async {
        do {
            let url = try await artifact(kind, id)
            let size = (try FileManager.default.attributesOfItem(atPath: url.path)[.size] as? NSNumber)?.int64Value ?? 0
            let header = FileHeader(size: size, sha256: try FleetCrypto.sha256Hex(file: url), stream: allocStream())
            say("\(s.name): sending \(kind.rawValue) \(id.prefix(19)) (\(size / 1_000_000) MB)")
            try await s.channel.send(.artifact(kind: kind, id: id, file: header))
            try await s.channel.sendFile(url, stream: header.stream)
        } catch {
            say("\(s.name): can't send \(kind.rawValue) \(id): \(error)")
            try? await s.channel.send(.artifactError(kind: kind, id: id, error: "\(error)"))
        }
    }

    func artifact(_ kind: ArtifactKind, _ id: String) async throws -> URL {
        let key = "\(kind.rawValue)-\(id)"
        if let t = artifactTasks[key] { return try await t.value }
        let t = Task { () throws -> URL in
            switch kind {
            case .bundle:
                let url = home.dir("bundles").appendingPathComponent("\(id).tgz")
                guard FileManager.default.fileExists(atPath: url.path) else { throw FleetError.failed("no bundle \(id)") }
                return url
            case .image:
                let url = home.dir("images").appendingPathComponent("\(id.replacingOccurrences(of: "sha256:", with: "")).tar.gz")
                if FileManager.default.fileExists(atPath: url.path) { return url }
                guard try await currentImageId() == id else { throw FleetError.failed("this server no longer has image \(id)") }
                say("exporting \(dcssImageTag) for run hosts (once)")
                let part = url.appendingPathExtension("part")
                try await Shell.sh(#"docker save "$1" | gzip -1 > "$2""#, [dcssImageTag, part.path])
                try FileManager.default.moveItem(at: part, to: url)
                return url
            }
        }
        artifactTasks[key] = t
        do { return try await t.value } catch { artifactTasks[key] = nil; throw error }
    }

    func currentImageId() async throws -> String {
        try await Shell.check("docker", ["image", "inspect", dcssImageTag, "--format", "{{.Id}}"])
    }

    /// A snapshot of the repo's code (tracked and new files, not ignored ones), so every host of a run
    /// plays the same code, committed or not.
    func makeBundle() async throws -> String {
        let listed = try await Shell.check("git", ["ls-files", "-co", "--exclude-standard", "-z"], cwd: cfg.repo)
        let skip = ["mac/", "runs/", ".claude/"]
        let files = listed.split(separator: "\0").map(String.init).filter { f in
            !skip.contains(where: f.hasPrefix) && FileManager.default.fileExists(atPath: cfg.repo.appendingPathComponent(f).path)
        }
        // named by content (paths and bytes), so unchanged code is the same bundle and hosts keep their checkout
        var digest = ""
        for f in files.sorted() {
            digest += f + "\0" + (try FleetCrypto.sha256Hex(file: cfg.repo.appendingPathComponent(f))) + "\n"
        }
        let id = String(FleetCrypto.sha256Hex(Data(digest.utf8)).prefix(16))
        let url = home.dir("bundles").appendingPathComponent("\(id).tgz")
        if FileManager.default.fileExists(atPath: url.path) { return id }
        let list = home.dir("bundles").appendingPathComponent("files.txt")
        try Data(files.joined(separator: "\0").utf8).write(to: list)
        let tmp = home.dir("bundles").appendingPathComponent("new.tgz")
        try await Shell.check("tar", ["-czf", tmp.path, "-C", cfg.repo.path, "--null", "-T", list.path])
        try FileManager.default.moveItem(at: tmp, to: url)
        return id
    }

    // MARK: control

    nonisolated func acceptControl(_ conn: NWConnection) async {
        let stream = NWByteStream(conn)
        do {
            try await stream.start()
            let frames = Frames(stream)
            let req = try JSONDecoder().decode(ControlRequest.self, from: try await frames.receive())
            let resp = await control(req)
            let enc = JSONEncoder()
            enc.dateEncodingStrategy = .iso8601
            try await frames.send(try enc.encode(resp))
        } catch {
            say("control: \(error)")
        }
        stream.close()
    }

    func control(_ req: ControlRequest) async -> ControlResponse {
        switch req {
        case .hosts:
            return .hosts(hostRows())
        case .runs:
            return .runs(scheduler.runs.suffix(20).map { $0.row() })
        case .run(let r):
            do { return .runs(try await startRun(r)) } catch { return .error("\(error)") }
        case .cancel(let id):
            guard scheduler.run(id) != nil else { return .error("no run \(id)") }
            let owners = scheduler.owner
            for b in scheduler.cancel(run: id) {
                if let agent = owners[b], let s = sessions[agent] {
                    Task { try? await s.channel.send(.cancel(batchId: b)) }
                }
                progress[b] = nil
            }
            persist()
            return .ok("cancelled \(id)")
        case .invite(let minutes):
            let code = FleetCrypto.newInviteCode()
            invite = (code, Date().addingTimeInterval(Double(minutes * 60)), 0)
            let exe = Bundle.main.executableURL!
            let sum = (try? FleetCrypto.sha256Hex(file: exe)) ?? "?"
            let host = "\(cfg.name).local"
            let cmd = "curl -fsSo ~/ladder-fleet http://\(host):\(cfg.downloadPort)/ladder-fleet && chmod +x ~/ladder-fleet"
                + " && ~/ladder-fleet join \(host) \(code)" + (cfg.port == defaultFleetPort ? "" : " --port \(cfg.port)")
            say("+ invite open for \(minutes) min")
            return .invite(Invite(code: code, expires: invite!.expires, command: cmd, sha256: sum))
        case .forget(let agent):
            guard known.removeValue(forKey: agent) != nil else { return .error("no host \(agent)") }
            sessions[agent]?.channel.close()
            persist()
            return .ok("forgot \(agent); it can't connect until it joins again")
        }
    }

    func hostRows() -> [HostRow] {
        known.values.sorted { $0.name < $1.name }.map { k in
            let s = sessions[k.name]
            var current: String?
            if let b = scheduler.owner.first(where: { $0.value == k.name })?.key,
               let run = scheduler.runs.first(where: { $0.inFlight[b] != nil }) {
                current = "\(run.name) batch \(b): \(progress[b] ?? 0)/\(run.inFlight[b]?.count ?? 0)"
            }
            return HostRow(name: k.name, connected: s != nil, info: s?.info ?? k.info, status: s?.status,
                           lastSeen: s?.lastSeen ?? k.lastSeen, batches: k.batches, games: k.games, current: current)
        }
    }

    func startRun(_ r: RunRequest) async throws -> [RunRow] {
        let spec = home.dir("specs").appendingPathComponent("request-\(UUID().uuidString.prefix(8)).json")
        try r.request.data().write(to: spec)
        defer { try? FileManager.default.removeItem(at: spec) }
        let out = try await Shell.check("uv", ["run", "--quiet", "ladder", "brain", "fleet-jobs", spec.path,
                                               "--out", cfg.out.path], cwd: cfg.repo)
        guard let runs = try JSONValue.parse(Data(out.utf8))["runs"]?.array else { throw FleetError.failed("fleet-jobs said: \(out)") }
        let image = try await currentImageId()
        imageId = image
        let bundle = try await makeBundle()
        var rows: [RunRow] = []
        let base = String(Int(Date().timeIntervalSince1970) % 1_000_000, radix: 36)
        for (i, r2) in runs.enumerated() {
            let name = r2["name"]?.string ?? "run"
            let jobs = r2["jobs"]?.array ?? []
            var run = FleetRun(id: "\(base)\(runs.count > 1 ? "\(i)" : "")", name: name, play: r2["play"] ?? .object([:]),
                               jobs: jobs, bundleId: bundle, imageId: image, hosts: r.hosts, maxPerHost: r.maxPerHost,
                               gamesPerWorker: r.gamesPerWorker)
            if let already = r2["already"]?.int, already > 0 { run.note = "\(already) games already played" }
            if jobs.isEmpty {
                run.finishedAt = Date()
                run.note = "nothing to play" + (run.note.map { ": \($0)" } ?? "")
            }
            scheduler.add(run)
            rows.append(run.row())
            say("✦ run \(run.id): \(name), \(jobs.count) games, code \(bundle)" + (run.note.map { " (\($0))" } ?? ""))
        }
        persist()
        tick()
        return rows
    }
}

/// Serves this binary over plain HTTP so a new run host can fetch it with curl. The invite prints its
/// SHA-256; the pairing that follows is what's authenticated.
enum BinaryDownload {
    static func serve(_ conn: NWConnection) {
        conn.start(queue: .global())
        conn.receive(minimumIncompleteLength: 1, maximumLength: 8192) { data, _, _, _ in
            let request = String(decoding: data ?? Data(), as: UTF8.self)
            let ok = request.hasPrefix("GET /ladder-fleet ")
            let body = ok ? ((try? Data(contentsOf: Bundle.main.executableURL!)) ?? Data()) : Data("not found\n".utf8)
            var head = "HTTP/1.1 \(ok ? "200 OK" : "404 Not Found")\r\nContent-Length: \(body.count)\r\n"
            head += "Content-Type: application/octet-stream\r\nConnection: close\r\n\r\n"
            conn.send(content: Data(head.utf8) + body, completion: .contentProcessed { _ in conn.cancel() })
        }
    }
}
