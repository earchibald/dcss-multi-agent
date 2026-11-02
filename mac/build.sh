#!/bin/bash
# Builds mac/build/Ladder.app.
#   --notarize  also notarizes it with Apple and staples the ticket (a few minutes; needs the network)
#   --install   also copies it to ~/Applications
# Signs with the first "Developer ID Application" identity in the keychain (or $LADDER_SIGN_ID), with
# the hardened runtime and a timestamp, which notarizing needs; with none, it signs ad hoc.
# Notarizing uses notarytool's saved credentials, profile $LADDER_NOTARY_PROFILE (default twistwright):
# `xcrun notarytool store-credentials` keeps them in the keychain, so no secret passes through here.
set -euo pipefail
cd "$(dirname "$0")"
NOTARIZE=0 INSTALL=0
for arg in "$@"; do
  case "$arg" in
    --notarize) NOTARIZE=1 ;;
    --install) INSTALL=1 ;;
    *) echo "usage: $0 [--notarize] [--install]" >&2; exit 2 ;;
  esac
done

swift build -c release
APP=build/Ladder.app
rm -rf "$APP"
mkdir -p "$APP/Contents/MacOS" "$APP/Contents/Resources" build/icon
cp "$(swift build -c release --show-bin-path)/Ladder" "$APP/Contents/MacOS/Ladder"
sed "s|__REPO__|$(cd .. && pwd)|" Info.plist > "$APP/Contents/Info.plist"
swift icon.swift build/icon/Ladder.iconset
iconutil -c icns -o "$APP/Contents/Resources/Ladder.icns" build/icon/Ladder.iconset

ID="${LADDER_SIGN_ID:-$(security find-identity -v -p codesigning | sed -n 's/.*"\(Developer ID Application: .*\)"/\1/p' | head -1)}"
if [ -n "$ID" ]; then
  codesign --force --options runtime --timestamp --sign "$ID" "$APP"
  echo "Signed with $ID"
else
  [ "$NOTARIZE" = 1 ] && { echo "Notarizing needs a Developer ID Application identity" >&2; exit 1; }
  codesign --force --sign - "$APP"
  echo "Signed ad hoc (no Developer ID identity)"
fi
codesign --verify --strict "$APP"
echo "Built $APP"

if [ "$NOTARIZE" = 1 ]; then
  ditto -c -k --keepParent "$APP" build/Ladder.zip
  xcrun notarytool submit build/Ladder.zip --keychain-profile "${LADDER_NOTARY_PROFILE:-twistwright}" --wait
  xcrun stapler staple "$APP"
  rm build/Ladder.zip
  spctl --assess --type execute --verbose "$APP"
  echo "Notarized $APP"
fi

if [ "$INSTALL" = 1 ]; then
  mkdir -p ~/Applications
  rm -rf ~/Applications/Ladder.app
  cp -R "$APP" ~/Applications/
  echo "Installed ~/Applications/Ladder.app"
fi
