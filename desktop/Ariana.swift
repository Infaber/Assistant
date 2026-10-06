import Cocoa
import WebKit

// A persistent WKWebView keeps the LiveKit session alive when its window is hidden.
// No microphone is requested until the user chooses voice input in the workspace.
@main
final class ArianaApp: NSObject, NSApplicationDelegate, NSWindowDelegate, WKNavigationDelegate, WKUIDelegate {
    private var item: NSStatusItem!
    private var window: NSWindow!
    private var web: WKWebView!
    private var frontend: Process?
    private var agent: Process?
    private var heartbeat: Timer?
    private var poll: Timer?
    private var attempts = 0
    private var log: FileHandle?
    private var terminationSignal: DispatchSourceSignal?
    private var quitting = false
    private let port = 3030
    private let code = UUID().uuidString + UUID().uuidString
    private var root: URL!

    static func main() {
        let app = NSApplication.shared
        let delegate = ArianaApp()
        app.delegate = delegate
        app.setActivationPolicy(.accessory)
        app.run()
        _ = delegate
    }

    func applicationDidFinishLaunching(_ notification: Notification) {
        guard let resource = Bundle.main.url(forResource: "project-path", withExtension: "txt"),
              let path = try? String(contentsOf: resource, encoding: .utf8).trimmingCharacters(in: .whitespacesAndNewlines), !path.isEmpty else {
            fail("The project folder is missing. Run desktop/install.sh again."); return
        }
        signal(SIGTERM, SIG_IGN)
        terminationSignal = DispatchSource.makeSignalSource(signal: SIGTERM, queue: .main)
        terminationSignal?.setEventHandler { NSApplication.shared.terminate(nil) }
        terminationSignal?.resume()
        root = URL(fileURLWithPath: path)
        let fm = FileManager.default
        let storage = fm.homeDirectoryForCurrentUser.appendingPathComponent("Library/Application Support/Ariana")
        try? fm.createDirectory(at: storage, withIntermediateDirectories: true)
        let logs = storage.appendingPathComponent("desktop.log")
        fm.createFile(atPath: logs.path, contents: nil, attributes: [.posixPermissions: 0o600])
        log = try? FileHandle(forWritingTo: logs)

        item = NSStatusBar.system.statusItem(withLength: NSStatusItem.squareLength)
        item.button?.image = NSImage(systemSymbolName: "sparkle", accessibilityDescription: "Ariana")
        let menu = NSMenu()
        menu.addItem(withTitle: "Show Ariana", action: #selector(show), keyEquivalent: "")
        menu.addItem(withTitle: "Pause conversation", action: #selector(pause), keyEquivalent: "")
        menu.addItem(.separator())
        menu.addItem(withTitle: "Quit Ariana", action: #selector(quit), keyEquivalent: "q")
        for entry in menu.items { entry.target = self }
        item.menu = menu

        let configuration = WKWebViewConfiguration()
        configuration.mediaTypesRequiringUserActionForPlayback = []
        let config: [String: Any] = ["desktop": true, "accessCode": code]
        let data = try! JSONSerialization.data(withJSONObject: config)
        let source = "window.arianaDesktop = " + String(data: data, encoding: .utf8)! + ";"
        configuration.userContentController.addUserScript(WKUserScript(source: source, injectionTime: .atDocumentStart, forMainFrameOnly: true))
        web = WKWebView(frame: .zero, configuration: configuration)
        web.navigationDelegate = self
        web.uiDelegate = self
        web.setValue(false, forKey: "drawsBackground")
        window = NSWindow(contentRect: NSRect(x: 0, y: 0, width: 1360, height: 960), styleMask: [.titled, .closable, .miniaturizable, .resizable], backing: .buffered, defer: false)
        window.title = "Ariana"
        window.backgroundColor = NSColor(calibratedRed: 0.025, green: 0.05, blue: 0.07, alpha: 1)
        window.contentView = web
        window.delegate = self
        window.isReleasedWhenClosed = false
        window.center()
        show()

        let candidates = ["/usr/local/bin/node", "/opt/homebrew/bin/node"]
        guard let node = candidates.first(where: { fm.isExecutableFile(atPath: $0) }) else { fail("Node.js is missing. Install it, then reopen Ariana."); return }
        let uvPath = [fm.homeDirectoryForCurrentUser.appendingPathComponent(".local/bin/uv").path, "/opt/homebrew/bin/uv", "/usr/local/bin/uv"].first(where: { fm.isExecutableFile(atPath: $0) })
        guard let uv = uvPath else { fail("uv is missing. Install it, then reopen Ariana."); return }
        var environment = ProcessInfo.processInfo.environment
        environment["PATH"] = fm.homeDirectoryForCurrentUser.appendingPathComponent(".local/bin").path + ":/usr/local/bin:/opt/homebrew/bin:/usr/bin:/bin"
        environment["ARIANA_AGENT_NAME"] = "ariana-desktop"
        agent = launch(uv, ["run", "--no-sync", "--module", "livekit.agents", "start", "src/agent.py"], at: root.appendingPathComponent("ariana"), environment: environment)
        environment["LIVEKIT_AGENT_NAME"] = "ariana-desktop"
        environment["ARIANA_ACCESS_CODE"] = code
        environment["APP_ORIGIN"] = "http://127.0.0.1:\(port)"
        environment["NODE_ENV"] = "production"
        frontend = launch(node, ["node_modules/next/dist/bin/next", "start", "--hostname", "127.0.0.1", "--port", String(port)], at: root.appendingPathComponent("frontend"), environment: environment)
        poll = Timer.scheduledTimer(withTimeInterval: 1, repeats: true) { [weak self] _ in self?.checkServer() }
        heartbeat = Timer.scheduledTimer(withTimeInterval: 25, repeats: true) { [weak self] _ in
            self?.web.evaluateJavaScript("window.dispatchEvent(new Event('ariana:heartbeat'))", completionHandler: nil)
        }
    }

    private func launch(_ executable: String, _ arguments: [String], at directory: URL, environment: [String: String]) -> Process? {
        let process = Process()
        process.executableURL = URL(fileURLWithPath: executable)
        process.arguments = arguments
        process.currentDirectoryURL = directory
        process.environment = environment
        process.standardOutput = log
        process.standardError = log
        process.terminationHandler = { [weak self] exited in
            DispatchQueue.main.async {
                if exited.terminationStatus != 0 && self?.quitting == false { self?.fail("An Ariana service stopped. Check ~/Library/Application Support/Ariana/desktop.log, then quit and reopen Ariana.") }
            }
        }
        do { try process.run(); return process }
        catch { fail("Could not start Ariana: \(error.localizedDescription)"); return nil }
    }

    private func checkServer() {
        attempts += 1
        if attempts > 45 { poll?.invalidate(); fail("Ariana's local interface did not start. Check desktop.log or whether port 3030 is already in use."); return }
        let url = URL(string: "http://127.0.0.1:\(port)/")!
        var request = URLRequest(url: url)
        request.timeoutInterval = 1
        URLSession.shared.dataTask(with: request) { [weak self] _, response, _ in
            guard let response = response as? HTTPURLResponse, response.statusCode == 200 else { return }
            DispatchQueue.main.async {
                guard let self = self, self.poll?.isValid == true else { return }
                self.poll?.invalidate()
                self.web.load(URLRequest(url: url))
            }
        }.resume()
    }

    func applicationShouldHandleReopen(_ sender: NSApplication, hasVisibleWindows flag: Bool) -> Bool { show(); return true }
    func windowShouldClose(_ sender: NSWindow) -> Bool { sender.orderOut(nil); return false }
    @objc private func show() { window?.makeKeyAndOrderFront(nil); NSApplication.shared.activate(ignoringOtherApps: true) }
    @objc private func pause() {
        web?.evaluateJavaScript("window.dispatchEvent(new Event('ariana:pause'))", completionHandler: nil)
        show()
    }
    @objc private func quit() { NSApplication.shared.terminate(nil) }
    func applicationWillTerminate(_ notification: Notification) {
        quitting = true
        heartbeat?.invalidate(); poll?.invalidate()
        web?.stopLoading()
        frontend?.terminate(); agent?.terminate()
        try? log?.close()
    }
    private func fail(_ message: String) {
        let alert = NSAlert()
        alert.messageText = "Ariana needs attention"
        alert.informativeText = message
        alert.runModal()
    }
    func webView(_ webView: WKWebView, decidePolicyFor navigationAction: WKNavigationAction, decisionHandler: @escaping (WKNavigationActionPolicy) -> Void) {
        guard let url = navigationAction.request.url, url.scheme == "http", url.host == "127.0.0.1", url.port == port else { decisionHandler(.cancel); return }
        decisionHandler(.allow)
    }
    @available(macOS 12.0, *)
    func webView(_ webView: WKWebView, requestMediaCapturePermissionFor origin: WKSecurityOrigin, initiatedByFrame frame: WKFrameInfo, type: WKMediaCaptureType, decisionHandler: @escaping (WKPermissionDecision) -> Void) {
        decisionHandler(origin.host == "127.0.0.1" && origin.port == port && type == .microphone ? .prompt : .deny)
    }
}
