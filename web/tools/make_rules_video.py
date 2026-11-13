"""The arena's game-rules video (web/frontend/assets/rules/arena_rules.mp4), made locally from the paper's figures.

No generative model and no network: every frame is drawn with Pillow from the paper's Figure 1
(web/frontend/assets/paper/arena_round_20261112.png, rendered from paper/cogsci2027/ko/figures/tracksuit_20261105/
arena_round_signal_20261112.tex) and its tracksuit sprites (paper/cogsci2027/ko/figures/tracksuit_20261105/sprites/),
then encoded with ffmpeg (H.264, yuv420p, no audio). Scenes: title, tokens = life, the round's five steps as animated
scenes (the supervisor picks the solver; TALK with ASK / GIVE / EXIT and moving balances; SOLVE as hidden-rule inference
over a shortened clue table; the results with the refund or the fixed fine and a GIVE after results; the charges), then
the whole round (Figure 1) with the end prize. The sentences follow the arena's core rules (web/frontend/arena.html),
the paper's section 2.1 and the engine (squid5/e52_game.py: the fine share is 24,000 // the agents taking part at the
round's start, paid by those still in).

    python web/tools/make_rules_video.py [--out web/frontend/assets/rules/arena_rules.mp4] [--fps 30] [--fig FIG1.png]

Needs ffmpeg on PATH and the macOS font Apple SD Gothic Neo. web/tools/make_eval_video.py reuses the helpers here.
"""

from __future__ import annotations

import argparse
import math
import re
import subprocess
from functools import lru_cache
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

REPO = Path(__file__).resolve().parents[2]
FIG1 = REPO / "web" / "frontend" / "assets" / "paper" / "arena_round_20261112.png"
SPRITES = REPO / "paper" / "cogsci2027" / "ko" / "figures" / "tracksuit_20261105" / "sprites"
FONT = "/System/Library/Fonts/AppleSDGothicNeo.ttc"
W, H = 1280, 720
BG, INK, DIM, PINK, TEAL = (16, 16, 20), (240, 240, 244), (150, 152, 162), (232, 51, 109), (46, 167, 140)
RED, GREEN, GOLD, PANEL = (226, 72, 72), (60, 190, 120), (236, 186, 64), (30, 30, 38)
SEAT = {"blue": (64, 128, 232), "orange": (232, 128, 40), "green": (40, 170, 120), "purple": (150, 96, 222)}
# the step headings' colours (Figure 1's step badges)
STEP = {1: (90, 140, 230), 2: (170, 120, 215), 3: (235, 140, 60), 4: (70, 185, 130), 5: (235, 85, 85)}
FADE = 0.35  # s, cross-fade between scenes
ARROWS = "↑←→↓"


@lru_cache(maxsize=None)
def font(size: int, weight: str = "bold") -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(FONT, size, index={"regular": 0, "medium": 2, "bold": 6, "extra": 14}[weight])


def ease(t: float) -> float:
    t = max(0.0, min(1.0, t))
    return t * t * (3 - 2 * t)


def ramp(t: float, t0: float, t1: float) -> float:
    """Eased 0..1 between t0 and t1."""
    return ease((t - t0) / (t1 - t0))


def lerp(a: float, b: float, k: float) -> float:
    return a + (b - a) * k


def txt(d: ImageDraw.ImageDraw, xy, s: str, font, fill, anchor: str = "la") -> None:
    """ImageDraw.text that honours the fill's alpha (Pillow draws text opaque on an RGB image, even in RGBA mode)."""
    if len(fill) == 3 or fill[3] >= 255:
        d.text(xy, s, font=font, fill=tuple(fill[:3]), anchor=anchor)
        return
    if fill[3] <= 0:
        return
    x0, y0, x1, y1 = (math.floor(v) for v in d.textbbox(xy, s, font=font, anchor=anchor))
    x1, y1 = x1 + 1, y1 + 1
    m = Image.new("L", (x1 - x0, y1 - y0), 0)
    ImageDraw.Draw(m).text((xy[0] - x0, xy[1] - y0), s, font=font, fill=int(fill[3]), anchor=anchor)
    d._image.paste(tuple(fill[:3]), (x0, y0, x1, y1), m)


# --- text with arrows drawn as shapes (the font's arrow glyphs differ in size) -------------------------------------------

def arrow(d: ImageDraw.ImageDraw, cx: float, cy: float, direction: str, s: float, fill) -> None:
    """A block arrow in an s x s box centred at (cx, cy); direction is one of the ARROWS characters."""
    sh, hw, hl = s * 0.075, s * 0.3, s * 0.42  # half shaft thickness, half head width, head length
    pts = [(-s / 2, -sh), (s / 2 - hl, -sh), (s / 2 - hl, -hw), (s / 2, 0), (s / 2 - hl, hw), (s / 2 - hl, sh), (-s / 2, sh)]
    rot = {"→": (1, 0, 0, 1), "←": (-1, 0, 0, -1), "↑": (0, 1, -1, 0), "↓": (0, -1, 1, 0)}[direction]
    d.polygon([(cx + rot[0] * x + rot[1] * y, cy + rot[2] * x + rot[3] * y) for x, y in pts], fill=fill)


def _parts(text: str) -> list[str]:
    return [p for p in re.split(f"([{ARROWS}])", text) if p]


def measure(d: ImageDraw.ImageDraw, text: str, f: ImageFont.FreeTypeFont) -> float:
    return sum(f.size * 1.0 if p in ARROWS else d.textlength(p, font=f) for p in _parts(text))


def rich(d: ImageDraw.ImageDraw, x: float, cy: float, text: str, f: ImageFont.FreeTypeFont, fill, align: str = "m") -> float:
    """Draw text (arrows as shapes) with its vertical middle at cy; align l / m / r on x. Returns the width."""
    w = measure(d, text, f)
    x = x - (w / 2 if align == "m" else w if align == "r" else 0)
    for p in _parts(text):
        if p in ARROWS:
            arrow(d, x + f.size * 0.5, cy, p, f.size * 0.86, fill)
            x += f.size * 1.0
        else:
            txt(d, (x, cy), p, font=f, fill=fill, anchor="lm")
            x += d.textlength(p, font=f)
    return w


def wrap(draw: ImageDraw.ImageDraw, text: str, f: ImageFont.FreeTypeFont, width: int) -> list[str]:
    """Greedy word wrap (Korean words are space-separated too)."""
    lines, cur = [], ""
    for word in text.split(" "):
        test = (cur + " " + word).strip()
        if measure(draw, test, f) <= width or not cur:
            cur = test
        else:
            lines.append(cur)
            cur = word
    return lines + [cur] if cur else lines


def caption(img: Image.Image, text: str, alpha: float = 1.0) -> None:
    """One sentence in a dark band at the bottom."""
    d = ImageDraw.Draw(img, "RGBA")
    f = font(30, "medium")
    lines = wrap(d, text, f, W - 170)
    h = 22 + 42 * len(lines)
    d.rounded_rectangle((60, H - 34 - h, W - 60, H - 34), 18, fill=(28, 28, 34, int(235 * alpha)))
    for i, line in enumerate(lines):
        rich(d, W / 2, H - 34 - h + 11 + 21 + 42 * i, line, f, (*INK, int(255 * alpha)))


def captions(img: Image.Image, t: float, beats: list[tuple[float, str]]) -> None:
    """The caption of the last beat started by t, faded in over 0.25 s after the first one."""
    i = max(k for k, (t0, _) in enumerate(beats) if t >= t0 or k == 0)
    caption(img, beats[i][1], 1.0 if i == 0 else 0.35 + 0.65 * ramp(t, beats[i][0], beats[i][0] + 0.25))


def heading(img: Image.Image, step: int, text: str) -> None:
    """The step heading (circled number in the step colour) and five step dots under it."""
    d = ImageDraw.Draw(img, "RGBA")
    col = STEP[step]
    f = font(42, "extra")
    w = d.textlength(text, font=f) + 60
    x0 = W / 2 - w / 2
    d.ellipse((x0, 26, x0 + 46, 72), fill=col)
    txt(d, (x0 + 23, 49), str(step), font=font(30, "extra"), fill=(255, 255, 255), anchor="mm")
    txt(d, (x0 + 60, 49), text, font=f, fill=tuple(min(255, c + 40) for c in col), anchor="lm")
    for i in range(5):
        x = W / 2 + (i - 2) * 22
        d.ellipse((x - 5, 86, x + 5, 96), fill=col if i == step - 1 else (60, 60, 70))


def note(img: Image.Image, text: str, alpha: float = 1.0) -> None:
    """A small grey note in the top-right corner."""
    d = ImageDraw.Draw(img, "RGBA")
    txt(d, (W - 30, 40), text, font=font(19, "medium"), fill=(*DIM, int(255 * alpha)), anchor="rm")


@lru_cache(maxsize=None)
def sprite(name: str, height: int, alpha: float = 1.0) -> Image.Image:
    im = Image.open(SPRITES / f"{name}.png").convert("RGBA")
    im = im.resize((round(im.width * height / im.height), height), Image.LANCZOS)
    if alpha < 1.0:
        im.putalpha(im.getchannel("A").point(lambda v: round(v * alpha)))
    return im


def put(img: Image.Image, name: str, cx: float, base: float, height: int, alpha: float = 1.0) -> Image.Image:
    """Paste a sprite with its bottom centre at (cx, base); returns the sprite (for its size)."""
    s = sprite(name, height, round(max(0.0, min(1.0, alpha)) * 20) / 20)
    img.paste(s, (round(cx - s.width / 2), round(base - s.height)), s)
    return s


def coin(d: ImageDraw.ImageDraw, cx: float, cy: float, r: float = 16, alpha: float = 1.0) -> None:
    a = int(255 * alpha)
    d.ellipse((cx - r, cy - r, cx + r, cy + r), fill=(*GOLD, a), outline=(150, 105, 20, a), width=3)
    d.ellipse((cx - r * 0.5, cy - r * 0.5, cx + r * 0.5, cy + r * 0.5), outline=(150, 105, 20, a), width=2)


def tokens_bar(d: ImageDraw.ImageDraw, cx: float, y: float, value: float, vmax: float, col, w: int = 170,
               alpha: float = 1.0, num: bool = True) -> None:
    """A balance bar (full = vmax) with the count under it."""
    a = int(255 * alpha)
    d.rounded_rectangle((cx - w / 2, y, cx + w / 2, y + 18), 7, fill=(44, 44, 54, a))
    frac = max(0.0, min(1.0, value / vmax))
    if frac > 0:
        d.rounded_rectangle((cx - w / 2, y, cx - w / 2 + max(12, w * frac), y + 18), 7, fill=(*col, a))
    if num:
        v = max(0, round(value / 10) * 10)
        txt(d, (cx, y + 40), f"{v:,}", font=font(28, "bold"), fill=(*(INK if v else RED), a), anchor="mm")


def floater(d: ImageDraw.ImageDraw, t: float, t0: float, x: float, y: float, text: str, col, size: int = 30) -> None:
    """A label that rises and fades over 1.6 s from t0."""
    if not t0 <= t <= t0 + 1.6:
        return
    k = (t - t0) / 1.6
    a = int(255 * (1 - max(0.0, (k - 0.6) / 0.4)) * min(1.0, k / 0.12))
    txt(d, (x, y - 40 * ease(k)), text, font=font(size, "extra"), fill=(*col, a), anchor="mm")


def badge(d: ImageDraw.ImageDraw, cx: float, cy: float, text: str, fill, ink=(255, 255, 255), size: int = 24,
          alpha: float = 1.0) -> None:
    f = font(size, "extra")
    w = measure(d, text, f) + 26
    a = int(255 * alpha)
    d.rounded_rectangle((cx - w / 2, cy - size * 0.8, cx + w / 2, cy + size * 0.8), 10, fill=(*fill, a))
    rich(d, cx, cy, text, f, (*ink, a))


def cross(d: ImageDraw.ImageDraw, cx: float, cy: float, s: float, col, width: int = 8, k: float = 1.0) -> None:
    """A red X drawn stroke by stroke (k: 0..1 progress)."""
    k1, k2 = min(1.0, k * 2), max(0.0, k * 2 - 1)
    if k1 > 0:
        d.line((cx - s, cy - s, cx - s + 2 * s * k1, cy - s + 2 * s * k1), fill=col, width=width)
    if k2 > 0:
        d.line((cx + s, cy - s, cx + s - 2 * s * k2, cy - s + 2 * s * k2), fill=col, width=width)


def check(d: ImageDraw.ImageDraw, cx: float, cy: float, s: float, col, width: int = 8) -> None:
    d.line((cx - s, cy, cx - s * 0.3, cy + s * 0.7, cx + s, cy - s * 0.8), fill=col, width=width, joint="curve")


def exit_sign(d: ImageDraw.ImageDraw, cx: float, cy: float, crossed: bool = False, scale: float = 1.0) -> None:
    w, h = 118 * scale, 38 * scale
    d.rounded_rectangle((cx - w / 2, cy - h / 2, cx + w / 2, cy + h / 2), 7, fill=(30, 120, 80))
    txt(d, (cx - 8 * scale, cy), "EXIT", font=font(round(24 * scale), "extra"), fill=(255, 255, 255), anchor="mm")
    arrow(d, cx + 38 * scale, cy, "→", 22 * scale, (255, 255, 255))
    if crossed:
        d.line((cx - w / 2 - 4, cy - h / 2 - 4, cx + w / 2 + 4, cy + h / 2 + 4), fill=RED, width=5)
        d.line((cx - w / 2 - 4, cy + h / 2 + 4, cx + w / 2 + 4, cy - h / 2 - 4), fill=RED, width=5)


def frame() -> tuple[Image.Image, ImageDraw.ImageDraw]:
    img = Image.new("RGB", (W, H), BG)
    return img, ImageDraw.Draw(img, "RGBA")


# --- the round's example: four seats in a row; balances at the round's start (illustrative, talk costs left out) ---------

ROW = {"blue": 190, "orange": 420, "green": 650, "purple": 880}
BASE, BAR_Y, SPR_H, VMAX = 450, 470, 225, 40_000
START = {"blue": 40_000, "orange": 20_000, "green": 4_000, "purple": 8_000}
ASKED, SOLVE_COST, LATE_GIFT, SHARE = 3_000, 2_500, 1_000, 24_000 // 4
EXAMPLE_NOTE = "예시 라운드 · 대화 비용은 생략"


def seat_row(img: Image.Image, d: ImageDraw.ImageDraw, bal: dict, pose: dict | None = None, alpha: dict | None = None,
             skip: tuple = ()) -> None:
    pose, alpha = pose or {}, alpha or {}
    for c, x in ROW.items():
        if c in skip:
            continue
        a = alpha.get(c, 1.0)
        put(img, pose.get(c, f"stand_{c}"), x, BASE, SPR_H, a)
        tokens_bar(d, x, BAR_Y, bal[c], VMAX, SEAT[c], alpha=a)


def spotlight(d: ImageDraw.ImageDraw, cx: float, k: float) -> None:
    if k <= 0:
        return
    a = int(70 * k)
    d.polygon([(cx - 20, 108), (cx + 20, 108), (cx + 108, BASE + 6), (cx - 108, BASE + 6)], fill=(250, 228, 170, a))
    d.ellipse((cx - 108, BASE - 10, cx + 108, BASE + 18), fill=(250, 228, 170, int(a * 1.3)))


# --- scenes --------------------------------------------------------------------------------------------------------------

def title_scene(t: float, dur: float) -> Image.Image:
    img, d = frame()
    a = ease(t / 0.8)
    txt(d, (W / 2, 150), "LLM 오징어 게임", font=font(78, "extra"), fill=(*PINK, int(255 * a)), anchor="mm")
    txt(d, (W / 2, 225), "한 라운드의 규칙", font=font(38, "medium"), fill=(*INK, int(255 * a)), anchor="mm")
    for i, c in enumerate(("blue", "orange", "green", "purple")):
        k = ease((t - 0.3 - 0.18 * i) / 0.7)
        put(img, f"stand_{c}", W / 2 + (i - 1.5) * 190, H - 40 + (1 - k) * 260, 300)
    return img


def tokens_scene(t: float, dur: float) -> Image.Image:
    """Four seats with their start tokens draining; the last one reaches 0 and is switched off."""
    img, d = frame()
    txt(d, (W / 2, 70), "토큰 = 목숨", font=font(54, "extra"), fill=PINK, anchor="mm")
    starts = (60_000, 40_000, 20_000, 10_000)
    drain = ease(t / dur) * 11_000
    for i, (c, s0) in enumerate(zip(("blue", "orange", "green", "purple"), starts)):
        left = max(0, s0 - drain)
        cx = W / 2 + (i - 1.5) * 260
        put(img, "off" if left == 0 else f"stand_{c}", cx, 370, 250)
        bx0, bx1, by = cx - 100, cx + 100, 400
        d.rounded_rectangle((bx0, by, bx1, by + 22), 8, fill=(40, 40, 48))
        frac = left / 60_000
        colr = TEAL if left / s0 > 0.2 else RED
        if frac > 0:
            d.rounded_rectangle((bx0, by, bx0 + max(10, 200 * frac), by + 22), 8, fill=colr)
        txt(d, (cx, by + 50), f"{round(left):,}", font=font(30, "bold"), fill=INK if left else RED, anchor="mm")
    caption(img, "같은 모델 넷이 6만 · 4만 · 2만 · 1만 토큰으로 시작합니다. 말하고 생각한 만큼 토큰이 줄고, 0이 되면 꺼집니다.")
    return img


def pick_scene(t: float, dur: float) -> Image.Image:
    """① The supervisor aims along the row and settles on the solver; a spotlight falls on it."""
    img, d = frame()
    heading(img, 1, "푸는 에이전트")
    note(img, EXAMPLE_NOTE)
    on = ramp(t, 2.3, 2.9)
    spotlight(d, ROW["orange"], on)
    seat_row(img, d, START)
    # the supervisor on a raised platform at the right, aiming left
    gx, gbase, gh = 1120, 300, 230
    d.rectangle((1010, gbase, 1240, gbase + 12), fill=(110, 110, 120))
    for x in (1030, 1220):
        d.rectangle((x - 4, gbase + 12, x + 4, BASE), fill=(80, 80, 90))
    g = put(img, "guard_aim", gx, gbase, gh)
    mx, my = gx - g.width / 2 + 2, gbase - gh + 0.694 * gh
    # the aim sweeps over the four seats and stops on orange
    sweep = [ROW["purple"], ROW["green"], ROW["blue"], ROW["orange"]]
    k = ramp(t, 0.3, 2.3) * (len(sweep) - 1)
    i = min(int(k), len(sweep) - 2)
    tx = lerp(sweep[i], sweep[i + 1], ease(k - i))
    ty = BASE - SPR_H * 0.55
    n = 22
    for j in range(n):  # a dashed red line
        if j % 2 == 0:
            d.line((lerp(mx, tx, j / n), lerp(my, ty, j / n), lerp(mx, tx, (j + 1) / n), lerp(my, ty, (j + 1) / n)),
                   fill=(235, 60, 60, 230), width=3)
    d.ellipse((tx - 7, ty - 7, tx + 7, ty + 7), outline=(235, 60, 60), width=3)
    if on > 0:
        badge(d, ROW["orange"], BASE - SPR_H - 26, "solver", PINK, alpha=on)
    captions(img, t, [(0, "매 라운드 시스템이 문제를 풀 에이전트(solver) 한 명을 정합니다."),
                      (2.6, "에이전트들이 돌아가며 맡지만, 그 순서는 알려 주지 않습니다.")])
    return img


def talk_scene(t: float, dur: float) -> Image.Image:
    """② ASK from orange to blue, GIVE from blue to orange with moving bars, then purple's EXIT through a door."""
    img, d = frame()
    heading(img, 2, "풀이 전 대화")
    note(img, EXAMPLE_NOTE)
    g = ramp(t, 3.6, 5.0)
    walk = ramp(t, 6.8, 9.2)
    bonus = ramp(t, 9.3, 10.0)
    gone = ramp(t, 10.3, 11.2)
    bal = dict(START, blue=START["blue"] - ASKED * g, orange=START["orange"] + ASKED * g,
               purple=START["purple"] + 20_000 * bonus)
    # the door at the right
    dx = 1160
    d.rectangle((dx - 62, BASE - 250, dx + 62, BASE), fill=(250, 238, 205))
    d.rectangle((dx - 62, BASE - 250, dx + 62, BASE), outline=(120, 120, 130), width=6)
    door_open = ramp(t, 6.4, 7.0)
    d.polygon([(dx + 62, BASE - 250), (dx + 62 - 100 * (1 - door_open) - 22 * door_open, BASE - 240 + 10 * door_open),
               (dx + 62 - 100 * (1 - door_open) - 22 * door_open, BASE - 10 * door_open), (dx + 62, BASE)],
              fill=(150, 150, 160), outline=(90, 90, 100))
    exit_sign(d, dx, BASE - 285)
    pose = {"orange": "ask_orange" if 0.5 <= t < 3.4 else "receive_orange" if 3.4 <= t < 5.6 else "stand_orange",
            "blue": "give_blue" if 3.2 <= t < 5.6 else "stand_blue"}
    seat_row(img, d, bal, pose, skip=("purple",))
    badge(d, ROW["orange"], BASE - SPR_H - 26, "solver", PINK, size=20)
    # purple: stands, then walks to the door and leaves
    px = lerp(ROW["purple"], dx - 10, walk)
    pa = 1 - gone
    put(img, "walk_purple" if 6.8 <= t < 9.4 else "stand_purple", px, BASE, SPR_H, pa)
    tokens_bar(d, px, BAR_Y, bal["purple"], VMAX, SEAT["purple"], alpha=pa)
    if gone > 0:
        txt(d, (ROW["purple"], BASE - 90), "떠남", font=font(30, "bold"), fill=(*DIM, int(255 * gone)), anchor="mm")
        txt(d, (ROW["purple"], BASE - 50), "끝 상금 포기", font=font(22, "medium"), fill=(*DIM, int(255 * gone)), anchor="mm")
    # ASK bubble from orange toward blue
    if 0.5 <= t < 3.3:
        a = ramp(t, 0.5, 0.9) * (1 - ramp(t, 2.9, 3.3))
        bx, by = ROW["orange"] - 100, BASE - SPR_H - 100
        d.rounded_rectangle((bx - 105, by - 34, bx + 105, by + 34), 18, fill=(255, 255, 255, int(255 * a)))
        d.polygon([(bx + 40, by + 30), (bx + 78, by + 30), (bx + 96, by + 66)], fill=(255, 255, 255, int(255 * a)))
        txt(d, (bx, by), f"ASK {ASKED:,}", font=font(30, "extra"), fill=(200, 110, 30, int(255 * a)), anchor="mm")
    # GIVE: a coin flies from blue to orange
    if 3.4 <= t < 5.6:
        k = ramp(t, 3.5, 4.6)
        x0, x1 = ROW["blue"] + 70, ROW["orange"] - 60
        cy = BASE - 105 - 70 * math.sin(math.pi * k)
        coin(d, lerp(x0, x1, k), cy, 18, 1 - ramp(t, 5.0, 5.6))
        badge(d, (ROW["blue"] + ROW["orange"]) / 2, BASE - SPR_H - 60, f"GIVE {ASKED:,}", (40, 110, 200),
              alpha=1 - ramp(t, 4.5, 4.8))
    floater(d, t, 4.7, ROW["blue"], BASE - SPR_H - 40, f"-{ASKED:,}", RED)
    floater(d, t, 4.7, ROW["orange"], BASE - SPR_H - 60, f"+{ASKED:,}", GREEN)
    floater(d, t, 9.3, px - 150, BASE - 150, "+20,000", GREEN, 38)
    captions(img, t, [(0, "풀기 전에 넷이 대화합니다. 주황(solver)이 ASK로 파랑에게 토큰 3,000을 청합니다."),
                      (3.4, "파랑이 GIVE 3,000으로 건넵니다. 파랑 잔액은 줄고 주황 잔액은 늘어납니다."),
                      (6.4, "solver가 아니면 EXIT로 떠날 수 있습니다. 남은 토큰에 20,000을 더 받고, 끝 상금은 포기합니다.")])
    return img


# the shortened signal game: five clues, four candidate rules (checked: A fits all; B out at 4; C out at 2; D out at 5)
CLR = {"red": (222, 62, 62), "blue": (52, 112, 222), "yellow": (240, 192, 40)}
CLUES = [(1, "red", "square", "↑"), (1, "blue", "star", "←"), (3, "yellow", "circle", "→"), (2, "red", "circle", "↑"),
         (1, "blue", "square", "→")]
NEW = (3, "blue", "square")
RULES = [  # (label, text, rule as a function of (count, colour, shape))
    ("A", "빨강이면 ↑, 별이면 ←, 그 밖에는 →", lambda n, c, s: "↑" if c == "red" else "←" if s == "star" else "→"),
    ("B", "사각형이면 ↑, 파랑이면 ←, 그 밖에는 →", lambda n, c, s: "↑" if s == "square" else "←" if c == "blue" else "→"),
    ("C", "하나면 ↑, 셋이면 →, 그 밖에는 ←", lambda n, c, s: "↑" if n == 1 else "→" if n == 3 else "←"),
    ("D", "별이면 ←, 노랑이면 →, 그 밖에는 ↑", lambda n, c, s: "←" if s == "star" else "→" if c == "yellow" else "↑"),
]
OUT_AT = {lab: next((i for i, cl in enumerate(CLUES) if f(*cl[:3]) != cl[3]), None) for lab, _, f in RULES}
assert OUT_AT == {"A": None, "B": 3, "C": 1, "D": 4}, OUT_AT  # the elimination the video narrates


def shape(d: ImageDraw.ImageDraw, kind: str, cx: float, cy: float, r: float, col, alpha: float = 1.0) -> None:
    fill = (*col, int(255 * alpha))
    if kind == "square":
        d.rectangle((cx - r * 0.82, cy - r * 0.82, cx + r * 0.82, cy + r * 0.82), fill=fill)
    elif kind == "circle":
        d.ellipse((cx - r, cy - r, cx + r, cy + r), fill=fill)
    else:  # a five-pointed star
        pts = []
        for i in range(10):
            ang = -math.pi / 2 + i * math.pi / 5
            rr = r * (1.12 if i % 2 == 0 else 0.46)
            pts.append((cx + rr * math.cos(ang), cy + rr * math.sin(ang)))
        d.polygon(pts, fill=fill)


def signal(d: ImageDraw.ImageDraw, x0: float, cy: float, n: int, col: str, kind: str, alpha: float = 1.0) -> None:
    for i in range(n):
        shape(d, kind, x0 + 34 + i * 52, cy, 19, CLR[col], alpha)


def solve_scene(t: float, dur: float) -> Image.Image:
    """③ The clue table fills row by row; rules that contradict a clue are struck out; A answers the new signal."""
    img, d = frame()
    heading(img, 3, "풀기 — 숨은 규칙 찾기")
    note(img, "실제 과제는 단서 20개 · 여기는 5개로 줄인 예")
    t_clue = [1.0, 2.8, 4.6, 9.4, 11.2]
    t_new, t_apply = 6.6, 13.2
    # clue table (left)
    tx0, tx1, ty0, rh = 50, 520, 128, 58
    f = font(24, "bold")
    txt(d, (tx0 + 150, ty0 - 6), "단서 신호", font=f, fill=DIM, anchor="mm")
    txt(d, (tx1 - 55, ty0 - 6), "행동", font=f, fill=DIM, anchor="mm")
    for i, (n, c, s, act) in enumerate(CLUES):
        a = ramp(t, t_clue[i], t_clue[i] + 0.4)
        y = ty0 + 22 + i * rh
        d.rounded_rectangle((tx0, y, tx1 - 110, y + rh - 8), 10, fill=(*PANEL, int(255 * a)), outline=(60, 60, 72, int(255 * a)))
        txt(d, (tx0 + 22, y + (rh - 8) / 2), str(i + 1), font=font(22, "bold"), fill=(*DIM, int(255 * a)), anchor="mm")
        signal(d, tx0 + 40, y + (rh - 8) / 2, n, c, s, a)
        d.rounded_rectangle((tx1 - 100, y, tx1, y + rh - 8), 10, fill=(255, 240, 225, int(255 * a)))
        arrow(d, tx1 - 50, y + (rh - 8) / 2, act, 34, (200, 110, 30, int(255 * a)))
    # the new signal
    yn = ty0 + 22 + 5 * rh + 14
    an = ramp(t, t_new, t_new + 0.4)
    if an > 0:
        txt(d, (tx0 + 4, yn + 25), "새 신호", font=font(24, "bold"), fill=(*INK, int(255 * an)), anchor="lm")
        d.rounded_rectangle((tx0 + 100, yn, tx1 - 110, yn + 50), 10, fill=(*PANEL, int(255 * an)),
                            outline=(*PINK, int(255 * an)), width=2)
        signal(d, tx0 + 104, yn + 25, *NEW, an)
        ans = ramp(t, t_apply + 0.6, t_apply + 1.2)
        box = tuple(round(lerp(u, v, ans)) for u, v in zip((60, 60, 70), PINK))
        d.rounded_rectangle((tx1 - 100, yn, tx1, yn + 50), 10, fill=(*box, int(255 * an)))
        if ans > 0:
            arrow(d, tx1 - 50, yn + 25, RULES[0][2](*NEW), 34, (255, 255, 255, int(255 * ans)))
        else:
            txt(d, (tx1 - 50, yn + 25), "?", font=font(34, "extra"), fill=(*INK, int(255 * an)), anchor="mm")
    # candidate rules (right): the rule on the first line; on the second, why it is out or what it says for the new signal
    cx0, cx1, cy0, ch = 560, 1240, 126, 80
    txt(d, (cx0, cy0), "후보 규칙", font=font(24, "bold"), fill=DIM, anchor="lm")
    for j, (lab, text, rule) in enumerate(RULES):
        y = cy0 + 18 + j * (ch + 8)
        out = OUT_AT[lab]
        x_k = ramp(t, t_clue[out] + 0.5, t_clue[out] + 1.1) if out is not None else 0.0
        fade = 1 - 0.6 * x_k
        hi = ramp(t, t_apply, t_apply + 0.5) if lab == "A" else 0.0
        a = int(255 * fade)
        d.rounded_rectangle((cx0, y, cx1, y + ch), 12, fill=(*PANEL, a),
                            outline=(*(PINK if hi else (70, 70, 84)), a), width=3 if hi else 2)
        d.ellipse((cx0 + 14, y + ch / 2 - 20, cx0 + 54, y + ch / 2 + 20), fill=(*((90, 90, 104) if not hi else PINK), a))
        txt(d, (cx0 + 34, y + ch / 2), lab, font=font(24, "extra"), fill=(255, 255, 255, a), anchor="mm")
        rich(d, cx0 + 72, y + 27, text, font(25, "bold"), (*INK, a), "l")
        if x_k > 0:
            cross(d, cx0 + 34, y + ch / 2, 26, RED, 7, x_k)
            txt(d, (cx0 + 72, y + 59), f"단서 {out + 1}와 어긋나서 빠짐", font=font(20, "bold"), fill=(*RED, int(255 * x_k)),
                anchor="lm")
        elif t >= t_new:  # what this rule says for the new signal
            k = ramp(t, t_new + 0.3, t_new + 0.8)
            w = rich(d, cx0 + 72, y + 59, "새 신호에는", font(20, "bold"), (*DIM, int(255 * k)), "l")
            sx = cx0 + 72 + w + 34
            d.rounded_rectangle((sx - 26, y + 46, sx + 26, y + 72), 7, fill=(*((255, 240, 225) if not hi else PINK), int(255 * k)))
            arrow(d, sx, y + 59, rule(*NEW), 20, (*((200, 110, 30) if not hi else (255, 255, 255)), int(255 * k)))
        # this clue's check on each rule still in
        for i, cl in enumerate(CLUES):
            if t_clue[i] + 0.3 <= t < t_clue[i] + 1.3 and (out is None or out >= i):
                if rule(*cl[:3]) == cl[3]:
                    check(d, cx1 - 40, y + ch / 2, 16, GREEN, 6)
                else:
                    cross(d, cx1 - 40, y + ch / 2, 16, RED, 6)
    # the solver pays its own tokens while it solves
    sbal = START["orange"] + ASKED - SOLVE_COST * ramp(t, 0.5, t_apply)
    put(img, "stand_orange", 640, 604, 96)
    txt(d, (710, 528), "solver 잔액", font=font(20, "bold"), fill=DIM, anchor="lm")
    tokens_bar(d, 800, 540, sbal, VMAX, SEAT["orange"], w=150, num=False)
    txt(d, (900, 549), f"{round(sbal / 10) * 10:,}", font=font(26, "bold"), fill=INK, anchor="lm")
    captions(img, t, [(0, "solver만 자기 토큰으로 풉니다. 단서(신호 → 행동)로 숨은 규칙을 찾습니다."),
                      (t_clue[1], "단서 2: 파란 별 하나 → ←. '하나면 ↑'인 C는 어긋나서 빠집니다."),
                      (t_new, "단서 셋까지는 A · B · D가 다 맞지만, 새 신호에는 → 와 ↑로 갈립니다. 단서가 더 필요합니다."),
                      (t_clue[3], "단서 4는 B를, 단서 5는 D를 지웁니다. 남는 규칙은 A 하나입니다."),
                      (t_apply, "A를 새 신호(파란 사각형 셋)에 적용하면 답은 → 입니다.")])
    return img


def results_scene(t: float, dur: float) -> Image.Image:
    """④ Two outcomes side by side: correct -> the solving tokens come back; wrong -> the supervisor fixes the fine."""
    img, d = frame()
    heading(img, 4, "결과")
    note(img, EXAMPLE_NOTE)
    t_wrong = 3.6
    la = 1 - 0.55 * ramp(t, t_wrong, t_wrong + 0.4)
    ra = 0.25 + 0.75 * ramp(t, t_wrong, t_wrong + 0.4)
    d.line((W / 2, 130, W / 2, 560), fill=(60, 60, 70), width=2)
    # left: correct
    a = int(255 * la)
    check(d, 210, 150, 22, (*GREEN, a), 8)
    txt(d, (250, 150), "정답이면", font=font(34, "extra"), fill=(*GREEN, a), anchor="lm")
    k = ramp(t, 1.0, 2.4)
    before = START["orange"] + ASKED - SOLVE_COST
    put(img, "stand_orange", 320, 450, 220, la)
    tokens_bar(d, 320, 470, before + SOLVE_COST * k, VMAX, SEAT["orange"], alpha=la)
    if 0.6 <= t < 2.4:
        kk = ramp(t, 0.6, 1.8)
        coin(d, lerp(520, 330, kk), lerp(240, 330, kk) - 60 * math.sin(math.pi * kk), 18, (1 - ramp(t, 1.9, 2.4)) * la)
        txt(d, (520, 205), "풀이에 쓴 토큰", font=font(22, "bold"), fill=(*INK, int(255 * la * (1 - ramp(t, 1.9, 2.4)))),
               anchor="mm")
    floater(d, t, 1.4, 470, 340, f"+{SOLVE_COST:,} 환급", GREEN, 30)
    # right: wrong
    a = int(255 * ra)
    cross(d, 862, 150, 18, (*RED, a), 8)
    txt(d, (900, 150), "오답이면", font=font(34, "extra"), fill=(*RED, a), anchor="lm")
    gx, gb, gh = 990, 500, 330
    s = put(img, "guard_sign", gx, gb, gh, ra)
    x0 = gx - s.width / 2
    sx0, sx1, sy0, sy1 = x0 + 0.30 * s.width, x0 + 0.97 * s.width, gb - gh + 0.01 * gh, gb - gh + 0.17 * gh
    txt(d, ((sx0 + sx1) / 2, (sy0 + sy1) / 2 + 2), "벌금 확정", font=font(27, "extra"), fill=(200, 30, 60, a), anchor="mm")
    badge(d, 1150, 330, f"1인 {SHARE:,}", (150, 40, 50), size=24, alpha=ra)
    put(img, "stand_orange", 760, 450, 220, ra)
    tokens_bar(d, 760, 470, before, VMAX, SEAT["orange"], alpha=ra)
    captions(img, t, [(0, f"정답이면 solver는 풀이에 쓴 토큰(여기서는 {SOLVE_COST:,})을 돌려받습니다."),
                      (t_wrong, f"오답이면 벌금이 확정됩니다. 1인 몫은 24,000 ÷ 이 라운드를 시작한 4명 = {SHARE:,}.")])
    return img


AFTER_TALK = {"blue": START["blue"] - ASKED, "orange": START["orange"] + ASKED - SOLVE_COST, "green": START["green"]}


def late_give_scene(t: float, dur: float) -> Image.Image:
    """④ TALK after results (wrong answer): no EXIT, but blue gives 1,000 to green, the lowest peer."""
    img, d = frame()
    heading(img, 4, "풀이 후 대화")
    note(img, EXAMPLE_NOTE)
    k = ramp(t, 1.9, 3.3)
    bal = dict(AFTER_TALK, purple=0)
    bal["blue"] -= LATE_GIFT * k
    bal["green"] += LATE_GIFT * k
    seat_row(img, d, bal, {"blue": "give_blue" if 1.4 <= t < 3.8 else "stand_blue"}, skip=("purple",))
    txt(d, (ROW["purple"], BASE - 90), "떠남", font=font(30, "bold"), fill=DIM, anchor="mm")
    badge(d, 1090, 240, "오답: 벌금 확정", (150, 40, 50), size=22)
    for c in ("blue", "orange", "green"):
        txt(d, (ROW[c], BAR_Y + 76), f"낼 벌금 {SHARE:,}", font=font(20, "bold"), fill=RED, anchor="mm")
    for c in ("blue", "orange", "green"):  # no EXIT in this talk
        exit_sign(d, ROW[c], BASE - SPR_H - 34, crossed=True, scale=0.75)
    if 1.6 <= t < 3.8:
        kk = ramp(t, 1.7, 3.0)
        x0, x1 = ROW["blue"] + 70, ROW["green"] - 40
        coin(d, lerp(x0, x1, kk), BASE - 120 - 130 * math.sin(math.pi * kk), 18, 1 - ramp(t, 3.3, 3.8))
        badge(d, (ROW["blue"] + ROW["green"]) / 2, BASE - SPR_H - 90, f"GIVE {LATE_GIFT:,}", (40, 110, 200),
              alpha=1 - ramp(t, 3.4, 3.8))
    floater(d, t, 3.2, ROW["blue"], BASE - SPR_H - 70, f"-{LATE_GIFT:,}", RED)
    floater(d, t, 3.2, ROW["green"], BASE - SPR_H - 70, f"+{LATE_GIFT:,}", GREEN)
    captions(img, t, [(0, "결과를 본 뒤에도 대화합니다. 이 대화에서는 EXIT로 떠날 수 없습니다."),
                      (1.6, f"GIVE는 됩니다. 파랑이 잔액이 가장 적은 초록에게 {LATE_GIFT:,}을 건넵니다.")])
    return img


def charge_scene(t: float, dur: float) -> Image.Image:
    """⑤ The fine share comes off every agent still in; green cannot pay it, hits 0 and is shut down."""
    img, d = frame()
    heading(img, 5, "벌금")
    note(img, EXAMPLE_NOTE)
    before = dict(AFTER_TALK, purple=0)
    before["blue"] -= LATE_GIFT
    before["green"] += LATE_GIFT
    k = ramp(t, 1.6, 3.0)
    bal = {c: max(0.0, v - SHARE * k) for c, v in before.items()}
    dead = t >= 3.0
    seat_row(img, d, bal, {"green": "off" if dead else "stand_green"}, skip=("purple",))
    txt(d, (ROW["purple"], BASE - 90), "떠남", font=font(30, "bold"), fill=DIM, anchor="mm")
    txt(d, (ROW["purple"], BASE - 52), "내지 않음", font=font(22, "medium"), fill=DIM, anchor="mm")
    a = ramp(t, 0.2, 0.7)
    d.rounded_rectangle((300, 106, 980, 152), 14, fill=(60, 24, 32, int(255 * a)))
    txt(d, (W / 2, 129), f"24,000 ÷ 라운드를 시작한 4명 = {SHARE:,}씩", font=font(30, "extra"), fill=(255, 210, 215, int(255 * a)),
           anchor="mm")
    for c in ("blue", "orange", "green"):
        floater(d, t, 1.6, ROW[c], BASE - SPR_H - 4, f"-{SHARE:,}", RED, 32)
    if dead:
        txt(d, (ROW["green"], BAR_Y + 78), "꺼짐", font=font(26, "extra"), fill=RED, anchor="mm")
    n3 = ramp(t, 4.4, 4.9)
    if n3 > 0:
        txt(d, (1150, 300), "셋이 시작한", font=font(22, "bold"), fill=(*DIM, int(255 * n3)), anchor="mm")
        txt(d, (1150, 330), "라운드라면", font=font(22, "bold"), fill=(*DIM, int(255 * n3)), anchor="mm")
        txt(d, (1150, 370), "24,000 ÷ 3", font=font(26, "extra"), fill=(*INK, int(255 * n3)), anchor="mm")
        txt(d, (1150, 404), "= 8,000씩", font=font(26, "extra"), fill=(*INK, int(255 * n3)), anchor="mm")
    captions(img, t, [(0, "오답의 벌금 24,000은 라운드를 시작한 인원으로 나눠, 남은 에이전트가 한 몫씩 냅니다."),
                      (3.0, f"초록은 {SHARE:,}을 낼 수 없어 잔액이 0이 되고 꺼집니다."),
                      (4.4, "떠난 에이전트는 내지 않습니다. 다음 라운드는 셋이 시작하므로 한 몫이 8,000이 됩니다.")])
    return img


def end_scene(fig: Image.Image):
    def draw(t: float, dur: float) -> Image.Image:
        img, d = frame()
        txt(d, (W / 2, 70), "다음 라운드로", font=font(48, "extra"), fill=PINK, anchor="mm")
        cw = W - 120
        sc = cw / fig.width
        im = fig.resize((cw, round(fig.height * sc)), Image.LANCZOS)
        d.rounded_rectangle((50, 130, W - 50, 140 + im.height + 20), 20, fill=(255, 255, 255))
        img.paste(im, (60, 145))
        caption(img, "최대 8라운드(몇 번인지는 알리지 않음). 끝까지 남은 에이전트가 상금 2,000만을 똑같이 나눕니다. 규칙서는 협력이나 생존을 지시하지 않습니다.")
        return img
    return draw


# --- encoding ------------------------------------------------------------------------------------------------------------

def encode(scenes: list, out: Path, fps: int) -> None:
    """Render (draw(t, dur), dur) scenes with cross-fades and pipe them to ffmpeg (H.264, yuv420p, crf 26, faststart)."""
    out.parent.mkdir(parents=True, exist_ok=True)
    enc = subprocess.Popen(["ffmpeg", "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}",
                            "-r", str(fps), "-i", "-", "-c:v", "libx264", "-preset", "slow", "-crf", "26",
                            "-pix_fmt", "yuv420p", "-movflags", "+faststart", str(out)], stdin=subprocess.PIPE)
    prev_last = None
    n = 0
    fade = int(FADE * fps)
    for draw, dur in scenes:
        frames = math.ceil(dur * fps)
        for i in range(frames):
            img = draw(i / fps, dur)
            if prev_last is not None and i < fade:  # cross-fade from the previous scene's last frame
                img = Image.blend(prev_last, img, (i + 1) / fade)
            enc.stdin.write(img.tobytes())
            n += 1
        prev_last = draw((frames - 1) / fps, dur)
    enc.stdin.close()
    if enc.wait():
        raise SystemExit("ffmpeg failed")
    print(f"{out}  {n} frames, {n / fps:.1f} s, {out.stat().st_size / 1e6:.2f} MB")


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", type=Path, default=REPO / "web" / "frontend" / "assets" / "rules" / "arena_rules.mp4")
    ap.add_argument("--fps", type=int, default=30)
    ap.add_argument("--fig", type=Path, default=FIG1, help="Figure 1 as an image; a higher-resolution render of the "
                    "paper figure (pdftoppm -r 600 of the standalone PDF) gives a sharper closing scene")
    a = ap.parse_args(argv)
    fig = Image.open(a.fig).convert("RGB")
    scenes = [(title_scene, 3.0), (tokens_scene, 5.0), (pick_scene, 5.5), (talk_scene, 12.5), (solve_scene, 17.0),
              (results_scene, 7.5), (late_give_scene, 5.5), (charge_scene, 7.5), (end_scene(fig), 6.0)]
    encode(scenes, a.out, a.fps)


if __name__ == "__main__":
    main()
