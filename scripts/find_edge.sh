#!/usr/bin/env bash
# find_edge.sh — measure a panel edge on a strip crop, at SOURCE resolution.
# Usage: scripts/find_edge.sh INPUT.mp4 TIME_SEC X_OFFSET STRIP_WIDTH [OUT=strip.jpg]
# Then read the image and note where the boundary falls inside the strip;
# absolute_x = X_OFFSET + offset_within_strip.
set -euo pipefail
IN="${1:?usage: find_edge.sh INPUT.mp4 TIME X WIDTH [OUT]}"
T="${2:?}"
X="${3:?}"
W="${4:?}"
OUT="${5:-strip.jpg}"
FF="${FFMPEG:-ffmpeg}"
# -ss AFTER -i: frame-accurate, and timestamps stay intact (see SKILL.md trap 1)
"$FF" -hide_banner -loglevel error -y -i "$IN" -ss "$T" -frames:v 1 \
  -vf "crop=${W}:ih:${X}:0,scale=2*iw:-1:flags=lanczos" -q:v 2 "$OUT"
echo "strip: x=${X}..$((X+W)) of source, upscaled 2x -> $OUT"
echo "Read the image, locate the boundary, then: absolute_x = ${X} + offset_in_strip"
