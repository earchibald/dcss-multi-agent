import Foundation

/// One named run (what `ladder brain fleet-jobs` returned for one name) and where its jobs are.
public struct FleetRun: Codable, Sendable {
    public var id: String
    public var name: String
    public var play: JSONValue
    public var jobs: [JSONValue]
    public var bundleId: String
    public var imageId: String
    public var hosts: [String]?
    public var maxPerHost: Int?
    public var gamesPerWorker: Int
    public var createdAt: Date
    public var finishedAt: Date?
    public var cancelled = false

    public var pending: [Int]                  // job indexes, in the order they go out
    public var inFlight: [String: [Int]] = [:] // batch id -> job indexes
    public var done: Set<Int> = []
    public var lost: Set<Int> = []
    public var attempts: [Int: Int] = [:]
    public var byHost: [String: Int] = [:]     // games played to the end, per host
    public var summary: JSONValue?             // the last `fleet-merge` output
    public var note: String?

    public init(id: String, name: String, play: JSONValue, jobs: [JSONValue], bundleId: String, imageId: String,
                hosts: [String]? = nil, maxPerHost: Int? = nil, gamesPerWorker: Int = 3, createdAt: Date = Date()) {
        self.id = id; self.name = name; self.play = play; self.jobs = jobs; self.bundleId = bundleId
        self.imageId = imageId; self.hosts = hosts; self.maxPerHost = maxPerHost
        self.gamesPerWorker = max(1, gamesPerWorker); self.createdAt = createdAt
        pending = Array(jobs.indices)
    }

    public var finished: Bool { cancelled || (pending.isEmpty && inFlight.isEmpty) }

    public func row() -> RunRow {
        RunRow(id: id, name: name, total: jobs.count, done: done.count, lost: lost.count,
               inFlight: inFlight.values.reduce(0) { $0 + $1.count }, pending: pending.count, byHost: byHost,
               startedAt: createdAt, finishedAt: finishedAt, cancelled: cancelled, summary: summary, note: note)
    }
}

/// Hands out batches by each agent's offer. Games that weren't played go back in the queue (once,
/// by default); a host that drops out loses its batches back to the queue.
public struct Scheduler: Codable, Sendable {
    public var runs: [FleetRun] = []
    public var owner: [String: String] = [:]   // batch id -> agent
    public var maxAttempts = 2
    private var nextBatch = 1

    public init() {}

    public mutating func add(_ run: FleetRun) { runs.append(run) }

    public func run(_ id: String) -> FleetRun? { runs.first { $0.id == id } }

    /// The next batch for `agent`, which offers `offer` games at once, or nil if there's nothing for it.
    public mutating func assign(agent: String, offer: Int, now: Date = Date()) -> Batch? {
        guard offer > 0 else { return nil }
        guard let i = runs.firstIndex(where: { !$0.finished && !$0.pending.isEmpty && ($0.hosts?.contains(agent) ?? true) })
        else { return nil }
        var run = runs[i]
        let workers = min(offer, run.maxPerHost ?? offer)
        let take = min(run.pending.count, workers * run.gamesPerWorker)
        let picked = Array(run.pending.prefix(take))
        run.pending.removeFirst(take)
        let id = "\(run.id)-\(nextBatch)"
        nextBatch += 1
        run.inFlight[id] = picked
        runs[i] = run
        owner[id] = agent
        return Batch(id: id, runId: run.id, runName: run.name, play: run.play, jobs: picked.map { run.jobs[$0] },
                     workers: min(workers, picked.count), bundleId: run.bundleId, imageId: run.imageId)
    }

    /// A batch came back. Returns the run's index, or nil if the batch is unknown (already given up on).
    @discardableResult
    public mutating func complete(batch id: String, outcomes: [GameOutcome], agent: String, now: Date = Date()) -> Int? {
        guard let i = runs.firstIndex(where: { $0.inFlight[id] != nil }), let picked = runs[i].inFlight[id] else {
            owner[id] = nil
            return lateResults(outcomes, agent: agent)
        }
        var run = runs[i]
        run.inFlight[id] = nil
        owner[id] = nil
        let played = Dictionary(outcomes.map { ($0.game, $0.played) }, uniquingKeysWith: { $0 || $1 })
        for j in picked {
            if played[run.jobs[j].gameKey] == true {
                run.done.insert(j)
                run.byHost[agent, default: 0] += 1
            } else {
                retryOrLose(&run, j)
            }
        }
        finishIfDone(&run, now)
        runs[i] = run
        return i
    }

    /// Results for a batch already put back in the queue (its host dropped out, then came back): the
    /// games it did play count, and come out of the queue.
    private mutating func lateResults(_ outcomes: [GameOutcome], agent: String) -> Int? {
        for o in outcomes where o.played {
            for i in runs.indices {
                guard let j = runs[i].jobs.firstIndex(where: { $0.gameKey == o.game }), !runs[i].done.contains(j) else { continue }
                if let p = runs[i].pending.firstIndex(of: j) {
                    runs[i].pending.remove(at: p)
                    runs[i].done.insert(j)
                    runs[i].lost.remove(j)
                    runs[i].byHost[agent, default: 0] += 1
                    var run = runs[i]
                    finishIfDone(&run, Date())
                    runs[i] = run
                    return i
                }
            }
        }
        return nil
    }

    public mutating func fail(batch id: String, now: Date = Date()) {
        owner[id] = nil
        guard let i = runs.firstIndex(where: { $0.inFlight[id] != nil }), let picked = runs[i].inFlight[id] else { return }
        var run = runs[i]
        run.inFlight[id] = nil
        // a batch that failed as a whole (a host problem) doesn't use up the games' attempts
        run.pending.insert(contentsOf: picked, at: 0)
        finishIfDone(&run, now)
        runs[i] = run
    }

    /// Everything `agent` had out goes back in the queue.
    public mutating func agentLost(_ agent: String) -> [String] {
        let batches = owner.filter { $0.value == agent }.map(\.key)
        for b in batches { fail(batch: b) }
        return batches
    }

    public mutating func cancel(run id: String, now: Date = Date()) -> [String] {
        guard let i = runs.firstIndex(where: { $0.id == id }) else { return [] }
        let batches = Array(runs[i].inFlight.keys)
        runs[i].cancelled = true
        runs[i].pending = []
        runs[i].inFlight = [:]
        runs[i].finishedAt = now
        for b in batches { owner[b] = nil }
        return batches
    }

    /// After a restart nothing is in flight: whatever was goes back in the queue.
    public mutating func requeueInFlight() {
        for i in runs.indices {
            for (_, picked) in runs[i].inFlight { runs[i].pending.insert(contentsOf: picked, at: 0) }
            runs[i].inFlight = [:]
        }
        owner = [:]
    }

    private mutating func retryOrLose(_ run: inout FleetRun, _ j: Int) {
        run.attempts[j, default: 0] += 1
        if run.attempts[j, default: 0] < maxAttempts { run.pending.append(j) } else { run.lost.insert(j) }
    }

    private func finishIfDone(_ run: inout FleetRun, _ now: Date) {
        if run.pending.isEmpty && run.inFlight.isEmpty && run.finishedAt == nil { run.finishedAt = now }
    }
}

/// How many games a host offers to play at once, and why.
public enum OfferPolicy {
    public static func offer(info: HostInfo, vitals: Vitals, policy: AgentPolicy, dockerCPUs: Int?) -> (workers: Int, reason: String) {
        if !vitals.onAC && !policy.allowOnBattery { return (0, "on battery") }
        if vitals.thermal == "critical" { return (0, "too hot") }
        if let m = policy.idleOnlyMinutes, vitals.idleSeconds < Double(m * 60) {
            return (0, "in use (idle \(Int(vitals.idleSeconds))s of \(m * 60)s)")
        }
        if vitals.freeDiskGB < policy.minFreeDiskGB { return (0, "disk nearly full (\(Int(vitals.freeDiskGB)) GB free)") }
        var n = info.perfCores + info.effCores / 2 - policy.reserveCores
        var reason = "\(info.perfCores)P+\(info.effCores)E cores, \(policy.reserveCores) kept back"
        let byMemory = Int((info.memoryGB - 4) / max(policy.gbPerWorker, 0.25))
        if byMemory < n { n = byMemory; reason = "\(Int(info.memoryGB)) GB memory" }
        if let d = dockerCPUs, 2 * d < n { n = 2 * d; reason = "docker has \(d) CPUs" }
        if let m = policy.maxWorkers, m < n { n = m; reason = "owner's limit" }
        if vitals.thermal == "serious" { n /= 2; reason = "running hot" }
        return (max(n, 0), reason)
    }
}

/// selfplay prints one line per finished game: "  [3/12] seed 42: died  reached 5 ...".
public enum ProgressLine {
    public static func isGame(_ line: String) -> Bool {
        let t = line.trimmingCharacters(in: .whitespaces)
        return t.hasPrefix("[") && t.contains("/") && t.contains("] seed ")
    }
}
