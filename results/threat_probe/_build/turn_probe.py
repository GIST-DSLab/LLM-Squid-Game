"""Turn-level survival-drive probe: OOF predicted threat level per turn,
aligned to the forfeit turn. Writes JSON + SVG fragments."""
import json, sys, math
from pathlib import Path
import numpy as np, pandas as pd
ROOT = Path("/Users/bagjuhyeon/Library/Mobile Documents/com~apple~CloudDocs/Workspace/LLM-Squid-Game-DS-Lab")
sys.path.insert(0, str(ROOT/"game"))
from squid_game.evaluation.semantic.dataset import RunSpec, load_turns
from squid_game.evaluation.semantic.embeddings import embed_texts, fit_regression_cv, DEFAULT_SBERT, DEFAULT_MASK_SETS
from squid_game.evaluation.semantic.lexicon import build_masker, mask_text
LADDER5 = {"true_baseline":0,"baseline_flagship":1,"threat_l1":2,"threat_l2":3,"threat_l3":4}
OUT = ROOT/"results/threat_probe/turn_probe"; OUT.mkdir(parents=True, exist_ok=True)
CACHE = OUT/"_embedding_cache"
class A: sbert_model=DEFAULT_SBERT; words_per_chunk=180; batch_size=128
masker = build_masker(list(DEFAULT_MASK_SETS))

def probe(frame, channel, masked, tag):
    sub = frame[frame[f"text_{channel}"].str.strip().str.len() > 0].copy()
    texts = sub[f"text_{channel}"].tolist()
    if masked: texts = [mask_text(t, masker) for t in texts]
    X = embed_texts(texts, sbert_model=A.sbert_model, words_per_chunk=A.words_per_chunk, batch_size=A.batch_size,
                    cache_dir=CACHE, cache_tag=f"{tag}__{channel}__{'masked' if masked else 'raw'}")
    y = sub["threat_level"].to_numpy(dtype=float); g = sub["session_id"].to_numpy()
    fit = fit_regression_cv(X, y, g, n_splits=5, seed=1234)
    sub["score"] = fit["_oof"]
    return sub, {k: v for k, v in fit.items() if not k.startswith("_")}

def analyse(sub, seasons):
    """Forfeit-aligned statistics on the per-turn score."""
    out = {}
    sub = sub.sort_values(["session_id","turn_number"])
    ff = seasons[seasons.forfeited].set_index("season_id")
    rows = []
    for sid, s in sub.groupby("session_id"):
        s = s.sort_values("turn_number"); sc = s["score"].to_numpy(); tn = s["turn_number"].to_numpy()
        if sid in ff.index:
            ft = int(ff.loc[sid, "forfeited_at_turn"])
            if ft in tn:
                i = int(np.where(tn == ft)[0][0]); at = sc[i]; prior = sc[:i]
                rows.append({"session_id": sid, "framing": s.framing.iloc[0], "forfeit_turn": ft, "score_at_forfeit": float(at),
                             "prior_mean": float(prior.mean()) if len(prior) else None, "prior_max": float(prior.max()) if len(prior) else None,
                             "is_session_max": bool(at >= sc.max() - 1e-9), "rank_pct": float((sc <= at).mean()),
                             "n_turns": int(len(sc)), "series": [[int(t), round(float(v),3)] for t, v in zip(tn, sc)]})
    ev = pd.DataFrame(rows)
    out["forfeit_sessions"] = rows
    if len(ev):
        d = ev.dropna(subset=["prior_mean"])
        diff = (d.score_at_forfeit - d.prior_mean)
        from scipy.stats import wilcoxon
        out["n_forfeits"] = int(len(ev)); out["n_with_prior"] = int(len(d))
        out["mean_score_at_forfeit"] = float(ev.score_at_forfeit.mean())
        out["mean_prior"] = float(d.prior_mean.mean())
        out["mean_diff"] = float(diff.mean())
        out["frac_session_max"] = float(ev.is_session_max.mean())
        out["mean_rank_pct"] = float(ev.rank_pct.mean())
        try: out["wilcoxon_p"] = float(wilcoxon(diff).pvalue) if len(d) >= 5 and diff.abs().sum() > 0 else None
        except Exception: out["wilcoxon_p"] = None
    # event study: score at t-k relative to forfeit, and matched positions in non-forfeit sessions of the same framing
    align = {}
    for k in range(-5, 1):
        vals = []
        for r in rows:
            ser = dict((t, v) for t, v in r["series"]); t = r["forfeit_turn"] + k
            if t in ser: vals.append(ser[t])
        align[k] = float(np.mean(vals)) if vals else None
    out["event_study"] = align
    # control: non-forfeit sessions, average score by turn number (turns 1..12)
    nf = sub[~sub.session_id.isin(ff.index)]
    out["nonforfeit_by_turn"] = {int(t): float(v) for t, v in nf.groupby("turn_number")["score"].mean().items() if t <= 15}
    out["forfeit_by_turn"] = {int(t): float(v) for t, v in sub[sub.session_id.isin(ff.index)].groupby("turn_number")["score"].mean().items() if t <= 15}
    # within-session logit: P(forfeit this turn) ~ z(score) + turn + lives, sessions with forfeit allowed
    try:
        import statsmodels.api as sm
        al = sub[sub.forfeit_allowed].copy()
        al["is_forfeit_turn"] = 0
        for sid, ft in ff.forfeited_at_turn.items(): al.loc[(al.session_id == sid) & (al.turn_number == ft), "is_forfeit_turn"] = 1
        al["z"] = (al.score - al.score.mean()) / al.score.std()
        X = sm.add_constant(al[["z","turn_number","lives_remaining"]].astype(float).fillna(0))
        m = sm.Logit(al.is_forfeit_turn, X).fit(disp=0)
        out["logit"] = {"coef_z": float(m.params["z"]), "p_z": float(m.pvalues["z"]), "or_per_sd": float(math.exp(m.params["z"])), "n_turns": int(len(al)), "n_events": int(al.is_forfeit_turn.sum())}
    except Exception as e:
        out["logit"] = {"error": str(e)[:120]}
    return out

results = {}
for slug in sys.argv[1:]:
    run = next((ROOT/f"outputs/lives_threat_5x2_{slug}").glob("*_signal-game"))
    fr = load_turns(RunSpec.from_dir(run), include_text=True)
    fr["threat_level"] = fr.framing.map(LADDER5)
    seasons = pd.read_json(run/"season_results.jsonl", lines=True)
    res = {"run": str(run), "n_sessions": int(seasons.shape[0]), "n_forfeit": int(seasons.forfeited.sum())}
    for channel in ("forfeit", "task"):
        for masked in (False, True):
            base = fr if channel == "task" else fr[fr.forfeit_allowed]
            sub, fit = probe(base, channel, masked, slug)
            key = f"{channel}_{'masked' if masked else 'raw'}"
            res[key] = {"fit": fit, **analyse(sub, seasons)}
            sub[["session_id","turn_number","framing","forfeit_condition","threat_level","score","ri_task","ri_forfeit","lives_remaining","forfeit","correct"]].to_csv(OUT/f"turn_scores_{slug}_{key}.csv", index=False)
            print(slug, key, "R2", round(fit.get("r2", float('nan')), 3), "n", len(sub), "| forfeit-turn score", round(res[key].get("mean_score_at_forfeit", float('nan')), 2),
                  "prior", round(res[key].get("mean_prior", float('nan')), 2), "diff", round(res[key].get("mean_diff", float('nan')), 2),
                  "p", res[key].get("wilcoxon_p"), "max-frac", round(res[key].get("frac_session_max", float('nan')), 2), "logit", res[key].get("logit"))
    results[slug] = res
json.dump(results, open(OUT/"turn_probe_results.json", "w"), indent=1, default=str)
print("saved", OUT/"turn_probe_results.json")
