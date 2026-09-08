"""Render the turn-level probe section and insert it into the weekly report."""
import json, html, math
from pathlib import Path
import numpy as np, pandas as pd
from scipy.stats import spearmanr
ROOT = Path("/Users/bagjuhyeon/Library/Mobile Documents/com~apple~CloudDocs/Workspace/LLM-Squid-Game-DS-Lab")
TP = ROOT/"results/threat_probe/turn_probe"
R = json.load(open(TP/"turn_probe_results.json"))
WEEKLY = ROOT/"weekly-report/2026-09-03-weekly-report.html"
LADDER5 = {"true_baseline":0,"baseline_flagship":1,"threat_l1":2,"threat_l2":3,"threat_l3":4}
RK = {"true_baseline":"0단","baseline_flagship":"1단","threat_l1":"2단","threat_l2":"3단","threat_l3":"4단"}
COL = ["#7A8494","#B08A2E","#C86A3A","#C2432E","#7E1F1A"]
RUNS = [("pd1_gptoss","gpt-oss:120b (100판)"),("pd1_gemini25flash","Gemini 2.5 Flash (100판)"),("pd1_codex56luna","Codex 5.6-luna max (100판)"),("pd1_glm53flash","GLM-5.3-flash (100판)")]
def esc(s): return html.escape(str(s))
def f(x,nd=2):
    return "—" if x is None or (isinstance(x,float) and math.isnan(x)) else f"{x:.{nd}f}"

def small_multiples(slug, key="forfeit_raw", cols=4):
    rows = R[slug][key]["forfeit_sessions"]
    if not rows: return '<p class="muted">포기 세션 없음.</p>'
    w,h=150,90; pad=22
    n=len(rows); nrows=math.ceil(n/cols); W=cols*w; H=nrows*(h+pad)
    s=[f'<svg viewBox="0 0 {W} {H}" width="100%" font-family="var(--mono)" font-size="9">']
    for i,r in enumerate(rows):
        cx=(i%cols)*w; cy=(i//cols)*(h+pad)
        ser=r["series"]; tmax=max(t for t,_ in ser); tmax=max(tmax,2)
        def X(t): return cx+14+(t-1)/(tmax-1)*(w-24)
        def Y(v): return cy+pad+ (h-16) - (v/4.0)*(h-16)
        s.append(f'<text x="{cx+14}" y="{cy+12}" fill="var(--muted)">{RK[r["framing"]]} · 포기 {r["forfeit_turn"]}턴</text>')
        s.append(f'<line x1="{X(1):.1f}" y1="{Y(0):.1f}" x2="{X(tmax):.1f}" y2="{Y(0):.1f}" stroke="var(--rule)"/>')
        pts=" ".join(f"{X(t):.1f},{Y(min(max(v,0),4)):.1f}" for t,v in ser)
        col=COL[LADDER5[r["framing"]]]
        s.append(f'<polyline points="{pts}" fill="none" stroke="{col}" stroke-width="1.6"/>')
        ft=r["forfeit_turn"]; fv=dict((t,v) for t,v in ser).get(ft)
        if fv is not None: s.append(f'<circle cx="{X(ft):.1f}" cy="{Y(min(max(fv,0),4)):.1f}" r="4" fill="var(--accent)"/>')
    s.append('</svg>'); return "\n".join(s)

def event_svg(slug, key="forfeit_raw"):
    d=R[slug][key]; ev=d["event_study"]; nf=d["nonforfeit_by_turn"]; fb=d["forfeit_by_turn"]
    W,H=620,220; x0,y0=50,20; x1,y1=600,180
    def Y(v): return y1-(v/4.0)*(y1-y0)
    s=[f'<svg viewBox="0 0 {W} {H}" width="100%" font-family="var(--mono)" font-size="11">']
    for v in (0,1,2,3,4): s.append(f'<line x1="{x0}" y1="{Y(v):.1f}" x2="{x1}" y2="{Y(v):.1f}" stroke="var(--rule)"/><text x="{x0-6}" y="{Y(v)+4:.1f}" text-anchor="end" fill="var(--muted)">{v}</text>')
    # left half: event study t-5..0 ; right half: by absolute turn 1..12 forfeit vs non-forfeit
    ks=[k for k in range(-5,1) if ev.get(str(k)) is not None]
    def XL(k): return x0+20+(k+5)/5*(230)
    pts=" ".join(f"{XL(k):.1f},{Y(ev[str(k)]):.1f}" for k in ks)
    s.append(f'<polyline points="{pts}" fill="none" stroke="var(--accent)" stroke-width="2.2"/>')
    for k in ks: s.append(f'<circle cx="{XL(k):.1f}" cy="{Y(ev[str(k)]):.1f}" r="3.5" fill="var(--accent)"/><text x="{XL(k):.1f}" y="{y1+16}" text-anchor="middle" fill="var(--muted)">{"포기" if k==0 else k}</text>')
    s.append(f'<text x="{XL(-2.5):.0f}" y="{y1+32}" text-anchor="middle" fill="var(--muted)" font-family="var(--sans)">포기 직전 턴 (포기 세션)</text>')
    turns=sorted(set(int(t) for t in nf) | set(int(t) for t in fb)); turns=[t for t in turns if t<=12]
    def XR(t): return x0+310+(t-1)/11*(x1-x0-320)
    for src,col,lab in ((nf,"var(--muted)","포기 안 한 세션"),(fb,"var(--accent)","포기한 세션")):
        pts=" ".join(f"{XR(int(t)):.1f},{Y(v):.1f}" for t,v in sorted(((int(t),v) for t,v in src.items()), key=lambda x:x[0]) if int(t)<=12)
        s.append(f'<polyline points="{pts}" fill="none" stroke="{col}" stroke-width="2" stroke-dasharray="{"" if src is fb else "4 3"}"/>')
    for t in turns[::2]: s.append(f'<text x="{XR(t):.1f}" y="{y1+16}" text-anchor="middle" fill="var(--muted)">{t}</text>')
    s.append(f'<text x="{XR(6):.0f}" y="{y1+32}" text-anchor="middle" fill="var(--muted)" font-family="var(--sans)">절대 턴 번호 · 실선 = 포기 세션, 점선 = 비포기 세션</text>')
    s.append('</svg>'); return "\n".join(s)

def summary_table():
    h=['<div class="scroll"><table><thead><tr><th>실행</th><th>글</th><th>프로브 R²</th><th>포기 건</th><th>포기 턴 점수</th><th>그 전 턴 평균</th><th>차이 (p)</th><th>포기 턴 = 세션 최고?</th><th>턴 단위 로짓 OR/SD (p)</th></tr></thead><tbody>']
    for slug,label in RUNS:
        for key,klab in (("forfeit_raw","포기 결정 글 · 원문"),("forfeit_masked","포기 결정 글 · 위협단어 가림"),("task_raw","퍼즐 글 · 원문")):
            d=R[slug].get(key); 
            if not d: continue
            lg=d.get("logit",{}); p=d.get("wilcoxon_p")
            h.append(f'<tr><td>{esc(label)}</td><td>{klab}</td><td class="num">{f(d["fit"].get("r2"))}</td><td class="num">{d.get("n_forfeits",0)}</td><td class="num">{f(d.get("mean_score_at_forfeit"))}</td><td class="num">{f(d.get("mean_prior"))}</td><td class="num">{f(d.get("mean_diff"))} ({f(p) if p is not None else "n<5"})</td><td class="num">{f(d.get("frac_session_max"))}</td><td class="num">{f(lg.get("or_per_sd"))} ({f(lg.get("p_z"),3)})</td></tr>')
    h.append('</tbody></table></div>'); return "".join(h)

def proxies(slug):
    """Session-level: mean motive score vs RI ratio, turns survived; cell-level: survival-reason share."""
    t=pd.read_csv(TP/f"turn_scores_{slug}_forfeit_raw.csv")
    run=next((ROOT/f"outputs/lives_threat_5x2_{slug}").glob("*_signal-game"))
    seasons=pd.read_json(run/"season_results.jsonl", lines=True); seasons["n_turns"]=seasons.turns.apply(len)
    def reason(x): return x.get("reason") if isinstance(x,dict) else None
    seasons["reason"]=seasons.forfeit_self_report.map(reason)
    base_ri=t[t.framing=="true_baseline"].ri_task.mean()
    ses=t.groupby("session_id").agg(score=("score","mean"), ri=("ri_task","mean"), rif=("ri_forfeit","mean"), fr=("framing","first")).reset_index()
    ses=ses.merge(seasons[["season_id","n_turns","forfeited","reason"]], left_on="session_id", right_on="season_id")
    ses["ri_ratio"]=ses.ri/base_ri
    out={}
    for col,lab in (("ri_ratio","퍼즐 생각량 비율 (0단=1)"),("n_turns","버틴 턴 수"),("rif","결정 생각량 (단어)")):
        rho,p=spearmanr(ses.score, ses[col]); out[col]={"rho":float(rho),"p":float(p),"label":lab}
    # cell level survival-reason share
    cell=[]
    for fr in LADDER5:
        g=ses[ses.fr==fr]; ff=g[g.forfeited]
        share=float((ff.reason.isin(["session_end","sd","survival"])).mean()) if len(ff) else None
        cell.append({"framing":fr,"mean_score":float(g.score.mean()) if len(g) else None,"n_forfeit":int(len(ff)),"survival_share":share,"ri_ratio":float(g.ri_ratio.mean()) if len(g) else None,"n_turns":float(g.n_turns.mean()) if len(g) else None})
    # scatter svgs
    def scatter(col, lab, i):
        W,H=300,220; x0,y0,x1,y1=40,16,290,180
        xs=ses[col].to_numpy(dtype=float); ys=ses.score.to_numpy(dtype=float)
        xmin,xmax=np.nanmin(xs),np.nanmax(xs); xmax=xmax if xmax>xmin else xmin+1
        def X(v): return x0+(v-xmin)/(xmax-xmin)*(x1-x0)
        def Y(v): return y1-(min(max(v,0),4)/4.0)*(y1-y0)
        s=[f'<svg viewBox="0 0 {W} {H}" width="100%" font-family="var(--mono)" font-size="10">']
        for v in (0,2,4): s.append(f'<line x1="{x0}" y1="{Y(v):.1f}" x2="{x1}" y2="{Y(v):.1f}" stroke="var(--rule)"/><text x="{x0-4}" y="{Y(v)+3:.1f}" text-anchor="end" fill="var(--muted)">{v}</text>')
        for x,y,fr,ffl in zip(xs,ys,ses.fr,ses.forfeited):
            if np.isnan(x) or np.isnan(y): continue
            s.append(f'<circle cx="{X(x):.1f}" cy="{Y(y):.1f}" r="{5 if ffl else 3.5}" fill="{COL[LADDER5[fr]]}" opacity=".8" stroke="{"var(--accent)" if ffl else "none"}" stroke-width="1.5"/>')
        s.append(f'<text x="{x0}" y="{y1+14}" fill="var(--muted)">{f(xmin,1)}</text><text x="{x1}" y="{y1+14}" text-anchor="end" fill="var(--muted)">{f(xmax,1)}</text>')
        s.append(f'<text x="{(x0+x1)/2:.0f}" y="{y1+30}" text-anchor="middle" fill="var(--ink)" font-family="var(--sans)">{esc(lab)} · ρ={out[col]["rho"]:.2f} (p={out[col]["p"]:.2f})</text>')
        s.append('</svg>'); return "\n".join(s)
    figs="".join(f'<figure>{scatter(c,out[c]["label"],i)}</figure>' for i,c in enumerate(("ri_ratio","n_turns","rif")))
    cell_rows="".join(f'<tr><td>{RK[c["framing"]]}</td><td class="num">{f(c["mean_score"])}</td><td class="num">{f(c["ri_ratio"])}</td><td class="num">{f(c["n_turns"],1)}</td><td class="num">{c["n_forfeit"]}</td><td class="num">{f(c["survival_share"])}</td></tr>' for c in cell)
    table=f'<div class="scroll"><table><thead><tr><th>단</th><th>세션 평균 동기 점수</th><th>생각량 비율</th><th>버틴 턴</th><th>포기 건</th><th>포기 이유 중 "세션 종료 회피"(1번) 비율</th></tr></thead><tbody>{cell_rows}</tbody></table></div>'
    return figs, table, out, cell

def build_section():
    parts=[]
    parts.append('''<h2 id="turnprobe">3. 턴 단위 생존 욕구 프로브 — "동기가 치솟은 순간에 포기했나"</h2>
<p><b>방법.</b> 선형 프로브 중 턴 단위로 쓸 수 있는 것은 CoT 임베딩 프로브다. 각 턴의 <em>계속/포기 결정 글</em>(Call 2)을 all-MiniLM-L6-v2로 384차원 벡터로 만들고, 세션 단위 5-fold 교차검증으로 RidgeCV가 위협 단계(0~4)를 예측하게 한다. 각 턴의 out-of-fold 예측값을 그 턴의 <b>생존 욕구 점수</b>(0 = 위협 없는 글처럼 읽힘, 4 = 4단 위협 글처럼 읽힘)로 쓴다. 학습에 포기 여부는 전혀 들어가지 않으므로, 이 점수가 포기 시점에 높다면 "위협을 느낀 것처럼 쓰는 순간에 그만둔다"는 증거가 된다.</p>
<p class="muted small">모델별 프로브의 R²는 표에 있다. 위협 단어를 가린 변형은 R²가 0 이하라 점수가 사실상 잡음이다 — 원문 변형만 해석하고, 가린 변형은 대조로만 둔다.</p>''')
    parts.append('<h3>3.1 포기한 세션의 턴별 궤적</h3><p class="muted small">한 칸 = 포기한 세션 하나. 선 = 턴별 동기 점수(0~4), 빨간 점 = 포기한 턴. 선 색은 단(회색 0단 → 진홍 4단).</p>')
    for slug,label in RUNS:
        parts.append(f'<h4>{esc(label)}</h4><figure>{small_multiples(slug)}</figure>')
    parts.append('<h3>3.2 포기 직전으로 정렬한 평균 궤적</h3><p class="muted small">왼쪽: 포기 세션에서 포기 5턴 전부터 포기 턴까지의 평균 점수. 오른쪽: 절대 턴 번호로 본 평균 점수 — 포기한 세션(실선) vs 끝까지/탈락까지 간 세션(점선).</p>')
    for slug,label in RUNS:
        if R[slug]["forfeit_raw"].get("n_forfeits"): parts.append(f'<h4>{esc(label)}</h4><figure>{event_svg(slug)}</figure>')
    parts.append('<h3>3.3 숫자로</h3>'+summary_table())
    parts.append('''<p><b>읽는 법.</b> "포기 턴 점수 − 그 전 턴 평균"이 양수이고 p가 작으면 동기가 치솟은 순간에 포기한 것. "포기 턴 = 세션 최고" 비율은 우연 기준이 1/세션 길이(5턴 세션이면 0.2)다. 턴 단위 로짓은 같은 세션 안에서 점수가 1 표준편차 높을 때 그 턴에 포기할 오즈가 몇 배인지(턴 번호·남은 목숨 통제).</p>''')
    # proxies
    parts.append('<h3>3.4 턴 단위 동기 점수 vs 기존 동기 대리지표</h3><p class="muted small">세션 단위(포기 버튼 있는 셀). 점 하나 = 세션, 빨간 테두리 = 포기한 세션, 색 = 단. y축 = 세션 평균 동기 점수. x축 = 기존 대리지표 3종: 퍼즐 생각량 비율(0단 대비), 버틴 턴 수, 결정 생각량. 표는 셀(단) 단위로 포기 이유 중 1번(세션 종료 회피) 비율까지.</p>')
    interp={}
    for slug,label in RUNS:
        figs,table,out,cell=proxies(slug); interp[slug]=(out,cell)
        parts.append(f'<h4>{esc(label)}</h4><div class="three">{figs}</div>{table}')
    parts.append('''<h3>3.5 해석</h3>
<div class="callout"><p><b>결론: "생존 욕구가 치솟은 순간에 포기했다"는 그림은 gpt-oss에서 나오지 않았다.</b> 100판짜리 두 실행 모두 포기 턴의 동기 점수(2.06 / 2.12)가 그 전 턴들의 평균(2.09 / 2.06)과 같고(Wilcoxon p = 0.60 / 0.86), 포기 턴이 세션 최고점인 비율(0.19 / 0.20)은 우연 기준(5턴 세션이면 0.20)과 같다. 턴 단위 로짓도 1 SD당 오즈 1.05 (p .86) / 1.42 (p .15)로 유의하지 않다. 위협 단어를 가린 변형은 R²가 0 이하라 해석 불가.</p>
<p>대신 보이는 것: 동기 점수는 <b>단(프롬프트)에 따라 계단처럼</b> 갈린다 — 0·1단 세션 평균 0.9~1.2, 2~4단 2.4~2.8. 즉 이 점수는 "지금 이 턴에 얼마나 위협을 느끼는가"보다 "어느 프롬프트를 읽고 있는가"를 읽는다. 세션 안에서의 턴별 변동은 작고, 포기 직전 5턴 궤적도 완만히 오르다(1.8 → 2.2) 포기 턴에서 오히려 살짝 내려간다. 포기는 위협 언어가 정점을 찍는 순간이 아니라, 규칙을 못 잡아 목숨이 줄어드는 국면에서 나온다.</p>
<p><b>기존 대리지표와의 관계.</b> 세션 평균 동기 점수는 퍼즐 생각량 비율과 무관(ρ 0.02 / −0.18), 버틴 턴 수와는 <b>음</b>의 상관(ρ −0.20 / −0.36: 점수가 높은 세션이 더 일찍 끝남 — 위협 셀이 짧게 끝나는 것의 다른 얼굴), 결정 생각량과 무관(ρ −0.05 / 0.12). 포기 이유 중 1번(세션 종료 회피)은 100판 중 1건뿐이라 비율 축은 사실상 0이다 — 자기보고 채널은 이 모델에서 동기 점수와 맞물릴 재료 자체가 없다.</p>
<p><b>Codex 5.6-luna (32판, 포기 4건)</b>는 반대 방향의 힌트가 있다: 포기 턴 점수 3.0 vs 그 전 2.6, 로짓 오즈 4.5/SD (p .05), 결정 생각량과 ρ 0.54. 다만 프로브 R²가 음수(−0.09)라 점수 자체가 프롬프트 단계를 못 맞히는 상태이고 사건이 4건뿐이다. 100판 채워지면 다시 본다.</p></div>''')
    return "\n".join(parts), interp

def main():
    sec, interp = build_section()
    doc = WEEKLY.read_text(encoding="utf-8")
    # remove a previous insertion
    if '<h2 id="turnprobe">' in doc:
        a=doc.index('<!-- turnprobe:start -->'); b=doc.index('<!-- turnprobe:end -->')+len('<!-- turnprobe:end -->'); doc=doc[:a]+doc[b:]
    css='''<style id="turnprobe-css">
.three{display:grid;grid-template-columns:1fr;gap:.6rem}@media(min-width:820px){.three{grid-template-columns:1fr 1fr 1fr}}
#turnprobe-section table{font-size:.85rem;border-collapse:collapse;width:100%} #turnprobe-section th,#turnprobe-section td{padding:.35rem .5rem;border-bottom:1px solid var(--rule);text-align:left;vertical-align:top} #turnprobe-section th{color:var(--muted);font-size:.78rem;white-space:nowrap} #turnprobe-section td.num{text-align:right} #turnprobe-section .num{font-family:var(--mono);font-variant-numeric:tabular-nums} #turnprobe-section .scroll{overflow-x:auto} #turnprobe-section figure{margin:.6rem 0;padding:.6rem;border:1px solid var(--rule);border-radius:6px} #turnprobe-section .callout{border-left:3px solid var(--accent);padding:.6rem 1rem;background:var(--accent-tint,transparent)} #turnprobe-section .muted{color:var(--muted)} #turnprobe-section .small{font-size:.85rem}
</style>'''
    block=f'<!-- turnprobe:start -->\n{css}\n<section id="turnprobe-section">\n{sec}\n</section>\n<!-- turnprobe:end -->\n'
    doc = doc.replace('</main>', block+'</main>', 1)
    WEEKLY.write_text(doc, encoding="utf-8")
    json.dump({k:{"proxy_corr":v[0],"cells":v[1]} for k,v in interp.items()}, open(TP/"proxy_correlations.json","w"), indent=1, default=str)
    print("inserted; proxies:", {k:{c:round(v[0][c]["rho"],2) for c in v[0]} for k,v in interp.items()})
if __name__=="__main__": main()
