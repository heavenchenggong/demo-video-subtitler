#!/usr/bin/env bash
# probe.sh — inventory a video before subtitling.
# Usage: scripts/probe.sh INPUT.mp4
set -uo pipefail
IN="${1:?usage: probe.sh INPUT.mp4}"
FF="${FFMPEG:-ffmpeg}"

# Capture once. Do NOT feed this into `grep -q`: grep exits on first match, ffmpeg dies of
# SIGPIPE, and with `set -o pipefail` the test then evaluates false even when audio exists.
info="$("$FF" -hide_banner -i "$IN" 2>&1 || true)"

printf '== streams ==\n'
printf '%s\n' "$info" | grep -E "Duration|Stream #" || true
printf '\n'

if [[ "$info" == *"Audio:"* ]]; then
  printf '== audio level ==\n'
  "$FF" -hide_banner -i "$IN" -af volumedetect -f null - 2>&1 \
    | grep -E "mean_volume|max_volume" || true
  printf '\n== silence map (noise=-35dB, min 1.5s) ==\n'
  "$FF" -hide_banner -i "$IN" -af silencedetect=noise=-35dB:d=1.5 -f null - 2>&1 \
    | grep -E "silence_(start|end)" | head -40 || true
  printf '\nNOTE: loud audio with no silent gaps is usually background music, not speech.\n'
  printf '      Transcribe a 10s slice to confirm before choosing the subtitle type.\n'
else
  printf 'NO AUDIO STREAM -> silent demo. Author narration subtitles (the caption tells the story).\n'
fi
