#!/usr/bin/env bash
# split_frames.sh — extract review frames at a fixed rate.
# Usage: scripts/split_frames.sh INPUT.mp4 OUTDIR [FPS=2] [WIDTH=1280]
set -euo pipefail
IN="${1:?usage: split_frames.sh INPUT.mp4 OUTDIR [FPS] [WIDTH]}"
OUT="${2:?usage: split_frames.sh INPUT.mp4 OUTDIR [FPS] [WIDTH]}"
FPS="${3:-2}"
W="${4:-1280}"
FF="${FFMPEG:-ffmpeg}"
mkdir -p "$OUT"
"$FF" -hide_banner -loglevel error -i "$IN" -vf "fps=${FPS},scale=${W}:-1" -q:v 3 "$OUT/f_%04d.jpg"
n=$(ls -1 "$OUT"/f_*.jpg | wc -l | tr -d ' ')
echo "wrote ${n} frames to ${OUT} (frame N ≈ (N-1)/${FPS} s)"
echo "Review every 4th frame for the arc first; zoom into UI text at source resolution, not here."
