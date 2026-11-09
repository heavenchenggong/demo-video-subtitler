# demo-video-subtitler

An agent skill that turns a screen-recorded product demo into a captioned, shareable video:
analyse the recording, write the caption copy, style it, place it so it never hides the thing
being demonstrated, and burn it in with ffmpeg.

Built for the case where a demo is silent (or its audio is only background music) and its UI is
in the wrong language for the audience — the caption has to carry the whole story.

## What it does

| Phase | Output |
|---|---|
| 1. Inventory | duration, resolution, and whether the audio is speech, music, or nothing |
| 2. Visual analysis | beat sheet, verbatim on-screen UI text, pixel map of the demo panel |
| 2.5 Timing calibration | every cue pinned to the moment the operator actually acted — not to when text appeared |
| 3. Caption copy | one idea per cue, measured against a per-script reading-speed budget |
| 4. Style | white text, thick coloured outline, soft halo (two ASS layers) |
| 5. Placement | anchored next to the current focus — beside a side panel, under a toast, in a measured gap |
| 6. Burn-in | hard subtitles via libass; the source audio track is preserved |
| 7. Verify | frame-level checks for occlusion, clipping, and reading speed |
| 8. Delivery | swap the burned file into a site or offline mirror, verify through the server |

Also covered: **batch mode** for a 10–40 video series (one config per video, timing patched by cue
index, burn serially, verify in labelled sheets), and the **accumulating-viewport trap** — in an
agent console the whole conversation stays on screen, so "OCR found this keyword at t=X" is not
when the click happened. That single mistake cost three re-timing passes.

## Quick start

```sh
git clone <this repo> && cd demo-video-subtitler

scripts/bootstrap.sh --dry-run     # what is missing on this machine?
scripts/bootstrap.sh               # install it (asks once)

scripts/probe.sh my-demo.mp4       # inventory
scripts/split_frames.sh my-demo.mp4 frames/ 2
scripts/doctor.sh zh               # ffmpeg+libass, fontconfig, a CJK font
scripts/preview_frame.sh my-demo.mp4 subs.ass 16.0 check.jpg
scripts/burn.sh my-demo.mp4 subs.ass out.mp4
scripts/export_cues.py subs.ass --lang zh   # cue table + reading-speed audit

# calibration and generation (new in 1.2.0)
scripts/audit_actions.py --base . --ocr scripts/ocr.sh my-demo.mp4   # action timeline
scripts/md_to_ass.py copy.md subs.ass config.json                    # copy table -> .ass
```

## Requirements

One hard requirement: **ffmpeg built with libass**. `bootstrap.sh` installs it via the platform
package manager, or drops a static build into `~/.local/bin` when there is none. Fontconfig and a
font for the caption language are also needed; `python3` is optional (standard library only).

`ocr.sh` / `audit_actions.py` are macOS-only: they use the Vision framework through `swiftc`
(Xcode command line tools) to read on-screen text **with coordinates**, which is what separates an
operator's chat bubble from the assistant's reply. On other platforms the agent's own vision can
read the extracted frames — the frames are written either way.

## Languages

The pipeline is language-agnostic. Timecodes, styling, and placement work the same for Chinese,
Japanese, Korean, Latin, and RTL scripts; what changes is the font family, the reading-speed budget,
and the line-width calculation. See "Phase 3b" in `SKILL.md` for the tables.

## Files

```
SKILL.md                        the full pipeline, including 24 traps that cost real time
scripts/bootstrap.sh            idempotent installer: check, then install what is missing
scripts/doctor.sh               environment self-check (ffmpeg, libass, fontconfig, font, python)
scripts/probe.sh                inventory + audio classification
scripts/split_frames.sh         frame extraction for the beat sheet
scripts/find_edge.sh            measure a panel edge at source resolution
scripts/preview_frame.sh        single-frame render for style/placement review
scripts/burn.sh                 burn the .ass into the video, keep the audio
scripts/export_cues.py          cue table with per-cue reading density (RUSHED flags)
scripts/md_to_ass.py            copy table -> two-layer .ass (implements phases 3-5)
scripts/audit_actions.py        action timeline from 1 fps OCR (implements phase 2.5)
scripts/ocr.sh                  macOS Vision OCR with coordinates, compiled on first use
scripts/ocr_box.swift           the OCR source ocr.sh compiles
assets/caption-template.ass     commented style template, ready to parameterise
assets/config-example.json     worked example for md_to_ass.py (geometry, timing overrides)
```

## Changelog

- **1.2.0** — action-timeline calibration for chat/agent UIs (`audit_actions.py`, `ocr.sh`), the
  two-direction drift model (cues can run late, not just early), `md_to_ass.py` generator, batch
  mode for 10–40 video series, delivery into an offline site, traps 19–24.
- **1.1.0** — timing calibration (phase 2.5), music-hallucination classification, eight production
  traps from a 40-video batch.
- **1.0.2** — Claude Code compatibility (`${CLAUDE_SKILL_DIR}` paths, frontmatter portability).
- **1.0.1** — first public version: caption pipeline for screen-recorded demos.

## Install as a skill

- WorkBuddy: copy the folder to `~/.workbuddy/skills/demo-video-subtitler/`
- Claude Code: copy to `~/.claude/skills/demo-video-subtitler/`, then
  `chmod +x scripts/*.sh scripts/*.py`

## Notes

- The `.ass` file is the source of truth. Re-render after a text or position tweak; never hand-edit
  a burned video.
- Prefer system fonts (Hiragino, Noto CJK, Malgun Gothic) when the output will be shared — font
  licensing travels with the file.

## License

MIT — see `LICENSE`.
