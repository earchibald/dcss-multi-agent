#!/bin/bash
# Builds mac/build/Ladder.app. `./build.sh --install` also copies it to ~/Applications.
set -euo pipefail
cd "$(dirname "$0")"
swift build -c release
APP=build/Ladder.app
rm -rf "$APP"
mkdir -p "$APP/Contents/MacOS" "$APP/Contents/Resources" build/icon
cp "$(swift build -c release --show-bin-path)/Ladder" "$APP/Contents/MacOS/Ladder"
sed "s|__REPO__|$(cd .. && pwd)|" Info.plist > "$APP/Contents/Info.plist"
swift icon.swift build/icon/Ladder.iconset
iconutil -c icns -o "$APP/Contents/Resources/Ladder.icns" build/icon/Ladder.iconset
codesign --force --sign - "$APP"
echo "Built $APP"
if [ "${1:-}" = "--install" ]; then
  mkdir -p ~/Applications
  rm -rf ~/Applications/Ladder.app
  cp -R "$APP" ~/Applications/
  echo "Installed ~/Applications/Ladder.app"
fi
