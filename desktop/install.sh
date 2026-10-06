#!/bin/bash
set -euo pipefail
project_root="$(cd "$(dirname "$0")/.." && pwd)"
app_root="$HOME/Applications/Ariana.app"
mkdir -p "$app_root/Contents/MacOS" "$app_root/Contents/Resources"
cd "$project_root/ariana"
uv sync --locked
cd "$project_root/frontend"
npm ci
npm run build
swiftc -parse-as-library -O "$project_root/desktop/Ariana.swift" -o "$app_root/Contents/MacOS/Ariana" -framework Cocoa -framework WebKit
printf '%s\n' "$project_root" > "$app_root/Contents/Resources/project-path.txt"
cat > "$app_root/Contents/Info.plist" <<'PLIST'
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
<key>CFBundleName</key><string>Ariana</string>
<key>CFBundleIdentifier</key><string>local.ariana.companion</string>
<key>CFBundleExecutable</key><string>Ariana</string>
<key>CFBundlePackageType</key><string>APPL</string>
<key>CFBundleShortVersionString</key><string>0.1.0</string>
<key>LSUIElement</key><true/>
<key>NSMicrophoneUsageDescription</key><string>Ariana uses the microphone only when you enable voice input. Background check-ins work with the microphone off.</string>
<key>NSAppleEventsUsageDescription</key><string>Ariana controls Apple apps when you ask her to.</string>
</dict></plist>
PLIST
codesign --force --sign - "$app_root"
printf 'Installed %s\nOpen it with: open "%s"\n' "$app_root" "$app_root"
