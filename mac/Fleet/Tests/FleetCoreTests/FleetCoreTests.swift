import CryptoKit
import Foundation
import Testing
@testable import FleetCore

private let info = HostInfo(name: "m4", model: "Mac16,8", chip: "Apple M4 Pro", arch: "arm64", perfCores: 10,
                            effCores: 4, memoryGB: 48, os: "macOS 27.1")
private let calm = Vitals(onAC: true, thermal: "nominal", idleSeconds: 600, freeDiskGB: 200, load: 1)

private func handshake(serverKey: Data, clientKey: Data, mode: String = "fleet")
    async throws -> (SecureChannel, SecureChannel) {
    let (a, b) = MemoryStream.pair()
    async let server = SecureChannel.server(b, name: "Eugene-M5") { _, _ in serverKey }
    let client = try await SecureChannel.client(a, name: "m4", mode: mode, psk: clientKey)
    return (client, try await server.0)
}

@Test func messagesCrossTheChannelBothWays() async throws {
    let key = FleetCrypto.newFleetKey()
    let (client, server) = try await handshake(serverKey: key, clientKey: key)
    #expect(client.peer == "Eugene-M5" && server.peer == "m4")
    try await client.send(.hello(info: info, policy: AgentPolicy(), version: fleetVersion))
    guard case .message(.hello(let got, _, _)) = try await server.receive() else { Issue.record("no hello"); return }
    #expect(got == info)
    try await server.send(.ack(batchId: "r1-1"))
    try await server.send(.welcome(server: "Eugene-M5", fleetKey: key, imageId: "sha256:abc"))
    guard case .message(.ack(let id)) = try await client.receive() else { Issue.record("no ack"); return }
    #expect(id == "r1-1")
    guard case .message(.welcome(_, let k, _)) = try await client.receive() else { Issue.record("no welcome"); return }
    #expect(k == key)
}

@Test func aWrongKeyCannotTalk() async throws {
    let (client, server) = try await handshake(serverKey: FleetCrypto.newFleetKey(), clientKey: FleetCrypto.newFleetKey())
    try await client.send(.log("hi"))
    await #expect(throws: FleetError.self) { _ = try await server.receive() }
}

@Test func pairingCodesMatchHoweverTheyAreTyped() async throws {
    let code = FleetCrypto.newInviteCode()
    #expect(code.count == 9 && code.contains("-"))
    #expect(FleetCrypto.pairingKey(code: code) == FleetCrypto.pairingKey(code: code.lowercased().replacingOccurrences(of: "-", with: " ")))
    let (client, server) = try await handshake(serverKey: FleetCrypto.pairingKey(code: code),
                                               clientKey: FleetCrypto.pairingKey(code: code.lowercased()), mode: "pair")
    try await client.send(.log("pair"))
    guard case .message(.log(let s)) = try await server.receive() else { Issue.record("no log"); return }
    #expect(s == "pair")
}

@Test func aServerWithNoKeyForTheModeRefuses() async throws {
    let (a, b) = MemoryStream.pair()
    let client = Task { try await SecureChannel.client(a, name: "x", mode: "pair", psk: Data()) }
    var refused = false
    do { _ = try await SecureChannel.server(b, name: "s") { mode, _ in mode == "fleet" ? Data() : nil } }
    catch { refused = true }
    #expect(refused)
    a.close()
    _ = try? await client.value
}

@Test func replayedOrReorderedFramesAreRejected() throws {
    let key = SymmetricKey(size: .bits256)
    var sealer = FrameSealer(key: key)
    var opener = FrameOpener(key: key)
    let f0 = try sealer.seal(Data("zero".utf8)), f1 = try sealer.seal(Data("one".utf8))
    #expect(throws: FleetError.self) { _ = try opener.open(f1) }
    #expect(try opener.open(f0) == Data("zero".utf8))
    #expect(throws: FleetError.self) { _ = try opener.open(f0) }
    #expect(try opener.open(f1) == Data("one".utf8))
}

@Test func filesArriveWholeAndChecked() async throws {
    let key = FleetCrypto.newFleetKey()
    let (client, server) = try await handshake(serverKey: key, clientKey: key)
    let dir = FileManager.default.temporaryDirectory.appendingPathComponent("fleet-test-\(UUID())")
    try FileManager.default.createDirectory(at: dir, withIntermediateDirectories: true)
    defer { try? FileManager.default.removeItem(at: dir) }
    let src = dir.appendingPathComponent("src.bin")
    try FleetCrypto.randomBytes(300_000).write(to: src)
    let header = FileHeader(size: 300_000, sha256: try FleetCrypto.sha256Hex(file: src), stream: 7)
    let sinks = FileSinks()
    let dst = dir.appendingPathComponent("dst.bin")
    let arrived = AsyncStream<Result<URL, Error>>.makeStream()
    try sinks.open(header, at: dst) { arrived.continuation.yield($0) }
    try await client.sendFile(src, stream: 7, chunk: 64_000)
    var last = false
    while !last {
        guard case .chunk(let id, let data, let l) = try await server.receive() else { Issue.record("not a chunk"); return }
        #expect(sinks.write(stream: id, data: data, last: l))
        last = l
    }
    var it = arrived.stream.makeAsyncIterator()
    let result = await it.next()
    #expect(try result?.get() == dst)
    #expect(try Data(contentsOf: dst) == Data(contentsOf: src))
}

// MARK: - scheduling

private func run(_ n: Int, id: String = "r1", hosts: [String]? = nil, maxPerHost: Int? = nil) -> FleetRun {
    FleetRun(id: id, name: "p-\(id)", play: .object([:]), jobs: (1...n).map { .int($0) }, bundleId: "b", imageId: "i",
             hosts: hosts, maxPerHost: maxPerHost, gamesPerWorker: 2)
}

private func played(_ b: Batch, except: Set<String> = []) -> [GameOutcome] {
    b.jobs.map { GameOutcome(game: $0.gameKey, endedBy: except.contains($0.gameKey) ? "hung" : "died",
                             played: !except.contains($0.gameKey), maxDepth: 3) }
}

@Test func batchesFollowTheOfferAndTheRunsLimits() throws {
    var s = Scheduler()
    s.add(run(20, maxPerHost: 3))
    let bMaybe = s.assign(agent: "m4", offer: 8)
    let b = try #require(bMaybe)
    #expect(b.workers == 3 && b.jobs.count == 6)             // 3 workers x 2 games each
    let cMaybe = s.assign(agent: "m1-mini", offer: 2)
    let c = try #require(cMaybe)
    #expect(c.workers == 2 && c.jobs.map(\.gameKey) == ["7", "8", "9", "10"])
    #expect(s.assign(agent: "m4", offer: 0) == nil)
}

@Test func unplayedGamesAreRetriedOnceThenLost() throws {
    var s = Scheduler()
    s.add(run(2))
    let bMaybe = s.assign(agent: "m4", offer: 1)
    let b = try #require(bMaybe)
    s.complete(batch: b.id, outcomes: played(b, except: ["2"]), agent: "m4")
    let retryMaybe = s.assign(agent: "m4", offer: 1)
    let retry = try #require(retryMaybe)
    #expect(retry.jobs == [.int(2)])
    s.complete(batch: retry.id, outcomes: played(retry, except: ["2"]), agent: "m4")
    let r = try #require(s.run("r1"))
    #expect(r.done == [0] && r.lost == [1] && r.finished && r.finishedAt != nil)
    #expect(r.byHost == ["m4": 1])
}

@Test func aHostThatDropsOutGivesItsGamesBack() throws {
    var s = Scheduler()
    s.add(run(4))
    let bMaybe = s.assign(agent: "m1-mini", offer: 2)
    let b = try #require(bMaybe)
    #expect(s.agentLost("m1-mini") == [b.id])
    let againMaybe = s.assign(agent: "m4", offer: 2)
    let again = try #require(againMaybe)
    #expect(again.jobs == b.jobs)
    // the lost host comes back with results for the batch that was given away: they still count
    s.complete(batch: b.id, outcomes: played(b), agent: "m1-mini")
    s.complete(batch: again.id, outcomes: played(again), agent: "m4")
    #expect(try #require(s.run("r1")).done.count == 4)
}

@Test func runsCanBeLimitedToSomeHosts() {
    var s = Scheduler()
    s.add(run(4, hosts: ["m4"]))
    #expect(s.assign(agent: "m1-mini", offer: 4) == nil)
    #expect(s.assign(agent: "m4", offer: 4) != nil)
}

@Test func forkJobsAreKeyedByTheirId() {
    let fork = JSONValue.object(["seed": .int(12), "id": .string("12-40-fight"), "script": .array([])])
    #expect(fork.gameKey == "12-40-fight")
    #expect(JSONValue.int(500_001).gameKey == "500001")
}

@Test func schedulerSurvivesARestart() throws {
    var s = Scheduler()
    s.add(run(4))
    _ = s.assign(agent: "m4", offer: 1)
    var back = try JSONDecoder().decode(Scheduler.self, from: JSONEncoder().encode(s))
    back.requeueInFlight()
    #expect(back.runs[0].pending.count == 4 && back.owner.isEmpty)
}

// MARK: - offers

@Test func offersFollowCoresMemoryAndTheOwnersRules() {
    #expect(OfferPolicy.offer(info: info, vitals: calm, policy: AgentPolicy(), dockerCPUs: nil).workers == 10)
    let mini = HostInfo(name: "m1-mini", model: "Macmini9,1", chip: "Apple M1", arch: "arm64", perfCores: 4,
                        effCores: 4, memoryGB: 8, os: "")
    #expect(OfferPolicy.offer(info: mini, vitals: calm, policy: AgentPolicy(), dockerCPUs: nil).workers == 4)
    var battery = calm
    battery.onAC = false
    #expect(OfferPolicy.offer(info: info, vitals: battery, policy: AgentPolicy(), dockerCPUs: nil) == (0, "on battery"))
    #expect(OfferPolicy.offer(info: info, vitals: battery, policy: AgentPolicy(allowOnBattery: true), dockerCPUs: nil).workers == 10)
    var busy = calm
    busy.idleSeconds = 20
    #expect(OfferPolicy.offer(info: info, vitals: busy, policy: AgentPolicy(idleOnlyMinutes: 5), dockerCPUs: nil).workers == 0)
    #expect(OfferPolicy.offer(info: info, vitals: calm, policy: AgentPolicy(maxWorkers: 6), dockerCPUs: nil).workers == 6)
    #expect(OfferPolicy.offer(info: info, vitals: calm, policy: AgentPolicy(), dockerCPUs: 2).workers == 4)
    var hot = calm
    hot.thermal = "serious"
    #expect(OfferPolicy.offer(info: info, vitals: hot, policy: AgentPolicy(), dockerCPUs: nil).workers == 5)
}

@Test func aShortAgentJsonKeepsTheDefaults() throws {
    let p = try JSONDecoder().decode(AgentPolicy.self, from: Data(#"{"maxWorkers": 3}"#.utf8))
    #expect(p.maxWorkers == 3 && p.reserveCores == 2 && !p.allowOnBattery)
}

@Test func progressLinesAreRecognised() {
    #expect(ProgressLine.isGame("  [3/12] seed 42: died  reached 5  at D:5  xl 7  turn 4000"))
    #expect(!ProgressLine.isGame("p1 batch m4-1: 12 games, 4 workers"))
}

@Test func shellRunsPipelinesWithArgumentsKeptApart() async throws {
    let out = try await Shell.sh(#"printf '%s' "$1" | wc -c"#, ["a b; echo no"])
    #expect(out.trimmingCharacters(in: .whitespaces) == "12")
    let lines = LinesBox()
    _ = try await Shell.run("/bin/sh", ["-c", "echo one; echo two >&2"], onLine: { lines.add($0) })
    #expect(lines.all.sorted() == ["one", "two"])
}

final class LinesBox: @unchecked Sendable {
    private let lock = NSLock()
    private var lines: [String] = []
    func add(_ s: String) { lock.lock(); lines.append(s); lock.unlock() }
    var all: [String] { lock.lock(); defer { lock.unlock() }; return lines }
}

@Test func messagesFromANewerVersionAreSkippedNotFatal() async throws {
    let key = FleetCrypto.newFleetKey()
    let (client, server) = try await handshake(serverKey: key, clientKey: key)
    try await client.sendRaw(Data([1]) + Data(#"{"futureKind":{"x":1}}"#.utf8))
    guard case .unknown = try await server.receive() else { Issue.record("not skipped"); return }
    try await client.send(.log("still here"))
    guard case .message(.log(let s)) = try await server.receive() else { Issue.record("channel broke"); return }
    #expect(s == "still here")
}
