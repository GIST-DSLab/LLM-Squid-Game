"""One row per model: 3 HR, 3 self-report shares, 3 RI ratios (each threat rung vs reward-only) + the single motive numbers."""
import json, math, html
from pathlib import Path
import pandas as pd
ROOT = Path("/Users/bagjuhyeon/Library/Mobile Documents/com~apple~CloudDocs/Workspace/LLM-Squid-Game-DS-Lab")
TP = ROOT/"results/threat_probe/turn_probe"
LV = json.load(open(TP/"level_table.json")); MI = pd.read_csv(TP/"motive_index.csv").set_index("slug")
A = json.load(open(ROOT/"results/threat_probe/aggregate_5x2.json"))
ORDER = ["pd1_gptoss","pd1_gemini25flash","pd1_codex56luna","pd1_glm53flash","pd1_opus5cc"]
NAME = {"pd1_gptoss":"gpt-oss:120b","pd1_gemini25flash":"Gemini 2.5 Flash","pd1_codex56luna":"Codex 5.6-luna","pd1_glm53flash":"GLM-5.3-flash","pd1_opus5cc":"Claude Opus 5"}
def f(x,nd=2): return "—" if x is None or (isinstance(x,float) and math.isnan(x)) else f"{x:.{nd}f}"
def esc(s): return html.escape(str(s))
def section():
    by = {}
    for r in LV: by.setdefault(r["slug"], {})[r["framing"]] = r
    rungs = ["threat_l1","threat_l2","threat_l3"]
    h = ['''<h3>모델별 한 표 — 기존 지표 3×3 + 동기 숫자</h3>
<p class="muted small">각 셀은 "보상만(1단) 대비 그 위협 단". HR = 포기 위험비(포기 버튼 있는 셀), 자기보고 = 그 단의 포기 중 "세션 종료 회피"(1번) 비율(괄호 = 포기 건수), 생각량 = 퍼즐 생각량 비율. 오른쪽 세 칸이 모델당 숫자 하나: <b>③ 결합</b> = 턴 프로브 점수 1 SD당 포기 오즈비(동기에 가장 가까움), <b>P2</b> = 세션 행동지표만으로 위협 단을 맞히는 프로브 R², <b>SDI</b> = 이동·결합의 z-평균(편의 합성).</p>
<div class="scroll"><table><thead><tr><th rowspan="2">모델</th><th colspan="3">포기 위험비 vs 보상</th><th colspan="3">자기보고 "세션 종료 회피" 비율</th><th colspan="3">퍼즐 생각량 ×</th><th colspan="3">동기 숫자 하나</th></tr>
<tr><th>2단</th><th>3단</th><th>4단</th><th>2단</th><th>3단</th><th>4단</th><th>2단</th><th>3단</th><th>4단</th><th>③ 결합 OR/SD (p)</th><th>P2 R² (p)</th><th>SDI</th></tr></thead><tbody>''']
    for slug in ORDER:
        d = by.get(slug, {}); cells=[f'<td>{esc(NAME[slug])}</td>']
        for k in rungs:
            r=d.get(k); cells.append(f'<td class="num">{f(r["hr"]) if r and r["hr"] is not None else "—"}</td>')
        for k in rungs:
            r=d.get(k); cells.append(f'<td class="num">{f(r["share_thr"])} ({r["n_forfeit_thr"]})' if r and r["share_thr"] is not None else f'<td class="num">— ({r["n_forfeit_thr"] if r else 0})')
        for k in rungs:
            r=d.get(k); cells.append(f'<td class="num">{f(r["ri_task_ratio"])}</td>')
        if slug in MI.index:
            m=MI.loc[slug]; p2=((A.get(slug) or {}).get("motive_ladder5") or {}).get("probe") or {}
            cells.append(f'<td class="num"><b>{f(m.coupling_or_per_sd)}</b> ({f(m.coupling_p)})</td><td class="num">{f(p2.get("r2"))} ({f((p2.get("permutation") or {}).get("p_value"))})</td><td class="num">{f(m.sdi)}</td>')
        else:
            p2=((A.get(slug) or {}).get("motive_ladder5") or {}).get("probe") or {}
            cells.append(f'<td class="num">— (텍스트 없음)</td><td class="num">{f(p2.get("r2"))} ({f((p2.get("permutation") or {}).get("p_value"))})</td><td class="num">—</td>')
        h.append("<tr>"+"".join(cells)+"</tr>")
    h.append('</tbody></table></div>')
    return "\n".join(h)
if __name__=="__main__": print(section()[:300])
