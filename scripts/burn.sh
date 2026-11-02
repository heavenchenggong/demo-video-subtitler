#!/usr/bin/env bash
# burn.sh — burn an .ass subtitle file into the video (hard subs), keep the original audio.
# Usage: scripts/burn.sh INPUT.mp4 SUBS.ass OUT.mp4 [CRF=18] [PRESET=medium]
set -euo pipefail
IN="${1:?usage: burn.sh INPUT.mp4 SUBS.ass OUT.mp4 [CRF] [PRESET]}"
ASS="${2:?}"
OUT="${3:?}"
CRF="${4:-18}"
PRESET="${5:-medium}"
FF="${FFMPEG:-ffmpeg}"

# Audio: keep whatever the source has (-c:a copy); add nothing if there is no audio stream.
"$FF" -hide_banner -loglevel error -y -i "$IN" \
  -vf "ass=${ASS}" \
  -c:v libx264 -preset "$PRESET" -crf "$CRF" -pix_fmt yuv420p \
  -c:a copy -movflags +faststart "$OUT"

echo "wrote $OUT"
"$FF" -hide_banner -i "$OUT" 2>&1 | grep -E "Duration|Stream #" || true
echo "Now re-extract 2-3 frames from THIS file and confirm the captions look right."
