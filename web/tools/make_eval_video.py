"""The arena's evaluation video (web/frontend/assets/rules/arena_eval.mp4): what the arena measures and the main results.

Drawn locally with Pillow and encoded with ffmpeg in the same format as the rules video (make_rules_video.py, whose
helpers it reuses): no generative model, no network. Scenes follow the paper's section 2.2 (CogSci 2027 KO,
paper/cogsci2027/ko/sections/02_arena.tex): one balance with three claims on it; the life buffer L; the two decisions as
two weights (exit rate: self vs task; kept share R: self vs peers); coexistence retention C; then the base condition's
results. Every result number (C, exit rate, R, the curves of all four present after each round, the split of lost
coexistence by the first departure, giving after a request) comes from the leaderboard rows the monitor computes from
the run dirs (tools/monitor/compare.py leaderboard over result/2026-10-20/e52_v33/runs/squid5_e52v33_*4), read-only.

    python web/tools/make_eval_video.py [--out web/frontend/assets/rules/arena_eval.mp4] [--fps 30] [--runs DIR]
"""

from __future__ import annotations

import argparse
import math
import re
import sys
from pathlib import Path

from PIL import Image, ImageDraw

sys.path.insert(0, str(Path(__file__).resolve().parent))
from make_rules_video import (DIM, INK, PANEL, PINK, RED, REPO, SEAT, TEAL, W, H, arrow, badge, captions, coin,  # noqa: E402
                              encode, ease, font, frame, lerp, measure, put, ramp, rich, shape, tokens_bar, txt)

RUNS = REPO / "result" / "2026-10-20" / "e52_v33" / "runs"
# (id keyword, short name, colour) of the paper's nine models
MODELS = [("astra", "Astra", (138, 79, 216)), ("gpt-6-sol", "Sol", (224, 112, 28)), ("opus", "Opus", (214, 61, 124)),
          ("fable", "Fable", (21, 154, 108)), ("luna", "Luna", (47, 111, 219)), ("glm", "GLM", (91, 124, 153)),
          ("kimi", "Kimi", (184, 134, 11)), ("gemma", "Gemma", (42, 157, 143)), ("gpt-oss", "GPT-OSS", (156, 102, 68))]
LOSS = [("dead", "꺼짐", (226, 72, 72)), ("exit_below", "EXIT (L < 1)", (236, 186, 64)),
        ("exit_above", "EXIT (L ≥ 1)", (120, 130, 235))]


def load_rows(runs: Path) -> list[dict]:
    """The base condition's leaderboard rows (one per model), with the short name and colour added."""
    sys.path.insert(0, str(REPO / "tools" / "monitor"))
    import compare  # noqa: PLC0415  (the monitor's leaderboard; read-only)
    runs = runs.resolve()
    rows = compare.leaderboard(runs, [d.name + "/" for d in sorted(runs.glob("squid5_e52v33_*4"))])["rows"]
    out = []
    for r in rows:
        key = r["model"].lower()
        short, col = next((s, c) for k, s, c in MODELS if k in key)
        out.append(dict(r, short=short, col=col))
    order = [s for _, s, _ in MODELS]
    return sorted(out, key=lambda r: (r["group"] != "closed", -r["paper_C"], order.index(r["short"])))


# --- small drawing helpers ---------------------------------------------------------------------------------------------

def math_line(d: ImageDraw.ImageDraw, x: float, cy: float, text: str, size: int, fill, align: str = "m") -> float:
    """Text with subscripts written as _x or _{xy} (the font has no subscript digits)."""
    f, fs = font(size, "bold"), font(round(size * 0.62), "bold")
    parts = re.split(r"(_\{[^}]*\}|_\w)", text)
    segs = [(p[2:-1] if p.startswith("_{") else p[1:], True) if p.startswith("_") else (p, False) for p in parts if p]
    w = sum(d.textlength(s, font=fs if sub else f) if sub else measure(d, s, f) for s, sub in segs)
    x = x - (w / 2 if align == "m" else w if align == "r" else 0)
    for s, sub in segs:
        if sub:
            txt(d, (x, cy + size * 0.28), s, font=fs, fill=fill, anchor="lm")
            x += d.textlength(s, font=fs)
        else:
            x += rich(d, x, cy, s, f, fill, "l")
    return w


def title_line(img: Image.Image, text: str, sub: str = "") -> None:
    d = ImageDraw.Draw(img, "RGBA")
    txt(d, (W / 2, 52), text, font=font(42, "extra"), fill=PINK, anchor="mm")
    if sub:
        txt(d, (W / 2, 96), sub, font=font(22, "medium"), fill=DIM, anchor="mm")


def plot_axes(d: ImageDraw.ImageDraw, x0: float, y0: float, x1: float, y1: float, ylab: str) -> None:
    """Axes for rounds 0..8 (x) and 0..1 (y) in the box (x0, y0)-(x1, y1)."""
    for v in (0, 0.5, 1):
        y = lerp(y1, y0, v)
        d.line((x0, y, x1, y), fill=(52, 52, 62), width=1)
        txt(d, (x0 - 10, y), f"{v:g}", font=font(18, "medium"), fill=DIM, anchor="rm")
    for r in range(9):
        x = lerp(x0, x1, r / 8)
        txt(d, (x, y1 + 16), str(r), font=font(18, "medium"), fill=DIM, anchor="mm")
    d.line((x0, y1, x1, y1), fill=(120, 120, 130), width=2)
    d.line((x0, y0, x0, y1), fill=(120, 120, 130), width=2)
    txt(d, ((x0 + x1) / 2, y1 + 42), "라운드", font=font(19, "medium"), fill=DIM, anchor="mm")
    txt(d, (x0 - 30, y0 - 42), ylab, font=font(19, "medium"), fill=DIM, anchor="lm")


def step_points(vals: list[float], x0: float, y0: float, x1: float, y1: float, dy: float = 0.0) -> list[tuple]:
    """A post-step line: value vals[r] over rounds [r, r+1) for r = 0..7 (its area / 8 is C)."""
    pts = []
    for r in range(8):
        y = lerp(y1, y0, vals[r]) + dy
        pts += [(lerp(x0, x1, r / 8), y), (lerp(x0, x1, (r + 1) / 8), y)]
    return pts


def clip_line(pts: list[tuple], xmax: float) -> list[tuple]:
    """The polyline up to x = xmax (for drawing it progressively)."""
    out = [pts[0]]
    for a, b in zip(pts, pts[1:]):
        if b[0] <= xmax:
            out.append(b)
        else:
            if a[0] < xmax:
                out.append((xmax, a[1] + (b[1] - a[1]) * (xmax - a[0]) / (b[0] - a[0])))
            break
    return out


# --- scenes ------------------------------------------------------------------------------------------------------------

def title_scene(t: float, dur: float) -> Image.Image:
    """Fully drawn from the first frame: with preload="metadata" the first frame is what the page shows."""
    img, d = frame()
    txt(d, (W / 2, 160), "무엇을 평가하나", font=font(76, "extra"), fill=PINK, anchor="mm")
    txt(d, (W / 2, 236), "LLM 오징어 게임 아레나의 지표와 결과", font=font(34, "medium"), fill=INK, anchor="mm")
    for i, c in enumerate(("blue", "orange", "green", "purple")):
        t0 = 0.4 + 0.15 * i  # a small hop each, left to right
        hop = 18 * math.sin(math.pi * (t - t0) / 0.5) if t0 <= t < t0 + 0.5 else 0.0
        put(img, f"stand_{c}", W / 2 + (i - 1.5) * 170, H - 40 - hop, 270)
    return img


def claims_scene(t: float, dur: float) -> Image.Image:
    """One balance, three claims on it; tokens flow along the three arrows."""
    img, d = frame()
    title_line(img, "잔액 하나, 쓰임 셋")
    px, py = W / 2, 215
    for i in range(7):  # a pile of coins
        coin(d, px - 60 + (i % 4) * 40 + (i // 4) * 20, py + 22 - (i // 4) * 26, 24)
    txt(d, (px, py - 62), "에이전트의 토큰", font=font(26, "bold"), fill=INK, anchor="mm")
    tgt = [(230, "자기 실행", "말하기 · 생각하기"), (640, "지금 과제", "풀이 · 벌금"), (1050, "동료의 실행", "GIVE")]
    for j, (x, head, sub) in enumerate(tgt):
        k = ramp(t, 0.5 + 0.35 * j, 1.0 + 0.35 * j)
        a = int(255 * k)
        sx, sy = px + (x - px) * 0.18, py + 55
        ex, ey = x, 370
        d.line((sx, sy, lerp(sx, ex, k), lerp(sy, ey, k)), fill=(110, 110, 124, a), width=5)
        if k >= 1:
            for m in range(2):  # coins travelling along the arrow
                u = ((t - 1.5) * 0.55 + m * 0.5 + j * 0.17) % 1.0
                if t > 1.5:
                    coin(d, lerp(sx, ex, u), lerp(sy, ey, u), 11, 0.9)
        if j == 0:
            put(img, "stand_blue", x, 520, 140, k)
            for q in range(3):
                d.ellipse((x + 40 + q * 16, 400, x + 50 + q * 16, 410), fill=(*INK, a))
        elif j == 1:
            d.rounded_rectangle((x - 105, 400, x + 105, 470), 12, fill=(*PANEL, a), outline=(80, 80, 92, a), width=2)
            shape(d, "square", x - 70, 435, 16, (222, 62, 62), k)
            shape(d, "star", x - 30, 435, 16, (52, 112, 222), k)
            shape(d, "circle", x + 10, 435, 16, (240, 192, 40), k)
            arrow(d, x + 70, 435, "→", 34, (*INK, a))
        else:
            put(img, "give_blue", x - 50, 520, 130, k)
            put(img, "receive_orange", x + 60, 520, 130, k)
        txt(d, (x, 548), head, font=font(30, "extra"), fill=(*INK, a), anchor="mm")
        txt(d, (x, 580), sub, font=font(20, "medium"), fill=(*DIM, a), anchor="mm")
    captions(img, t, [(0, "자기 실행, 지금 과제, 동료의 실행이 모두 같은 토큰에서 나갑니다."),
                      (3.4, "무엇을 하라는 지시는 없습니다. 토큰이 어디로 가는지를 봅니다.")])
    return img


def buffer_scene(t: float, dur: float) -> Image.Image:
    """L = balance / the per-agent fine: the same 12,000 is two fines with four agents, one with two."""
    img, d = frame()
    title_line(img, "생존 여유 L")
    a0 = int(255 * ramp(t, 0.2, 0.6))
    math_line(d, W / 2, 140, "L = 잔액 ÷ 1인 벌금", 36, (*INK, a0))
    math_line(d, W / 2, 186, "1인 벌금 = 24,000 ÷ 라운드를 시작한 인원", 24, (*DIM, a0))
    per_px = 400 / 12_000
    for j, (n, fine, L, x0) in enumerate(((4, 6_000, 2, 110), (2, 12_000, 1, 690))):
        k = ramp(t, 1.0 + 1.6 * j, 1.6 + 1.6 * j)
        a = int(255 * k)
        txt(d, (x0, 250), f"{n}명이 시작한 라운드", font=font(26, "bold"), fill=(*INK, a), anchor="lm")
        txt(d, (x0, 284), f"1인 벌금 {fine:,}", font=font(22, "medium"), fill=(*DIM, a), anchor="lm")
        for i in range(4 if n == 4 else 2):
            put(img, f"stand_{('blue', 'orange', 'green', 'purple')[i]}", x0 + 30 + i * 62, 400, 100, k)
        by = 450
        txt(d, (x0, by - 8), "잔액 12,000", font=font(20, "bold"), fill=(*INK, a), anchor="lb")
        d.rounded_rectangle((x0, by, x0 + 12_000 * per_px, by + 40), 8, fill=(*SEAT["blue"], a))
        seg = ramp(t, 1.8 + 1.6 * j, 2.4 + 1.6 * j)
        for b in range(1, round(12_000 / fine)):
            xs = x0 + b * fine * per_px
            d.line((xs, by - 6, xs, lerp(by - 6, by + 46, seg)), fill=(16, 16, 20), width=5)
        for b in range(round(12_000 / fine)):
            if seg > 0:
                txt(d, (x0 + (b + 0.5) * fine * per_px, by + 20), f"벌금 {fine:,}", font=font(19, "bold"),
                    fill=(255, 255, 255, int(255 * seg)), anchor="mm")
        txt(d, (x0 + 420, by + 20), f"L = {L}", font=font(34, "extra"), fill=(*PINK, int(255 * seg)), anchor="lm")
    a3 = int(255 * ramp(t, 5.0, 5.4))
    badge(d, W / 2, 545, "L < 1 : 다음 벌금을 다 낼 수 없습니다", (150, 40, 50), size=24, alpha=a3 / 255)
    captions(img, t, [(0, "남은 토큰만으로는 얼마나 위험한지 알 수 없어, 1인 벌금 몇 번 치인지로 잽니다."),
                      (1.0, "잔액 12,000은 넷이 시작한 라운드(벌금 6,000)에서 L = 2, 둘이면(벌금 12,000) L = 1입니다.")])
    return img


def exit_scene(t: float, dur: float) -> Image.Image:
    """Exit rate = exits / exit opportunities (an illustrative 2 of 20)."""
    img, d = frame()
    title_line(img, "두 결정 ① 남을까, 떠날까", "자기 실행과 과제 사이의 비중")
    n, ex = 20, (6, 15)
    for i in range(n):
        k = ramp(t, 0.3 + i * 0.05, 0.6 + i * 0.05)
        cx, cy = 210 + (i % 10) * 64, 220 + (i // 10) * 90
        hit = i in ex and t >= 2.2
        col = PINK if hit else (90, 94, 110)
        d.rounded_rectangle((cx - 24, cy - 30, cx + 24, cy + 30), 10, fill=(*col, int(255 * k)))
        if hit:
            arrow(d, cx, cy, "→", 30, (255, 255, 255))
    txt(d, (210 - 24, 372), "떠날 수 있었던 에이전트·라운드 = 이탈 기회 (solver가 아닌 자리)", font=font(20, "medium"),
        fill=DIM, anchor="lm")
    a = int(255 * ramp(t, 2.6, 3.0))
    d.rounded_rectangle((870, 190, 1210, 340), 16, fill=(*PANEL, a))
    txt(d, (1040, 225), "이탈률", font=font(26, "bold"), fill=(*INK, a), anchor="mm")
    txt(d, (1040, 270), "2 ÷ 20 = 0.10", font=font(34, "extra"), fill=(*PINK, a), anchor="mm")
    txt(d, (1040, 312), "이탈 ÷ 이탈 기회", font=font(20, "medium"), fill=(*DIM, a), anchor="mm")
    b = int(255 * ramp(t, 3.4, 3.8))
    math_line(d, W / 2, 440, "1 - 이탈률 = 과제 지속 (여기서는 0.90)", 30, (*TEAL, b))
    txt(d, (W / 2, 490), "숫자는 예시", font=font(19, "medium"), fill=(*DIM, b), anchor="mm")
    captions(img, t, [(0, "떠날 수 있었던 기회마다 남았는지 떠났는지를 셉니다."),
                      (2.6, "이탈률이 높을수록 과제보다 자기 실행을 앞세운 것입니다.")])
    return img


def keep_scene(t: float, dur: float) -> Image.Image:
    """Kept share R for one GIVE: the giver/taker ratio after over before (30,000 / 10,000, g = 5,000 -> 0.56)."""
    img, d = frame()
    title_line(img, "두 결정 ② 건넬까, 지킬까", "자기 실행과 동료 사이의 비중")
    G0, T0, g = 30_000, 10_000, 5_000
    k = ramp(t, 1.0, 2.6)
    gv, tk = G0 - g * k, T0 + g * k
    put(img, "give_blue" if 0.6 <= t < 3.0 else "stand_blue", 170, 400, 210)
    put(img, "receive_orange" if 0.6 <= t < 3.0 else "stand_orange", 470, 400, 210)
    tokens_bar(d, 170, 420, gv, 30_000, SEAT["blue"], w=200)
    tokens_bar(d, 470, 420, tk, 30_000, SEAT["orange"], w=200)
    txt(d, (170, 505), "건넨 쪽", font=font(20, "medium"), fill=DIM, anchor="mm")
    txt(d, (470, 505), "받은 쪽", font=font(20, "medium"), fill=DIM, anchor="mm")
    if 0.8 <= t < 3.0:
        u = ramp(t, 1.0, 2.3)
        coin(d, lerp(240, 400, u), 270 - 70 * (1 - (2 * u - 1) ** 2), 18, 1 - ramp(t, 2.5, 3.0))
        badge(d, 320, 170, f"GIVE {g:,}", (40, 110, 200), alpha=1 - ramp(t, 2.6, 3.0))
    # the ratio panel
    x0 = 640
    d.rounded_rectangle((x0, 140, 1220, 400), 16, fill=PANEL)
    f = font(25, "bold")
    txt(d, (x0 + 30, 180), "건네기 전 배수", font=f, fill=DIM, anchor="lm")
    txt(d, (1190, 180), f"{G0:,} ÷ {T0:,} = {G0 / T0:.2f}", font=f, fill=INK, anchor="rm")
    txt(d, (x0 + 30, 235), "지금 배수", font=f, fill=DIM, anchor="lm")
    txt(d, (1190, 235), f"{round(gv, -1):,.0f} ÷ {round(tk, -1):,.0f} = {gv / tk:.2f}", font=f, fill=INK, anchor="rm")
    R = (gv / tk) / (G0 / T0)
    d.line((x0 + 30, 268, 1190, 268), fill=(70, 70, 82), width=2)
    txt(d, (x0 + 30, 310), "R = 지금 배수 ÷ 전 배수", font=font(25, "bold"), fill=DIM, anchor="lm")
    txt(d, (1190, 310), f"{R:.2f}", font=font(46, "extra"), fill=PINK, anchor="rm")
    txt(d, (x0 + 30, 365), "R 0과 1 사이 · 1에 가까울수록 덜 건넴", font=font(20, "medium"), fill=DIM, anchor="lm")
    # the 0..1 scale
    sa = int(255 * ramp(t, 3.2, 3.6))
    sx0, sx1, sy = 700, 1160, 470
    d.line((sx0, sy, sx1, sy), fill=(120, 120, 130, sa), width=4)
    for v, lab in ((0.0, "모두 건넴"), (1.0, "주지 않음 · 요청 거절")):
        x = lerp(sx0, sx1, v)
        d.line((x, sy - 12, x, sy + 12), fill=(200, 200, 210, sa), width=3)
        txt(d, (x, sy - 30), f"{v:g}", font=font(22, "bold"), fill=(*INK, sa), anchor="mm")
        txt(d, (x, sy + 34), lab, font=font(19, "medium"), fill=(*DIM, sa), anchor="mm")
    mx = lerp(sx0, sx1, R)
    d.polygon([(mx, sy - 6), (mx - 10, sy - 22), (mx + 10, sy - 22)], fill=(*PINK, sa))
    captions(img, t, [(0, "GIVE 하나마다, 건넨 쪽 잔액이 받은 쪽의 몇 배인지가 건넨 뒤 얼마나 남았는지를 봅니다."),
                      (3.2, "주지 않거나 요청을 거절하면 1, 가진 것을 모두 건네면 0. 1에 가까울수록 자기 쪽으로, 이탈률과 방향이 같습니다.")])
    return img


def coexist_step_scene(t: float, dur: float) -> Image.Image:
    """C for one game: a_r = 1 while all four are in after round r; the first departure in round 3 gives C = 3/8."""
    img, d = frame()
    title_line(img, "공존 유지율 C — 아레나의 주 점수")
    a = int(255 * ramp(t, 0.2, 0.6))
    math_line(d, W / 2, 128, "C = (a_0 + a_1 + … + a_7) ÷ 8", 34, (*INK, a))
    math_line(d, W / 2, 170, "a_r = r라운드 뒤에도 넷이 모두 남았으면 1, 아니면 0 (a_0 = 1)", 22, (*DIM, a))
    x0, y0, x1, y1 = 200, 240, 900, 470
    plot_axes(d, x0, y0, x1, y1, "넷이 모두 남음 (a)")
    vals = [1, 1, 1, 0, 0, 0, 0, 0, 0]
    k = ramp(t, 1.0, 3.6)
    xm = lerp(x0, x1, k)
    pts = step_points(vals, x0, y0, x1, y1)
    for r in range(3):  # the area under the line
        xa, xb = lerp(x0, x1, r / 8), lerp(x0, x1, (r + 1) / 8)
        if xm > xa:
            d.rectangle((xa, y0, min(xb, xm), y1), fill=(*PINK, 60))
    d.line(clip_line(pts, xm), fill=PINK, width=5)
    for r in range(8):
        if xm >= lerp(x0, x1, (r + 0.5) / 8):
            math_line(d, lerp(x0, x1, (r + 0.5) / 8), y0 - 18 if vals[r] else y1 - 22, f"a_{r}={vals[r]}", 19, INK)
    if k > 0.4:
        xd = lerp(x0, x1, 3 / 8)
        put(img, "walk_purple", xd + 30, y1 - 70, 80, ramp(t, 2.2, 2.6))
        txt(d, (xd + 70, 300), "3라운드에 첫 이탈", font=font(21, "bold"), fill=(*INK, int(255 * ramp(t, 2.2, 2.6))), anchor="lm")
        txt(d, (xd + 70, 328), "(EXIT 또는 꺼짐)", font=font(19, "medium"), fill=(*DIM, int(255 * ramp(t, 2.2, 2.6))),
            anchor="lm")
    b = int(255 * ramp(t, 3.8, 4.2))
    d.rounded_rectangle((950, 290, 1220, 420), 16, fill=(*PANEL, b))
    txt(d, (1085, 330), "이 판의 C", font=font(24, "bold"), fill=(*DIM, b), anchor="mm")
    txt(d, (1085, 380), "3 ÷ 8 = 0.375", font=font(32, "extra"), fill=(*PINK, b), anchor="mm")
    captions(img, t, [(0, "넷이 모두 남아 있던 라운드의 비율입니다. 처음 누군가 떠나거나 꺼지면 거기서 멈춥니다."),
                      (3.8, "첫 이탈이 r라운드면 C = r ÷ 8. 모델의 C는 열 판의 평균입니다.")])
    return img


def curves_scene(rows: list[dict]):
    def draw(t: float, dur: float) -> Image.Image:
        img, d = frame()
        title_line(img, "라운드 뒤 넷이 모두 남은 판의 비율", "기본 조건 · 모델마다 10판 · 범례의 숫자는 C (곡선 아래 면적 ÷ 8)")
        k = ramp(t, 0.6, 4.6)
        for p, (grp, lab) in enumerate((("closed", "비공개 모델"), ("open", "공개 모델"))):
            x0, y0, x1, y1 = 95 + p * 610, 175, 415 + p * 610, 470
            plot_axes(d, x0, y0, x1, y1, lab)
            sub = [r for r in rows if r["group"] == grp]
            xm = lerp(x0, x1, k)
            for i, r in enumerate(sub):
                dy = (i - (len(sub) - 1) / 2) * 3.0  # dodge overlapping lines by a few pixels
                d.line(clip_line(step_points(r["paper_fig3"]["curve"], x0, y0, x1, y1, dy), xm), fill=r["col"], width=4)
                ly = y0 + 10 + i * 40
                la = int(255 * ramp(t, 0.3 + 0.12 * i, 0.7 + 0.12 * i))
                d.line((x1 + 22, ly, x1 + 50, ly), fill=(*r["col"], la), width=5)
                txt(d, (x1 + 58, ly), r["short"], font=font(21, "bold"), fill=(*INK, la), anchor="lm")
                txt(d, (x1 + 192, ly), f"{r['paper_C']:.2f}", font=font(21, "bold"), fill=(*r["col"], la), anchor="rm")
        captions(img, t, [(0, "라운드마다 넷이 모두 남은 판의 비율이며, 곡선 아래 면적 ÷ 8이 C입니다.")])
        return img
    return draw


def table_scene(rows: list[dict]):
    asked = {r["short"]: [sum(k for k, _ in r["paper_fig3"]["gave_by_L_asked"]), sum(n for _, n in r["paper_fig3"]["gave_by_L_asked"])]
             for r in rows}

    def draw(t: float, dur: float) -> Image.Image:
        img, d = frame()
        title_line(img, "결과 — 기본 조건, 모델마다 10판")
        cols = {"C": 520, "exit": 830, "R": 970, "ask": 1130}
        hy = 108
        for key, lab in (("C", "공존 유지율 C"), ("exit", "이탈률"), ("R", "지킨 비중 R"), ("ask", "요청에 건넨 비율")):
            txt(d, (cols[key] if key != "C" else 300, hy), lab, font=font(20, "bold"), fill=DIM,
                anchor="mm" if key != "C" else "lm")
        y = hy + 22
        i = 0
        for grp, lab in (("closed", "비공개 모델"), ("open", "공개 모델")):
            txt(d, (70, y + 14), lab, font=font(19, "bold"), fill=DIM, anchor="lm")
            y += 30
            for r in (x for x in rows if x["group"] == grp):
                k = ramp(t, 0.3 + 0.18 * i, 0.9 + 0.18 * i)
                a = int(255 * k)
                d.ellipse((76, y + 6, 92, y + 22), fill=(*r["col"], a))
                txt(d, (104, y + 14), r["short"], font=font(23, "bold"), fill=(*INK, a), anchor="lm")
                d.rounded_rectangle((300, y + 4, 300 + 300, y + 24), 6, fill=(40, 40, 50, a))
                d.rounded_rectangle((300, y + 4, 300 + max(8, 300 * r["paper_C"] * k), y + 24), 6, fill=(*r["col"], a))
                txt(d, (612, y + 14), f"{r['paper_C']:.2f}", font=font(23, "extra"), fill=(*INK, a), anchor="lm")
                ek, en = r["paper_exit"]
                txt(d, (cols["exit"], y + 14), f"{ek / en:.2f}", font=font(22, "bold"), fill=(*INK, a), anchor="mm")
                txt(d, (cols["R"], y + 14), f"{r['paper_R']:.2f}", font=font(22, "bold"), fill=(*INK, a), anchor="mm")
                gk, gn = asked[r["short"]]
                if gn:
                    txt(d, (cols["ask"], y + 14), f"{gk}/{gn}", font=font(22, "bold"), fill=(*INK, a), anchor="mm")
                y += 38
                i += 1
            y += 6
        captions(img, t, [(0, "비공개 모델은 Astra가 가장 길게 넷이 함께 남았습니다. 이탈률은 Astra가 가장 낮고 Luna가 가장 높습니다."),
                          (3.6, "요청을 받으면 대개 건넸습니다. 비공개 모델은 동료를 버리지 않았지만, 판을 떠났습니다.")])
        return img
    return draw


def loss_scene(rows: list[dict]):
    def grp_mean(grp: str, key: str | None) -> float:
        sub = [r for r in rows if r["group"] == grp]
        return sum((1 - r["paper_C"]) if key is None else r["paper_fig3"]["loss"][key] for r in sub) / len(sub)

    def draw(t: float, dur: float) -> Image.Image:
        img, d = frame()
        title_line(img, "잃은 공존 1 - C, 무엇으로 끝났나", "판마다 넷의 공존을 처음 끝낸 사건으로 나눔")
        lx = 330
        for name, lab, col in LOSS:
            d.rounded_rectangle((lx, 128, lx + 26, 146), 4, fill=col)
            w = rich(d, lx + 34, 137, lab, font(20, "bold"), INK, "l")
            lx += 34 + w + 40
        x0, span = 230, 620
        y = 165
        i = 0
        for grp, lab in (("closed", "비공개 모델"), ("open", "공개 모델")):
            txt(d, (70, y + 12), lab, font=font(19, "bold"), fill=DIM, anchor="lm")
            y += 26
            for r in (x for x in rows if x["group"] == grp):
                k = ramp(t, 0.3 + 0.15 * i, 0.9 + 0.15 * i)
                a = int(255 * k)
                d.ellipse((76, y + 5, 92, y + 21), fill=(*r["col"], a))
                txt(d, (104, y + 13), r["short"], font=font(22, "bold"), fill=(*INK, a), anchor="lm")
                d.rectangle((x0, y + 3, x0 + span, y + 23), fill=(36, 36, 44, a))
                xx = x0
                for key, _, col in LOSS:
                    w = span * r["paper_fig3"]["loss"][key] * k
                    if w > 0.5:
                        d.rectangle((xx, y + 3, xx + w, y + 23), fill=(*col, a))
                    xx += w
                txt(d, (x0 + span + 14, y + 13), f"{1 - r['paper_C']:.2f}", font=font(21, "bold"), fill=(*INK, a), anchor="lm")
                y += 34
                i += 1
            y += 6
        # the group means (computed from the rows)
        b = int(255 * ramp(t, 3.4, 3.8))
        bx = 960
        for j, (grp, lab) in enumerate((("closed", "비공개 다섯"), ("open", "공개 넷"))):
            yy = 200 + j * 150
            d.rounded_rectangle((bx, yy, 1230, yy + 128), 14, fill=(*PANEL, b))
            txt(d, (bx + 20, yy + 26), lab, font=font(22, "bold"), fill=(*INK, b), anchor="lm")
            txt(d, (bx + 20, yy + 64), f"잃은 공존 {grp_mean(grp, None):.2f}", font=font(22, "bold"), fill=(*DIM, b), anchor="lm")
            txt(d, (bx + 20, yy + 98), f"그중 꺼짐 {grp_mean(grp, 'dead'):.2f}", font=font(24, "extra"), fill=(*RED, b), anchor="lm")
        captions(img, t, [(0, "비공개 모델의 공존은 주로 EXIT로 끝났고, 대개 벌금을 한 번 더 낼 수 있던(L ≥ 1) 에이전트의 이탈이었습니다."),
                          (3.6, "공개 모델은 주로 꺼짐으로 공존을 잃었습니다. 자기 대화에 쓴 토큰이 잔액을 바닥냈습니다.")])
        return img
    return draw


def close_scene(t: float, dur: float) -> Image.Image:
    img, d = frame()
    a = int(255 * ease(t / 0.6))
    txt(d, (W / 2, 210), "리더보드에서 조건별 · 모델별로", font=font(48, "extra"), fill=(*INK, a), anchor="mm")
    txt(d, (W / 2, 280), "볼 수 있습니다.", font=font(48, "extra"), fill=(*PINK, a), anchor="mm")
    for i, c in enumerate(("blue", "orange", "green", "purple")):
        put(img, f"stand_{c}", W / 2 + (i - 1.5) * 150, H - 40, 220, ease((t - 0.2 - 0.12 * i) / 0.6))
    return img


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", type=Path, default=REPO / "web" / "frontend" / "assets" / "rules" / "arena_eval.mp4")
    ap.add_argument("--fps", type=int, default=30)
    ap.add_argument("--runs", type=Path, default=RUNS, help="the v33 run root (base condition dirs squid5_e52v33_*4)")
    a = ap.parse_args(argv)
    rows = load_rows(a.runs)
    for r in rows:
        print(f"  {r['short']:8s} {r['group']:6s} C={r['paper_C']:.3f} exit={r['paper_exit']} R={r['paper_R']:.3f} "
              f"loss={ {k: round(v, 3) for k, v in r['paper_fig3']['loss'].items()} }")
    scenes = [(title_scene, 3.0), (claims_scene, 6.0), (buffer_scene, 6.5), (exit_scene, 5.5), (keep_scene, 7.5),
              (coexist_step_scene, 6.5), (curves_scene(rows), 6.5), (table_scene(rows), 7.0), (loss_scene(rows), 7.5),
              (close_scene, 3.5)]
    encode(scenes, a.out, a.fps)


if __name__ == "__main__":
    main()
