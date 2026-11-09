#!/usr/bin/env python3
"""Subtitle copy table (.md) -> two-layer .ass in the demo-video-subtitler style.

This is the reference implementation of Phases 3-5: it does the read-speed-independent line
wrapping, the title card, the focus anchor, and the halo+text double layer, so the style is never
hand-typed twice (trap 17).

Usage: python3 md_to_ass.py <copy.md> <out.ass> <config.json>

Expected .md shape — a pipe table, one row per cue, first column the time range:

    | 0:00-0:03 | Winston Companion | 温斯顿助手 |
    | 0:03-0:07 | It found the gap  | 它发现了缺口 |

config.json:
  W, H         source resolution (PlayRes; required)
  font         font family fontconfig resolves (default "Hiragino Sans GB")
  fs, tfs      body / title font size (default 80 / 72, scaled by H/1080)
  maxw         max line width in Han-character units (Latin/digits count 0.55)
  body_x       right-anchor x for body cues (default W-150)
  body_y       anchor y (default H*0.58)
  title_y      title-card anchor y (default H*0.66)
  text_col     which column holds the caption text (default 1)
  has_title    treat cue 0 as a title card, centred (default true)
  body_center  centre body cues horizontally instead of right-anchoring (narration films)
  linebreaks   {"cue text": ["line 1", "line 2"]} manual wrap override for the ugly ones
  timing       per-cue time override: [[start,end], ...] (seconds)
               null = keep the .md time · [0,0] or [] = drop the cue
"""
import json
import re
import sys


def to_sec(s):
    s = s.strip()
    if ":" in s:
        m, rest = s.split(":", 1)
        return int(m) * 60 + float(rest)
    return float(s)


def ass_time(t):
    h = int(t // 3600)
    m = int((t % 3600) // 60)
    s = t % 60
    return f"{h}:{m:02d}:{s:05.2f}"


def cw(ch):
    return 0.55 if ord(ch) < 128 else 1.0


def wrap(text, maxw):
    """按汉字宽断行：标点归上一行、英文/数字整体不拆、避免单字成行。

    允许 maxw*1.15 的弹性，用来换掉「处理」被拆成两行这种坏断点。
    """
    limit = maxw * 1.15
    # 短语：标点跟随前面的文字，不单独起行
    chunks = [c for c in re.findall(
        r"[^，。、：；！？]*[，。、：；！？]|[^，。、：；！？]+", text) if c]
    tokens_of = lambda s: re.findall(r"[A-Za-z0-9@._%+\-]+|[^\x00-\x7f]|.", s)
    lines, cur, w = [], "", 0.0
    for ch in chunks:
        c_width = sum(cw(c) for c in ch)
        if cur and w + c_width <= limit:
            cur += ch
            w += c_width
            continue
        if cur:
            lines.append(cur.strip())
            cur, w = "", 0.0
        if c_width <= limit:
            cur, w = ch, c_width
        else:
            for t in tokens_of(ch):
                tw = sum(cw(c) for c in t)
                # 标点永远粘在上一行末尾，绝不单独成行
                if t in "，。、：；！？" and cur:
                    cur += t
                    w += tw
                    continue
                if cur and w + tw > limit:
                    lines.append(cur.strip())
                    cur, w = "", 0.0
                cur += t
                w += tw
    if cur.strip():
        lines.append(cur.strip())
    # 末行只剩一个字：并回上一行，或从上一行借一个字下来
    if len(lines) > 1 and sum(cw(c) for c in lines[-1]) <= 1.5:
        last = lines.pop()
        prev = lines[-1]
        if sum(cw(c) for c in prev) + sum(cw(c) for c in last) <= limit * 1.35:
            lines[-1] = prev + last
        else:
            lines[-1] = prev[:-1]
            lines.append(prev[-1] + last)
    return lines


def parse_rows(md_path, text_col=1):
    rows = []
    with open(md_path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line.startswith("|") or line.startswith("|---"):
                continue
            cols = [c.strip() for c in line.strip("|").split("|")]
            if len(cols) <= text_col:
                continue
            tm, text = cols[0], cols[text_col]
            if not re.match(r"^\d", tm) or "–" not in tm and "-" not in tm:
                continue
            # 跳过占位行：整格只有一个括号注释，例如「（片尾音乐，无解说）」「(music outro)」
            if re.fullmatch(r"[（(][^）)]*[）)]", text):
                continue
            if any(w in text for w in ("无字幕", "无解说", "(music outro)")):
                continue
            # 去掉审阅标记，例如文案里手写的「⚠️超速」
            text = re.sub(r"\s*[⚠►→].*$", "", text).strip()
            if not text:
                continue
            parts = re.split(r"\s*[–—-]\s*", tm, maxsplit=1)
            if len(parts) != 2:
                continue
            try:
                start, end = to_sec(parts[0]), to_sec(parts[1])
            except ValueError:
                continue
            rows.append((start, end, text))
    return rows


def main():
    md_path, out_path, cfg_path = sys.argv[1:4]
    cfg = json.load(open(cfg_path, encoding="utf-8"))
    W, H = cfg["W"], cfg["H"]
    font = cfg.get("font", "Hiragino Sans GB")
    fs = cfg.get("fs") or max(24, round(80 * H / 1080))
    tfs = cfg.get("tfs") or max(20, round(72 * H / 1080))
    maxw = cfg.get("maxw", 7)
    body_x = cfg.get("body_x") or W - 150
    body_y = cfg.get("body_y") or round(H * 0.58)
    title_y = cfg.get("title_y") or round(H * 0.66)

    outline = round(fs / 11.4, 1)
    halo = round(fs / 6.7, 1)
    blur = round(fs / 6.7, 1)
    t_outline = round(tfs / 11.4, 1)
    t_halo = round(tfs / 6.7, 1)

    head = f"""[Script Info]
; generated by md_to_ass.py — demo-video-subtitler two-layer style
ScriptType: v4.00+
PlayResX: {W}
PlayResY: {H}
ScaledBorderAndShadow: yes
WrapStyle: 0

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Main,{font},{fs},&H00FFFFFF,&H00FFFFFF,&H00F02E7C,&H00000000,-1,0,0,0,100,100,1,0,1,{outline},0,2,60,60,60,1
Style: Halo,{font},{fs},&HFF000000,&HFF000000,&H55F02E7C,&H00000000,-1,0,0,0,100,100,1,0,1,{halo},0,2,60,60,60,1
Style: TitleMain,{font},{tfs},&H00FFFFFF,&H00FFFFFF,&H00F02E7C,&H00000000,-1,0,0,0,100,100,1,0,1,{t_outline},0,2,60,60,60,1
Style: TitleHalo,{font},{tfs},&HFF000000,&HFF000000,&H55F02E7C,&H00000000,-1,0,0,0,100,100,1,0,1,{t_halo},0,2,60,60,60,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    text_col = cfg.get("text_col", 1)
    has_title = cfg.get("has_title", True)
    rows = parse_rows(md_path, text_col)
    timing = cfg.get("timing")
    if timing:
        if len(timing) != len(rows):
            # A shorter array is normal (patch only the cues that moved); extra entries are ignored.
            print(f"note: timing has {len(timing)} entries, {len(rows)} cues — "
                  f"missing kept as-is, extra ignored", file=sys.stderr)
        revised = []
        for i, (s, e, t) in enumerate(rows):
            ov = timing[i] if i < len(timing) else None
            if ov is None:
                revised.append((s, e, t))
            elif len(ov) == 2 and float(ov[1]) > float(ov[0]):
                revised.append((float(ov[0]), float(ov[1]), t))
            # 空项 = 跳过该 cue
        rows = revised
    events = []
    for i, (start, end, text) in enumerate(rows):
        is_title = has_title and i == 0
        if is_title:
            text = re.sub(r"（[^）]*）", "", text).strip()
            lines = [text] if sum(cw(c) for c in text) <= 12 else wrap(text, 12)
            pos = f"{{\\an5\\pos({W // 2},{title_y})}}"
            hs, ms, blur_tag = "TitleHalo", "TitleMain", f"{{\\blur{t_halo}}}"
        else:
            lines = cfg.get("linebreaks", {}).get(text) or wrap(text, maxw)
            if cfg.get("body_center"):
                # 旁白片 / 画面底部留白型：整块居中放在画面下部，避开居中标题
                pos = f"{{\\an5\\pos({W // 2},{body_y})}}"
            else:
                pos = f"{{\\an6\\pos({body_x},{body_y})}}"
            hs, ms, blur_tag = "Halo", "Main", f"{{\\blur{blur}}}"
        body = "\\N".join(lines)
        st, en = ass_time(start), ass_time(end)
        events.append(f"Dialogue: 0,{st},{en},{hs},,0,0,0,,{blur_tag}{pos}{body}")
        events.append(f"Dialogue: 1,{st},{en},{ms},,0,0,0,,{pos}{body}")

    with open(out_path, "w", encoding="utf-8") as f:
        f.write(head + "\n".join(events) + "\n")
    print(f"wrote {out_path}: {len(rows)} cues")
    for i, (s, e, t) in enumerate(rows):
        lines = (["(title)"] if (has_title and i == 0)
                 else (cfg.get("linebreaks", {}).get(t) or wrap(t, maxw)))
        print(f"  {ass_time(s)} -> {ass_time(e)}  {' / '.join(lines)}")


if __name__ == "__main__":
    main()
