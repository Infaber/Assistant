import Foundation

@main struct ManagedServiceTests {
    static func main() throws {
        let args = CommandLine.arguments
        let directory = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        try FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true)
        defer { try? FileManager.default.removeItem(at: directory) }
        let count = directory.appendingPathComponent("count")
        let program = "import pathlib,time; p=pathlib.Path('count'); n=int(p.read_text())+1 if p.exists() else 1; p.write_text(str(n)); time.sleep(60) if n>=3 else exit(7)"
        var states: [String] = []
        let service = ManagedService(python: args[1], runner: args[2], command: [args[1], "-c", program], folder: directory, environment: ProcessInfo.processInfo.environment, log: nil) { states.append($0) }
        service.start(); service.start() // Second start must not create another child.
        let deadline = Date().addingTimeInterval(12)
        while Date() < deadline && (try? String(contentsOf: count, encoding: .utf8)) != "3" {
            RunLoop.current.run(until: Date().addingTimeInterval(0.05))
        }
        assert((try? String(contentsOf: count, encoding: .utf8)) == "3")
        assert(states.filter { $0 == "starting" }.count == 3)
        assert(states.filter { $0 == "recovering" }.count == 2)
        service.stop()
        let stopDeadline = Date().addingTimeInterval(10)
        while service.running && Date() < stopDeadline { RunLoop.current.run(until: Date().addingTimeInterval(0.05)) }
        assert(!service.running)
        RunLoop.current.run(until: Date().addingTimeInterval(1.2))
        assert((try? String(contentsOf: count, encoding: .utf8)) == "3")
        print("Mac service tests passed: two crashes recovered, duplicate start prevented, shutdown stopped retries.")
    }
}
