import AppKit
import WebKit

/// The webtiles window: spectates the bot while a run plays, and plays when you take the wheel.
@MainActor
final class Webtiles: NSObject, WKNavigationDelegate, WKUIDelegate, NSWindowDelegate {
    let window: NSWindow
    let web: WKWebView
    private unowned let app: AppDelegate

    init(app: AppDelegate) {
        self.app = app
        window = NSWindow(contentRect: NSRect(x: 0, y: 0, width: 1100, height: 760),
                          styleMask: [.titled, .closable, .miniaturizable, .resizable],
                          backing: .buffered, defer: false)
        let config = WKWebViewConfiguration()
        config.websiteDataStore = .default()
        web = WKWebView(frame: .zero, configuration: config)
        super.init()
        window.title = "Webtiles"
        window.isReleasedWhenClosed = false
        window.tabbingMode = .disallowed
        window.setFrameAutosaveName("ladder.webtiles")
        window.delegate = self
        window.contentView = web
        web.navigationDelegate = self
        web.uiDelegate = self
        web.allowsMagnification = true
        web.pageZoom = CGFloat(Prefs.d.object(forKey: "webtiles.zoom") as? Double ?? 1)
    }

    var lobby: URL { URL(string: app.cockpit.links["lobby"] as? String ?? Prefs.webtiles)! }
    var user: String { app.cockpit.links["user"] as? String ?? "ladderbot" }
    var watchURL: URL? { (app.cockpit.links["webtiles"] as? String).flatMap(URL.init(string:)) }
    var playURL: URL? { (app.cockpit.links["play"] as? String).flatMap(URL.init(string:)) }
    /// The cockpit's recording proxy: Play lands here, so your keys are recorded with the game.
    var proxyURL: URL? { (app.cockpit.links["proxy"] as? String).flatMap(URL.init(string:)) }

    /// In a game of its own (not spectating or in the lobby).
    var playing: Bool { web.url?.fragment?.hasPrefix("play-") ?? false }

    func load(_ url: URL) {
        web.load(URLRequest(url: url))
    }

    func watch() {
        guard let url = watchURL, !playing else { return }
        if web.url != url { load(url) }
    }

    func showLobbyIfBlank() {
        if web.url == nil { load(watchURL ?? lobby) }
    }

    func show() {
        window.makeKeyAndOrderFront(nil)
        NSApp.activate()
        Prefs.d.set(true, forKey: "shown.webtiles")
    }

    /// Take the wheel: the cockpit stops the bot, waits for the save, and answers with webtiles' login
    /// cookie for the bot and a redirect to Play. No password passes through here.
    func play() {
        guard let url = playURL else {
            return Alerts.toast("Playing from the cockpit needs webtiles on localhost; log in by hand.")
        }
        show()
        var req = URLRequest(url: url)
        req.httpMethod = "POST"
        web.load(req)
    }

    /// Hand back: leaving the game saves it (webtiles hangs up on it), and the cockpit starts a run that
    /// resumes the save. `watch()` follows the bot again at its game_start.
    func handBack() {
        if playing { load(lobby) }
        app.cockpit.act("api/resume")
    }

    func zoom(_ by: Double?) {
        let z = by.map { min(3, max(0.4, Double(web.pageZoom) * $0)) } ?? 1
        web.pageZoom = CGFloat(z)
        Prefs.d.set(z, forKey: "webtiles.zoom")
    }

    // MARK: WebKit

    func webView(_ webView: WKWebView, decidePolicyFor action: WKNavigationAction,
                 decisionHandler: @escaping @MainActor (WKNavigationActionPolicy) -> Void) {
        guard let url = action.request.url else { return decisionHandler(.cancel) }
        let ours = [lobby, proxyURL].compactMap { $0 }.contains { url.host == $0.host && url.port == $0.port }
        if ours || url.scheme == "about" || url == playURL {
            return decisionHandler(.allow)
        }
        decisionHandler(.cancel)
        NSWorkspace.shared.open(url)
    }

    func webView(_ webView: WKWebView, createWebViewWith configuration: WKWebViewConfiguration,
                 for action: WKNavigationAction, windowFeatures: WKWindowFeatures) -> WKWebView? {
        if let url = action.request.url { app.open(url) }
        return nil
    }

    func webViewWebContentProcessDidTerminate(_ webView: WKWebView) {
        webView.reload()
    }

    // webtiles' own alerts and confirmations (WebKit drops them without these)
    func webView(_ webView: WKWebView, runJavaScriptAlertPanelWithMessage message: String,
                 initiatedByFrame frame: WKFrameInfo, completionHandler: @escaping @MainActor () -> Void) {
        let alert = NSAlert()
        alert.messageText = message
        alert.beginSheetModal(for: window) { _ in completionHandler() }
    }

    func webView(_ webView: WKWebView, runJavaScriptConfirmPanelWithMessage message: String,
                 initiatedByFrame frame: WKFrameInfo, completionHandler: @escaping @MainActor (Bool) -> Void) {
        let alert = NSAlert()
        alert.messageText = message
        alert.addButton(withTitle: "OK")
        alert.addButton(withTitle: "Cancel")
        alert.beginSheetModal(for: window) { completionHandler($0 == .alertFirstButtonReturn) }
    }

    func windowWillClose(_ notification: Notification) {
        Prefs.d.set(false, forKey: "shown.webtiles")
    }
}
