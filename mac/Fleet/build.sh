#!/bin/bash
# Builds mac/Fleet/build/ladder-fleet, signed with the first "Developer ID Application" identity in the
# keychain (or $LADDER_SIGN_ID), identifier com.dcss-ladder.fleet.
#
# The signature matters: the fleet key lives in the Keychain, and the Keychain lets a binary read it
# without asking only if it is "the same program". For a Developer ID signature that means the same
# identifier and team, so a rebuilt (or self-updated) ladder-fleet keeps access. An ad-hoc signature
# is a hash of the binary: every build would raise a Keychain prompt, and a headless run host would
# wait on it.
#   --install   also copy it to ~/.local/bin/ladder-fleet
set -euo pipefail
cd "$(dirname "$0")"
INSTALL=0
for arg in "$@"; do
  case "$arg" in
    --install) INSTALL=1 ;;
    *) echo "usage: $0 [--install]" >&2; exit 2 ;;
  esac
done

swift build -c release
mkdir -p build
cp "$(swift build -c release --show-bin-path)/ladder-fleet" build/ladder-fleet
ID="${LADDER_SIGN_ID:-$(security find-identity -v -p codesigning | sed -n 's/.*"\(Developer ID Application: .*\)"/\1/p' | head -1)}"
if [ -n "$ID" ]; then
  codesign --force --options runtime --timestamp=none --identifier com.dcss-ladder.fleet --sign "$ID" build/ladder-fleet
  echo "signed with $ID"
else
  codesign --force --identifier com.dcss-ladder.fleet --sign - build/ladder-fleet
  echo "no Developer ID identity: signed ad hoc (expect Keychain prompts after every rebuild)"
fi
codesign --verify --verbose=1 build/ladder-fleet
if [ "$INSTALL" = 1 ]; then
  mkdir -p ~/.local/bin
  cp build/ladder-fleet ~/.local/bin/ladder-fleet
  echo "installed ~/.local/bin/ladder-fleet"
fi
