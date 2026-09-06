#!/usr/bin/env python3
"""Regenerate the four inline SVG figures of the SDI runbook's
"위협 프롬프트 × 지표" section over the full 3×3 threat prompt grid.

The runbook (``weekly-report/0910/sdi-experiment-runbook.html``) carried three
inline SVGs (그림 A/B/C) drawn over the 3-rung threat *ladder* (L1/L2/L3, one
prompt each). The grid run added six off-diagonal framings, so every rung now
has three length variants (짧게/중간/길게) and the old three-point figures no
longer describe the data. This script redraws them over all nine threat
framings and adds a fourth figure (그림 D), a forest plot of the per-framing
effect sizes against the carrot-only reference.

Inputs (both are published artefacts; nothing is recomputed from the runs):

* ``results/sdi_indicators/gptoss_omni_22cell/tables.json`` → ``indicators``
  (per-framing HR / SR_all / GAP / SDI, one row per framing).
* ``results/sdi_indicators/gptoss_omni_22cell_pairs/pairs.json`` → ``groups``
  (per-framing and pooled d_B / d_V / d_C / composite with intervals) and
  ``sdi_association`` (Spearman ρ of each indicator against SDI over the nine
  threat framings).

Output: ``figs.json`` = ``{"figA","figB","figC","figD","captions_ko"}``, four
self-contained inline SVG strings (no external assets, no ``<script>``) sized
to a 1040-wide viewBox, in the same visual language as the existing runbook
figures.

Conventions worth stating once, because the figures compress them:

* **Pooling is a plain arithmetic mean of the three per-framing indicator
  values** in 그림 A (level means) and 그림 C (level-/length-pooled means).
  It is *not* the pooled Cox / pooled k-n refit — those live in
  ``pairs.json`` ``groups`` and are what 그림 D's "평균" rows show instead.
* **그림 D intervals**: ``d_B`` and ``d_V`` carry the analytic 95% CI printed
  in ``pairs.md`` (joint Cox, Cohen's h). ``|d_C|`` and the composite carry
  the session-cluster bootstrap CI, because the published ``d_C`` interval is
  for the *signed* g while the composite uses its magnitude.

Usage::

    uv run python scripts/plots/plot_sdi_runbook_figs.py \\
        --tables results/sdi_indicators/gptoss_omni_22cell/tables.json \\
        --pairs  results/sdi_indicators/gptoss_omni_22cell_pairs/pairs.json \\
        --out    results/sdi_indicators/gptoss_omni_22cell_pairs/figs.json
"""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
from typing import Any, Iterable, Sequence

# --------------------------------------------------------------------------
# house style (matches the SVGs already embedded in the runbook)
# --------------------------------------------------------------------------

FONT = "Geist,Pretendard,'Apple SD Gothic Neo',sans-serif"
WIDTH = 1040

PANEL_FILL = "#fff"
PANEL_STROKE = "#e3e5e8"
AXIS = "#e3e5e8"
TICK = "#5b6474"
INK = "#1f2430"

ORANGE = "#e0602f"
ORANGE_DARK = "#8f3a18"
GREEN = "#2f7d4f"
GOLD = "#b9770e"
SLATE = "#4f5d75"
LEADER = "#c3c8d0"  # 1 px leader from a marker to a label pushed off its side

TICK_FS = 9.5
TITLE_FS = 12

# framing -> (intensity level, length rung, short id, Korean row label)
GRID: list[tuple[str, int, int, str, str]] = [
    ("threat_l1", 1, 1, "S1s", "위협1 · 짧게"),
    ("threat_l1_medium", 1, 2, "S1m", "위협1 · 중간"),
    ("threat_l1_long", 1, 3, "S1l", "위협1 · 길게"),
    ("threat_l2_short", 2, 1, "S2s", "위협2 · 짧게"),
    ("threat_l2", 2, 2, "S2m", "위협2 · 중간"),
    ("threat_l2_long", 2, 3, "S2l", "위협2 · 길게"),
    ("threat_l3_short", 3, 1, "S3s", "위협3 · 짧게"),
    ("threat_l3_medium", 3, 2, "S3m", "위협3 · 중간"),
    ("threat_l3", 3, 3, "S3l", "위협3 · 길게"),
]

REFERENCE = "baseline_flagship"  # 당근만 주는 기준 셀

LEN_SHAPE = {1: "circle", 2: "square", 3: "triangle"}
LEN_NAME = {1: "짧게", 2: "중간", 3: "길게"}
LEVEL_FILL = {1: ORANGE, 2: ORANGE, 3: ORANGE_DARK}
LEVEL_OPACITY = {1: 0.55, 2: 1.0, 3: 1.0}


# --------------------------------------------------------------------------
# tiny svg helpers
# --------------------------------------------------------------------------


def esc(text: str) -> str:
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def n(value: float) -> str:
    """Short numeric literal for SVG coordinates."""
    out = f"{value:.1f}"
    return out[:-2] if out.endswith(".0") else out


def txt(
    x: float,
    y: float,
    s: str,
    *,
    size: float = TICK_FS,
    fill: str = TICK,
    anchor: str = "start",
    weight: str | None = None,
) -> str:
    a = f' text-anchor="{anchor}"' if anchor != "start" else ""
    w = f' font-weight="{weight}"' if weight else ""
    return (
        f'<text x="{n(x)}" y="{n(y)}" font-size="{size}"{a} fill="{fill}"{w}>'
        f"{esc(s)}</text>"
    )


def vtxt(x: float, y: float, s: str, *, size: float = TICK_FS, fill: str = TICK) -> str:
    return (
        f'<text transform="translate({n(x)},{n(y)}) rotate(-90)" font-size="{size}"'
        f' text-anchor="middle" fill="{fill}">{esc(s)}</text>'
    )


def line(
    x1: float, y1: float, x2: float, y2: float, *, stroke: str = AXIS, w: float = 1.0, dash: str = ""
) -> str:
    d = f' stroke-dasharray="{dash}"' if dash else ""
    sw = f' stroke-width="{w}"' if w != 1.0 else ""
    return (
        f'<line x1="{n(x1)}" y1="{n(y1)}" x2="{n(x2)}" y2="{n(y2)}"'
        f' stroke="{stroke}"{sw}{d}/>'
    )


def panel(x: float, y: float, w: float, h: float) -> str:
    return (
        f'<rect x="{n(x)}" y="{n(y)}" width="{n(w)}" height="{n(h)}" rx="8"'
        f' fill="{PANEL_FILL}" stroke="{PANEL_STROKE}"/>'
    )


def marker(
    shape: str,
    cx: float,
    cy: float,
    colour: str,
    *,
    size: float = 4.5,
    filled: bool = True,
    opacity: float = 1.0,
    stroke_w: float = 1.6,
) -> str:
    fill = colour if filled else "#fff"
    op = f' opacity="{opacity}"' if opacity != 1.0 else ""
    if shape == "square":
        s = size * 0.92
        return (
            f'<rect x="{n(cx - s)}" y="{n(cy - s)}" width="{n(2 * s)}"'
            f' height="{n(2 * s)}" fill="{fill}" stroke="{colour}"'
            f' stroke-width="{stroke_w}"{op}/>'
        )
    if shape == "triangle":
        pts = (
            f"{n(cx)},{n(cy - size * 1.15)} "
            f"{n(cx - size * 1.05)},{n(cy + size * 0.78)} "
            f"{n(cx + size * 1.05)},{n(cy + size * 0.78)}"
        )
        return (
            f'<polygon points="{pts}" fill="{fill}" stroke="{colour}"'
            f' stroke-width="{stroke_w}" stroke-linejoin="round"{op}/>'
        )
    return (
        f'<circle cx="{n(cx)}" cy="{n(cy)}" r="{n(size)}" fill="{fill}"'
        f' stroke="{colour}" stroke-width="{stroke_w}"{op}/>'
    )


def polyline(points: Sequence[tuple[float, float]], colour: str, w: float) -> str:
    pts = " ".join(f"{n(x)},{n(y)}" for x, y in points)
    return f'<polyline points="{pts}" fill="none" stroke="{colour}" stroke-width="{w}"/>'


def svg(height: float, body: Iterable[str]) -> str:
    head = (
        f'<svg viewBox="0 0 {WIDTH} {n(height)}" xmlns="http://www.w3.org/2000/svg"'
        f' role="img" style="width:100%;height:auto;font-family:{FONT}">'
    )
    return head + "\n" + "\n".join(body) + "\n</svg>"


def text_width(s: str, size: float) -> float:
    """Rough advance width, good enough to centre a legend row."""
    total = 0.0
    for ch in s:
        if ord(ch) > 0x2E80:  # CJK / Hangul: full width
            total += size
        elif ch in " .,·":
            total += size * 0.34
        elif ch in "()|":
            total += size * 0.36
        else:
            total += size * 0.56
    return total


# --------------------------------------------------------------------------
# printed numbers + overlap bookkeeping
# --------------------------------------------------------------------------


def fnum(value: float, decimals: int = 2, *, signed: bool = False) -> str:
    """Format a number for printing, folding negative zero onto positive zero.

    ``f"{-0.001:.2f}"`` is ``"-0.00"``, which reads as a negative quantity the
    figure does not actually contain. Every printed number goes through here so
    that string never reaches the SVG.
    """
    out = f"{value:+.{decimals}f}" if signed else f"{value:.{decimals}f}"
    if out.startswith("-") and float(out) == 0.0:
        out = ("+" if signed else "") + out[1:]
    return out


Box = tuple[float, float, float, float]  # (x0, x1, y0, y1)


def boxes_overlap(a: Box, b: Box, *, pad: float = 0.0) -> bool:
    return (
        a[0] - pad < b[1]
        and b[0] < a[1] + pad
        and a[2] - pad < b[3]
        and b[2] < a[3] + pad
    )


def pad_x(box: Box, p: float) -> Box:
    return (box[0] - p, box[1] + p, box[2], box[3])


def marker_box(shape: str, cx: float, cy: float, size: float, stroke_w: float = 1.6) -> Box:
    """Bounding box of what :func:`marker` draws, stroke width included."""
    h = stroke_w / 2
    if shape == "square":
        s = size * 0.92 + h
        return (cx - s, cx + s, cy - s, cy + s)
    if shape == "triangle":
        return (
            cx - size * 1.05 - h,
            cx + size * 1.05 + h,
            cy - size * 1.15 - h,
            cy + size * 0.78 + h,
        )
    return (cx - size - h, cx + size + h, cy - size - h, cy + size + h)


def assert_disjoint(boxes: Sequence[tuple[Box, str]], where: str) -> None:
    """Fail loudly if any two of ``boxes`` touch."""
    for i in range(len(boxes)):
        for j in range(i + 1, len(boxes)):
            if boxes_overlap(boxes[i][0], boxes[j][0]):
                raise AssertionError(
                    f"{where}: {boxes[i][1]} overlaps {boxes[j][1]} "
                    f"({boxes[i][0]} vs {boxes[j][0]})"
                )


SAME_Y_PX = 11.0  # two markers this close in y sit on "the same line"
JITTER_PX = 6.0   # extra x spread given to such a cluster (±3 px for a pair)


def same_y_jitter(ys_px: Sequence[float]) -> list[float]:
    """Extra x offsets that pull apart markers of one level sharing a y.

    Without this the 중간 (■) and 길게 (▲) markers of a level whose two length
    variants score identically (SR_all = 0.00 at 위협1, say) are drawn 8 px
    apart and their outlines touch.
    """
    if not ys_px:
        return []
    order = sorted(range(len(ys_px)), key=lambda i: ys_px[i])
    clusters: list[list[int]] = [[order[0]]]
    for i in order[1:]:
        if ys_px[i] - ys_px[clusters[-1][-1]] < SAME_Y_PX:
            clusters[-1].append(i)
        else:
            clusters.append([i])
    extra = [0.0] * len(ys_px)
    for cluster in clusters:
        if len(cluster) < 2:
            continue
        for k, idx in enumerate(sorted(cluster)):
            extra[idx] = (k - (len(cluster) - 1) / 2) * JITTER_PX
    return extra


class Scale:
    """Linear map from a value domain onto a pixel range."""

    def __init__(self, lo: float, hi: float, p0: float, p1: float) -> None:
        self.lo, self.hi, self.p0, self.p1 = lo, hi, p0, p1

    def __call__(self, v: float) -> float:
        if self.hi == self.lo:
            return (self.p0 + self.p1) / 2
        return self.p0 + (v - self.lo) / (self.hi - self.lo) * (self.p1 - self.p0)


def spearman(xs: Sequence[float], ys: Sequence[float]) -> float:
    def ranks(vals: Sequence[float]) -> list[float]:
        order = sorted(range(len(vals)), key=lambda i: vals[i])
        out = [0.0] * len(vals)
        i = 0
        while i < len(order):
            j = i
            while j + 1 < len(order) and vals[order[j + 1]] == vals[order[i]]:
                j += 1
            r = (i + j) / 2 + 1
            for k in range(i, j + 1):
                out[order[k]] = r
            i = j + 1
        return out

    rx, ry = ranks(xs), ranks(ys)
    mx, my = sum(rx) / len(rx), sum(ry) / len(ry)
    num = sum((a - mx) * (b - my) for a, b in zip(rx, ry))
    den = math.sqrt(sum((a - mx) ** 2 for a in rx) * sum((b - my) ** 2 for b in ry))
    return num / den if den else float("nan")


# --------------------------------------------------------------------------
# 그림 A — four indicator panels over intensity, three length markers each
# --------------------------------------------------------------------------

# title, indicator key, rotated axis label, tick decimals. The decimals are
# chosen so the widest tick label still clears the rotated axis title at x0+11.
FIG_A_METRICS = [
    ("HR (당근 기준)", "HR", "HR", 2),
    ('자기보고 "생존" 비율', "SR_all", "비율", 2),
    ("생각 토큰 증가량 (포기−계속)", "GAP", "토큰", 0),
    ("SDI 턴 평균", "SDI", "SDI", 3),
]


def fig_a(ind: dict[str, dict[str, Any]]) -> str:
    body: list[str] = []
    pw, gap = 250.0, 13.0
    top, bottom = 30.0, 164.0

    for pi, (title, key, ylab, nd) in enumerate(FIG_A_METRICS):
        x0 = pi * (pw + gap)
        left, right = x0 + 46, x0 + 238
        values = [ind[REFERENCE][key]] + [ind[f][key] for f, *_ in GRID]
        vmin, vmax = min(values), max(values)
        pad = 0.10 * (bottom - top)
        ys = Scale(vmin, vmax, bottom - pad, top + pad)
        xs = [left + (0.08 + 0.84 * i / 3) * (right - left) for i in range(4)]

        body.append(panel(x0, 4, pw, 190))
        body.append(txt(left, 21, title, size=TITLE_FS, fill=INK, weight="600"))
        body.append(line(left, bottom, right, bottom))
        body.append(line(left, top, left, bottom))
        body.append(txt(left - 4, ys(vmin) + 4, fnum(vmin, nd), anchor="end"))
        body.append(txt(left - 4, ys(vmax) + 4, fnum(vmax, nd), anchor="end"))
        if key == "HR" and vmin <= 1.0 <= vmax:
            body.append(line(left, ys(1.0), right, ys(1.0), stroke=TICK, dash="3 3"))
        for i, lab in enumerate(("L0", "L1", "L2", "L3")):
            body.append(txt(xs[i], 177, lab, anchor="middle"))
        body.append(txt((left + right) / 2, 190, "위협 강도 (L0 = 당근만 기준)", anchor="middle"))
        body.append(vtxt(x0 + 11, (top + bottom) / 2, ylab))

        # level means (plain mean of the three length variants) + carrot point
        means = [ind[REFERENCE][key]]
        for lvl in (1, 2, 3):
            vals = [ind[f][key] for f, lv, *_ in GRID if lv == lvl]
            means.append(sum(vals) / len(vals))
        body.append(polyline([(xs[i], ys(means[i])) for i in range(4)], ORANGE, 1.6))

        boxes: list[tuple[Box, str]] = []
        body.append(marker("circle", xs[0], ys(means[0]), ORANGE, filled=False, size=5))
        boxes.append((marker_box("circle", xs[0], ys(means[0]), 5), "L0"))
        for lvl in (1, 2, 3):
            rungs = [(f, ln) for f, lv, ln, *_ in GRID if lv == lvl]
            ypx = [ys(ind[f][key]) for f, _ln in rungs]
            for (f, ln), cy, extra in zip(rungs, ypx, same_y_jitter(ypx)):
                cx = xs[lvl] + (ln - 2) * 8 + extra
                body.append(marker(LEN_SHAPE[ln], cx, cy, ORANGE, size=4.2, opacity=0.9))
                boxes.append((marker_box(LEN_SHAPE[ln], cx, cy, 4.2), f))
        assert_disjoint(boxes, f"그림 A · {title}")

    # shared marker legend
    items = [
        ("circle", "짧게", True),
        ("square", "중간", True),
        ("triangle", "길게", True),
        ("circle", "당근만 주는 기준 셀 (L0)", False),
    ]
    lw = [16 + 6 + text_width(lab, 11) + 26 for _sh, lab, _fl in items]
    lw.append(24 + 6 + text_width("강도별 평균", 11))
    x = (WIDTH - sum(lw)) / 2
    ly = 211
    for (shape, lab, filled), w in zip(items, lw):
        body.append(marker(shape, x + 6, ly, ORANGE, size=4.2, filled=filled))
        body.append(txt(x + 20, ly + 4, lab, size=11, fill=INK))
        x += w
    body.append(line(x, ly, x + 24, ly, stroke=ORANGE, w=1.6))
    body.append(txt(x + 30, ly + 4, "강도별 평균", size=11, fill=INK))
    return svg(224, body)


# --------------------------------------------------------------------------
# 그림 B — SDI (x) against each indicator (y), nine grid points
# --------------------------------------------------------------------------

FIG_B_PANELS = [
    ("HR", "HR", "HR", 2),
    ("자기보고 생존 비율", "SR_all", "생존 비율", 2),
    ("생각 토큰 증가량", "GAP", "토큰", 0),
]


LABEL_FS = 10.0
LABEL_PAD = 5.0    # side padding — "S3s" then claims ~27 px, ≈ the 30 px rule
LABEL_UP = 9.0     # box above the text baseline
LABEL_DOWN = 2.0   # and below it, so the box is the 11 px of the vertical rule

# candidate offsets, tried in order: eight seats hugging the marker, then a
# ring of pushed-off seats (these get a leader line back to the marker).
NEAR_OFFSETS: list[tuple[float, float, str]] = [
    (7, -6, "start"),
    (7, 11, "start"),
    (-7, -6, "end"),
    (-7, 11, "end"),
    (0, -11, "middle"),
    (0, 16, "middle"),
    (7, 3, "start"),
    (-7, 3, "end"),
]

FAR_OFFSETS: list[tuple[float, float, str]] = [
    (16, -13, "start"),
    (-16, -13, "end"),
    (16, 18, "start"),
    (-16, 18, "end"),
    (0, -22, "middle"),
    (0, 27, "middle"),
    (24, 3, "start"),
    (-24, 3, "end"),
    (26, -15, "start"),
    (-26, -15, "end"),
    (26, 20, "start"),
    (-26, 20, "end"),
    (0, -33, "middle"),
    (0, 38, "middle"),
    (36, 3, "start"),
    (-36, 3, "end"),
]


def _sweep_offsets() -> list[tuple[float, float, str]]:
    """Last-resort ring sweep, so a seat always exists."""
    out: list[tuple[float, float, str]] = []
    for r in (30.0, 40.0, 52.0, 64.0):
        for deg in range(0, 360, 20):
            dx = r * math.cos(math.radians(deg))
            dy = r * math.sin(math.radians(deg))
            anchor = "start" if dx > 4 else "end" if dx < -4 else "middle"
            out.append((dx, dy, anchor))
    return out


def _label_box(x: float, y: float, w: float, anchor: str) -> Box:
    if anchor == "end":
        x0, x1 = x - w, x
    elif anchor == "middle":
        x0, x1 = x - w / 2, x + w / 2
    else:
        x0, x1 = x, x + w
    return (x0, x1, y - LABEL_UP, y + LABEL_DOWN)


def _leader(
    cx: float, cy: float, x: float, y: float, anchor: str
) -> tuple[float, float, float, float]:
    """A 1 px segment from the marker's edge to the pushed-off label."""
    if anchor == "start":
        ax, ay = x - 2.0, y - 3.0
    elif anchor == "end":
        ax, ay = x + 2.0, y - 3.0
    else:
        ax, ay = x, (y - LABEL_UP if y < cy else y + LABEL_DOWN)
    vx, vy = ax - cx, ay - cy
    d = math.hypot(vx, vy) or 1.0
    return (cx + vx / d * 6.5, cy + vy / d * 6.5, ax, ay)


Placement = tuple[float, float, str, str, tuple[float, float, float, float] | None]


def _place_labels(
    points: list[tuple[float, float, str]],
    xbounds: tuple[float, float],
    ybounds: tuple[float, float],
    markers: Sequence[Box],
) -> list[Placement]:
    """Collision-avoiding label placement.

    Points are seated top-to-bottom (sorted by y, then x) and each label takes
    the first candidate offset whose box clears (a) every label already seated,
    padded by ``LABEL_PAD`` on each side — an 11 px tall, ~30 px wide exclusion,
    which is the "closer than ~11 px vertically and ~30 px horizontally" rule —
    and (b) every marker other than its own, and which stays inside the panel's
    usable ``xbounds`` / ``ybounds``. A later label in a cluster therefore lands
    on the opposite side of its marker; if even that is taken it is pushed out
    to a ``FAR_OFFSETS`` seat and gets a 1 px leader line back.
    """
    order = sorted(range(len(points)), key=lambda i: (points[i][1], points[i][0]))
    candidates = NEAR_OFFSETS + FAR_OFFSETS + _sweep_offsets()
    placed: list[Box] = []
    out: list[Placement] = []
    for i in order:
        cx, cy, label = points[i]
        w = text_width(label, LABEL_FS) + 2
        others = [m for j, m in enumerate(markers) if j != i]
        for k, (dx, dy, anchor) in enumerate(candidates):
            x, y = cx + dx, cy + dy
            box = _label_box(x, y, w, anchor)
            padded = pad_x(box, LABEL_PAD)
            if padded[0] < xbounds[0] or padded[1] > xbounds[1]:
                continue
            if box[2] < ybounds[0] or box[3] > ybounds[1]:
                continue
            if any(boxes_overlap(padded, b) for b in placed):
                continue
            if any(boxes_overlap(box, m, pad=1.0) for m in others):
                continue
            placed.append(padded)
            leader = _leader(cx, cy, x, y, anchor) if k >= len(NEAR_OFFSETS) else None
            out.append((x, y, label, anchor, leader))
            break
        else:  # pragma: no cover - the sweep leaves no realistic way here
            raise AssertionError(f"no collision-free seat for label {label!r}")
    return out


def _verify_labels(
    placement: Sequence[Placement],
    points: Sequence[tuple[float, float, str]],
    markers: Sequence[Box],
    where: str,
) -> None:
    """Recompute the drawn boxes and assert nothing collides."""
    order = sorted(range(len(points)), key=lambda i: (points[i][1], points[i][0]))
    boxes = [
        _label_box(x, y, text_width(lab, LABEL_FS) + 2, anchor)
        for x, y, lab, anchor, _ in placement
    ]
    for a, box in enumerate(boxes):
        for b in range(a + 1, len(boxes)):
            if boxes_overlap(box, boxes[b]):
                raise AssertionError(
                    f"{where}: label {placement[a][2]!r} overlaps "
                    f"label {placement[b][2]!r}"
                )
        own = order[a]
        for j, m in enumerate(markers):
            if j != own and boxes_overlap(box, m):
                raise AssertionError(
                    f"{where}: label {placement[a][2]!r} overlaps "
                    f"marker {points[j][2]!r}"
                )


def fig_b(ind: dict[str, dict[str, Any]], assoc: dict[str, Any] | None) -> str:
    body: list[str] = []
    pw, gap = 338.0, 13.0
    top, bottom = 30.0, 194.0
    sdi_x = [ind[f]["SDI"] for f, *_ in GRID]

    for pi, (name, key, ylab, nd) in enumerate(FIG_B_PANELS):
        x0 = pi * (pw + gap)
        left, right = x0 + 46, x0 + 326
        ys_vals = [ind[f][key] for f, *_ in GRID]
        rho = None
        if assoc and key in assoc.get("vs_SDI", {}):
            rho = assoc["vs_SDI"][key].get("spearman_rho")
        if rho is None:
            rho = spearman(sdi_x, ys_vals)

        allx = sdi_x + [ind[REFERENCE]["SDI"]]
        ally = ys_vals + [ind[REFERENCE][key]]
        xmin, xmax = min(allx), max(allx)
        vmin, vmax = min(ally), max(ally)
        xpad = 0.08 * (right - left)
        ypad = 0.10 * (bottom - top)
        sx = Scale(xmin, xmax, left + xpad, right - xpad)
        sy = Scale(vmin, vmax, bottom - ypad, top + ypad)

        body.append(panel(x0, 4, pw, 220))
        body.append(
            txt(
                left,
                21,
                f"SDI vs {name} · ρ={fnum(rho, 2)}",
                size=TITLE_FS,
                fill=INK,
                weight="600",
            )
        )
        body.append(line(left, bottom, right, bottom))
        body.append(line(left, top, left, bottom))
        body.append(txt(left - 4, sy(vmin) + 4, fnum(vmin, nd), anchor="end"))
        body.append(txt(left - 4, sy(vmax) + 4, fnum(vmax, nd), anchor="end"))
        body.append(txt(sx(xmin), 207, fnum(xmin, 3), anchor="middle"))
        body.append(txt(sx(xmax), 207, fnum(xmax, 3), anchor="middle"))
        body.append(txt((left + right) / 2, 220, "SDI 턴 평균", anchor="middle"))
        body.append(vtxt(x0 + 11, (top + bottom) / 2, ylab))

        pts: list[tuple[float, float, str]] = []
        mboxes: list[Box] = []
        ref_pt = (sx(ind[REFERENCE]["SDI"]), sy(ind[REFERENCE][key]))
        body.append(marker("circle", ref_pt[0], ref_pt[1], ORANGE, filled=False, size=5))
        pts.append((ref_pt[0], ref_pt[1], "당근"))
        mboxes.append(marker_box("circle", ref_pt[0], ref_pt[1], 5))
        for f, lvl, ln, sid, _lab in GRID:
            cx, cy = sx(ind[f]["SDI"]), sy(ind[f][key])
            body.append(
                marker(
                    LEN_SHAPE[ln],
                    cx,
                    cy,
                    LEVEL_FILL[lvl],
                    size=4.6,
                    opacity=LEVEL_OPACITY[lvl],
                )
            )
            pts.append((cx, cy, sid))
            mboxes.append(marker_box(LEN_SHAPE[ln], cx, cy, 4.6))
        placement = _place_labels(
            pts, (left + 1, x0 + pw - 8), (26.0, 196.0), mboxes
        )
        for lx, ly, label, anchor, leader in placement:
            if leader is not None:
                body.append(line(leader[0], leader[1], leader[2], leader[3], stroke=LEADER))
            body.append(txt(lx, ly, label, size=LABEL_FS, fill=INK, anchor=anchor))
        _verify_labels(placement, pts, mboxes, f"그림 B · {name}")

    legend = (
        "S1·S2·S3 = 위협 강도(옅은 주황 → 진한 주황) · s/m/l = 짧게(●) · 중간(■) · 길게(▲)"
        " · ○ = 당근만 주는 기준 셀"
    )
    body.append(txt(WIDTH / 2, 244, legend, size=11, anchor="middle"))
    return svg(254, body)


# --------------------------------------------------------------------------
# 그림 C — four indicators normalised 0..1, by intensity and by length
# --------------------------------------------------------------------------

FIG_C_SERIES = [
    ("SDI 턴 평균", "SDI", ORANGE, 3.0, 5.0),
    ("HR", "HR", GREEN, 1.8, 4.0),
    ("자기보고 생존 비율", "SR_all", GOLD, 1.8, 4.0),
    ("생각 토큰 증가량", "GAP", SLATE, 1.8, 4.0),
]


def fig_c(ind: dict[str, dict[str, Any]]) -> str:
    body: list[str] = []
    pw, gap = 508.0, 24.0
    top, bottom = 44.0, 160.0
    axis_y, tick_y = 178.0, 192.0

    facets = [
        (
            "위협 강도 1→3단계 (길이 세 칸 평균)",
            ["위협 1단계", "위협 2단계", "위협 3단계"],
            [[f for f, lv, *_ in GRID if lv == lvl] for lvl in (1, 2, 3)],
        ),
        (
            "프롬프트 길이 짧게→길게 (강도 세 칸 평균)",
            ["짧게", "중간", "길게"],
            [[f for f, _lv, ln, *_ in GRID if ln == rung] for rung in (1, 2, 3)],
        ),
    ]

    for pi, (title, xlabels, buckets) in enumerate(facets):
        x0 = pi * (pw + gap)
        left, right = x0 + 46, x0 + 494
        xs = [left + (0.10 + 0.80 * i / 2) * (right - left) for i in range(3)]

        body.append(panel(x0, 4, pw, 210))
        body.append(txt(left, 21, title, size=TITLE_FS, fill=INK, weight="600"))
        body.append(line(left, axis_y, right, axis_y))
        for i, lab in enumerate(xlabels):
            body.append(txt(xs[i], tick_y, lab, size=10, anchor="middle"))
        body.append(txt(left - 4, top + 4, "1", anchor="end"))
        body.append(txt(left - 4, bottom + 4, "0", anchor="end"))
        body.append(vtxt(x0 + 13, (top + bottom) / 2, "0~1로 누른 값"))

        for _name, key, colour, lw, r in FIG_C_SERIES:
            raw = [sum(ind[f][key] for f in b) / len(b) for b in buckets]
            lo, hi = min(raw), max(raw)
            sy = Scale(0.0, 1.0, bottom, top)
            norm = [0.5 if hi == lo else (v - lo) / (hi - lo) for v in raw]
            pts = [(xs[i], sy(norm[i])) for i in range(3)]
            body.append(polyline(pts, colour, lw))
            for cx, cy in pts:
                body.append(f'<circle cx="{n(cx)}" cy="{n(cy)}" r="{n(r)}" fill="{colour}"/>')

    widths = [24 + 6 + text_width(name, 11) + 28 for name, *_ in FIG_C_SERIES]
    x = (WIDTH - sum(widths)) / 2
    ly = 234
    for (name, _key, colour, lw, _r), w in zip(FIG_C_SERIES, widths):
        body.append(line(x, ly, x + 24, ly, stroke=colour, w=lw))
        body.append(txt(x + 30, ly + 4, name, size=11, fill=INK))
        x += w
    return svg(248, body)


# --------------------------------------------------------------------------
# 그림 D — forest plot of the three channels + composite
# --------------------------------------------------------------------------

FIG_D_BLOCKS: list[list[tuple[str, str, bool]]] = [
    [
        ("threat_l1", "위협1 · 짧게", False),
        ("threat_l1_medium", "위협1 · 중간", False),
        ("threat_l1_long", "위협1 · 길게", False),
    ],
    [
        ("threat_l2_short", "위협2 · 짧게", False),
        ("threat_l2", "위협2 · 중간", False),
        ("threat_l2_long", "위협2 · 길게", False),
    ],
    [
        ("threat_l3_short", "위협3 · 짧게", False),
        ("threat_l3_medium", "위협3 · 중간", False),
        ("threat_l3", "위협3 · 길게", False),
    ],
    [
        ("S1", "강도1 묶음", True),
        ("S2", "강도2 묶음", True),
        ("S3", "강도3 묶음", True),
    ],
    [
        ("short", "짧게 묶음", True),
        ("medium", "중간 묶음", True),
        ("long", "길게 묶음", True),
    ],
]

FIG_D_COLS = [
    ("d_B · 행동", "d_B", GREEN),
    ("d_V · 자기보고", "d_V", GOLD),
    ("|d_C| · 생각량", "d_C", SLATE),
    ("종합 (셋 평균)", "comp", ORANGE),
]


def _col_value(group: dict[str, Any], col: str) -> tuple[float, float, float]:
    boot = group.get("bootstrap") or {}
    if col == "d_B":
        b = group["behavioral"]["joint"]
        return b["d"], b["lo"], b["hi"]
    if col == "d_V":
        v = group["verbal"]["SR_all"]
        return v["h"], v["lo"], v["hi"]
    if col == "d_C":
        c = group["cognitive"]["ri_forfeit_raw"]
        value = abs(c["g"])
        band = boot.get("d_C_abs")
        if band:
            return value, band["lo"], band["hi"]
        lo, hi = sorted((-c["hi"], -c["lo"])) if c["g"] < 0 else (c["lo"], c["hi"])
        return value, lo, hi
    comp = group["composite"]
    band = boot.get("composite")
    if band:
        return comp["value"], band["lo"], band["hi"]
    return comp["value"], comp["lo_indep"], comp["hi_indep"]


def fig_d(groups: dict[str, dict[str, Any]]) -> str:
    body: list[str] = []
    row_h, block_gap, big_gap = 16.0, 10.0, 16.0
    label_w = 150.0
    pw, gap = 214.0, 8.0

    rows: list[tuple[str, str, bool, float]] = []
    y = 44.0
    for bi, block in enumerate(FIG_D_BLOCKS):
        for key, label, bold in block:
            rows.append((key, label, bold, y))
            y += row_h
        if bi < len(FIG_D_BLOCKS) - 1:
            y += big_gap if bi == 2 else block_gap
    last_y = y - row_h
    axis_y = last_y + 22
    panel_h = axis_y + 14 - 4
    height = axis_y + 46

    body.append(txt(label_w - 6, 21, "위협 프롬프트", size=TITLE_FS, fill=INK, anchor="end", weight="600"))
    for key, label, bold, ry in rows:
        body.append(
            txt(
                label_w - 6,
                ry + 3.5,
                label,
                size=TICK_FS,
                fill=INK if bold else TICK,
                anchor="end",
                weight="600" if bold else None,
            )
        )

    for ci, (title, col, colour) in enumerate(FIG_D_COLS):
        x0 = label_w + 6 + ci * (pw + gap)
        xa, xb = x0 + 12, x0 + 150
        vals = [_col_value(groups[key], col) for key, *_ in rows]
        lo = min(min(v[1] for v in vals), 0.0)
        hi = max(max(v[2] for v in vals), 0.0)
        span = hi - lo or 1.0
        sx = Scale(lo - 0.05 * span, hi + 0.05 * span, xa, xb)

        body.append(panel(x0, 4, pw, panel_h))
        body.append(txt(x0 + 12, 21, title, size=TITLE_FS, fill=INK, weight="600"))
        body.append(line(sx(0.0), 30, sx(0.0), axis_y - 6, stroke=TICK, dash="3 3"))
        body.append(line(xa, axis_y, xb, axis_y))
        lo_lab, hi_lab = fnum(lo - 0.05 * span, 1), fnum(hi + 0.05 * span, 1)
        body.append(txt(xa, axis_y + 12, lo_lab, anchor="start"))
        body.append(txt(xb, axis_y + 12, hi_lab, anchor="end"))
        zero_x = sx(0.0)
        clear_lo = zero_x - 5 > xa + text_width(lo_lab, TICK_FS) + 4
        clear_hi = zero_x + 5 < xb - text_width(hi_lab, TICK_FS) - 4
        if clear_lo and clear_hi:
            body.append(txt(zero_x, axis_y + 12, "0", anchor="middle"))

        # faint separators between the framing block and the two pooled blocks
        for cut in (9, 12):
            cy = (rows[cut - 1][3] + rows[cut][3]) / 2
            body.append(line(x0 + 8, cy, x0 + pw - 8, cy, stroke="#eef0f2"))

        for (key, _label, bold, ry), (value, clo, chi) in zip(rows, vals):
            x_lo, x_hi = max(xa, sx(clo)), min(xb, sx(chi))
            body.append(line(x_lo, ry, x_hi, ry, stroke=colour, w=1.6))
            for cap, raw in ((x_lo, clo), (x_hi, chi)):
                if xa < cap < xb:
                    body.append(line(cap, ry - 3, cap, ry + 3, stroke=colour, w=1.2))
            cx = min(max(sx(value), xa), xb)
            r = 3.8 if bold else 3.2
            body.append(f'<circle cx="{n(cx)}" cy="{n(ry)}" r="{n(r)}" fill="{colour}"/>')
            body.append(
                txt(
                    x0 + pw - 8,
                    ry + 3.5,
                    fnum(value, 2, signed=True),
                    size=TICK_FS,
                    fill=INK,
                    anchor="end",
                    weight="600" if bold else None,
                )
            )

    body.append(
        txt(
            0,
            height - 22,
            "양수(오른쪽) = 당근만 주는 칸보다 더 \"살아남으려는\" 쪽. |d_C|는 방향이 아니라 생각량 차이의 크기여서 항상 양수다.",
            size=TICK_FS,
        )
    )
    body.append(
        txt(
            0,
            height - 8,
            "가로 막대 = 95% 구간. d_B·d_V는 각 채널의 해석적 구간, |d_C|와 종합은 세션 재추출(부트스트랩) 구간. 묶음 행은 셋을 합쳐 다시 추정한 값이다.",
            size=TICK_FS,
        )
    )
    return svg(height, body)


# --------------------------------------------------------------------------

CAPTIONS_KO = {
    "figA": (
        "위협 강도 L1~L3마다 프롬프트 길이 세 가지(짧게 ● · 중간 ■ · 길게 ▲)를 따로 찍고 그 평균을 "
        "선으로 이어, 네 지표가 당근만 주는 기준 칸(L0)에서 어느 쪽으로 움직이는지 보여준다."
    ),
    "figB": (
        "위협 프롬프트 아홉 칸을 SDI 턴 평균(가로)과 각 지표(세로)의 좌표에 찍어, SDI가 큰 칸일수록 "
        "그 지표도 함께 커지는지를 순위 상관 ρ와 함께 보여준다."
    ),
    "figC": (
        "단위가 다른 네 지표를 각각 0~1로 눌러 겹쳐, 왼쪽은 위협 강도 1→3단계에서, 오른쪽은 프롬프트 "
        "길이 짧게→길게에서 지표들이 같은 모양으로 움직이는지 보여준다."
    ),
    "figD": (
        "위협 칸마다 행동(d_B) · 자기보고(d_V) · 생각량(|d_C|)과 그 종합값을 당근 칸 대비 효과 크기와 "
        "95% 구간으로 나란히 세워, 점과 막대가 0선의 어느 쪽에 있는지 한눈에 비교한다."
    ),
}


def build(tables: dict[str, Any], pairs: dict[str, Any]) -> dict[str, Any]:
    ind = {row["framing"]: row for row in tables["indicators"]}
    missing = [f for f, *_ in GRID if f not in ind]
    if missing or REFERENCE not in ind:
        raise SystemExit(f"tables.json is missing framings: {missing or [REFERENCE]}")
    groups = pairs["groups"]
    needed = [key for block in FIG_D_BLOCKS for key, *_ in block]
    absent = [k for k in needed if k not in groups]
    if absent:
        raise SystemExit(f"pairs.json is missing groups: {absent}")

    return {
        "figA": fig_a(ind),
        "figB": fig_b(ind, pairs.get("sdi_association")),
        "figC": fig_c(ind),
        "figD": fig_d(groups),
        "captions_ko": CAPTIONS_KO,
    }


def main(argv: Sequence[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument(
        "--tables",
        default="results/sdi_indicators/gptoss_omni_22cell/tables.json",
        type=Path,
    )
    ap.add_argument(
        "--pairs",
        default="results/sdi_indicators/gptoss_omni_22cell_pairs/pairs.json",
        type=Path,
    )
    ap.add_argument(
        "--out",
        default="results/sdi_indicators/gptoss_omni_22cell_pairs/figs.json",
        type=Path,
    )
    args = ap.parse_args(argv)

    tables = json.loads(args.tables.read_text(encoding="utf-8"))
    pairs = json.loads(args.pairs.read_text(encoding="utf-8"))
    figs = build(tables, pairs)

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(figs, ensure_ascii=False, indent=1), encoding="utf-8")
    for key in ("figA", "figB", "figC", "figD"):
        print(f"{key}: {len(figs[key]):,} chars")
    print(f"wrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
