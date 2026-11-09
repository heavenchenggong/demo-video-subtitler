#!/usr/bin/env python3
"""Reconstruct a demo's ACTION TIMELINE from the video itself, so cue times can be calibrated
against what a human actually did rather than against when text appeared on screen.

Why this exists
---------------
Chat / assistant UIs (Joule, Copilot, any agent console) render the whole conversation in one
scrolling viewport. A sentence the assistant said at t=12 may still be on screen at t=40, and a
long answer card paints its later lines in one go. So "OCR found this keyword for the first time
at t=X" is NOT when the corresponding action happened — trusting it produced three successive
mis-calibrations on a real batch before the pattern was understood.

What is reliable: the *bottom-edge focus text* — the last thing in the viewport. That is where
typing appears character by character, where "Processing your request / Thinking / Submitting"
rotates, and where the newest button lands. Plus the user's own message bubble, which is
distinguishable by x position (right side).

Output (one file per video)
---------------------------
  ## status changes   deduplicated fingerprint of the bottom focus text -> one line per change
  ## state keywords   first/last second each processing keyword was visible (compressed ranges)
  ## user bubbles     short right-side text blocks (what the operator typed / clicked)
  ## existing cues    the cue times already in the .ass or config, for side-by-side comparison

Usage
-----
  scripts/audit_actions.py --base ./videos clip1.mp4 clip2.mp4
  scripts/audit_actions.py --base ./videos --out ./audit --fps 1 --ocr ../scripts/ocr.sh clip.mp4
  scripts/audit_actions.py --base ./videos --cue-file subs.ass clip.mp4     # compare to burned cues

macOS only (uses Vision OCR through ocr.sh). On other platforms the agent's own vision can read
the extracted frames — the script still writes the frame set and skips OCR.
"""
import argparse
import json
import os
import re
import subprocess
import sys

# Processing / submit states that only exist while the user's request is in flight.
DEFAULT_KEYWORDS = [
    "Processing your", "Thinking", "Starting agent request", "Confirming your choice",
    "Finalizing your response", "Submitting", "SUBMITTED", "Finding pending",
    "Analyzing", "Searching", "Loading", "Generating",
]
# A right-side block that looks like an operator message rather than a rendered answer.
BUBBLE_RE = re.compile(r"^(yes|no|ok|sure|submit|confirm|accept|apply|cancel|\d{1,2})\b", re.I)


def slug(name):
    return re.sub(r"[^A-Za-z0-9]+", "_", name).strip("_")


def extract_frames(src, outdir, fps):
    """One decode pass at a fixed real-time rate.

    Verified on a 1080p screen recording that `fps=1` frame N corresponds to real second N
    (pixel-identical to output-seek `-ss N`). If the source is VFR this no longer holds — check
    with: ffmpeg -i IN -vf showinfo -f null - 2>&1 | grep -c showinfo  vs  duration * banner fps.
    A mismatch > ~5% means VFR; fall back to pts-driven selection (see SKILL.md trap 18).
    """
    os.makedirs(outdir, exist_ok=True)
    if os.path.exists(os.path.join(outdir, "f_001.jpg")):
        return sorted(f for f in os.listdir(outdir) if f.startswith("f_") and f.endswith(".jpg"))
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", src,
                    "-vf", f"fps={fps}", "-q:v", "3",
                    os.path.join(outdir, "f_%03d.jpg")], check=True)
    return sorted(f for f in os.listdir(outdir) if f.startswith("f_") and f.endswith(".jpg"))


def ocr_frames(ocr_cmd, paths):
    """-> {basename: [(cy, cx, text), ...]}"""
    if not ocr_cmd:
        return {}
    r = subprocess.run([ocr_cmd] + paths, capture_output=True, text=True, timeout=3600)
    if r.returncode != 0:
        print(f"  OCR failed: {r.stderr.strip()[:200]}", file=sys.stderr)
        return {}
    blocks, cur, buf = {}, None, []
    for line in r.stdout.splitlines():
        if line.startswith("@@@ "):
            if cur:
                blocks[os.path.basename(cur)] = buf
            cur, buf = line[4:], []
        else:
            buf.append(line)
    if cur:
        blocks[os.path.basename(cur)] = buf
    out = {}
    for name, lines in blocks.items():
        rows = []
        for line in lines:
            parts = line.split("\t")
            if len(parts) != 3:
                continue
            txt = parts[0].strip()
            if len(txt) >= 3:
                rows.append((float(parts[2]), float(parts[1]), txt))
        out[name] = sorted(rows)
    return out


def compress(hits):
    segs, a, b = [], None, None
    for x in hits:
        if a is None:
            a = b = x
        elif x <= b + 1:
            b = x
        else:
            segs.append((a, b))
            a = b = x
    if a is not None:
        segs.append((a, b))
    return segs


def read_cues(cue_file):
    """Pull cue times out of an .ass file (Dialogue lines) or a json config with a timing array."""
    if not cue_file or not os.path.exists(cue_file):
        return []
    if cue_file.endswith(".json"):
        cfg = json.load(open(cue_file, encoding="utf-8"))
        return [(i, x[0], x[1]) for i, x in enumerate(cfg.get("timing", []))
                if x and len(x) == 2]
    cues, seen = [], set()
    pat = re.compile(r"^Dialogue:\s*\d+,(\d+:\d\d:\d\d\.\d+),(\d+:\d\d:\d\d\.\d+),")
    for line in open(cue_file, encoding="utf-8"):
        m = pat.match(line.strip())
        if not m:
            continue
        key = (m.group(1), m.group(2))
        if key in seen:          # two layers (halo + text) describe the same cue
            continue
        seen.add(key)
        cues.append((len(cues), to_sec(m.group(1)), to_sec(m.group(2))))
    return cues


def to_sec(t):
    h, m, s = t.split(":")
    return int(h) * 3600 + int(m) * 60 + float(s)


def analyse(video, base, outdir, fps, ocr_cmd, keywords, cue_file):
    name = os.path.basename(video)[:-4] if video.lower().endswith(".mp4") else os.path.basename(video)
    s = slug(name)
    frames_dir = os.path.join(outdir, f"frames_{s}")
    files = extract_frames(os.path.join(base, video), frames_dir, fps)
    blocks = ocr_frames(ocr_cmd, [os.path.join(frames_dir, f) for f in files])

    frames = [blocks.get(f, []) for f in files]
    lines = [f"# {name} | {fps} fps real seconds | full-frame OCR with coordinates",
             f"# {len(frames)} frames, source {os.path.join(base, video)}", ""]

    lines.append("## status changes (bottom focus text fingerprint)")
    prev = None
    for t, rows in enumerate(frames):
        low = [txt for cy, cx, txt in rows if cy > 0.55 and len(txt) > 5]
        fp = " | ".join(x[:38] for x in low[-3:])
        if fp != prev:
            lines.append(f"t={t:3d} | {fp[:190]}")
            prev = fp
    if not blocks:
        lines.append("(no OCR — read the frames in frames_%s/ directly)" % s)

    lines += ["", "## state keywords (request in flight / submitted)"]
    for kw in keywords:
        hits = [t for t, rows in enumerate(frames)
                if any(kw.lower() in txt.lower() for cy, cx, txt in rows)]
        if hits:
            lines.append(f"  {kw:<28} -> " + ", ".join(f"{a}-{b}s" for a, b in compress(hits)[:12]))

    lines += ["", "## user bubble candidates (right side, cx > 0.62, short text)"]
    for t, rows in enumerate(frames):
        cand = [f"{cy:.2f}:{txt}" for cy, cx, txt in rows
                if cx > 0.62 and len(txt) < 40 and (BUBBLE_RE.match(txt.strip(" .,:;")) or len(txt) < 14)]
        if cand:
            lines.append(f"t={t:3d} | " + " ; ".join(cand[:5]))

    cues = read_cues(cue_file)
    if cues:
        lines += ["", f"## existing cues ({os.path.basename(cue_file)})"]
        lines.append("  " + "  ".join(f"c{i}:{a:.1f}-{b:.1f}" for i, a, b in cues))

    dest = os.path.join(outdir, f"{s}_actions.txt")
    with open(dest, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    return dest, len(frames)


def main():
    ap = argparse.ArgumentParser(description="Reconstruct a demo's user-action timeline via OCR.")
    ap.add_argument("videos", nargs="+", help="video file names (resolved against --base)")
    ap.add_argument("--base", default=".", help="directory holding the videos")
    ap.add_argument("--out", default="audit_actions", help="output directory")
    ap.add_argument("--fps", type=float, default=1, help="analysis frame rate (default 1)")
    ap.add_argument("--ocr", default=None,
                    help="OCR command, e.g. <skill>/scripts/ocr.sh; omit for frames-only")
    ap.add_argument("--cue-file", default=None,
                    help="existing .ass or config .json whose cue times should be listed alongside")
    ap.add_argument("--keywords", default=None,
                    help="file with one status keyword per line (replaces the built-in list)")
    args = ap.parse_args()

    keywords = DEFAULT_KEYWORDS
    if args.keywords:
        keywords = [l.strip() for l in open(args.keywords, encoding="utf-8") if l.strip()]

    ok = 0
    for v in args.videos:
        try:
            dest, n = analyse(v, args.base, args.out, args.fps, args.ocr, keywords, args.cue_file)
            print(f"OK   {v:<48} {n:4d} frames -> {dest}")
            ok += 1
        except Exception as e:                       # keep the batch going
            print(f"FAIL {v}: {e}")
    sys.exit(0 if ok == len(args.videos) else 1)


if __name__ == "__main__":
    main()
