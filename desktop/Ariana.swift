import Cocoa
import AVFoundation
import WebKit
import Network
import ServiceManagement
import Darwin

// A persistent WKWebView keeps the LiveKit session alive when its window is hidden.
// No microphone is requested until the user chooses voice input in the workspace.
@main
final class ArianaApp: NSObject, NSApplicationDelegate, NSWindowDelegate, WKNavigationDelegate, WKUIDelegate, WKScriptMessageHandler {
    private var item: NSStatusItem!
    private var window: NSWindow!
    private var web: WKWebView!
    private var frontend: ManagedService?
    private var agent: ManagedService?
    private var statusEntry: NSMenuItem!
    private var loginEntry: NSMenuItem!
    private var wakeEntry: NSMenuItem!
    private var wakeProcess: Process?
    private var wakeInput: Pipe?
    private var wakeOutput: Pipe?
    private var wakeBuffer = ""
    private var wakeGate = WakeGate()
    private var outputSuppression = OutputSuppression()
    private var wakeFailure = ""
    private var lockFile: Int32 = -1
    private let network = NWPathMonitor()
    private var networkOnline = true
    private var loading = false
    private var viewPolicy = RestartBackoff()
    private var nextViewLoad = Date.distantPast
    private var healthInFlight = false
    private var healthFailures = 0
    private var python = ""
    private var lastFrontendState = "connecting"
    private var lastStateAt = Date()
    private var observers: [NSObjectProtocol] = []
    private let instance = UUID().uuidString
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
        lockFile = Darwin.open(storage.appendingPathComponent("companion.lock").path, O_CREAT | O_RDWR, S_IRUSR | S_IWUSR)
        guard lockFile >= 0 && flock(lockFile, LOCK_EX | LOCK_NB) == 0 else { NSApplication.shared.terminate(nil); return }
        let logs = storage.appendingPathComponent("desktop.log")
        fm.createFile(atPath: logs.path, contents: nil, attributes: [.posixPermissions: 0o600])
        log = try? FileHandle(forWritingTo: logs)

        item = NSStatusBar.system.statusItem(withLength: NSStatusItem.squareLength)
        item.button?.image = NSImage(systemSymbolName: "sparkle", accessibilityDescription: "Ariana")
        let menu = NSMenu()
        statusEntry = NSMenuItem(title: "Ariana · Connecting", action: nil, keyEquivalent: "")
        menu.addItem(statusEntry)
        loginEntry = NSMenuItem(title: "Start at login", action: #selector(toggleLogin), keyEquivalent: "")
        wakeEntry = NSMenuItem(title: "Wake word (local)", action: #selector(toggleWake), keyEquivalent: "")
        menu.addItem(loginEntry); menu.addItem(wakeEntry)
        menu.addItem(withTitle: "Reconnect", action: #selector(recover), keyEquivalent: "")
        menu.addItem(withTitle: "Show Ariana", action: #selector(show), keyEquivalent: "")
        menu.addItem(withTitle: "Pause conversation", action: #selector(pause), keyEquivalent: "")
        menu.addItem(.separator())
        menu.addItem(withTitle: "Quit Ariana", action: #selector(quit), keyEquivalent: "q")
        for entry in menu.items { entry.target = self }
        item.menu = menu

        refreshLogin()
        wakeGate.enabled = UserDefaults.standard.bool(forKey: "wakeWordEnabled")
        wakeGate.busy = true
        let configuration = WKWebViewConfiguration()
        configuration.userContentController.add(self, name: "companion")
        configuration.mediaTypesRequiringUserActionForPlayback = []
        let config: [String: Any] = ["desktop": true, "accessCode": code]
        let data = try! JSONSerialization.data(withJSONObject: config)
        let source = "window.arianaDesktop = " + String(data: data, encoding: .utf8)! + "; window.arianaDesktop.postMessage = function(message) { window.webkit.messageHandlers.companion.postMessage(message); };"
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
        python = root.appendingPathComponent("ariana/.venv/bin/python").path
        guard fm.isExecutableFile(atPath: python) else { fail("Run desktop/install.sh to install Ariana's Python environment."); return }
        var environment = ProcessInfo.processInfo.environment
        environment["PATH"] = fm.homeDirectoryForCurrentUser.appendingPathComponent(".local/bin").path + ":/usr/local/bin:/opt/homebrew/bin:/usr/bin:/bin"
        environment["ARIANA_AGENT_NAME"] = "ariana-desktop"
        environment["ARIANA_AGENT_PORT"] = "8083"
        let runner = root.appendingPathComponent("ariana/src/service_runner.py").path
        agent = ManagedService(python: python, runner: runner, command: [python, "-m", "livekit.agents", "start", "src/agent.py"], folder: root.appendingPathComponent("ariana"), environment: environment, log: log) { [weak self] state in
            if state == "recovering" || state == "offline" { self?.setStatus(state) }
            if state == "starting" && self?.loading == true && self?.networkOnline == true && self?.wakeGate.sleeping == false { self?.notify("ariana:service-recover") }
        }
        agent?.start()
        environment["LIVEKIT_AGENT_NAME"] = "ariana-desktop"
        environment["ARIANA_ACCESS_CODE"] = code
        environment["APP_ORIGIN"] = "http://127.0.0.1:\(port)"
        environment["NODE_ENV"] = "production"
        environment["ARIANA_DESKTOP_INSTANCE"] = instance
        frontend = ManagedService(python: python, runner: runner, command: [node, root.appendingPathComponent("frontend/node_modules/next/dist/bin/next").path, "start", "--hostname", "127.0.0.1", "--port", String(port)], folder: root.appendingPathComponent("frontend"), environment: environment, log: log) { [weak self] state in
            self?.setStatus(state == "starting" ? "connecting" : state)
            if state == "starting" { self?.loading = false; self?.attempts = 0 }
        }
        frontend?.start()
        poll = Timer.scheduledTimer(withTimeInterval: 2, repeats: true) { [weak self] _ in self?.checkServer() }
        heartbeat = Timer.scheduledTimer(withTimeInterval: 25, repeats: true) { [weak self] _ in
            self?.notify("ariana:heartbeat")
            if let self = self, self.loading && Date().timeIntervalSince(self.lastStateAt) > 75 { self.notify("ariana:service-recover") }
        }
        let center = NSWorkspace.shared.notificationCenter
        observers.append(center.addObserver(forName: NSWorkspace.willSleepNotification, object: nil, queue: .main) { [weak self] _ in
            self?.wakeGate.sleeping = true; self?.syncWake(); self?.notify("ariana:sleep"); self?.setStatus("sleeping")
        })
        observers.append(center.addObserver(forName: NSWorkspace.didWakeNotification, object: nil, queue: .main) { [weak self] _ in
            self?.wakeGate.sleeping = false; self?.automaticRecovery()
        })
        network.pathUpdateHandler = { [weak self] path in
            DispatchQueue.main.async {
                guard let self = self else { return }
                let online = path.status == .satisfied
                let previous = self.networkOnline; self.networkOnline = online
                if !online { self.setStatus("offline"); self.notify("ariana:offline") }
                else if !previous { self.automaticRecovery() }
            }
        }
        network.start(queue: DispatchQueue(label: "ariana.network"))
        syncWake()
    }

    private func checkServer() {
        guard !quitting && !wakeGate.sleeping && !healthInFlight && frontend?.running == true else { return }
        // After first load, check only once per ~30 seconds; no constant network probes.
        attempts += 1
        if loading && attempts % 15 != 0 { return }
        if !loading && Date() < nextViewLoad { return }
        healthInFlight = true
        let url = URL(string: "http://127.0.0.1:\(port)/api/health")!
        var request = URLRequest(url: url); request.timeoutInterval = 2
        URLSession.shared.dataTask(with: request) { [weak self] data, response, _ in
            DispatchQueue.main.async {
                guard let self = self else { return }; self.healthInFlight = false
                guard let data = data, (response as? HTTPURLResponse)?.statusCode == 200,
                      let result = try? JSONSerialization.jsonObject(with: data) as? [String: Any], result["instance"] as? String == self.instance else {
                    self.healthFailures += 1
                    self.setStatus("offline")
                    if self.healthFailures >= 3 { self.healthFailures = 0; self.frontend?.restartAfterHealthFailure() }
                    return
                }
                self.healthFailures = 0
                if !self.loading { self.loading = true; self.web.load(URLRequest(url: URL(string: "http://127.0.0.1:\(self.port)/")!)) }
            }
        }.resume()
    }

    private func notify(_ name: String) {
        web?.evaluateJavaScript("window.dispatchEvent(new Event('" + name + "'))", completionHandler: nil)
    }
    private func setStatus(_ state: String) {
        let labels = ["connecting":"Connecting", "starting":"Starting", "idle":"Ready", "listening":"Listening", "thinking":"Thinking", "speaking":"Speaking", "offline":"Offline", "recovering":"Recovering", "sleeping":"Sleeping", "paused":"Paused"]
        statusEntry?.title = "Ariana · " + (labels[state] ?? "Ready")
        item?.button?.toolTip = statusEntry?.title
        item?.button?.image = NSImage(systemSymbolName: state == "listening" ? "mic.fill" : state == "offline" ? "wifi.slash" : "sparkle", accessibilityDescription: statusEntry?.title)
    }
    @objc private func recover() {
        guard !quitting else { return }
        viewPolicy.reset(); nextViewLoad = .distantPast
        agent?.start(reset: true); frontend?.start(reset: true)
        setStatus("recovering"); notify("ariana:recover"); syncWake()
    }
    private func automaticRecovery() {
        guard !quitting else { return }
        agent?.start(); frontend?.start()
        notify("ariana:service-recover"); syncWake()
    }
    private func refreshLogin() {
        if #available(macOS 13.0, *) {
            let status = SMAppService.mainApp.status
            loginEntry?.state = status == .enabled ? .on : .off
            loginEntry?.title = status == .requiresApproval ? "Start at login · approve in System Settings" : "Start at login"
        } else { loginEntry?.isEnabled = false }
    }
    @objc private func toggleLogin() {
        if #available(macOS 13.0, *) {
            do { if SMAppService.mainApp.status == .enabled { try SMAppService.mainApp.unregister() } else { try SMAppService.mainApp.register() } }
            catch { fail("Could not update login startup. Check System Settings → General → Login Items.") }
            refreshLogin()
        }
    }
    @objc private func toggleWake() {
        if wakeGate.enabled {
            wakeGate.enabled = false; UserDefaults.standard.set(false, forKey: "wakeWordEnabled")
            wakeFailure = ""; syncWake(); return
        }
        AVCaptureDevice.requestAccess(for: .audio) { [weak self] granted in
            DispatchQueue.main.async {
                guard let self = self else { return }
                self.wakeGate.enabled = granted
                UserDefaults.standard.set(granted, forKey: "wakeWordEnabled")
                self.wakeFailure = granted ? "" : "microphone permission denied"
                self.syncWake()
            }
        }
    }
    private func syncWake() {
        wakeGate.outputActive = outputSuppression.blocks(now: ProcessInfo.processInfo.systemUptime)
        wakeEntry?.state = wakeGate.enabled ? .on : .off
        wakeEntry?.title = wakeFailure.isEmpty ? "Wake word · " + (wakeGate.enabled ? (wakeGate.armed ? "armed locally" : "paused during conversation") : "off") : "Wake word · " + wakeFailure
        if !wakeGate.enabled { stopWake(); return }
        guard AVCaptureDevice.authorizationStatus(for: .audio) == .authorized else {
            wakeFailure = "microphone permission needed"; wakeEntry?.title = "Wake word · " + wakeFailure; return
        }
        if wakeProcess == nil && wakeFailure.isEmpty && !python.isEmpty {
            let process = Process(), input = Pipe(), output = Pipe()
            process.executableURL = URL(fileURLWithPath: python); process.arguments = [root.appendingPathComponent("ariana/src/wake_word.py").path]
            process.currentDirectoryURL = root.appendingPathComponent("ariana")
            process.standardInput = input; process.standardOutput = output; process.standardError = log
            wakeInput = input; wakeOutput = output; wakeProcess = process
            output.fileHandleForReading.readabilityHandler = { [weak self] handle in
                let data = handle.availableData
                guard !data.isEmpty, let text = String(data: data, encoding: .utf8) else { return }
                DispatchQueue.main.async { self?.receiveWake(text) }
            }
            process.terminationHandler = { [weak self] _ in DispatchQueue.main.async {
                guard self?.wakeProcess === process else { return }
                self?.wakeOutput?.fileHandleForReading.readabilityHandler = nil
                self?.wakeProcess = nil
                if self?.wakeGate.enabled == true && self?.quitting == false { self?.wakeFailure = "needs setup or microphone access"; self?.syncWake() }
            } }
            do { try process.run() } catch { wakeProcess = nil; wakeFailure = "needs setup" }
        }
        if let data = try? JSONSerialization.data(withJSONObject: ["enabled": wakeGate.armed]) { try? wakeInput?.fileHandleForWriting.write(contentsOf: data + Data([10])) }
    }
    private func stopWake() {
        try? wakeInput?.fileHandleForWriting.close(); wakeInput = nil
        wakeOutput?.fileHandleForReading.readabilityHandler = nil
        wakeProcess?.terminate(); wakeProcess = nil
    }
    private func receiveWake(_ text: String) {
        wakeBuffer += text
        while let end = wakeBuffer.firstIndex(of: "\n") {
            let line = String(wakeBuffer[..<end]); wakeBuffer.removeSubrange(...end)
            guard let data = line.data(using: .utf8), let message = try? JSONSerialization.jsonObject(with: data) as? [String: Any] else { continue }
            if message["event"] as? String == "wake", wakeGate.detect(now: ProcessInfo.processInfo.systemUptime) {
                notify("ariana:wake-word"); syncWake()
            } else if message["event"] as? String == "error" { wakeFailure = "needs setup or microphone access"; syncWake() }
        }
    }
    func userContentController(_ controller: WKUserContentController, didReceive message: WKScriptMessage) {
        guard message.frameInfo.isMainFrame, let data = message.body as? [String: Any], data["type"] as? String == "state",
              let state = data["state"] as? String, ["idle","listening","thinking","speaking","connecting","offline","recovering","paused"].contains(state) else { return }
        lastStateAt = Date(); lastFrontendState = state; setStatus(wakeGate.sleeping ? "sleeping" : !networkOnline ? "offline" : state)
        wakeGate.sessionListening = data["microphone"] as? Bool == true
        let output = data["output"] as? Bool == true
        outputSuppression.observe(active: output, now: ProcessInfo.processInfo.systemUptime)
        if !output && outputSuppression.blocks(now: ProcessInfo.processInfo.systemUptime) {
            DispatchQueue.main.asyncAfter(deadline: .now() + 1.05) { [weak self] in self?.syncWake() }
        }
        wakeGate.busy = state == "thinking" || state == "speaking" || state == "connecting" || state == "recovering"
        syncWake()
    }
    func applicationShouldTerminate(_ sender: NSApplication) -> NSApplication.TerminateReply {
        if quitting { return .terminateNow }
        quitting = true; network.cancel(); heartbeat?.invalidate(); poll?.invalidate(); stopWake()
        agent?.stop(); frontend?.stop()
        let deadline = Date().addingTimeInterval(10)
        func finish() {
            if (self.agent?.running == true || self.frontend?.running == true) && Date() < deadline { DispatchQueue.main.asyncAfter(deadline: .now() + 0.2, execute: finish) }
            else { sender.reply(toApplicationShouldTerminate: true) }
        }
        DispatchQueue.main.async(execute: finish)
        return .terminateLater
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
        frontend?.stop(); agent?.stop()
        for observer in observers { NSWorkspace.shared.notificationCenter.removeObserver(observer) }
        if lockFile >= 0 { Darwin.close(lockFile) }
        try? log?.close()
    }
    private func fail(_ message: String) {
        let alert = NSAlert()
        alert.messageText = "Ariana needs attention"
        alert.informativeText = message
        alert.runModal()
    }
    func webView(_ webView: WKWebView, didFinish navigation: WKNavigation!) {
        viewPolicy.reset()
    }
    private func viewFailed() {
        loading = false
        if let delay = viewPolicy.failed() { nextViewLoad = Date().addingTimeInterval(delay); setStatus("recovering") }
        else { nextViewLoad = .distantFuture; setStatus("offline") }
    }
    func webView(_ webView: WKWebView, didFail navigation: WKNavigation!, withError error: Error) { viewFailed() }
    func webView(_ webView: WKWebView, didFailProvisionalNavigation navigation: WKNavigation!, withError error: Error) { viewFailed() }
    func webViewWebContentProcessDidTerminate(_ webView: WKWebView) { viewFailed() }
    func webView(_ webView: WKWebView, decidePolicyFor navigationAction: WKNavigationAction, decisionHandler: @escaping (WKNavigationActionPolicy) -> Void) {
        guard let url = navigationAction.request.url, url.scheme == "http", url.host == "127.0.0.1", url.port == port else { decisionHandler(.cancel); return }
        decisionHandler(.allow)
    }
    @available(macOS 12.0, *)
    func webView(_ webView: WKWebView, requestMediaCapturePermissionFor origin: WKSecurityOrigin, initiatedByFrame frame: WKFrameInfo, type: WKMediaCaptureType, decisionHandler: @escaping (WKPermissionDecision) -> Void) {
        decisionHandler(origin.host == "127.0.0.1" && origin.port == port && type == .microphone ? .prompt : .deny)
    }
}
