import Foundation

@main
struct CompanionStateTests {
    static func main() {
        var restart = RestartBackoff()
        assert((0..<8).map { _ in restart.failed()! } == [1,2,4,8,16,32,60,60])
        assert(restart.failed() == nil)
        restart.reset(); assert(restart.failed() == 1)
        var wake = WakeGate()
        assert(!wake.detect(now: 1))
        wake.enabled = true; assert(wake.detect(now: 2))
        assert(!wake.detect(now: 8)) // no duplicate session before state acknowledgment
        wake.busy = false; assert(!wake.detect(now: 3)); assert(wake.detect(now: 6))
        wake.busy = false; wake.outputActive = true; assert(!wake.detect(now: 10))
        wake.outputActive = false; wake.sleeping = true; assert(!wake.armed)
        wake.sleeping = false; wake.sessionListening = true; assert(!wake.armed)
        var output = OutputSuppression()
        output.observe(active: true, now: 10); assert(output.blocks(now: 50))
        output.observe(active: false, now: 50); assert(output.blocks(now: 50.9))
        output.observe(active: false, now: 50.5); assert(!output.blocks(now: 51.1))
        print("Companion state tests passed: backoff, disabled/repeated wake, output suppression, sleep and listening.")
    }
}
