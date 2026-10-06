import AppKit
let app = NSApplication.shared
app.setActivationPolicy(.regular)
let menu = NSMenu()
let edit = NSMenuItem(title: "Edit", action: nil, keyEquivalent: "")
let editMenu = NSMenu(title: "Edit")
let selectAll = NSMenuItem(title: "Select All", action: #selector(NSText.selectAll(_:)), keyEquivalent: "a")
selectAll.keyEquivalentModifierMask = .command
editMenu.addItem(selectAll)
edit.submenu = editMenu
menu.addItem(edit)
app.mainMenu = menu
class Actions: NSObject {
    let output: NSTextField
    init(_ output: NSTextField) { self.output = output }
    @objc func pressed(_ sender: Any?) { output.stringValue = "Button clicked" }
}
let window = NSWindow(contentRect: NSRect(x: 200, y: 200, width: 550, height: 240), styleMask: [.titled, .closable, .resizable], backing: .buffered, defer: false)
window.title = "Ariana Controls QA"
let field = NSTextField(frame: NSRect(x: 20, y: 150, width: 450, height: 30))
field.stringValue = "Old search"
field.setAccessibilityLabel("Ariana Test Search")
window.contentView!.addSubview(field)
let label = NSTextField(labelWithString: "Button idle")
label.frame = NSRect(x: 20, y: 70, width: 450, height: 30)
window.contentView!.addSubview(label)
class FrameButton: NSView {
    let output: NSTextField
    init(_ output: NSTextField) { self.output = output; super.init(frame: NSRect(x: 300, y: 110, width: 180, height: 30))
        setAccessibilityElement(true); setAccessibilityRole(.button); setAccessibilityLabel("Ariana Frame Button")
        wantsLayer = true; layer?.backgroundColor = NSColor.systemBlue.cgColor
    }
    required init?(coder: NSCoder) { fatalError() }
    override func mouseDown(with event: NSEvent) { output.stringValue = event.clickCount == 2 ? "Double clicked" : "Frame clicked" }
    override func rightMouseDown(with event: NSEvent) { output.stringValue = "Context clicked" }
    override func accessibilityActionNames() -> [NSAccessibility.Action] { [] }
}
window.contentView!.addSubview(FrameButton(label))
let actions = Actions(label)
let covered = FrameButton(label)
covered.frame = NSRect(x: 300, y: 20, width: 180, height: 30)
covered.setAccessibilityLabel("Ariana Covered Frame")
let inner = NSButton(title: "Do Not Click", target: actions, action: #selector(Actions.pressed(_:)))
inner.frame = NSRect(x: 20, y: 0, width: 140, height: 30)
covered.addSubview(inner)
covered.setAccessibilityChildren([inner])
window.contentView!.addSubview(covered)
let button = NSButton(title: "Ariana Test Button", target: actions, action: #selector(Actions.pressed(_:)))
button.frame = NSRect(x: 20, y: 110, width: 250, height: 30)
window.contentView!.addSubview(button)
let second = NSWindow(contentRect: NSRect(x: 800, y: 300, width: 350, height: 180), styleMask: [.titled, .closable], backing: .buffered, defer: false)
second.title = "Ariana Second QA Window"
second.orderFront(nil)
window.makeKeyAndOrderFront(nil)
window.makeFirstResponder(field)
app.activate(ignoringOtherApps: true)
DispatchQueue.main.asyncAfter(deadline: .now() + 180) { app.terminate(nil) }
app.run()
