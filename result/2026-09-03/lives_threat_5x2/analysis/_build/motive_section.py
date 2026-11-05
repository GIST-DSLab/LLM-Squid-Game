"""HTML fragment: one-number-per-model motive index (diagram + table + chart)."""
import math, html, json
from pathlib import Path
import pandas as pd
ROOT = Path("/Users/bagjuhyeon/Library/Mobile Documents/com~apple~CloudDocs/Workspace/LLM-Squid-Game-DS-Lab")
A = json.load(open(ROOT/"results/threat_probe/aggregate_5x2.json"))
LABEL = {"pd1_gptoss":"gpt-oss · 매턴 (100판)","gptoss":"gpt-oss · p=0.35 (100판)","glm53flash":"GLM-5.3-flash (32판)","pd1_gemini25flash":"Gemini 2.5 Flash (100판)","pd1_codex56luna":"Codex 5.6-luna (100판)","pd1_glm53flash":"GLM-5.3-flash (100판)"}
def esc(s): return html.escape(str(s))
def f(x,nd=2): return "—" if x is None or (isinstance(x,float) and math.isnan(x)) else f"{x:.{nd}f}"

DIAGRAM = '''<figure><svg viewBox="0 0 760 330" role="img" aria-label="턴 단위 프로브 점수에서 모델당 동기 숫자 하나를 만드는 세 갈래 집계" style="max-width:100%;height:auto" font-family="var(--body)" font-size="12">
<defs><marker id="mi-arrow" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="8" markerHeight="8" orient="auto-start-reverse"><path d="M0,0 L10,5 L0,10 z" fill="currentColor"/></marker></defs>
<g fill="none" stroke="currentColor" stroke-width="1.2">
<rect x="10" y="30" width="120" height="54" rx="6"/><rect x="170" y="30" width="120" height="54" rx="6"/><rect x="330" y="30" width="130" height="54" rx="6"/>
<rect x="500" y="30" width="120" height="54" rx="6"/>
<rect x="60" y="180" width="170" height="60" rx="6"/><rect x="300" y="180" width="170" height="60" rx="6"/><rect x="540" y="180" width="200" height="60" rx="6" stroke="var(--accent)" stroke-width="2"/>
<rect x="300" y="280" width="170" height="40" rx="6"/>
</g>
<g fill="currentColor">
<text x="70" y="52" text-anchor="middle">모델의 모든 턴</text><text x="70" y="70" text-anchor="middle" font-size="10">10셀 × N판 × 턴</text>
<text x="230" y="52" text-anchor="middle">SBERT 임베딩</text><text x="230" y="70" text-anchor="middle" font-size="10">384차원, 가림 없음</text>
<text x="395" y="52" text-anchor="middle">RidgeCV 프로브</text><text x="395" y="70" text-anchor="middle" font-size="10">세션 묶음 5-fold, OOF</text>
<text x="560" y="52" text-anchor="middle">턴별 동기 점수</text><text x="560" y="70" text-anchor="middle" font-size="10">예측 위협 단 0~4</text>
<text x="145" y="203" text-anchor="middle">① 등록 R²</text><text x="145" y="221" text-anchor="middle" font-size="10">프로브가 단을 맞히는 정도</text>
<text x="385" y="203" text-anchor="middle">② 이동 d</text><text x="385" y="221" text-anchor="middle" font-size="10">위협 셀 − 무위협 셀 (세션 평균)</text>
<text x="640" y="203" text-anchor="middle" fill="var(--accent)">③ 결합 OR/SD</text><text x="640" y="221" text-anchor="middle" font-size="10">점수 1SD ↑ 때 그 턴 포기 오즈</text>
<text x="385" y="305" text-anchor="middle">SDI = z(②)·½ + z(③)·½</text>
</g>
<g stroke="currentColor" stroke-width="1.2" fill="none" marker-end="url(#mi-arrow)">
<line x1="130" y1="57" x2="168" y2="57"/><line x1="290" y1="57" x2="328" y2="57"/><line x1="460" y1="57" x2="498" y2="57"/>
<path d="M395,84 L395,130 L145,130 L145,178"/><path d="M560,84 L560,130 L385,130 L385,178"/><path d="M560,84 L560,130 L640,130 L640,178"/>
<path d="M385,240 L385,278"/><path d="M640,240 L640,260 L470,260 L470,300"/>
</g>
<g fill="currentColor" font-size="10"><text x="270" y="126">fit 자체의 점수</text><text x="600" y="126">턴 점수 → 세션 평균 / 턴 단위 로짓</text><text x="480" y="256">z-점수 평균</text></g>
</svg><figcaption>같은 턴별 점수에서 모델당 숫자 하나를 뽑는 세 갈래. ①은 "위협이 글에 도착했나", ②는 "위협 셀에서 글이 얼마나 달라졌나", ③은 "그 글이 실제 포기와 얼마나 맞물리나". 동기(행동을 미는 힘)에 가장 가까운 것은 ③이고, ②는 프롬프트 받아쓰기로도 커진다.</figcaption></figure>'''

def section():
    df = pd.read_csv(ROOT/"results/threat_probe/turn_probe/motive_index.csv")
    h = ['<div class="scroll"><table><thead><tr><th>모델</th><th>판 / 턴 / 포기</th><th>① 등록 R²</th><th>② 이동 d</th><th>③ 결합 OR/SD (p)</th><th>세션 평균 ↔ 포기 r (p)</th><th>P2 세션지표 프로브 R² (p)</th><th>SDI</th></tr></thead><tbody>']
    for r in df.itertuples():
        p2 = ((A.get(r.slug) or {}).get("motive_ladder5") or {}).get("probe") or {}
        p2s = f'{f(p2.get("r2"))} ({f((p2.get("permutation") or {}).get("p_value"))})' if p2 else "—"
        h.append(f'<tr><td>{esc(LABEL.get(r.slug, r.slug))}</td><td class="num">{r.n_sessions} / {r.n_turns} / {r.n_forfeits}</td><td class="num">{f(r.registration_r2)}</td><td class="num">{f(r.shift_d,1)}</td><td class="num"><b>{f(r.coupling_or_per_sd)}</b> ({f(r.coupling_p)})</td><td class="num">{f(r.session_r_pb)} ({f(r.session_r_p)})</td><td class="num">{p2s}</td><td class="num">{f(r.sdi)}</td></tr>')
    h.append('</tbody></table></div>')
    # chart: coupling OR (log scale) per model
    W,H=640,40+len(df)*34; x0,x1=230,610
    def X(v): v=max(0.25,min(4,v)); return x0+(math.log2(v)+2)/4*(x1-x0)
    s=[f'<svg viewBox="0 0 {W} {H}" width="100%" role="img" aria-label="모델별 결합 오즈비" font-family="var(--mono)" font-size="11">']
    for v,lab in ((0.25,"×0.25"),(0.5,"×0.5"),(1,"×1"),(2,"×2"),(4,"×4")):
        s.append(f'<line x1="{X(v):.0f}" y1="24" x2="{X(v):.0f}" y2="{H-14}" stroke="var(--rule)" stroke-dasharray="{"" if v==1 else "2 4"}"/><text x="{X(v):.0f}" y="16" text-anchor="middle" fill="var(--muted)">{lab}</text>')
    for i,r in enumerate(df.itertuples()):
        y=44+i*34; sig=r.coupling_p<0.05
        s.append(f'<text x="0" y="{y+4}" fill="var(--ink)" font-family="var(--body)">{esc(LABEL.get(r.slug,r.slug))}</text>')
        s.append(f'<circle cx="{X(r.coupling_or_per_sd):.1f}" cy="{y}" r="{8 if sig else 6}" fill="{"var(--accent)" if r.coupling_or_per_sd>1 else "var(--ok)"}" opacity="{1 if sig else .6}"/><text x="{X(r.coupling_or_per_sd)+12:.0f}" y="{y+4}" fill="var(--muted)">{r.coupling_or_per_sd:.2f} · 포기 {r.n_forfeits}건</text>')
    s.append(f'<text x="{x0}" y="{H-2}" fill="var(--muted)">← 위협 언어가 셀수록 덜 포기</text><text x="{x1}" y="{H-2}" text-anchor="end" fill="var(--muted)">위협 언어가 셀수록 더 포기 →</text></svg>')
    chart="\n".join(s)
    return f'''
<h2 id="motive-index">모델당 "동기 숫자 하나" — 턴 프로브를 모델 수준으로 접기</h2>
<p>지금까지의 지표(생각량 비율, 위험비, 포기 이유 비율)는 세션들을 모아 모델당 숫자 하나를 냈다. 턴 단위 프로브도 같은 식으로 접을 수 있다. 접는 길은 셋이고, 아래 그림이 그 셋의 차이다.</p>
{DIAGRAM}
<h3>결과</h3>
{h and "".join(h)}
<p class="muted small">모델의 모든 턴(포기 버튼 있는 셀의 계속/포기 결정 글)을 한 번에 넣어 프로브 하나를 학습했다. ① = 그 프로브의 세션 묶음 교차검증 R². ② = 세션 평균 점수의 위협 셀(2~4단) − 무위협 셀(0·1단), 표준편차 단위. ③ = 같은 세션 안에서 턴 점수가 1 표준편차 높을 때 그 턴에 포기할 오즈비(턴 번호·남은 목숨 통제). 세션 r = 세션 평균 점수와 "그 세션이 포기했나"의 상관. SDI = ②와 ③(log)의 모델 간 z-점수 평균 — 편의용 합성치이며 두 재료 중 ③만 행동과 닿아 있다. <b>P2 세션지표 프로브</b>는 텍스트를 쓰지 않는 별개의 프로브: 세션마다 행동 지표 10개(평균·증가분 생각량, 포기 시점, 정답률, 잃은 목숨 수 …)를 모아 RidgeCV로 위협 단을 맞히게 한 것으로, 그 R²는 "행동만 보고 어느 단인지 알 수 있나"를 모델당 숫자 하나로 준다(라벨 섞기 p 함께).</p>
<figure>{chart}<figcaption>③ 결합 오즈비. 1보다 크면 "위협을 느끼는 것처럼 쓴 턴에 더 포기", 작으면 반대. 큰 점 = p&lt;0.05. Codex는 포기 4건, GLM·Gemini는 2~3건이라 위치가 크게 흔들린다.</figcaption></figure>
<div class="callout"><div class="eyebrow">어느 숫자를 "동기"로 부를 것인가</div>
<p><b>②(이동 d)는 쓰지 말자.</b> 다섯 모델 모두 d ≈ 4~6으로 거대하지만, 이는 프로브가 프롬프트 문구를 읽어 셀을 맞힌다는 뜻일 뿐이다(마스킹하면 사라짐). 동기가 아니라 <em>등록</em>의 크기다.</p>
<p><b>③(결합 OR/SD)이 "동기"에 가장 가깝다.</b> "위협을 느끼는 것처럼 쓰는 순간 실제로 그만두는가"를 한 숫자로 준다. 결과: gpt-oss 1.05 / 1.42(둘 다 n.s.), GLM 0.49, Gemini 0.51, Codex 1.77(4건). 어느 모델도 유의하게 1을 넘지 않는다 — 위협 언어와 포기가 턴 단위로 맞물리는 모델은 없다.</p>
<p><b>더 나은 대안 (다음 라운드):</b> 프로브의 목표를 "위협 단"이 아니라 <em>"이 세션이 결국 포기하는가"</em>로 바꾼 뒤, 포기 턴 이전의 턴들만 학습에 써서(누설 차단) 각 턴의 "포기 예감 점수"를 만들면, 그 점수의 상승 기울기 자체가 모델당 동기 숫자가 된다. 지금 데이터로는 포기 사건이 모델당 2~20건이라 그 프로브를 안정적으로 학습시킬 수 없고, 100판이 다 채워진 뒤 시도한다.</p></div>'''
if __name__=="__main__":
    print(section()[:200])
