import AppKit
import SwiftUI

/// A menu item that runs a closure, with an optional refresh for its title, state and enabled flag.
@MainActor
final class Item: NSObject {
    let fn: () -> Void
    let update: ((NSMenuItem) -> Void)?
    init(_ fn: @escaping () -> Void, update: ((NSMenuItem) -> Void)?) { self.fn = fn; self.update = update }
    @objc func run() { fn() }
}

@MainActor
final class AppDelegate: NSObject, NSApplicationDelegate, NSMenuDelegate {
    let cockpit = Cockpit()
    let server = Server()
    let notifier = Notifier()
    var panels: [PanelKind: Panel] = [:]
    var webtiles: Webtiles!
    private let log = LogWindow()
    private var settingsWindow: NSWindow?
    private var status: NSStatusItem!
    private var items: [NSMenuItem] = []          // items with an update closure
    private var decisionMenu = NSMenu(title: "Decision")
    private var activity: NSObjectProtocol?
    private var lastBoot: String?
    private var quitting = false

    // MARK: launch

    func applicationDidFinishLaunching(_ note: Notification) {
        Prefs.register()
        webtiles = Webtiles(app: self)
        for k in PanelKind.allCases { panels[k] = Panel(k, app: self) }
        NSApp.mainMenu = mainMenu()
        setUpStatusItem()
        Alerts.show = { [weak self] text in self?.panels[.control]?.toast(text) }

        log.set(server.log)
        server.onOutput = { [weak self] s in self?.log.append(s) }
        server.onExit = { [weak self] code in
            guard let self else { return }
            if code != 0 && !self.quitting { self.log.window.makeKeyAndOrderFront(nil) }
            if !self.cockpit.up { self.panels.values.forEach { $0.offline() } }
            self.refresh()
        }

        cockpit.onUp = { [weak self] up in self?.connection(up) }
        cockpit.onEvent = { [weak self] e, raw in
            self?.panels.values.forEach { $0.send(raw) }
            if e["ev"] as? String == "game_start" { self?.webtiles.watch() }
        }
        cockpit.onPending = { [weak self] new, old in self?.pendingChanged(new, old) }
        cockpit.onGameEnd = { [weak self] e in self?.gameEnded(e) }
        cockpit.onChange = { [weak self] in self?.refresh() }

        notifier.onAnswer = { [weak self] id, choice in self?.cockpit.decide(choice, id: id) }
        notifier.onOpen = { [weak self] in self?.panels[.call]?.show(); NSApp.activate() }
        notifier.onPlay = { [weak self] in self?.playInWebtiles() }
        notifier.setup()

        restoreWindows()
        cockpit.start()
        if Prefs.startOnLaunch {
            Task {
                try? await Task.sleep(for: .seconds(1.5))
                if !cockpit.up { startCockpit() }
            }
        }
        refresh()
    }

    private func restoreWindows() {
        let firstRun = Prefs.d.object(forKey: "arranged") == nil
        if Prefs.d.object(forKey: "shown.webtiles") as? Bool ?? true { webtiles.window.orderFront(nil) }
        webtiles.showLobbyIfBlank()
        for p in panels.values where Prefs.d.object(forKey: p.shownKey) as? Bool ?? p.kind.shownByDefault {
            p.window.orderFront(nil)
        }
        if firstRun { arrange() }
        webtiles.window.makeKey()
    }

    func applicationShouldHandleReopen(_ sender: NSApplication, hasVisibleWindows flag: Bool) -> Bool {
        if !flag { webtiles.show(); showAllPanels() }
        return true
    }

    func applicationShouldTerminate(_ sender: NSApplication) -> NSApplication.TerminateReply {
        guard server.running else { return .terminateNow }
        // A cockpit we started stops like Ctrl-C, after the current action, with the game saved.
        quitting = true
        server.onExit = { _ in NSApp.reply(toApplicationShouldTerminate: true) }
        server.stop()
        Task {
            try? await Task.sleep(for: .seconds(25))
            NSApp.reply(toApplicationShouldTerminate: true)
        }
        return .terminateLater
    }

    // MARK: the stream

    private func connection(_ up: Bool) {
        guard up else {
            panels.values.forEach { $0.offline() }
            return
        }
        let newBoot = cockpit.boot != lastBoot
        lastBoot = cockpit.boot
        for p in panels.values {
            if newBoot || !p.ready { p.load() } else { Task { if let h = await cockpit.hello() { p.send(h) } } }
        }
        if cockpit.running { webtiles.watch() } else { webtiles.showLobbyIfBlank() }
    }

    private func pendingChanged(_ new: JSON?, _ old: JSON?) {
        if let id = old?["id"] as? String { notifier.clear(decision: id) }
        NSApp.dockTile.badgeLabel = new == nil ? nil : "1"
        guard let new else { return refreshDecisionMenu() }
        let ctx = (new["snapshot"] as? JSON).map { s in
            "\(s["place"] ?? "") · turn \(s["turn"] ?? "") · HP \(s["hp"] ?? "")/\(s["hp_max"] ?? "")"
        } ?? ""
        notifier.decision(new, context: ctx)
        if Prefs.followDecisions, let call = panels[.call] {
            call.window.orderFrontRegardless()
            Prefs.d.set(true, forKey: call.shownKey)
        }
        if !NSApp.isActive { NSApp.requestUserAttention(.informationalRequest) }
        refreshDecisionMenu()
    }

    private func gameEnded(_ e: JSON) {
        guard let by = e["ended_by"] as? String, by == "take_over" || by == "stopped" else { return }
        let place = e["final_place"] as? String ?? "?"
        notifier.handover("Saved at \(place), turn \(e["turns"] ?? "?"). Play it in the webtiles window.")
        panels[.call]?.window.orderFrontRegardless()
    }

    // MARK: actions

    func startCockpit() {
        if cockpit.up { return Alerts.toast("A cockpit is already running on port \(Prefs.port).") }
        do {
            try server.start()
            panels.values.forEach { $0.offline() }
        } catch {
            log.append("Couldn't start: \(error.localizedDescription)\n")
            log.window.makeKeyAndOrderFront(nil)
        }
        refresh()
    }

    func stopCockpit() {
        if server.running { server.stop() } else { cockpit.takeWheel() }
    }

    func playInWebtiles() { webtiles.play() }

    func handBack() { webtiles.handBack() }

    /// Links out of the panels: webtiles ones open in the webtiles window, the rest in the browser.
    func open(_ url: URL) {
        if url.host == webtiles.lobby.host && url.port == webtiles.lobby.port {
            webtiles.load(url)
            webtiles.show()
        } else if url.scheme == "http" || url.scheme == "https" {
            NSWorkspace.shared.open(url)
        }
    }

    func showAllPanels() { panels.values.forEach { $0.show() } }

    /// Webtiles on the left; the shown panels stacked on the right, sized by weight.
    func arrange() {
        guard let screen = (webtiles.window.screen ?? NSScreen.main)?.visibleFrame else { return }
        let gap: CGFloat = 8
        let side = max(340, min(500, screen.width * 0.32))
        webtiles.window.setFrame(NSRect(x: screen.minX + gap, y: screen.minY + gap,
                                        width: screen.width - side - 3 * gap, height: screen.height - 2 * gap),
                                 display: true, animate: true)
        var shown = PanelKind.allCases.filter { panels[$0]!.visible }
        if shown.isEmpty { shown = PanelKind.allCases; showAllPanels() }
        let total = shown.map(\.weight).reduce(0, +)
        let room = screen.height - gap * CGFloat(shown.count + 1)
        var top = screen.maxY - gap
        for k in shown {
            let h = (room * k.weight / total).rounded()
            panels[k]!.window.setFrame(NSRect(x: screen.maxX - side - gap, y: top - h, width: side, height: h),
                                       display: true, animate: true)
            top -= h + gap
        }
        Prefs.d.set(true, forKey: "arranged")
    }

    private func showSettings() {
        if settingsWindow == nil {
            let w = NSWindow(contentViewController: NSHostingController(rootView: SettingsView()))
            w.title = "Ladder Settings"
            w.styleMask = [.titled, .closable]
            w.isReleasedWhenClosed = false
            settingsWindow = w
        }
        settingsWindow?.center()
        settingsWindow?.makeKeyAndOrderFront(nil)
        NSApp.activate()
    }

    // MARK: refreshing

    func refresh() {
        for item in items { (item.representedObject as? Item)?.update?(item) }
        refreshStatusTitle()
        let doing = webtiles.playing ? "playing" : (webtiles.web.url?.fragment?.hasPrefix("watch-") ?? false) ? "watching \(webtiles.user)" : "lobby"
        webtiles.window.subtitle = [doing, cockpit.placeLine].filter { !$0.isEmpty }.joined(separator: " · ")
        let live = cockpit.runState == "running"
        if live, activity == nil {
            activity = ProcessInfo.processInfo.beginActivity(options: [.idleSystemSleepDisabled, .userInitiated],
                                                             reason: "A ladder run is playing")
        } else if !live, let a = activity {
            ProcessInfo.processInfo.endActivity(a)
            activity = nil
        }
    }

    private func refreshStatusTitle() {
        guard let button = status?.button else { return }
        let font = NSFont.monospacedSystemFont(ofSize: 12, weight: .semibold)
        let s = cockpit.snapshot
        let text: String
        var color = NSColor.labelColor
        if cockpit.pending != nil {
            text = "@ your call"
            color = .systemRed
        } else if !cockpit.up {
            text = "* –"
            color = .secondaryLabelColor
        } else if let place = s["place"] as? String, !place.isEmpty {
            let glyph = cockpit.held ? "❚❚" : cockpit.runState == "running" ? "*" : "·"
            text = "\(glyph) \(place) \(s["hp"] ?? "–")/\(s["hp_max"] ?? "–")"
        } else {
            text = "* \(cockpit.runState)"
        }
        button.attributedTitle = NSAttributedString(string: text, attributes: [.font: font, .foregroundColor: color])
        button.toolTip = "Ladder · \(cockpit.runState)" + (cockpit.placeLine.isEmpty ? "" : " · " + cockpit.placeLine)
    }

    private func refreshDecisionMenu() {
        let m = decisionMenu
        m.removeAllItems()
        guard let p = cockpit.pending else {
            m.addItem(disabled("Nothing is waiting on you"))
            return
        }
        m.addItem(disabled((p["question"] as? String) ?? "Decision"))
        m.addItem(.separator())
        for (i, o) in cockpit.choices.enumerated() {
            let key = o["key"] as? String ?? ""
            let rec = key == p["recommended"] as? String
            m.addItem(item("\(o["label"] ?? key)" + (rec ? "  ✦" : ""), key: i < 9 ? "\(i + 1)" : "") { [weak self] in
                self?.cockpit.decide(key)
            })
        }
        m.addItem(.separator())
        for o in cockpit.exits {
            let key = o["key"] as? String ?? ""
            m.addItem(item("\(o["label"] ?? key)") { [weak self] in self?.cockpit.decide(key) })
        }
    }

    // MARK: menus

    private func item(_ title: String, key: String = "", mods: NSEvent.ModifierFlags = .command,
                      update: ((NSMenuItem) -> Void)? = nil, _ fn: @escaping () -> Void) -> NSMenuItem {
        let target = Item(fn, update: update)
        let mi = NSMenuItem(title: title, action: #selector(Item.run), keyEquivalent: key)
        mi.keyEquivalentModifierMask = mods
        mi.target = target
        mi.representedObject = target
        if update != nil { items.append(mi) }
        return mi
    }

    private func disabled(_ title: String) -> NSMenuItem {
        let mi = NSMenuItem(title: title, action: nil, keyEquivalent: "")
        mi.isEnabled = false
        return mi
    }

    private func menu(_ title: String, _ list: [NSMenuItem]) -> NSMenuItem {
        let m = NSMenu(title: title)
        m.autoenablesItems = false
        list.forEach(m.addItem)
        let top = NSMenuItem(title: title, action: nil, keyEquivalent: "")
        top.submenu = m
        return top
    }

    private func sel(_ title: String, _ action: Selector, _ key: String, mods: NSEvent.ModifierFlags = .command) -> NSMenuItem {
        let mi = NSMenuItem(title: title, action: action, keyEquivalent: key)
        mi.keyEquivalentModifierMask = mods
        return mi
    }

    private var up: (NSMenuItem) -> Void { { [weak self] in $0.isEnabled = self?.cockpit.up ?? false } }

    private func mainMenu() -> NSMenu {
        let main = NSMenu()

        let appMenu = NSMenu()
        appMenu.addItem(withTitle: "About Ladder", action: #selector(NSApplication.orderFrontStandardAboutPanel(_:)), keyEquivalent: "")
        appMenu.addItem(.separator())
        appMenu.addItem(item("Settings…", key: ",") { [weak self] in self?.showSettings() })
        appMenu.addItem(.separator())
        appMenu.addItem(sel("Hide Ladder", #selector(NSApplication.hide(_:)), "h"))
        appMenu.addItem(sel("Hide Others", #selector(NSApplication.hideOtherApplications(_:)), "h", mods: [.command, .option]))
        appMenu.addItem(sel("Show All", #selector(NSApplication.unhideAllApplications(_:)), ""))
        appMenu.addItem(.separator())
        appMenu.addItem(sel("Quit Ladder", #selector(NSApplication.terminate(_:)), "q"))
        let appItem = NSMenuItem()
        appItem.submenu = appMenu
        main.addItem(appItem)

        let edit = NSMenu(title: "Edit")
        edit.addItem(sel("Undo", Selector(("undo:")), "z"))
        edit.addItem(sel("Redo", Selector(("redo:")), "z", mods: [.command, .shift]))
        edit.addItem(.separator())
        edit.addItem(sel("Cut", #selector(NSText.cut(_:)), "x"))
        edit.addItem(sel("Copy", #selector(NSText.copy(_:)), "c"))
        edit.addItem(sel("Paste", #selector(NSText.paste(_:)), "v"))
        edit.addItem(sel("Select All", #selector(NSText.selectAll(_:)), "a"))
        let editItem = NSMenuItem(title: "Edit", action: nil, keyEquivalent: "")
        editItem.submenu = edit
        main.addItem(editItem)

        let speeds = NSMenu(title: "Pause Between Actions")
        speeds.autoenablesItems = false
        for d in Cockpit.speeds {
            speeds.addItem(item(d == 0 ? "Full Speed" : "\(d.formatted()) s", update: { [weak self] mi in
                mi.isEnabled = self?.cockpit.up ?? false
                mi.state = abs((self?.cockpit.delay ?? -1) - d) < 0.001 ? .on : .off
            }) { [weak self] in self?.cockpit.setDelay(d) })
        }
        let speedItem = NSMenuItem(title: "Pause Between Actions", action: nil, keyEquivalent: "")
        speedItem.submenu = speeds

        main.addItem(menu("Cockpit", [
            item("Start Cockpit", key: "r", update: { [weak self] in
                $0.isEnabled = !(self?.cockpit.up ?? true) && !(self?.server.running ?? true)
            }) { [weak self] in self?.startCockpit() },
            item("Stop Cockpit (Game Stays Saved)", key: "r", mods: [.command, .shift], update: { [weak self] in
                $0.isEnabled = self?.server.running ?? false
            }) { [weak self] in self?.stopCockpit() },
            item("Cockpit Log", key: "l") { [weak self] in self?.log.window.makeKeyAndOrderFront(nil) },
            .separator(),
            item("Hold at Next Event", key: ".", update: { [weak self] mi in
                guard let c = self?.cockpit else { return }
                mi.isEnabled = c.running
                mi.title = c.held ? (c.paused ? "Resume" : "Resume (Will Hold)") : "Hold at Next Event"
            }) { [weak self] in self?.cockpit.toggleHold() },
            item("Step One Action", key: "'", update: { [weak self] in $0.isEnabled = self?.cockpit.running ?? false }) { [weak self] in
                self?.cockpit.step()
            },
            item("Slower", key: "[", update: up) { [weak self] in self?.cockpit.slower() },
            item("Faster", key: "]", update: up) { [weak self] in self?.cockpit.faster() },
            speedItem,
            .separator(),
            item("Assisted", update: { [weak self] mi in
                mi.isEnabled = self?.cockpit.up ?? false
                mi.state = self?.cockpit.mode == "assisted" ? .on : .off
            }) { [weak self] in self?.cockpit.setMode("assisted") },
            item("Autonomous", update: { [weak self] mi in
                mi.isEnabled = self?.cockpit.up ?? false
                mi.state = self?.cockpit.mode == "autonomous" ? .on : .off
            }) { [weak self] in self?.cockpit.setMode("autonomous") },
            .separator(),
            item("Take the Wheel", key: "t", mods: [.command, .shift], update: { [weak self] in
                $0.isEnabled = self?.cockpit.up ?? false
                $0.title = self?.cockpit.running ?? true ? "Take the Wheel" : "Play in Webtiles"
            }) { [weak self] in self?.playInWebtiles() },
            item("Hand Back to the Bot", key: "b", mods: [.command, .shift], update: { [weak self] in
                $0.isEnabled = (self?.cockpit.up ?? false) && !(self?.cockpit.running ?? true)
            }) { [weak self] in self?.handBack() },
        ]))

        decisionMenu.autoenablesItems = false
        let decisionItem = NSMenuItem(title: "Decision", action: nil, keyEquivalent: "")
        decisionItem.submenu = decisionMenu
        main.addItem(decisionItem)
        refreshDecisionMenu()

        main.addItem(menu("View", [
            item("Zoom In", key: "=") { [weak self] in self?.webtiles.zoom(1.1) },
            item("Zoom Out", key: "-") { [weak self] in self?.webtiles.zoom(1 / 1.1) },
            item("Actual Size", key: "0") { [weak self] in self?.webtiles.zoom(nil) },
            .separator(),
            item("Reload Panels", key: "r", mods: [.command, .option]) { [weak self] in
                guard let self else { return }
                self.panels.values.forEach { self.cockpit.up ? $0.load() : $0.offline() }
            },
            item("Reload Webtiles", key: "r", mods: [.command, .option, .shift]) { [weak self] in self?.webtiles.web.reload() },
        ]))

        let floats = NSMenu(title: "Float on Top")
        floats.autoenablesItems = false
        let alphas = NSMenu(title: "Panel Opacity")
        alphas.autoenablesItems = false
        for a in [1.0, 0.92, 0.85, 0.75, 0.6] {
            alphas.addItem(item("\(Int(a * 100))%", update: { [weak self] in
                $0.state = abs((self?.panels[.control]?.alpha ?? 1) - a) < 0.001 ? .on : .off
            }) { [weak self] in self?.panels.values.forEach { $0.alpha = a }; self?.refresh() })
        }
        var windowItems: [NSMenuItem] = [
            sel("Minimize", #selector(NSWindow.performMiniaturize(_:)), "m"),
            sel("Zoom", #selector(NSWindow.performZoom(_:)), ""),
            .separator(),
            item("Webtiles", key: "0", mods: [.command, .option], update: { [weak self] in
                $0.state = self?.webtiles.window.isVisible ?? false ? .on : .off
            }) { [weak self] in self?.webtiles.show() },
        ]
        for (i, k) in PanelKind.allCases.enumerated() {
            windowItems.append(item(k.title, key: "\(i + 1)", mods: [.command, .option], update: { [weak self] in
                $0.state = self?.panels[k]?.visible ?? false ? .on : .off
            }) { [weak self] in
                guard let p = self?.panels[k] else { return }
                p.visible ? p.hide() : p.show()
                self?.refresh()
            })
            floats.addItem(item(k.title, update: { [weak self] in
                $0.state = self?.panels[k]?.floats ?? false ? .on : .off
            }) { [weak self] in
                guard let p = self?.panels[k] else { return }
                p.floats.toggle()
                self?.refresh()
            })
        }
        let floatItem = NSMenuItem(title: "Float on Top", action: nil, keyEquivalent: "")
        floatItem.submenu = floats
        let alphaItem = NSMenuItem(title: "Panel Opacity", action: nil, keyEquivalent: "")
        alphaItem.submenu = alphas
        windowItems += [
            .separator(),
            floatItem,
            alphaItem,
            .separator(),
            item("Arrange Around Webtiles", key: "a", mods: [.command, .option]) { [weak self] in self?.arrange() },
            item("Show All Panels") { [weak self] in self?.showAllPanels(); self?.refresh() },
            item("Hide All Panels") { [weak self] in self?.panels.values.forEach { $0.hide() }; self?.refresh() },
            .separator(),
            sel("Bring All to Front", #selector(NSApplication.arrangeInFront(_:)), ""),
        ]
        let window = menu("Window", windowItems)
        NSApp.windowsMenu = window.submenu
        main.addItem(window)
        return main
    }

    // MARK: menu bar

    private func setUpStatusItem() {
        status = NSStatusBar.system.statusItem(withLength: NSStatusItem.variableLength)
        let m = NSMenu()
        m.delegate = self
        m.autoenablesItems = false
        status.menu = m
        refreshStatusTitle()
    }

    func menuNeedsUpdate(_ m: NSMenu) {
        guard m === status.menu else { return }
        m.removeAllItems()
        m.addItem(disabled("Cockpit: \(cockpit.runState)" + (cockpit.placeLine.isEmpty ? "" : " · " + cockpit.placeLine)))
        if let p = cockpit.pending {
            m.addItem(.separator())
            m.addItem(disabled((p["question"] as? String) ?? "Decision"))
            for (i, o) in (cockpit.choices + cockpit.exits).enumerated() {
                let key = o["key"] as? String ?? ""
                let n = i < cockpit.choices.count ? "\(i + 1)  " : "    "
                m.addItem(item(n + "\(o["label"] ?? key)") { [weak self] in self?.cockpit.decide(key) })
            }
        }
        m.addItem(.separator())
        let c = cockpit
        let hold = item(c.held ? "Resume" : "Hold at Next Event") { [weak self] in self?.cockpit.toggleHold() }
        hold.isEnabled = c.running
        m.addItem(hold)
        let step = item("Step One Action") { [weak self] in self?.cockpit.step() }
        step.isEnabled = c.running
        m.addItem(step)
        if c.running || !c.up {
            let wheel = item("Take the Wheel") { [weak self] in self?.playInWebtiles() }
            wheel.isEnabled = c.up
            m.addItem(wheel)
        } else {
            m.addItem(item("Hand Back to the Bot") { [weak self] in self?.handBack() })
            m.addItem(item("Play in Webtiles") { [weak self] in self?.playInWebtiles() })
        }
        m.addItem(.separator())
        m.addItem(item("Show Webtiles") { [weak self] in self?.webtiles.show() })
        m.addItem(item("Show All Panels") { [weak self] in self?.showAllPanels(); NSApp.activate() })
        m.addItem(item("Arrange Around Webtiles") { [weak self] in self?.arrange() })
        m.addItem(.separator())
        if server.running {
            m.addItem(item("Stop Cockpit (Game Stays Saved)") { [weak self] in self?.stopCockpit() })
        } else {
            let start = item("Start Cockpit") { [weak self] in self?.startCockpit() }
            start.isEnabled = !c.up
            m.addItem(start)
        }
        m.addItem(sel("Quit Ladder", #selector(NSApplication.terminate(_:)), ""))
    }
}

struct SettingsView: View {
    @AppStorage("repo") private var repo = Prefs.builtRepo
    @AppStorage("port") private var port = 8090
    @AppStorage("cockpitArgs") private var args = "--idle-minutes 10 --jev"
    @AppStorage("startOnLaunch") private var startOnLaunch = false
    @AppStorage("notify") private var notify = true
    @AppStorage("followDecisions") private var follow = true

    var body: some View {
        Form {
            Section("Cockpit") {
                TextField("Repository", text: $repo)
                TextField("Port", value: $port, format: .number.grouping(.never))
                TextField("Options", text: $args)
                Text("Start Cockpit runs `ladder cockpit --port \(String(port)) \(args)` in the repository. A cockpit you start in a terminal works too: Ladder connects to whatever answers on the port.")
                    .font(.caption).foregroundStyle(.secondary)
                Toggle("Start the cockpit when Ladder opens, if none is running", isOn: $startOnLaunch)
            }
            Section("Decisions") {
                Toggle("Bring “Your Call” to the front when a decision waits", isOn: $follow)
                Toggle("Notify me (answer from the banner) when Ladder isn't in front", isOn: $notify)
            }
        }
        .formStyle(.grouped)
        .frame(width: 520)
        .fixedSize(horizontal: false, vertical: true)
    }
}
