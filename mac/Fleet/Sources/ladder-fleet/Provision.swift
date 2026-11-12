import FleetCore
import Foundation

/// Gets a run host ready to play: uv, a Docker that works, the DCSS image and its own DCSS server,
/// and the code a batch needs. Everything goes in the fleet's folder; nothing needs sudo.
actor Provisioner {
    let home: FleetHome
    let log: @Sendable (String) -> Void
    private(set) var readiness = Readiness()
    private var ownColima = false
    static let colimaProfile = "ladder-fleet"
    static let container = "ladder-fleet-dcss"

    init(home: FleetHome, log: @escaping @Sendable (String) -> Void) {
        self.home = home
        self.log = log
        let lima = home.dir("tools/lima/bin").path
        Shell.extraPath = [home.bin.path, lima]
    }

    var checkout: URL { home.dir("checkout") }
    var arch: String { HostProbe.info().arch }           // arm64 or x86_64

    // MARK: uv

    func ensureUV() async throws {
        if readiness.uv != nil { return }
        if Shell.which("uv") == nil {
            log("installing uv")
            let triple = arch == "arm64" ? "aarch64-apple-darwin" : "x86_64-apple-darwin"
            let tgz = try await download("https://github.com/astral-sh/uv/releases/latest/download/uv-\(triple).tar.gz")
            let tmp = home.dir("tmp/uv")
            try await Shell.check("tar", ["-xzf", tgz.path, "-C", tmp.path])
            for tool in ["uv", "uvx"] {
                let dst = home.bin.appendingPathComponent(tool)
                try? FileManager.default.removeItem(at: dst)
                try FileManager.default.moveItem(at: tmp.appendingPathComponent("uv-\(triple)/\(tool)"), to: dst)
            }
            try? FileManager.default.removeItem(at: tmp)
        }
        readiness.uv = try await Shell.check("uv", ["--version"])
    }

    // MARK: docker

    /// A Docker that answers: the one this Mac already has, or a colima VM of our own sized for `cpus`.
    func ensureDocker(cpus: Int, memoryGB: Int) async throws {
        if readiness.docker != nil, (try? await dockerCPUs()) != nil { return }
        if !ownColima, Shell.which("docker") != nil, let n = try? await dockerCPUs() {
            readiness.docker = "existing"
            readiness.dockerCPUs = n
            log("using this Mac's Docker (\(n) CPUs)")
            return
        }
        try await installColima()
        let sock = FileManager.default.homeDirectoryForCurrentUser.appendingPathComponent(".colima/\(Self.colimaProfile)/docker.sock").path
        Shell.extraEnv["DOCKER_HOST"] = "unix://\(sock)"
        ownColima = true
        if (try? await dockerCPUs()) == nil {
            log("starting a colima VM (\(cpus) CPUs, \(memoryGB) GB); the first start downloads its disk image")
            try await Shell.check("colima", ["start", "--profile", Self.colimaProfile, "--cpu", "\(cpus)", "--memory", "\(memoryGB)",
                                             "--disk", "60", "--vm-type", "vz", "--runtime", "docker"],
                                  onLine: { [log] l in if l.contains("msg=") { log("colima: \(l)") } })
        }
        readiness.dockerCPUs = try await dockerCPUs()
        readiness.docker = "colima (\(Self.colimaProfile))"
    }

    func dockerCPUs() async throws -> Int {
        let out = try await Shell.check("docker", ["info", "--format", "{{.NCPU}}"])
        guard let n = Int(out) else { throw FleetError.failed("docker info: \(out)") }
        return n
    }

    private func installColima() async throws {
        let a = arch
        if Shell.which("docker") == nil {
            log("installing the docker CLI")
            let base = "https://download.docker.com/mac/static/stable/\(a == "arm64" ? "aarch64" : "x86_64")/"
            let listing = String(decoding: try await fetch(base), as: UTF8.self)
            let versions = listing.matches(of: #/docker-(\d+)\.(\d+)\.(\d+)\.tgz/#).map { m in
                (Int(m.1)!, Int(m.2)!, Int(m.3)!, String(m.0))
            }
            guard let newest = versions.max(by: { ($0.0, $0.1, $0.2) < ($1.0, $1.1, $1.2) }) else {
                throw FleetError.failed("no docker CLI listed at \(base)")
            }
            let tgz = try await download(base + newest.3)
            let tmp = home.dir("tmp/docker")
            try await Shell.check("tar", ["-xzf", tgz.path, "-C", tmp.path])
            try place(tmp.appendingPathComponent("docker/docker"), as: "docker")
            try? FileManager.default.removeItem(at: tmp)
        }
        if Shell.which("limactl") == nil {
            log("installing lima")
            let release = try JSONValue.parse(try await fetch("https://api.github.com/repos/lima-vm/lima/releases/latest"))
            let want = "-Darwin-\(a).tar.gz"
            guard let url = release["assets"]?.array?.compactMap({ $0["browser_download_url"]?.string })
                .first(where: { $0.hasSuffix(want) && !$0.contains("guestagents") }) else {
                throw FleetError.failed("no lima release for Darwin-\(a)")
            }
            let tgz = try await download(url)
            try await Shell.check("tar", ["-xzf", tgz.path, "-C", home.dir("tools/lima").path])
        }
        if Shell.which("colima") == nil {
            log("installing colima")
            let bin = try await download("https://github.com/abiosoft/colima/releases/latest/download/colima-Darwin-\(a)")
            try place(bin, as: "colima")
        }
    }

    private func place(_ file: URL, as name: String) throws {
        let dst = home.bin.appendingPathComponent(name)
        try? FileManager.default.removeItem(at: dst)
        try FileManager.default.moveItem(at: file, to: dst)
        try FileManager.default.setAttributes([.posixPermissions: 0o755], ofItemAtPath: dst.path)
    }

    // MARK: the DCSS image and server

    /// Have image `id` (fetching it from the server if needed) and our DCSS server running it.
    func ensureImage(_ id: String, fetch: @Sendable () async throws -> URL) async throws {
        let have = try? await Shell.check("docker", ["image", "inspect", dcssImageTag, "--format", "{{.Id}}"])
        if have != id {
            log("fetching the DCSS image from the server")
            let file = try await fetch()
            log("loading the DCSS image")
            try await Shell.check("docker", ["load", "-i", file.path])
            try? FileManager.default.removeItem(at: file)
            let now = try await Shell.check("docker", ["image", "inspect", dcssImageTag, "--format", "{{.Id}}"])
            guard now == id else { throw FleetError.failed("loaded image is \(now), wanted \(id)") }
        }
        readiness.imageId = id
        try await ensureDCSS(id)
    }

    func ensureDCSS(_ imageId: String) async throws {
        let running = try? await Shell.check("docker", ["inspect", Self.container, "--format", "{{.Image}} {{.State.Running}}"])
        if running != "\(imageId) true" {
            log("starting DCSS on port \(agentDCSSPort)")
            _ = try? await Shell.run("docker", ["rm", "-f", Self.container])
            try await Shell.check("docker", ["run", "-d", "--name", Self.container, "--restart", "unless-stopped",
                                             "-p", "127.0.0.1:\(agentDCSSPort):8080", "-v", "\(Self.container):/data", dcssImageTag])
        }
        for _ in 0..<60 {
            if let (_, r) = try? await URLSession.shared.data(from: URL(string: "http://127.0.0.1:\(agentDCSSPort)/")!),
               (r as? HTTPURLResponse)?.statusCode == 200 {
                readiness.dcss = true
                return
            }
            try await Task.sleep(nanoseconds: 1_000_000_000)
        }
        readiness.dcss = false
        throw FleetError.failed("DCSS didn't answer on port \(agentDCSSPort)")
    }

    // MARK: the code

    /// The checkout holds bundle `id`, with its Python environment synced.
    func ensureBundle(_ id: String, fetch: @Sendable () async throws -> URL) async throws -> URL {
        let marker = checkout.appendingPathComponent(".fleet-bundle")
        if (try? String(contentsOf: marker, encoding: .utf8)) == id { return checkout }
        let file = try await fetch()
        log("unpacking code \(id)")
        let keep: Set<String> = [".venv"]
        for item in (try? FileManager.default.contentsOfDirectory(atPath: checkout.path)) ?? [] where !keep.contains(item) {
            try FileManager.default.removeItem(at: checkout.appendingPathComponent(item))
        }
        try await Shell.check("tar", ["-xzf", file.path, "-C", checkout.path])
        try? FileManager.default.removeItem(at: file)
        log("uv sync (the first one downloads Python 3.12 and the packages)")
        try await Shell.check("uv", ["sync", "--frozen", "--no-dev"], cwd: checkout)
        try id.write(to: marker, atomically: true, encoding: .utf8)
        readiness.bundleId = id
        return checkout
    }

    // MARK: downloads

    private func fetch(_ url: String) async throws -> Data {
        var req = URLRequest(url: URL(string: url)!)
        req.setValue("ladder-fleet", forHTTPHeaderField: "User-Agent")
        let (data, resp) = try await URLSession.shared.data(for: req)
        guard (resp as? HTTPURLResponse)?.statusCode == 200 else { throw FleetError.failed("GET \(url): \(resp)") }
        return data
    }

    private func download(_ url: String) async throws -> URL {
        var req = URLRequest(url: URL(string: url)!)
        req.setValue("ladder-fleet", forHTTPHeaderField: "User-Agent")
        let (tmp, resp) = try await URLSession.shared.download(for: req)
        guard (resp as? HTTPURLResponse)?.statusCode == 200 else { throw FleetError.failed("GET \(url): \(resp)") }
        let dst = home.dir("tmp").appendingPathComponent(URL(string: url)!.lastPathComponent)
        try? FileManager.default.removeItem(at: dst)
        try FileManager.default.moveItem(at: tmp, to: dst)
        return dst
    }
}
