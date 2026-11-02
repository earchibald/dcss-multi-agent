import AppKit
import WebKit

/// The webtiles window: spectates the bot while a run plays, and signs in and plays when the
/// cockpit hands the game over.
@MainActor
final class Webtiles: NSObject, WKNavigationDelegate, WKUIDelegate, NSWindowDelegate {
    let window: NSWindow
    let web: WKWebView
    private unowned let app: AppDelegate
    private var afterLoad: (() -> Void)?

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

    /// In a game of its own (not spectating or in the lobby).
    var playing: Bool { web.url?.fragment?.hasPrefix("play-") ?? false }

    func load(_ url: URL) {
        afterLoad = nil
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

    /// The cockpit left the game saved: sign in as the bot with the Keychain password and press Play.
    func signInAndPlay() {
        let user = self.user
        show()
        Task.detached {
            let password = Keychain.password(service: "dcss-ladder", account: "dcss-account/\(user)")
            await MainActor.run {
                guard let password else {
                    return Alerts.toast("No Keychain password for \(user) (service dcss-ladder, account dcss-account/\(user)).")
                }
                // a query, not just the fragment, so it's a full load that ends in didFinish
                self.web.load(URLRequest(url: self.lobby.appending(queryItems: [URLQueryItem(name: "from", value: "ladder")])))
                self.afterLoad = {
                    self.web.evaluateJavaScript(Self.signInScript(user: user, password: password))
                }
            }
        }
    }

    /// Fill the lobby's login form once it shows, then follow the first Play link.
    private static func signInScript(user: String, password: String) -> String {
        """
        (function (user, pass) {
          let tries = 0;
          const shown = (el) => el && el.offsetParent !== null;
          const t = setInterval(() => {
            if (++tries > 120) return clearInterval(t);
            const play = document.querySelector('a[href^="#play-"]');
            if (shown(document.getElementById("logout_link")) && play) {
              clearInterval(t);
              play.click();
              return;
            }
            const form = document.getElementById("login_form");
            if (shown(form) && !form.dataset.ladder) {
              form.dataset.ladder = "1";
              document.getElementById("username").value = user;
              document.getElementById("password").value = pass;
              form.requestSubmit();
            }
          }, 250);
        })(\(jsString(user)), \(jsString(password)));
        """
    }

    func zoom(_ by: Double?) {
        let z = by.map { min(3, max(0.4, Double(web.pageZoom) * $0)) } ?? 1
        web.pageZoom = CGFloat(z)
        Prefs.d.set(z, forKey: "webtiles.zoom")
    }

    // MARK: WebKit

    func webView(_ webView: WKWebView, didFinish navigation: WKNavigation!) {
        let run = afterLoad
        afterLoad = nil
        run?()
    }

    func webView(_ webView: WKWebView, decidePolicyFor action: WKNavigationAction,
                 decisionHandler: @escaping @MainActor (WKNavigationActionPolicy) -> Void) {
        guard let url = action.request.url else { return decisionHandler(.cancel) }
        if url.host == lobby.host && url.port == lobby.port || url.scheme == "about" {
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
