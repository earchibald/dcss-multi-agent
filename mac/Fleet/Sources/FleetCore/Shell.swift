import Foundation

public struct ShellResult: Sendable {
    public var status: Int32
    public var out: String
    public var err: String
    public var ok: Bool { status == 0 }
}

/// Runs tools (uv, docker, colima, tar, git) with a PATH that includes the fleet's own bin directory
/// and the usual Homebrew places, since a LaunchAgent starts with almost no PATH.
public enum Shell {
    nonisolated(unsafe) public static var extraPath: [String] = []
    nonisolated(unsafe) public static var extraEnv: [String: String] = [:]

    public static var path: String {
        let home = FileManager.default.homeDirectoryForCurrentUser.path
        let base = ProcessInfo.processInfo.environment["PATH"] ?? "/usr/bin:/bin:/usr/sbin:/sbin"
        return (extraPath + ["/opt/homebrew/bin", "/usr/local/bin", "\(home)/.local/bin", "\(home)/.cargo/bin"] + [base])
            .joined(separator: ":")
    }

    public static func which(_ tool: String) -> String? {
        if tool.hasPrefix("/") { return FileManager.default.isExecutableFile(atPath: tool) ? tool : nil }
        for dir in path.split(separator: ":") {
            let p = "\(dir)/\(tool)"
            if FileManager.default.isExecutableFile(atPath: p) { return p }
        }
        return nil
    }

    /// Run `tool` with `args`. `onLine` sees stdout and stderr lines as they come.
    @discardableResult
    public static func run(_ tool: String, _ args: [String], cwd: URL? = nil, env: [String: String] = [:],
                           onLine: (@Sendable (String) -> Void)? = nil,
                           started: (@Sendable (Process) -> Void)? = nil) async throws -> ShellResult {
        guard let exe = which(tool) else { throw FleetError.failed("\(tool) not found (PATH \(path))") }
        let p = Process()
        p.executableURL = URL(fileURLWithPath: exe)
        p.arguments = args
        if let cwd { p.currentDirectoryURL = cwd }
        var environment = ProcessInfo.processInfo.environment
        environment["PATH"] = path
        for (k, v) in extraEnv { environment[k] = v }
        for (k, v) in env { environment[k] = v }
        p.environment = environment
        let outPipe = Pipe(), errPipe = Pipe()
        p.standardOutput = outPipe
        p.standardError = errPipe
        p.standardInput = FileHandle.nullDevice
        let out = LineCollector(onLine), err = LineCollector(onLine)
        outPipe.fileHandleForReading.readabilityHandler = { out.feed($0.availableData) }
        errPipe.fileHandleForReading.readabilityHandler = { err.feed($0.availableData) }
        return try await withCheckedThrowingContinuation { c in
            p.terminationHandler = { proc in
                outPipe.fileHandleForReading.readabilityHandler = nil
                errPipe.fileHandleForReading.readabilityHandler = nil
                out.feed((try? outPipe.fileHandleForReading.readToEnd()) ?? Data())
                err.feed((try? errPipe.fileHandleForReading.readToEnd()) ?? Data())
                c.resume(returning: ShellResult(status: proc.terminationStatus, out: out.finish(), err: err.finish()))
            }
            do {
                try p.run()
                started?(p)
            } catch {
                c.resume(throwing: error)
            }
        }
    }

    /// Run and require success; returns stdout, trimmed.
    @discardableResult
    public static func check(_ tool: String, _ args: [String], cwd: URL? = nil, env: [String: String] = [:],
                             onLine: (@Sendable (String) -> Void)? = nil) async throws -> String {
        let r = try await run(tool, args, cwd: cwd, env: env, onLine: onLine)
        guard r.ok else {
            let tail = (r.err.isEmpty ? r.out : r.err).split(separator: "\n").suffix(6).joined(separator: "\n")
            throw FleetError.failed("\(tool) \(args.prefix(3).joined(separator: " ")) failed (\(r.status)): \(tail)")
        }
        return r.out.trimmingCharacters(in: .whitespacesAndNewlines)
    }

    /// A pipeline in /bin/sh, with values passed as $1, $2, ... (never spliced into the script).
    @discardableResult
    public static func sh(_ script: String, _ args: [String] = [], cwd: URL? = nil, env: [String: String] = [:],
                          onLine: (@Sendable (String) -> Void)? = nil) async throws -> String {
        try await check("/bin/sh", ["-c", "set -o pipefail; " + script, "sh"] + args, cwd: cwd, env: env, onLine: onLine)
    }
}

final class LineCollector: @unchecked Sendable {
    private let lock = NSLock()
    private var all = Data()
    private var partial = Data()
    private let onLine: (@Sendable (String) -> Void)?
    private static let cap = 4 << 20       // keep the last few MB of output, not all of it

    init(_ onLine: (@Sendable (String) -> Void)?) { self.onLine = onLine }

    func feed(_ data: Data) {
        guard !data.isEmpty else { return }
        lock.lock()
        all.append(data)
        if all.count > Self.cap { all.removeFirst(all.count - Self.cap) }
        var lines: [String] = []
        if onLine != nil {
            partial.append(data)
            while let nl = partial.firstIndex(of: 10) {
                lines.append(String(decoding: partial[partial.startIndex..<nl], as: UTF8.self))
                partial.removeSubrange(partial.startIndex...nl)
            }
        }
        lock.unlock()
        for l in lines { onLine?(l) }
    }

    func finish() -> String {
        lock.lock()
        defer { lock.unlock() }
        if let onLine, !partial.isEmpty { onLine(String(decoding: partial, as: UTF8.self)); partial = Data() }
        return String(decoding: all, as: UTF8.self)
    }
}
