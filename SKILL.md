---
name: demo-video-subtitler
description: |
  Burn styled, well-placed subtitles into a screen-recorded product demo or UI walkthrough, and
  produce the caption copy that goes with it. This skill should be used when someone asks to
  "add subtitles", "caption this demo", or "make this recording readable for a non-English
  audience (Chinese, Japanese, Korean, any other)", or when a demo video's on-screen text is too
  small or English-only for the target audience. Handles the full loop: frame-by-frame video
  analysis, verbatim extraction of on-screen UI text, caption copy drafting with a reading-speed
  budget, a white-on-purple outlined caption look (white fill, thick coloured outline, soft halo),
  focus-following placement that never covers the live demo panel, ffmpeg/libass burn-in, and
  frame-level verification. Also covers the traps that silently break this workflow: -ss placed
  before -i kills the ass filter, downscaled preview frames give wrong crop coordinates,
  single-layer ASS cannot render a glow, and captions that straddle scene transitions.
version: 1.0.1
slug: demo-video-subtitler
displayName: Demo Video Subtitler
summary: Analyse a screen-recorded demo, author readable captions, style them (white text + coloured outline + halo) and burn them in with focus-aware placement that never covers the demo panel.
license: MIT
---

# Demo Video Subtitler

## Problem

Screen-recorded product demos fail their audience for three reasons that have nothing to do with
the product: the UI text is in the wrong language, it is too small to read, and the video often
has no narration at all (silent recordings). The viewer sees clicks happening but cannot follow
why. Subtitles fix that — but only if they are styled to be legible over busy UI, placed where
they do not cover the thing being demonstrated, and timed so they never get cut by a transition.

This skill is the full pipeline, including the non-obvious failure modes that cost hours when
discovered the hard way.

## When to use

- "Add subtitles to this demo video" / "caption this recording for our Korean team"
- A silent screen recording (`.mp4`, no audio stream, or audio that is only background music)
  where the story must be told by the caption text itself
- An English-only product demo being shown to a non-English audience
- Subtitles already exist but sit centered-bottom and cover the demo panel — needing
  focus-following placement instead
- Generating a reading script for a presenter who will talk over the video (see "Companion use")

Do **not** use this skill for: dubbing with synthesized voice (that is a TTS pipeline), or
extracting captions that already exist on a platform.

## Install (one command)

```sh
scripts/bootstrap.sh --dry-run          # inspect only: prints exactly what is missing
scripts/bootstrap.sh                    # install what is missing (asks once)
scripts/bootstrap.sh --yes --lang ja    # unattended; also prepare Japanese fonts
```

`bootstrap.sh` is idempotent — it does nothing on a machine that is already ready. It detects the
platform and picks the right installer (Homebrew / apt / dnf / pacman / winget / scoop), and falls
back to dropping a static ffmpeg into `~/.local/bin` when no package manager is available.
Run it as the first action of any session that will burn captions; skills have no install-time
hook, so this script *is* the installer.

## Prerequisites

Run the built-in check first — it inspects the machine and tells you exactly what is missing:

```sh
scripts/doctor.sh "Hiragino Sans GB"     # pass the CJK family you intend to use
```

What it checks, and the install command when something is missing:

| Requirement | Why | Install |
|---|---|---|
| `ffmpeg` **built with libass** | burns the `.ass` captions (`-vf ass=...`) | macOS `brew install ffmpeg`; Windows: gyan.dev **full** build; Debian `apt install ffmpeg` |
| `--enable-fontconfig` in the ffmpeg build | resolves fonts by family name; without it you get a silent fallback face | same builds as above include it |
| a CJK font family the system can resolve | the caption text itself | macOS: Hiragino Sans GB (pre-installed) · Windows: Microsoft YaHei (pre-installed) · Linux: `apt install fonts-noto-cjk` |
| `python3` (optional) | only `export_cues.py`; standard library, **no pip installs** | macOS: `xcode-select --install`; Linux: `apt install python3` |
| `bash`, `zip` (optional) | scripts, and packaging for distribution | pre-installed everywhere |

No Node, no ImageMagick, no pip packages, no API keys. A vision-capable model (the agent itself)
reads the frames — that is not something you install.

Two environment notes that bite:

- **Put `ffmpeg` on `PATH`**, or export its location for the scripts: `FFMPEG=/path/to/ffmpeg scripts/burn.sh ...`.
- **Windows**: libass resolves fonts through fontconfig/DirectWrite depending on the build. If
  captions render in the wrong typeface, install fontconfig (`scoop install fontconfig` or MSYS2)
  and re-check with `fc-match "Microsoft YaHei:bold"`.

## Pipeline

Work top to bottom. Do not skip Phase 2 — every later phase depends on knowing the UI geometry.

### Phase 1 — Inventory (2 minutes)

```sh
scripts/probe.sh INPUT.mp4
```

Record: duration, resolution, fps, bitrate, **whether an audio stream exists**. Run the audio
check inside the script (mean volume + silence map).

Decision from the audio check:

| Audio finding | Subtitle type |
|---|---|
| No audio stream at all | **Narration subtitles** — you author the story ("what is happening / why it matters") |
| Audio present but no speech (music only) | Same as above. Confirm by transcribing a 10s slice: an ASR tool that returns empty or near-empty on loud audio means music, not voice |
| Speech present | **Dialogue subtitles** — transcribe with timestamps first, then clean up; do not invent copy |

### Phase 2 — Visual analysis and geometry (the phase people skip)

Extract frames at 2 fps (a 60s clip → ~120 frames; review every 4th frame first for the arc, then
zoom in on text):

```sh
scripts/split_frames.sh INPUT.mp4 frames/ 2
```

Build three artifacts before writing a single caption:

1. **Beat sheet** — `| time | what changed on screen | on-screen text (verbatim) |`. A "beat" is
   any change: a notification appears, a panel slides in, a button is clicked, a scroll happens,
   a page swap, a transition. Note transition types (white flash, cut, black) — captions must not
   cross them.
2. **UI text, verbatim, read from the source resolution.** Downscaled preview frames blur small
   UI text and you will transcribe it wrong. Crop from the original file:
   `ffmpeg -i IN.mp4 -ss 12.5 -frames:v 1 -vf "crop=W:H:X:Y,scale=2*iw:-1" out.jpg`
   (`-ss` after `-i` for frame-accurate extraction; see Traps.)
3. **Geometry map** — the pixel bounds of the "live" panel (the thing being demonstrated) in
   **source pixels**. Measure it, do not eyeball it:

   ```sh
   scripts/find_edge.sh INPUT.mp4 30 2880 300     # t=30s, strip from x=2880, 300px wide
   ```

   Then read the returned strip image and note where the panel's left edge falls inside the
   strip; add that offset to the strip's x to get the absolute edge. Repeat for other scenes if
   the layout changes (e.g. a chat panel opens later).

**Rule that follows from the geometry map:** the caption lives in the *free region adjacent to*
the demo panel, never on top of it. See Phase 5.

### Phase 3 — Author the caption copy

Two rules govern everything:

- **One idea per cue.** 2–3 short lines max. A cue is a sentence, not a paragraph.
- **Reading-speed budget.** CJK: 3.5–5.5 characters per second is comfortable; above 6 is a
  scramble; below 3 feels dead. Latin: 12–18 characters per second. Compute it, don't guess.
  `scripts/export_cues.py` prints the density per cue once you have an `.ass` file — iterate
  against that number.

Cue timing rules:

- Start the cue **as the visual beat lands**, not before. If a notification slides in at 1.0s,
  the cue starts at 1.0s.
- End cues **before** a transition (white flash / cut), leaving at least 0.8s of dead air across
  it. A caption that straddles a transition reads as a glitch.
- Leave real gaps. Three to five blank seconds per minute keeps the video breathing; wall-to-wall
  captions exhaust the viewer.
- For narration subtitles, put the *reason* in the caption, not the mechanics: "the agent reached
  out on its own" beats "a notification appeared in the top-right corner".

**Stop here and get the copy signed off.** Text approved → styling. Text rejected after styling
costs a second render for nothing.

### Phase 3b — Choosing the caption language

The pipeline is language-agnostic, but three things must be decided per language before styling.

**1. Font family** — pick one the platform can resolve (verify with `scripts/doctor.sh <lang>`):

| Caption language | macOS | Windows | Linux |
|---|---|---|---|
| Chinese (zh) | Hiragino Sans GB / PingFang SC | Microsoft YaHei | Noto Sans CJK SC |
| Japanese (ja) | Hiragino Sans | Yu Gothic / Meiryo | Noto Sans CJK JP |
| Korean (ko) | Apple SD Gothic Neo | Malgun Gothic | Noto Sans CJK KR |
| Latin (en/fr/de/es…) | Helvetica Neue | Segoe UI | Inter / DejaVu Sans |

**2. Reading speed** — the budget is script-dependent; `scripts/export_cues.py` selects the right
one automatically (`--lang` overrides) and flags cues that exceed it:

| Script | Comfortable | Flag as too fast |
|---|---|---|
| Han / Kana (zh, ja) | 3.5–5.5 chars/s | > 6.0 |
| Hangul (ko) | 4.0–6.0 chars/s | > 6.5 |
| Latin | 12–18 chars/s | > 19 |

**3. Line breaking** — Chinese and Japanese have no inter-word spaces: break at punctuation
(U+FF0C, U+3001, U+3002, U+FF1A) and never split a product name. Korean and Latin break at spaces; keep a Korean
particle attached to its noun. If a line will not fit, re-wrap before shrinking the font — a
smaller typeface loses more legibility than an extra line.

**4. Line width by script** — glyph width is not the same across scripts, so the same
`Fontsize` gives different line lengths. Budget lines as `floor(available_px / (fontsize * k))`,
where `k` is roughly 1.0 for Han and 1.05–1.1 for Hangul and Kana (they set wider), and 0.5 for
Latin on average (it varies with the word).

Measured at 4K with `Fontsize 165`: 13 Hangul characters ≈ 2,150 px (safe in a 2,450 px slot),
while 18 characters ≈ 2,970 px — that overflows and pushes the line off the left edge of the
frame. When a line does not fit, re-wrap it; do not shrink the font to make it fit.

**Bilingual captions** (original + translation): only when both lines are short. Two language
lines double the reading load and, in a demo, compete with the UI. Prefer one language per
version of the file unless the client asks otherwise; when you must, stack original on top and
translation below, and budget the whole block against the *translation's* reading speed.

**Right-to-left scripts** (Arabic, Hebrew): libass supports RTL, but shaping quality depends on
the build's harfbuzz. Render a preview frame before committing — check that letters join
correctly and the alignment anchor still makes sense.

**Font weight differs by script.** Japanese and Korean families usually render visually larger
than a Chinese family at the same `Fontsize`; verify with one preview frame and adjust by eye,
not by rule.

### Phase 4 — Style (the two-layer glow)

A single ASS style cannot produce "white text with a thick colored outline and a soft colored
halo" — `Outline` only draws one ring. Use two events per cue on two layers:

| Layer | Fill | Outline | Blur | Purpose |
|---|---|---|---|---|
| 0 | transparent (`&HFF000000`) | wide, semi-transparent purple | `\blur` 20–30 | the halo |
| 1 | white | narrower, solid purple | none / `\blur1` | the readable text |

Starting point (see `assets/caption-template.ass`). Colors are `&HAABBGGRR` — alpha `00` is
opaque, `FF` is fully transparent, and the byte order is **BGR**:

```
purple RGB(124,46,240)  →  &H00F02E7C
halo, 35% opaque        →  &H55F02E7C
```

Scale by PlayRes, not by taste: a 4K render used `fontsize 180 / outline 16 / halo 28 / blur 24`;
the same look at 1080p is `80 / 7 / 12 / 12`. Set `PlayResX/Y` to the **output resolution** and
keep `ScaledBorderAndShadow: yes`.

### Phase 5 — Placement that follows the focus

Center-bottom is wrong for demos: the bottom is usually UI, and the demo panel is the one thing
that must stay visible. Anchor each cue to the free region *adjacent to* whatever is being shown:

| Focus of this cue | Anchor | Why |
|---|---|---|
| A side panel / chat panel is open | `\an6\pos(<panel_left - 40>, <panel_vertical_middle>)` | right edge hugs the panel, block grows leftward, width changes need no recompute |
| A toast/notification at top-right | `\an3\pos(<toast_right>, <toast_bottom + 80>)` | bottom-right anchor sits the block right under the toast |
| Full-width page, no panel | `\an5\pos(<visual_center_x>, <y between two content blocks>)` | centered, but placed in a measured gap — not at the geometric center |
| Title card with large built-in type | `\an5\pos(center_x, BELOW the title)` | the geometric center collides with the video's own headline |

Compute the maximum line width before writing: `max_line_px ≈ fontsize × characters`. If a line
would exceed the free region, re-wrap it (never shrink the font just for one cue) — split at
punctuation and keep product names unbroken.

For right-anchored blocks, spill of a few tens of pixels onto flat background is fine and looks
intentional; spill *onto the demo panel* is not.

**Keep the anchor off the frame edge.** The outline and halo extend beyond the glyph box by roughly
`outline + blur` pixels (at 4K with `outline 15 / blur 22`, that is ~40 px, plus anti-aliasing).
An `\an3` anchor parked 50 px from the right edge therefore gets its halo clipped and reads like a
broken word. Park anchors at least 150 px inside the frame, and check the result in a preview frame
— clipping is invisible in the `.ass` file and obvious on screen.

### Phase 6 — Burn in

```sh
scripts/burn.sh INPUT.mp4 subs.ass OUT.mp4 [crf]
```

This is `-i IN -vf "ass=subs.ass" -c:v libx264 -crf 17~18 -pix_fmt yuv420p -movflags +faststart`,
keeping the original audio track. Hard subtitles are the right default for demos — they survive
every player, upload, and screen share; ship an `.ass`/`.srt` alongside only if asked.

### Phase 7 — Verify

Render cheap stills first, then verify the encoded file:

```sh
scripts/preview_frame.sh INPUT.mp4 subs.ass 16.0 /tmp/check1.jpg
```

Check each frame for: text over the demo panel, text off-frame, unexpected line wrap, a cue that
should have ended, halo that turned into mush over a bright background. Then re-extract 3 frames
from the **finished** file (subtitles are baked, quality is final) and confirm again.

## Traps (each one cost real time to find)

1. **`-ss` before `-i` silences the `ass` filter.** Input seeking resets timestamps to zero, so
   the filter renders the subtitle state at t≈0 for every frame. Result: the video burns with no
   subtitles at all, and **ffmpeg prints no error**. Always put `-ss` after `-i` (output
   seeking), or add `-copyts`. The bundled scripts already do this.
2. **Preview-frame coordinates lie.** A frame scaled to 1280×720 but displayed to you at 1080 wide
   shifts every pixel you measure against it. Measure geometry on the **source-resolution**
   frame, and cross-check any coordinate against a strip crop of the real video.
3. **A glow needs two layers.** One style = one outline ring. Two layered events = readable text
   plus halo (Phase 4).
4. **libass needs fontconfig, not a font path.** Set `Fontname` to a family fontconfig resolves
   (`fc-match "Family:bold"`), else you silently get a fallback face.
5. **Captions across transitions.** A cue spanning a white flash looks broken; end the cue ≥0.8s
   before the cut.
6. **Reading speed is invisible until you measure it.** A cue that looks fine as text can demand
   8 characters/second. Compute density per cue and rewrite anything above budget.
7. **Do not center a caption on a title card** without looking at that frame first — the video's
   own headline is usually exactly there.
8. **A right anchor 50 px from the frame edge clips the halo.** The glyphs fit, the glow does
   not — it looks like the line was cut mid-word. Measure edge clearance as `outline + blur +
   margin`, not as "is the text inside the frame".
9. **Keep the source audio decision explicit.** Silent-in, silent-out is fine; but if the source
   has background music, say whether the deliverable keeps it. Presenting live with music under
   your voice is a common accident.

## Companion use: presenter script

The same cue table doubles as a reading script for a human who will talk over the video: dump
`| screen time | cue text | duration | density |` and the presenter reads what is on screen
instead of memorizing separate copy. Keep the two in sync by exporting from the final `.ass`,
never by retyping.

## Verification checklist

- [ ] Every cue's text appears on screen at the intended time in the **finished** file
- [ ] No cue overlaps the demo panel or runs off-frame
- [ ] No cue crosses a transition
- [ ] Densest cue ≤ 5.5 CJK chars/s (or ≤ 18 Latin chars/s)
- [ ] Halo reads cleanly over both light and dark backgrounds
- [ ] Duration, resolution and audio track of the output match the intent

## Notes

- Keep the `.ass` file as the source of truth; re-rendering after a text or position tweak is a
  one-command operation. Never hand-edit the burned video.
- If the same client has a series of demos, reuse the style block and re-derive only three things:
  PlayRes, panel geometry, per-cue focus mapping.
- Font licensing: prefer system fonts (Hiragino Sans GB, Noto Sans CJK) over bundled commercial
  faces when the output will be shared externally.

## References

- libass override tags and ASS style fields: https://github.com/libass/libass/wiki
- Aegisub ASS format reference (colour byte order, `\an` anchors, `\blur`)
- ffmpeg subtitle filters (`ass`, `subtitles`): https://ffmpeg.org/ffmpeg-filters.html#Subtitles
- ffmpeg seeking and timestamp behaviour: https://trac.ffmpeg.org/wiki/Seeking

## Sharing / install

This skill is self-contained: `SKILL.md`, `assets/caption-template.ass`, and seven scripts
(`doctor.sh` is the entry point — run it on the target machine first).

- **WorkBuddy**: copy the folder to `~/.workbuddy/skills/demo-video-subtitler/`
  (project-scoped alternative: `<repo>/.workbuddy/skills/`).
- **Claude Code**: copy to `~/.claude/skills/demo-video-subtitler/` and make the scripts
  executable (`chmod +x scripts/*.sh scripts/*.py`).
- Requirements on the receiving machine: `ffmpeg` built with libass + fontconfig, and at least
  one CJK font fontconfig can resolve. Everything else is bash + python3 standard library.
- Pack for distribution: `cd ~/.workbuddy/skills && zip -r demo-video-subtitler.zip demo-video-subtitler -x '*.DS_Store'`
