import Foundation

struct RestartBackoff {
    private(set) var failures = 0
    mutating func failed() -> TimeInterval? {
        guard failures < 8 else { return nil }
        failures += 1
        return min(60, pow(2, Double(failures - 1)))
    }
    mutating func reset() { failures = 0 }
}

struct WakeGate {
    var enabled = false
    var sleeping = false
    var sessionListening = false
    var outputActive = false
    var busy = false
    private(set) var lastDetection: TimeInterval = -.infinity
    var armed: Bool { enabled && !sleeping && !sessionListening && !outputActive && !busy }
    mutating func detect(now: TimeInterval) -> Bool {
        guard armed && now - lastDetection >= 3 else { return false }
        lastDetection = now
        // Remain disarmed until frontend reports the resulting state.
        busy = true
        return true
    }
}


struct OutputSuppression {
    private var active = false
    private var quietUntil: TimeInterval = 0
    mutating func observe(active next: Bool, now: TimeInterval) {
        if active && !next { quietUntil = now + 1 }
        active = next
    }
    func blocks(now: TimeInterval) -> Bool { active || now < quietUntil }
}
