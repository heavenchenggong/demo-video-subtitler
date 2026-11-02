#!/usr/bin/env python3
"""export_cues.py — dump an .ass cue table with timing and reading-density audit.

Usage:  python3 scripts/export_cues.py subs.ass [--md] [--lang zh|ja|ko|en|auto]

Output: | start-end | text | duration | density | — plus a flag for cues that are too fast.
Use it to (a) audit reading speed before rendering, and (b) hand a presenter a reading script
that is guaranteed to match the burned captions.

Density model — counts "reading units": one Han/Kana/Hangul character = 1 unit, one Latin
word = 1.5 units (a word reads in about the same time as ~1.5 CJK characters). Thresholds differ
by script because the scripts differ in information density:

  script          comfortable      too fast (flagged)
  Han / Kana      3.5 - 5.5 /s     > 6.0
  Hangul          4.0 - 6.0 /s     > 6.5   (spaces break the stream, reads slightly faster)
  Latin          12 - 18 /s        > 19     (chars per second)

--lang auto (default) guesses from the cue text; override when the video mixes languages.
"""
import re
import sys

HAN = re.compile(r"[\u3400-\u4dbf\u4e00-\u9fff]")
KANA = re.compile(r"[\u3040-\u30ff\u31f0-\u31ff]")
HANGUL = re.compile(r"[\uac00-\ud7af\u1100-\u11ff]")
LATIN = re.compile(r"[A-Za-z]+")

MODES = {
    "cjk":   {"name": "Han/Kana", "warn": 5.5, "rush": 6.0},
    "ko":    {"name": "Hangul",   "warn": 6.0, "rush": 6.5},
    "latin": {"name": "Latin",    "warn": 18.0, "rush": 19.0},
}


def parse(path):
    cues = []
    for line in open(path, encoding="utf-8"):
        if not line.startswith("Dialogue:"):
            continue
        parts = line.split(",", 9)
        if len(parts) < 10:
            continue
        start, end, text = parts[1], parts[2], parts[9].rstrip("\n")
        text = re.sub(r"\{[^}]*\}", "", text).replace(r"\N", " / ")
        cues.append((start, end, text))
    # one row per time range (skip the duplicate halo layer)
    seen, out = set(), []
    for start, end, text in cues:
        if (start, end) in seen:
            continue
        seen.add((start, end))
        out.append((start, end, text))
    return out


def sec(t):
    h, m, s = t.split(":")
    return int(h) * 3600 + int(m) * 60 + float(s)


def mmss(t):
    s = sec(t)
    return f"{int(s // 60)}:{s % 60:04.1f}"


def counts(text):
    return (len(HAN.findall(text)), len(KANA.findall(text)),
            len(HANGUL.findall(text)), len(LATIN.findall(text)))


def pick_mode(cues, override):
    if override != "auto":
        return {"zh": "cjk", "ja": "cjk", "ko": "ko", "en": "latin"}[override]
    han = kana = hangul = latin = 0
    for _, _, t in cues:
        h, k, g, l = counts(t)
        han, kana, hangul, latin = han + h, kana + k, hangul + g, latin + l
    if hangul > (han + kana):
        return "ko"
    if (han + kana) > latin * 1.5:
        return "cjk"
    return "latin"


def main():
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    path = sys.argv[1]
    md = "--md" in sys.argv
    override = "auto"
    if "--lang" in sys.argv:
        override = sys.argv[sys.argv.index("--lang") + 1]

    cues = parse(path)
    mode_key = pick_mode(cues, override)
    mode = MODES[mode_key]

    rows = []
    for start, end, text in cues:
        dur = sec(end) - sec(start)
        h, k, g, l = counts(text)
        units = h + k + g + l * 1.5
        d = units / dur if dur > 0 else 0.0
        flag = " RUSHED" if d > mode["rush"] else (" tight" if d > mode["warn"] else "")
        rows.append((mmss(start), mmss(end), text, dur, d, flag))

    print(f"# script: {mode['name']} (comfortable {mode['warn']}/s, rush >{mode['rush']}/s)\n")
    if md:
        print("| time | cue | dur | units/s |")
        print("|---|---|---|---|")
        for a, b, t, d, r, f in rows:
            print(f"| {a}-{b} | {t} | {d:.1f}s | {r:.1f}{f} |")
    else:
        for a, b, t, d, r, f in rows:
            print(f"{a}-{b}  {d:5.1f}s  {r:4.1f}/s{f}  {t}")

    total = sum(r[3] for r in rows)
    print(f"\n{len(rows)} cues, {total:.1f}s of caption coverage")
    bad = [r for r in rows if r[5].strip() == "RUSHED"]
    if bad:
        print(f"\nRUSHED ({len(bad)}) — rewrite, split, or shorten:")
        for a, b, t, d, r, f in bad:
            print(f"  {a}-{b}  {r:.1f}/s  {t}")
    if mode_key == "cjk":
        print("\nNote: for Japanese, keep line breaks off word boundaries where possible;")
        print("      for Chinese, break at punctuation. Neither script uses spaces between words,")
        print("      so a shorter line is easier to re-read than a smaller font.")


if __name__ == "__main__":
    main()
