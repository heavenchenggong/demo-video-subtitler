#!/usr/bin/env bash
# preview_frame.sh — render one still with subtitles baked, for placement/style review.
# Usage: scripts/preview_frame.sh INPUT.mp4 SUBS.ass TIME_SEC OUT.jpg [WIDTH]
set -euo pipefail
IN="${1:?usage: preview_frame.sh INPUT.mp4 SUBS.ass TIME OUT.jpg [WIDTH]}"
ASS="${2:?}"
T="${3:?}"
OUT="${4:?}"
W="${5:-0}"   # 0 = keep source width
FF="${FFMPEG:-ffmpeg}"
if [ "$W" = "0" ]; then VF="ass=${ASS}"; else VF="ass=${ASS},scale=${W}:-1"; fi
# CRITICAL: -ss goes AFTER -i, otherwise timestamps reset and the ass filter renders nothing.
"$FF" -hide_banner -loglevel error -y -i "$IN" -ss "$T" -frames:v 1 -vf "$VF" -q:v 2 "$OUT"
echo "wrote $OUT (t=${T}s)"
