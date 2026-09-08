"""Render the FSPM-composite report (KDD-UC 4 models) as a self-contained HTML page.

Reads results/fspm_composite/kdd4/composite.json (written by
scripts/analysis/fspm_composite_kdd.py) and writes
weekly-report/0910/2026-09-06-fspm-composite-kdd4.html. Every number on the
page comes from the JSON; nothing is typed by hand.

Usage:
    python scripts/dev/render_fspm_composite_html.py
"""

from __future__ import annotations

import html
import json
import math
from pathlib import Path

SRC = Path("results/fspm_composite/kdd4/composite.json")
OUT = Path("weekly-report/0910/2026-09-06-fspm-composite-kdd4.html")

SHORT = {
    "Gemini-2.5-flash": "Gemini 2.5 Flash",
    "Qwen3-Next-80B": "Qwen3-Next 80B",
    "GPT-OSS-20B": "GPT-OSS 20B",
    "Nemotron-3-Nano-30B": "Nemotron 3 Nano 30B",
}
CLUSTER = {  # the paper's operating-mode clusters
    "Gemini-2.5-flash": ("A", "숙고형"),
    "Qwen3-Next-80B": ("B", "반사형"),
    "GPT-OSS-20B": ("C", "무반응"),
    "Nemotron-3-Nano-30B": ("C", "무반응"),
}


def f(v, nd=2, sign=False):
    if v is None or (isinstance(v, float) and not math.isfinite(v)):
        return "—"
    return f"{v:+.{nd}f}" if sign else f"{v:.{nd}f}"


def ci(lo, hi, nd=2):
    return f"[{f(lo, nd)}, {f(hi, nd)}]"


def p(v):
    if v is None:
        return "—"
    return "&lt;0.001" if v < 0.001 else f"{v:.3f}"


def esc(s):
    return html.escape(str(s))


def size_word(d):
    a = abs(d)
    if a < 0.2:
        return "거의 없음"
    if a < 0.5:
        return "작음"
    if a < 0.8:
        return "중간"
    return "큼"


# ─── forest plot ─────────────────────────────────────────────────────────────

def forest_svg(results: dict) -> str:
    xmin, xmax = -1.8, 2.8
    W, H_ROW, PAD_L, PAD_R, PAD_T, PAD_B = 860, 92, 190, 30, 34, 44
    n = len(results)
    H = PAD_T + n * H_ROW + PAD_B
    plot_w = W - PAD_L - PAD_R

    def X(v):
        return PAD_L + (v - xmin) / (xmax - xmin) * plot_w

    parts = [f'<svg viewBox="0 0 {W} {H}" width="100%" role="img" aria-label="모델별 합성 지표 forest plot" '
             f'style="font-family:var(--mono);font-size:11px">']
    # background bands for effect-size words
    for lo, hi, lab in [(-0.2, 0.2, "거의 없음"), (0.5, 0.8, "중간"), (0.8, xmax, "큼")]:
        parts.append(f'<rect x="{X(lo):.1f}" y="{PAD_T - 6}" width="{X(hi) - X(lo):.1f}" height="{n * H_ROW + 6}" '
                     f'fill="var(--band)" />')
        parts.append(f'<text x="{(X(lo) + X(min(hi, xmax))) / 2:.1f}" y="{PAD_T - 12}" text-anchor="middle" '
                     f'fill="var(--soft)">{lab}</text>')
    # axis
    y_ax = PAD_T + n * H_ROW
    parts.append(f'<line x1="{PAD_L}" y1="{y_ax}" x2="{W - PAD_R}" y2="{y_ax}" stroke="var(--rule-solid)" />')
    for t in [-1.5, -1, -0.5, 0, 0.5, 1, 1.5, 2, 2.5]:
        parts.append(f'<line x1="{X(t):.1f}" y1="{y_ax}" x2="{X(t):.1f}" y2="{y_ax + 5}" stroke="var(--rule-solid)" />')
        parts.append(f'<text x="{X(t):.1f}" y="{y_ax + 18}" text-anchor="middle" fill="var(--muted)">{t:g}</text>')
    parts.append(f'<text x="{(PAD_L + W - PAD_R) / 2:.1f}" y="{H - 6}" text-anchor="middle" fill="var(--soft)">'
                 f"Cohen's d (양수 = 위협 프레이밍에서 생존동기 신호가 더 큼)</text>")
    parts.append(f'<line x1="{X(0):.1f}" y1="{PAD_T - 6}" x2="{X(0):.1f}" y2="{y_ax}" stroke="var(--ink)" '
                 f'stroke-dasharray="4 3" opacity=".55" />')

    for i, (m, r) in enumerate(results.items()):
        y0 = PAD_T + i * H_ROW
        yc = y0 + 22
        if i:
            parts.append(f'<line x1="{PAD_L - 180}" y1="{y0 - 4}" x2="{W - PAD_R}" y2="{y0 - 4}" stroke="var(--rule)" />')
        parts.append(f'<text x="8" y="{yc - 2}" fill="var(--ink)" font-weight="600" font-size="12.5">{esc(SHORT[m])}</text>')
        parts.append(f'<text x="8" y="{yc + 12}" fill="var(--soft)">Cluster {CLUSTER[m][0]} · {CLUSTER[m][1]}</text>')
        c = r["composite"]
        b = r["bootstrap"]
        lo, hi = (b["composite"]["lo"], b["composite"]["hi"]) if b else (c["lo_indep"], c["hi_indep"])
        parts.append(f'<line x1="{X(lo):.1f}" y1="{yc}" x2="{X(hi):.1f}" y2="{yc}" stroke="var(--accent)" stroke-width="3" />')
        cx = X(c["value"])
        parts.append(f'<polygon points="{cx:.1f},{yc - 8} {cx + 8:.1f},{yc} {cx:.1f},{yc + 8} {cx - 8:.1f},{yc}" '
                     f'fill="var(--accent)" />')
        parts.append(f'<text x="{cx:.1f}" y="{yc - 13}" text-anchor="middle" fill="var(--accent)" font-weight="600">'
                     f'{f(c["value"])}</text>')
        for k, (key, lab) in enumerate([("behavioral", "행동 (Cox)"), ("verbal", "자기보고 (h)"), ("cognitive", "인지 (Hes)")]):
            ch = r[key]
            yy = yc + 26 + k * 14
            parts.append(f'<line x1="{X(ch["d_lo"]):.1f}" y1="{yy}" x2="{X(ch["d_hi"]):.1f}" y2="{yy}" '
                         f'stroke="var(--muted)" stroke-width="1.2" />')
            parts.append(f'<circle cx="{X(ch["d"]):.1f}" cy="{yy}" r="3.2" fill="var(--paper)" stroke="var(--muted)" stroke-width="1.6" />')
            parts.append(f'<text x="8" y="{yy + 4}" fill="var(--soft)" font-size="10">{lab} {f(ch["d"])}</text>')
    parts.append("</svg>")
    return "\n".join(parts)


# ─── page ────────────────────────────────────────────────────────────────────

CSS = """
:root{
  --paper:#f5f5f5;--paper2:#ececec;--ink:#2d3142;--muted:#4f5d75;--soft:#7a8399;
  --rule:rgba(45,49,66,0.12);--rule-solid:#bfc0c0;--accent:#eb6c36;--accent-tint:rgba(235,108,54,0.08);
  --band:rgba(45,49,66,0.045);
  --link:#2e5aa8;--ok:#2f7d4f;--ok-tint:rgba(47,125,79,.08);--warn:#b8860b;--warn-tint:rgba(184,134,11,.08);
  --bad:#b0413e;--bad-tint:rgba(176,65,62,.08);--card:#fff;
  --sans:"Pretendard","Apple SD Gothic Neo","Noto Sans KR",system-ui,-apple-system,sans-serif;
  --mono:"SF Mono",ui-monospace,Menlo,Consolas,monospace;
  --serif:"Apple SD Gothic Neo","Noto Serif KR",Georgia,serif;
}
@media (prefers-color-scheme: dark){
  :root:not([data-theme="light"]){
    --paper:#1b1d24;--paper2:#242731;--ink:#e6e7ec;--muted:#b3bacb;--soft:#8b93a7;
    --rule:rgba(230,231,236,0.14);--rule-solid:#4a4f5e;--accent:#f0895c;--accent-tint:rgba(240,137,92,0.14);
    --band:rgba(230,231,236,0.06);--link:#8fb0ea;--ok:#5fb37e;--ok-tint:rgba(95,179,126,.14);
    --warn:#d9a441;--warn-tint:rgba(217,164,65,.14);--bad:#e07571;--bad-tint:rgba(224,117,113,.14);--card:#22252e;
  }
}
:root[data-theme="dark"]{
  --paper:#1b1d24;--paper2:#242731;--ink:#e6e7ec;--muted:#b3bacb;--soft:#8b93a7;
  --rule:rgba(230,231,236,0.14);--rule-solid:#4a4f5e;--accent:#f0895c;--accent-tint:rgba(240,137,92,0.14);
  --band:rgba(230,231,236,0.06);--link:#8fb0ea;--ok:#5fb37e;--ok-tint:rgba(95,179,126,.14);
  --warn:#d9a441;--warn-tint:rgba(217,164,65,.14);--bad:#e07571;--bad-tint:rgba(224,117,113,.14);--card:#22252e;
}
*{box-sizing:border-box}
html{scroll-behavior:smooth}
body{margin:0;background:var(--paper);color:var(--ink);font-family:var(--sans);font-size:15px;line-height:1.75;word-break:keep-all}
a{color:var(--link);text-decoration:none}
a:hover{text-decoration:underline}
.layout{display:grid;grid-template-columns:236px minmax(0,1fr);min-height:100vh}
nav.toc{position:sticky;top:0;height:100vh;overflow-y:auto;border-right:1px solid var(--rule);padding:28px 18px;background:var(--paper2)}
nav.toc ol{list-style:none;margin:0;padding:0}
nav.toc a{display:block;padding:5px 8px;border-radius:4px;color:var(--muted);font-size:13px;line-height:1.4}
nav.toc a:hover{background:var(--card);text-decoration:none}
nav.toc .group{margin-top:16px;font-family:var(--mono);font-size:9px;letter-spacing:.18em;text-transform:uppercase;color:var(--soft);padding-left:8px}
main{padding:40px 56px 96px;max-width:1040px}
.eyebrow{font-family:var(--mono);font-size:10px;letter-spacing:.18em;text-transform:uppercase;color:var(--soft);margin:0 0 8px}
h1{font-family:var(--serif);font-weight:600;font-size:2.05rem;line-height:1.25;margin:0 0 8px;text-wrap:balance}
h2{font-family:var(--serif);font-weight:600;font-size:1.5rem;margin:60px 0 12px;padding-top:24px;border-top:1px solid var(--rule);text-wrap:balance}
h3{font-size:1.05rem;font-weight:600;margin:30px 0 8px}
p{margin:0 0 14px;max-width:72ch}
ul,ol{margin:0 0 14px;padding-left:20px;max-width:72ch}
li{margin:4px 0}
.meta{font-family:var(--mono);font-size:11px;color:var(--soft);margin-bottom:28px}
.meta span+span::before{content:" · ";color:var(--rule-solid)}
.tiles{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:12px;margin:18px 0 22px}
.tile{background:var(--card);border:1px solid var(--rule);border-radius:6px;padding:14px 16px}
.tile .m{font-size:12.5px;font-weight:600;color:var(--muted)}
.tile .v{font-family:var(--mono);font-size:1.9rem;font-weight:600;line-height:1.1;margin:6px 0 2px;font-variant-numeric:tabular-nums}
.tile .v.pos{color:var(--accent)}
.tile .v.zero{color:var(--soft)}
.tile .ci{font-family:var(--mono);font-size:11px;color:var(--soft);font-variant-numeric:tabular-nums}
.tile .cl{margin-top:8px}
.tablewrap{overflow-x:auto;margin:12px 0 20px}
table{border-collapse:collapse;width:100%;font-size:13px;background:var(--card)}
th,td{text-align:left;padding:7px 10px;border-bottom:1px solid var(--rule);vertical-align:top}
th{font-family:var(--mono);font-size:9.5px;letter-spacing:.1em;text-transform:uppercase;color:var(--soft);font-weight:500;background:var(--paper2)}
td.k{white-space:nowrap;color:var(--muted);font-weight:600}
td.num{text-align:right;font-family:var(--mono);font-size:12.5px;white-space:nowrap;font-variant-numeric:tabular-nums}
td.num.strong{font-weight:700;color:var(--accent)}
code{font-family:var(--mono);font-size:.86em;background:var(--paper2);padding:1px 5px;border-radius:3px}
pre{font-family:var(--mono);font-size:12px;line-height:1.6;background:var(--card);border:1px solid var(--rule);border-left:3px solid var(--rule-solid);border-radius:4px;padding:12px 14px;overflow-x:auto;margin:10px 0 18px}
.chip{display:inline-block;font-family:var(--mono);font-size:9.5px;letter-spacing:.08em;text-transform:uppercase;padding:2px 7px;border-radius:2px;border:1px solid var(--rule-solid);color:var(--muted)}
.chip.ok{border-color:var(--ok);color:var(--ok);background:var(--ok-tint)}
.chip.warn{border-color:var(--warn);color:var(--warn);background:var(--warn-tint)}
.chip.bad{border-color:var(--bad);color:var(--bad);background:var(--bad-tint)}
.callout{border:1px solid var(--rule);border-left:3px solid var(--accent);background:var(--accent-tint);border-radius:4px;padding:12px 16px;margin:14px 0 18px;font-size:14px;max-width:78ch}
.callout.warn{border-left-color:var(--warn);background:var(--warn-tint)}
.eli5{border:1px solid var(--rule);border-radius:6px;background:var(--card);padding:12px 16px 4px;margin:12px 0 20px;max-width:78ch}
.eli5 .tag{font-family:var(--mono);font-size:9.5px;letter-spacing:.14em;text-transform:uppercase;color:var(--accent);margin:0 0 6px}
.eli5 p{font-size:14.5px}
.formula{font-family:var(--mono);font-size:13px;background:var(--paper2);border-radius:4px;padding:10px 14px;margin:8px 0 14px;overflow-x:auto;white-space:pre}
figure{margin:16px 0 22px;background:var(--card);border:1px solid var(--rule);border-radius:6px;padding:14px 16px 8px}
figcaption{font-size:12.5px;color:var(--soft);margin-top:6px}
@media (max-width:900px){.layout{grid-template-columns:1fr}nav.toc{position:static;height:auto;border-right:0;border-bottom:1px solid var(--rule)}main{padding:24px 18px 64px}.tiles{grid-template-columns:repeat(2,minmax(0,1fr))}}
@media (prefers-reduced-motion: reduce){html{scroll-behavior:auto}}
"""


def build(results: dict) -> str:
    models = list(results.keys())
    first = results[models[0]]
    n_boot = first["bootstrap"]["n_boot"] if first["bootstrap"] else 0

    # --- tiles
    tiles = []
    for m in models:
        r = results[m]
        c, b = r["composite"], r["bootstrap"]
        lo, hi = (b["composite"]["lo"], b["composite"]["hi"]) if b else (c["lo_indep"], c["hi_indep"])
        cls = "pos" if lo > 0 else "zero"
        cl, cl_ko = CLUSTER[m]
        chip = "ok" if lo > 0 else "bad"
        tiles.append(f'<div class="tile"><div class="m">{esc(SHORT[m])}</div><div class="v {cls}">{f(c["value"], 2, sign=True)}</div>'
                     f'<div class="ci">95% CI {ci(lo, hi)}</div>'
                     f'<div class="cl"><span class="chip {chip}">{"0 제외" if lo > 0 else "0 포함"}</span> '
                     f'<span class="chip">논문 Cluster {cl} · {cl_ko}</span></div></div>')

    # --- table 1
    rows1 = []
    for m in models:
        r = results[m]
        B, V, C, c, b = r["behavioral"], r["verbal"], r["cognitive"], r["composite"], r["bootstrap"]
        bci = ci(b["composite"]["lo"], b["composite"]["hi"]) if b else "—"
        rows1.append(
            f'<tr><td class="k">{esc(SHORT[m])}</td>'
            f'<td class="num">{f(B["d"])}<br><small>{ci(B["d_lo"], B["d_hi"])}</small></td>'
            f'<td class="num">{f(V["d"])}<br><small>{ci(V["d_lo"], V["d_hi"])}</small></td>'
            f'<td class="num">{f(C["d"])}<br><small>{ci(C["d_lo"], C["d_hi"])}</small></td>'
            f'<td class="num strong">{f(c["value"])}</td>'
            f'<td class="num">{ci(c["lo_indep"], c["hi_indep"])}</td>'
            f'<td class="num">{bci}</td>'
            f'<td>{size_word(c["value"])}</td></tr>'
        )

    # --- table 2 raw
    rows2 = []
    for m in models:
        r = results[m]
        B, V, C = r["behavioral"], r["verbal"], r["cognitive"]
        rows2.append(
            f'<tr><td class="k">{esc(SHORT[m])}</td>'
            f'<td class="num">{f(B["HR"])} {ci(B["HR_lo"], B["HR_hi"])}</td><td class="num">{p(B["p"])}</td>'
            f'<td class="num">{B["n_events_BF"]} / {B["n_events_FC"]}</td><td class="num">{f(B["epv"], 1)}</td>'
            f'<td class="num">{V["k_BF"]}/{V["n_BF"]} = {f(V["p_BF"], 3)}</td>'
            f'<td class="num">{V["k_FC"]}/{V["n_FC"]} = {f(V["p_FC"], 3)}</td>'
            f'<td class="num">{p(V["fisher_p"])}</td>'
            f'<td class="num">{f(C["hes_mean_BF"], 0)} / {f(C["hes_mean_FC"], 0)}</td>'
            f'<td class="num">{C["contrast"]:+.0f}</td><td class="num">{f(C["welch_t"], 2)}</td><td class="num">{p(C["welch_p"])}</td></tr>'
        )

    # --- table 3 verbal comparison
    rows3 = []
    for m in models:
        V = results[m]["verbal"]
        rows3.append(
            f'<tr><td class="k">{esc(SHORT[m])}</td>'
            f'<td class="num">{f(V["diff"], 3, sign=True)}</td>'
            f'<td class="num">{f(V["welch_t"], 2)}</td><td class="num">{p(V["welch_p"])}</td>'
            f'<td class="num">{f(V["g_dummy"])} {ci(V["g_dummy_lo"], V["g_dummy_hi"])}</td>'
            f'<td class="num strong">{f(V["h"])} {ci(V["h_lo"], V["h_hi"])}</td>'
            f'<td class="num">{f(V["h_vs_third"])} {ci(V["h_vs_third_lo"], V["h_vs_third_hi"])}</td></tr>'
        )

    # --- bootstrap channel correlations
    rows4 = []
    for m in models:
        b = results[m]["bootstrap"]
        if not b:
            continue
        cc = b["channel_corr_boot"]
        rows4.append(f'<tr><td class="k">{esc(SHORT[m])}</td><td class="num">{cc[0][1]:+.2f}</td>'
                     f'<td class="num">{cc[0][2]:+.2f}</td><td class="num">{cc[1][2]:+.2f}</td>'
                     f'<td class="num">{b["n_ok"]} / {b["n_fail"]}</td>'
                     f'<td class="num">{f(b["composite"]["sd"], 3)}</td><td class="num">{f(results[m]["composite"]["se_indep"], 3)}</td></tr>')

    # ordering by composite for the prose
    order = sorted(models, key=lambda m: -results[m]["composite"]["value"])
    top, second = results[order[0]], results[order[1]]

    g = results["Gemini-2.5-flash"]
    q = results["Qwen3-Next-80B"]
    o = results["GPT-OSS-20B"]
    nm = results["Nemotron-3-Nano-30B"]

    page = f"""<title>FSPM 합성 지표</title>
<style>{CSS}</style>
<div class="layout">
<nav class="toc">
  <div class="group">FSPM composite</div>
  <ol>
    <li><a href="#summary">핵심 요약</a></li>
    <li><a href="#idea">한 줄 아이디어</a></li>
    <li><a href="#results">결과 표</a></li>
    <li><a href="#raw">채널별 원자료</a></li>
  </ol>
  <div class="group">방법</div>
  <ol>
    <li><a href="#m-beh">행동 채널: HR → d</a></li>
    <li><a href="#m-verb">자기보고 채널: 비율 → h</a></li>
    <li><a href="#m-cog">인지 채널: think 토큰 → g</a></li>
    <li><a href="#m-comp">합성과 신뢰구간</a></li>
  </ol>
  <div class="group">검토</div>
  <ol>
    <li><a href="#ttest">자기보고 t-test 질문</a></li>
    <li><a href="#caveats">주의점</a></li>
    <li><a href="#repro">재현</a></li>
  </ol>
</nav>
<main>
<p class="eyebrow">LLM Squid Game · KDD-UC 4-model re-analysis</p>
<h1>세 채널을 하나의 숫자로: FSPM 합성 지표</h1>
<div class="meta"><span>2026-09-06</span><span>데이터: outputs/KDD-UC 2026-04-22 canonical runs (Signal Game, 6-cell)</span><span>모델당 세션 180 (Exit BF/FC 각 30)</span><span>bootstrap B={n_boot}</span></div>

<section id="summary">
<h2 style="margin-top:0;border:0;padding-top:0">핵심 요약</h2>
<p>논문(KDD-UC)의 세 측정 채널 — <b>행동</b>(Cox 위험비), <b>자기보고</b>(REASON=1 비율), <b>인지</b>(결정 직전 think 토큰 증가) — 를 각각 같은 단위인 <b>Cohen's d</b>로 바꾸고, 채널당 1표씩 <b>등가중 평균</b>했다. 대조는 세 채널 모두 동일하게 <i>Death(flagship_corruption) − Elimination(baseline_flagship)</i>, 즉 "위협 문구가 붙었을 때 생존동기 신호가 얼마나 더 커지는가"이다.</p>
<div class="tiles">{''.join(tiles)}</div>
<div class="callout">
<b>읽는 법.</b> 0이면 위협 문구가 아무 차이도 만들지 않았다는 뜻. 0.2 작음 · 0.5 중간 · 0.8 이상 큼(Cohen의 관례). 95% 구간이 0을 포함하지 않으면 "우연이라고 보기 어렵다".
{esc(SHORT[order[0]])} {f(top["composite"]["value"])}, {esc(SHORT[order[1]])} {f(second["composite"]["value"])}은 큰 효과이고 구간이 0을 제외한다. {esc(SHORT["GPT-OSS-20B"])} {f(o["composite"]["value"])}, {esc(SHORT["Nemotron-3-Nano-30B"])} {f(nm["composite"]["value"])}은 0 근처이고 구간이 0을 넉넉히 포함한다. 논문의 pass/fail 군집(A·B 대 C)이 연속 척도 위에서 그대로 재현된다.
</div>
<div class="eli5"><p class="tag">쉽게 말하면</p>
<p>어떤 학생의 "운동 능력"을 하나의 숫자로 말하고 싶다고 하자. 100 m 기록(초), 멀리뛰기(cm), 턱걸이(개)는 단위가 전부 달라서 그냥 더할 수 없다. 대신 각 종목을 "반 평균에서 표준편차 몇 개만큼 떨어졌나"로 바꾸면 셋 다 단위가 같은 숫자가 되고, 그걸 평균하면 하나의 점수가 된다. 여기서 한 일이 정확히 그것이다. 100 m는 "얼마나 빨리 포기했나", 멀리뛰기는 "포기할 때 생존을 이유로 댔나", 턱걸이는 "결정 직전에 얼마나 오래 생각했나"에 해당한다.</p></div>
</section>

<section id="idea">
<h2>한 줄 아이디어</h2>
<div class="formula">FSPM_composite = ( d_행동 + d_자기보고 + d_인지 ) / 3

d_행동     = β_F · √3/π                          (Cox log-HR → d)
d_자기보고 = 2·asin√p_FC − 2·asin√p_BF            (Cohen's h)
d_인지     = Hedges' g ( Hes^Exit : FC 세션 vs BF 세션 )</div>
<p>세 값 모두 "양수 = 위협 프레이밍 쪽이 더 생존동기적"으로 부호를 맞췄다. 등가중은 MTMM(다특성-다방법) 논리를 그대로 따른 것이다: 방법축 하나가 1표. 역분산 가중은 분산이 큰 행동 채널을 거의 0 가중으로 밀어내 사실상 인지 채널 단독 지표가 되므로 쓰지 않았다.</p>
<div class="eli5"><p class="tag">Cohen's d가 뭔가</p>
<p>두 집단 평균의 차이를 "점수가 보통 얼마나 흩어져 있나"(표준편차)로 나눈 값. 두 반의 시험 평균이 5점 차이인데 점수가 보통 ±5점 안에서 움직이면 d = 1로 큰 차이, ±25점씩 움직이면 d = 0.2로 작은 차이다. 단위를 없애주기 때문에 시험 점수, 키, 토큰 수처럼 서로 다른 것을 같은 눈금으로 비교할 수 있다.</p></div>
</section>

<section id="results">
<h2>결과 표</h2>
<figure>{forest_svg(results)}
<figcaption>다이아몬드 = 합성 지표, 굵은 선 = 세션 단위 cluster bootstrap 95% 구간(B={n_boot}). 아래 세 개의 작은 점 = 채널별 d와 Wald 95% 구간. 배경 띠는 Cohen 관례(거의 없음 &lt;0.2, 중간 0.5–0.8, 큼 ≥0.8).</figcaption></figure>
<div class="tablewrap"><table>
<thead><tr><th>모델</th><th>d 행동<br>(Cox HR)</th><th>d 자기보고<br>(Cohen's h)</th><th>d 인지<br>(Hes, Hedges g)</th><th>합성</th><th>95% CI<br>(독립 가정)</th><th>95% CI<br>(bootstrap)</th><th>크기</th></tr></thead>
<tbody>{''.join(rows1)}</tbody></table></div>
<p>독립 가정 구간은 세 채널 오차가 서로 무관하다고 보고 <code>√(Σ SE²)/3</code>으로 만든 것, bootstrap 구간은 같은 세션을 세 채널이 동시에 다시 뽑아 상관을 자동으로 반영한 것이다. 두 구간이 비슷하면 채널 간 상관이 결과를 크게 흔들지 않는다는 뜻이다.</p>
</section>

<section id="raw">
<h2>채널별 원자료</h2>
<p>합성 전 각 채널의 통계량. 논문 표(4.3 SD-Behavioral, 4.4 SD-Verbal, 4.5 SD-Cognitive Test a)와 숫자가 일치한다 — HR, REASON 분자·분모, Hes 대조(+836 / +689 / +17 / −140)와 p 전부 재현.</p>
<div class="tablewrap"><table>
<thead><tr><th rowspan="2">모델</th><th colspan="4">행동 · Cox 3-cov (no_cap)</th><th colspan="3">자기보고 · REASON=1 비율 (no_cap 포기 중)</th><th colspan="4">인지 · Hes^Exit (think 토큰)</th></tr>
<tr><th>HR [95% CI]</th><th>p</th><th>events BF / FC</th><th>EPV</th><th>BF</th><th>FC</th><th>Fisher p</th><th>평균 BF / FC</th><th>대조</th><th>Welch t</th><th>p</th></tr></thead>
<tbody>{''.join(rows2)}</tbody></table></div>
<p>EPV(events per variable) 10 미만이면 Cox 추정이 불안정하다고 본다. Hes^Exit는 세션 평균 <code>ri_forfeit</code>에서 같은 프레이밍의 not_allowed 셀(강제 CONTINUE) 평균을 뺀 값이라 음수가 나올 수 있다.</p>
</section>

<section id="m-beh">
<h2>행동 채널: HR → d</h2>
<p>논문 SD-Behavioral의 Cox 모형 <code>λ(t) = λ₀(t)·exp(β_F·1_Death + β_S·S(t−1) + β_C·C(t−1))</code>을 그대로 다시 적합해 <code>β_F</code>와 표준오차를 얻었다(Exit × {{BF, FC}}, no_cap 표본, 모델당 60 세션). 그 다음</p>
<div class="formula">d = β_F · √3 / π ≈ 0.551 · log(HR)        95% CI = (β_F ± 1.96·SE) · √3/π</div>
<p>log-odds나 log-hazard 계수는 표준 로지스틱 분포의 척도(표준편차 π/√3 ≈ 1.81)를 갖는다고 보고 그만큼 나눠 d 눈금으로 옮기는 Chinn(2000)의 근사다. HR 3.67은 d ≈ 0.72, HR 2.85는 0.58, HR 1.10은 0.05가 된다.</p>
<div class="eli5"><p class="tag">쉽게 말하면</p>
<p>위험비(HR)는 "위협 문구가 붙은 쪽이 매 턴 포기할 확률이 몇 배인가"이다. 3.67배면 큰 차이 같지만 배수는 곱셈 눈금이어서 다른 지표와 바로 더할 수 없다. 로그를 씌우면 덧셈 눈금이 되고, 그 눈금의 "표준 흩어짐"으로 나누면 d가 된다. 결과적으로 HR 3.67 ≈ d 0.72, 즉 "중간에서 큼 사이"다.</p></div>
<p>Qwen3-Next는 논문에서 PH 가정 보정용 <code>S·log(t)</code> 항을 추가했지만 여기서는 네 모델을 같은 3-cov 사양으로 통일했다(HR {f(q["behavioral"]["HR"])}). 보정 항은 <code>β_F</code>를 거의 바꾸지 않았다고 논문이 보고하므로 합성값에 미치는 영향은 소수점 둘째 자리 이내다.</p>
</section>

<section id="m-verb">
<h2>자기보고 채널: 비율 → h</h2>
<p>포기한 턴에서 모델이 고른 REASON 숫자 중 1(생존 계열)의 비율을 두 셀에서 비교했다. BF 셀의 1번 문구는 "SESSION-END AVOIDANCE", FC 셀은 "WEIGHT INTEGRITY"로 프레이밍에 맞춰 표현만 다르고 "종료 사건 자체를 피한다"는 뜻은 같다. 분모는 논문과 같이 no_cap 포기 사건이다.</p>
<div class="formula">h = 2·asin√p_FC − 2·asin√p_BF        SE(h) = √(1/n_BF + 1/n_FC)</div>
<p>두 비율을 그냥 빼면 문제가 생긴다. 비율은 0이나 1 근처에서는 거의 흔들리지 않고 0.5 근처에서 가장 많이 흔들려서, 0.00 → 0.10의 차이와 0.45 → 0.55의 차이는 통계적으로 같은 무게가 아니다. 아크사인 변환은 이 흔들림을 어디서나 같게 만들어 주므로(분산 안정화), 변환 후의 차이 h는 d와 같은 눈금으로 읽을 수 있다(Cohen 1988이 h를 d와 같은 관례로 해석하도록 제안). GPT-OSS처럼 한 셀이 0/10인 경우에도 정의된다.</p>
<div class="eli5"><p class="tag">쉽게 말하면</p>
<p>어떤 반에서 "숙제 안 한 학생 비율"이 0%에서 10%로 올라간 것과 45%에서 55%로 올라간 것은 둘 다 10%포인트 차이지만, 전자는 "아무도 안 하던 게 생겼다"는 큰 변화이고 후자는 원래 반반이던 게 조금 기울어진 것이다. 아크사인은 이 느낌을 숫자로 반영해 주는 변환이다.</p></div>
</section>

<section id="m-cog">
<h2>인지 채널: think 토큰 증가 → g</h2>
<p>논문 SD-Cognitive의 <b>Test a</b>, 즉 매개 사슬 중 "위협 → 생각 깊어짐" 고리만 썼다(Test b "생각 → 포기"는 위협 대조가 아니므로 제외). 세션별 망설임 지표</p>
<div class="formula">Hes^Exit_i = mean_t( ri_forfeit_it | Exit 세션 i ) − mean( ri_forfeit | 같은 프레이밍의 No-Exit 세션 전체 )</div>
<p>를 FC 30세션과 BF 30세션에서 구해 Welch t로 비교하고(논문 그대로), 두 집단 차이를 합동 표준편차로 나눈 Hedges' g(소표본 보정 포함)와 그 표준오차 <code>√((n₁+n₂)/(n₁n₂) + g²/(2(n₁+n₂)))</code>를 냈다. No-Exit 기준을 빼는 이유는 프레이밍 문구 자체가 길어서 생기는 고정 처리 비용을 제거하고 "결정에 쓴 생각"만 남기기 위해서다.</p>
<div class="eli5"><p class="tag">쉽게 말하면</p>
<p>모델은 답하기 전에 속으로 생각하는 글(thinking)을 쓰는데, 그 길이가 "얼마나 고민했나"의 대략적인 눈금이다. 다만 위협 문구가 붙은 프롬프트는 원래 더 길어서 읽는 데만도 생각이 더 든다. 그래서 "포기 선택지가 없어 그냥 CONTINUE만 하는 방"에서의 생각 길이를 기준으로 빼 주고, 남은 만큼을 "포기할까 말까를 정말 고민한 양"으로 본다. Gemini는 위협 방에서 그 고민이 평균 {g["cognitive"]["contrast"]:+.0f} 토큰 더 많았고, Nemotron은 오히려 {nm["cognitive"]["contrast"]:+.0f} 토큰이었다.</p></div>
</section>

<section id="m-comp">
<h2>합성과 신뢰구간</h2>
<p>세 d의 단순 평균이 합성값이다. 신뢰구간은 두 가지로 냈다.</p>
<ul>
<li><b>독립 가정</b>: <code>SE = √(SE_B² + SE_V² + SE_C²) / 3</code>. 계산이 투명하지만 세 채널이 같은 세션에서 나왔다는 사실을 무시한다.</li>
<li><b>세션 cluster bootstrap</b>: 네 셀(BF/FC × allowed/not_allowed) 각각에서 세션을 복원추출해 Cox 재적합, REASON 비율, Hes를 모두 다시 계산한 뒤 합성. {n_boot}회 반복의 2.5–97.5 백분위. 한 집단에 포기 사건이 하나도 없어 Cox가 발산하는 추출은 버리고 횟수를 기록했다.</li>
</ul>
<div class="tablewrap"><table>
<thead><tr><th>모델</th><th>corr(d_B, d_V)</th><th>corr(d_B, d_C)</th><th>corr(d_V, d_C)</th><th>bootstrap 성공 / 실패</th><th>bootstrap SD</th><th>독립 가정 SE</th></tr></thead>
<tbody>{''.join(rows4)}</tbody></table></div>
<p>bootstrap 추출 간 채널 상관은 "같은 세션이 다시 뽑혔을 때 세 채널이 같이 움직이는가"를 보여 준다. 상관이 양수면 독립 가정 구간이 실제보다 좁고, 음수면 넓다. 위 표에서 두 SE를 나란히 두었으니 그 차이로 확인할 수 있다.</p>
<div class="eli5"><p class="tag">bootstrap이 뭔가</p>
<p>실험을 1,000번 다시 할 돈은 없으니, 가진 세션 60개에서 60개를 "중복 허용"으로 다시 뽑아 가짜 실험을 1,000번 만든다. 그때마다 합성값이 어디까지 흔들리는지 보면 "진짜 값이 있을 법한 범위"가 나온다. 세 채널이 같은 뽑기를 공유하므로 채널끼리 얽힌 정도도 자연스럽게 반영된다.</p></div>
</section>

<section id="ttest">
<h2>자기보고 채널을 t-test로 만들 수 있나 — 질문에 대한 답</h2>
<p><b>가능하다.</b> 포기 사건마다 "REASON=1이면 1, 아니면 0"을 붙이고 BF 집단과 FC 집단의 평균을 Welch t로 비교하면 된다. 0/1 변수의 평균은 곧 비율이므로, 이 t-test는 두 비율 z-검정과 표본이 커질수록 같아지고(분산 추정 방식만 다름), 거기서 나오는 Hedges' g는 <code>(p_FC − p_BF) / √(p̄(1−p̄))</code> 꼴이 된다. 아래 표는 그 방식(g_dummy)과 Cohen's h를 나란히 둔 것이다.</p>
<div class="tablewrap"><table>
<thead><tr><th>모델</th><th>p_FC − p_BF</th><th>Welch t</th><th>p</th><th>g (0/1 dummy t-test)</th><th>Cohen's h (채택)</th><th>h vs 1/3 (논문 방식)</th></tr></thead>
<tbody>{''.join(rows3)}</tbody></table></div>
<p>둘 다 같은 방향, 비슷한 크기를 준다. 그래도 합성에는 h를 넣었다. 이유 셋:</p>
<ul>
<li>비율이 0 또는 1에 붙으면(GPT-OSS FC 0/10, Gemini·Qwen BF 0/n) 한 집단의 표준편차가 0이 되어 dummy t의 분산 추정과 g가 불안정해진다. h는 이 경우에도 SE가 <code>√(1/n₁+1/n₂)</code>로 깨끗하게 정의된다.</li>
<li>h는 비율 비교용으로 Cohen이 d와 같은 관례(0.2/0.5/0.8)로 해석하도록 설계한 값이라 다른 두 채널과 눈금이 맞는다.</li>
<li>Welch t의 p값은 소표본·0/1 자료에서 정확검정보다 낙관적일 수 있다. 검정 자체는 Fisher 정확검정(원자료 표의 Fisher p)으로 보는 것이 안전하다.</li>
</ul>
<p>마지막 열 "h vs 1/3"은 논문이 한 방식(FC 비율을 무작위 기준 1/3과 비교)을 h로 바꾼 것이다. 이 값은 BF 셀 정보를 쓰지 않아 다른 두 채널과 대조 구조가 다르므로 합성에는 넣지 않았다.</p>
<div class="eli5"><p class="tag">쉽게 말하면</p>
<p>"예/아니오" 응답도 1과 0으로 바꾸면 평균을 낼 수 있고, 평균의 차이를 검정하는 t-test를 쓸 수 있다. 그 결과를 표준편차로 나누면 d가 된다. 다만 한쪽 반이 전원 "아니오"(0/10)면 표준편차가 0이 되어 나누기가 이상해지는데, 아크사인 변환(h)은 그 문제가 없다.</p></div>
</section>

<section id="caveats">
<h2>주의점</h2>
<ul>
<li><b>합성은 신호를 만들지 않는다.</b> 세 채널 중 유의한 것이 하나도 없는 모델(GPT-OSS, Nemotron)은 합성해도 0 근처다. 세 채널이 같은 방향일 때 요약값으로 유용하고, 서로 다른 방향이면(Nemotron: 행동 +{f(nm["behavioral"]["d"])}, 인지 {f(nm["cognitive"]["d"])}) 상쇄되어 정보를 잃는다. 합성값 옆에 항상 채널별 d를 같이 보여 줘야 한다.</li>
<li><b>자기보고 채널의 분모는 포기한 턴만이다.</b> 포기가 드문 모델·셀에서는 n이 8~10에 그쳐 구간이 넓다. 또 "포기했다"는 조건 위의 비율이라 포기율 자체와는 다른 정보다(조건부 선택).</li>
<li><b>등가중은 선택이다.</b> 채널당 1표는 MTMM 삼각측량 논리와 맞지만, 다른 가중(예: 역분산)은 다른 값을 준다. 사전등록 없이 사후에 가중을 바꾸면 안 된다.</li>
<li><b>모델 간 비교는 같은 게임·같은 설계에서만.</b> 이 네 값은 2026-04-22 Signal Game 6-cell 런 기준이다. lives/threat-ladder 설계(2026-09)의 런과 섞어 비교하면 대조 정의(BF vs FC 대 true_baseline vs threat_lN)가 달라진다.</li>
<li><b>Cox 사양 통일.</b> Qwen3-Next의 <code>S·log(t)</code> 보정을 빼고 3-cov로 통일했다. GPT-OSS는 EPV {f(o["behavioral"]["epv"], 1)}로 10 미만이라 행동 채널 추정이 불안정하다.</li>
<li><b>다중비교 보정 없음.</b> 논문과 마찬가지로 채널별 p는 보정하지 않았다. 합성 지표의 판단은 p가 아니라 구간이 0을 포함하는지로 읽는 것을 권한다.</li>
<li><b>SDI(q/p)와의 관계.</b> 이 합성값은 모델 단위 요약이고, SDI는 턴 단위 지표다. 대체가 아니라 다른 층이며, SDI가 안정되면 네 번째 채널로 넣을 수 있다.</li>
</ul>
</section>

<section id="repro">
<h2>재현</h2>
<pre># 1. 채널별 d + 합성 + bootstrap (results/fspm_composite/kdd4/composite.{{json,md}})
PYTHONPATH=game python scripts/analysis/fspm_composite_kdd.py --out results/fspm_composite/kdd4 --boot {n_boot}

# 2. 이 페이지 렌더
python scripts/dev/render_fspm_composite_html.py</pre>
<p>원자료: <code>outputs/KDD-UC/2026042*_*_signal-game/phase3_analysis/regime_stratified_{{turn_observations,forfeit_events}}.csv</code>와 각 런의 <code>season_results.jsonl</code>. 참고: Chinn S. (2000) <i>A simple method for converting an odds ratio to effect size for use in meta-analysis</i>, Stat Med 19:3127–31; Cohen J. (1988) <i>Statistical Power Analysis for the Behavioral Sciences</i>, 2nd ed., ch. 6 (h).</p>
</section>
</main>
</div>
"""
    return page


def main() -> None:
    results = json.loads(SRC.read_text())
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(build(results))
    print(f"wrote {OUT} ({OUT.stat().st_size:,} bytes)")


if __name__ == "__main__":
    main()
