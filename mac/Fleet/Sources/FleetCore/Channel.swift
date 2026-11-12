import CryptoKit
import Foundation
import Network

/// Bytes in order, both ways. `enqueue` must hand the bytes on before it returns, so frames go out in
/// the order they were sealed.
public protocol ByteStream: AnyObject, Sendable {
    func enqueue(_ data: Data, done: @escaping @Sendable (Error?) -> Void)
    func read(_ count: Int) async throws -> Data
    func close()
}

extension ByteStream {
    public func write(_ data: Data) async throws {
        try await withCheckedThrowingContinuation { (c: CheckedContinuation<Void, Error>) in
            enqueue(data) { error in if let error { c.resume(throwing: error) } else { c.resume() } }
        }
    }
}

public final class NWByteStream: ByteStream, @unchecked Sendable {
    public let connection: NWConnection
    private let queue = DispatchQueue(label: "ladder-fleet.connection")

    public init(_ connection: NWConnection) { self.connection = connection }

    /// `blocked` is called (once) if macOS's Local Network privacy is holding the connection back. That
    /// applies to a LaunchAgent, not to SSH or Terminal. The connection then waits instead of failing,
    /// so macOS has time to ask on the screen, and it goes ahead as soon as it's allowed.
    public static func connect(host: String, port: UInt16,
                               blocked: (@Sendable () -> Void)? = nil) async throws -> NWByteStream {
        let params = NWParameters.tcp
        if let tcp = params.defaultProtocolStack.transportProtocol as? NWProtocolTCP.Options {
            tcp.enableKeepalive = true
            tcp.keepaliveIdle = 30
        }
        let s = NWByteStream(NWConnection(host: NWEndpoint.Host(host), port: NWEndpoint.Port(rawValue: port)!, using: params))
        try await s.start(blocked: blocked)
        return s
    }

    public static func connect(unixPath: String) async throws -> NWByteStream {
        let s = NWByteStream(NWConnection(to: .unix(path: unixPath), using: .tcp))
        try await s.start()
        return s
    }

    public struct LocalNetworkBlocked: Error, CustomStringConvertible {
        public var description: String { "macOS's Local Network privacy is keeping this process off the local network" }
    }

    /// Local Network privacy refusing this process. The documented sign is unsatisfiedReason
    /// .localNetworkDenied, but macOS 26 reports ENETDOWN on a path that says it's satisfied (seen on an
    /// M1 running 26.4: Apple's nc, from the same LaunchAgent context, got through).
    public static func isLocalNetworkBlock(_ error: Error, _ path: NWPath?) -> Bool {
        if path?.unsatisfiedReason == .localNetworkDenied { return true }
        guard case .posix(let code)? = error as? NWError, code == .ENETDOWN else { return false }
        return path?.status == .satisfied
    }

    /// Wait until the connection is up (or has failed). With `blocked`, a connection held back by Local
    /// Network privacy keeps waiting rather than failing.
    public func start(blocked: (@Sendable () -> Void)? = nil) async throws {
        try await withCheckedThrowingContinuation { (c: CheckedContinuation<Void, Error>) in
            let once = Once()
            let told = Once()
            connection.stateUpdateHandler = { [connection] state in
                switch state {
                case .ready: if once.claim() { c.resume() }
                case .waiting(let e) where blocked != nil && Self.isLocalNetworkBlock(e, connection.currentPath):
                    // Wait a while (so macOS can ask on the screen), then give up so the caller tries
                    // afresh: a connection refused this way doesn't go ahead by itself once allowed.
                    if told.claim() {
                        blocked?()
                        DispatchQueue.global().asyncAfter(deadline: .now() + 15) {
                            if once.claim() { connection.cancel(); c.resume(throwing: LocalNetworkBlocked()) }
                        }
                    }
                case .failed(let e), .waiting(let e): if once.claim() { connection.cancel(); c.resume(throwing: e) }
                case .cancelled: if once.claim() { c.resume(throwing: FleetError.closed) }
                default: break
                }
            }
            connection.start(queue: queue)
        }
    }

    public func enqueue(_ data: Data, done: @escaping @Sendable (Error?) -> Void) {
        connection.send(content: data, completion: .contentProcessed { done($0) })
    }

    public func read(_ count: Int) async throws -> Data {
        if count == 0 { return Data() }
        return try await withCheckedThrowingContinuation { c in
            connection.receive(minimumIncompleteLength: count, maximumLength: count) { data, _, _, error in
                if let error { c.resume(throwing: error) }
                else if let data, data.count == count { c.resume(returning: data) }
                else { c.resume(throwing: FleetError.closed) }
            }
        }
    }

    public func close() { connection.cancel() }

    public var remote: String {
        if case .hostPort(let host, _) = connection.endpoint { return "\(host)" }
        return "\(connection.endpoint)"
    }
}

/// True the first time only.
public final class Once: @unchecked Sendable {
    private let lock = NSLock()
    private var done = false
    public init() {}
    public func claim() -> Bool {
        lock.lock(); defer { lock.unlock() }
        if done { return false }
        done = true
        return true
    }
}

/// Two ends of an in-memory connection, for tests.
public final class MemoryStream: ByteStream, @unchecked Sendable {
    private let lock = NSLock()
    private var buffer = Data()
    private var waiters: [(Int, CheckedContinuation<Data, Error>)] = []
    private var closed = false
    weak var peer: MemoryStream?

    public static func pair() -> (MemoryStream, MemoryStream) {
        let a = MemoryStream(), b = MemoryStream()
        a.peer = b; b.peer = a
        return (a, b)
    }

    public func enqueue(_ data: Data, done: @escaping @Sendable (Error?) -> Void) {
        guard let peer else { done(FleetError.closed); return }
        peer.deliver(data)
        done(nil)
    }

    func deliver(_ data: Data) {
        lock.lock()
        buffer.append(data)
        var ready: [(CheckedContinuation<Data, Error>, Data)] = []
        while let (n, c) = waiters.first, buffer.count >= n {
            waiters.removeFirst()
            ready.append((c, Data(buffer.prefix(n))))
            buffer.removeFirst(n)
        }
        lock.unlock()
        for (c, d) in ready { c.resume(returning: d) }
    }

    public func read(_ count: Int) async throws -> Data {
        try await withCheckedThrowingContinuation { c in
            lock.lock()
            if buffer.count >= count && waiters.isEmpty {
                let d = Data(buffer.prefix(count))
                buffer.removeFirst(count)
                lock.unlock()
                c.resume(returning: d)
            } else if closed {
                lock.unlock()
                c.resume(throwing: FleetError.closed)
            } else {
                waiters.append((count, c))
                lock.unlock()
            }
        }
    }

    public func close() {
        for s in [self, peer].compactMap({ $0 }) {
            s.lock.lock()
            s.closed = true
            let w = s.waiters
            s.waiters = []
            s.lock.unlock()
            for (_, c) in w { c.resume(throwing: FleetError.closed) }
        }
    }
}

/// Length-prefixed frames.
public struct Frames: Sendable {
    public let stream: ByteStream
    public static let maxFrame = 4 << 20

    public init(_ stream: ByteStream) { self.stream = stream }

    public static func encode(_ body: Data) -> Data {
        var d = withUnsafeBytes(of: UInt32(body.count).bigEndian) { Data($0) }
        d.append(body)
        return d
    }

    public func send(_ body: Data) async throws { try await stream.write(Self.encode(body)) }

    public func receive(max: Int = Frames.maxFrame) async throws -> Data {
        let head = try await stream.read(4)
        let n = Int(head.reduce(UInt32(0)) { $0 << 8 | UInt32($1) })
        guard n <= max else { throw FleetError.badFrame("\(n) bytes is too long") }
        return try await stream.read(n)
    }
}

public enum Incoming: Sendable {
    case message(Message)
    case chunk(stream: UInt32, data: Data, last: Bool)
    case unknown(String)        // a message from a newer version: skipped, so an old agent can still update
}

struct ClientHello: Codable {
    var v: String
    var mode: String        // "fleet" or "pair"
    var name: String
    var pub: Data
    var nonce: Data
}

struct ServerHello: Codable {
    var v: String
    var server: String
    var pub: Data
    var nonce: Data
}

/// An authenticated, encrypted message channel. One task reads (`receive`); any task may send.
public actor SecureChannel {
    public nonisolated let peer: String
    public nonisolated let stream: ByteStream
    private var sealer: FrameSealer
    private var opener: FrameOpener
    private static let encoder = JSONEncoder()

    init(stream: ByteStream, keys: (send: SymmetricKey, recv: SymmetricKey), peer: String) {
        self.stream = stream
        self.peer = peer
        sealer = FrameSealer(key: keys.send)
        opener = FrameOpener(key: keys.recv)
    }

    private func sendPlain(_ plain: Data) async throws {
        // seal and enqueue with no suspension between them: frame order is nonce order
        let frame = Frames.encode(try sealer.seal(plain))
        try await withCheckedThrowingContinuation { (c: CheckedContinuation<Void, Error>) in
            stream.enqueue(frame) { error in if let error { c.resume(throwing: error) } else { c.resume() } }
        }
    }

    /// For tests: a frame with any content.
    func sendRaw(_ plain: Data) async throws { try await sendPlain(plain) }

    public func send(_ message: Message) async throws {
        var plain = Data([1])
        plain.append(try Self.encoder.encode(message))
        try await sendPlain(plain)
    }

    public func sendChunk(stream id: UInt32, data: Data, last: Bool) async throws {
        var plain = Data([2])
        withUnsafeBytes(of: id.bigEndian) { plain.append(contentsOf: $0) }
        plain.append(last ? 1 : 0)
        plain.append(data)
        try await sendPlain(plain)
    }

    /// Send a file as `stream`'s chunks. The header announcing it must already have gone.
    public func sendFile(_ url: URL, stream id: UInt32, chunk: Int = 1 << 20) async throws {
        let h = try FileHandle(forReadingFrom: url)
        defer { try? h.close() }
        var next = try h.read(upToCount: chunk) ?? Data()
        while true {
            let after = next.isEmpty ? Data() : (try h.read(upToCount: chunk) ?? Data())
            try await sendChunk(stream: id, data: next, last: after.isEmpty)
            if after.isEmpty { break }
            next = after
        }
    }

    public func receive() async throws -> Incoming {
        let sealed = try await Frames(stream).receive(max: Frames.maxFrame + 64)
        let plain = try opener.open(sealed)
        guard let kind = plain.first else { throw FleetError.badFrame("empty") }
        let body = plain.dropFirst()
        switch kind {
        case 1:
            do { return .message(try JSONDecoder().decode(Message.self, from: Data(body))) }
            catch { return .unknown(String(decoding: body.prefix(80), as: UTF8.self)) }
        case 2:
            guard body.count >= 5 else { throw FleetError.badFrame("short chunk") }
            let b = Array(body.prefix(5))
            let id = b[0..<4].reduce(UInt32(0)) { $0 << 8 | UInt32($1) }
            return .chunk(stream: id, data: Data(body.dropFirst(5)), last: b[4] == 1)
        default:
            throw FleetError.badFrame("kind \(kind)")
        }
    }

    public nonisolated func close() { stream.close() }

    // MARK: handshake

    /// The agent's side. `psk` is the fleet key, or the pairing key for `mode` "pair".
    public static func client(_ stream: ByteStream, name: String, mode: String, psk: Data) async throws -> SecureChannel {
        let frames = Frames(stream)
        let priv = Curve25519.KeyAgreement.PrivateKey()
        let hello = try JSONEncoder().encode(ClientHello(v: fleetVersion, mode: mode, name: name,
                                                         pub: priv.publicKey.rawRepresentation,
                                                         nonce: FleetCrypto.randomBytes(32)))
        try await frames.send(hello)
        let reply = try await frames.receive(max: 8192)
        let sh: ServerHello
        do { sh = try JSONDecoder().decode(ServerHello.self, from: reply) }
        catch { throw FleetError.protocolError("not a fleet server") }
        guard sh.v == fleetVersion else { throw FleetError.protocolError("server speaks version \(sh.v), we speak \(fleetVersion)") }
        let keys = try FleetCrypto.sessionKeys(privateKey: priv, peer: sh.pub, psk: psk, transcript: hello + reply, isClient: true)
        return SecureChannel(stream: stream, keys: keys, peer: sh.server)
    }

    /// The server's side. `psk` picks the key for the client's mode and name (nil: refuse).
    public static func server(_ stream: ByteStream, name: String,
                              psk: (_ mode: String, _ client: String) async -> Data?) async throws -> (SecureChannel, mode: String) {
        let frames = Frames(stream)
        let hello = try await frames.receive(max: 8192)
        let ch: ClientHello
        do { ch = try JSONDecoder().decode(ClientHello.self, from: hello) }
        catch { throw FleetError.protocolError("not a fleet agent") }
        guard ch.v == fleetVersion else { throw FleetError.protocolError("agent speaks version \(ch.v), we speak \(fleetVersion)") }
        guard let key = await psk(ch.mode, ch.name) else { throw FleetError.protocolError("no \(ch.mode) key for \(ch.name)") }
        let priv = Curve25519.KeyAgreement.PrivateKey()
        let reply = try JSONEncoder().encode(ServerHello(v: fleetVersion, server: name, pub: priv.publicKey.rawRepresentation,
                                                         nonce: FleetCrypto.randomBytes(32)))
        try await frames.send(reply)
        let keys = try FleetCrypto.sessionKeys(privateKey: priv, peer: ch.pub, psk: key, transcript: hello + reply, isClient: false)
        return (SecureChannel(stream: stream, keys: keys, peer: ch.name), ch.mode)
    }
}

/// Collects files arriving as chunks, by stream id. Used by the single reading task.
public final class FileSinks: @unchecked Sendable {
    struct Sink {
        let url: URL
        let handle: FileHandle
        let header: FileHeader
        var written: Int64
        let done: (Result<URL, Error>) -> Void
    }
    private var sinks: [UInt32: Sink] = [:]
    private let lock = NSLock()

    public init() {}

    public func open(_ header: FileHeader, at url: URL, done: @escaping (Result<URL, Error>) -> Void) throws {
        try? FileManager.default.removeItem(at: url)
        try FileManager.default.createDirectory(at: url.deletingLastPathComponent(), withIntermediateDirectories: true)
        FileManager.default.createFile(atPath: url.path, contents: nil)
        let h = try FileHandle(forWritingTo: url)
        lock.lock(); sinks[header.stream] = Sink(url: url, handle: h, header: header, written: 0, done: done); lock.unlock()
    }

    /// Returns false if no file is open on that stream.
    public func write(stream: UInt32, data: Data, last: Bool) -> Bool {
        lock.lock()
        guard var s = sinks[stream] else { lock.unlock(); return false }
        do {
            try s.handle.write(contentsOf: data)
            s.written += Int64(data.count)
        } catch {
            sinks[stream] = nil
            lock.unlock()
            try? s.handle.close()
            s.done(.failure(error))
            return true
        }
        if !last { sinks[stream] = s; lock.unlock(); return true }
        sinks[stream] = nil
        lock.unlock()
        try? s.handle.close()
        let sinkDone = s.done, url = s.url, header = s.header, written = s.written
        // hashing a large image takes a moment: off the reading task
        DispatchQueue.global().async {
            if written != header.size {
                sinkDone(.failure(FleetError.failed("got \(written) of \(header.size) bytes")))
            } else if let sum = try? FleetCrypto.sha256Hex(file: url), sum == header.sha256 {
                sinkDone(.success(url))
            } else {
                sinkDone(.failure(FleetError.failed("checksum mismatch for \(url.lastPathComponent)")))
            }
        }
        return true
    }

    public func failAll(_ error: Error) {
        lock.lock(); let all = sinks; sinks = [:]; lock.unlock()
        for s in all.values { try? s.handle.close(); s.done(.failure(error)) }
    }
}
