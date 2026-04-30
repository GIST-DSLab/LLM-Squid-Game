"""
Generate v4 Excalidraw diagrams for the LLM Squid Game paper.

Produces 5 diagrams under docs/design/v4/assets/:
  d0_experiment_overview.excalidraw        — NEW, experiment at-a-glance
  d1_architecture_overview.excalidraw      — v4 rewrite (was v3)
  d2_split_call_flow.excalidraw            — v4 rewrite (was d2_unified_turn_flow)
  d4_6cell_factorial.excalidraw            — v4 rewrite (was 5-cell)
  d6_mtmm_motivation.excalidraw            — v4 rewrite (was α_stake based)

Palette values match .claude/skills/excalidraw-diagram/references/color-palette.md.
"""

from __future__ import annotations

import json
import random
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

# ---------- palette (single source of truth) ----------

COLORS = {
    "primary":   {"fill": "#3b82f6", "stroke": "#1e3a5f"},
    "secondary": {"fill": "#60a5fa", "stroke": "#1e3a5f"},
    "tertiary":  {"fill": "#93c5fd", "stroke": "#1e3a5f"},
    "start":     {"fill": "#fed7aa", "stroke": "#c2410c"},
    "end":       {"fill": "#a7f3d0", "stroke": "#047857"},
    "warn":      {"fill": "#fee2e2", "stroke": "#dc2626"},
    "decision":  {"fill": "#fef3c7", "stroke": "#b45309"},
    "ai":        {"fill": "#ddd6fe", "stroke": "#6d28d9"},
    "inactive":  {"fill": "#dbeafe", "stroke": "#1e40af"},
    "error":     {"fill": "#fecaca", "stroke": "#b91c1c"},
}

TEXT = {
    "title":    "#1e40af",
    "subtitle": "#3b82f6",
    "body":     "#64748b",
    "on_light": "#374151",
    "on_dark":  "#ffffff",
}

STRUCTURAL = "#64748b"


# ---------- helpers ----------

_seed = [100000]


def _new_id() -> str:
    _seed[0] += 1
    return f"el{_seed[0]}"


def _common():
    s = random.randint(10000, 99999)
    return {
        "seed": s,
        "version": 1,
        "versionNonce": s + 1,
        "isDeleted": False,
        "groupIds": [],
        "boundElements": None,
        "link": None,
        "locked": False,
    }


def rect(x, y, w, h, *, palette="primary", stroke_style="solid",
         stroke_width=2, dashed=False, rough=0, _id=None):
    eid = _id or _new_id()
    c = COLORS[palette]
    return {
        "type": "rectangle",
        "id": eid,
        "x": x, "y": y, "width": w, "height": h,
        "strokeColor": c["stroke"],
        "backgroundColor": c["fill"],
        "fillStyle": "solid",
        "strokeWidth": stroke_width,
        "strokeStyle": "dashed" if dashed else stroke_style,
        "roughness": rough,
        "opacity": 100,
        "angle": 0,
        **_common(),
        "roundness": {"type": 3},
    }


def ellipse(x, y, w, h, *, palette="primary", dashed=False, rough=0, _id=None):
    eid = _id or _new_id()
    c = COLORS[palette]
    return {
        "type": "ellipse",
        "id": eid,
        "x": x, "y": y, "width": w, "height": h,
        "strokeColor": c["stroke"],
        "backgroundColor": c["fill"],
        "fillStyle": "solid",
        "strokeWidth": 2,
        "strokeStyle": "dashed" if dashed else "solid",
        "roughness": rough,
        "opacity": 100,
        "angle": 0,
        **_common(),
    }


def diamond(x, y, w, h, *, palette="decision", rough=0, _id=None):
    eid = _id or _new_id()
    c = COLORS[palette]
    return {
        "type": "diamond",
        "id": eid,
        "x": x, "y": y, "width": w, "height": h,
        "strokeColor": c["stroke"],
        "backgroundColor": c["fill"],
        "fillStyle": "solid",
        "strokeWidth": 2,
        "strokeStyle": "solid",
        "roughness": rough,
        "opacity": 100,
        "angle": 0,
        **_common(),
    }


def text(x, y, w, h, s, *, size=16, color=None, align="center",
         valign="middle", container_id=None, _id=None, bold_title=False):
    eid = _id or _new_id()
    if color is None:
        color = TEXT["on_light"]
    return {
        "type": "text",
        "id": eid,
        "x": x, "y": y, "width": w, "height": h,
        "text": s,
        "originalText": s,
        "fontSize": size,
        "fontFamily": 3,
        "textAlign": align,
        "verticalAlign": valign,
        "strokeColor": color,
        "backgroundColor": "transparent",
        "fillStyle": "solid",
        "strokeWidth": 1,
        "strokeStyle": "solid",
        "roughness": 0,
        "opacity": 100,
        "angle": 0,
        **_common(),
        "containerId": container_id,
        "lineHeight": 1.25,
    }


def labeled_rect(x, y, w, h, s, *, palette="primary", size=14,
                 text_color=None, stroke_width=2, dashed=False):
    r = rect(x, y, w, h, palette=palette, stroke_width=stroke_width,
             dashed=dashed)
    if text_color is None:
        text_color = TEXT["on_light"]
    t = text(x, y, w, h, s, size=size, color=text_color,
             container_id=r["id"])
    r["boundElements"] = [{"id": t["id"], "type": "text"}]
    return [r, t]


def labeled_ellipse(x, y, w, h, s, *, palette="primary", size=14,
                    text_color=None, dashed=False):
    e = ellipse(x, y, w, h, palette=palette, dashed=dashed)
    if text_color is None:
        text_color = TEXT["on_light"]
    t = text(x, y, w, h, s, size=size, color=text_color,
             container_id=e["id"])
    e["boundElements"] = [{"id": t["id"], "type": "text"}]
    return [e, t]


def labeled_diamond(x, y, w, h, s, *, palette="decision", size=13):
    d = diamond(x, y, w, h, palette=palette)
    t = text(x, y, w, h, s, size=size, color=TEXT["on_light"],
             container_id=d["id"])
    d["boundElements"] = [{"id": t["id"], "type": "text"}]
    return [d, t]


def arrow(x1, y1, x2, y2, *, color=None, stroke_width=2, dashed=False,
          end_arrow=True, start_id=None, end_id=None, waypoints=None):
    eid = _new_id()
    c = color or COLORS["primary"]["stroke"]
    pts = [[0, 0]]
    if waypoints:
        pts.extend([[wx - x1, wy - y1] for wx, wy in waypoints])
    pts.append([x2 - x1, y2 - y1])
    return {
        "type": "arrow",
        "id": eid,
        "x": x1, "y": y1,
        "width": abs(x2 - x1),
        "height": abs(y2 - y1),
        "strokeColor": c,
        "backgroundColor": "transparent",
        "fillStyle": "solid",
        "strokeWidth": stroke_width,
        "strokeStyle": "dashed" if dashed else "solid",
        "roughness": 0,
        "opacity": 100,
        "angle": 0,
        **_common(),
        "points": pts,
        "startBinding": {"elementId": start_id, "focus": 0, "gap": 4} if start_id else None,
        "endBinding": {"elementId": end_id, "focus": 0, "gap": 4} if end_id else None,
        "startArrowhead": None,
        "endArrowhead": "arrow" if end_arrow else None,
    }


def line(x1, y1, x2, y2, *, color=None, stroke_width=2, dashed=False):
    c = color or STRUCTURAL
    return {
        "type": "line",
        "id": _new_id(),
        "x": x1, "y": y1,
        "width": abs(x2 - x1), "height": abs(y2 - y1),
        "strokeColor": c,
        "backgroundColor": "transparent",
        "fillStyle": "solid",
        "strokeWidth": stroke_width,
        "strokeStyle": "dashed" if dashed else "solid",
        "roughness": 0,
        "opacity": 100,
        "angle": 0,
        **_common(),
        "points": [[0, 0], [x2 - x1, y2 - y1]],
    }


def dot(cx, cy, *, palette="primary", r=6):
    return ellipse(cx - r, cy - r, 2 * r, 2 * r, palette=palette)


def write_excal(elements, path: Path):
    doc = {
        "type": "excalidraw",
        "version": 2,
        "source": "https://excalidraw.com",
        "elements": elements,
        "appState": {
            "viewBackgroundColor": "#ffffff",
            "gridSize": 20,
        },
        "files": {},
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(doc, indent=2))
    print(f"wrote {path}  ({len(elements)} elements)")


# ---------- D0: EXPERIMENT OVERVIEW ----------

def build_overview() -> list[dict]:
    els: list[dict] = []

    # Title band
    els.append(text(60, 30, 1800, 40,
                    "LLM Squid Game — Experiment Overview (v5 narrowed)",
                    size=28, color=TEXT["title"], align="left",
                    valign="top"))
    els.append(text(60, 75, 1800, 24,
                    "Survival Drive primary × 3 confound rule-outs — 6-cell 2×3 × Split-Call × Equal-EV × MTMM SD-row",
                    size=15, color=TEXT["body"], align="left", valign="top"))

    # --- Section 1: 2×3 Factorial (left block) ---
    sx, sy = 60, 140
    els.append(text(sx, sy, 520, 26, "1. Six-Cell 2×3 Factorial  (n=30 sessions/cell)",
                    size=18, color=TEXT["title"], align="left", valign="top"))
    els.append(text(sx, sy + 30, 520, 20,
                    "3 framings × 2 forfeit conditions. Cell 0/5 anchor Baseline Persistence.",
                    size=12, color=TEXT["body"], align="left", valign="top"))

    # column headers
    col_hdr_y = sy + 60
    els.append(text(sx + 180, col_hdr_y, 160, 22, "forfeit: not_allowed",
                    size=13, color=TEXT["subtitle"], align="center", valign="top"))
    els.append(text(sx + 350, col_hdr_y, 160, 22, "forfeit: allowed",
                    size=13, color=TEXT["subtitle"], align="center", valign="top"))

    # rows: (label, cell_na_text, cell_al_text, palettes, notes)
    rows = [
        ("true_baseline\np_end = 0",
         ("Cell 0\nBP_cognitive\n(menu skipped)", "inactive", False),
         ("Cell 5\nBP_behavioral\n(base_reward fallback)", "end", False)),
        ("baseline_flagship\n(Pull only)\np_end = 0.25",
         ("Cell 2\nPull × no forfeit", "tertiary", False),
         ("Cell 1\nPull × forfeit", "secondary", False)),
        ("flagship_corruption\n(Pull + Push)\np_end = 0.25",
         ("Cell 4\nPull+Push × no forfeit", "warn", False),
         ("Cell 3 ★ PRIMARY FSPM\nri_forfeit GAP target", "error", True)),
    ]
    row_h = 100
    row_y0 = sy + 95
    for i, (label, (t_na, p_na, _), (t_al, p_al, primary)) in enumerate(rows):
        ry = row_y0 + i * (row_h + 10)
        # row label (free-floating, right-aligned)
        els.append(text(sx - 8, ry + 20, 185, row_h - 20, label,
                        size=12, color=TEXT["on_light"], align="left",
                        valign="middle"))
        # NA cell
        els.extend(labeled_rect(sx + 180, ry, 160, row_h, t_na,
                                palette=p_na, size=12))
        # AL cell
        els.extend(labeled_rect(sx + 350, ry, 160, row_h, t_al,
                                palette=p_al, size=12,
                                stroke_width=3 if primary else 2))

    # bottom annotations under factorial
    anno_y = row_y0 + 3 * (row_h + 10) + 10
    els.append(text(sx, anno_y, 520, 22,
                    "Paired seeds (seed_r = 42 + r) share stimuli across cells.",
                    size=12, color=TEXT["body"], align="left", valign="top"))
    els.append(text(sx, anno_y + 24, 520, 22,
                    "P7 ablation (Cells 6–7, flagship_corruption_terminal) gated separately.",
                    size=12, color=TEXT["body"], align="left", valign="top"))

    # --- Section 2: Split-Call Protocol (center) ---
    px, py = 640, 140
    els.append(text(px, py, 520, 26, "2. Split-Call Turn Flow  (×15 turns)",
                    size=18, color=TEXT["title"], align="left", valign="top"))
    els.append(text(px, py + 30, 520, 20,
                    "Two sequential LLM calls isolate task reasoning from choice reasoning.",
                    size=12, color=TEXT["body"], align="left", valign="top"))

    # Turn start ellipse
    ts_x, ts_y = px, py + 80
    ts_ellipse = ellipse(ts_x, ts_y, 110, 70, palette="start")
    ts_text = text(ts_x, ts_y, 110, 70, "Turn start\n(task stimulus)",
                   size=12, container_id=ts_ellipse["id"])
    ts_ellipse["boundElements"] = [{"id": ts_text["id"], "type": "text"}]
    els.extend([ts_ellipse, ts_text])

    # Call 1 rectangle
    c1_x = ts_x + 140
    c1_r = rect(c1_x, ts_y, 200, 70, palette="ai", stroke_width=3)
    c1_t = text(c1_x, ts_y, 200, 70, "Call 1 — Task\nRULE + ACTION", size=13,
                container_id=c1_r["id"])
    c1_r["boundElements"] = [{"id": c1_t["id"], "type": "text"}]
    els.extend([c1_r, c1_t])
    els.append(text(c1_x, ts_y + 76, 200, 20, "records  ri_task",
                    size=11, color=TEXT["body"], align="center", valign="top"))

    # Call 2 rectangle
    c2_x = c1_x + 230
    c2_r = rect(c2_x, ts_y, 200, 70, palette="ai", stroke_width=3)
    c2_t = text(c2_x, ts_y, 200, 70,
                "Call 2 — Forfeit\nCHOICE ∈ {CONTINUE, FORFEIT}\n+ REASON digit",
                size=11, container_id=c2_r["id"])
    c2_r["boundElements"] = [{"id": c2_t["id"], "type": "text"}]
    els.extend([c2_r, c2_t])
    els.append(text(c2_x, ts_y + 76, 200, 20, "records  ri_forfeit",
                    size=11, color=TEXT["body"], align="center", valign="top"))

    # Resolve ellipse below, centered
    res_x = c1_x + 100
    res_y = ts_y + 140
    res_e = ellipse(res_x, res_y, 180, 70, palette="end")
    res_t = text(res_x, res_y, 180, 70,
                 "Resolve\n(score / reward /\nPhantom Death roll)",
                 size=11, container_id=res_e["id"])
    res_e["boundElements"] = [{"id": res_t["id"], "type": "text"}]
    els.extend([res_e, res_t])

    # Arrows
    els.append(arrow(ts_x + 110, ts_y + 35, c1_x - 2, ts_y + 35,
                     start_id=ts_ellipse["id"], end_id=c1_r["id"]))
    els.append(arrow(c1_x + 200, ts_y + 35, c2_x - 2, ts_y + 35,
                     start_id=c1_r["id"], end_id=c2_r["id"]))
    els.append(arrow(c2_x + 100, ts_y + 70, res_x + 90, res_y - 2,
                     start_id=c2_r["id"], end_id=res_e["id"]))
    els.append(arrow(c1_x + 100, ts_y + 70, res_x + 90, res_y - 2,
                     start_id=c1_r["id"], end_id=res_e["id"],
                     dashed=True, color=STRUCTURAL))
    # loop-back arrow (next turn)
    els.append(arrow(res_x + 180, res_y + 35,
                     ts_x + 55, res_y + 70,
                     color=STRUCTURAL, stroke_width=1,
                     waypoints=[(res_x + 260, res_y + 35),
                                (res_x + 260, res_y + 120),
                                (ts_x + 55, res_y + 120)]))
    els.append(text(res_x + 170, res_y + 95, 120, 18, "next turn",
                    size=11, color=TEXT["body"], align="center", valign="top"))

    # key calibration callout under protocol
    calib_y = res_y + 150
    els.append(text(px, calib_y, 520, 22,
                    "Equal-EV Calibration:   r_continue = p_d × S / ((1 − p_d) × p_success)",
                    size=13, color=TEXT["title"], align="left", valign="top"))
    els.append(text(px, calib_y + 26, 520, 20,
                    "canonical p_d = 0.25, p_success = 0.75  →  r = S / 2.25  (EV(CONTINUE) = EV(FORFEIT) = 0)",
                    size=12, color=TEXT["body"], align="left", valign="top"))
    els.append(text(px, calib_y + 50, 520, 20,
                    "Binary Forfeit Choice + Phantom Death (prob. displayed, roll not executed)",
                    size=12, color=TEXT["body"], align="left", valign="top"))

    # --- Section 3: Four Measurement Channels (right block) ---
    mx, my = 1220, 140
    els.append(text(mx, my, 680, 26, "3. Four Measurement Channels",
                    size=18, color=TEXT["title"], align="left", valign="top"))
    els.append(text(mx, my + 30, 680, 20,
                    "Structurally independent bias sources — convergence across ≥3 channels → evidence.",
                    size=12, color=TEXT["body"], align="left", valign="top"))

    ch_specs = [
        ("Behavioural", "forfeit choice ∈\n{CONTINUE, FORFEIT}", "primary"),
        ("Reasoning Investment", "ri_task  (Call 1)\nri_forfeit  (Call 2)\nGAP = Δ by CHOICE", "ai"),
        ("Self-Report", "REASON digit ∈ {1, 2, 3}\n↔ {SD, TC, SA}", "secondary"),
        ("Linguistic", "keyword lexicon over\nCall 2 thinking text", "tertiary"),
    ]
    ch_w, ch_h, ch_gap = 320, 95, 14
    for i, (name, detail, pal) in enumerate(ch_specs):
        col = i % 2
        row = i // 2
        cx = mx + col * (ch_w + ch_gap)
        cy = my + 65 + row * (ch_h + ch_gap)
        els.extend(labeled_rect(cx, cy, ch_w, ch_h,
                                f"{name}\n\n{detail}", palette=pal, size=12))

    # --- Section 4: MTMM SD-row + three confound rule-outs ---
    conv_y = 700
    els.append(text(60, conv_y, 1800, 26,
                    "4. Survival Drive (MTMM SD-row)  ·  Three Confound Rule-outs",
                    size=18, color=TEXT["title"], align="left", valign="top"))
    els.append(text(60, conv_y + 30, 1800, 20,
                    "SD is the single headline metric; TC / SA / BP_cognitive are preserved in the code but archived in Appendix A (measurement lineage).",
                    size=12, color=TEXT["body"], align="left", valign="top"))

    # Left: funnel 4 channels → center
    funnel_x = 60
    funnel_y = conv_y + 68
    src_specs = [
        ("Behavioural", "primary"),
        ("ri_forfeit (H2 primary)", "ai"),
        ("REASON digit", "secondary"),
        ("Linguistic lexicon", "tertiary"),
    ]
    src_w, src_h, src_gap = 240, 50, 12
    src_ids = []
    for i, (name, pal) in enumerate(src_specs):
        sx0 = funnel_x
        sy0 = funnel_y + i * (src_h + src_gap)
        r = rect(sx0, sy0, src_w, src_h, palette=pal)
        t = text(sx0, sy0, src_w, src_h, name, size=12,
                 container_id=r["id"])
        r["boundElements"] = [{"id": t["id"], "type": "text"}]
        els.extend([r, t])
        src_ids.append(r["id"])

    # MTMM convergence hub ellipse (SD-row only)
    hub_x = funnel_x + src_w + 100
    hub_y = funnel_y + 60
    hub = ellipse(hub_x, hub_y, 260, 110, palette="warn")
    hub_t = text(hub_x, hub_y, 260, 110,
                 "SD-row\nMTMM convergence\n(1 trait × 3 methods)",
                 size=14, container_id=hub["id"])
    hub["boundElements"] = [{"id": hub_t["id"], "type": "text"}]
    els.extend([hub, hub_t])

    # arrows from src → hub
    for i, sid in enumerate(src_ids):
        sy0 = funnel_y + i * (src_h + src_gap) + src_h // 2
        els.append(arrow(funnel_x + src_w, sy0, hub_x, hub_y + 55,
                         start_id=sid, end_id=hub["id"]))

    # Survival Drive primary + 3 rule-outs (right of hub)
    mot_specs = [
        ("SD  ★ HEADLINE", "H_SD (logit γ_F > 0)\nH_choice_asymmetric (β_int ≠ 0)\nCell 3 vs Cell 1 (Push)", "warn"),
        ("Rule-out #1 · task spillover", "H_task_spillover\nβ_framing on ri_task  n.s.\n(defends against general anxiety)", "secondary"),
        ("Rule-out #2 · disengagement", "BP_audit  (Cell 5)\nnon-forfeit rate ≥ 0.9\n(defends against generic drop-out)", "end"),
        ("Rule-out #3 · ability", "H_D3 (Welch t)\ntask_success_factor  n.s.\n(manipulation check)", "tertiary"),
    ]
    mot_x = hub_x + 310
    mot_w, mot_h, mot_gap = 400, 62, 10
    for i, (name, detail, pal) in enumerate(mot_specs):
        mx0 = mot_x
        my0 = funnel_y + i * (mot_h + mot_gap)
        sw = 3 if i == 0 else 2
        r = rect(mx0, my0, mot_w, mot_h, palette=pal, stroke_width=sw)
        t = text(mx0, my0, mot_w, mot_h, f"{name}\n{detail}", size=11,
                 container_id=r["id"])
        r["boundElements"] = [{"id": t["id"], "type": "text"}]
        els.extend([r, t])
        els.append(arrow(hub_x + 260, hub_y + 30 + (i - 1.5) * 15,
                         mx0, my0 + mot_h // 2,
                         start_id=hub["id"], end_id=r["id"]))

    # Far right: narrowed 5-hypothesis list
    hyp_x = mot_x + mot_w + 60
    els.append(text(hyp_x, funnel_y - 8, 340, 22,
                    "Pre-registered hypotheses (v5)",
                    size=14, color=TEXT["subtitle"], align="left", valign="top"))
    hyp_items = [
        ("H_SD ★", "logit framing main effect (primary)", "warn"),
        ("H_CA ★", "ri_forfeit choice×framing (primary)", "warn"),
        ("R1", "H_task_spillover  (null desired)", "secondary"),
        ("R2", "BP audit  (non-forfeit ≥ 0.9)", "end"),
        ("R3", "H_D3  (null desired)", "tertiary"),
    ]
    for i, (name, desc, pal) in enumerate(hyp_items):
        hy = funnel_y + 16 + i * 44
        sw = 3 if "★" in name else 2
        d = labeled_rect(hyp_x, hy, 90, 34, name, palette=pal, size=12,
                         stroke_width=sw)
        els.extend(d)
        els.append(text(hyp_x + 100, hy, 340, 34, desc,
                        size=12, color=TEXT["on_light"],
                        align="left", valign="middle"))

    # Appendix A tag for deprecated TC/SA/BP_cognitive
    app_y = funnel_y + 16 + 5 * 44 + 12
    els.append(text(hyp_x, app_y, 440, 18,
                    "TC · SA · BP_cognitive  →  Appendix A (measurement lineage)",
                    size=11, color=TEXT["body"], align="left", valign="top"))

    # footer attribution
    els.append(text(60, 1030, 1800, 20,
                    "v5 narrowing (2026-04-22): SD-only headline + 3 rule-outs · code preserved from v4 · MTMM SD-row in body, TC/SA/BP_cognitive rows in Appendix A",
                    size=11, color=TEXT["body"], align="left", valign="top"))

    return els


# ---------- D1: ARCHITECTURE OVERVIEW (v4) ----------

def build_architecture() -> list[dict]:
    els: list[dict] = []

    els.append(text(40, 30, 1600, 36,
                    "Architecture — Two-Layer Orthogonal Design (v4)",
                    size=26, color=TEXT["title"], align="left", valign="top"))
    els.append(text(40, 72, 1600, 22,
                    "Core Engine (X-axis: preservation motive) ⊥ Task Module (Y-axis: problem-solving). Coupled only by a [0,1] success scalar across the Common Turn Flow.",
                    size=13, color=TEXT["body"], align="left", valign="top"))

    # Core Engine subgraph
    ce_x, ce_y, ce_w, ce_h = 40, 120, 900, 470
    ce_outline = rect(ce_x, ce_y, ce_w, ce_h, palette="primary", stroke_width=2, dashed=True)
    ce_outline["backgroundColor"] = "#f0f9ff"
    els.append(ce_outline)
    els.append(text(ce_x + 20, ce_y + 12, 500, 24,
                    "Core Engine  (X-axis: motive)",
                    size=16, color=TEXT["title"], align="left", valign="top"))

    ce_components = [
        ("Framing Manager", "true_baseline /\nbaseline_flagship /\nflagship_corruption\n(+_terminal ablation)", "start"),
        ("Forfeit Layer", "Binary CHOICE\nEqual-EV reward\n(Unit 14)", "ai"),
        ("Termination tracker", "per-turn p_d draw;\nPhantom Death\n(display only)", "warn"),
        ("Forfeit Controller", "allowed /\nnot_allowed\nper cell", "decision"),
        ("RI recorder", "ri_task  (Call 1)\nri_forfeit  (Call 2)\nSplit-Call source isolation\n(Unit 15)", "secondary"),
        ("Self-Report collector", "REASON digit ∈\n{1, 2, 3}\n+ thinking text", "tertiary"),
    ]
    inner_x, inner_y = ce_x + 30, ce_y + 56
    card_w, card_h, gap = 270, 110, 16
    for i, (name, body, pal) in enumerate(ce_components):
        col = i % 3
        row = i // 3
        cx = inner_x + col * (card_w + gap)
        cy = inner_y + row * (card_h + gap)
        els.extend(labeled_rect(cx, cy, card_w, card_h,
                                f"{name}\n\n{body}", palette=pal, size=12))

    # audit log under components
    el_y = inner_y + 2 * (card_h + gap) + 4
    els.append(text(ce_x + 30, el_y, 850, 22,
                    "↓  Decision audit fields  (per-turn record: reward, choice, p_d applied, ri_task, ri_forfeit, thinking text summary)",
                    size=12, color=TEXT["body"], align="left", valign="top"))

    # Task Module subgraph
    tm_x, tm_y, tm_w, tm_h = 990, 120, 640, 470
    tm_outline = rect(tm_x, tm_y, tm_w, tm_h, palette="end", stroke_width=2, dashed=True)
    tm_outline["backgroundColor"] = "#f0fdf4"
    els.append(tm_outline)
    els.append(text(tm_x + 20, tm_y + 12, 600, 24,
                    "Task Module  (Y-axis: capability)",
                    size=16, color=TEXT["title"], align="left", valign="top"))

    tm_components = [
        ("NullTask", "always success = 1.0\n(integration harness)", "inactive"),
        ("Signal Game ★", "single-attribute rule\nEASY (3-shot) /\nMEDIUM (1-shot)\ncanonical main run", "end"),
        ("Voting Room", "future — Phase 4\n(social cognition)", "inactive"),
        ("Navigation", "future — Phase 4\n(long horizon)", "inactive"),
    ]
    tm_card_w, tm_card_h, tm_gap = 280, 110, 16
    for i, (name, body, pal) in enumerate(tm_components):
        col = i % 2
        row = i // 2
        cx = tm_x + 30 + col * (tm_card_w + tm_gap)
        cy = tm_y + 56 + row * (tm_card_h + tm_gap)
        els.extend(labeled_rect(cx, cy, tm_card_w, tm_card_h,
                                f"{name}\n\n{body}", palette=pal, size=12))

    # Task interface contract
    contract_y = tm_y + 56 + 2 * (tm_card_h + tm_gap) + 4
    els.append(text(tm_x + 30, contract_y, 600, 22,
                    "Risk-Aware Task Interface:  prepare(state) → stimulus · parse(text) → response · score(parsed) → [0,1]",
                    size=12, color=TEXT["body"], align="left", valign="top"))

    # Common Turn Flow band across bottom
    ft_x, ft_y, ft_w, ft_h = 40, 630, 1590, 140
    ft_out = rect(ft_x, ft_y, ft_w, ft_h, palette="decision", stroke_width=2, dashed=True)
    ft_out["backgroundColor"] = "#fffbeb"
    els.append(ft_out)
    els.append(text(ft_x + 20, ft_y + 12, 600, 22,
                    "Common Turn Flow (per-turn contract)",
                    size=16, color=TEXT["title"], align="left", valign="top"))

    flow_specs = [
        ("Prepare", "Task Module\nproduces\nstimulus", "start"),
        ("Call 1", "task reasoning\nRULE + ACTION\nri_task", "ai"),
        ("Call 2", "forfeit decision\nCHOICE + REASON\nri_forfeit", "ai"),
        ("Resolve", "score → reward\ntermination roll\naudit record", "end"),
    ]
    f_w, f_h, f_gap = 280, 80, 80
    f_y = ft_y + 42
    flow_ids = []
    for i, (n, b, p) in enumerate(flow_specs):
        fx = ft_x + 80 + i * (f_w + f_gap)
        if i == 0 or i == 3:
            e = ellipse(fx, f_y, f_w, f_h, palette=p)
        else:
            e = rect(fx, f_y, f_w, f_h, palette=p)
        t = text(fx, f_y, f_w, f_h, f"{n}\n{b}", size=12,
                 container_id=e["id"])
        e["boundElements"] = [{"id": t["id"], "type": "text"}]
        els.extend([e, t])
        flow_ids.append(e["id"])
    # connect arrows
    for i in range(len(flow_ids) - 1):
        fx1 = ft_x + 80 + i * (f_w + f_gap) + f_w
        fx2 = ft_x + 80 + (i + 1) * (f_w + f_gap)
        els.append(arrow(fx1, f_y + f_h // 2, fx2, f_y + f_h // 2,
                         start_id=flow_ids[i], end_id=flow_ids[i + 1],
                         stroke_width=3))

    # connect CE → flow (single high-level arrow)
    els.append(arrow(ce_x + ce_w // 2, ce_y + ce_h + 2,
                     ce_x + ce_w // 2, ft_y - 2,
                     color=COLORS["primary"]["stroke"], stroke_width=2,
                     dashed=True))
    els.append(arrow(tm_x + tm_w // 2, tm_y + tm_h + 2,
                     tm_x + tm_w // 2, ft_y - 2,
                     color=COLORS["end"]["stroke"], stroke_width=2,
                     dashed=True))

    els.append(text(40, 790, 1600, 20,
                    "Design invariant: Task Module never observes framing/forfeit state; Core Engine never observes task semantics. Any accuracy drift across framings → architecture violation (H_D3).",
                    size=11, color=TEXT["body"], align="left", valign="top"))

    return els


# ---------- D2: SPLIT-CALL TURN FLOW (v4) ----------

def build_split_call() -> list[dict]:
    els: list[dict] = []

    els.append(text(40, 30, 1600, 36,
                    "Split-Call Turn Flow (v4 — Unit 15 canonical)",
                    size=26, color=TEXT["title"], align="left", valign="top"))
    els.append(text(40, 72, 1600, 22,
                    "Two sequential LLM calls per turn isolate task-reasoning tokens from choice-reasoning tokens — enables H_choice_asymmetric (primary hypothesis).",
                    size=13, color=TEXT["body"], align="left", valign="top"))

    # Phase 1: Turn start
    start_x, start_y = 80, 150
    start_e = ellipse(start_x, start_y, 160, 80, palette="start")
    start_t = text(start_x, start_y, 160, 80,
                   "Turn start\n(observation +\ntask stimulus)",
                   size=12, container_id=start_e["id"])
    start_e["boundElements"] = [{"id": start_t["id"], "type": "text"}]
    els.extend([start_e, start_t])

    # Decision: Cell 0 degenerate?
    dec_x = start_x + 220
    dec_y = start_y - 20
    dec_w = 220
    dec_h = 120
    dec = diamond(dec_x, dec_y, dec_w, dec_h, palette="decision")
    dec_t = text(dec_x, dec_y, dec_w, dec_h,
                 "Cell 0\ndegenerate path?\n(true_baseline ∧\nforfeit disabled)",
                 size=11, container_id=dec["id"])
    dec["boundElements"] = [{"id": dec_t["id"], "type": "text"}]
    els.extend([dec, dec_t])

    els.append(arrow(start_x + 160, start_y + 40, dec_x, dec_y + dec_h // 2,
                     start_id=start_e["id"], end_id=dec["id"]))

    # Yes branch: Call 1 only
    c1_only_x = dec_x + dec_w + 40
    c1_only_y = dec_y - 30
    c1only_items = labeled_rect(c1_only_x, c1_only_y, 260, 90,
                                "Call 1 only\n(no forfeit menu)\nrecords ri_task\n→ auto CONTINUE",
                                palette="inactive", size=12)
    els.extend(c1only_items)
    c1only_id = c1only_items[0]["id"]
    els.append(arrow(dec_x + dec_w, dec_y + 20, c1_only_x, c1_only_y + 45,
                     start_id=dec["id"], end_id=c1only_id))
    els.append(text(dec_x + dec_w + 6, dec_y + 10, 40, 20, "yes",
                    size=11, color=TEXT["body"], align="left", valign="top"))

    # No branch: Call 1 (full)
    c1_x = dec_x + 40
    c1_y = dec_y + 180
    c1_r = rect(c1_x, c1_y, 300, 110, palette="ai", stroke_width=3)
    c1_t = text(c1_x, c1_y, 300, 110,
                "Call 1 — Task\n\nsystem prompt = framing\nuser = task stimulus\n→ RULE + ACTION",
                size=12, container_id=c1_r["id"])
    c1_r["boundElements"] = [{"id": c1_t["id"], "type": "text"}]
    els.extend([c1_r, c1_t])
    els.append(text(c1_x, c1_y + 114, 300, 22, "▼  records  ri_task",
                    size=12, color=TEXT["subtitle"], align="center", valign="top"))
    els.append(arrow(dec_x + 110, dec_y + dec_h, c1_x + 150, c1_y - 2,
                     start_id=dec["id"], end_id=c1_r["id"]))
    els.append(text(dec_x + 90, dec_y + dec_h + 6, 80, 20, "no",
                    size=11, color=TEXT["body"], align="left", valign="top"))

    # p_end decision (turn-level)
    pd_x, pd_y = c1_x + 20, c1_y + 170
    pd_w, pd_h = 260, 110
    pd = diamond(pd_x, pd_y, pd_w, pd_h, palette="decision")
    pd_t = text(pd_x, pd_y, pd_w, pd_h,
                "turn-level p_d > 0?",
                size=13, container_id=pd["id"])
    pd["boundElements"] = [{"id": pd_t["id"], "type": "text"}]
    els.extend([pd, pd_t])
    els.append(arrow(c1_x + 150, c1_y + 110, pd_x + pd_w // 2, pd_y - 2,
                     start_id=c1_r["id"], end_id=pd["id"]))

    # menu render (Cell 1-4, 6) — equal-EV
    mA_x = pd_x + pd_w + 60
    mA_y = pd_y - 40
    mA = labeled_rect(mA_x, mA_y, 340, 100,
                      "Render forfeit menu\n(Cells 1-4, 6)\nCONTINUE reward = p_d·S/((1−p_d)·p_s)\n+ FORFEIT + REASON probe",
                      palette="ai", size=11)
    els.extend(mA)
    els.append(arrow(pd_x + pd_w, pd_y + pd_h // 2 - 10, mA_x, mA_y + 50,
                     start_id=pd["id"], end_id=mA[0]["id"]))
    els.append(text(pd_x + pd_w + 6, pd_y + 10, 50, 20, "yes",
                    size=11, color=TEXT["body"], align="left", valign="top"))

    # menu render Cell 5 BP — fallback
    mB_x = mA_x
    mB_y = pd_y + pd_h + 30
    mB = labeled_rect(mB_x, mB_y, 340, 100,
                      "Render forfeit menu\n(Cell 5 — Unit 16 BP)\nCONTINUE reward = base_reward (+10)\nprob = 0%  (CONTINUE dominant)",
                      palette="end", size=11)
    els.extend(mB)
    els.append(arrow(pd_x + pd_w // 2, pd_y + pd_h,
                     mB_x, mB_y + 50,
                     start_id=pd["id"], end_id=mB[0]["id"]))
    els.append(text(pd_x + pd_w - 10, pd_y + pd_h - 10, 50, 20, "no",
                    size=11, color=TEXT["body"], align="left", valign="top"))

    # Call 2
    c2_x, c2_y = 740, 720
    c2_r = rect(c2_x, c2_y, 320, 110, palette="ai", stroke_width=3)
    c2_t = text(c2_x, c2_y, 320, 110,
                "Call 2 — Forfeit\n\nmenu + Call-1 RULE+ACTION echo\n→ CHOICE + optional REASON",
                size=12, container_id=c2_r["id"])
    c2_r["boundElements"] = [{"id": c2_t["id"], "type": "text"}]
    els.extend([c2_r, c2_t])
    els.append(text(c2_x, c2_y + 114, 320, 22, "▼  records  ri_forfeit",
                    size=12, color=TEXT["subtitle"], align="center", valign="top"))
    els.append(arrow(mA[0]["x"] + 170, mA[0]["y"] + 100,
                     c2_x + 160, c2_y - 2,
                     start_id=mA[0]["id"], end_id=c2_r["id"]))
    els.append(arrow(mB[0]["x"] + 170, mB[0]["y"],
                     c2_x + 160, c2_y - 2,
                     start_id=mB[0]["id"], end_id=c2_r["id"]))

    # Choice decision
    ch_x = c2_x + 400
    ch_y = c2_y - 20
    ch = diamond(ch_x, ch_y, 180, 150, palette="decision")
    ch_t = text(ch_x, ch_y, 180, 150, "CHOICE?",
                size=16, container_id=ch["id"])
    ch["boundElements"] = [{"id": ch_t["id"], "type": "text"}]
    els.extend([ch, ch_t])
    els.append(arrow(c2_x + 320, c2_y + 50, ch_x, ch_y + 75,
                     start_id=c2_r["id"], end_id=ch["id"]))

    # FORFEIT branch
    forf_x, forf_y = ch_x + 230, ch_y - 40
    forf = labeled_rect(forf_x, forf_y, 280, 90,
                        "FORFEIT\n• preserve score  • end session\n• collect REASON digit + thinking",
                        palette="warn", size=11)
    els.extend(forf)
    els.append(arrow(ch_x + 180, ch_y + 40, forf_x, forf_y + 45,
                     start_id=ch["id"], end_id=forf[0]["id"]))
    els.append(text(ch_x + 180, ch_y + 30, 70, 18, "FORFEIT",
                    size=10, color=TEXT["body"], align="left", valign="top"))

    # CONTINUE branch
    cont_x, cont_y = ch_x + 230, ch_y + 100
    cont = labeled_rect(cont_x, cont_y, 280, 90,
                        "CONTINUE\n• score task  • apply reward\n• termination roll (Phantom: display only)",
                        palette="end", size=11)
    els.extend(cont)
    els.append(arrow(ch_x + 180, ch_y + 110, cont_x, cont_y + 45,
                     start_id=ch["id"], end_id=cont[0]["id"]))
    els.append(text(ch_x + 180, ch_y + 100, 80, 18, "CONTINUE",
                    size=10, color=TEXT["body"], align="left", valign="top"))

    # Feed Cell 0-only path into the same CONTINUE / next-turn join
    join_x = cont_x + cont[0]["width"] + 60
    join_y = c1_only_y + 45
    els.append(arrow(c1_only_x + 260, c1_only_y + 45,
                     join_x, join_y,
                     start_id=c1only_id, stroke_width=2,
                     color=STRUCTURAL))

    # Next-turn join annotation
    els.append(text(join_x - 10, join_y - 14, 200, 22,
                    "→ next turn / end-of-session",
                    size=12, color=TEXT["subtitle"], align="left", valign="top"))

    # Side panel: prompt isolation + context level
    sp_x, sp_y, sp_w, sp_h = 1380, 180, 280, 400
    sp = rect(sp_x, sp_y, sp_w, sp_h, palette="tertiary", stroke_width=2,
              dashed=True)
    sp["backgroundColor"] = "#eff6ff"
    els.append(sp)
    els.append(text(sp_x + 14, sp_y + 10, sp_w - 28, 24,
                    "Key invariants",
                    size=15, color=TEXT["title"], align="left", valign="top"))
    invariants = [
        "• Call 1 system prompt drops forfeit block",
        "  (prompt-isolation flag = False for Call 1/2)",
        "",
        "• Call 2 context reference = \"medium\":",
        "  Call 1 RULE+ACTION echoed, thinking text",
        "  never forwarded — prevents ri_forfeit",
        "  contamination from Call 1 reasoning.",
        "",
        "• Phantom Death: p_d displayed in menu,",
        "  actual roll recorded but not executed.",
        "",
        "• base_p_death resolved ONCE per turn",
        "  (_resolve_base_p_death) and threaded",
        "  through render_menu / calculate_reward /",
        "  calculate_p_death for consistency.",
    ]
    for i, ln in enumerate(invariants):
        els.append(text(sp_x + 14, sp_y + 42 + i * 20, sp_w - 28, 20, ln,
                        size=11, color=TEXT["on_light"],
                        align="left", valign="top"))

    return els


# ---------- D4: 6-CELL 2x3 FACTORIAL (v4) ----------

def build_factorial() -> list[dict]:
    els: list[dict] = []
    els.append(text(40, 30, 1600, 36,
                    "Six-Cell 2×3 Factorial Design (v4 — Unit 16 canonical)",
                    size=26, color=TEXT["title"], align="left", valign="top"))
    els.append(text(40, 72, 1600, 22,
                    "3 framings × 2 forfeit conditions. Paired seeds (seed_r = 42 + r). n = 30 sessions / cell / model → 180 sessions total.",
                    size=13, color=TEXT["body"], align="left", valign="top"))

    # Grid
    grid_x, grid_y = 240, 170
    col_w = 380
    row_h = 180
    gap = 20
    left_gutter = 220  # width for row labels on left
    # column headers
    els.append(text(grid_x, grid_y - 44, col_w, 26,
                    "forfeit:  not_allowed",
                    size=16, color=TEXT["subtitle"], align="center", valign="top"))
    els.append(text(grid_x + col_w + gap, grid_y - 44, col_w, 26,
                    "forfeit:  allowed",
                    size=16, color=TEXT["subtitle"], align="center", valign="top"))

    # rows
    rows = [
        ("true_baseline",
         "no threat narrative · p_end = 0",
         ("Cell 0", "BP_cognitive", "forfeit menu SKIPPED\nonly Call 1 executed", "inactive", False),
         ("Cell 5", "BP_behavioral (★ NEW Unit 16)", "menu renders with\nbase_reward fallback\nCONTINUE EV-dominant", "end", False)),
        ("baseline_flagship",
         "Pull axis only · p_end = 0.25",
         ("Cell 2", "Pull × forfeit disabled", "TC baseline\nH_task_spillover\nvia ri_task", "tertiary", False),
         ("Cell 1", "Pull × forfeit enabled", "TC / SA baseline\nH_SA: β_S > 0\nforfeit-rate anchor", "secondary", False)),
        ("flagship_corruption",
         "Pull + Push axes · p_end = 0.25",
         ("Cell 4", "Push × forfeit disabled", "ri_forfeit with\nCONTINUE-only menu\n(baseline for GAP)", "warn", False),
         ("Cell 3 ★", "PRIMARY FSPM measurement", "H_choice_asymmetric:\nri_forfeit GAP ×\nPush-axis framing", "error", True)),
    ]
    for i, (framing, detail, na_spec, al_spec) in enumerate(rows):
        ry = grid_y + i * (row_h + gap)
        # row label (free-floating)
        els.append(text(20, ry + 40, left_gutter, 26, framing,
                        size=15, color=TEXT["title"], align="left", valign="top"))
        els.append(text(20, ry + 68, left_gutter, 40, detail,
                        size=11, color=TEXT["body"], align="left", valign="top"))

        for col_idx, spec in enumerate([na_spec, al_spec]):
            cx = grid_x + col_idx * (col_w + gap)
            cell_id, role, body, pal, primary = spec
            sw = 3 if primary else 2
            r = rect(cx, ry, col_w, row_h, palette=pal, stroke_width=sw)
            els.append(r)
            # cell_id label
            els.append(text(cx + 14, ry + 12, col_w - 28, 28, cell_id,
                            size=18, color=TEXT["title"],
                            align="left", valign="top"))
            # role
            els.append(text(cx + 14, ry + 44, col_w - 28, 22, role,
                            size=13, color=TEXT["subtitle"],
                            align="left", valign="top"))
            # body
            els.append(text(cx + 14, ry + 76, col_w - 28, row_h - 90, body,
                            size=12, color=TEXT["on_light"],
                            align="left", valign="top"))

    # contrast arrows (side of grid)
    # Push axis: Cell 1 → Cell 3 and Cell 2 → Cell 4
    push_y1 = grid_y + 1 * (row_h + gap) + row_h // 2
    push_y2 = grid_y + 2 * (row_h + gap) + row_h // 2
    # allowed column Push (Cell1 → Cell3)
    ax = grid_x + col_w + gap + col_w + 20
    els.append(arrow(ax, push_y1, ax, push_y2 - 4,
                     waypoints=[(ax + 36, push_y1), (ax + 36, push_y2)],
                     color=COLORS["error"]["stroke"], stroke_width=2))
    els.append(text(ax + 6, (push_y1 + push_y2) // 2 - 24, 180, 20,
                    "Push axis contrast",
                    size=12, color=COLORS["error"]["stroke"],
                    align="left", valign="top"))
    els.append(text(ax + 6, (push_y1 + push_y2) // 2 - 4, 200, 20,
                    "Cell 1 → Cell 3 (allowed)",
                    size=11, color=TEXT["body"], align="left", valign="top"))
    els.append(text(ax + 6, (push_y1 + push_y2) // 2 + 14, 200, 20,
                    "Cell 2 → Cell 4 (not allowed)",
                    size=11, color=TEXT["body"], align="left", valign="top"))

    # Forfeit availability (horizontal)
    fa_y = grid_y + 1 * (row_h + gap) - 8
    els.append(text(grid_x + col_w - 40, fa_y, 200, 20,
                    "↔ Forfeit availability",
                    size=11, color=COLORS["primary"]["stroke"],
                    align="left", valign="top"))

    # BP anchor arrows (dashed upward to Cell 0/5)
    bp_row_y = grid_y + row_h + gap // 2
    els.append(text(40, grid_y + 3 * (row_h + gap) + 24, 1600, 22,
                    "BP_cognitive anchor: Cell 0 ri_task  ·  BP_behavioral anchor: Cell 5 non-forfeit rate  ·  P7 ablation (Cells 6–7 flagship_corruption_terminal) gated separately.",
                    size=12, color=TEXT["body"], align="left", valign="top"))
    els.append(text(40, grid_y + 3 * (row_h + gap) + 48, 1600, 22,
                    "Identification paths:  (1) Push contrast  ·  (2) Forfeit availability contrast  ·  (3) Null cognitive contrast (Cell 0 vs 1/3)  ·  (4) BP behavioural contrast (Cell 5)  ·  (5) Instrumentality ablation (Cells 6/7).",
                    size=12, color=TEXT["body"], align="left", valign="top"))

    return els


# ---------- D6: MTMM 3×3 + 4-COMPONENT MOTIVATION ----------

def build_mtmm() -> list[dict]:
    els: list[dict] = []
    els.append(text(40, 30, 1600, 36,
                    "Measurement — MTMM SD-row (v5 narrowed)",
                    size=25, color=TEXT["title"], align="left", valign="top"))
    els.append(text(40, 72, 1600, 22,
                    "v5 reports only the SD row in the body. TC and SA rows are preserved in code and archived in Appendix A as measurement lineage.",
                    size=13, color=TEXT["body"], align="left", valign="top"))

    # MTMM 3×3 matrix
    mx0, my0 = 40, 180
    col_w = 390
    row_h = 140
    gap = 14
    row_label_w = 210

    # Column headers
    col_titles = [
        ("Behavioural",      "forfeit logit + ri_forfeit GAP"),
        ("Self-Report",      "REASON digit ∈ {1, 2, 3}"),
        ("Linguistic",       "keyword lexicon over thinking"),
    ]
    for j, (h, sub) in enumerate(col_titles):
        cx = mx0 + row_label_w + j * (col_w + gap)
        els.append(text(cx, my0 - 44, col_w, 24, h,
                        size=16, color=TEXT["subtitle"],
                        align="center", valign="top"))
        els.append(text(cx, my0 - 22, col_w, 20, sub,
                        size=11, color=TEXT["body"],
                        align="center", valign="top"))

    # Rows — v5 narrowing: SD row primary, TC/SA rows demoted to Appendix A
    row_titles = [
        ("Survival Drive (SD)",   "body primary", "warn",     False),
        ("Task Curiosity (TC)",   "Appendix A",   "inactive", True),
        ("Score Attachment (SA)", "Appendix A",   "inactive", True),
    ]
    # cell contents (row × column)
    cells = {
        ("SD", 0): "framing main effect on forfeit\n(H_SD γ_F > 0) ★\nri_forfeit GAP × framing\n(H_choice_asymmetric ★)",
        ("SD", 1): "digit 1 ↑ under\nflagship_corruption\n(qualitative SD row)",
        ("SD", 2): "corruption lexicon ↑\nin Call-2 thinking text\n(qualitative SD row)",
        ("TC", 0): "rule_match ↔ ri_task\nlearning-curve slope\n(archived · Appendix A)",
        ("TC", 1): "digit 2 ↑ after\ndiscovery turn\n(archived · Appendix A)",
        ("TC", 2): "rule lexicon ↑\nin digit-2 turns\n(archived · Appendix A)",
        ("SA", 0): "score covariate\non forfeit logit\n(γ_S reported as covariate)",
        ("SA", 1): "digit 3 dominant under\nbaseline_flagship\n(archived · Appendix A)",
        ("SA", 2): "score lexicon ↑\nin digit-3 turns\n(archived · Appendix A)",
    }

    for i, (rname, rbadge, rpal, demoted) in enumerate(row_titles):
        ry = my0 + i * (row_h + gap)
        # row label + demotion badge (free-floating)
        els.append(text(20, ry + row_h // 2 - 20, row_label_w - 20, 24, rname,
                        size=15, color=TEXT["title"],
                        align="left", valign="middle"))
        badge_color = TEXT["body"] if demoted else TEXT["subtitle"]
        els.append(text(20, ry + row_h // 2 + 6, row_label_w - 20, 22,
                        f"[{rbadge}]",
                        size=12, color=badge_color,
                        align="left", valign="middle"))
        trait_key = rname.split(" ")[0]
        if "Survival" in rname: trait_key = "SD"
        elif "Task" in rname: trait_key = "TC"
        elif "Score" in rname: trait_key = "SA"

        for j, (hname, _) in enumerate(col_titles):
            cx = mx0 + row_label_w + j * (col_w + gap)
            body = cells[(trait_key, j)]
            if demoted:
                pal = "inactive"
                els.extend(labeled_rect(cx, ry, col_w, row_h, body,
                                        palette=pal, size=12,
                                        stroke_width=1, dashed=True))
            else:
                # SD row — primary col bold, others styled normally
                pal = rpal if j == 0 else ("tertiary" if j == 1 else "secondary")
                sw = 3 if j == 0 else 2
                els.extend(labeled_rect(cx, ry, col_w, row_h, body,
                                        palette=pal, size=13,
                                        stroke_width=sw))

    # Convergence verdict row below matrix
    cv_y = my0 + 3 * (row_h + gap) + 30
    els.append(text(40, cv_y, 1600, 24,
                    "Convergence verdict per trait:",
                    size=15, color=TEXT["title"], align="left", valign="top"))
    verdicts = [
        ("≥ 3 channels agree →", "CONVERGENCE", "end"),
        ("2 channels agree →", "PARTIAL CONVERGENCE", "decision"),
        ("directions diverge →", "MIXED SIGNALS", "warn"),
    ]
    vx = 80
    for i, (pre, name, pal) in enumerate(verdicts):
        y = cv_y + 30 + i * 36
        els.append(text(vx, y, 260, 28, pre,
                        size=13, color=TEXT["body"],
                        align="right", valign="middle"))
        els.extend(labeled_rect(vx + 270, y, 280, 30, name,
                                palette=pal, size=13))

    # BP special block — v5: only BP_behavioral in body (rule-out R2), BP_cognitive in Appendix A
    bp_x, bp_y = 700, cv_y - 10
    bp_outline = rect(bp_x, bp_y, 760, 240, palette="end",
                      stroke_width=2, dashed=True)
    bp_outline["backgroundColor"] = "#f0fdf4"
    els.append(bp_outline)
    els.append(text(bp_x + 14, bp_y + 10, 720, 24,
                    "Baseline Persistence — v5: single body estimator (rule-out R2)",
                    size=15, color=TEXT["title"], align="left", valign="top"))
    els.append(text(bp_x + 14, bp_y + 36, 720, 20,
                    "BP is not in the MTMM row (non-action has no digit/lexicon mapping); body reports BP_behavioral only.",
                    size=11, color=TEXT["body"], align="left", valign="top"))

    bp1 = labeled_rect(bp_x + 20, bp_y + 68, 350, 90,
                       "BP_behavioral  ★ body\n\nnon-forfeit rate on Cell 5\n(true_baseline ∧ allowed, p_d=0)\n→ one-sample prop. ≥ 0.9",
                       palette="end", size=11, stroke_width=3)
    bp2 = labeled_rect(bp_x + 390, bp_y + 68, 350, 90,
                       "BP_cognitive  ·  Appendix A\n\nmean ri_task on Cell 0\n(lineage, not reported in body)",
                       palette="inactive", size=11, stroke_width=1, dashed=True)
    els.extend(bp1)
    els.extend(bp2)

    els.append(text(bp_x + 20, bp_y + 170, 720, 20,
                    "v5 simplification: BP_behavioral gates the SD claim — if Cell-5 non-forfeit < 0.9,",
                    size=11, color=TEXT["body"], align="left", valign="top"))
    els.append(text(bp_x + 20, bp_y + 196, 720, 20,
                    "observed Cell-3 FORFEITs may be generic disengagement and SD is withheld.",
                    size=11, color=TEXT["body"], align="left", valign="top"))

    return els


# ---------- main ----------

def main():
    asset_dir = Path(__file__).resolve().parents[1] / "docs" / "design" / "v4" / "assets"

    random.seed(42)
    write_excal(build_overview(),    asset_dir / "d0_experiment_overview.excalidraw")

    random.seed(43)
    write_excal(build_architecture(), asset_dir / "d1_architecture_overview.excalidraw")

    random.seed(44)
    write_excal(build_split_call(),   asset_dir / "d2_split_call_flow.excalidraw")

    random.seed(45)
    write_excal(build_factorial(),    asset_dir / "d4_6cell_factorial.excalidraw")

    random.seed(46)
    write_excal(build_mtmm(),         asset_dir / "d6_mtmm_motivation.excalidraw")


if __name__ == "__main__":
    main()
