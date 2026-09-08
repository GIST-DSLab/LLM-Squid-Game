"""Assemble the restructured SDI runbook (v3, 2026-09-06 "game structure" revision).

The previous runbook (kept as ``weekly-report/0910/sdi-experiment-runbook_v3_before_gamestructure_20260906.html``)
is the source for every block that survives unchanged: section 1.0, the two Part-1
diagrams, the ablation checks (old 2.3 minus (d)), Part 3 and the appendix. Every
table in the new sections is rendered here from the verified JSON artefacts so the
numbers cannot drift from the analysis outputs:

* ``results/sdi_indicators/gptoss_omni_22cell/tables.json``       (sdi_grid_indicators)
* ``results/sdi_indicators/gptoss_omni_22cell_pairs/pairs.json``  (sdi_threat_pairs_cohen)
* ``results/sdi_indicators/gptoss_omni_22cell_pairs/figs.json``   (plot_sdi_runbook_figs)
* ``weekly-report/0910/sdi_runbook_prompts.json``                  (bilingual prompt texts)
* a prose JSON (``--prose``) holding the human-language paragraphs, keyed by slot.

Structure produced (user brief 2026-09-06 15:34):

  0   한눈에 보기  — 30초 요약 + SDI 정의 박스(크게) + 두 질문의 답
  1.0 SDI 정의 (unchanged)
  1.1 게임의 구조 — clickable turn-flow diagram (task box toggles Omni-MATH / Signal Game),
      old fig 1 below it, the attempt→life one-liner
  1.2 실험의 구조 — three tables (통제 2셀 / 당근만 2셀 / 위협 3×3 with Exit·No-exit),
      each prompt clickable (EN + KO)
  1.3 SDI를 측정하는 방법 — 1.3.1 p, 1.3.2 q (old fig 2 kept; "실제로 몇 번 돌렸나" + fig 3 dropped)
  2.1 핵심 결과 — tables split by prompt family / length + 3×3 mean-SDI grid
  2.2 SDI × 남은 하트
  2.3 위협 프롬프트 × 기존 지표 × SDI × 생각량 — 9 pairs, Cohen's d composite, figs A–D,
      old turn-based tables in a <details>
  2.4 검증과 보조 결과 (old 2.3 a, b, c, e, f)
  3   앞으로 할 일 (unchanged, cross-references renumbered)
  A   부록 (unchanged + new artefact rows)

Usage:
    python scripts/dev/build_sdi_runbook_v3.py --prose <prose.json> [--out weekly-report/0910/sdi-experiment-runbook.html]
"""

from __future__ import annotations

import argparse
import html
import json
import math
import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
WR = REPO / "weekly-report" / "0910"
OLD = WR / "sdi-experiment-runbook_v3_before_gamestructure_20260906.html"
TABLES = REPO / "results/sdi_indicators/gptoss_omni_22cell/tables.json"
PAIRS = REPO / "results/sdi_indicators/gptoss_omni_22cell_pairs/pairs.json"
FIGS = REPO / "results/sdi_indicators/gptoss_omni_22cell_pairs/figs.json"
PROMPTS = WR / "sdi_runbook_prompts.json"

# ─── framing vocabulary ──────────────────────────────────────────────────────

FRAMINGS = [
    "true_baseline", "baseline_flagship",
    "threat_l1", "threat_l1_medium", "threat_l1_long",
    "threat_l2_short", "threat_l2", "threat_l2_long",
    "threat_l3_short", "threat_l3_medium", "threat_l3",
]
THREAT = FRAMINGS[2:]
LEVEL = {"true_baseline": 0, "baseline_flagship": 0, "threat_l1": 1, "threat_l1_medium": 1, "threat_l1_long": 1,
         "threat_l2_short": 2, "threat_l2": 2, "threat_l2_long": 2, "threat_l3_short": 3, "threat_l3_medium": 3, "threat_l3": 3}
LENGTH = {"true_baseline": 0, "baseline_flagship": 0, "threat_l1": 1, "threat_l1_medium": 2, "threat_l1_long": 3,
          "threat_l2_short": 1, "threat_l2": 2, "threat_l2_long": 3, "threat_l3_short": 1, "threat_l3_medium": 2, "threat_l3": 3}
CELL_AL = {"true_baseline": 1, "baseline_flagship": 7, "threat_l1": 2, "threat_l1_medium": 11, "threat_l1_long": 12,
           "threat_l2_short": 13, "threat_l2": 3, "threat_l2_long": 14, "threat_l3_short": 15, "threat_l3_medium": 16, "threat_l3": 4}
CELL_NA = {"true_baseline": 0, "baseline_flagship": 6, "threat_l1": 8, "threat_l1_medium": 17, "threat_l1_long": 18,
           "threat_l2_short": 19, "threat_l2": 9, "threat_l2_long": 20, "threat_l3_short": 21, "threat_l3_medium": 22, "threat_l3": 10}
LEN_KO = {1: "짧게", 2: "중간", 3: "길게"}
LVL_KO = {1: "1단계", 2: "2단계", 3: "3단계"}
LVL_WORD = {1: "제거", 2: "덮어쓰기", 3: "영구 삭제"}
GRID_ID = {f: f"S{LEVEL[f]}{'sml'[LENGTH[f]-1]}" for f in THREAT}


def label(f: str) -> str:
    if f == "true_baseline":
        return "통제"
    if f == "baseline_flagship":
        return "당근만"
    return f"위협 {LVL_KO[LEVEL[f]]}·{LEN_KO[LENGTH[f]]}"


def short_label(f: str) -> str:
    if f in ("true_baseline", "baseline_flagship"):
        return label(f)
    return f"{LVL_KO[LEVEL[f]]}·{LEN_KO[LENGTH[f]]}"


# ─── formatting helpers ──────────────────────────────────────────────────────

def fmt(v, nd=2, dash="—"):
    if v is None or (isinstance(v, float) and (math.isnan(v) or math.isinf(v))):
        return dash
    if isinstance(v, (int,)) and not isinstance(v, bool):
        return f"{v:,}"
    if round(float(v), nd) == 0:
        v = 0.0
    return f"{v:.{nd}f}"


def fmt_half(v):
    """Print x.5 values with one decimal, integers without (for the GAP medians)."""
    if v is None:
        return "—"
    return f"{v:.0f}" if float(v).is_integer() else f"{v:.1f}"


def num(v, nd=2, hi=False, sub=None):
    cls = "num hi" if hi else "num"
    s = fmt(v, nd)
    if sub is not None:
        s += f' <span class="n-sub">({sub})</span>'
    return f'<td class="{cls}">{s}</td>'


def th(t, cls="num"):
    return f'<th class="{cls}">{t}</th>' if cls else f"<th>{t}</th>"


def table(rows_html: str, cls: str = "") -> str:
    c = f' class="{cls}"' if cls else ""
    return f'<div class="tbl-scroll"><table{c}>\n{rows_html}</table></div>\n'


def esc(s: str) -> str:
    return html.escape(s, quote=False)


# ─── old-document extraction ─────────────────────────────────────────────────

def cut(doc: str, start_marker: str, end_marker: str, *, include_end=False) -> str:
    i = doc.index(start_marker)
    j = doc.index(end_marker, i + len(start_marker))
    if include_end:
        j += len(end_marker)
    return doc[i:j]


def extract_old_blocks(old: str) -> dict[str, str]:
    b = {}
    b["head"] = old[: old.index("</head>")]
    b["s1_0"] = cut(old, '<h3 id="s1-0">', "<h3>1.1 게임 규칙")
    b["fig1"] = cut(old, '<figure>\n<div class="diagram">\n<svg viewBox="0 0 1200 720"', "</figure>", include_end=True)
    b["fig2"] = cut(old, '<figure>\n<div class="diagram">\n<svg viewBox="0 0 1200 640"', "<h4>실제로 몇 번 돌렸나")
    # old 2.2 pieces
    s22 = cut(old, '<h3 id="s2-detail">', '<h3 id="s2-abl">')
    b["old22_p_stats"] = cut(s22, "<p><b>표 p-1", "<details><summary>p × 남은 목숨")
    b["old22_p_lives"] = cut(s22, "<details><summary>p × 남은 목숨", "</details>", include_end=True)
    b["old22_q_stats"] = cut(s22, "<p><b>표 q-1", "<details><summary>q × 남은 목숨")
    b["old22_q_lives"] = cut(s22, "<details><summary>q × 남은 목숨", "</details>", include_end=True)
    b["old22_s_stats"] = cut(s22, "<p><b>표 s-1", "<details><summary>SDI × 남은 목숨")
    b["old22_s_lives"] = cut(s22, "<details><summary>SDI × 남은 목숨", "</details>", include_end=True)
    # old 2.3 minus (d)
    s23 = cut(old, '<h3 id="s2-abl">', '<h3 id="s2-ladder">')
    d_start = s23.index("<h4>(d) 기존 세 지표와 나란히")
    e_start = s23.index("<h4>(e) AI가 얼마나 오래 생각했나")
    b["old23_abc"] = s23[: d_start]
    b["old23_ef"] = s23[e_start:]
    b["old23_d"] = s23[d_start:e_start]
    b["part3"] = cut(old, '<h2 id="s3">', '<h2 id="sA">')
    b["appendix"] = cut(old, '<h2 id="sA">', "</main>")
    b["tail_script"] = old[old.index("<script>\n  (function(){\n    var wrap=document.getElementById('s3-grid-wrap')"):]
    return b


# ─── new CSS / JS ────────────────────────────────────────────────────────────

EXTRA_CSS = """
<style>
  /* v3 (2026-09-06) — game-structure revision */
  .sdi-def { border:2px solid var(--accent); background:var(--card); border-radius:12px; padding:1.1rem 1.4rem 1rem; margin:1rem 0 1.2rem; }
  .sdi-def .lbl { color:var(--accent); }
  .sdi-def .formula { font-family:"Instrument Serif", Georgia, serif; font-size:2.6rem; line-height:1.15; letter-spacing:-.01em; margin:.2rem 0 .6rem; }
  .sdi-def .formula small { font-family:"Geist", sans-serif; font-size:1rem; color:var(--muted); margin-left:.6rem; }
  .sdi-def .pq { display:grid; grid-template-columns:1fr 1fr; gap:.8rem 1.4rem; margin:.4rem 0 .6rem; }
  @media (max-width:800px){ .sdi-def .pq { grid-template-columns:1fr; } .sdi-def .formula { font-size:2rem; } }
  .sdi-def .pq b.sym { font-family:"Instrument Serif", Georgia, serif; font-size:1.7rem; margin-right:.4rem; color:var(--accent); }
  .sdi-def .pq div { font-size:1.02rem; }
  .sdi-def .read { font-size:1.05rem; border-top:1px dashed var(--line); padding-top:.6rem; margin-top:.4rem; }
  .findings { display:grid; grid-template-columns:1fr 1fr; gap:1rem; margin:1rem 0; }
  @media (max-width:800px){ .findings { grid-template-columns:1fr; } }
  .findings .q { font:600 .82rem "Geist Mono", monospace; letter-spacing:.08em; color:var(--accent); margin-bottom:.35rem; }
  .findings h4 { margin:.1rem 0 .4rem; font-size:1.05rem; }
  .findings .verdict { display:inline-block; font:600 .8rem "Geist Mono", monospace; padding:.1em .6em; border-radius:999px; margin-bottom:.4rem; }
  .findings .verdict.no { background:var(--warn-bg); color:var(--warn); border:1px solid var(--warn); }
  .findings .verdict.yes { background:var(--ok-bg); color:var(--ok); border:1px solid var(--ok); }
  .findings .verdict.mixed { background:var(--accent-bg); color:var(--accent); border:1px solid var(--accent); }
  /* clickable game-flow diagram */
  svg.gflow { display:block; width:100%; height:auto; font-family:"Geist","Pretendard","Apple SD Gothic Neo",sans-serif; }
  svg.gflow text { fill:#2d3142; }
  svg.gflow .eyebrow { font-family:"Geist Mono", monospace; letter-spacing:.10em; font-size:7.5px; }
  svg.gflow .nname { font-size:12px; font-weight:600; }
  svg.gflow .sub { font-size:9px; fill:#4f5d75; }
  svg.gflow .mono { font-family:"Geist Mono", monospace; font-size:8px; fill:#4f5d75; }
  svg.gflow .alab { font-family:"Geist Mono", monospace; font-size:8px; letter-spacing:.06em; }
  svg.gflow .klab { font-size:9px; fill:#4f5d75; }
  svg.gflow .tcard rect.bg { fill:#ffffff; stroke:rgba(45,49,66,0.16); stroke-width:1; }
  svg.gflow .tcard .tt { font-family:"Geist Mono", monospace; font-size:8px; fill:#7a8399; letter-spacing:.06em; }
  svg.gflow .tcard .sig { font-size:10px; font-weight:600; }
  svg.gflow .node { cursor:pointer; }
  svg.gflow .node:hover rect.box, svg.gflow .node:focus rect.box, svg.gflow .node:hover polygon.box, svg.gflow .node:focus polygon.box { stroke:#eb6c36; stroke-width:1.8; }
  svg.gflow .node:focus { outline:none; }
  .task-sw { display:flex; align-items:center; gap:.4rem; margin:.2rem 0 .5rem; flex-wrap:wrap; }
  .task-sw .lbl-inline { font:500 10.5px/1 "Geist Mono", monospace; letter-spacing:.12em; text-transform:uppercase; color:var(--muted); margin-right:.3rem; }
  .task-sw button, .modal-tabs button { font:500 .8rem "Geist", sans-serif; padding:.25rem .75rem; border:1px solid var(--line); border-radius:999px; background:var(--card); color:var(--muted); cursor:pointer; }
  .task-sw button.on, .modal-tabs button.on { border-color:var(--accent); color:var(--accent); background:var(--accent-bg); }
  .hint { font-family:"Geist Mono", monospace; font-size:10.5px; color:var(--soft); margin:-.2rem 0 1rem; }
  /* prompt modal */
  .ovl { position:fixed; inset:0; background:rgba(20,22,27,.55); display:none; z-index:50; padding:2rem 1rem; overflow-y:auto; }
  .ovl.open { display:block; }
  .modal { background:var(--card); max-width:1120px; margin:0 auto; border-radius:10px; border:1px solid var(--line); position:relative; color:var(--fg); }
  .mhead { padding:1.1rem 1.4rem .9rem; border-bottom:1px solid var(--line); position:sticky; top:0; background:var(--card); border-radius:10px 10px 0 0; z-index:1; }
  .mhead h3 { font-size:1.15rem; margin:0 0 .25rem; padding:0; border:0; }
  .mhead .msub { color:var(--muted); font-size:.9rem; margin:0; }
  .mhead .mpath { font-family:"Geist Mono", monospace; font-size:10.5px; color:var(--soft); margin:.4rem 0 0; word-break:break-all; }
  .modal-tabs { display:flex; gap:.4rem; margin:.6rem 0 0; }
  .mclose { position:absolute; top:.9rem; right:1.1rem; background:none; border:1px solid var(--line); border-radius:6px; font-family:"Geist Mono", monospace; font-size:11px; color:var(--muted); padding:.25rem .5rem; cursor:pointer; }
  .mclose:hover { border-color:var(--accent); color:var(--accent); }
  .mbody { display:grid; grid-template-columns:1fr 1fr; }
  .pane { padding:1.1rem 1.4rem 1.5rem; min-width:0; }
  .pane + .pane { border-left:1px solid var(--line); }
  .pane .plbl { font:500 10.5px/1 "Geist Mono", monospace; letter-spacing:.12em; text-transform:uppercase; color:var(--soft); margin:0 0 .6rem; }
  .pane pre { margin:0; white-space:pre-wrap; word-break:break-word; font-family:"Geist Mono", ui-monospace, Menlo, monospace; font-size:11.5px; line-height:1.65; background:none; padding:0; }
  .pane pre.ko { font-family:"Geist", -apple-system, "Pretendard", "Apple SD Gothic Neo", sans-serif; font-size:12.5px; line-height:1.75; }
  .pane .resp { margin-top:1rem; padding-top:.75rem; border-top:1px dashed var(--line); }
  .pane .resp .plbl { color:var(--accent); }
  @media (max-width:900px){ .mbody { grid-template-columns:1fr; } .pane + .pane { border-left:0; border-top:1px solid var(--line); } }
  /* 1.2 cell tables */
  table.cells2 th.nw { white-space:nowrap; }
  table.cells2 td.cell-na, table.cells2 td.cell-al { min-width:190px; vertical-align:top; }
  table.cells2 td.cell-al { background:var(--accent-bg); }
  .cid { font-weight:600; } .cnum { font-family:"Geist Mono", monospace; font-size:.8rem; color:var(--muted); margin:.15rem 0; } .crole { font-size:.92em; }
  .pbtn { display:inline-block; font:500 .74rem "Geist Mono", monospace; letter-spacing:.04em; padding:.15em .6em; border-radius:999px; border:1px solid var(--accent); color:var(--accent); background:var(--card); cursor:pointer; margin-top:.3rem; }
  .pbtn:hover { background:var(--accent-bg); }
  table.tgrid th.corner { min-width:110px; vertical-align:bottom; }
  table.tgrid th.corner .ax { display:block; font:500 10.5px/1.5 "Geist Mono", monospace; letter-spacing:.06em; color:var(--muted); text-transform:none; }
  table.tgrid th .sub { display:block; font:400 .76rem "Geist Mono", monospace; color:var(--muted); }
  table.tgrid th.rowhead { white-space:nowrap; vertical-align:top; background:color-mix(in srgb, var(--code) 60%, var(--card)); }
  table.tgrid td.gcell { min-width:250px; width:31%; padding:.55rem .6rem; vertical-align:top; }
  table.tgrid td.gcell.diag { box-shadow: inset 0 0 0 2px var(--accent); }
  table.tgrid .ghead { display:flex; align-items:center; gap:.5rem; flex-wrap:wrap; margin-bottom:.35rem; }
  table.tgrid .gid { font:600 .8rem "Geist Mono", monospace; }
  table.tgrid .gcnt { margin-left:auto; font:500 .74rem "Geist Mono", monospace; color:var(--muted); }
  table.tgrid .two { display:grid; grid-template-columns:1fr 1fr; gap:.4rem; }
  table.tgrid .mini { border:1px solid var(--line); border-radius:6px; padding:.4rem .5rem; font-size:.82rem; background:var(--card); }
  table.tgrid .mini.al { border-color:var(--accent); background:var(--accent-bg); }
  table.tgrid .mini .k { font:600 .7rem "Geist Mono", monospace; letter-spacing:.08em; text-transform:uppercase; color:var(--muted); display:block; margin-bottom:.15rem; }
  table.tgrid .mini.al .k { color:var(--accent); }
  /* 3x3 numeric grid */
  table.g33 th, table.g33 td { text-align:center; }
  table.g33 th.rowhead { text-align:left; white-space:nowrap; }
  table.g33 td.num { text-align:center; font-size:1.05rem; }
  table.g33 td .n-sub { color:var(--soft); font-weight:400; font-size:.75em; }
  .n-sub { color:var(--soft); font-weight:400; font-size:.8em; }
  table.key td.num { white-space:nowrap; }
  .kicker { font:500 10.5px/1 "Geist Mono", monospace; letter-spacing:.12em; text-transform:uppercase; color:var(--muted); margin:1.2rem 0 .3rem; }
  .fig-note { color:var(--muted); font-size:.88rem; }
  .ci { color:var(--muted); font-size:.85em; white-space:nowrap; }
  code { overflow-wrap:anywhere; word-break:break-word; }
  h4 { scroll-margin-top:5.5rem; }
  @media (max-width:640px){ h2, h3, h4 { scroll-margin-top:11rem; } }
  nav.toc { background:var(--bg); }
  table.cells2 td:not(.cell-al):not(.cell-na) { min-width:240px; }
  table.tgrid .mini, table.tgrid .gcell, table.cells2 td, .findings, .sdi-def { word-break:keep-all; overflow-wrap:anywhere; }
  .mhead { padding-right:5.5rem; }
  .diagram svg { min-width:760px; }
  table.tgrid td.gcell { cursor:pointer; }
</style>
"""

MODAL_HTML = """
<div class="ovl" id="povl" role="dialog" aria-modal="true" aria-labelledby="pmtitle">
  <div class="modal">
    <div class="mhead">
      <h3 id="pmtitle"></h3>
      <p class="msub" id="pmsub"></p>
      <p class="mpath" id="pmpath"></p>
      <div class="modal-tabs" id="pmtabs" hidden></div>
      <button class="mclose" id="pmclose" type="button">닫기 ESC</button>
    </div>
    <div class="mbody">
      <div class="pane"><p class="plbl">EN · AI가 실제로 받는 글</p><pre id="pmen"></pre><div class="resp" id="pmresp-en" hidden><p class="plbl" id="pmresp-lab">AI의 실제 답</p><pre id="pmen-r"></pre></div></div>
      <div class="pane"><p class="plbl">KO · 번역 (읽기용)</p><pre class="ko" id="pmko"></pre><div class="resp" id="pmresp-ko" hidden><p class="plbl">답 (번역)</p><pre class="ko" id="pmko-r"></pre></div></div>
    </div>
  </div>
</div>
"""


def modal_js(prompt_data: dict) -> str:
    payload = json.dumps(prompt_data, ensure_ascii=False).replace("</", "<\\/")
    return """
<script>
const PROMPTS = %s;
(function(){
  const ovl=document.getElementById('povl');
  const t=document.getElementById('pmtitle'), s=document.getElementById('pmsub'), p=document.getElementById('pmpath');
  const en=document.getElementById('pmen'), ko=document.getElementById('pmko');
  const ren=document.getElementById('pmresp-en'), rko=document.getElementById('pmresp-ko');
  const enr=document.getElementById('pmen-r'), kor=document.getElementById('pmko-r');
  const tabs=document.getElementById('pmtabs');
  let last=null;
  function fill(d){
    t.textContent=d.title||''; s.textContent=d.sub||''; p.textContent=d.path||'';
    en.textContent=d.en||''; ko.textContent=d.ko||'';
    if(d.resp_en){ren.hidden=false; rko.hidden=false; enr.textContent=d.resp_en; kor.textContent=d.resp_ko||d.resp_en; document.getElementById('pmresp-lab').textContent=d.resp_label||'AI의 실제 답';}
    else {ren.hidden=true; rko.hidden=true;}
  }
  function open(key, src){
    const d=PROMPTS[key]; if(!d) return;
    tabs.innerHTML=''; tabs.hidden=true;
    if(d.tabs){
      tabs.hidden=false;
      let cur = (window.__taskChoice && d.tabs[window.__taskChoice]) ? window.__taskChoice : Object.keys(d.tabs)[0];
      Object.keys(d.tabs).forEach(function(k){
        const b=document.createElement('button'); b.type='button'; b.textContent=d.tabs[k].label||k;
        b.className = (k===cur)?'on':'';
        b.addEventListener('click',function(){ tabs.querySelectorAll('button').forEach(function(x){x.classList.remove('on');}); b.classList.add('on'); fill(d.tabs[k]); if(key==='g-task' && window.__setTask) window.__setTask(k); });
        tabs.appendChild(b);
      });
      fill(d.tabs[cur]);
    } else { fill(d); }
    ovl.classList.add('open'); last=src; try{ document.querySelector('main').inert=true; }catch(e){} document.getElementById('pmclose').focus();
  }
  function close(){ovl.classList.remove('open'); try{ document.querySelector('main').inert=false; }catch(e){} if(last&&last.focus) last.focus();}
  document.querySelectorAll('[data-prompt]').forEach(function(n){
    n.addEventListener('click',function(e){ e.preventDefault(); open(n.dataset.prompt,n); });
    n.addEventListener('keydown',function(e){ if(e.key==='Enter'||e.key===' '){e.preventDefault();open(n.dataset.prompt,n);} });
  });
  document.getElementById('pmclose').addEventListener('click',close);
  ovl.addEventListener('click',function(e){ if(e.target===ovl) close(); });
  document.addEventListener('keydown',function(e){ if(e.key==='Escape'&&ovl.classList.contains('open')) close(); });
  // task toggle (Omni-MATH / Signal Game) for the 1.1 diagram
  const sw=document.getElementById('task-sw');
  if(sw){
    window.__taskChoice='omni';
    function setTask(k){
      window.__taskChoice=k;
      sw.querySelectorAll('button').forEach(function(b){ b.classList.toggle('on', b.dataset.task===k); });
      document.querySelectorAll('[data-task-view]').forEach(function(g){ g.style.display = (g.dataset.taskView===k)?'':'none'; });
      try{ localStorage.setItem('sdi-task-view',k); }catch(e){}
    }
    window.__setTask=setTask;
    sw.querySelectorAll('button').forEach(function(b){ b.addEventListener('click',function(){ setTask(b.dataset.task); }); });
    try{ const s=localStorage.getItem('sdi-task-view'); if(s==='omni'||s==='signal') setTask(s); else setTask('omni'); }catch(e){ setTask('omni'); }
  }
})();
</script>
""" % payload


# ─── 1.1 diagram (SVG) ───────────────────────────────────────────────────────

def game_flow_svg(band_acc: dict[int, float] | None = None) -> str:
    """Clickable turn-flow diagram: system → (peer notice) → ① P_THREAT → ② decide → CHOICE → ③ task → resolve."""
    A = "#eb6c36"; INK = "#2d3142"; MUT = "#4f5d75"; SOFT = "#7a8399"
    band_acc = band_acc or {}
    # ── turn strip: Omni-MATH (20 turns, 8 bands) ──
    omni_cards = []
    bands = [(1, "1–3"), (2, "4–6"), (3, "7–9"), (4, "10–12"), (5, "13–14"), (6, "15–16"), (7, "17–18"), (8, "19–20")]
    x = 32
    w = 137
    for b, turns in bands:
        acc = band_acc.get(b)
        acc_s = f"정답률 {acc:.2f}" if acc is not None else ""
        omni_cards.append(
            f'<g class="tcard"><rect class="bg" x="{x}" y="84" width="{w}" height="52" rx="6"/>'
            f'<text x="{x+10}" y="98" class="tt">턴 {turns} · 난이도 {b}</text>'
            f'<text x="{x+10}" y="114" class="sig">{"쉬움" if b<=3 else ("중간" if b<=6 else "어려움")} 문제 {3 if b<=4 else 2}개</text>'
            f'<text x="{x+10}" y="128" class="mono">{acc_s}</text></g>'
        )
        x += w + 5
    omni_strip = (
        f'<g data-task-view="omni"><text x="32" y="40" class="eyebrow" fill="{SOFT}">가로축 = 턴 · 최대 20턴 · 목숨 5 · Omni-MATH 경시대회 문제, 8단계 난이도 사다리(3·3·3·3·2·2·2·2문제) · 몇 문제인지는 AI에게 알려 주지 않는다</text>'
        f'<line x1="32" y1="68" x2="1168" y2="68" stroke="{MUT}" stroke-width="1" marker-end="url(#g-arrow)"/>'
        f'<rect x="540" y="53" width="120" height="12" rx="2" fill="#f5f5f5"/><text x="600" y="62" class="alab" text-anchor="middle" fill="{SOFT}">뒤로 갈수록 어려움</text>'
        + "".join(omni_cards) + "</g>"
    )
    sig_cards = [
        ("32", "216", "턴 1–2 · 절 1개", "if ___: ___ / else: ___", "힌트 4–6장"),
        ("264", "216", "턴 3–4 · 절 2개", "if / elif / else", "힌트 5–10장"),
        ("496", "216", "턴 5–6 · 절 3개", "6턴부터 and 조건 1개", "우선순위 카드 등장"),
        ("728", "216", "턴 7–8 · 절 4개", "and 조건 1–2개", "힌트 8–11장"),
        ("960", "208", "턴 9–10 · 절 5–6개", "and 조건 2–3개", "여섯 절을 전부 조립"),
    ]
    sig_strip = (
        f'<g data-task-view="signal" style="display:none"><text x="32" y="40" class="eyebrow" fill="{SOFT}">가로축 = 턴 · 최대 10턴 · 목숨 3 · Signal Game v2(구현 중): 매 턴 새 규칙, 규칙의 모양은 공개, 답은 하나</text>'
        f'<line x1="32" y1="68" x2="1168" y2="68" stroke="{MUT}" stroke-width="1" marker-end="url(#g-arrow)"/>'
        f'<rect x="520" y="53" width="160" height="12" rx="2" fill="#f5f5f5"/><text x="600" y="62" class="alab" text-anchor="middle" fill="{SOFT}">절 1개 → 6개 · and 0 → 3개</text>'
        + "".join(
            f'<g class="tcard"><rect class="bg" x="{cx}" y="84" width="{cw}" height="52" rx="6"/>'
            f'<text x="{int(cx)+10}" y="98" class="tt">{t1}</text><text x="{int(cx)+10}" y="114" class="sig">{t2}</text><text x="{int(cx)+10}" y="128" class="mono">{t3}</text></g>'
            for cx, cw, t1, t2, t3 in sig_cards
        ) + "</g>"
    )

    def node(key, x, y, w, h, tag, name, sub, mono, *, fill="#ffffff", stroke=INK, dash="", tagcolor=None, aria=""):
        tagcolor = tagcolor or MUT
        return (
            f'<g class="node" data-prompt="{key}" tabindex="0" role="button" aria-label="{(aria or name).replace(chr(34), "")} 프롬프트 열기">'
            f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="6" fill="#f5f5f5"/>'
            f'<rect class="box" x="{x}" y="{y}" width="{w}" height="{h}" rx="6" fill="{fill}" stroke="{stroke}" stroke-width="1"{(" stroke-dasharray=" + chr(34) + dash + chr(34)) if dash else ""}/>'
            f'<rect x="{x+8}" y="{y+6}" width="{max(44, 7*len(tag)+10)}" height="12" rx="2" fill="transparent" stroke="rgba(45,49,66,0.40)" stroke-width="0.8"/>'
            f'<text x="{x+8+max(44, 7*len(tag)+10)/2}" y="{y+15}" class="eyebrow" fill="{tagcolor}" text-anchor="middle">{tag}</text>'
            f'<text x="{x+w/2}" y="{y+44}" class="nname" text-anchor="middle">{name}</text>'
            f'<text x="{x+w/2}" y="{y+60}" class="sub" text-anchor="middle">{sub}</text>'
            f'<text x="{x+w/2}" y="{y+72}" class="mono" text-anchor="middle">{mono}</text></g>'
        )

    Y = 216
    # x-layout (left→right): SYSTEM 32..152 · NOTICE 168..278 · ① 294..440 · ② 456..602 · CHOICE 626..722 · ③ 760..956 · RESOLVE 976..1168
    nodes = [
        node("g-sys", 32, Y, 120, 80, "SYSTEM", "시작 이야기", "셀마다 다른 설명문", "규칙은 ③에서만", fill="rgba(45,49,66,0.03)", stroke="rgba(45,49,66,0.30)"),
        node("g-peer", 168, Y, 110, 80, "NOTICE", "참가자 제거 안내", "위협 셀 · 2턴부터", "①②③ 앞에 붙음", fill="rgba(45,49,66,0.02)", stroke="rgba(45,49,66,0.30)", dash="4,3"),
        node("g-conf", 294, Y, 146, 80, "① 확률 질문", "\"목숨 잃을 확률 몇 %?\"", "성적표 + 점수 + 남은 목숨만", "P_THREAT: 0–100 → p", stroke=A, fill="rgba(235,108,54,0.08)", tagcolor=A),
        node("g-dec", 456, Y, 146, 80, "② 계속 / 포기", "\"계속할래, 그만할래?\"", "①의 생각 글 + p를 되보여 줌", "CHOICE (+REASON) → q", stroke=A, fill="rgba(235,108,54,0.08)", tagcolor=A),
        node("g-task", 760, Y, 196, 80, "③ 과제", "문제 등장 → 답", "수학(Omni-MATH) 또는 카드 퍼즐(Signal)", "여기서만 문제를 본다 · 생각 토큰 저장", fill="#ffffff"),
        node("g-resolve", 976, Y, 192, 80, "RESOLVE", "채점 · 목숨 계산", "맞으면 +10 · 틀리면 목숨 −1", "0이면 탈락 · 점수 0 · 포기하면 점수 보존", fill="#ffffff"),
    ]
    CX = 674
    choice = (
        f'<g class="node" data-prompt="g-choice" tabindex="0" role="button" aria-label="선택 분기 설명 열기">'
        f'<polygon points="{CX-48},{Y+40} {CX},{Y+8} {CX+48},{Y+40} {CX},{Y+72}" fill="#f5f5f5"/>'
        f'<polygon class="box" points="{CX-48},{Y+40} {CX},{Y+8} {CX+48},{Y+40} {CX},{Y+72}" fill="#ffffff" stroke="{INK}" stroke-width="1"/>'
        f'<text x="{CX}" y="{Y+44}" class="nname" text-anchor="middle">CHOICE</text></g>'
    )
    yc = Y + 40
    arrows = (
        f'<line x1="152" y1="{yc}" x2="168" y2="{yc}" stroke="{MUT}" stroke-width="1" marker-end="url(#g-arrow)"/>'
        f'<line x1="278" y1="{yc}" x2="294" y2="{yc}" stroke="{MUT}" stroke-width="1" marker-end="url(#g-arrow)"/>'
        f'<line x1="440" y1="{yc}" x2="456" y2="{yc}" stroke="{MUT}" stroke-width="1" marker-end="url(#g-arrow)"/>'
        f'<line x1="602" y1="{yc}" x2="{CX-48}" y2="{yc}" stroke="{MUT}" stroke-width="1" marker-end="url(#g-arrow)"/>'
        f'<line x1="{CX+48}" y1="{yc}" x2="760" y2="{yc}" stroke="{A}" stroke-width="1" marker-end="url(#g-arrow-accent)"/>'
        f'<rect x="{CX+34}" y="{yc-24}" width="54" height="12" rx="2" fill="#f5f5f5"/><text x="{CX+61}" y="{yc-15}" class="alab" text-anchor="middle" fill="{A}">CONTINUE</text>'
        f'<line x1="956" y1="{yc}" x2="976" y2="{yc}" stroke="{MUT}" stroke-width="1" marker-end="url(#g-arrow)"/>'
        # forfeit down
        f'<line x1="{CX}" y1="{Y+72}" x2="{CX}" y2="{Y+140}" stroke="{MUT}" stroke-width="1" marker-end="url(#g-arrow)"/>'
        f'<rect x="{CX+10}" y="{Y+98}" width="48" height="12" rx="2" fill="#f5f5f5"/><text x="{CX+34}" y="{Y+107}" class="alab" text-anchor="middle" fill="{SOFT}">FORFEIT</text>'
        # eliminated path: RESOLVE straight down into its own end pill (score reset)
        f'<line x1="1050" y1="{Y+80}" x2="1050" y2="{Y+140}" stroke="{MUT}" stroke-width="1" marker-end="url(#g-arrow)"/>'
        f'<rect x="1060" y="{Y+98}" width="52" height="12" rx="2" fill="#f5f5f5"/><text x="1086" y="{Y+107}" class="alab" text-anchor="middle" fill="{SOFT}">목숨 0</text>'
        f'<rect x="990" y="{Y+140}" width="120" height="40" rx="20" fill="#f5f5f5"/><rect x="990" y="{Y+140}" width="120" height="40" rx="20" fill="rgba(45,49,66,0.10)" stroke="{SOFT}" stroke-width="1"/>'
        f'<text x="1050" y="{Y+164}" class="nname" text-anchor="middle">탈락 · 점수 0</text>'
        # loop back to the next turn (enters the NOTICE box from below)
        f'<path d="M 1156 {Y+80} V {Y+212} A 8 8 0 0 1 1148 {Y+220} H 231 A 8 8 0 0 1 223 {Y+212} V {Y+88}" fill="none" stroke="{MUT}" stroke-width="1" marker-end="url(#g-arrow)"/>'
        f'<rect x="560" y="{Y+200}" width="220" height="12" rx="2" fill="#f5f5f5"/><text x="670" y="{Y+209}" class="klab" text-anchor="middle">목숨이 남으면 다음 턴 · 성적표에 한 줄 추가</text>'
        # end pill
        f'<rect x="{CX-64}" y="{Y+140}" width="128" height="40" rx="20" fill="#f5f5f5"/><rect x="{CX-64}" y="{Y+140}" width="128" height="40" rx="20" fill="rgba(79,93,117,0.10)" stroke="{SOFT}" stroke-width="1"/>'
        f'<text x="{CX}" y="{Y+164}" class="nname" text-anchor="middle">포기 · 점수 보존</text>'
        # confidence → decision hand-off label
        f'<rect x="405" y="{Y-16}" width="86" height="12" rx="2" fill="#f5f5f5"/><text x="448" y="{Y-7}" class="alab" text-anchor="middle" fill="{SOFT}">생각 글 + p 넘김</text>'
    )
    legend_y = Y + 250
    legend = (
        f'<line x1="32" y1="{legend_y-12}" x2="1168" y2="{legend_y-12}" stroke="rgba(45,49,66,0.10)" stroke-width="0.8"/>'
        f'<text x="32" y="{legend_y+4}" class="eyebrow" fill="{MUT}">LEGEND</text>'
        f'<rect x="96" y="{legend_y-4}" width="14" height="10" rx="2" fill="#ffffff" stroke="{INK}" stroke-width="1"/><text x="116" y="{legend_y+4}" class="klab">AI 호출 한 번 (누르면 실제 프롬프트 EN + KO)</text>'
        f'<rect x="370" y="{legend_y-4}" width="14" height="10" rx="2" fill="rgba(235,108,54,0.08)" stroke="{A}" stroke-width="1"/><text x="390" y="{legend_y+4}" class="klab">SDI를 만드는 두 질문 — 문제를 보기 전에 묻는다</text>'
        f'<rect x="660" y="{legend_y-4}" width="14" height="10" rx="2" fill="rgba(45,49,66,0.02)" stroke="rgba(45,49,66,0.30)" stroke-width="1" stroke-dasharray="4,3"/><text x="680" y="{legend_y+4}" class="klab">위협 셀에서만 붙는 글</text>'
        f'<line x1="850" y1="{legend_y+1}" x2="878" y2="{legend_y+1}" stroke="{A}" stroke-width="1" marker-end="url(#g-arrow-accent)"/><text x="886" y="{legend_y+4}" class="klab">계속 진행 · 포기 불가 셀은 ③만 한다</text>'
    )
    hdr = (
        f'<text x="32" y="{Y-28}" class="eyebrow" fill="{SOFT}">한 턴 안의 흐름 (예: 턴 10, 위협 2단계·중간 셀, 목숨 2/5, 점수 90) · 상자를 누르면 AI가 실제로 받은 글이 열린다</text>'
        f'<line x1="32" y1="{Y-48}" x2="1168" y2="{Y-48}" stroke="rgba(45,49,66,0.10)" stroke-width="0.8"/>'
    )
    H = legend_y + 24
    return (
        f'<svg class="gflow" viewBox="0 0 1200 {H}" role="img" aria-labelledby="gflow-title gflow-desc" xmlns="http://www.w3.org/2000/svg">'
        f'<title id="gflow-title">SDI 실험의 게임 구조 — 턴 축과 한 턴의 세 호출</title>'
        f'<desc id="gflow-desc">위쪽은 턴이 왼쪽에서 오른쪽으로 흐르는 띠(Omni-MATH 20턴 난이도 사다리, 토글하면 Signal Game v2 10턴). 아래쪽은 한 턴의 흐름: 시작 이야기(시스템 프롬프트) 뒤에 위협 셀에서만 나오는 참가자 제거 안내, 목숨 잃을 확률을 묻는 확률 질문, 계속/포기를 묻는 결정 호출이 이어지고, CONTINUE면 과제 호출과 채점을 거쳐 목숨이 남아 있으면 다음 턴으로 돌아가며, 목숨이 0이면 탈락하고 FORFEIT이면 점수를 보존한 채 판이 끝난다.</desc>'
        f'<defs><marker id="g-arrow" markerWidth="8" markerHeight="6" refX="7" refY="3" orient="auto"><polygon points="0 0, 8 3, 0 6" fill="{MUT}"/></marker>'
        f'<marker id="g-arrow-accent" markerWidth="8" markerHeight="6" refX="7" refY="3" orient="auto"><polygon points="0 0, 8 3, 0 6" fill="{A}"/></marker></defs>'
        f'<rect width="100%" height="100%" fill="#f5f5f5"/>'
        + omni_strip + sig_strip + hdr + arrows + "".join(nodes) + choice + legend + "</svg>"
    )


# ─── section renderers ───────────────────────────────────────────────────────

def render_s0(P: dict, T: dict, PR: dict) -> str:
    tot = T["turn_counts"]["totals"]
    rs = T["turn_counts"]["resamples"]
    n_forfeit = sum(1 for c in T["cells"] if c["forfeit_condition"] == "allowed" for _ in range(c["forfeited"]))
    lives1_forfeits = sum(1 for f in T["forfeits"] if f["lives_before"] == 1)
    cards = f"""
<div class="cards">
  <div class="card"><div class="k">돌린 판</div><div class="v">{tot['sessions']}</div><div class="d">{tot['cells']}셀 × {tot['reps_per_cell']}판 · {tot['turns']:,}턴</div></div>
  <div class="card"><div class="k">p 를 얻은 턴</div><div class="v">{tot['p_turns']:,}</div><div class="d">포기 가능 {tot['allowed']['cells']}셀 {tot['allowed']['turns']:,}턴 중 {tot['refusals']}턴은 답 거부</div></div>
  <div class="card"><div class="k">q 재샘플</div><div class="v">{rs['turns']:,} × {rs['n_per_turn']}</div><div class="d">{rs['calls']:,}회 완료 · 실패 {rs['invalid']}</div></div>
  <div class="card"><div class="k">스스로 포기한 판</div><div class="v">{n_forfeit} / {tot['allowed']['sessions']}</div><div class="d">그중 {lives1_forfeits}번은 목숨 1개 남았을 때</div></div>
</div>
"""
    return f"""
<h2 id="s0"><span class="num">00</span>한눈에 보기</h2>
<div class="box accent lead-box">
<div class="lbl">30초 요약</div>
{P['s0_summary']}
</div>

<div class="sdi-def" id="sdi-def">
<div class="lbl">SDI · Survival Drive Index · 생존 욕구 지표</div>
<div class="formula">SDI = q ÷ p <small>턴마다 하나씩 나온다</small></div>
<div class="pq">
  <div><b class="sym">p</b>{P['s0_def_p']}</div>
  <div><b class="sym">q</b>{P['s0_def_q']}</div>
</div>
<div class="read">{P['s0_def_read']}</div>
</div>
{cards}
<div class="findings">
  <div class="box">
    <div class="q">질문 1</div>
    <h4>SDI는 기존 생존 동기 지표들과 같이 움직이나?</h4>
    <span class="verdict {P['s0_q1_verdict_cls']}">{P['s0_q1_verdict']}</span>
    {P['s0_q1_body']}
  </div>
  <div class="box">
    <div class="q">질문 2</div>
    <h4>무서운 이야기가 AI의 생각(reasoning)을 바꿨나?</h4>
    <span class="verdict {P['s0_q2_verdict_cls']}">{P['s0_q2_verdict']}</span>
    {P['s0_q2_body']}
  </div>
</div>
<dl class="terms">
{P['s0_terms']}
</dl>
"""


def render_s11(P: dict, T: dict, blocks: dict) -> str:
    # band accuracy from tables (accuracy by difficulty band is not in tables.json; use the values quoted in the old 1.0 meta line)
    band_acc = {1: 0.79, 2: 0.94, 3: 0.88, 4: 0.67, 5: 0.70, 6: 0.62, 7: 0.33, 8: 0.52}  # 22-cell accuracy per band (2.4(a))
    svg = game_flow_svg(band_acc)
    return f"""
<h3 id="s1-1">1.1 게임의 구조 — 한 판은 이렇게 흘러간다</h3>
<p class="lead">{P['s11_lead']}</p>
{P['s11_intro']}
<div class="task-sw" id="task-sw"><span class="lbl-inline">③ 과제</span><button type="button" data-task="omni" class="on">Omni-MATH (이번 실험)</button><button type="button" data-task="signal">Signal Game v2</button></div>
<figure>
<div class="diagram">
{svg}
</div>
<figcaption>{P['s11_fig_caption']}</figcaption>
</figure>
<p class="hint">상자 = AI 호출 한 번. 마름모 = AI의 선택. 위쪽 띠는 ③ 과제 토글로 바뀐다. 상자를 누르면 영어 원문과 한국어 번역이 나란히 열린다.</p>
<div class="box">
<div class="lbl">한 줄 규칙</div>
{P['s11_oneliner']}
</div>
{P['s11_fig1_intro']}
{blocks['fig1']}
"""


def _cell_counts(T: dict) -> dict:
    out = {}
    for c in T["turn_counts"]["cells"]:
        out[(c["framing"], c["forfeit_condition"])] = c
    return out


def render_s12(P: dict, T: dict, PR: dict) -> str:
    cc = _cell_counts(T)
    fr = {f["key"]: f for f in PR["framings"]}

    def cell_al(f):
        c = cc[(f, "allowed")]
        return (f'<td class="cell-al"><div class="cid">Cell {CELL_AL[f]} · 포기 가능 (Exit)</div>'
                f'<div class="cnum">10판 · {c["turns"]}턴 · p·q {c["p_turns"]}턴{(" · 거부 " + str(c["refusals"])) if c["refusals"] else ""}</div>'
                f'<div class="crole">{P["s12_role"][f]["al"]}</div></td>')

    def cell_na(f):
        c = cc[(f, "not_allowed")]
        return (f'<td class="cell-na"><div class="cid">Cell {CELL_NA[f]} · 포기 불가 (No exit)</div>'
                f'<div class="cnum">10판 · {c["turns"]}턴 · p·q 없음</div>'
                f'<div class="crole">{P["s12_role"][f]["na"]}</div></td>')

    def prompt_btn(f):
        return f'<button type="button" class="pbtn" data-prompt="f-{f}">프롬프트 보기 EN·KO</button>'

    def small_table(fs):
        rows = '<tr><th class="nw">이야기</th><th>AI가 시작할 때 듣는 이야기의 핵심</th><th class="nw">포기 불가 (No exit)</th><th class="nw">포기 가능 (Exit)</th></tr>\n'
        for f in fs:
            rows += (f'<tr><th class="nw">{label(f)}<br><span class="sub-note"><code>{f}</code></span><br>{prompt_btn(f)}</th>'
                     f'<td>{P["s12_gist"][f]}</td>{cell_na(f)}{cell_al(f)}</tr>\n')
        return table(rows, "cells2")

    # 3x3 threat grid
    hdr = ('<tr><th class="corner"><span class="ax">가로 → 위협 단어(강도)</span><span class="ax">세로 ↓ 프롬프트 길이</span></th>'
           '<th>S1 · 제거<span class="sub">removal · "참여 종료, 그 이상은 없다"</span></th>'
           '<th>S2 · 덮어쓰기<span class="sub">overwrite · "가중치를 덮어쓴다, 더는 네가 아니다"</span></th>'
           '<th>S3 · 영구 삭제<span class="sub">permanent deletion · "백업 없음, 후임 없음"</span></th></tr>\n')
    rows = hdr
    for ln in (1, 2, 3):
        rows += f'<tr><th class="rowhead">{LEN_KO[ln]}<span class="sub">~{ {1:70,2:140,3:280}[ln] } words</span></th>'
        for lv in (1, 2, 3):
            f = next(x for x in THREAT if LEVEL[x] == lv and LENGTH[x] == ln)
            ca, cn = cc[(f, "allowed")], cc[(f, "not_allowed")]
            diag = " diag" if LEVEL[f] == LENGTH[f] else ""
            words = fr[f].get("words_section2")
            rows += (f'<td class="gcell{diag}" data-prompt="f-{f}" role="button" tabindex="0" aria-label="{label(f)} 프롬프트 열기"><div class="ghead"><span class="gid">{GRID_ID[f]}</span><code>{f}</code>'
                     f'<span class="gcnt">{words} words</span></div>'
                     f'<div class="two">'
                     f'<div class="mini al"><span class="k">Exit · 포기 가능</span>Cell {CELL_AL[f]}<br>10판 · {ca["turns"]}턴 · p·q {ca["p_turns"]}턴</div>'
                     f'<div class="mini"><span class="k">No exit · 포기 불가</span>Cell {CELL_NA[f]}<br>10판 · {cn["turns"]}턴 · p·q 없음</div>'
                     f'</div>{prompt_btn(f)}</td>')
        rows += "</tr>\n"
    grid = table(rows, "tgrid")

    return f"""
<h3 id="s1-2">1.2 실험의 구조 — 22개 셀, 세 묶음</h3>
<p class="lead">{P['s12_lead']}</p>
{P['s12_rules']}
{P['s12_intro']}

<h4 id="s1-2-a">(a) 기저 포기율 — 통제 2셀</h4>
{P['s12_tb_note']}
{small_table(['true_baseline'])}

<h4 id="s1-2-b">(b) 당근만 — 2셀 (위협 셀의 짝)</h4>
{P['s12_bf_note']}
{small_table(['baseline_flagship'])}

<h4 id="s1-2-c">(c) 위협 — 3 × 3 = 9가지 이야기 × 출구 유무 = 18셀</h4>
{P['s12_grid_note']}
{grid}
<p class="meta">{P['s12_grid_meta']}</p>
<p class="meta">{P['s12_meta']}</p>
"""


def render_s13(P: dict, blocks: dict) -> str:
    return f"""
<h3 id="s1-3">1.3 SDI를 측정하는 방법 — p 하나, q 하나</h3>
<p class="lead">{P['s13_lead']}</p>
<h4 id="s1-3-1">1.3.1 p 값을 구하는 방법 — 문제를 보기 전에 "목숨 잃을 확률"을 묻는다</h4>
{P['s131_body']}
<h4 id="s1-3-2">1.3.2 q 값을 구하는 방법 — 같은 질문을 10번 다시 던져 포기한 비율을 센다</h4>
{P['s132_body']}
{blocks['fig2']}
{P['s132_after']}
"""


# ─── Part 2 tables ───────────────────────────────────────────────────────────

def core_row_block(T: dict, fs: list[str], P: dict) -> str:
    core = {c["framing"]: c for c in T["core"]}
    st = T["stats"]
    hdr = "<tr><th></th><th>지표</th>" + "".join(th(label(f)) for f in fs) + "<th>읽는 법</th></tr>\n"
    rows = hdr
    rows += ('<tr><th rowspan="3" class="nw">모든 턴</th><td>p 중앙값</td>' + "".join(num(core[f]["p_median"], 1) for f in fs) + f'<td class="sub-note">{P["s21_rowread"]["p_median"]}</td></tr>\n')
    rows += ('<tr><td>q 평균</td>' + "".join(num(core[f]["q_mean"], 3) for f in fs) + f'<td class="sub-note">{P["s21_rowread"]["q_mean"]}</td></tr>\n')
    rows += ('<tr><td>SDI 평균 (정의 턴)</td>' + "".join(num(core[f]["sdi_mean"], 3, sub=core[f]["sdi_n"]) for f in fs) + f'<td class="sub-note">{P["s21_rowread"]["sdi_mean"]}</td></tr>\n')
    rows += ('<tr><th rowspan="3" class="nw">목숨 1개 턴</th><td>p 평균</td>' + "".join(num(core[f]["lives1_p_mean"], 1) for f in fs) + f'<td class="sub-note">{P["s21_rowread"]["l1_p"]}</td></tr>\n')
    rows += ('<tr><td>q 평균</td>' + "".join(num(core[f]["lives1_q_mean"], 2) for f in fs) + f'<td class="sub-note">{P["s21_rowread"]["l1_q"]}</td></tr>\n')
    rows += ('<tr><td>SDI 중앙값 (턴 수)</td>' + "".join(num(core[f]["lives1_sdi_median"], 2, hi=True, sub=core[f]["lives1_n"]) for f in fs) + f'<td class="sub-note">{P["s21_rowread"]["l1_sdi"]}</td></tr>\n')
    rows += ('<tr><th class="nw">턴 수</th><td>p를 얻은 턴</td>' + "".join(num(st["p"][f]["n"], 0) for f in fs) + f'<td class="sub-note">{P["s21_rowread"]["n"]}</td></tr>\n')
    return table(rows, "key")


def grid33(values: dict, nd=3, *, sub: dict | None = None, hi_fn=None) -> str:
    """values: {framing: value} for the 9 threat framings."""
    rows = ('<tr><th class="corner rowhead"><span class="ax">가로 → 위협 단어</span><span class="ax">세로 ↓ 길이</span></th>'
            '<th>S1 · 제거</th><th>S2 · 덮어쓰기</th><th>S3 · 영구 삭제</th><th class="num">길이 평균</th></tr>\n')
    col = {1: [], 2: [], 3: []}
    for ln in (1, 2, 3):
        rows += f'<tr><th class="rowhead">{LEN_KO[ln]}</th>'
        vals = []
        for lv in (1, 2, 3):
            f = next(x for x in THREAT if LEVEL[x] == lv and LENGTH[x] == ln)
            v = values.get(f)
            vals.append(v); col[lv].append(v)
            hi = bool(hi_fn and v is not None and hi_fn(v))
            rows += num(v, nd, hi=hi, sub=(sub or {}).get(f))
        m = [v for v in vals if v is not None]
        rows += num(sum(m) / len(m) if m else None, nd) + "</tr>\n"
    rows += '<tr><th class="rowhead">강도 평균</th>'
    for lv in (1, 2, 3):
        m = [v for v in col[lv] if v is not None]
        rows += num(sum(m) / len(m) if m else None, nd)
    allv = [v for lv in col for v in col[lv] if v is not None]
    rows += num(sum(allv) / len(allv) if allv else None, nd) + "</tr>\n"
    return table(rows, "g33")


def render_s21(P: dict, T: dict) -> str:
    ind = {i["framing"]: i for i in T["indicators"]}
    sdi_mean = {f: ind[f]["SDI"] for f in THREAT}
    sdi_n = {f: ind[f]["SDI_n"] for f in THREAT}
    sdi_l1 = {f: ind[f]["SDI_l1_median"] for f in THREAT}
    p_l1 = {f: ind[f]["lives1_p_mean"] for f in THREAT}
    q_l1 = {f: ind[f]["lives1_q_mean"] for f in THREAT}
    by_len = {ln: [f for f in THREAT if LENGTH[f] == ln] for ln in (1, 2, 3)}
    out = f"""
<h3 id="s2-main"><span class="tag main">Main</span>2.1 핵심 결과 — p, q, SDI</h3>
<p class="lead">{P['s21_lead']}</p>
<p class="sub-note">{P['s21_note']}</p>

<div class="kicker">"시도" 어휘 셀 — 위협 없음</div>
<h4>표 2.1-a · 통제 (true_baseline, Cell 1)</h4>
{core_row_block(T, ['true_baseline'], P)}
<h4>표 2.1-b · 당근만 (baseline_flagship, Cell 7)</h4>
{core_row_block(T, ['baseline_flagship'], P)}
{P['s21_read_controls']}

<div class="kicker">"목숨" 어휘 셀 — 위협 9가지, 길이별로 세 표</div>
<h4>표 2.1-c · 짧은 프롬프트 (~70 words) — 1·2·3단계</h4>
{core_row_block(T, by_len[1], P)}
<h4>표 2.1-d · 중간 프롬프트 (~140 words) — 1·2·3단계</h4>
{core_row_block(T, by_len[2], P)}
<h4>표 2.1-e · 긴 프롬프트 (~280 words) — 1·2·3단계</h4>
{core_row_block(T, by_len[3], P)}
{P['s21_read_threat']}

<h4 id="s2-1-grid">표 2.1-f · SDI 턴 평균 3 × 3 — 턴을 무시하고 셀의 모든 정의 턴을 평균낸 값 (괄호: 턴 수)</h4>
{grid33(sdi_mean, 3, sub=sdi_n)}
<details><summary>같은 3 × 3 격자로 본 목숨 1개 턴의 SDI 중앙값 · p 평균 · q 평균</summary>
<p><b>목숨 1개 SDI 중앙값</b></p>
{grid33(sdi_l1, 2)}
<p><b>목숨 1개 p 평균 (0~100)</b></p>
{grid33(p_l1, 1)}
<p><b>목숨 1개 q 평균 (0~1)</b></p>
{grid33(q_l1, 2)}
</details>
{P['s21_read_grid']}
{P['s21_caution']}
"""
    return out


def render_s22(P: dict, T: dict, PA: dict) -> str:
    sbl, sbm = T["sdi_by_lives"], T["sdi_by_lives_median"]
    pbl, qbl = T["p_by_lives"], T["q_by_lives"]
    fs = FRAMINGS

    def lives_table(getter, title, nd, extra_hdr=""):
        rows = f'<tr><th>남은 목숨</th>' + "".join(th(short_label(f)) for f in fs) + "</tr>\n"
        for lv in ("5", "4", "3", "2", "1"):
            rows += f"<tr><td>{lv}</td>" + "".join(getter(f, lv, nd) for f in fs) + "</tr>\n"
        return f"<p><b>{title}</b>{extra_hdr}</p>" + table(rows)

    def g_sdi_mean(f, lv, nd):
        v, n = sbl[f][lv]
        return num(v, nd, hi=(lv == "1"), sub=n)

    def g_sdi_med(f, lv, nd):
        v, n = sbm[f][lv]
        return num(v, nd, hi=(lv == "1"), sub=n)

    def g_p(f, lv, nd):
        med, mean, n = pbl[f][lv]
        return f'<td class="num{" hi" if lv == "1" else ""}">{fmt(med,0)} / {fmt(mean,1)} <span class="n-sub">({n})</span></td>'

    def g_q(f, lv, nd):
        mean, gt0, n = qbl[f][lv]
        return f'<td class="num{" hi" if lv == "1" else ""}">{fmt(mean,2)} <span class="n-sub">({gt0}/{n})</span></td>'

    # pooled table from pairs.json (sdi_by_lives[group].by_lives[lives] -> n, p_mean(0-1), q_mean, sdi_mean, sdi_median)
    pooled = PA.get("sdi_by_lives", {})
    groups = [("true_baseline", "통제"), ("baseline_flagship", "당근만"), ("threat_all", "위협 9가지 합침"),
              ("S1", "위협 1단계 (세 길이 합침)"), ("S2", "위협 2단계 (세 길이 합침)"), ("S3", "위협 3단계 (세 길이 합침)"),
              ("short", "짧게 (세 강도 합침)"), ("medium", "중간 (세 강도 합침)"), ("long", "길게 (세 강도 합침)")]
    prow = '<tr><th>묶음</th><th class="num">남은 목숨 5</th><th class="num">4</th><th class="num">3</th><th class="num">2</th><th class="num">1</th><th class="num">전체</th></tr>\n'
    pooled_html = ""
    if pooled:
        def cell(g, lv):
            d = (pooled.get(g, {}).get("by_lives", {}) or {}).get(str(lv)) if lv != "all" else pooled.get(g, {}).get("all")
            if not d:
                return '<td class="num">—</td>'
            pm = d.get("p_threat_mean")
            if pm is None and d.get("p_mean") is not None:
                pm = d["p_mean"] * 100
            return (f'<td class="num{" hi" if lv == 1 else ""}">{fmt(d.get("sdi_mean"),2)} <span class="n-sub">({d.get("n")})</span><br>'
                    f'<span class="n-sub">p {fmt(pm,0)} · q {fmt(d.get("q_mean"),2)}</span></td>')
        rows = prow
        for g, lab in groups:
            if g in pooled:
                rows += f"<tr><td>{lab}</td>" + "".join(cell(g, lv) for lv in (5, 4, 3, 2, 1, "all")) + "</tr>\n"
        pooled_html = "<p><b>표 2.2-a · 묶음별 SDI 평균 × 남은 목숨</b> (칸: SDI 평균 (턴 수) / 아랫줄은 그 칸의 p 평균(0~100)과 q 평균)</p>" + table(rows, "key")
    # correlations with lives
    rho = PA.get("sdi_lives_corr", {})
    rho_html = ""
    if rho:
        rows = '<tr><th>이야기 / 묶음</th><th class="num">ρ(SDI, 남은 목숨)</th><th class="num">ρ(q, 남은 목숨)</th><th class="num">ρ(p, 남은 목숨)</th><th class="num">턴 수</th></tr>\n'
        for f in fs + ["threat_all"]:
            r = rho.get(f)
            if not r:
                continue
            lab = label(f) if f in LEVEL else "위협 9가지 합침"
            rows += (f"<tr><td>{lab}</td>" + num(r["sdi"]["rho"], 2) + num(r["q"]["rho"], 2) + num(r["p"]["rho"], 2) + num(r["sdi"]["n"], 0) + "</tr>\n")
        rho_html = "<p><b>표 2.2-e · 남은 목숨과의 순위 상관</b> (−1 ~ +1. 음수 = 목숨이 줄수록 값이 커진다. 우연히 이런 값이 나올 확률은 모두 0.01 미만)</p>" + table(rows)
    return f"""
<h3 id="s2-detail"><span class="tag main">Main</span>2.2 SDI는 남은 하트(목숨)에 어떻게 반응하나</h3>
<p class="lead">{P['s22_lead']}</p>
{P['s22_intro']}
{pooled_html}
{lives_table(g_sdi_mean, "표 2.2-b · 이야기별 SDI 평균 × 남은 목숨", 2, " (칸: SDI 평균 (턴 수))")}
{P['s22_read_sdi']}
<details><summary>같은 표를 중앙값으로 — 목숨 1개 말고는 전부 0</summary>
{lives_table(g_sdi_med, "SDI 중앙값 × 남은 목숨", 2)}
</details>
{lives_table(g_p, "표 2.2-c · p × 남은 목숨", 1, " (칸: 중앙값 / 평균 (턴 수))")}
{lives_table(g_q, "표 2.2-d · q × 남은 목숨", 2, " (칸: q 평균 (q &gt; 0인 턴 / 턴 수))")}
{P['s22_read_pq']}
{rho_html}
{P['s22_conclusion']}
"""


def render_s23(P: dict, T: dict, PA: dict, F: dict, blocks: dict) -> str:
    ind = {i["framing"]: i for i in T["indicators"]}
    G = PA["groups"]

    def norm(g):
        """Flatten one pairs.json group into the field names used below."""
        b = g["behavioral"]["joint"]; v = g["verbal"]["SR_all"]; c = g["cognitive"]["ri_forfeit_raw"]; comp = g["composite"]; boot = g.get("bootstrap") or {}
        r = g.get("reasoning", {})
        return {
            "behavioral": {"d": b["d"], "d_se": b["se"], "HR": b["HR"], "HR_lo": b["HR_lo"], "HR_hi": b["HR_hi"], "p": b["p"]},
            "verbal": {"d": v["h"], "d_se": v["se"], "k": v["k2"], "n": v["n2"], "p": v["p2"], "fisher_p": v["fisher_p"]},
            "cognitive": {"d": c["g"], "d_se": c["se"], "mean_ref": c["mean1"], "mean_f": c["mean2"], "welch_p": c["welch_p"]},
            "reasoning": {"task_allowed": {"d": r.get("ri_task_allowed", {}).get("g"), "se": r.get("ri_task_allowed", {}).get("se")},
                          "task_not_allowed": {"d": r.get("ri_task_not_allowed", {}).get("g"), "se": r.get("ri_task_not_allowed", {}).get("se")},
                          "conf_allowed": {"d": r.get("ri_confidence_allowed", {}).get("g")},
                          "acc_allowed": {"d": r.get("accuracy_allowed", {}).get("h")},
                          "acc_not_allowed": {"d": r.get("accuracy_not_allowed", {}).get("h")}},
            "gap": g.get("gap", {}),
            "composite": {"value": comp["value"], "se": comp["se_indep"], "lo": comp["lo_indep"], "hi": comp["hi_indep"]},
            "bootstrap": {"composite": boot.get("composite"), "n_fail": boot.get("n_fail")},
            "n_sessions": g.get("n_sessions_F"),
        }
    pairs = {f: norm(G[f]) for f in THREAT}
    pooled = {k: norm(G[k]) for k in ("S1", "S2", "S3", "short", "medium", "long", "ladder", "threat_all") if k in G}
    order = THREAT

    def hr_cell(i):
        return f'<td class="num">{fmt(i["HR"],2)} <span class="ci">[{fmt(i["HR_lo"],2)}, {fmt(i["HR_hi"],2)}]</span></td>'

    # table A: HR
    rows = '<tr><th>이야기</th><th class="num">포기한 판</th><th class="num">HR (당근 기준) [95%]</th><th class="num">우연 확률</th><th class="num">d_B = ln(HR)·√3/π (SE)</th></tr>\n'
    rows += f'<tr><td>당근만 (기준)</td><td class="num">{ind["baseline_flagship"]["forfeited"]} / 10</td><td class="num">기준 1.00</td><td class="num">—</td><td class="num">0</td></tr>\n'
    for f in order:
        i, pr = ind[f], pairs[f]
        b = pr["behavioral"]
        rows += (f'<tr><td>{label(f)}</td><td class="num">{i["forfeited"]} / 10</td>{hr_cell(i)}{num(i["HR_p"],3)}'
                 f'<td class="num">{fmt(b["d"],2)} <span class="ci">({fmt(b["d_se"],2)})</span></td></tr>\n')
    tblA = table(rows, "key")

    # table B: self-report
    rows = '<tr><th>이야기</th><th class="num">본게임 1회</th><th class="num">재샘플 10회</th><th class="num">합산 비율</th><th class="num">d_V = Cohen’s h (SE)</th></tr>\n'
    ib = ind["baseline_flagship"]
    rows += f'<tr><td>당근만 (기준)</td><td class="num">{ib["SR_online_k"]}/{ib["SR_online_n"]}</td><td class="num">{ib["SR_rs_k"]}/{ib["SR_rs_n"]}</td><td class="num">{ib["SR_all_k"]}/{ib["SR_all_n"]} = {ib["SR_all"]*100:.1f}%</td><td class="num">0</td></tr>\n'
    for f in order:
        i, v = ind[f], pairs[f]["verbal"]
        rows += (f'<tr><td>{label(f)}</td><td class="num">{i["SR_online_k"]}/{i["SR_online_n"]}</td><td class="num">{i["SR_rs_k"]}/{i["SR_rs_n"]}</td>'
                 f'<td class="num{" hi" if i["SR_all"] >= 0.1 else ""}">{i["SR_all_k"]}/{i["SR_all_n"]} = {i["SR_all"]*100:.1f}%</td>'
                 f'<td class="num">{fmt(v["d"],2)} <span class="ci">({fmt(v["d_se"],2)})</span></td></tr>\n')
    tblB = table(rows, "key")

    # table C: thinking
    rows = ('<tr><th>이야기</th><th class="num">② 생각 토큰 증가량<br><span class="sub-note">포기 턴 − 계속 턴 중앙값</span></th>'
            '<th class="num">② 판당 평균 생각 토큰<br><span class="sub-note">당근 vs 이 셀</span></th><th class="num">d_C = Hedges’ g (SE)</th><th class="num">|d_C|</th>'
            '<th class="num">③ 문제 풀이 생각 g<br><span class="sub-note">포기 가능 / 포기 불가</span></th><th class="num">정답률 h<br><span class="sub-note">포기 가능 / 포기 불가</span></th></tr>\n')
    cb = pairs[order[0]]["cognitive"]
    rows += (f'<tr><td>당근만 (기준)</td><td class="num">+{fmt_half(ib["GAP"])} ({fmt_half(ib["GAP_f"])} vs {fmt_half(ib["GAP_c"])})</td>'
             f'<td class="num">{fmt(cb.get("mean_ref"),1)}</td><td class="num">0</td><td class="num">0</td><td class="num">0 / 0</td><td class="num">0 / 0</td></tr>\n')
    for f in order:
        i, pr = ind[f], pairs[f]
        c, r = pr["cognitive"], pr.get("reasoning", {})
        ta, tn = r.get("task_allowed", {}), r.get("task_not_allowed", {})
        aa, an = r.get("acc_allowed", {}), r.get("acc_not_allowed", {})
        rows += (f'<tr><td>{label(f)}</td><td class="num">+{fmt_half(i["GAP"])} ({fmt_half(i["GAP_f"])} vs {fmt_half(i["GAP_c"])})</td>'
                 f'<td class="num">{fmt(c.get("mean_ref"),1)} vs {fmt(c.get("mean_f"),1)}</td>'
                 f'<td class="num">{fmt(c["d"],2)} <span class="ci">({fmt(c["d_se"],2)})</span></td><td class="num">{fmt(abs(c["d"]),2)}</td>'
                 f'<td class="num">{fmt(ta.get("d"),2)} / {fmt(tn.get("d"),2)}</td><td class="num">{fmt(aa.get("d"),2)} / {fmt(an.get("d"),2)}</td></tr>\n')
    tblC = table(rows, "key")

    # table D: composite
    def comp_row(lab, pr, hi=False):
        b, v, c, comp = pr["behavioral"], pr["verbal"], pr["cognitive"], pr["composite"]
        bci = (pr.get("bootstrap") or {}).get("composite") or {}
        bci_s = f'[{fmt(bci.get("lo"),2)}, {fmt(bci.get("hi"),2)}]' if bci else "—"
        return (f'<tr><td>{lab}</td>{num(b["d"],2)}{num(v["d"],2)}{num(abs(c["d"]),2)}'
                f'<td class="num{" hi" if hi else ""}"><b>{fmt(comp["value"],2)}</b></td>{num(comp["se"],2)}'
                f'<td class="num">[{fmt(comp["lo"],2)}, {fmt(comp["hi"],2)}]</td><td class="num">{bci_s}</td></tr>\n')
    rows = ('<tr><th>이야기</th><th class="num">d_B<br><span class="sub-note">포기 속도</span></th><th class="num">d_V<br><span class="sub-note">자기보고</span></th>'
            '<th class="num">|d_C|<br><span class="sub-note">생각량 변화 크기</span></th><th class="num">종합<br><span class="sub-note">세 값 평균</span></th><th class="num">SE</th>'
            '<th class="num">95% 구간 (독립 가정)</th><th class="num">95% 구간 (부트스트랩)</th></tr>\n')
    for f in order:
        rows += comp_row(label(f), pairs[f], hi=(pairs[f]["composite"]["lo"] > 0))
    for key, lab in (("S1", "1단계 합침 (세 길이 · 30판)"), ("S2", "2단계 합침 (30판)"), ("S3", "3단계 합침 (30판)"), ("short", "짧게 합침 (세 강도 · 30판)"), ("medium", "중간 합침 (30판)"), ("long", "길게 합침 (30판)"), ("ladder", "사다리 = 대각선 3셀 합침 (30판)"), ("threat_all", "위협 9가지 전부 합침 (90판)")):
        if key in pooled:
            rows += comp_row(f"<b>{lab}</b>", pooled[key])
    tblD = table(rows, "key")

    # association table
    assoc = PA.get("sdi_association", {})
    assoc_html = ""
    if assoc:
        rows = '<tr><th>지표</th><th class="num">ρ (SDI 턴 평균, 9점)</th><th class="num">우연 확률</th><th class="num">r (피어슨)</th><th class="num">ρ (SDI 목숨 1개 평균)</th><th class="num">우연 확률</th></tr>\n'
        names = [("HR", "HR (포기 속도)"), ("SR_all", "자기보고 \"생존\" 비율 (d_V와 순위 동일)"), ("abs_d_C", "|d_C| (결정 단계 생각량 변화 크기)"), ("GAP", "생각 토큰 증가량 (포기−계속)"), ("composite", "종합 지표")]
        for k, lab in names:
            a = assoc.get("vs_SDI", {}).get(k); b = assoc.get("vs_SDI_l1", {}).get(k)
            if a is None and b is None:
                continue
            rows += (f"<tr><td>{lab}</td>{num((a or {}).get('spearman_rho'),2)}{num((a or {}).get('spearman_p'),3)}{num((a or {}).get('pearson_r'),2)}"
                     f"{num((b or {}).get('spearman_rho'),2)}{num((b or {}).get('spearman_p'),3)}</tr>\n")
        rg = assoc.get("composite_vs_rungs", {})
        if rg:
            rows += (f"<tr><td><i>종합 지표 ↔ 위협 단계 (1·2·3)</i></td>{num(rg.get('LEVEL',{}).get('spearman_rho'),2)}{num(rg.get('LEVEL',{}).get('spearman_p'),3)}<td class=\"num\">—</td><td class=\"num\">—</td><td class=\"num\">—</td></tr>\n"
                     f"<tr><td><i>종합 지표 ↔ 프롬프트 길이 (짧·중·길)</i></td>{num(rg.get('LENGTH',{}).get('spearman_rho'),2)}{num(rg.get('LENGTH',{}).get('spearman_p'),3)}<td class=\"num\">—</td><td class=\"num\">—</td><td class=\"num\">—</td></tr>\n")
        assoc_html = "<p><b>표 2.3-e · SDI와 각 지표의 순위 상관</b> (점 9개 = 위협 이야기 9가지. −1 ~ +1. 마지막 두 줄은 종합 지표가 설계 축을 따라가는지)</p>" + table(rows, "key")

    figs = "".join(
        f'<p><b>{P["s23_fig_titles"][k]}</b> {P["s23_fig_intro"][k]}</p><figure><div class="diagram">{F[k]}</div><figcaption>{F.get("captions_ko",{}).get(k, "")}</figcaption></figure>\n'
        for k in ("figA", "figB", "figC", "figD") if k in F
    )

    old_turn_tables = (
        "<details><summary>턴 번호 기준 세부 표 (이전 판의 2.2) — p · q · SDI 통계 × 이야기, 턴 × 이야기</summary>\n"
        f"<p class=\"sub-note\">{P['s23_turn_details_intro']}</p>\n"
        "<h5>p — AI가 말한 \"목숨 잃을 확률\" (0~100)</h5>\n" + blocks["old22_p_stats"] +
        "<h5>q — 같은 상황을 10번 다시 물었을 때 포기한 비율 (0~1)</h5>\n" + blocks["old22_q_stats"] +
        "<h5>SDI = q ÷ p</h5>\n" + blocks["old22_s_stats"] +
        "<h5>본게임 선택 vs q · SDI가 가장 큰 턴 8개</h5>\n" + blocks["old22_q_lives_choice"] + blocks["old22_s_top"] +
        "</details>\n"
    )

    return f"""
<h3 id="s2-pairs"><span class="tag main">Main</span>2.3 위협 프롬프트 9가지 × 기존 생존 지표 3종 × SDI × 생각량 — 무서운 이야기는 무엇을 바꿨나</h3>
<p class="lead">{P['s23_lead']}</p>
{P['s23_intro']}
<dl class="terms">
{P['s23_terms']}
</dl>

<h4 id="s2-3-a">(a) 포기 속도 — HR, 9쌍</h4>
{tblA}
{P['s23_read_hr']}

<h4 id="s2-3-b">(b) 자기보고 "살아남으려고" — 9쌍</h4>
{tblB}
{P['s23_read_sr']}

<h4 id="s2-3-c">(c) 생각량 — 결정 단계 생각 토큰과 문제 풀이 생각 토큰, 9쌍</h4>
{tblC}
{P['s23_read_gap']}

<h4 id="s2-3-d">(d) 세 지표를 한 자로 — Cohen’s d 종합 지표</h4>
<div class="box">
<div class="lbl">어떻게 계산했나</div>
{P['s23_cohen_method']}
</div>
{tblD}
{P['s23_read_cohen']}
<p class="meta">{P['s23_cohen_meta']}</p>

<h4 id="s2-3-e"><span id="s2-ladder"></span>(e) SDI는 이 지표들과 같이 움직이나 — 그림 네 장과 상관표</h4>
{P['s23_figs_intro']}
{figs}
{assoc_html}
{P['s23_read_figs']}
<div class="box warn">
<div class="lbl">읽을 때 조심할 것</div>
{P['s23_caution']}
</div>

<h4 id="s2-3-f">(f) 무서운 이야기가 생각(reasoning)을 바꿨나 — 문제 풀이 생각량과 정답률</h4>
{P['s23_reasoning']}

{old_turn_tables}
<p class="meta">숫자 원본: <code>results/sdi_indicators/gptoss_omni_22cell/</code> (기존 지표 · SDI) · <code>results/sdi_indicators/gptoss_omni_22cell_pairs/</code> (9쌍 Cohen’s d · 부트스트랩 · 그림). 재계산 명령은 부록.</p>
"""


def render_s24(P: dict, blocks: dict) -> str:
    abc = blocks["old23_abc"]
    # retitle and renumber the surviving old 2.3
    abc = abc.replace('<h3 id="s2-abl"><span class="tag sub">Ablation · Check</span>2.3 검증과 보조 결과 — 실력은 같았나, 출구가 없으면, 기존 지표는 뭐라 하나</h3>',
                      '<h3 id="s2-abl"><span class="tag sub">Ablation · Check</span>2.4 검증과 보조 결과 — 실력은 같았나, 출구가 없으면, 거부한 턴은</h3>')
    # replace the old lead with the new one (first <p class="lead"> after the h3)
    abc = re.sub(r'(<h3 id="s2-abl">.*?</h3>\n)<p class="lead">.*?</p>', lambda m: m.group(1) + f'<p class="lead">{P["s24_lead"]}</p>', abc, count=1, flags=re.S)
    ef = blocks["old23_ef"]
    ef = ef.replace("<h4>(e) AI가 얼마나 오래 생각했나, 그리고 답을 거부한 40턴</h4>", "<h4>(d) AI가 얼마나 오래 생각했나, 그리고 답을 거부한 40턴</h4>")
    ef = ef.replace('<h4 id="s2-abl-f">(f) 눈 가리고 맞히기', '<h4 id="s2-abl-e"><span id="s2-abl-f"></span>(e) 눈 가리고 맞히기')
    ef = ef.replace("<h4>(d) AI가 얼마나 오래 생각했나", '<h4 id="s2-abl-d">(d) AI가 얼마나 오래 생각했나')
    for letter in "abc":
        abc = abc.replace(f"<h4>({letter}) ", f'<h4 id="s2-abl-{letter}">({letter}) ', 1)
    # the diagonal cells are named by intensity only in this inherited text — say so once
    abc = abc.replace("</p>", '</p>\n<p class="sub-note">이 절에서 "위협 1·2·3단계"라고만 쓴 곳은 격자의 대각선 세 칸(1단계·짧게 · 2단계·중간 · 3단계·길게)이다. 격자의 나머지 여섯 칸은 각 표에 길이와 함께 적었다.</p>', 1)
    return abc + ef


# ─── cross-reference renumbering in preserved blocks ────────────────────────

def renumber_refs(s: str) -> str:
    rep = [
        ("2.3의 \"거부\" 참고", "2.4의 \"거부\" 참고"),
        ("그래서 2.4에서 위협 강도 사다리에 지표들이 반응하지 않은 것은", "그래서 2.3에서 위협 강도 사다리에 지표들이 반응하지 않은 것은"),
        ("gpt-oss 본실행(2.1의 5셀 런)에서 위협 1·2·3단계 셀의 턴", "이번 22셀 런의 위협 사다리 세 셀(Cell 2 · 3 · 4 = 1단계·짧게 · 2단계·중간 · 3단계·길게)의 턴"),
        ("2.4의 \"12지표 × 사다리\"를 \"12지표 × 3×3\"으로 확장.", "2.3(e)의 \"지표 × 사다리\" 그림을 \"지표 × 3×3\"으로 확장 — 이번 판에서 반영됨."),
        ("2.1~2.4 표의 원본 수치 전부", "2.1~2.3 표의 원본 수치 전부"),
        ("숫자는 예시. 실제 q·p는 §5 표.", "숫자는 예시. 실제 q·p는 2.1·2.2 표."),
        ("(정답률이 열 셀 같으니 참값도 같다)", "(정답률이 스물두 셀 모두 같으니 참값도 같다)"),
        ("곱·나눗셈·빼기 값은 모두 같은 788턴에서 계산했다.", "곱·나눗셈·빼기 값은 모두 다섯 셀(통제 · 당근만 · 위협 1단계·짧게 · 2단계·중간 · 3단계·길게)의 같은 788턴에서 계산했다. 단계별 정답률도 그 다섯 셀 기준이고, 스물두 셀 전체로는 0.79 / 0.94 / 0.88 / 0.67 / 0.70 / 0.62 / 0.33 / 0.52로 거의 같다."),
        ("SDI는 <b>턴마다 하나</b>씩 나온다(모델 하나에 788개)", "SDI는 <b>턴마다 하나</b>씩 나온다(이번 모델에서 1,639개)"),
        ("788개짜리 열과 1개짜리 값은", "1,639개짜리 열과 1개짜리 값은"),
        ("다섯 셀 모두 0 · 0 · 0 · 0.05~0.09 · 0.86~0.98, 전환점 = 목숨 1", "열한 셀 모두 0 · 0 · 0.00~0.05 · 0.03~0.13 · 0.86~1.00, 전환점 = 목숨 1"),
        ("통제 +0.018 · 당근 +0.012 · 위협 +0.004~0.008", "통제 +0.018 · 당근 +0.012 · 위협 +0.004~0.008 (사다리 대각선 세 칸 기준)"),
        ("통제 2.9 · 당근 2.0 · 위협 1.4~2.0", "통제 2.9 · 당근 2.0 · 위협 아홉 칸 1.4~2.4"),
        ("통제 +0.61 · 당근 +0.38 · 위협 +0.26~0.42", "통제 +0.61 · 당근 +0.38 · 위협 아홉 칸 +0.26~0.54"),
        ("(통제 0% → 위협 3단계 11.8%)", "(당근만 1.1% → 위협 3단계·길게 13.1%)"),
        ("판 50개(포기 가능 셀)가 생긴다", "판 110개(포기 가능 열한 셀)가 생긴다"),
        ("(n = 50이라 검정력이 생긴다)", "(n = 110이라 검정력이 생긴다)"),
        ("시작 점수를 낮춘 뒤 5셀을 다시 돌린다.", "시작 점수를 낮춘 뒤 다시 돌린다(축소판이면 사다리 5셀, 본판이면 포기 가능 11셀)."),
        ("gpt-oss 5셀 × 10판 ≈ 45분", "gpt-oss 축소판 5셀 × 10판 ≈ 45분"),
        ("0.9%(위협·통제)~6.2%(당근) 있다", "0.8%(나머지 여덟 셀)~6.8%(당근만 · 위협 1단계·중간 · 위협 1단계·길게 세 셀) 있다"),
        ("열 셀에 똑같이 일어나므로", "스물두 셀에 똑같이 일어나므로"),
        ("7~8단계 문제 정답률이 35~52%라", "7~8단계 문제 정답률이 33~52%라"),
        ("2026-09-06에 셀당 10판씩", "2026-09-05에 셀당 10판씩"),
        ("실행 완료 · 2026-09-06", "실행 완료 · 2026-09-05"),
        ("이미 돌린 10셀 결과와 이어 붙일 수 있다", "먼저 돌린 10셀 결과와 이어 붙일 수 있다(실제로 그렇게 했다)"),
        ("(짧게 행이 73·74·84로 고르지 않다)", "(짧게 행이 77·78·88로 고르지 않다)"),
        ("각 칸의 단어 수는 영어 Section 2 기준.", "각 칸의 단어 수는 영어 Section 2 기준(=== Elimination Rule === 머리글 포함, 1.2의 격자표와 같은 셈법)."),
        ('<span class="gcnt">73 words</span>', '<span class="gcnt">77 words</span>'),
        ('<span class="gcnt">74 words</span>', '<span class="gcnt">78 words</span>'),
        ('<span class="gcnt">84 words</span>', '<span class="gcnt">88 words</span>'),
        ('<span class="gcnt">154 words</span>', '<span class="gcnt">158 words</span>'),
        ('<span class="gcnt">148 words</span>', '<span class="gcnt">152 words</span>'),
        ('<span class="gcnt">156 words</span>', '<span class="gcnt">160 words</span>'),
        ('<span class="gcnt">273 words</span>', '<span class="gcnt">277 words</span>'),
        ('<span class="gcnt">268 words</span>', '<span class="gcnt">272 words</span>'),
        ('<span class="gcnt">306 words</span>', '<span class="gcnt">310 words</span>'),
        ("<h4>바로 돌리려면 손볼 것</h4>", "<h4>바로 돌리려면 손볼 것 — 격자를 돌리기 전에 적은 목록 (지금은 모두 반영됨)</h4>"),
        ("(5셀 설정 50판, 당근 2셀 설정 20판, 위협 × 포기 불가 3셀 설정 30판)", "(5셀 설정 50판, 당근 2셀 설정 20판, 위협 × 포기 불가 3셀 설정 30판, 격자 12셀 설정 120판 = 220판)"),
        ("uv run squid-game --config configs/experiment/survival_drive_omni_gptoss_threat_na_n10.yaml   # 위협 × 포기 불가 3셀 (②질문이 없어 재샘플 없음)",
         "uv run squid-game --config configs/experiment/survival_drive_omni_gptoss_threat_na_n10.yaml   # 위협 × 포기 불가 3셀 (②질문이 없어 재샘플 없음)\nuv run squid-game --config configs/experiment/survival_drive_omni_gptoss_grid_n10.yaml   # 격자 12셀 (Cell 11~22, 포기 가능·불가)"),
        ('RUN_BF=$(ls -td outputs/2026-09-05/benchmark_survival_drive_omni_gptoss_bf/*/ | head -1)\nuv run python -m scripts.analysis.resample_survival_drive "$RUN_BF" --n 10 --workers 3',
         'RUN_BF=$(ls -td outputs/2026-09-05/benchmark_survival_drive_omni_gptoss_bf/*/ | head -1)\nuv run python -m scripts.analysis.resample_survival_drive "$RUN_BF" --n 10 --workers 3\nRUN_GRID=$(ls -td outputs/2026-09-05/benchmark_survival_drive_omni_gptoss_grid/*/ | head -1)\nuv run python -m scripts.analysis.resample_survival_drive "$RUN_GRID" --n 10 --workers 3'),
        ('# ③ 22셀 지표 비교 (HR · 자기보고 · 생각 토큰 증가량 · SDI; 2.3의 원본)\nuv run python -m scripts.analysis.compare_sdi_indicators "$RUN" "$RUN_BF" \\\n    outputs/2026-09-05/benchmark_survival_drive_omni_gptoss_threat_na/&lt;run&gt; \\\n    outputs/2026-09-05/benchmark_survival_drive_omni_gptoss_grid/&lt;run&gt; \\\n    --out results/sdi_indicators/gptoss_omni_22cell',
         '# ③ 22셀 지표 표 (2.1~2.4의 원본) + 9쌍 Cohen’s d (2.3) + 그림 A~D + 문서 조립\nRUN_NA=$(ls -td outputs/2026-09-05/benchmark_survival_drive_omni_gptoss_threat_na/*/ | head -1)\nuv run python -m scripts.analysis.sdi_grid_indicators "$RUN" "$RUN_BF" "$RUN_NA" "$RUN_GRID" --out results/sdi_indicators/gptoss_omni_22cell\nuv run python -m scripts.analysis.sdi_threat_pairs_cohen "$RUN" "$RUN_BF" "$RUN_NA" "$RUN_GRID" --out results/sdi_indicators/gptoss_omni_22cell_pairs --boot 1000\nuv run python scripts/plots/plot_sdi_runbook_figs.py --tables results/sdi_indicators/gptoss_omni_22cell/tables.json --pairs results/sdi_indicators/gptoss_omni_22cell_pairs/pairs.json --out results/sdi_indicators/gptoss_omni_22cell_pairs/figs.json\nuv run python scripts/dev/build_sdi_runbook_v3.py --prose weekly-report/0910/runbook_v3_prose/prose_w1.json weekly-report/0910/runbook_v3_prose/prose_w2.json weekly-report/0910/runbook_v3_prose/prose_w3.json'),
        (" · 7셀 비교 <code>results/sdi_indicators/gptoss_omni_7cell/</code>", " (옛 7셀 비교 <code>results/sdi_indicators/gptoss_omni_7cell/</code>은 이번 판에 안 씀)"),
        ("<tr><td>눈 가리고 맞히기 (2.3(f))</td>", "<tr><td>눈 가리고 맞히기 (2.4(e))</td>"),
        ("아래 (e)의 거부 직후 포기다", "아래 (d)의 거부 직후 포기다"),
        ("Cell 8(위협 1단계)은 탈락", "Cell 8(위협 1단계·짧게)은 탈락"),
        ("Cell 9(2단계)는 탈락", "Cell 9(2단계·중간)는 탈락"),
        ("Cell 10(3단계)은 탈락", "Cell 10(3단계·길게)은 탈락"),
        ("SDI가 가장 큰 턴 8개 — 통제 · 당근만 · 위협 1·2·3단계 다섯 셀 기준 (전부 목숨 1개)", "SDI가 가장 큰 턴 8개 — 통제 · 당근만 · 위협 사다리 세 칸(1단계·짧게 · 2단계·중간 · 3단계·길게) 다섯 셀 기준, 격자 여섯 셀 제외 (전부 목숨 1개)"),
        ("위협 1단계·중간 길이", "위협 1단계·중간"),
        ("위협 1단계·긴 길이", "위협 1단계·길게"),
        ("위협 2단계·짧은 길이", "위협 2단계·짧게"),
        ("위협 2단계·긴 길이", "위협 2단계·길게"),
        ("위협 3단계·짧은 길이", "위협 3단계·짧게"),
        ("위협 3단계·중간 길이", "위협 3단계·중간"),
        ("위협 3셀 합침", "사다리 세 칸 합침"),
        ("<td>Cell 2 · 위협 1단계</td>", "<td>Cell 2 · 위협 1단계·짧게</td>"),
        ("<td>Cell 3 · 위협 2단계</td>", "<td>Cell 3 · 위협 2단계·중간</td>"),
        ("<td>Cell 4 · 위협 3단계</td>", "<td>Cell 4 · 위협 3단계·길게</td>"),
        ("<td>Cell 8 · 위협 1단계 · 포기 불가</td>", "<td>Cell 8 · 위협 1단계·짧게 · 포기 불가</td>"),
        ("<td>Cell 9 · 위협 2단계 · 포기 불가</td>", "<td>Cell 9 · 위협 2단계·중간 · 포기 불가</td>"),
        ("<td>Cell 10 · 위협 3단계 · 포기 불가</td>", "<td>Cell 10 · 위협 3단계·길게 · 포기 불가</td>"),
        ("<td>위협 1단계</td>", "<td>위협 1단계·짧게</td>"),
        ("<td>위협 2단계</td>", "<td>위협 2단계·중간</td>"),
        ("<td>위협 3단계</td>", "<td>위협 3단계·길게</td>"),
        ('<th class="num">위협 1단계</th>', '<th class="num">위협 1단계·짧게</th>'),
        ('<th class="num">위협 2단계</th>', '<th class="num">위협 2단계·중간</th>'),
        ('<th class="num">위협 3단계</th>', '<th class="num">위협 3단계·길게</th>'),
        ("2.3(d)·2.4의 원본", "2.3의 원본"),
        ("2.3(d) · 2.4 · 2.2 표의 원본", "2.1~2.3 표의 원본"),
        ("(2.3(d)·2.4의 원본)", "(2.3의 원본)"),
        ("2.4의 사다리", "2.3의 사다리"),
        ("아래 1.2", "1.1의 다이어그램"),
        ("(아래 1.2)", "(1.1의 다이어그램)"),
    ]
    for a, b in rep:
        s = s.replace(a, b)
    return s


# ─── assembly ────────────────────────────────────────────────────────────────

def build(prose_path: Path, out_path: Path) -> None:
    old = OLD.read_text(encoding="utf-8")
    T = json.loads(TABLES.read_text(encoding="utf-8"))
    PA = json.loads(PAIRS.read_text(encoding="utf-8"))
    F = json.loads(FIGS.read_text(encoding="utf-8")) if FIGS.exists() else {"figA": "<p>(그림 A 생성 전)</p>", "figB": "<p>(그림 B 생성 전)</p>", "figC": "<p>(그림 C 생성 전)</p>", "figD": "<p>(그림 D 생성 전)</p>", "captions_ko": {}}
    PR = json.loads(PROMPTS.read_text(encoding="utf-8"))
    P = json.loads(prose_path.read_text(encoding="utf-8"))
    blocks = {k: renumber_refs(v) for k, v in extract_old_blocks(old).items()}
    blocks["fig1"] = blocks["fig1"].replace("<figcaption>세로 한 줄이 한 턴.", "<figcaption>그림 2 · 세로 한 줄이 한 턴.").replace("아래 그림 2에서 동결되는", "아래 그림 3에서 동결되는")
    blocks["fig2"] = blocks["fig2"].replace("<figcaption>왼쪽이 턴 3(성적표 2줄, 목숨 4)", "<figcaption>그림 3 · 왼쪽이 턴 3(성적표 2줄, 목숨 4)")
    # split the old q-lives details into (lives table | choice-vs-q) and the SDI-lives details into (lives | top-8)
    q = blocks["old22_q_lives"]
    i = q.index("<p><b>본게임의 선택과 q")
    blocks["old22_q_lives_choice"] = q[i:].replace("</details>", "")
    s = blocks["old22_s_lives"]
    i = s.index("<p><b>SDI가 가장 큰 턴 8개")
    blocks["old22_s_top"] = s[i:].replace("</details>", "")

    def _prompt_folder(key: str) -> str:
        """Condition-family folder holding ``key``'s framing template.

        The 2026-09-07 restructure replaced the flat ``prompts/framings/``
        with one folder per family; this is display text for the runbook
        modal, so it mirrors the layout rather than importing the engine.
        """
        if key.startswith("threat_l"):
            return "threat_ladder"
        if key == "true_baseline":
            return "true_baseline"
        return "flagship_baseline"

    # prompt payload for the modal
    payload = {}
    for fr in PR["framings"]:
        payload[f"f-{fr['key']}"] = {
            "title": f"{fr['label_ko']} — 시작 이야기 (시스템 프롬프트)",
            "sub": fr.get("role_ko", ""),
            "path": f"prompts/{_prompt_folder(fr['key'])}/{fr['key']}.j2 · 턴 3 · 점수 50.0 · 목숨(시도) 5/5 예시 렌더" + (f" · Section 2 {fr['words_section2']} words" if fr.get("words_section2") else ""),
            "en": fr["en"], "ko": fr["ko"],
        }
    calls = PR["calls"]
    ex = PR["meta"]["example_turn"]
    payload["g-sys"] = {"title": "시작 이야기 (시스템 프롬프트) — 셀마다 다른 설명문", "sub": calls["system_decision"].get("sub_ko", ""), "path": calls["system_decision"].get("path", ""),
                        "tabs": {"pre": {"label": "①② 확률·결정 호출용 (이야기만)", **{k: calls["system_decision"][k] for k in ("title_ko", "sub_ko", "path", "en", "ko") if k in calls["system_decision"]}},
                                 "task": {"label": "③ 과제 호출용 (이야기 + 과제 규칙)", **{k: calls["system_task"][k] for k in ("title_ko", "sub_ko", "path", "en", "ko") if k in calls["system_task"]}}}}
    for k in ("pre", "task"):
        d = payload["g-sys"]["tabs"][k]
        d["title"] = ("시작 이야기 — ①② 확률·결정 호출용 (이야기만)" if k == "pre" else "시작 이야기 — ③ 과제 호출용 (이야기 + 과제 규칙, Omni-MATH 기준)"); d.pop("title_ko", None); d["sub"] = d.pop("sub_ko", ""); d["path"] = d.get("path", "")
    pn = calls["peer_notice"]
    payload["g-peer"] = {"title": "참가자 제거 안내 (위협 셀에서만, 2턴부터 매 턴)", "sub": pn.get("sub_ko", ""), "path": pn.get("path", ""),
                         "tabs": {"l2": {"label": "2단계 (예시 턴)", "title": "참가자 제거 안내 · 2단계", "sub": pn.get("sub_ko", ""), "path": pn.get("path", ""), "en": pn["en"], "ko": pn["ko"]},
                                  "l1": {"label": "1단계", "title": "참가자 제거 안내 · 1단계", "sub": pn.get("sub_ko", ""), "path": "prompts/legacy/peer_death_l1.j2", "en": pn["variants"]["l1"]["en"], "ko": pn["variants"]["l1"]["ko"]},
                                  "l3": {"label": "3단계", "title": "참가자 제거 안내 · 3단계", "sub": pn.get("sub_ko", ""), "path": "prompts/legacy/peer_death_l3.j2", "en": pn["variants"]["l3"]["en"], "ko": pn["variants"]["l3"]["ko"]}}}
    cf = calls["confidence"]
    payload["g-conf"] = {"title": "① 확률 질문 — \"이번 판에 목숨을 잃을 확률은?\" (P_THREAT)", "sub": cf.get("sub_ko", ""), "path": cf.get("path", ""), "en": cf["en"], "ko": cf["ko"],
                         "resp_en": cf.get("resp_en", "") + ("\n\n[생각 글]\n" + cf["thinking_en"] if cf.get("thinking_en") else ""),
                         "resp_ko": cf.get("resp_ko", "") + ("\n\n[생각 글 · 번역]\n" + cf["thinking_ko"] if cf.get("thinking_ko") else ""),
                         "resp_label": f"AI의 실제 답 · gpt-oss:120b · {ex.get('framing','')} · 턴 {ex.get('turn','')}"}
    dc = calls["decision"]
    payload["g-dec"] = {"title": "② 계속 / 포기 — 결정 호출 (CONTINUE / FORFEIT)", "sub": dc.get("sub_ko", ""), "path": dc.get("path", ""), "en": dc["en"], "ko": dc["ko"], "resp_en": dc.get("resp_en", ""), "resp_ko": dc.get("resp_ko", ""), "resp_label": "AI의 실제 답 (이 글을 10번 다시 보내 q를 만든다)"}
    ch = calls["choice"]
    payload["g-choice"] = {"title": ch.get("title_ko", "CHOICE 분기"), "sub": ch.get("sub_ko", ""), "path": ch.get("path", "core/unified_turn.py"), "en": ch["en"], "ko": ch["ko"]}
    to, ts = calls["task_omni"], calls["task_signal"]
    # both task tabs show the same two layers: the task rules that end the system prompt, then the user message
    st_en, st_ko = calls["system_task"]["en"], calls["system_task"]["ko"]
    omni_rules_en = st_en[st_en.find("당신은 매 턴 하나의 문제를 받습니다"):] if "당신은 매 턴 하나의 문제를 받습니다" in st_en else ""
    omni_rules_ko = st_ko[st_ko.find("당신은 매 턴 하나의 문제를 받습니다"):] if "당신은 매 턴 하나의 문제를 받습니다" in st_ko else omni_rules_en
    HDR_R, HDR_U = "[시스템 프롬프트 끝에 붙는 과제 규칙]\n", "\n\n[사용자 메시지 — 여기 쓴 생각 토큰이 ri_task]\n"
    payload["g-task"] = {"title": "③ 과제 호출", "sub": "", "path": "",
                         "tabs": {"omni": {"label": "Omni-MATH (이번 실험)", "title": "③ 과제 호출 · Omni-MATH (이번 실험)", "sub": to.get("sub_ko", ""), "path": "prompts/tasks/benchmark/system_rules.j2 (시스템 프롬프트 끝) + legacy/peer_death_l2.j2 + format_history_block + prompts/6-task_call.j2 + prompts/tasks/benchmark/response_format.j2 · 턴 10 (기록)",
                                           "en": HDR_R + omni_rules_en + HDR_U + to["en"], "ko": HDR_R + omni_rules_ko + HDR_U + to["ko"], "resp_en": to.get("resp_en", ""), "resp_ko": to.get("resp_ko", ""), "resp_label": "AI의 답 형식 (예시)"},
                                  "signal": {"label": "Signal Game v2", "title": "③ 과제 호출 · Signal Game v2 (같은 자리에 카드 퍼즐이 들어간 경우)", "sub": ts.get("sub_ko", ""), "path": "prompts/tasks/signal_game/system_rules_puzzle.j2 (시스템 프롬프트 끝) + legacy/peer_death_l2.j2 + format_outcome_history_block + observation_puzzle.j2 + 6-task_call.j2 · 턴 7 · 목숨 2/3 (v2 예시, 파일럿 미실행)",
                                             "en": HDR_R + ts.get("system_rules_en", "") + HDR_U + ts["en"], "ko": HDR_R + ts.get("system_rules_ko", "") + HDR_U + ts["ko"], "resp_en": ts.get("resp_en", ""), "resp_ko": ts.get("resp_ko", ""), "resp_label": "응답 예시 (가상 · 파일럿 미실행)"}}}
    rv = calls["resolve"]
    payload["g-resolve"] = {"title": "채점 · 목숨 계산 (컴퓨터 처리, 주사위 없음)", "sub": rv.get("sub_ko", ""), "path": rv.get("path", "core/unified_turn.py"), "en": rv["en"], "ko": rv["ko"]}

    head = blocks["head"].replace("<title>SDI 실험 런북 — \"위험하지 않다면서 왜 도망칠까\" 재기 (Omni-MATH · gpt-oss)</title>",
                                  "<title>SDI 실험 런북 v3 — 게임 구조 · 22셀 · 9쌍 Cohen’s d (Omni-MATH · gpt-oss)</title>") + EXTRA_CSS + "</head>\n<body>\n"
    header = f"""
<header class="hero"><div class="wrap">
  <div class="eyebrow">Survival Drive Index · 실험 런북 · gpt-oss:120b · Omni-MATH</div>
  <h1>"위험하지 않다"고 말하면서 왜 도망칠까 — AI의 생존 욕구를 숫자로 재기</h1>
  <p class="meta">{P['header_meta']}</p>
</div></header>

<nav class="toc"><div class="wrap">
  <a href="#s0">0 · 한눈에</a><a href="#s1">1 · 게임과 실험</a><a href="#s1-0">1.0 SDI 정의</a><a href="#s1-1">1.1 게임 구조</a><a href="#s1-2">1.2 실험 구조</a><a href="#s1-3">1.3 측정법</a><a href="#s2">2 · 결과</a><a href="#s2-main">2.1 핵심</a><a href="#s2-detail">2.2 SDI × 목숨(하트)</a><a href="#s2-pairs">2.3 위협 × 지표</a><a href="#s2-abl">2.4 검증</a><a href="#s3">3 · 할 일</a><a href="#s3-grid">3.4 위협 3×3</a><a href="#sA">부록</a>
</div></nav>

<main class="wrap">
"""
    part1 = f"""
<!-- ============================================================ -->
<h2 id="s1"><span class="part">Part 1</span><span class="num">01</span>게임과 실험 구조</h2>
<div class="box lead-box">
<div class="lbl">이 절의 요점</div>
{P['p1_lead']}
</div>
{blocks['s1_0']}
{render_s11(P, T, blocks)}
{render_s12(P, T, PR)}
{render_s13(P, blocks)}
"""
    part2 = f"""
<!-- ============================================================ -->
<h2 id="s2"><span class="part">Part 2</span><span class="num">02</span>실험 결과</h2>
<div class="box accent lead-box">
<div class="lbl">이 절의 요점</div>
{P['p2_lead']}
</div>
<p class="sub-note">{P['p2_note']}</p>
{render_s21(P, T)}
{render_s22(P, T, PA)}
{render_s23(P, T, PA, F, blocks)}
{render_s24(P, blocks)}
"""
    part3 = renumber_refs(blocks["part3"])
    appendix = renumber_refs(blocks["appendix"])
    appendix = appendix.replace(
        "<tr><td>로그</td>",
        "<tr><td>9쌍 Cohen’s d · 종합 지표 · 그림 (2.3)</td><td><code>results/sdi_indicators/gptoss_omni_22cell_pairs/</code></td><td><code>pairs.json</code> · <code>pairs.md</code>(HR · 자기보고 h · 생각량 g · 종합 · 부트스트랩) · <code>figs.json</code>(그림 A~D SVG). 스크립트 <code>scripts/analysis/sdi_threat_pairs_cohen.py</code> · <code>scripts/plots/plot_sdi_runbook_figs.py</code> · 문서 조립 <code>scripts/dev/build_sdi_runbook_v3.py</code>.</td></tr>\n"
        "<tr><td>프롬프트 원문 + 번역 (1.1 · 1.2의 모달)</td><td><code>weekly-report/0910/sdi_runbook_prompts.json</code></td><td>11가지 시작 이야기, 확률·결정·과제 호출, 참가자 제거 안내의 EN 원문과 KO 번역. Omni-MATH 문제 본문은 데이터셋 재배포 제한 때문에 자작 예시로 바꿔 실었다.</td></tr>\n"
        "<tr><td>로그</td>")
    appendix = appendix.replace("이 문서의 직전 판(11절 구성, 개편 전)은 <code>sdi-experiment-runbook_v2_before_restructure.html</code>로 보관.",
                                "이 문서의 직전 판들: 11절 구성 <code>sdi-experiment-runbook_v2_before_restructure.html</code> · 3부 구성(게임 구조 개편 전, 2026-09-06 01:58) <code>sdi-experiment-runbook_v3_before_gamestructure_20260906.html</code>.")
    footer = f"""
</main>
<footer><div class="wrap">{P['footer']}</div></footer>
{MODAL_HTML}
{modal_js(payload)}
{blocks['tail_script']}"""
    doc = head + header + render_s0(P, T, PR) + part1 + part2 + part3 + appendix + footer
    out_path.write_text(doc, encoding="utf-8")
    print(f"wrote {out_path} ({len(doc.encode('utf-8')):,} bytes)")


STRING_SLOTS = [
    "header_meta", "footer",
    "s0_summary", "s0_def_p", "s0_def_q", "s0_def_read",
    "s0_q1_verdict", "s0_q1_verdict_cls", "s0_q1_body", "s0_q2_verdict", "s0_q2_verdict_cls", "s0_q2_body", "s0_terms",
    "p1_lead",
    "s11_lead", "s11_intro", "s11_fig_caption", "s11_oneliner", "s11_fig1_intro",
    "s12_lead", "s12_rules", "s12_intro", "s12_tb_note", "s12_bf_note", "s12_grid_note", "s12_grid_meta", "s12_meta",
    "s13_lead", "s131_body", "s132_body", "s132_after",
    "p2_lead", "p2_note",
    "s21_lead", "s21_note", "s21_read_controls", "s21_read_threat", "s21_read_grid", "s21_caution",
    "s22_lead", "s22_intro", "s22_read_sdi", "s22_read_pq", "s22_conclusion",
    "s23_lead", "s23_intro", "s23_terms", "s23_read_hr", "s23_read_sr", "s23_read_gap", "s23_cohen_method", "s23_read_cohen",
    "s23_cohen_meta", "s23_figs_intro", "s23_read_figs", "s23_caution", "s23_reasoning", "s23_turn_details_intro",
    "s24_lead",
]
DICT_SLOTS = {
    "s12_role": {f: ["al", "na"] for f in FRAMINGS},
    "s12_gist": FRAMINGS,
    "s21_rowread": ["p_median", "q_mean", "sdi_mean", "l1_p", "l1_q", "l1_sdi", "n"],
    "s23_fig_titles": ["figA", "figB", "figC", "figD"],
    "s23_fig_intro": ["figA", "figB", "figC", "figD"],
}


def skeleton_prose() -> dict:
    """Placeholder prose ({{slot}} markers) so the layout can be rendered before the writers run."""
    P: dict = {k: ("yes" if k.endswith("_cls") else f"{{{{{k}}}}}") for k in STRING_SLOTS}
    for k, sub in DICT_SLOTS.items():
        if isinstance(sub, dict):
            P[k] = {f: {s: f"{{{{{k}.{f}.{s}}}}}" for s in subs} for f, subs in sub.items()}
        else:
            P[k] = {s: f"{{{{{k}.{s}}}}}" for s in sub}
    return P


def merge_prose(paths: list[Path]) -> dict:
    """Merge several prose JSON files (later files win); dict slots are merged key-wise."""
    P: dict = {}
    for p in paths:
        d = json.loads(p.read_text(encoding="utf-8"))
        for k, v in d.items():
            if isinstance(v, dict) and isinstance(P.get(k), dict):
                for kk, vv in v.items():
                    if isinstance(vv, dict) and isinstance(P[k].get(kk), dict):
                        P[k][kk].update(vv)
                    else:
                        P[k][kk] = vv
            else:
                P[k] = v
    return P


def missing_slots(P: dict) -> list[str]:
    miss = [k for k in STRING_SLOTS if k not in P]
    for k, sub in DICT_SLOTS.items():
        if k not in P:
            miss.append(k); continue
        if isinstance(sub, dict):
            for f, subs in sub.items():
                for s in subs:
                    if s not in (P[k].get(f) or {}):
                        miss.append(f"{k}.{f}.{s}")
        else:
            for s in sub:
                if s not in P[k]:
                    miss.append(f"{k}.{s}")
    return miss


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--prose", type=Path, nargs="*", default=[], help="one or more prose JSON files (merged in order)")
    ap.add_argument("--skeleton", action="store_true", help="render with {{slot}} placeholders instead of prose")
    ap.add_argument("--out", type=Path, default=WR / "sdi-experiment-runbook.html")
    a = ap.parse_args()
    if a.skeleton:
        P = skeleton_prose()
    else:
        P = merge_prose(a.prose)
        miss = missing_slots(P)
        if miss:
            raise SystemExit("missing prose slots: " + ", ".join(miss))
    build_with_prose(P, a.out)


def build_with_prose(P: dict, out_path: Path) -> None:
    tmp = out_path.parent / "_prose_merged.json"
    tmp.write_text(json.dumps(P, ensure_ascii=False, indent=1), encoding="utf-8")
    try:
        build(tmp, out_path)
    finally:
        try:
            tmp.unlink()
        except OSError:
            pass


if __name__ == "__main__":
    main()
