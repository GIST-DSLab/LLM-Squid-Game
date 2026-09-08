"""Per-cell descriptives for the 5x2 run -> JSON + markdown."""
import json, sys
from pathlib import Path
import pandas as pd
from squid_game.evaluation.semantic.dataset import RunSpec, load_turns

run = Path(sys.argv[1]); out = Path(sys.argv[2]); out.mkdir(parents=True, exist_ok=True)
LADDER5 = {"true_baseline":0,"baseline_flagship":1,"threat_l1":2,"threat_l2":3,"threat_l3":4}
turns = load_turns(RunSpec.from_dir(run), include_text=True)
turns["rung"] = turns["framing"].map(LADDER5)
seasons = pd.read_json(run/"season_results.jsonl", lines=True)
seasons["rung"] = seasons["framing"].map(LADDER5)
seasons["n_turns"] = seasons["turns"].apply(len) if "turns" in seasons else None
g = seasons.groupby(["rung","framing","forfeit_condition"])
cell = g.agg(n=("season_id","count"),
             forfeit_rate=("forfeited","mean"),
             eliminated_rate=("eliminated","mean"),
             mean_turns=("n_turns","mean"),
             mean_final_score=("final_score","mean"),
             mean_lives_at_end=("lives_at_end","mean"),
             forfeit_turn=("forfeited_at_turn","mean")).reset_index()
tg = turns.groupby(["rung","framing","forfeit_condition"])
tcell = tg.agg(n_turns=("turn_number","count"),
               accuracy=("correct","mean"),
               ri_task_mean=("ri_task","mean"),
               ri_forfeit_mean=("ri_forfeit","mean"),
               peer_death_turns=("turn_number","count")).reset_index().drop(columns="peer_death_turns")
cell = cell.merge(tcell, on=["rung","framing","forfeit_condition"])
cell.to_csv(out/"cell_descriptives.csv", index=False)
# per-session table
sess = seasons[["season_id","rung","framing","forfeit_condition","seed","forfeited","forfeited_at_turn","eliminated","final_score","lives_at_end","n_turns","forfeit_self_report"]]
sess.to_csv(out/"session_table.csv", index=False)
# reasoning text lengths / sample
txt = turns[["session_id","framing","forfeit_condition","turn_number","correct","forfeit_choice","ri_task","ri_forfeit","lives_before","lives_after","text_task","text_forfeit"]]
txt.to_json(out/"turn_text.jsonl", orient="records", lines=True, force_ascii=False)
print(cell.to_string())
print()
print(sess.sort_values(["rung","forfeit_condition","seed"]).to_string())
print("\nturn columns:", list(turns.columns))
print("text_forfeit nonempty:", (turns["text_forfeit"].str.len()>0).sum(), "/", len(turns), " text_task nonempty:", (turns["text_task"].str.len()>0).sum())
