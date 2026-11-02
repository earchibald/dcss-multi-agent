import AppKit
import UserNotifications

/// Banners for decisions (answerable from the banner) and for a game handed over to you.
/// Posted only while Ladder isn't the active app; when it is, the "Your Call" window comes forward instead.
@MainActor
final class Notifier: NSObject, UNUserNotificationCenterDelegate {
    private let center = UNUserNotificationCenter.current()
    var onAnswer: ((_ id: String, _ choice: String) -> Void)?
    var onOpen: (() -> Void)?
    var onPlay: (() -> Void)?

    func setup() {
        center.delegate = self
        center.requestAuthorization(options: [.alert, .sound, .badge]) { _, _ in }
    }

    func decision(_ p: JSON, context: String) {
        guard Prefs.notify, let id = p["id"] as? String else { return }
        let options = p["options"] as? [JSON] ?? []
        let actions = options.compactMap { o -> UNNotificationAction? in
            guard let key = o["key"] as? String, let label = o["label"] as? String else { return nil }
            let exit = o["exit"] as? Bool ?? false
            return UNNotificationAction(identifier: "opt:" + key, title: label, options: exit ? [.destructive] : [])
        }
        center.setNotificationCategories([
            UNNotificationCategory(identifier: "decision", actions: actions, intentIdentifiers: []),
            Self.handoverCategory,
        ])
        let c = UNMutableNotificationContent()
        c.title = "Your call · " + ((p["decision_type"] as? String) ?? "decision").replacingOccurrences(of: "_", with: " ")
        c.subtitle = context
        c.body = p["question"] as? String ?? ""
        c.categoryIdentifier = "decision"
        c.userInfo = ["kind": "decision", "id": id]
        c.sound = .default
        center.add(UNNotificationRequest(identifier: "decision-" + id, content: c, trigger: nil))
    }

    func clear(decision id: String) {
        center.removeDeliveredNotifications(withIdentifiers: ["decision-" + id])
        center.removePendingNotificationRequests(withIdentifiers: ["decision-" + id])
    }

    func handover(_ text: String) {
        guard Prefs.notify else { return }
        center.setNotificationCategories([Self.handoverCategory])
        let c = UNMutableNotificationContent()
        c.title = "Your game"
        c.body = text
        c.categoryIdentifier = "handover"
        c.userInfo = ["kind": "handover"]
        c.sound = .default
        center.add(UNNotificationRequest(identifier: "handover", content: c, trigger: nil))
    }

    private static let handoverCategory = UNNotificationCategory(
        identifier: "handover",
        actions: [UNNotificationAction(identifier: "play", title: "Sign in and play", options: [.foreground])],
        intentIdentifiers: [])

    nonisolated func userNotificationCenter(_ center: UNUserNotificationCenter, didReceive response: UNNotificationResponse,
                                            withCompletionHandler done: @escaping () -> Void) {
        let action = response.actionIdentifier
        let info = response.notification.request.content.userInfo
        let id = info["id"] as? String
        Task { @MainActor in
            if action.hasPrefix("opt:"), let id {
                self.onAnswer?(id, String(action.dropFirst(4)))
            } else if action == "play" {
                self.onPlay?()
            } else if action == UNNotificationDefaultActionIdentifier {
                self.onOpen?()
            }
        }
        done()
    }

    nonisolated func userNotificationCenter(_ center: UNUserNotificationCenter, willPresent notification: UNNotification,
                                            withCompletionHandler done: @escaping (UNNotificationPresentationOptions) -> Void) {
        done([.list])
    }
}
