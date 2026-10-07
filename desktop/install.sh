#!/bin/bash
set -euo pipefail
project_root="$(cd "$(dirname "$0")/.." && pwd)"
app_root="$HOME/Applications/Ariana.app"
if pgrep -x Ariana >/dev/null; then
  printf 'Quit Ariana from its menu bar before installing an updated build.\n' >&2
  exit 1
fi
mkdir -p "$app_root/Contents/MacOS" "$app_root/Contents/Resources"
cd "$project_root/ariana"
# Preserve an existing optional wake installation during ordinary upgrades.
if [[ "${1:-}" == "--wake-word" ]] || { [[ -x .venv/bin/python ]] && .venv/bin/python -c 'import importlib.util,sys; sys.exit(0 if importlib.util.find_spec("pvporcupine") else 1)'; }; then
  uv sync --locked --extra wake-word
else
  uv sync --locked
fi
cd "$project_root/frontend"
npm ci
npm run build
swiftc -parse-as-library -O "$project_root/desktop/Ariana.swift" "$project_root/desktop/CompanionState.swift" "$project_root/desktop/ManagedService.swift" -o "$app_root/Contents/MacOS/Ariana" -framework Cocoa -framework WebKit -framework Network -framework ServiceManagement -framework AVFoundation
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
<key>NSMicrophoneUsageDescription</key><string>Ariana uses the microphone for voice input or optional local wake-word detection.</string>
<key>NSAppleEventsUsageDescription</key><string>Ariana controls Apple apps when you ask her to.</string>
</dict></plist>
PLIST
codesign --force --sign - "$app_root"
printf 'Installed %s\nOpen it with: open "%s"\n' "$app_root" "$app_root"
