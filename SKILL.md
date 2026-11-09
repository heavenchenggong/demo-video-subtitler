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
license: MIT
allowed-tools: Bash(${CLAUDE_SKILL_DIR}/scripts/*) Bash(ffmpeg:*) Bash(python3:*) Bash(chmod:*) Read Write Glob Grep
metadata:
  version: 1.2.0
  slug: demo-video-subtitler
  displayName: Demo Video Subtitler
  summary: Analyse a screen-recorded demo, author readable captions, style them (white text + coloured outline + halo), and burn them in with focus-aware placement that never covers the demo panel. v1.2.0 adds action-timeline calibration for chat/agent UIs (the accumulating-viewport trap), batch mode for 10+ video sets, and delivery into an offline site.
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
- A series of 10–40 demo videos that all need the same treatment before a booth, an event, or an
  offline hand-off (see "Batch mode")
- Videos must play in a place with unreliable network, so an offline mirror needs hard subtitles
  (see "Phase 8 — Delivery")
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
| `python3` (optional) | `export_cues.py`, `md_to_ass.py`, `audit_actions.py`; standard library, **no pip installs** | macOS: `xcode-select --install`; Linux: `apt install python3` |
| `swiftc` (optional, macOS) | compiles `ocr_box.swift` so `audit_actions.py` can read text *with coordinates* — the coordinate step is what separates the operator's bubble from the assistant's reply | `xcode-select --install` |
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

Music-only confirmation, done right: ASR hallucinates on music ("Come To" loops, "Thank you.").
Transcribe a 20s mid-video slice and classify by word count and unique-word ratio — fewer than
40 words, or unique/total < 0.35, means music, not narration. Loud audio (mean −11 dB) with a
near-empty transcript is still music. Never classify from the raw transcript alone.

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

### Phase 2.5 — Timing calibration (mandatory for screen recordings)

Cue times estimated from frame-sequence numbers do not survive contact with a real recording — and
they can fail in **two opposite directions**. Diagnose which one you have before moving anything:

| Symptom | Cause | Fix |
|---|---|---|
| Captions run **AHEAD** (+2 … +9.5 s) | frame index drifts on loading-heavy, slow-scrolling, jump-cut demos; a cue says "back in the profile" at 60 s while the profile lands at 67.4 s | re-measure each referenced action and pull the cue back |
| Captions run **BEHIND** (−2 … −8 s) | timed from "when the text appeared on screen", or a previous pass shifted everything later | rebuild the action timeline and push the cue forward |

Do not assume drift and re-align blindly. One 38-video batch was "corrected" under the assumption
of drift and came out 3–8 s **late** on eight videos; the source copy had been right all along. The
direction is a measurement, not a style choice.

Four steps:

1. **Build an action timeline from the video, not a keyword map.** Extract frames at 1 fps and read
   every frame's text *with coordinates* — `scripts/audit_actions.py` does this and writes a
   per-video report. In a chat UI the coordinates are what separate the operator's bubble (right
   side, `cx > 0.62`) from the assistant's answer (left side).
2. **Re-allocate cues to the action moments.** A cue may lead its action by ≤ 0.5 s (standard
   subtitle lead); anything more is drift, anything that *trails* it is lag.
3. **Long static states are ONE long cue.** AI generation, list scrolling, a form filling itself —
   do not slice them into a timeline of fragments.
4. **Verify "caption and referenced action in the same frame"** on the burned file, with OUTPUT
   seeking: `ffmpeg -i OUT.mp4 -ss t -frames:v 1`. Input seeking (`-ss t -i`) lands up to ~2 s
   stale on a re-encoded output and once caused a false re-timing.

Edited demos contain jump cuts — one cut skipped an entire intermediate exchange at 82→83 s. Never
assume continuity between adjacent frames.

#### Chat / assistant UIs: the accumulating-viewport trap

This is the single most expensive timing mistake in agent demos (Joule, Copilot, any agent
console), and it cost three successive mis-calibrations on one batch.

**The viewport accumulates.** The conversation scrolls but never clears, so a sentence spoken at
t=12 is still on screen at t=40. Worse, a long answer card paints its *later* lines in one go. Two
consequences:

- **"OCR found this keyword for the first time at t=X" is not when the action happened.** The text
  may have been visible for 20 s or appeared all at once.
- Caption timeline built this way sits still while the operator has already moved two steps ahead.
  A reviewer put it exactly right: "the user has already picked 2 and your caption is still on the
  previous content."

**What is reliable** — the bottom-edge focus text, i.e. the last thing in the viewport:

| Signal | Reads as |
|---|---|
| Operator bubble appearing on the right | a message was just sent |
| Composer text growing character by character (`accept and` → `accept and apply`) | typing, seconds before sending |
| The composer placeholder *disappearing* | typing just started |
| Processing-state rotation (`Processing your…` → `Finalizing your response` → `Thinking` → `Starting agent request`) | request in flight, then the next turn |
| A new button (`Add as Successor`, `Submit`) appearing at the bottom | the agent finished answering |

Recipe: `scripts/audit_actions.py --base videos --ocr scripts/ocr.sh clip.mp4`, then read
`## status changes` top to bottom — each line is a moment you can hang a cue on.

#### When a human reports a specific moment

The person who watched the video is the ground truth; a screenshot outranks any amount of frame
analysis. Workflow:

1. Get the timestamp (and the screenshot, if offered).
2. Locate that exact second in your burned file — extract candidate frames and match the
   screenshot's panel state, rather than trusting the stated second.
3. Fix **the whole video** with that evidence, not just the one cue: the misalignment is systemic,
   the reported moment is only its most visible symptom.
4. Report back with the verification frame from that same second. "Fixed at 0:23, here is what it
   now shows" ends the loop; "re-timed the timeline" restarts it.


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

Once the copy is approved, generate the `.ass` instead of typing styles by hand:

```sh
scripts/md_to_ass.py copy.md subs.ass config.json     # table of cues in, two-layer .ass out
```

The config carries PlayRes, font, line width, anchors and an optional per-cue `timing` override
(`null` keeps the copy's time, `[0,0]` drops the cue) — so re-timing after Phase 2.5 is a JSON
edit plus one command, and the halo/outline/colour triples are never retyped (see trap 17).


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

### Phase 8 — Delivery (site, app, or offline bundle)

When the videos are consumed by a page rather than a person, the burn output is not the deliverable
— the *served* file is.

1. **Do not infer the served path from the disk layout.** Grep the front-end bundle for the asset
   base instead of guessing: `grep -o 'videos/[^"]*' site/index-*.js`, then look at the variable it
   is prefixed with. A bundle base of `pod/` means the player requests `site/pod/videos/…` — while
   copies of the same files may sit in a sibling folder that nothing references. Replacing the
   wrong copy looks successful and changes nothing on screen.
2. **Replace in place, keep the filename identical.** Dropping the `_subtitled`/`_字幕版` suffix is
   the whole point: the page keeps working, no markup changes, and the swap is reversible from the
   original masters.
3. **Verify through the server, not the filesystem.** Start it, then confirm the response is media
   and supports seeking:
   `curl -sI http://127.0.0.1:PORT/pod/videos/assistants/Name.mp4` → `200`,
   `Content-Type: video/mp4`, `Accept-Ranges: bytes`. A file on disk proves nothing about what the
   player receives.
4. **Extract a burned frame from the deployed copy.** One frame at the timestamp that previously
   went wrong proves both that the new render is live and that it is correctly timed.
5. **Leave the gaps visible.** If some videos in the folder have no subtitle version, list which
   ones instead of silently shipping a mixed set.

The win this unlocks is the reason to do it at all: an offline mirror with burned subtitles needs no
network, so a booth or a customer site can run the whole demo from a local folder.


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
10. **Cue times from frame-sequence estimates run ahead of the UI.** Observed +9.5s on a
    loading-heavy demo. Re-measure every referenced action at 2 fps (Phase 2.5) before burning,
    and confirm "caption and action in the same frame" afterwards.
11. **Whisper hallucinates on music-only audio.** "Come To" loops, "Thank you." on silent demos.
    Classify by word count + unique-word ratio (< 0.35 → music), never by the raw transcript.
12. **Numbers quoted from the screen get misread.** USG10001 vs US010001 (G/0); "3/5" vs "3/3".
    Crop-zoom and read character-by-character, and cross-check the arithmetic — one demo's own
    on-screen text was internally inconsistent (3−1 ≠ a "4-point spread"; the case-detail value
    was the correct one).
13. **Verify frames need output seeking.** `ffmpeg -i OUT.mp4 -ss t`; input seeking (`-ss t -i`)
    showed ~2s-stale frames on a re-encoded output and nearly triggered a wrong re-timing.
14. **One PlayRes design space fits every frame size.** A 1600×900 PlayRes scaled cleanly to
    1600×900, 1920×1080, 1912×944 and 1280×720 sources. Confirm the source resolution, keep the
    coordinates.
15. **Line width must fit the reserved zone.** width ≈ chars × fontsize: an 8-char line at
    fontsize 76 is 608 px — clipped at the frame edge when the free zone is 460 px. Re-wrap to
    ≤ zone/fontsize chars per line and re-check on a verify frame.
16. **Kinetic-typography brand films.** The caption is the translation of the on-screen text:
    below full-screen centered lines, beside left-side lines — never over the demo device.
17. **Text-style PrimaryColour is the white fill** (&H00FFFFFF). Filling it with the outline
    colour renders purple blobs — invisible in the .ass, obvious on a verify frame. Always
    generate styles from a checked template, never hand-type colour triples twice.
18. **VFR sources silently corrupt `fps`-filter analysis frames.** A screen recording with
    11476 frames over 186 s (30 fps early, ~65 fps late) produced `fps=2` frames whose nominal
    time drifted up to 8 s ahead of real playback — captions burned 8 s early mid-video.
    Detect it first: frame count (`-vf showinfo -f null -` + count) vs duration × banner fps;
    mismatch > ~5 % ⇒ VFR. For VFR, extract analysis frames by **real pts**:
    `ffmpeg -i IN -vf "select='floor(t/2)>floor(prev_t/2)'" -fps_mode vfr out_%04d.jpg`
    (one frame per 2 real seconds), and pin boundaries with `select='gte(t,T)*lt(t,T+0.08)'`.
    Cross-check every phase transition against burned-output seek frames, which are always
    real-time.
19. **In an accumulating chat viewport, "text first appeared" is not the action time.** The
    conversation never clears, and a long answer card paints its later lines all at once, so a
    keyword can be visible 20 s before or after the click it seems to describe. Three successive
    re-timing passes failed this way; the proof was a reviewer's screenshot showing the operator
    already on step 3 while the caption still described step 1. Use the bottom-edge focus text and
    the right-side bubble (Phase 2.5), never a keyword map.
20. **Re-aligning in the wrong direction makes it worse.** If the copy was authored against the
    real video, a "drift correction" can push every cue 3–8 s late. Measure the sign first: compare
    one known action against its cue before touching the rest.
21. **A contact sheet is for spotting *where* something changed, never for reading it.** Eight
    1280×720 frames tiled into one 2560 px image makes UI text and captions illegible — you will
    "verify" misread text. Crop the panel and scale it up (≥ 700 px wide for one panel) before
    claiming a frame is checked.
22. **`ffprobe` may be missing while `ffmpeg` is present** (static builds, minimal PATH). Probe with
    `ffmpeg -i file 2>&1 | grep -oE '[0-9]{3,4}x[0-9]{3,4}'` and read codec from
    `grep -o 'Video: [^,]*'`. Do not let a missing probe tool turn into "I could not verify".
23. **The served asset path is not the disk layout.** A front-end bundle base (`pod/`) can point at
    a completely different folder from the one you copied into, and duplicated files in a sibling
    directory make the wrong choice look plausible. Grep the bundle, then confirm over HTTP.
24. **The composer placeholder is chrome, not content.** "Message HR Service Assistant…" is present
    in every frame of a chat demo, so it dominates the OCR fingerprint — but its *disappearance* is
    exactly what marks typing start. Read it as a state change, not as noise to be filtered.

## Batch mode (10+ videos in one series)

A 38-video product series is not 38 hand-crafted jobs; it is one pipeline run 38 times, with the
per-video differences held in data. Structure it so a re-timing pass costs minutes, not hours:

1. **One config file per video**, never one global config:
   `cfg_<slug>.json` with `W/H`, font, anchors, `text_col`, `has_title`, `linebreaks`, `timing`.
   Same style block across the series; only geometry and timing vary.
2. **Generate all `.ass` from the copy tables in one loop**, then spot-check by eye before burning.
   A wrong `text_col` in one config silently ships the wrong language column — filter the table
   for review markers (`⚠`, `►`) and placeholder rows first.
3. **Patch timings by cue index**, not by editing generated files:
   `{"Talent_Scouting_Agent": {4: [17.0, 25.8], 5: [26.0, 32.8]}}` → write into each `timing`
   array → regenerate → burn. This keeps the diff reviewable and reversible.
4. **Burn serially, verify in labelled sheets.** Burning in parallel looks faster until two jobs
   contend for the same disk and one silently produces a truncated file. After burning, extract the
   boundary frames (one frame per changed transition) into a contact sheet with labels, and read it.
5. **Keep the previous cut until the new one is verified.** Render as `_v2.mp4`, check, then
   `mv` over the final name — and delete the variant afterwards, or the folder fills with
   unlabelled near-duplicates that no one can tell apart a week later.
6. **Report per video, not per batch.** A table of "what was wrong → what it is now" lets the
   reviewer check the two or three that matter instead of re-watching forty.

The cheap failure mode to avoid: burning all forty, then discovering the style was wrong for all
forty. Burn two, get approval, then run the rest.

## Companion use: presenter script

The same cue table doubles as a reading script for a human who will talk over the video: dump
`| screen time | cue text | duration | density |` and the presenter reads what is on screen
instead of memorizing separate copy. Keep the two in sync by exporting from the final `.ass`,
never by retyping.

## Verification checklist

- [ ] Every cue's text appears on screen at the intended time in the **finished** file
- [ ] Caption and the UI action it describes appear in the **same frame** (checked with output seeking)
- [ ] Numbers quoted from the screen read character-by-character from a crop-zoomed frame
- [ ] No cue overlaps the demo panel or runs off-frame
- [ ] No cue crosses a transition
- [ ] Densest cue ≤ 5.5 CJK chars/s (or ≤ 18 Latin chars/s)
- [ ] Halo reads cleanly over both light and dark backgrounds
- [ ] Duration, resolution and audio track of the output match the intent
- [ ] Timing calibrated against the **action timeline**, not against when text first appeared
- [ ] Any moment a reviewer called out is re-checked in the final file at that same second
- [ ] For a batch: no `_v2` / `_v3` variants left behind, and the folder count matches the source
- [ ] For a site/app delivery: the served file returns `200` + `video/mp4` and a burned frame was
      read back from the deployed copy

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

## Harness notes (WorkBuddy vs Claude Code)

The pipeline is harness-agnostic; only how a script path resolves differs.

| Harness | Install path | Calling scripts |
|---|---|---|
| WorkBuddy | `~/.workbuddy/skills/demo-video-subtitler/` | `scripts/burn.sh ...` (resolved against the skill directory) |
| Claude Code | `~/.claude/skills/demo-video-subtitler/` | `${CLAUDE_SKILL_DIR}/scripts/burn.sh ...` — the shell CWD moves when the agent runs `cd`, so a bare relative path can drift |

The `allowed-tools` entry in this file's frontmatter pre-approves `${CLAUDE_SKILL_DIR}/scripts/*`
plus `ffmpeg`, `python3` and `chmod`, so Claude Code runs the bundled scripts without a permission
prompt on every call. Other harnesses ignore that field.

Frontmatter portability: only `name`, `description`, `license`, `compatibility`, `metadata` and
`allowed-tools` are accepted outside Claude Code (claude.ai upload, Skills API, packaging tools) —
anything else is a **hard error** there, silently ignored in Claude Code. That is why `version`,
`slug`, `displayName` and `summary` live under `metadata:` rather than at the top level.

## Sharing / install

This skill is self-contained: `SKILL.md`, `assets/caption-template.ass`, and these scripts
(`doctor.sh` is the entry point — run it on the target machine first):

| Script | Role |
|---|---|
| `doctor.sh` | environment check (ffmpeg+libass, fontconfig, CJK font) |
| `bootstrap.sh` | installs what is missing, idempotent |
| `probe.sh` | duration / resolution / fps / audio inventory |
| `split_frames.sh` | analysis frame extraction |
| `find_edge.sh` | panel edge measurement on a strip crop |
| `burn.sh` | ffmpeg + libass burn-in |
| `preview_frame.sh` | one still with the `.ass` applied |
| `export_cues.py` | cue table with reading-speed density |
| `md_to_ass.py` | copy table → two-layer `.ass` (implements Phases 3–5) |
| `audit_actions.py` | action timeline from 1 fps OCR (implements Phase 2.5) |
| `ocr.sh` / `ocr_box.swift` | macOS Vision OCR **with coordinates**, compiled on first use |

Only `ocr.sh` / `ocr_box.swift` and therefore `audit_actions.py --ocr` are macOS-only (they need
`swiftc` from Xcode command line tools); everything else is platform-neutral.

- **WorkBuddy**: copy the folder to `~/.workbuddy/skills/demo-video-subtitler/`
  (project-scoped alternative: `<repo>/.workbuddy/skills/`).
- **Claude Code**: copy to `~/.claude/skills/demo-video-subtitler/`, then
  `chmod +x scripts/*.sh scripts/*.py` — a zip unpacked by some tools loses the executable bit,
  and every script fails with "permission denied" until it is restored.
- Requirements on the receiving machine: `ffmpeg` built with libass + fontconfig, and at least
  one CJK font fontconfig can resolve. Everything else is bash + python3 standard library.
- Pack for distribution: `cd ~/.workbuddy/skills && zip -r demo-video-subtitler.zip demo-video-subtitler -x '*.DS_Store'`
