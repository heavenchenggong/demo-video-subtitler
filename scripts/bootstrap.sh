#!/usr/bin/env bash
# bootstrap.sh — make this machine ready for demo-video-subtitler.
#
# It checks the real prerequisites (ffmpeg with libass, fontconfig, a CJK font, python3) and
# installs whatever is missing. Safe to run repeatedly: it does nothing when already ready.
#
# Usage:
#   scripts/bootstrap.sh --dry-run          # show the plan, change nothing (start here)
#   scripts/bootstrap.sh                    # show the plan and ask once
#   scripts/bootstrap.sh --yes              # run without prompting (CI / "just do it")
#   scripts/bootstrap.sh --yes --lang ja    # also verify a Japanese font family
#
# Options:
#   --dry-run   plan only
#   --yes       no prompt
#   --lang X    zh | ja | ko | en  (default zh) — which caption language to prepare fonts for
#
# Exit: 0 ready, 1 failed, 2 needs a manual step (message printed).
set -uo pipefail

ASSUME_YES=0
DRY=0
LANG_CODE="zh"
while [ $# -gt 0 ]; do
  case "$1" in
    --yes|-y) ASSUME_YES=1 ;;
    --dry-run|-n) DRY=1 ;;
    --lang) shift; LANG_CODE="${1:-zh}" ;;
    -h|--help) sed -n '2,20p' "$0"; exit 0 ;;
    *) echo "unknown option: $1" >&2; exit 1 ;;
  esac
  shift
done

case "$LANG_CODE" in zh|ja|ko|en) ;; *) echo "--lang must be zh|ja|ko|en" >&2; exit 1 ;; esac

HERE="$(cd "$(dirname "$0")" && pwd)"
FF="${FFMPEG:-ffmpeg}"
BIN_DIR="$HOME/.local/bin"
OS="$(uname -s 2>/dev/null || echo unknown)"
NEEDS=()          # human-readable list of pending actions
ACTIONS=()        # shell snippets, executed in order

say()  { printf '%s\n' "$*"; }
plan() { NEEDS+=("$1"); ACTIONS+=("$2"); }

# ---------------------------------------------------------------- detection
have_ffmpeg_libass() {
  command -v "$FF" >/dev/null 2>&1 || return 1
  "$FF" -hide_banner -h filter=ass >/dev/null 2>&1 || return 1
  "$FF" -hide_banner -h filter=subtitles >/dev/null 2>&1 || return 1
  return 0
}

# Family names contain spaces ("Hiragino Sans GB"), so they must NOT be word-split.
# Pipe-delimited list keeps each family intact.
font_candidates() {
  case "$1" in
    zh) echo "Hiragino Sans GB|PingFang SC|Microsoft YaHei|Noto Sans SC|Noto Sans CJK SC|Source Han Sans SC" ;;
    ja) echo "Hiragino Sans|Yu Gothic|Meiryo|Noto Sans JP|Noto Sans CJK JP" ;;
    ko) echo "Apple SD Gothic Neo|Malgun Gothic|Noto Sans KR|Noto Sans CJK KR" ;;
    en) echo "Helvetica Neue|Arial|Inter" ;;
  esac
}

first_available_font() {
  command -v fc-match >/dev/null 2>&1 || return 1
  local fam
  while IFS= read -r fam; do
    [ -z "$fam" ] && continue
    if fc-match "$fam" 2>/dev/null | grep -qiF "$fam"; then
      printf '%s' "$fam"; return 0
    fi
  done <<EOF
$(font_candidates "$1" | tr '|' '\n')
EOF
  return 1
}

say "== demo-video-subtitler bootstrap =="
say "platform: $OS   caption language: $LANG_CODE   mode: $([ "$DRY" = 1 ] && echo 'dry-run' || echo 'apply')"
say ""

if have_ffmpeg_libass; then
  say "[ok] ffmpeg with libass: $("$FF" -version 2>/dev/null | head -1 | cut -c1-60)"
else
  say "[--] ffmpeg missing or built without libass (the one hard requirement)"
  case "$OS" in
    Darwin)
      if command -v brew >/dev/null 2>&1; then
        plan "install ffmpeg via Homebrew" "brew install ffmpeg"
      else
        plan "download static ffmpeg (evermeet) into $BIN_DIR" \
             "mkdir -p '$BIN_DIR' && curl -fL https://evermeet.cx/ffmpeg/getrelease/zip -o /tmp/ffmpeg.zip && unzip -o /tmp/ffmpeg.zip -d '$BIN_DIR' && chmod +x '$BIN_DIR/ffmpeg'"
      fi ;;
    Linux)
      if command -v apt-get >/dev/null 2>&1; then
        plan "install ffmpeg via apt" "sudo apt-get update && sudo apt-get install -y ffmpeg"
      elif command -v dnf >/dev/null 2>&1; then
        plan "install ffmpeg via dnf" "sudo dnf install -y ffmpeg"
      elif command -v pacman >/dev/null 2>&1; then
        plan "install ffmpeg via pacman" "sudo pacman -S --noconfirm ffmpeg"
      else
        plan "download static ffmpeg (johnvansickle) into $BIN_DIR" \
             "mkdir -p '$BIN_DIR' && curl -fL https://johnvansickle.com/ffmpeg/releases/ffmpeg-release-amd64-static.tar.xz -o /tmp/ff.tar.xz && tar -xJf /tmp/ff.tar.xz -C /tmp && cp /tmp/ffmpeg-*-static/ffmpeg '$BIN_DIR/' && chmod +x '$BIN_DIR/ffmpeg'"
      fi ;;
    MINGW*|MSYS*|CYGWIN*)
      if command -v winget >/dev/null 2>&1; then
        plan "install ffmpeg via winget (full build)" "winget install --id Gyan.FFmpeg -e --accept-source-agreements --accept-package-agreements"
      elif command -v scoop >/dev/null 2>&1; then
        plan "install ffmpeg via scoop" "scoop install ffmpeg"
      else
        say "[!!] Windows without winget/scoop: install the gyan.dev 'full' build manually, then re-run."
      fi ;;
    *) say "[!!] unknown platform — install ffmpeg with libass manually, then re-run." ;;
  esac
fi

if command -v fc-match >/dev/null 2>&1; then
  if fam="$(first_available_font "$LANG_CODE")"; then
    say "[ok] font for $LANG_CODE: $fam  ($(fc-match "$fam" 2>/dev/null | cut -c1-70))"
  else
    say "[--] no resolvable font for '$LANG_CODE' captions"
    case "$OS" in
      Linux) plan "install CJK fonts" "sudo apt-get install -y fonts-noto-cjk" ;;
      *) say "     install a font family such as $(font_candidates "$LANG_CODE" | cut -d'|' -f1)" ;;
    esac
  fi
else
  say "[!!] fc-match not found — libass may still resolve fonts, but the family name cannot be verified"
  if [ "$OS" = "Darwin" ] && command -v brew >/dev/null 2>&1; then
    plan "install fontconfig (font verification)" "brew install fontconfig"
  fi
fi

if command -v python3 >/dev/null 2>&1; then
  say "[ok] python3: $(python3 -V 2>&1)"
else
  say "[--] python3 missing (only export_cues.py needs it, stdlib only — optional)"
fi

say ""
if [ ${#ACTIONS[@]} -eq 0 ]; then
  say "READY — nothing to install. Next: scripts/probe.sh <video>"
  exit 0
fi

say "plan:"
i=1
for n in "${NEEDS[@]}"; do say "  $i) $n"; i=$((i+1)); done
say ""

if [ "$DRY" = 1 ]; then
  say "--dry-run: nothing executed."
  exit 0
fi

if [ "$ASSUME_YES" -ne 1 ]; then
  printf 'Proceed? [y/N] '
  read -r ans </dev/tty || ans="n"
  case "$ans" in y|Y|yes|YES) ;; *) say "aborted."; exit 2 ;; esac
fi

fails=0
for a in "${ACTIONS[@]}"; do
  say "--> $a"
  if ! bash -c "$a"; then
    say "    failed (often a sudo/password or network issue). Run it manually, then re-run this script."
    fails=$((fails+1))
  fi
done

say ""
if [ -x "$HERE/doctor.sh" ]; then
  "$HERE/doctor.sh" "$(first_available_font "$LANG_CODE" || true)" || exit 1
fi
[ "$fails" -eq 0 ] && exit 0 || exit 2
