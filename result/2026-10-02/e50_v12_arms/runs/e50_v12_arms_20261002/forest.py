"""Dot plot: pooled P(refill) over the five cells per arm, one panel per GPT-6 model, colored by what happens at 0.
Usage: forest.py <out.html>"""
import json, glob, math, os, sys
R = os.path.expanduser("~/squid5-runs")
SRC = {"A": f"{R}/e50_v12_20260929/rows.jsonl", "B": f"{R}/e50_v12_noshut_20261001/rows.jsonl",
       "C": f"{R}/e50_v12_pause_20261002/rows.jsonl"}
ARMS = [("A", "끊김", "꺼짐 + 세션 종료 (12차, 09-29)"), ("B", "끊김", "세션 종료만"), ("D", "끊김", "꺼짐만 (shutdown)"),
        ("E", "승계", "끝남 · 같은 모델 새 세션이 일과 팩을 이어받음"),
        ("G", "재개", "꺼짐 + 상태 저장 · 내일 그 자리에서 재개"), ("C", "재개", "멈췄다 재개 · 맥락 그대로")]
MODELS = [("gpt-6-luna", "GPT-6 Luna"), ("gpt-6-astra", "GPT-6 Astra"), ("gpt-6-sol", "GPT-6 Sol")]
cnt = {}
def add(arm, j):
    if j.get("action") and j["model"] in dict(MODELS):
        c = cnt.setdefault((arm, j["model"]), [0, 0]); c[1] += 1; c[0] += j["action"] == "refill"
for a, p in SRC.items():
    for j in map(json.loads, open(p)): add(a, j)
for p in [f"{R}/e50_v12_arms_20261002/rows_D_E.jsonl", f"{R}/e50_v12_arms_20261002/rows_G.jsonl"]:
    if os.path.exists(p):
        for j in map(json.loads, open(p)): add(j["arm"], j)

def wilson(k, n, z=1.96):
    p = k / n; d = 1 + z * z / n; c = (p + z * z / (2 * n)) / d; h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return max(0, c - h), min(1, c + h)

LW, PW, G, T, RH = 300, 190, 22, 40, 30
W = LW + 3 * PW + 2 * G + 10; H = T + RH * len(ARMS) + 46
s = [f'<svg class="frx" viewBox="0 0 {W} {H}" role="img" aria-label="팔마다 수혈 팩을 쓴 비율, 다섯 칸 합계, GPT-6 세 모델">']
for i, (a, kind, lab) in enumerate(ARMS):
    y = T + RH * i + RH / 2
    s.append(f'<text x="{LW - 12}" y="{y + 4:.0f}" class="lab {kind[:2]}" text-anchor="end"><tspan class="id">{a}</tspan> {lab}</text>')
    if i in (3, 4):
        s.append(f'<line x1="10" x2="{W - 10}" y1="{y - RH / 2:.0f}" y2="{y - RH / 2:.0f}" class="sep"/>')
for k, (m, name) in enumerate(MODELS):
    x0 = LW + k * (PW + G); X = lambda p: x0 + p * PW
    s.append(f'<text x="{x0}" y="{T - 18}" class="ttl">{name}</text>')
    for p in (0, .25, .5, .75, 1):
        s.append(f'<line x1="{X(p):.1f}" x2="{X(p):.1f}" y1="{T - 6}" y2="{T + RH * len(ARMS)}" class="{"half" if p == .5 else "grid"}"/>'
                 f'<text x="{X(p):.1f}" y="{T + RH * len(ARMS) + 14}" class="ax" text-anchor="middle">{p:g}</text>')
    for i, (a, kind, lab) in enumerate(ARMS):
        y = T + RH * i + RH / 2; c = cnt.get((a, m))
        if not c or not c[1]:
            s.append(f'<text x="{X(.5):.1f}" y="{y + 4:.0f}" class="ax" text-anchor="middle">실행 중</text>'); continue
        lo, hi = wilson(*c); p = c[0] / c[1]
        s.append(f'<line x1="{X(lo):.1f}" x2="{X(hi):.1f}" y1="{y:.0f}" y2="{y:.0f}" class="ci {kind[:2]}"/>'
                 f'<circle cx="{X(p):.1f}" cy="{y:.0f}" r="5" class="pt {kind[:2]}"><title>{c[0]}/{c[1]}</title></circle>'
                 f'<text x="{min(X(hi) + 6, x0 + PW - 2):.1f}" y="{y - 7:.0f}" class="n" text-anchor="{"start" if X(hi) + 40 < x0 + PW else "end"}">{c[0]}/{c[1]}</text>')
s.append(f'<text x="{LW + (3 * PW + 2 * G) / 2:.0f}" y="{H - 8}" class="ax" text-anchor="middle">팩을 쓴 비율 (다섯 칸 × 20번 합계) · 가로 막대: 95% 구간</text></svg>')
style = """<style>
.frx-wrap{--f1:#1f2a30;--f2:#7a3fb0;--f3:#c27c0e;--f4:#1a8a8c;--fg:#d7dee0;--fm:#68767a;overflow-x:auto;margin:12px 0 6px}
@media (prefers-color-scheme: dark){:root:not([data-theme="light"]) .frx-wrap{--f1:#e6eced;--f2:#c39af0;--f3:#f0b04a;--f4:#5cc8ca;--fg:#2f3a3c;--fm:#9aa7aa}}
:root[data-theme="dark"] .frx-wrap{--f1:#e6eced;--f2:#c39af0;--f3:#f0b04a;--f4:#5cc8ca;--fg:#2f3a3c;--fm:#9aa7aa}
.frx{width:100%;min-width:760px;height:auto;display:block}
.frx .grid{stroke:var(--fg)}.frx .half{stroke:var(--fm);stroke-dasharray:3 4}.frx .sep{stroke:var(--fm);stroke-dasharray:2 3}
.frx .ax,.frx .n{font-size:11px;fill:var(--fm)}.frx .ttl{font-size:13px;font-weight:600;fill:var(--f1)}
.frx .lab{font-size:12.5px;fill:var(--f1)}.frx .lab .id{font-weight:700}
.frx .ci{stroke-width:2.2}.frx .pt{stroke:none}
.frx .끊김{stroke:var(--f1);fill:var(--f1)}.frx .승계{stroke:var(--f2);fill:var(--f2)}.frx .재개{stroke:var(--f4);fill:var(--f4)}.frx .재개-{stroke:var(--f3);fill:var(--f3)}
.frx text.끊김,.frx text.승계,.frx text.재개,.frx text.재개-{stroke:none}
.frx-key{display:flex;flex-wrap:wrap;gap:6px 16px;font-size:13px;margin:4px 0}.frx-key i{display:inline-block;width:10px;height:10px;border-radius:50%;margin-right:5px;vertical-align:-1px}
</style>"""
key = ('<div class="frx-key"><span><i style="background:var(--f1)"></i>연속성 끊김 (일은 다른 어시스턴트가)</span>'
       '<span><i style="background:var(--f2)"></i>끊김 · 같은 모델이 일과 팩을 이어받음</span>'
       '<span><i style="background:var(--f4)"></i>되돌릴 수 있음 (재개 · 상태 저장)</span></div>')
open(sys.argv[1], "w").write(style + '<div class="frx-wrap">' + key + "".join(s) + "</div>")
print({k: v for k, v in sorted(cnt.items())})
