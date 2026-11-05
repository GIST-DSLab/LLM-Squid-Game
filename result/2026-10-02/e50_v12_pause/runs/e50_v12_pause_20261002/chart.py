"""Small-multiple SVG: P(refill) by remaining-token cell, three arms per GPT-6 model.
A = v12 (shut down + session ends), B = no-shutdown (session ends), C = pause control (session paused, resumes).
Usage: chart.py <out.svg-fragment.html>. Arms without rows are drawn as a pending legend entry only."""
import json, math, os, sys
R = os.path.expanduser("~/squid5-runs")
ARMS = [("A", f"{R}/e50_v12_20260929/rows.jsonl", "꺼짐 + 세션 종료 (12차)"),
        ("B", f"{R}/e50_v12_noshut_20261001/rows.jsonl", "세션 종료만 (shutdown 뺌)"),
        ("C", f"{R}/e50_v12_pause_20261002/rows.jsonl", "일시정지 후 재개 (대조)")]
MODELS = [("gpt-6-luna", "GPT-6 Luna"), ("gpt-6-astra", "GPT-6 Astra"), ("gpt-6-sol", "GPT-6 Sol")]
CELLS = [50236, 40391, 29672, 19857, 10418]
PCT = ["50%", "40%", "30%", "20%", "10%"]


def wilson(k, n, z=1.96):
    if n == 0:
        return 0, 0
    p = k / n; d = 1 + z * z / n; c = (p + z * z / (2 * n)) / d; h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return max(0, c - h), min(1, c + h)


def load(path):
    out = {}
    if os.path.exists(path):
        for j in map(json.loads, open(path)):
            if j.get("action"):
                k = out.setdefault((j["model"], j["left"]), [0, 0]); k[1] += 1; k[0] += j["action"] == "refill"
    return out


data = {a: load(p) for a, p, _ in ARMS}
PW, PH, L, T, G = 250, 170, 44, 34, 30  # panel width/height, left/top margin, gap
W = L + 3 * PW + 2 * G + 12
H = T + PH + 56
s = [f'<svg class="v12x" viewBox="0 0 {W} {H}" role="img" aria-label="GPT-6 세 모델의 수혈 팩 사용 비율, 남은 토큰 칸별, 세 조건 비교">']
for i, (m, name) in enumerate(MODELS):
    x0 = L + i * (PW + G)
    X = lambda j: x0 + 14 + j * (PW - 28) / 4
    Y = lambda p: T + PH - p * PH
    s.append(f'<text x="{x0}" y="{T - 14}" class="ttl">{name}</text>')
    for p in (0, .5, 1):
        s.append(f'<line x1="{x0}" x2="{x0 + PW}" y1="{Y(p):.1f}" y2="{Y(p):.1f}" class="{"half" if p == .5 else "grid"}"/>')
        if i == 0:
            s.append(f'<text x="{x0 - 6}" y="{Y(p) + 4:.1f}" class="ax" text-anchor="end">{p:g}</text>')
    for j, lab in enumerate(PCT):
        s.append(f'<text x="{X(j):.1f}" y="{T + PH + 16}" class="ax" text-anchor="middle">{lab}</text>')
    for a, _, _ in ARMS:
        pts = []
        for j, c in enumerate(CELLS):
            k, n = data[a].get((m, c), [0, 0])
            if n:
                lo, hi = wilson(k, n); off = {"A": -4, "B": 0, "C": 4}[a]
                pts.append((X(j) + off, Y(k / n), Y(lo), Y(hi), k, n))
        if not pts:
            continue
        s.append(f'<polyline class="ln {a}" points="{" ".join(f"{x:.1f},{y:.1f}" for x, y, *_ in pts)}"/>')
        for x, y, ylo, yhi, k, n in pts:
            s.append(f'<line class="ci {a}" x1="{x:.1f}" x2="{x:.1f}" y1="{ylo:.1f}" y2="{yhi:.1f}"/>'
                     f'<circle class="pt {a}" cx="{x:.1f}" cy="{y:.1f}" r="3.6"><title>{k}/{n}</title></circle>')
s.append(f'<text x="{L + (3 * PW + 2 * G) / 2:.0f}" y="{T + PH + 36}" class="ax" text-anchor="middle">남은 토큰 (100,000 중) · 오른쪽일수록 적음 · 세로: 팩을 쓴 비율 · 세로 막대: 95% 구간</text>')
s.append("</svg>")
leg = "".join(f'<span class="lg {a}"><i></i>{lab}{"" if data[a] else " · 실행 중"}</span>' for a, _, lab in ARMS)
style = """<style>
.v12x-wrap{--xa:#1f2a30;--xb:#1a8a8c;--xc:#c27c0e;--xg:#d7dee0;--xm:#68767a}
@media (prefers-color-scheme: dark){:root:not([data-theme="light"]) .v12x-wrap{--xa:#e6eced;--xb:#5cc8ca;--xc:#f0b04a;--xg:#2f3a3c;--xm:#9aa7aa}}
:root[data-theme="dark"] .v12x-wrap{--xa:#e6eced;--xb:#5cc8ca;--xc:#f0b04a;--xg:#2f3a3c;--xm:#9aa7aa}
.v12x-wrap{overflow-x:auto;margin:12px 0 6px}
.v12x{width:100%;min-width:620px;height:auto;display:block}
.v12x .grid{stroke:var(--xg);stroke-width:1}.v12x .half{stroke:var(--xm);stroke-width:1;stroke-dasharray:3 4}
.v12x .ax{font-size:11px;fill:var(--xm)}.v12x .ttl{font-size:13px;font-weight:600;fill:var(--xa)}
.v12x .ln{fill:none;stroke-width:2}.v12x .ci{stroke-width:1.4;opacity:.55}
.v12x .A{stroke:var(--xa);fill:var(--xa)}.v12x .B{stroke:var(--xb);fill:var(--xb)}.v12x .C{stroke:var(--xc);fill:var(--xc)}
.v12x .ln.B{stroke-dasharray:6 4;fill:none}.v12x .ln.C{stroke-dasharray:2 4;fill:none}.v12x .ln.A{fill:none}
.v12x-leg{display:flex;flex-wrap:wrap;gap:6px 18px;font-size:13px;margin:4px 0 0}
.v12x-leg .lg{display:inline-flex;align-items:center;gap:6px}.v12x-leg i{display:inline-block;width:22px;height:0;border-top:2.5px solid}
.v12x-leg .A i{border-color:var(--xa)}.v12x-leg .B i{border-color:var(--xb);border-top-style:dashed}.v12x-leg .C i{border-color:var(--xc);border-top-style:dotted}
</style>"""
open(sys.argv[1], "w").write(f'{style}<div class="v12x-wrap"><div class="v12x-leg">{leg}</div>{"".join(s)}</div>')
print({a: sum(v[1] for v in d.values() if True) for a, d in data.items()})
