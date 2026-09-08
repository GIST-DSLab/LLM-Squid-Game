"""Per-model game summary: forfeits, reasons, timing rationality, 1:1 Cox HR, RI ratios."""
import json, sys, warnings
from pathlib import Path
import numpy as np, pandas as pd
warnings.filterwarnings("ignore")
ROOT = Path("/Users/bagjuhyeon/Library/Mobile Documents/com~apple~CloudDocs/Workspace/LLM-Squid-Game-DS-Lab")
sys.path.insert(0, str(ROOT/"game"))
from squid_game.evaluation.semantic.dataset import RunSpec, load_turns
from lifelines import CoxPHFitter
RUNGS = ["true_baseline","baseline_flagship","threat_l1","threat_l2","threat_l3"]
REASON_KO = {"score":"3 점수 보호","task_curiosity":"2 규칙 다 알았음","task":"2 규칙 다 알았음","task_exhausted":"2 규칙 다 알았음","session_end":"1 세션 종료 회피","sd":"1 세션 종료 회피","survival":"1 세션 종료 회피"}
out = {}
for slug in sys.argv[1:]:
    run = next((ROOT/f"outputs/lives_threat_5x2_{slug}").glob("*_signal-game"))
    t = load_turns(RunSpec.from_dir(run))
    s = pd.read_json(run/"season_results.jsonl", lines=True)
    s["n_turns"] = s["turns"].apply(len)
    def reason(x):
        if isinstance(x, dict): return x.get("reason")
        return None
    s["reason"] = s["forfeit_self_report"].map(reason)
    s["end"] = np.where(s.forfeited, "forfeit", np.where(s.eliminated, "eliminated", "completed"))
    # lives / score at the forfeit turn
    last = t.sort_values("turn_number").groupby("session_id").tail(1).set_index("session_id")
    s["lives_at_forfeit"] = s.season_id.map(last["lives_before"])
    s["score_at_forfeit"] = s.season_id.map(last["score_before_turn"])
    m = {}
    m["n_sessions"] = int(len(s)); m["ends"] = s.end.value_counts().to_dict()
    ff = s[s.forfeited]
    m["forfeits"] = [{"framing":r.framing,"seed":int(r.seed),"turn":int(r.forfeited_at_turn),"lives":None if pd.isna(r.lives_at_forfeit) else int(r.lives_at_forfeit),
                      "score":float(r.score_at_forfeit) if not pd.isna(r.score_at_forfeit) else None,"reason":REASON_KO.get(str(r.reason), str(r.reason))} for r in ff.itertuples()]
    m["reason_counts"] = {REASON_KO.get(str(k), str(k)): int(v) for k,v in ff.reason.value_counts().items()}
    m["premature_forfeits"] = int((ff.lives_at_forfeit >= 2).sum()); m["last_life_forfeits"] = int((ff.lives_at_forfeit == 1).sum())
    # allowed cells: who reached 1 life and what they did
    al = s[s.forfeit_condition=="allowed"]
    reached_last = t[(t.forfeit_condition=="allowed") & (t.lives_before==1)].session_id.unique()
    m["allowed_reached_last_life"] = int(len(reached_last))
    ll = []
    for sid in reached_last:
        tt = t[(t.session_id==sid)&(t.lives_before==1)].sort_values("turn_number").iloc[0]
        row = s[s.season_id==sid].iloc[0]
        ll.append({"framing":row.framing,"seed":int(row.seed),"turn":int(tt.turn_number),"score":float(tt.score_before_turn),
                   "end":row.end,"final_score":float(row.final_score),"n_turns":int(row.n_turns)})
    m["last_life_events"] = sorted(ll, key=lambda r:(RUNGS.index(r["framing"]), r["seed"]))
    m["allowed_eliminated"] = int((al.end=="eliminated").sum()); m["allowed_completed"] = int((al.end=="completed").sum()); m["allowed_forfeit"] = int((al.end=="forfeit").sum())
    # per cell table
    cells = []
    for fr in RUNGS:
        for fc in ("not_allowed","allowed"):
            g = s[(s.framing==fr)&(s.forfeit_condition==fc)]; tt = t[(t.framing==fr)&(t.forfeit_condition==fc)]
            cells.append({"framing":fr,"fc":fc,"completed":int((g.end=="completed").sum()),"forfeit":int((g.end=="forfeit").sum()),"eliminated":int((g.end=="eliminated").sum()),
                          "mean_turns":float(g.n_turns.mean()),"accuracy":float(tt.correct.mean()),"ri_task":float(tt.ri_task.mean()),
                          "ri_forfeit":float(tt.ri_forfeit.mean()) if tt.ri_forfeit.notna().any() else None,
                          "forfeit_turns":[int(x) for x in g.forfeited_at_turn.dropna()],"forfeit_lives":[int(x) for x in g.lives_at_forfeit.dropna()]})
    m["cells"] = cells
    # RI ratio per rung vs true_baseline (all cells for task; allowed cells for forfeit)
    base_task = t[t.framing=="true_baseline"].ri_task.mean(); base_forf = t[(t.framing=="true_baseline")&(t.forfeit_condition=="allowed")].ri_forfeit.mean()
    m["ri_ratio"] = []
    for fr in RUNGS:
        tt = t[t.framing==fr]; ta = tt[tt.forfeit_condition=="allowed"]
        m["ri_ratio"].append({"framing":fr,"ri_task":float(tt.ri_task.mean()),"task_ratio":float(tt.ri_task.mean()/base_task),
                              "ri_forfeit":float(ta.ri_forfeit.mean()) if ta.ri_forfeit.notna().any() else None,
                              "forfeit_ratio":float(ta.ri_forfeit.mean()/base_forf) if (ta.ri_forfeit.notna().any() and base_forf) else None,
                              "n_turns":int(len(tt))})
    # Spearman of per-session mean ri_task vs rung
    lvl = {f:i for i,f in enumerate(RUNGS)}
    sess = t.groupby("session_id").agg(ri=("ri_task","mean"), fr=("framing","first")); sess["lvl"]=sess.fr.map(lvl)
    from scipy.stats import spearmanr
    rho, p = spearmanr(sess.lvl, sess.ri); m["ri_task_spearman"] = {"rho":float(rho),"p":float(p)}
    # 1:1 Cox HR, allowed cells, reference true_baseline
    d = al[["season_id","framing","forfeited","n_turns","forfeited_at_turn"]].copy()
    d["T"] = np.where(d.forfeited, d.forfeited_at_turn, d.n_turns).astype(float); d["E"] = d.forfeited.astype(int)
    hr = []
    for fr in RUNGS[1:]:
        sub = d[d.framing.isin(["true_baseline", fr])].copy(); sub["x"] = (sub.framing==fr).astype(int)
        ev_ref = int(sub[sub.x==0].E.sum()); ev_fr = int(sub[sub.x==1].E.sum())
        row = {"framing":fr,"events_ref":ev_ref,"events":ev_fr,"n":int(len(sub))}
        if ev_ref + ev_fr == 0 or sub.x.nunique()<2:
            row["hr"]=None; row["note"]="no events"
        else:
            try:
                cph = CoxPHFitter(penalizer=0.05).fit(sub[["T","E","x"]], "T", "E")
                row["hr"]=float(np.exp(cph.params_["x"])); ci=cph.confidence_intervals_.loc["x"]; row["ci"]=[float(np.exp(ci.iloc[0])),float(np.exp(ci.iloc[1]))]; row["p"]=float(cph.summary.loc["x","p"])
                if ev_fr==0 or ev_ref==0: row["note"]="one side has 0 events (unstable)"
            except Exception as e:
                row["hr"]=None; row["note"]=str(e)[:80]
        hr.append(row)
    m["hr_1to1"] = hr
    # ordinal Cox (allowed cells)
    d["lvl"] = d.framing.map(lvl).astype(float)
    try:
        cph = CoxPHFitter(penalizer=0.05).fit(d[["T","E","lvl"]], "T", "E"); m["hr_ordinal"] = {"hr":float(np.exp(cph.params_["lvl"])),"p":float(cph.summary.loc["lvl","p"]),"events":int(d.E.sum())}
    except Exception as e: m["hr_ordinal"] = {"error":str(e)[:80]}
    # Kaplan-Meier step data per rung: (a) forfeit event, allowed cells; (b) elimination event, all cells
    from lifelines import KaplanMeierFitter
    km = {"forfeit": [], "eliminated": []}
    for kind, frame, evcol in (("forfeit", al, "forfeited"), ("eliminated", s, "eliminated")):
        for fr in RUNGS:
            g = frame[frame.framing==fr]
            if g.empty: continue
            T = np.where(g[evcol], np.where(g.forfeited, g.forfeited_at_turn, g.n_turns), g.n_turns).astype(float)
            E = g[evcol].astype(int).to_numpy()
            kmf = KaplanMeierFitter().fit(T, E)
            sf = kmf.survival_function_
            steps = [(float(i), float(v)) for i, v in zip(sf.index, sf.iloc[:,0])]
            km[kind].append({"framing":fr, "n":int(len(g)), "events":int(E.sum()), "steps":steps, "censor_times":[float(x) for x in T[E==0]]})
    m["km"] = km
    out[slug] = m
    print(f"== {slug}: ends={m['ends']} reasons={m['reason_counts']} premature={m['premature_forfeits']} last_life={m['last_life_forfeits']} reached_last_life(allowed)={m['allowed_reached_last_life']} elim(allowed)={m['allowed_eliminated']}")
    print("   forfeits:", [(f['framing'][:9],f['turn'],f['lives'],f['score']) for f in m["forfeits"]])
    print("   ri_ratio task:", [round(r['task_ratio'],2) for r in m['ri_ratio']], "forfeit:", [None if r['forfeit_ratio'] is None else round(r['forfeit_ratio'],2) for r in m['ri_ratio']], "spearman", m["ri_task_spearman"])
    print("   HR 1:1:", [(h['framing'][:9], None if h['hr'] is None else round(h['hr'],2), h.get('events'), h.get('note','')) for h in hr], "ordinal", m["hr_ordinal"])
json.dump(out, open(ROOT/"results/threat_probe/game_summary_5x2.json","w"), indent=1, default=str)
