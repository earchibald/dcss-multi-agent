import AppKit

/// A cockpit the app starts itself: `ladder cockpit` in the repo, run through the login shell so
/// it sees the same PATH as a terminal. Stopping sends SIGINT, which the cockpit takes as Ctrl-C:
/// it stops after the current action and leaves the game saved.
@MainActor
final class Server {
    private(set) var process: Process?
    private(set) var log = ""
    var onOutput: ((String) -> Void)?
    var onExit: ((Int32) -> Void)?

    var running: Bool { process?.isRunning ?? false }

    var command: String {
        let repo = Prefs.repo
        let ladder = FileManager.default.isExecutableFile(atPath: repo + "/.venv/bin/ladder") ? "./.venv/bin/ladder" : "uv run ladder"
        return "\(ladder) cockpit --port \(Prefs.port) \(Prefs.cockpitArgs)"
    }

    func start() throws {
        guard !running else { return }
        let p = Process()
        p.executableURL = URL(fileURLWithPath: Self.loginShell)
        p.arguments = ["-lc", "exec \(command)"]       // exec: the signal goes straight to the cockpit
        p.currentDirectoryURL = URL(fileURLWithPath: Prefs.repo)
        var env = ProcessInfo.processInfo.environment
        env["PYTHONUNBUFFERED"] = "1"
        p.environment = env
        let pipe = Pipe()
        p.standardOutput = pipe
        p.standardError = pipe
        p.standardInput = FileHandle.nullDevice
        pipe.fileHandleForReading.readabilityHandler = { [weak self] h in
            let data = h.availableData
            if data.isEmpty { h.readabilityHandler = nil; return }
            let text = String(decoding: data, as: UTF8.self)
            Task { @MainActor in self?.append(text) }
        }
        p.terminationHandler = { [weak self] proc in
            let code = proc.terminationStatus
            Task { @MainActor in
                self?.process = nil
                self?.append("\n— cockpit exited (\(code)) —\n")
                self?.onExit?(code)
            }
        }
        append("$ cd \(Prefs.repo) && \(command)\n")
        try p.run()
        process = p
    }

    func stop() {
        guard running else { return }
        append("\n— stopping: the game is left saved —\n")
        process?.interrupt()
    }

    private func append(_ text: String) {
        log += text
        if log.count > 400_000 { log = String(log.suffix(300_000)) }
        onOutput?(text)
    }

    static var loginShell: String {
        if let pw = getpwuid(getuid()), let sh = pw.pointee.pw_shell, let s = String(validatingCString: sh),
           FileManager.default.isExecutableFile(atPath: s) { return s }
        return "/bin/zsh"
    }
}

/// The cockpit's output, for a cockpit the app started.
@MainActor
final class LogWindow {
    let window: NSWindow
    private let text: NSTextView

    init() {
        let scroll = NSTextView.scrollableTextView()
        text = scroll.documentView as! NSTextView
        text.isEditable = false
        text.font = .monospacedSystemFont(ofSize: 11, weight: .regular)
        text.textContainerInset = NSSize(width: 6, height: 6)
        window = NSWindow(contentRect: NSRect(x: 0, y: 0, width: 760, height: 380),
                          styleMask: [.titled, .closable, .resizable, .miniaturizable], backing: .buffered, defer: false)
        window.title = "Cockpit Log"
        window.isReleasedWhenClosed = false
        window.setFrameAutosaveName("ladder.log")
        window.contentView = scroll
    }

    func set(_ s: String) {
        text.string = s
        text.scrollToEndOfDocument(nil)
    }

    func append(_ s: String) {
        let atEnd = text.visibleRect.maxY >= text.bounds.maxY - 20
        text.textStorage?.append(NSAttributedString(string: s, attributes: [
            .font: NSFont.monospacedSystemFont(ofSize: 11, weight: .regular), .foregroundColor: NSColor.textColor]))
        if atEnd { text.scrollToEndOfDocument(nil) }
    }
}
