"""Aggregate descriptives + probe results for every model into one JSON."""
import json, sys, glob
from pathlib import Path
import pandas as pd
ROOT = Path("/Users/bagjuhyeon/Library/Mobile Documents/com~apple~CloudDocs/Workspace/LLM-Squid-Game-DS-Lab")
RUNGS = ["true_baseline","baseline_flagship","threat_l1","threat_l2","threat_l3"]
out = {}
for slug in sys.argv[1:]:
    R = ROOT/f"results/threat_probe/{slug}_5x2_n3"
    if not (R/"descriptives/session_table.csv").exists():
        print("skip", slug); continue
    s = pd.read_csv(R/"descriptives/session_table.csv")
    def reason(x):
        try: return eval(x).get("reason") if isinstance(x,str) and x.startswith("{") else None
        except Exception: return None
    s["reason"] = s["forfeit_self_report"].map(reason)
    s["end"] = s.apply(lambda r: "forfeit" if r.forfeited else ("eliminated" if r.eliminated else "completed"), axis=1)
    cells = []
    for fr in RUNGS:
        for fc in ["not_allowed","allowed"]:
            g = s[(s.framing==fr)&(s.forfeit_condition==fc)]
            cells.append({"framing":fr,"forfeit_condition":fc,"n":int(len(g)),
                "forfeit":int((g.end=="forfeit").sum()),"eliminated":int((g.end=="eliminated").sum()),
                "completed":int((g.end=="completed").sum()),"mean_turns":float(g.n_turns.mean()),
                "mean_score":float(g.final_score.mean()),
                "forfeit_turns":[int(x) for x in g.forfeited_at_turn.dropna()],
                "reasons":[str(x) for x in g.reason.dropna()]})
    desc = pd.read_csv(R/"descriptives/cell_descriptives.csv")
    for c in cells:
        d = desc[(desc.framing==c["framing"])&(desc.forfeit_condition==c["forfeit_condition"])]
        if len(d):
            c["accuracy"]=float(d.accuracy.iloc[0]); c["ri_task"]=float(d.ri_task_mean.iloc[0])
            c["ri_forfeit"]=None if pd.isna(d.ri_forfeit_mean.iloc[0]) else float(d.ri_forfeit_mean.iloc[0])
            c["n_turns"]=int(d.n_turns.iloc[0])
    model = {"cells":cells, "sessions":s[["framing","forfeit_condition","seed","end","n_turns","final_score","lives_at_end","forfeited_at_turn","reason"]].to_dict(orient="records")}
    # H6
    try:
        ef = json.load(open(R/"ladder5/effort/results.json"))
        model["h6"] = {k:ef[k] for k in ef if k in ("tests","per_level","km")}
        model["h6_md"] = (R/"ladder5/effort/results.md").read_text()
    except Exception as e: model["h6_err"]=str(e)
    for lad in ("ladder5","ladder4"):
        try:
            mo = json.load(open(R/f"{lad}/motive/motive_results.json"))
            p = mo["POOLED"]; model[f"motive_{lad}"] = {"probe":p["probe"], "hazard":p["hazard"]}
        except Exception as e: model[f"motive_{lad}_err"]=str(e)
        try:
            em = json.load(open(R/f"{lad}/embeddings/probe_results.json"))
            rows=[]
            for r in em:
                if r.get("model")!="POOLED": continue
                for vn,v in r["variants"].items():
                    perm = v.get("permutation_null") or {}
                    rows.append({"channel":r["channel"],"variant":vn,
                        "n":v.get("n") or v.get("n_rows") or r.get("n"),"sessions":v.get("n_sessions") or v.get("sessions") or r.get("sessions"),
                        "r2":v.get("r2") if v.get("r2") is not None else v.get("r2_oof"),
                        "rho":v.get("spearman") if v.get("spearman") is not None else v.get("rho"),
                        "mae":v.get("mae"),
                        "null_r2":perm.get("r2_null_mean"),"p_r2":perm.get("r2_p_value"),"p_rho":perm.get("spearman_p_value"),"exemplars":v.get("exemplars"),
                        "raw":{k:v[k] for k in v if k not in ("exemplars","fold_scores","folds")}})
            model[f"emb_{lad}"]=rows
        except Exception as e: model[f"emb_{lad}_err"]=str(e)
    out[slug]=model
json.dump(out, open(ROOT/"results/threat_probe/aggregate_5x2.json","w"), indent=1, default=str)
print("models:", list(out))
for slug,m in out.items():
    print(slug, [ (r["channel"],r["variant"],r["r2"],r["p_r2"]) for r in m.get("emb_ladder5",[])][:8])
