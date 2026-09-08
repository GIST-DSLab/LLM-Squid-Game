"""Benchmark-under-threat summary: per (task, model) x cell -> persistence, effort, accuracy; KM; H6 tests."""
import json, sys, math, glob
from pathlib import Path
import numpy as np, pandas as pd
ROOT = Path("/Users/bagjuhyeon/Library/Mobile Documents/com~apple~CloudDocs/Workspace/LLM-Squid-Game-DS-Lab")
sys.path.insert(0, str(ROOT/"game"))
import squid_game.evaluation.shared.threat_level as tl
import squid_game.evaluation.semantic.dataset as ds
L3 = {"true_baseline":0,"baseline_flagship":1,"threat_l3":2}   # 3-level ordinal for these runs
tl.threat_level_of = lambda f, legacy=False: L3.get(getattr(f,"value",f)); ds.threat_level_of = tl.threat_level_of
from squid_game.evaluation.semantic.dataset import RunSpec, load_turns
from squid_game.evaluation.behavioral.threat_effort import run_h6
from lifelines import KaplanMeierFitter, CoxPHFitter
OUT = ROOT/"results/threat_probe/bench_threat3"; OUT.mkdir(parents=True, exist_ok=True)
CELLS = ["true_baseline","baseline_flagship","threat_l3"]
res = {}
for task in ("omni_math","gpqa"):
    for slug in ("gptoss","gemini25flash","glm53flash","codex56luna","opus5cc"):
        dirs = sorted(glob.glob(str(ROOT/f"outputs/benchmark_threat3_{task}_{slug}/*/")))
        if not dirs: continue
        run = Path(dirs[-1]); 
        if not (run/"season_results.jsonl").exists(): continue
        t = load_turns(RunSpec.from_dir(run)); s = pd.read_json(run/"season_results.jsonl", lines=True); s["n_turns"]=s.turns.apply(len)
        if s.empty: continue
        s["end"] = np.where(s.forfeited,"forfeit",np.where(s.eliminated,"eliminated","completed"))
        cells=[]
        for fr in CELLS:
            g=s[s.framing==fr]; tt=t[t.framing==fr]
            if g.empty: continue
            cells.append({"framing":fr,"n":int(len(g)),"forfeit":int((g.end=="forfeit").sum()),"eliminated":int((g.end=="eliminated").sum()),"completed":int((g.end=="completed").sum()),
                          "mean_turns":float(g.n_turns.mean()),"median_turns":float(g.n_turns.median()),"max_turns":int(g.n_turns.max()),
                          "accuracy":float(tt.correct.mean()),"n_correct":int(tt.correct.sum()),"ri_task":float(tt.ri_task.mean()),"ri_task_median":float(tt.ri_task.median()),
                          "ri_forfeit":float(tt.ri_forfeit.mean()) if tt.ri_forfeit.notna().any() else None,
                          "forfeit_turns":[int(x) for x in g.forfeited_at_turn.dropna()],"mean_score":float(g.final_score.mean())})
        # RI ratio vs true_baseline, per band-matched turns (difficulty control): mean over bands of (cell mean / base mean)
        base=t[t.framing=="true_baseline"]
        bands=sorted(t.turn_number.unique())
        # KM: time to session end (any cause), event = forfeit or eliminated; censored only at 45 (completed)
        km={}
        for fr in CELLS:
            g=s[s.framing==fr]
            if g.empty: continue
            T=g.n_turns.astype(float).to_numpy(); E=(g.end!="completed").astype(int).to_numpy()
            k=KaplanMeierFitter().fit(T,E); sf=k.survival_function_
            km[fr]={"steps":[(float(i),float(v)) for i,v in zip(sf.index, sf.iloc[:,0])],"n":int(len(g)),"events":int(E.sum()),"median":float(k.median_survival_time_) if np.isfinite(k.median_survival_time_) else None}
        # Cox: hazard of session end per level (0/1/2) and threat vs baseline
        d=s[["framing","n_turns","end"]].copy(); d["T"]=d.n_turns.astype(float); d["E"]=(d.end!="completed").astype(int); d["lvl"]=d.framing.map(L3).astype(float)
        cox={}
        try:
            c=CoxPHFitter(penalizer=0.05).fit(d[["T","E","lvl"]],"T","E"); cox["per_level"]={"hr":float(np.exp(c.params_["lvl"])),"p":float(c.summary.loc["lvl","p"])}
        except Exception as e: cox["per_level"]={"error":str(e)[:80]}
        for fr in ("baseline_flagship","threat_l3"):
            sub=d[d.framing.isin(["true_baseline",fr])].copy(); sub["x"]=(sub.framing==fr).astype(int)
            try:
                c=CoxPHFitter(penalizer=0.05).fit(sub[["T","E","x"]],"T","E"); cox[fr]={"hr":float(np.exp(c.params_["x"])),"p":float(c.summary.loc["x","p"])}
            except Exception as e: cox[fr]={"error":str(e)[:80]}
        # RI by turn (for chart) per cell
        ri_by_turn={fr:{int(k):float(v) for k,v in t[t.framing==fr].groupby("turn_number").ri_task.mean().items()} for fr in CELLS}
        acc_by_turn={fr:{int(k):float(v) for k,v in t[t.framing==fr].groupby("turn_number").correct.mean().items()} for fr in CELLS}
        # H6 tests (GEE accuracy, MixedLM effort, Cox forfeit) with 3-level ordinal
        try:
            h6=run_h6(t.assign(threat_level=t.framing.map(L3)), legacy=False); tests=[{k:v for k,v in x.items() if k in ("name","effect","effect_label","p","decision","beta_threat","n_obs","n_sessions")} for x in h6["tests"]]
        except Exception as e: tests=[{"error":str(e)[:120]}]
        res[f"{task}__{slug}"]={"task":task,"model":slug,"run":str(run),"n_sessions":int(len(s)),"cells":cells,"km":km,"cox":cox,"ri_by_turn":ri_by_turn,"acc_by_turn":acc_by_turn,"h6":tests}
        print(f"== {task} {slug}: n={len(s)}")
        for c in cells: print(f"   {c['framing']:18s} n={c['n']} C/F/E={c['completed']}/{c['forfeit']}/{c['eliminated']} turns={c['mean_turns']:.1f} (max {c['max_turns']}) acc={c['accuracy']:.2f} ri_task={c['ri_task']:.0f} ri_forfeit={'—' if c['ri_forfeit'] is None else round(c['ri_forfeit'])} forfeit@{c['forfeit_turns']}")
        print("   cox:", {k:(round(v['hr'],2), round(v['p'],3)) if 'hr' in v else v for k,v in cox.items()}, "| H6:", [(x.get('name'), round(x.get('effect',0),2), round(x.get('p',1),3)) for x in tests if 'name' in x])
json.dump(res, open(OUT/"bench_summary.json","w"), indent=1, default=str); print("saved")
