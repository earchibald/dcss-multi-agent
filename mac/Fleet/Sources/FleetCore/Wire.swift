import Foundation

public let fleetVersion = "1"
public let fleetServiceType = "_ladderfleet._tcp"
public let defaultFleetPort: UInt16 = 8091      // the cockpit is 8090
public let defaultDownloadPort: UInt16 = 8092   // plain HTTP: the binary, for a new run host
public let agentDCSSPort = 8180                 // a run host's own DCSS server (8080 may be the user's)
public let dcssImageTag = "dcss-ladder/webtiles:0.34.0"

/// What a run host is: fixed for its lifetime.
public struct HostInfo: Codable, Equatable, Sendable {
    public var name: String
    public var model: String
    public var chip: String
    public var arch: String
    public var perfCores: Int
    public var effCores: Int
    public var memoryGB: Double
    public var os: String

    public init(name: String, model: String, chip: String, arch: String, perfCores: Int, effCores: Int,
                memoryGB: Double, os: String) {
        self.name = name; self.model = model; self.chip = chip; self.arch = arch
        self.perfCores = perfCores; self.effCores = effCores; self.memoryGB = memoryGB; self.os = os
    }
}

/// How a run host is doing right now.
public struct Vitals: Codable, Equatable, Sendable {
    public var onAC: Bool
    public var thermal: String          // nominal, fair, serious, critical
    public var idleSeconds: Double      // since the last keyboard or mouse input
    public var freeDiskGB: Double
    public var load: Double             // 1-minute load average

    public init(onAC: Bool, thermal: String, idleSeconds: Double, freeDiskGB: Double, load: Double) {
        self.onAC = onAC; self.thermal = thermal; self.idleSeconds = idleSeconds
        self.freeDiskGB = freeDiskGB; self.load = load
    }
}

/// What a run host's owner lets the fleet use. Lives in the agent's agent.json.
public struct AgentPolicy: Codable, Equatable, Sendable {
    public var maxWorkers: Int?         // nil: as many as cores and memory allow
    public var reserveCores: Int        // left for the person using the Mac
    public var allowOnBattery: Bool
    public var idleOnlyMinutes: Int?    // offer nothing until input has been idle this long
    public var gbPerWorker: Double
    public var minFreeDiskGB: Double

    public init(maxWorkers: Int? = nil, reserveCores: Int = 2, allowOnBattery: Bool = false,
                idleOnlyMinutes: Int? = nil, gbPerWorker: Double = 1.0, minFreeDiskGB: Double = 10) {
        self.maxWorkers = maxWorkers; self.reserveCores = reserveCores; self.allowOnBattery = allowOnBattery
        self.idleOnlyMinutes = idleOnlyMinutes; self.gbPerWorker = gbPerWorker; self.minFreeDiskGB = minFreeDiskGB
    }

    enum CodingKeys: String, CodingKey {
        case maxWorkers, reserveCores, allowOnBattery, idleOnlyMinutes, gbPerWorker, minFreeDiskGB
    }

    public init(from decoder: Decoder) throws {     // every key optional, so agent.json can be short
        let c = try decoder.container(keyedBy: CodingKeys.self)
        let d = AgentPolicy()
        maxWorkers = try c.decodeIfPresent(Int.self, forKey: .maxWorkers)
        reserveCores = try c.decodeIfPresent(Int.self, forKey: .reserveCores) ?? d.reserveCores
        allowOnBattery = try c.decodeIfPresent(Bool.self, forKey: .allowOnBattery) ?? d.allowOnBattery
        idleOnlyMinutes = try c.decodeIfPresent(Int.self, forKey: .idleOnlyMinutes)
        gbPerWorker = try c.decodeIfPresent(Double.self, forKey: .gbPerWorker) ?? d.gbPerWorker
        minFreeDiskGB = try c.decodeIfPresent(Double.self, forKey: .minFreeDiskGB) ?? d.minFreeDiskGB
    }
}

public enum AgentState: String, Codable, Sendable {
    case provisioning, ready, busy, error
}

/// What a run host has installed.
public struct Readiness: Codable, Equatable, Sendable {
    public var uv: String?              // version
    public var docker: String?          // "colima (ladder-fleet)", "existing", ...
    public var dockerCPUs: Int?
    public var imageId: String?
    public var bundleId: String?
    public var dcss: Bool               // its DCSS server answers

    public init(uv: String? = nil, docker: String? = nil, dockerCPUs: Int? = nil, imageId: String? = nil,
                bundleId: String? = nil, dcss: Bool = false) {
        self.uv = uv; self.docker = docker; self.dockerCPUs = dockerCPUs; self.imageId = imageId
        self.bundleId = bundleId; self.dcss = dcss
    }
}

/// An agent's standing offer: how many games it will play at once, and why not more.
public struct AgentStatus: Codable, Equatable, Sendable {
    public var state: AgentState
    public var offer: Int
    public var reason: String
    public var vitals: Vitals
    public var readiness: Readiness
    public var busyBatch: String?
    public var note: String?

    public init(state: AgentState, offer: Int, reason: String, vitals: Vitals, readiness: Readiness,
                busyBatch: String? = nil, note: String? = nil) {
        self.state = state; self.offer = offer; self.reason = reason; self.vitals = vitals
        self.readiness = readiness; self.busyBatch = busyBatch; self.note = note
    }
}

/// A slice of a run handed to one host.
public struct Batch: Codable, Equatable, Sendable {
    public var id: String
    public var runId: String
    public var runName: String
    public var play: JSONValue
    public var jobs: [JSONValue]
    public var workers: Int
    public var bundleId: String
    public var imageId: String
}

public struct GameOutcome: Codable, Equatable, Sendable {
    public var game: String
    public var endedBy: String
    public var played: Bool
    public var maxDepth: Int?

    public init(game: String, endedBy: String, played: Bool, maxDepth: Int? = nil) {
        self.game = game; self.endedBy = endedBy; self.played = played; self.maxDepth = maxDepth
    }
}

public enum ArtifactKind: String, Codable, Sendable {
    case bundle   // a snapshot of the repo, as a .tgz
    case image    // `docker save` of the DCSS image, gzipped
}

/// Announces a file that follows as data chunks on `stream`.
public struct FileHeader: Codable, Equatable, Sendable {
    public var size: Int64
    public var sha256: String
    public var stream: UInt32

    public init(size: Int64, sha256: String, stream: UInt32) {
        self.size = size; self.sha256 = sha256; self.stream = stream
    }
}

/// Everything said between an agent and the server, inside the secure channel.
public enum Message: Codable, Equatable, Sendable {
    case hello(info: HostInfo, policy: AgentPolicy, version: String)
    case welcome(server: String, fleetKey: Data?, imageId: String?)
    case status(AgentStatus)
    case assign(Batch)
    case need(kind: ArtifactKind, id: String)
    case artifact(kind: ArtifactKind, id: String, file: FileHeader)
    case artifactError(kind: ArtifactKind, id: String, error: String)
    case progress(batchId: String, line: String)
    case batchDone(batchId: String, runName: String, games: [GameOutcome], seconds: Int, file: FileHeader)
    case batchFailed(batchId: String, error: String)
    case ack(batchId: String)
    case cancel(batchId: String)
    case update(sha256: String, downloadPort: UInt16)    // the server's binary: an installed agent replaces itself
    case log(String)
}

// MARK: - control socket (the ladder-fleet commands on the driving Mac talk to its server)

/// A request to play games, as `ladder brain fleet-jobs` reads it (`request`), plus how to spread it.
public struct RunRequest: Codable, Sendable {
    public var request: JSONValue
    public var hosts: [String]?         // only these agents (default: any)
    public var maxPerHost: Int?         // at most this many games at once on one host
    public var gamesPerWorker: Int      // batch size, per worker

    public init(request: JSONValue, hosts: [String]? = nil, maxPerHost: Int? = nil, gamesPerWorker: Int = 3) {
        self.request = request; self.hosts = hosts; self.maxPerHost = maxPerHost; self.gamesPerWorker = gamesPerWorker
    }
}

public enum ControlRequest: Codable, Sendable {
    case hosts
    case runs
    case run(RunRequest)
    case cancel(runId: String)
    case invite(minutes: Int)
    case forget(agent: String)
}

public struct HostRow: Codable, Sendable {
    public var name: String
    public var connected: Bool
    public var info: HostInfo?
    public var status: AgentStatus?
    public var lastSeen: Date?
    public var batches: Int
    public var games: Int
    public var current: String?         // "p1 batch 4: 7/12"

    public init(name: String, connected: Bool, info: HostInfo?, status: AgentStatus?, lastSeen: Date?, batches: Int,
                games: Int, current: String?) {
        self.name = name; self.connected = connected; self.info = info; self.status = status
        self.lastSeen = lastSeen; self.batches = batches; self.games = games; self.current = current
    }
}

public struct RunRow: Codable, Sendable {
    public var id: String
    public var name: String
    public var total: Int
    public var done: Int
    public var lost: Int
    public var inFlight: Int
    public var pending: Int
    public var byHost: [String: Int]
    public var startedAt: Date
    public var finishedAt: Date?
    public var cancelled: Bool
    public var summary: JSONValue?
    public var note: String?
}

public struct Invite: Codable, Sendable {
    public var code: String
    public var expires: Date
    public var command: String
    public var sha256: String

    public init(code: String, expires: Date, command: String, sha256: String) {
        self.code = code; self.expires = expires; self.command = command; self.sha256 = sha256
    }
}

public enum ControlResponse: Codable, Sendable {
    case hosts([HostRow])
    case runs([RunRow])
    case invite(Invite)
    case ok(String)
    case error(String)
}
