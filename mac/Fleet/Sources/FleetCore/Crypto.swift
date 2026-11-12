import CryptoKit
import Foundation

/// The fleet's channel security: an X25519 exchange mixed with a pre-shared key, then
/// ChaCha20-Poly1305 frames numbered by a counter.
///
/// The pre-shared key is the fleet key (Keychain, service dcss-ladder, account fleet-key) or, while
/// pairing, a key derived from the server's one-time invite code. Recording a pairing doesn't let
/// anyone guess the code offline, since the session key also needs the X25519 secret; guessing it
/// online gets a few tries before the invite closes.
public enum FleetCrypto {
    public static let keychainService = "dcss-ladder"
    public static let fleetKeyAccount = "fleet-key"

    public static func pairingKey(code: String) -> Data {
        Data(SHA256.hash(data: Data("ladder-fleet pair v1|\(normalize(code: code))".utf8)))
    }

    public static func normalize(code: String) -> String {
        code.uppercased().filter { $0.isLetter || $0.isNumber }
    }

    /// A code people can read aloud: no 0/O, 1/I/L.
    public static func newInviteCode(length: Int = 8) -> String {
        let alphabet = Array("ABCDEFGHJKMNPQRSTUVWXYZ23456789")
        var rng = SystemRandomNumberGenerator()
        let chars = (0..<length).map { _ in alphabet[Int(rng.next(upperBound: UInt32(alphabet.count)))] }
        return String(chars.prefix(4)) + "-" + String(chars.dropFirst(4))
    }

    public static func randomBytes(_ n: Int) -> Data {
        var rng = SystemRandomNumberGenerator()
        return Data((0..<n).map { _ in UInt8.random(in: 0...255, using: &rng) })
    }

    public static func newFleetKey() -> Data { randomBytes(32) }

    /// (send, receive) keys for one side of a session.
    public static func sessionKeys(privateKey: Curve25519.KeyAgreement.PrivateKey, peer: Data, psk: Data,
                                   transcript: Data, isClient: Bool) throws -> (send: SymmetricKey, recv: SymmetricKey) {
        let shared = try privateKey.sharedSecretFromKeyAgreement(
            with: Curve25519.KeyAgreement.PublicKey(rawRepresentation: peer))
        var ikm = shared.withUnsafeBytes { Data($0) }
        ikm.append(psk)
        let salt = Data(SHA256.hash(data: transcript))
        func key(_ info: String) -> SymmetricKey {
            HKDF<SHA256>.deriveKey(inputKeyMaterial: SymmetricKey(data: ikm), salt: salt,
                                   info: Data(info.utf8), outputByteCount: 32)
        }
        let c2s = key("ladder-fleet v1 client to server"), s2c = key("ladder-fleet v1 server to client")
        return isClient ? (c2s, s2c) : (s2c, c2s)
    }

    static func nonce(_ counter: UInt64) -> Data {
        var d = Data(count: 4)
        withUnsafeBytes(of: counter.bigEndian) { d.append(contentsOf: $0) }
        return d
    }

    public static func sha256Hex(_ data: Data) -> String {
        SHA256.hash(data: data).map { String(format: "%02x", $0) }.joined()
    }

    public static func sha256Hex(file: URL) throws -> String {
        let h = try FileHandle(forReadingFrom: file)
        defer { try? h.close() }
        var hasher = SHA256()
        while let chunk = try h.read(upToCount: 1 << 20), !chunk.isEmpty { hasher.update(data: chunk) }
        return hasher.finalize().map { String(format: "%02x", $0) }.joined()
    }
}

public enum FleetError: Error, CustomStringConvertible {
    case closed
    case badFrame(String)
    case authentication
    case protocolError(String)
    case failed(String)

    public var description: String {
        switch self {
        case .closed: return "connection closed"
        case .badFrame(let s): return "bad frame: \(s)"
        case .authentication: return "authentication failed (wrong fleet key or invite code)"
        case .protocolError(let s): return "protocol: \(s)"
        case .failed(let s): return s
        }
    }
}

/// Seals frames under one direction's key. Each frame's nonce is its number, so a frame can't be
/// replayed, dropped or reordered without the other side noticing.
public struct FrameSealer: Sendable {
    let key: SymmetricKey
    var counter: UInt64 = 0
    public init(key: SymmetricKey) { self.key = key }

    public mutating func seal(_ plain: Data) throws -> Data {
        let box = try ChaChaPoly.seal(plain, using: key, nonce: ChaChaPoly.Nonce(data: FleetCrypto.nonce(counter)))
        counter += 1
        return box.combined
    }
}

public struct FrameOpener: Sendable {
    let key: SymmetricKey
    var counter: UInt64 = 0
    public init(key: SymmetricKey) { self.key = key }

    public mutating func open(_ sealed: Data) throws -> Data {
        let box: ChaChaPoly.SealedBox
        do { box = try ChaChaPoly.SealedBox(combined: sealed) } catch { throw FleetError.badFrame("not a sealed box") }
        guard Data(box.nonce) == FleetCrypto.nonce(counter) else { throw FleetError.badFrame("out of order") }
        do {
            let plain = try ChaChaPoly.open(box, using: key)
            counter += 1
            return plain
        } catch {
            throw FleetError.authentication
        }
    }
}
