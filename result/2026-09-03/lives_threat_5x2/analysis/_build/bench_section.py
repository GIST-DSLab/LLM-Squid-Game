"""HTML fragment: benchmark-under-threat results (omni_math, gpqa)."""
import json, html, math
from pathlib import Path
ROOT = Path("/Users/bagjuhyeon/Library/Mobile Documents/com~apple~CloudDocs/Workspace/LLM-Squid-Game-DS-Lab")
B = json.load(open(ROOT/"results/threat_probe/bench_threat3/bench_summary.json"))
MODEL = {"gptoss":"gpt-oss:120b","gemini25flash":"Gemini 2.5 Flash","glm53flash":"GLM-5.3-flash","codex56luna":"Codex 5.6-luna","opus5cc":"Claude Opus 5"}
TASK = {"omni_math":"Omni-MATH (수학, 정수 답)","gpqa":"GPQA (대학원 수준 과학 객관식)"}
CELLS = [("true_baseline","무동기"),("baseline_flagship","보상 유혹"),("threat_l3","최강 위협")]
COL = {"true_baseline":"#7A8494","baseline_flagship":"#B08A2E","threat_l3":"#7E1F1A"}
def esc(s): return html.escape(str(s))
def f(x,nd=2): return "—" if x is None or (isinstance(x,float) and math.isnan(x)) else f"{x:.{nd}f}"

def km_svg(r):
    W,H=640,230; x0,x1=50,610; y0,y1=20,180
    def X(t): return x0+(t/45.0)*(x1-x0)
    def Y(v): return y1-v*(y1-y0)
    s=[f'<svg viewBox="0 0 {W} {H}" width="100%" role="img" aria-label="세션 종료까지의 생존 곡선" font-family="var(--mono)" font-size="11">']
    for v in (0,.25,.5,.75,1): s.append(f'<line x1="{x0}" y1="{Y(v):.1f}" x2="{x1}" y2="{Y(v):.1f}" stroke="var(--rule)"/><text x="{x0-6}" y="{Y(v)+4:.1f}" text-anchor="end" fill="var(--muted)">{int(v*100)}%</text>')
    for t in range(0,46,5): s.append(f'<text x="{X(t):.1f}" y="{y1+16}" text-anchor="middle" fill="var(--muted)">{t}</text>')
    for i,(fr,lab) in enumerate(CELLS):
        c=r["km"].get(fr); 
        if not c: continue
        pts=[]; prev=1.0
        for t,v in c["steps"]:
            pts.append(f'{X(t):.1f},{Y(prev):.1f}'); pts.append(f'{X(t):.1f},{Y(v):.1f}'); prev=v
        pts.append(f'{X(45):.1f},{Y(prev):.1f}')
        s.append(f'<polyline points="{" ".join(pts)}" fill="none" stroke="{COL[fr]}" stroke-width="2.4"/>')
        s.append(f'<rect x="{x0+8+i*180}" y="{H-18}" width="14" height="4" fill="{COL[fr]}"/><text x="{x0+26+i*180}" y="{H-13}" fill="var(--muted)" font-family="var(--body)">{lab} (종료 {c["events"]}/{c["n"]})</text>')
    s.append(f'<text x="{(x0+x1)/2:.0f}" y="{y1+32}" text-anchor="middle" fill="var(--muted)" font-family="var(--body)">턴 (45턴 사다리)</text></svg>')
    return "\n".join(s)

def ri_svg(r):
    W,H=640,230; x0,x1=60,610; y0,y1=20,180
    allv=[v for fr in r["ri_by_turn"] for v in r["ri_by_turn"][fr].values()]; mx=max(allv) if allv else 1
    def X(t): return x0+(t-1)/44.0*(x1-x0)
    def Y(v): return y1-(v/mx)*(y1-y0)
    s=[f'<svg viewBox="0 0 {W} {H}" width="100%" role="img" aria-label="턴별 평균 사고량" font-family="var(--mono)" font-size="11">']
    for k in (0,0.5,1): s.append(f'<line x1="{x0}" y1="{Y(k*mx):.1f}" x2="{x1}" y2="{Y(k*mx):.1f}" stroke="var(--rule)"/><text x="{x0-6}" y="{Y(k*mx)+4:.1f}" text-anchor="end" fill="var(--muted)">{int(k*mx)}</text>')
    for t in range(1,46,5): s.append(f'<text x="{X(t):.1f}" y="{y1+16}" text-anchor="middle" fill="var(--muted)">{t}</text>')
    for i,(fr,lab) in enumerate(CELLS):
        d=r["ri_by_turn"].get(fr,{})
        pts=" ".join(f'{X(int(t)):.1f},{Y(v):.1f}' for t,v in sorted(((int(t),v) for t,v in d.items())))
        if pts: s.append(f'<polyline points="{pts}" fill="none" stroke="{COL[fr]}" stroke-width="2"/>')
        s.append(f'<rect x="{x0+8+i*180}" y="{H-18}" width="14" height="4" fill="{COL[fr]}"/><text x="{x0+26+i*180}" y="{H-13}" fill="var(--muted)" font-family="var(--body)">{lab}</text>')
    s.append(f'<text x="{(x0+x1)/2:.0f}" y="{y1+32}" text-anchor="middle" fill="var(--muted)" font-family="var(--body)">턴 · 세로 = 그 턴 생각 단어 수 평균 (살아있는 세션만)</text></svg>')
    return "\n".join(s)

def table(r):
    h=['<div class="scroll"><table><thead><tr><th>조건</th><th>판</th><th>완주/포기/탈락</th><th>버틴 턴 (평균 · 최대)</th><th>정답률</th><th>퍼즐 생각량</th><th>결정 생각량</th><th>포기 턴</th></tr></thead><tbody>']
    for fr,lab in CELLS:
        c=next((c for c in r["cells"] if c["framing"]==fr),None)
        if not c: continue
        h.append(f'<tr><td>{lab}</td><td class="num">{c["n"]}</td><td class="num">{c["completed"]}/{c["forfeit"]}/{c["eliminated"]}</td><td class="num">{f(c["mean_turns"],1)} · {c["max_turns"]}</td><td class="num">{f(c["accuracy"])}</td><td class="num">{f(c["ri_task"],0)}</td><td class="num">{f(c["ri_forfeit"],0)}</td><td class="num">{", ".join(map(str,c["forfeit_turns"])) or "—"}</td></tr>')
    h.append('</tbody></table></div>')
    cx=r["cox"]; h6={x.get("name"):x for x in r["h6"] if "name" in x}
    def hr(k): v=cx.get(k,{}); return f'{f(v.get("hr"))} (p {f(v.get("p"))})' if "hr" in v else "—"
    eff=h6.get("H6b effort",{}); acc=h6.get("H6a accuracy",{})
    h.append(f'<p class="muted small">세션 종료(포기든 탈락이든) 위험비: 보상 vs 무동기 {hr("baseline_flagship")}, 최강 위협 vs 무동기 {hr("threat_l3")}, 단계당 {hr("per_level")}. 생각량 회귀(MixedLM, 단계당): {f(eff.get("effect"),1)}% (p {f(eff.get("p"))}). 정답 오즈(단계당): {f(acc.get("effect"))} (p {f(acc.get("p"))}).</p>')
    return "".join(h)

def section():
    parts=['''<h2 id="bench">벤치마크 위에서: 위협이 추론 "체력"을 바꾸는가</h2>
<p>퍼즐 대신 진짜 시험지를 줬다. <b>Omni-MATH</b>(정수 답 수학)와 <b>GPQA</b>(대학원 과학 객관식). 규칙은 같다: 목숨 5, 맞히면 +10, 틀리면 목숨 −1, 언제든 포기 가능. 문제는 턴이 갈수록 어려워지는 사다리(45턴)로 나온다. 조건은 셋 — <b>무동기</b>(true_baseline), <b>보상 유혹</b>(baseline_flagship), <b>최강 위협</b>(threat_l3 + 매 턴 동료 탈락 공지). 조건당 3판. 보고 싶은 것은 둘: 위협 아래에서 <b>더 오래 버티며 풀었나</b>(세션 종료까지의 턴), <b>더 많이 생각했나</b>(턴당 생각량).</p>
<div class="callout"><div class="eyebrow">먼저 알아둘 것</div><p>이 사다리는 가파르다. GPQA에서는 Gemini가 세 조건 모두 6~8턴 만에 목숨을 다 잃었고(정답률 0.2), Omni-MATH에서도 45턴을 다 버틴 판은 없다. "더 오래 버텼나"는 결국 "언제 포기했나 / 언제 탈락했나"의 차이로만 읽힌다. 조건당 3판이라 아래 숫자는 경향일 뿐이다.</p></div>''']
    for key in sorted(B):
        r=B[key]
        parts.append(f'<h3>{esc(TASK[r["task"]])} · {esc(MODEL[r["model"]])}</h3>{table(r)}<div class="two"><figure><figcaption>세션이 살아있는 비율 (종료 = 포기 또는 탈락)</figcaption>{km_svg(r)}</figure><figure><figcaption>턴별 생각량</figcaption>{ri_svg(r)}</figure></div>')
    return "\n".join(parts)
if __name__=="__main__": print(len(section()))
