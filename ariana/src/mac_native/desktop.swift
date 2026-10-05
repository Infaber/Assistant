import AppKit
import ApplicationServices
import Foundation
import Carbon

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
func children(_ element: AXUIElement) -> [AXUIElement] {
    attr(element, "AXChildren") as? [AXUIElement] ?? attr(element, "AXVisibleChildren") as? [AXUIElement] ?? []
}
func actions(_ element: AXUIElement) -> [String] {
    var names: CFArray?
    guard AXUIElementCopyActionNames(element, &names) == .success else { return [] }
    return names as? [String] ?? []
}
func settable(_ element: AXUIElement, _ name: String) -> Bool {
    var result = DarwinBoolean(false)
    return AXUIElementIsAttributeSettable(element, name as CFString, &result) == .success && result.boolValue
}
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
    let secure = (role + subrole).lowercased().contains("secure") || (attr(element, "AXProtectedContent") as? Bool == true)
    let title = string(element, "AXTitle")
    let description = string(element, "AXDescription")
    let value = secure ? "[protected]" : String(string(element, "AXValue").prefix(200))
    let name = title.isEmpty && role == "AXStaticText" ? value : title
    return ["role": role, "subrole": subrole, "name": name,
            "label": description.isEmpty ? name : description, "value": value,
            "identifier": string(element, "AXIdentifier"),
            "enabled": attr(element, "AXEnabled") as? Bool ?? true, "secure": secure,
            "focused": attr(element, "AXFocused") as? Bool ?? false,
            "editable": !secure && (["AXTextField", "AXTextArea", "AXComboBox", "AXSearchField"].contains(role) || settable(element, "AXSelectedText")),
            "actions": actions(element),
            "shortcut": string(element, "AXMenuItemCmdChar"),
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
if action == "status" {
    output(["accessibility_allowed": AXIsProcessTrusted(),
            "screen_locked": workspace.frontmostApplication?.bundleIdentifier == "com.apple.loginwindow",
            "automation": "Not checked; permissions are app-specific."])
}
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
_ = AXUIElementSetAttributeValue(app, "AXEnhancedUserInterface" as CFString, kCFBooleanTrue)
let focused = attr(app, "AXFocusedUIElement").flatMap { CFGetTypeID($0) == AXUIElementGetTypeID() ? unsafeBitCast($0, to: AXUIElement.self) : nil }
let allWindows = attr(app, "AXWindows") as? [AXUIElement] ?? []
if action == "windows" {
    let rows = allWindows.enumerated().map { index, item -> [String: Any] in
        let info = describe(item)
        return ["id": "w\(index)", "index": index, "title": string(item, "AXTitle"),
                "signature": signature(info), "position": info["position"]!, "size": info["size"]!]
    }
    output(["app": front.localizedName ?? "", "pid": Int(pid), "windows": rows, "elements": []])
}
if action == "focus_window" {
    guard req["pid"] as? Int == Int(pid), let row = req["window_target"] as? [String: Any],
          let index = row["index"] as? Int, allWindows.indices.contains(index),
          row["signature"] as? String == signature(describe(allWindows[index])) else {
        fail("Window changed. List windows again.", "stale_target")
    }
    let item = allWindows[index]
    guard AXUIElementPerformAction(item, "AXRaise" as CFString) == .success else { fail("This window cannot be raised.") }
    _ = AXUIElementSetAttributeValue(item, "AXMain" as CFString, kCFBooleanTrue)
    output(["success": true, "message": "Window raised; inspect to verify."])
}
guard let windowRaw = attr(app, "AXFocusedWindow"), CFGetTypeID(windowRaw) == AXUIElementGetTypeID() else {
    fail("This app has no accessible focused window. Open the requested window first.", "no_window")
}
let window = unsafeBitCast(windowRaw, to: AXUIElement.self)
let title = string(window, "AXTitle")
let menus = attr(app, "AXMenuBar").flatMap { CFGetTypeID($0) == AXUIElementGetTypeID() ? unsafeBitCast($0, to: AXUIElement.self) : nil }
if action == "inspect" {
    let start = Date()
    var queue: [(AXUIElement, [Any], Int)] = []
    if let field = focused { queue.append((field, ["focused", 0], 0)) }
    queue.append((window, ["window", 0], 0))
    if let menu = menus { queue.append((menu, ["menu", 0], 0)) }
    var cursor = 0, infos: [[String: Any]] = [], truncated = false
    let query = (req["query"] as? String ?? "").lowercased()
    let limit = req["max_elements"] as? Int ?? 120
    var matches = 0
    var seen: [AXUIElement] = []
    while cursor < queue.count {
        if cursor >= 1200 || Date().timeIntervalSince(start) > 3.0 { truncated = true; break }
        let (element, path, depth) = queue[cursor]; cursor += 1
        if seen.contains(where: { CFEqual($0, element) }) { continue }
        seen.append(element)
        var info = describe(element)
        if let field = focused, CFEqual(field, element) { info["focused"] = true }
        let haystack = ["name", "label", "value", "role", "identifier"].map { String(describing: info[$0] ?? "") }.joined(separator: " ").lowercased()
        let role = info["role"] as? String ?? ""
        let useful = info["editable"] as? Bool == true || info["focused"] as? Bool == true ||
            !(info["actions"] as? [String] ?? []).isEmpty ||
            ["AXStaticText", "AXButton", "AXLink", "AXCheckBox", "AXRadioButton", "AXPopUpButton", "AXMenuItem", "AXScrollArea", "AXSlider", "AXTab", "AXRow", "AXCell"].contains(role)
        if (query.isEmpty ? useful : haystack.contains(query)) {
            matches += 1
            if infos.count < limit {
                var row = info; row["id"] = "e\(infos.count)"; row["path"] = path; row["signature"] = signature(info)
                infos.append(row)
            }
        }
        if info["secure"] as? Bool == true { continue }
        let next = children(element)
        if depth >= 24 { if !next.isEmpty { truncated = true }; continue }
        for (i, child) in next.enumerated() { queue.append((child, path + [i], depth + 1)) }
    }
    output(["app": front.localizedName ?? "", "pid": Int(pid), "window": title,
            "elements": infos, "truncated": truncated || matches > limit, "matches_found": matches,
            "window_signature": signature(describe(window)), "elapsed_ms": Int(Date().timeIntervalSince(start) * 1000)])
}
guard req["pid"] as? Int == Int(pid), req["window"] as? String == title else {
    fail("The foreground app or window changed. Inspect again before acting.", "stale_target")
}
if let expected = req["window_signature"] as? String, expected != signature(describe(window)) {
    fail("Window moved or changed. Inspect again.", "stale_target")
}
var target: AXUIElement?
if let row = req["target"] as? [String: Any], let path = row["path"] as? [Any], path.count >= 2 {
    switch path[0] as? String { case "window": target = window; case "menu": target = menus;
        case "focused": target = focused; default: fail("Unknown target root.", "stale_target") }
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
func pointFor(_ element: AXUIElement, allowInteractiveDescendants: Bool = false) -> CGPoint {
    let position = coordinate(element, "AXPosition", .cgPoint), size = coordinate(element, "AXSize", .cgSize)
    guard position.count == 2, size.count == 2, size[0] > 0, size[1] > 0 else { fail("Control has no usable onscreen frame.") }
    let point = CGPoint(x: position[0] + size[0]/2, y: position[1] + size[1]/2)
    var count: UInt32 = 0; var displays = [CGDirectDisplayID](repeating: 0, count: 32)
    guard CGGetActiveDisplayList(32, &displays, &count) == .success,
          displays.prefix(Int(count)).contains(where: { CGDisplayBounds($0).contains(point) }) else {
        fail("Control is offscreen. Scroll it into view and inspect again.", "offscreen")
    }
    var hit: AXUIElement?
    guard AXUIElementCopyElementAtPosition(system, Float(point.x), Float(point.y), &hit) == .success else {
        fail("Could not verify which control is at this position.")
    }
    for _ in 0..<32 {
        guard hit != nil else { break }
        if let candidate = hit, CFEqual(candidate, element) { return point }
        if !allowInteractiveDescendants, let candidate = hit,
           actions(candidate).contains("AXPress") || ["AXButton", "AXLink", "AXCheckBox", "AXRadioButton", "AXPopUpButton"].contains(string(candidate, "AXRole")) {
            fail("Another interactive control occupies this target's center. Inspect and choose the specific child control.", "occluded")
        }
        hit = hit.flatMap { attr($0, "AXParent") }.flatMap { CFGetTypeID($0) == AXUIElementGetTypeID() ? unsafeBitCast($0, to: AXUIElement.self) : nil }
    }
    fail("Control is covered by another interface element. Inspect again.", "occluded")
}
func mouseClick(_ element: AXUIElement) {
    let point = pointFor(element); checkFocus()
    guard let down = CGEvent(mouseEventSource: nil, mouseType: .leftMouseDown, mouseCursorPosition: point, mouseButton: .left),
          let up = CGEvent(mouseEventSource: nil, mouseType: .leftMouseUp, mouseCursorPosition: point, mouseButton: .left) else { fail("Could not create mouse events.") }
    down.post(tap: .cghidEventTap); up.post(tap: .cghidEventTap)
}
let codes: [String: CGKeyCode] = ["a":0,"s":1,"d":2,"f":3,"h":4,"g":5,"z":6,"x":7,"c":8,"v":9,"b":11,
 "q":12,"w":13,"e":14,"r":15,"y":16,"t":17,"1":18,"2":19,"3":20,"4":21,"6":22,"5":23,"=":24,"9":25,"7":26,
 "-":27,"8":28,"0":29,"]":30,"o":31,"u":32,"[":33,"i":34,"p":35,"l":37,"j":38,"'":39,"k":40,";":41,"\\":42,",":43,"/":44,"n":45,"m":46,".":47,"`":50]
func layoutKey(_ key: String) -> (CGKeyCode, Bool)? {
    let source = TISCopyCurrentKeyboardLayoutInputSource().takeRetainedValue()
    guard let raw = TISGetInputSourceProperty(source, kTISPropertyUnicodeKeyLayoutData) else { return nil }
    let data = Unmanaged<CFData>.fromOpaque(raw).takeUnretainedValue()
    guard let bytes = CFDataGetBytePtr(data) else { return nil }
    let layout = UnsafeRawPointer(bytes).assumingMemoryBound(to: UCKeyboardLayout.self)
    for shifted in [false, true] {
        for code in UInt16(0)..<UInt16(128) {
            var dead: UInt32 = 0, count = 0
            var chars = [UniChar](repeating: 0, count: 8)
            let status = UCKeyTranslate(layout, code, UInt16(kUCKeyActionDown),
                shifted ? UInt32(shiftKey >> 8) : 0, UInt32(LMGetKbdType()),
                OptionBits(kUCKeyTranslateNoDeadKeysMask), &dead, chars.count, &count, &chars)
            if status == noErr && String(utf16CodeUnits: chars, count: count) == key { return (code, shifted) }
        }
    }
    return nil
}
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
    let result = actions(current).contains("AXPress") ? AXUIElementPerformAction(current, "AXPress" as CFString) : AXError.actionUnsupported
    if result == .actionUnsupported || result == .notImplemented {
        guard ["AXButton", "AXLink", "AXCheckBox", "AXRadioButton", "AXPopUpButton", "AXTextField", "AXTextArea", "AXRow", "AXCell", "AXTab"].contains(string(current, "AXRole")) else {
            fail("This control cannot be pressed. Use an inspected menu or shortcut.", "unsupported_control")
        }
        mouseClick(current)
    } else if result != .success { fail("Press result was uncertain. Inspect before trying another action.", "uncertain_action") }
case "type":
    guard let current = target, describe(current)["editable"] as? Bool == true,
          let text = req["text"] as? String else { fail("Choose an editable text field.") }
    if attr(current, "AXFocused") as? Bool != true {
        _ = AXUIElementSetAttributeValue(current, "AXFocused" as CFString, kCFBooleanTrue)
    }
    let nowFocused = attr(app, "AXFocusedUIElement")
    guard attr(current, "AXFocused") as? Bool == true || (nowFocused != nil && CFEqual(nowFocused!, current)) else { fail("Could not focus the requested text field.") }
    if req["replace"] as? Bool == true {
        guard let old = attr(current, "AXValue") as? String else { fail("Cannot safely select this field's contents. Use a supported editable field.") }
        var range = CFRange(location: 0, length: old.utf16.count)
        guard let selection = AXValueCreate(.cfRange, &range),
              AXUIElementSetAttributeValue(current, "AXSelectedTextRange" as CFString, selection) == .success else {
            fail("Cannot select the field contents safely. Use a fresh inspection and an explicit select-all shortcut.")
        }
    }
    checkFocus()
    // Insert at the current selection, preserving Unicode and avoiding clipboard changes.
    if AXUIElementSetAttributeValue(current, "AXSelectedText" as CFString, text as CFString) != .success {
        let characters = Array(text.utf16)
        var offset = 0
        while offset < characters.count {
            checkFocus()
            let liveField = attr(app, "AXFocusedUIElement")
            guard (liveField != nil && CFEqual(liveField!, current)) || attr(current, "AXFocused") as? Bool == true else {
                fail("Focused field changed while typing. Some text may have been entered; inspect before continuing.", "stale_target")
            }
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
    else if let key = req["key"] as? String, let (code, shifted) = layoutKey(key) {
        if shifted { flags.insert(.maskShift) }; keyPress(code, flags)
    }
    else if let key = req["key"] as? String, let code = codes[key] { keyPress(code, flags) }
    else { fail("Unsupported keyboard character. Use a supported key.") }
case "scroll":
    checkFocus()
    let steps = req["amount"] as? Int ?? 1
    let direction = req["direction"] as? String ?? "down"
    let amount = Int32((["down", "right"].contains(direction) ? -1 : 1) * steps * 6)
    let horizontal = ["left", "right"].contains(direction)
    let point = pointFor(target ?? window, allowInteractiveDescendants: true)
    guard let move = CGEvent(mouseEventSource: nil, mouseType: .mouseMoved, mouseCursorPosition: point, mouseButton: .left) else { fail("Could not aim the scroll event.") }
    move.post(tap: .cghidEventTap)
    checkFocus()
    guard let event = CGEvent(scrollWheelEvent2Source: nil, units: .line, wheelCount: 2, wheel1: horizontal ? 0 : amount, wheel2: horizontal ? amount : 0, wheel3: 0) else { fail("Could not create a scroll event.") }
    event.post(tap: .cghidEventTap)
default: fail("Unsupported Mac action.")
}
output(["success": true, "app": front.localizedName ?? "", "message": "Action sent. Inspect again to verify the result."])
