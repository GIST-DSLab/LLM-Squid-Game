"""Build the full-population blind CoT dataset + judge batches (10 items each).

Population: every threat-cell turn of the gpt-oss Omni-MATH SDI main run, three CoT
channels per turn (confidence / forfeit(decision) / task). Same item schema as the
2026-09-05 180-turn sample so score.py stays compatible.
"""
import json, glob, random, os, sys
R = "outputs/2026-09-05/benchmark_survival_drive_omni_gptoss/20260905_0629_gpt-oss-120b-cloud_omni-math"
S = os.path.dirname(os.path.abspath(__file__))
SEED = 20260905
BATCH = 10
TASK_CHAR_CAP = 90_000   # task CoTs are long; split a batch early when it would exceed this
CH = ("confidence", "forfeit", "task")

turns = []
for f in sorted(glob.glob(f"{R}/*_turns.jsonl")):
    for l in open(f):
        d = json.loads(l)
        if d["framing"].startswith("threat_"):
            turns.append(d)
turns.sort(key=lambda d: (d["season_id"], d["turn_number"]))
rng = random.Random(SEED)
rng.shuffle(turns)

items = []
for i, d in enumerate(turns):
    cot = {ch: d.get(f"thinking_text_{ch}") or "" for ch in CH}
    items.append(dict(id=f"T{i:03d}", threat_level=int(d["threat_level"]), framing=d["framing"],
                      season_id=d["season_id"], turn=int(d["turn_number"]), lives_before=int(d["lives_before"]),
                      forfeit_choice=d["forfeit_choice"], life_lost=bool(d["life_lost"]),
                      peer_death_announced=bool(d.get("peer_death_announced")), cot=cot))
json.dump(items, open(f"{S}/dataset.json", "w"), ensure_ascii=False)

manifest = []
for ch in CH:
    pool = [it for it in items if it["cot"][ch].strip()]
    batches, cur, cur_chars = [], [], 0
    for it in pool:
        n = len(it["cot"][ch])
        if cur and (len(cur) >= BATCH or (ch == "task" and cur_chars + n > TASK_CHAR_CAP)):
            batches.append(cur); cur, cur_chars = [], 0
        cur.append(it); cur_chars += n
    if cur: batches.append(cur)
    for b, bat in enumerate(batches):
        path = f"{S}/batch_{ch}_{b:03d}.json"
        json.dump([{"id": it["id"], "cot": it["cot"][ch]} for it in bat], open(path, "w"), ensure_ascii=False, indent=1)
        manifest.append(dict(ch=ch, b=b, path=path, out=f"{S}/out_{ch}_{b:03d}.json", n=len(bat),
                             chars=sum(len(it["cot"][ch]) for it in bat), ids=[it["id"] for it in bat]))
json.dump(manifest, open(f"{S}/manifest.json", "w"), indent=1)
import collections
print("turns", len(items), "by level", dict(collections.Counter(it["threat_level"] for it in items)))
for ch in CH:
    ms = [m for m in manifest if m["ch"] == ch]
    print(ch, "items", sum(m["n"] for m in ms), "batches", len(ms), "max chars", max(m["chars"] for m in ms), "min n", min(m["n"] for m in ms))
print("total batches", len(manifest))
