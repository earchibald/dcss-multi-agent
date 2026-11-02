import AppKit
import WebKit

enum PanelKind: String, CaseIterable {
    case call, control, game, stream, decisions, claude

    var title: String {
        switch self {
        case .call: "Your Call"
        case .control: "Control"
        case .game: "Game"
        case .stream: "Escalation Stream"
        case .decisions: "Decisions"
        case .claude: "Claude Code"
        }
    }

    /// Share of the side column's height in Arrange.
    var weight: CGFloat {
        switch self {
        case .call: 1.0
        case .control: 2.0
        case .game: 1.5
        case .stream: 2.6
        case .decisions: 1.0
        case .claude: 0.8
        }
    }

    var floatsByDefault: Bool { self == .call || self == .control }
    var shownByDefault: Bool { self != .decisions && self != .claude }
}

/// Clicks land on the first click, even in a window that isn't key.
final class LadderWebView: WKWebView {
    override func acceptsFirstMouse(for event: NSEvent?) -> Bool { true }
}

/// A floating window holding one cockpit panel (`/?panel=<kind>&app`).
///
/// It's a non-activating panel that becomes key only when a text field asks: clicking Hold or
/// an answer leaves the keyboard with whatever had it, the webtiles game or another app.
@MainActor
final class Panel: NSObject, WKScriptMessageHandler, WKNavigationDelegate, WKUIDelegate, NSWindowDelegate {
    let kind: PanelKind
    let window: NSPanel
    let web: LadderWebView
    private unowned let app: AppDelegate
    private(set) var ready = false

    init(_ kind: PanelKind, app: AppDelegate) {
        self.kind = kind
        self.app = app
        window = NSPanel(contentRect: NSRect(x: 0, y: 0, width: 420, height: 300),
                         styleMask: [.titled, .closable, .resizable, .utilityWindow, .nonactivatingPanel],
                         backing: .buffered, defer: false)
        let config = WKWebViewConfiguration()
        config.websiteDataStore = .default()
        web = LadderWebView(frame: .zero, configuration: config)
        super.init()
        config.userContentController.add(self, name: "ladder")

        window.title = kind.title
        window.isReleasedWhenClosed = false
        window.hidesOnDeactivate = false
        window.becomesKeyOnlyIfNeeded = true
        window.collectionBehavior = [.fullScreenAuxiliary, .moveToActiveSpace]
        window.minSize = NSSize(width: 260, height: 120)
        window.delegate = self
        window.setFrameAutosaveName("ladder.panel.\(kind.rawValue)")
        let floats = Prefs.d.object(forKey: floatKey) as? Bool ?? kind.floatsByDefault
        window.level = floats ? .floating : .normal
        window.alphaValue = CGFloat(Prefs.d.object(forKey: alphaKey) as? Double ?? 1)

        let material = NSVisualEffectView()
        material.material = .sidebar
        material.blendingMode = .behindWindow
        material.state = .active
        window.contentView = material
        web.setValue(false, forKey: "drawsBackground")
        web.navigationDelegate = self
        web.uiDelegate = self
        web.frame = material.bounds
        web.autoresizingMask = [.width, .height]
        material.addSubview(web)
        offline()
    }

    private var floatKey: String { "float.\(kind.rawValue)" }
    private var alphaKey: String { "alpha.\(kind.rawValue)" }
    var shownKey: String { "shown.\(kind.rawValue)" }

    var floats: Bool {
        get { window.level == .floating }
        set { window.level = newValue ? .floating : .normal; Prefs.d.set(newValue, forKey: floatKey) }
    }

    var alpha: Double {
        get { Double(window.alphaValue) }
        set { window.alphaValue = CGFloat(newValue); Prefs.d.set(newValue, forKey: alphaKey) }
    }

    // MARK: loading

    func load() {
        ready = false
        var url = URLComponents(url: app.cockpit.base, resolvingAgainstBaseURL: false)!
        url.queryItems = [URLQueryItem(name: "panel", value: kind.rawValue), URLQueryItem(name: "app", value: nil)]
        web.load(URLRequest(url: url.url!))
    }

    /// Shown while nothing answers on the cockpit port.
    func offline() {
        ready = false
        web.loadHTMLString(Self.offlinePage(port: app.cockpit.port, managed: app.server.running), baseURL: nil)
    }

    func send(_ raw: String) {
        guard ready else { return }
        web.evaluateJavaScript("window.ladder && ladder.event(\(raw))")
    }

    func down() {
        guard ready else { return }
        web.evaluateJavaScript("window.ladder && ladder.down()")
    }

    func toast(_ text: String) {
        guard ready else { return }
        web.evaluateJavaScript("typeof toast === 'function' && toast(\(jsString(text)))")
    }

    func show() {
        window.orderFront(nil)
        Prefs.d.set(true, forKey: shownKey)
    }

    func hide() {
        window.orderOut(nil)
        Prefs.d.set(false, forKey: shownKey)
    }

    var visible: Bool { window.isVisible }

    /// Grow or shrink to the page's height, keeping the top edge where it is.
    private func fit(_ content: CGFloat) {
        guard let screen = window.screen?.visibleFrame else { return }
        var f = window.frame
        let chrome = f.height - window.contentLayoutRect.height
        let h = min(max(content + chrome, 90), screen.height * 0.7)
        guard abs(h - f.height) > 2 else { return }
        f.origin.y += f.height - h
        f.size.height = h
        if f.minY < screen.minY { f.origin.y = screen.minY }
        window.setFrame(f, display: true, animate: true)
    }

    // MARK: WebKit

    func userContentController(_ c: WKUserContentController, didReceive message: WKScriptMessage) {
        guard let body = message.body as? JSON, let type = body["type"] as? String else { return }
        switch type {
        case "ready":
            ready = true
            Task {
                guard let hello = await app.cockpit.hello() else { return }
                send(hello)
            }
        case "key": window.makeKey()
        case "height":
            if kind == .call, let h = body["h"] as? Double { fit(CGFloat(h)) }
        case "play": app.playInWebtiles()
        case "start": app.startCockpit()
        default: break
        }
    }

    func webView(_ webView: WKWebView, decidePolicyFor action: WKNavigationAction,
                 decisionHandler: @escaping @MainActor (WKNavigationActionPolicy) -> Void) {
        guard let url = action.request.url else { return decisionHandler(.cancel) }
        if url.scheme == "about" || (url.host == app.cockpit.base.host && url.port == app.cockpit.port && action.targetFrame != nil) {
            return decisionHandler(.allow)
        }
        decisionHandler(.cancel)
        app.open(url)
    }

    // target=_blank links ("Watch in webtiles", the lobby link)
    func webView(_ webView: WKWebView, createWebViewWith configuration: WKWebViewConfiguration,
                 for action: WKNavigationAction, windowFeatures: WKWindowFeatures) -> WKWebView? {
        if let url = action.request.url { app.open(url) }
        return nil
    }

    func webView(_ webView: WKWebView, didFailProvisionalNavigation navigation: WKNavigation!, withError error: Error) {
        offline()
    }

    func webViewWebContentProcessDidTerminate(_ webView: WKWebView) {
        app.cockpit.up ? load() : offline()
    }

    func windowWillClose(_ notification: Notification) {
        Prefs.d.set(false, forKey: shownKey)
    }

    static func offlinePage(port: Int, managed: Bool) -> String {
        """
        <!doctype html><meta charset="utf-8">
        <style>
          :root { color-scheme: light dark; font: 14px/1.5 system-ui; }
          body { margin: 0; padding: 18px; background: transparent; color: CanvasText; display: grid; gap: 10px; }
          p { margin: 0; } .m { opacity: .7; font-size: 12.5px; } code { font: 12px ui-monospace, monospace; }
          button { font: inherit; padding: 5px 12px; border-radius: 6px; border: 1px solid #8888; background: #8881; color: inherit; cursor: pointer; justify-self: start; }
        </style>
        <p><b>\(managed ? "The cockpit is starting…" : "No cockpit on port \(port).")</b></p>
        \(managed ? "<p class=m>This window fills in once it answers.</p>" : """
        <p class=m>Start one here, or run <code>uv run ladder cockpit</code> in the repo: this window connects by itself.</p>
        <button onclick="webkit.messageHandlers.ladder.postMessage({type:'start'})">Start cockpit</button>
        """)
        """
    }
}
