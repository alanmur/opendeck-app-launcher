#!/usr/bin/env bash
# Build the release archive: dist/cloud.caesium.applaunch.sdPlugin.zip
# The zip contains a top-level cloud.caesium.applaunch.sdPlugin/ folder, the
# layout OpenDeck (and Stream Deck) plugin installers expect.
set -euo pipefail

ID="cloud.caesium.applaunch"
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
STAGE="$(mktemp -d)"
trap 'rm -rf "$STAGE"' EXIT

mkdir -p "$STAGE/$ID.sdPlugin" "$HERE/dist"
cp -r "$HERE/manifest.json" "$HERE/LICENSE" "$HERE/README.md" "$HERE/bin" "$HERE/icons" "$HERE/pi" "$STAGE/$ID.sdPlugin/"
find "$STAGE" -name __pycache__ -type d -prune -exec rm -rf {} +

OUT="$HERE/dist/$ID.sdPlugin.zip"
rm -f "$OUT"
(cd "$STAGE" && zip -qr -X "$OUT" "$ID.sdPlugin")
echo "Built $OUT"
unzip -l "$OUT"
