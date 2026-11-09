#!/usr/bin/env bash
# macOS-only OCR with coordinates. Compiles ocr_box.swift on first use, then reuses the binary.
#
#   scripts/ocr.sh frames/f_001.jpg frames/f_002.jpg     # -> "@@@ path" + "<text>\t<cx>\t<cy>"
#   OCR_LANG=zh-Hans,en-US scripts/ocr.sh shot.jpg       # CJK UI text
#
# cx/cy are normalized to 0..1 with the origin at the TOP-LEFT, which is what makes it possible
# to separate the user's chat bubble (right side, cx > 0.62) from the assistant reply (left side).
# Needs Xcode command line tools (swiftc). Non-macOS: skip this and use the agent's own vision.
set -euo pipefail

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SRC="$DIR/ocr_box.swift"
BIN="${TMPDIR:-/tmp}/demo_subtitler_ocr_box"

command -v swiftc >/dev/null 2>&1 || {
  echo "ocr.sh: swiftc not found — install Xcode command line tools (xcode-select --install)" >&2
  exit 127
}

# Rebuild when the source is newer than the cached binary.
if [ ! -x "$BIN" ] || [ "$SRC" -nt "$BIN" ]; then
  swiftc -O -o "$BIN" "$SRC" 2>/dev/null || {
    echo "ocr.sh: failed to compile $SRC" >&2
    exit 1
  }
fi

exec "$BIN" "$@"
