import Foundation

final class ManagedService {
    private(set) var process: Process?
    private var input: Pipe?
    private var restart: DispatchWorkItem?
    private var policy = RestartBackoff()
    private var stopped = true
    private var startedAt = Date()
    private let python: String
    private let runner: String
    private let command: [String]
    private let folder: URL
    private let environment: [String: String]
    private let log: FileHandle?
    private let changed: (String) -> Void

    init(python: String, runner: String, command: [String], folder: URL, environment: [String: String], log: FileHandle?, changed: @escaping (String) -> Void) {
        self.python = python; self.runner = runner; self.command = command; self.folder = folder
        self.environment = environment; self.log = log; self.changed = changed
    }
    func start(reset: Bool = false) {
        if reset { policy.reset() }
        stopped = false
        guard process == nil else { return }
        restart?.cancel(); restart = nil
        let child = Process(), pipe = Pipe()
        child.executableURL = URL(fileURLWithPath: python)
        child.arguments = [runner, "--"] + command
        child.currentDirectoryURL = folder; child.environment = environment
        child.standardInput = pipe; child.standardOutput = log; child.standardError = log
        input = pipe; process = child; startedAt = Date()
        child.terminationHandler = { [weak self] exited in
            DispatchQueue.main.async { self?.exited(exited) }
        }
        changed("starting")
        do { try child.run() } catch { process = nil; input = nil; scheduleRecovery() }
    }
    private func exited(_ exited: Process) {
        guard process === exited else { return }
        process = nil; input = nil
        if !stopped {
            if Date().timeIntervalSince(startedAt) > 120 { policy.reset() }
            scheduleRecovery()
        }
    }
    private func scheduleRecovery() {
        guard !stopped else { return }
        guard let delay = policy.failed() else { changed("offline"); return }
        changed("recovering")
        let work = DispatchWorkItem { [weak self] in self?.start() }
        restart = work; DispatchQueue.main.asyncAfter(deadline: .now() + delay, execute: work)
    }
    func restartAfterHealthFailure() {
        guard !stopped, process != nil else { return }
        // Closing the owner pipe kills descendants; termination schedules bounded recovery.
        try? input?.fileHandleForWriting.close(); input = nil
    }
    func stop() {
        stopped = true; restart?.cancel(); restart = nil
        // EOF lets the Python owner terminate the whole child process group.
        try? input?.fileHandleForWriting.close(); input = nil
    }
    var running: Bool { process?.isRunning == true }
}
