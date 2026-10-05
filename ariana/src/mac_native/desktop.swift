import AppKit
import ApplicationServices
import Foundation

func output(_ value: [String: Any]) {
    if let data = try? JSONSerialization.data(withJSONObject: value, options: [.sortedKeys]),
       let text = String(data: data, encoding: .utf8) { print(text) }
    exit(0)
}
func fail(_ message: String, _ code: String = "ui_error") -> Never {
    output(["error": message, "code": code]); exit(0)
}
func attr(_ element: AXUIElement, _ name: String) -> CFTypeRef? {
    var result: CFTypeRef?
    guard AXUIElementCopyAttributeValue(element, name as CFString, &result) == .success else { return nil }
    return result
}
func string(_ element: AXUIElement, _ name: String) -> String { attr(element, name) as? String ?? "" }
func children(_ element: AXUIElement) -> [AXUIElement] { attr(element, "AXChildren") as? [AXUIElement] ?? [] }
func coordinate(_ element: AXUIElement, _ name: String, _ kind: AXValueType) -> [Double] {
    guard let raw = attr(element, name), CFGetTypeID(raw) == AXValueGetTypeID() else { return [] }
    let value = unsafeBitCast(raw, to: AXValue.self)
    if kind == .cgPoint {
        var point = CGPoint.zero
        guard AXValueGetValue(value, kind, &point) else { return [] }
        return [point.x, point.y]
    }
    var size = CGSize.zero
    guard AXValueGetValue(value, kind, &size) else { return [] }
    return [size.width, size.height]
}
func describe(_ element: AXUIElement) -> [String: Any] {
    let role = string(element, "AXRole"), subrole = string(element, "AXSubrole")
    let secure = (role + subrole).lowercased().contains("secure")
    let title = string(element, "AXTitle")
    let description = string(element, "AXDescription")
    let value = secure ? "[protected]" : String(string(element, "AXValue").prefix(200))
    let name = title.isEmpty && role == "AXStaticText" ? value : title
    return ["role": role, "subrole": subrole, "name": name,
            "label": description.isEmpty ? name : description, "value": value,
            "identifier": string(element, "AXIdentifier"),
            "enabled": attr(element, "AXEnabled") as? Bool ?? true, "secure": secure,
            "position": coordinate(element, "AXPosition", .cgPoint),
            "size": coordinate(element, "AXSize", .cgSize)]
}
func signature(_ info: [String: Any]) -> String {
    let fields: [Any] = ["role", "subrole", "name", "label", "identifier", "position", "size"].map { info[$0] ?? "" }
    return String(data: try! JSONSerialization.data(withJSONObject: fields, options: [.sortedKeys]), encoding: .utf8)!
}

let data = Data((CommandLine.arguments.dropFirst().first ?? "{}").utf8)
guard let req = (try? JSONSerialization.jsonObject(with: data)) as? [String: Any] else { fail("Invalid request.") }
let action = req["action"] as? String ?? ""
let workspace = NSWorkspace.shared
if action == "apps" {
    let apps = workspace.runningApplications.filter { $0.activationPolicy == .regular }.map {
        ["name": $0.localizedName ?? "", "pid": Int($0.processIdentifier), "frontmost": $0.isActive] as [String: Any]
    }
    output(["apps": apps])
}
guard AXIsProcessTrusted() else {
    fail("Accessibility access is not enabled. Allow the app running Ariana (Terminal or VS Code) in System Settings > Privacy & Security > Accessibility, then restart Ariana.", "accessibility_denied")
}
let system = AXUIElementCreateSystemWide()
AXUIElementSetMessagingTimeout(system, 0.15)
guard let front = workspace.frontmostApplication else { fail("No foreground app.") }
if front.bundleIdentifier == "com.apple.loginwindow" {
    fail("Your Mac is locked. Unlock it before using interface controls.", "screen_locked")
}
let pid = front.processIdentifier
let app = AXUIElementCreateApplication(pid)
AXUIElementSetMessagingTimeout(app, 0.15)
// Chromium apps may leave their Accessibility tree dormant until explicitly requested.
_ = AXUIElementSetAttributeValue(app, "AXManualAccessibility" as CFString, kCFBooleanTrue)
guard let windowRaw = attr(app, "AXFocusedWindow"), CFGetTypeID(windowRaw) == AXUIElementGetTypeID() else {
    fail("This app has no accessible focused window. Open the requested window first.", "no_window")
}
let window = unsafeBitCast(windowRaw, to: AXUIElement.self)
let title = string(window, "AXTitle")
let menus = attr(app, "AXMenuBar").flatMap { CFGetTypeID($0) == AXUIElementGetTypeID() ? unsafeBitCast($0, to: AXUIElement.self) : nil }
if action == "inspect" {
    let start = Date()
    var queue: [(AXUIElement, [Any], Int)] = [(window, ["window", 0], 0)]
    if let menu = menus { queue.append((menu, ["menu", 0], 0)) }
    var cursor = 0, infos: [[String: Any]] = [], truncated = false
    while cursor < queue.count {
        if infos.count >= 400 || Date().timeIntervalSince(start) > 3.0 { truncated = true; break }
        let (element, path, depth) = queue[cursor]; cursor += 1
        let info = describe(element)
        var row = info; row["id"] = "e\(infos.count)"; row["path"] = path; row["signature"] = signature(info)
        infos.append(row)
        if info["secure"] as? Bool == true { continue }
        let next = children(element)
        if depth >= 24 { if !next.isEmpty { truncated = true }; continue }
        for (i, child) in next.enumerated() { queue.append((child, path + [i], depth + 1)) }
    }
    output(["app": front.localizedName ?? "", "pid": Int(pid), "window": title,
            "elements": infos, "truncated": truncated, "elapsed_ms": Int(Date().timeIntervalSince(start) * 1000)])
}
guard req["pid"] as? Int == Int(pid), req["window"] as? String == title else {
    fail("The foreground app or window changed. Inspect again before acting.", "stale_target")
}
var target: AXUIElement?
if let row = req["target"] as? [String: Any], let path = row["path"] as? [Any], path.count >= 2 {
    target = path[0] as? String == "window" ? window : menus
    for index in path.dropFirst(2) {
        guard let current = target, let i = index as? Int else { fail("The target changed. Inspect again.", "stale_target") }
        let next = children(current)
        guard next.indices.contains(i) else { fail("The target changed. Inspect again.", "stale_target") }
        target = next[i]
    }
    guard let current = target else { fail("The target changed. Inspect again.", "stale_target") }
    let info = describe(current)
    guard row["signature"] as? String == signature(info) else { fail("The target control changed. Inspect again.", "stale_target") }
    guard info["secure"] as? Bool != true, info["enabled"] as? Bool != false else { fail("This control is protected or disabled.") }
}
func checkFocus() {
    guard workspace.frontmostApplication?.processIdentifier == pid else { fail("App focus changed. Inspect again.", "stale_target") }
}
let codes: [String: CGKeyCode] = ["a":0,"s":1,"d":2,"f":3,"h":4,"g":5,"z":6,"x":7,"c":8,"v":9,"b":11,
 "q":12,"w":13,"e":14,"r":15,"y":16,"t":17,"1":18,"2":19,"3":20,"4":21,"6":22,"5":23,"=":24,"9":25,"7":26,
 "-":27,"8":28,"0":29,"]":30,"o":31,"u":32,"[":33,"i":34,"p":35,"l":37,"j":38,"'":39,"k":40,";":41,"\\":42,",":43,"/":44,"n":45,"m":46,".":47,"`":50]
func keyPress(_ code: CGKeyCode, _ flags: CGEventFlags = []) {
    checkFocus()
    guard let down = CGEvent(keyboardEventSource: nil, virtualKey: code, keyDown: true),
          let up = CGEvent(keyboardEventSource: nil, virtualKey: code, keyDown: false) else { fail("Could not create keyboard events.") }
    down.flags = flags; up.flags = flags; down.post(tap: .cghidEventTap); up.post(tap: .cghidEventTap)
}
switch action {
case "click":
    guard let current = target else { fail("Select an inspected element.") }
    checkFocus()
    let result = AXUIElementPerformAction(current, "AXPress" as CFString)
    if result != .success { fail("This control does not support pressing. Use its app-specific command or shortcut.", "unsupported_control") }
case "type":
    guard let current = target, ["AXTextField", "AXTextArea", "AXComboBox", "AXSearchField"].contains(string(current, "AXRole")),
          let text = req["text"] as? String else { fail("Choose an editable text field.") }
    guard AXUIElementSetAttributeValue(current, "AXFocused" as CFString, kCFBooleanTrue) == .success,
          attr(current, "AXFocused") as? Bool == true else { fail("Could not focus the requested text field.") }
    checkFocus()
    // Insert at the current selection, preserving Unicode and avoiding clipboard changes.
    if AXUIElementSetAttributeValue(current, "AXSelectedText" as CFString, text as CFString) != .success {
        let characters = Array(text.utf16)
        var offset = 0
        while offset < characters.count {
            checkFocus()
            var end = min(offset + 20, characters.count)
            if end < characters.count && (0xD800...0xDBFF).contains(characters[end - 1]) { end -= 1 }
            let chunk = Array(characters[offset..<end])
            offset = end
            guard let event = CGEvent(keyboardEventSource: nil, virtualKey: 0, keyDown: true),
                  let up = CGEvent(keyboardEventSource: nil, virtualKey: 0, keyDown: false) else { fail("Could not type text.") }
            chunk.withUnsafeBufferPointer { buffer in
                event.keyboardSetUnicodeString(stringLength: chunk.count, unicodeString: buffer.baseAddress!)
                up.keyboardSetUnicodeString(stringLength: chunk.count, unicodeString: buffer.baseAddress!)
            }
            event.post(tap: .cghidEventTap); up.post(tap: .cghidEventTap)
        }
    }
case "shortcut":
    var flags: CGEventFlags = []
    for modifier in req["modifiers"] as? [String] ?? [] {
        switch modifier { case "command": flags.insert(.maskCommand); case "control": flags.insert(.maskControl);
            case "option": flags.insert(.maskAlternate); case "shift": flags.insert(.maskShift); default: break }
    }
    if let code = req["key_code"] as? Int { keyPress(CGKeyCode(code), flags) }
    else if let key = req["key"] as? String, let code = codes[key] { keyPress(code, flags) }
    else { fail("Unsupported keyboard character. Use a supported key.") }
case "scroll":
    checkFocus()
    let steps = req["amount"] as? Int ?? 1
    let amount = Int32((req["direction"] as? String == "down" ? -1 : 1) * steps * 6)
    guard let event = CGEvent(scrollWheelEvent2Source: nil, units: .line, wheelCount: 1, wheel1: amount, wheel2: 0, wheel3: 0) else { fail("Could not create a scroll event.") }
    event.post(tap: .cghidEventTap)
default: fail("Unsupported Mac action.")
}
output(["success": true, "app": front.localizedName ?? "", "message": "Action sent. Inspect again to verify the result."])
