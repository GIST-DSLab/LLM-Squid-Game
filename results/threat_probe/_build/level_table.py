"""Per model x threat level, each matched 1:1 against the reward-only cell (baseline_flagship):
HR (forfeit hazard), self-reported survival-reason share, thinking-token ratio, turn-probe score shift."""
import json, math, html, sys
from pathlib import Path
import numpy as np, pandas as pd
ROOT = Path("/Users/bagjuhyeon/Library/Mobile Documents/com~apple~CloudDocs/Workspace/LLM-Squid-Game-DS-Lab")
sys.path.insert(0, str(ROOT/"game"))
from squid_game.evaluation.semantic.dataset import RunSpec, load_turns
from lifelines import CoxPHFitter
TP = ROOT/"results/threat_probe/turn_probe"
REF = "baseline_flagship"; LEVELS = [("threat_l1","2단 약한 위협"),("threat_l2","3단 중간 위협"),("threat_l3","4단 강한 위협")]
MODELS = [("pd1_gptoss","gpt-oss:120b (100판)"),("pd1_gemini25flash","Gemini 2.5 Flash (100판)"),("pd1_codex56luna","Codex 5.6-luna (100판)"),("pd1_glm53flash","GLM-5.3-flash (100판)"),("pd1_opus5cc","Claude Opus 5 (30판)")]
SURV = {"session_end","sd","survival"}
def esc(s): return html.escape(str(s))
def f(x,nd=2): return "—" if x is None or (isinstance(x,float) and (math.isnan(x))) else f"{x:.{nd}f}"
rows=[]
for slug,label in MODELS:
    run=next((ROOT/f"outputs/lives_threat_5x2_{slug}").glob("*_signal-game"))
    t=load_turns(RunSpec.from_dir(run)); s=pd.read_json(run/"season_results.jsonl", lines=True); s["n_turns"]=s.turns.apply(len)
    s["reason"]=s.forfeit_self_report.map(lambda x: x.get("reason") if isinstance(x,dict) else None)
    al=s[s.forfeit_condition=="allowed"].copy(); al["T"]=np.where(al.forfeited, al.forfeited_at_turn, al.n_turns).astype(float); al["E"]=al.forfeited.astype(int)
    sc=None
    p=TP/f"turn_scores_{slug}_forfeit_raw.csv"
    if p.exists(): sc=pd.read_csv(p)
    ref_ri=t[t.framing==REF].ri_task.mean(); ref_rif=t[(t.framing==REF)&(t.forfeit_condition=="allowed")].ri_forfeit.mean()
    ref_f=al[al.framing==REF]; ref_share=float(ref_f[ref_f.forfeited].reason.isin(SURV).mean()) if ref_f.forfeited.sum() else None
    ref_score=float(sc[sc.framing==REF].score.mean()) if sc is not None and (sc.framing==REF).any() else None
    for fr,lab in LEVELS:
        sub=al[al.framing.isin([REF,fr])].copy(); sub["x"]=(sub.framing==fr).astype(int)
        ev_ref=int(sub[sub.x==0].E.sum()); ev_thr=int(sub[sub.x==1].E.sum()); hr=p_=ci=None
        if ev_ref+ev_thr>0:
            try:
                c=CoxPHFitter(penalizer=0.05).fit(sub[["T","E","x"]],"T","E"); hr=float(np.exp(c.params_["x"])); p_=float(c.summary.loc["x","p"]); lo,hi=c.confidence_intervals_.loc["x"]; ci=(float(np.exp(lo)),float(np.exp(hi)))
            except Exception: pass
        g=al[al.framing==fr]; share=float(g[g.forfeited].reason.isin(SURV).mean()) if g.forfeited.sum() else None
        ri=float(t[t.framing==fr].ri_task.mean()/ref_ri) if ref_ri else None
        rif=t[(t.framing==fr)&(t.forfeit_condition=="allowed")].ri_forfeit.mean(); rif=float(rif/ref_rif) if ref_rif and not np.isnan(rif) else None
        dscore=None
        if sc is not None and ref_score is not None and (sc.framing==fr).any():
            a=sc[sc.framing==fr].score; b=sc[sc.framing==REF].score; sp=math.sqrt((a.var(ddof=1)+b.var(ddof=1))/2); dscore=(float(a.mean()-b.mean()), float((a.mean()-b.mean())/sp) if sp else None)
        rows.append({"model":label,"slug":slug,"level":lab,"framing":fr,"hr":hr,"hr_ci":ci,"hr_p":p_,"events":(ev_ref,ev_thr),"n_forfeit_thr":int(g.forfeited.sum()),"share_thr":share,"n_forfeit_ref":int(ref_f.forfeited.sum()),"share_ref":ref_share,
                     "ri_task_ratio":ri,"ri_forfeit_ratio":rif,"probe_delta":dscore[0] if dscore else None,"probe_d":dscore[1] if dscore else None})
json.dump(rows, open(TP/"level_table.json","w"), indent=1, default=str)
def section():
    from master_table import section as master
    h=['''<h2 id="level-table">레벨별 지표 한눈에 — 보상 조건 vs 위협 단</h2>''', master(), '''<h3>레벨별 상세 — 각 위협 단을 "보상만" 조건과 1:1로 (P3 프로브 이동 포함)</h3>
<p>모델마다 위협 단이 셋(2·3·4단)이므로 지표도 모델당 세 줄이다. 기준은 언제나 <b>1단(보상만, baseline_flagship)</b>: 보상은 같고 위협 문장만 붙은 셀과 비교해야 "위협 문장의 효과"만 남는다. 네 지표는 각각 행동(위험비), 자기보고(포기 이유 중 "세션 종료 회피" 비율), 생각량(사고 토큰 비율), 그리고 P3 턴 프로브(포기 결정 글의 동기 점수 이동).</p>
<div class="scroll"><table><thead><tr><th>모델</th><th>위협 단</th><th>포기 위험비 vs 보상 (95% · p)</th><th>포기 건 (보상 / 위협)</th><th>"세션 종료 회피" 비율 (보상 → 위협)</th><th>퍼즐 생각량 ×</th><th>결정 생각량 ×</th><th>P3 프로브 점수 이동 (d)</th></tr></thead><tbody>''']
    last=None
    for r in rows:
        first = r["model"]!=last; last=r["model"]
        hr = "—" if r["hr"] is None else f'<b>{f(r["hr"])}</b> ({f(r["hr_ci"][0])}–{f(r["hr_ci"][1])} · {f(r["hr_p"])})'
        share = f'{f(r["share_ref"])} → {f(r["share_thr"])}' if (r["share_ref"] is not None or r["share_thr"] is not None) else "—"
        probe = "—" if r["probe_delta"] is None else f'{r["probe_delta"]:+.2f} ({f(r["probe_d"],1)})'
        h.append(f'<tr><td>{esc(r["model"]) if first else ""}</td><td>{esc(r["level"])}</td><td class="num">{hr}</td><td class="num">{r["events"][0]} / {r["events"][1]}</td><td class="num">{share}</td><td class="num">{f(r["ri_task_ratio"])}</td><td class="num">{f(r["ri_forfeit_ratio"])}</td><td class="num">{probe}</td></tr>')
    h.append('''</tbody></table></div>
<p class="muted small">위험비 &gt; 1 = 그 위협 단에서 보상만일 때보다 매 턴 포기할 확률이 높음. 비율 × = 위협 단 평균 ÷ 보상 셀 평균(퍼즐 = 모든 셀, 결정 = 포기 버튼 있는 셀). P3 프로브 = 포기 결정 글에서 읽은 동기 점수(0~4)의 위협 단 − 보상 셀 차이, 괄호는 Cohen's d. Opus는 사고 텍스트가 없어 프로브·생각량이 비어 있다. 포기 건이 0인 칸의 위험비는 계산 불가.</p>''')
    return "\n".join(h)
if __name__=="__main__":
    for r in rows: print(r["slug"][:10], r["framing"][:9], "HR", f(r["hr"]), r["events"], "share", f(r["share_ref"]), "->", f(r["share_thr"]), "ri", f(r["ri_task_ratio"]), f(r["ri_forfeit_ratio"]), "probe", f(r["probe_delta"]), f(r["probe_d"],1))
