#!/usr/bin/env bash
# doctor.sh — check everything this skill needs, before you start subtitling.
# Usage: scripts/doctor.sh [zh|ja|ko|en | "Font Family Name"]
# Exit code 0 = all good, 1 = something is missing.
set -uo pipefail
FF="${FFMPEG:-ffmpeg}"
FONT="${1:-}"
FAIL=0

ok()   { printf '  [ OK ] %s\n' "$1"; }
warn() { printf '  [WARN] %s\n' "$1"; }
bad()  { printf '  [FAIL] %s\n' "$1"; FAIL=1; }

printf '== ffmpeg ==\n'
if command -v "$FF" >/dev/null 2>&1; then
  ok "$("$FF" -version 2>/dev/null | head -1)"
else
  bad "ffmpeg not found. Install it (macOS: brew install ffmpeg | Windows: gyan.dev full build | Debian: apt install ffmpeg)"
  printf '\nCannot continue without ffmpeg.\n'; exit 1
fi

printf '\n== libass (subtitles filter) ==\n'
# Ask ffmpeg directly whether the filter exists: robust across versions and table layouts.
# (Grepping `-filters` output by column width breaks whenever the flag columns change.)
if "$FF" -hide_banner -h filter=ass >/dev/null 2>&1 && "$FF" -hide_banner -h filter=subtitles >/dev/null 2>&1; then
  ok "ass / subtitles filters available (libass linked)"
else
  bad "this ffmpeg build has no working ass/subtitles filter -> cannot burn subtitles. Reinstall with libass."
fi

printf '\n== fontconfig support in ffmpeg ==\n'
if "$FF" -hide_banner -version 2>/dev/null | tr ' ' '\n' | grep -q -- '--enable-fontconfig'; then
  ok "compiled with --enable-fontconfig (styles resolve fonts by family name)"
elif "$FF" -hide_banner -version 2>/dev/null | tr ' ' '\n' | grep -q -- '--enable-libass'; then
  warn "libass present but fontconfig flag not visible; font resolution may fall back. Test with preview_frame.sh."
else
  bad "no fontconfig/libass signal in build config"
fi

printf '\n== fontconfig tool ==\n'
font_candidates() {
  case "$1" in
    zh) echo "Hiragino Sans GB|PingFang SC|Microsoft YaHei|Noto Sans SC|Noto Sans CJK SC|Source Han Sans SC" ;;
    ja) echo "Hiragino Sans|Yu Gothic|Meiryo|Noto Sans JP|Noto Sans CJK JP" ;;
    ko) echo "Apple SD Gothic Neo|Malgun Gothic|Noto Sans KR|Noto Sans CJK KR" ;;
    en) echo "Helvetica Neue|Arial|Inter" ;;
  esac
}
if command -v fc-match >/dev/null 2>&1; then
  ok "fc-match available"
  case "$FONT" in
    zh|ja|ko|en)
      found=""
      while IFS= read -r fam; do
        [ -z "$fam" ] && continue
        if fc-match "$fam" 2>/dev/null | grep -qiF "$fam"; then found="$fam"; break; fi
      done <<LIST
$(font_candidates "$FONT" | tr '|' '\n')
LIST
      if [ -n "$found" ]; then
        ok "font for '$FONT': $found  ->  $(fc-match "$found" 2>/dev/null | cut -c1-80)"
      else
        bad "no resolvable font for '$FONT'. Install one of: $(font_candidates "$FONT" | tr '|' ' / ')"
      fi ;;
    "")
      printf '  hint: pass a language or a family, e.g.\n'
      printf '        scripts/doctor.sh zh            (tries Hiragino Sans GB, PingFang SC, Microsoft YaHei, Noto Sans CJK SC...)\n'
      printf '        scripts/doctor.sh "Hiragino Sans GB"\n' ;;
    *)
      printf '  -> fc-match "%s:bold": %s\n' "$FONT" "$(fc-match "$FONT:bold" 2>/dev/null)" ;;
  esac
else
  warn "fc-match not installed. libass may still resolve fonts via its own provider, but you cannot
        verify the family name matches. If preview text appears in the wrong face, install fontconfig
        (macOS: brew install fontconfig | Debian: apt install fontconfig)."
fi

printf '\n== python3 (only needed for export_cues.py) ==\n'
if command -v python3 >/dev/null 2>&1; then
  ok "$(python3 -V 2>&1) — script uses the standard library only, no pip installs"
else
  warn "python3 not found: export_cues.py (cue table + reading-speed audit) will not run.
        Everything else works without it."
fi

printf '\n== scripts executable ==\n'
here="$(cd "$(dirname "$0")" && pwd)"
notexec=0
for f in "$here"/*.sh "$here"/*.py; do
  [ -x "$f" ] || { printf '  not executable: %s\n' "$(basename "$f")"; notexec=1; }
done
[ "$notexec" -eq 0 ] && ok "all scripts executable" || warn "run: chmod +x scripts/*.sh scripts/*.py"

printf '\n'
if [ "$FAIL" -eq 0 ]; then
  printf 'READY. Next: scripts/probe.sh <video>\n'
else
  printf 'NOT READY. Fix the FAIL lines above.\n'
fi
exit "$FAIL"
