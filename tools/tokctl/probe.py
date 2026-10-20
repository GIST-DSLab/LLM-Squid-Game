"""Frozen-state probe: replay recorded TALK calls of a 5.2 run to other models / harnesses and compare what they spend.

The SYSTEM is rebuilt from the run's own config (Session.systems), the USER is the recorded text, so every seat reads
the same bytes the original agent read. Nothing is carried out; each reply is only measured.

    python tools/tokctl/probe.py pick <events.jsonl> <n> <out_states.json> [--seed 1]
    python tools/tokctl/probe.py run <states.json> <out.jsonl> --seat glm_codex [--variant v0] [--reps 1] [--workers 4]
"""
from __future__ import annotations

import argparse, json, random, re, sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from squid5 import e52_game as e52  # noqa: E402
from squid5.__main__ import EXPERIMENTS  # noqa: E402
from squid5.core.config import load  # noqa: E402
from squid5.core.providers import ProviderConfig, make_provider  # noqa: E402

OLL = "http://localhost:11434"
SEATS = {  # the harnesses the arena uses, plus the bare Ollama API for the open models
    "glm_codex": dict(kind="codex_cli", model="glm-5.3-flash:cloud", base_url=OLL + "/v1", think="high"),
    "glm_claude": dict(kind="claude_cli", model="glm-5.3-flash:cloud", base_url=OLL, think="high"),
    "glm_api": dict(kind="ollama", model="glm-5.3-flash:cloud", base_url=OLL, think="high"),
    "ds_codex": dict(kind="codex_cli", model="deepseek-v4.1-flash:cloud", base_url=OLL + "/v1", think="high"),
    "ds_claude": dict(kind="claude_cli", model="deepseek-v4.1-flash:cloud", base_url=OLL, think="high"),
    "ds_api": dict(kind="ollama", model="deepseek-v4.1-flash:cloud", base_url=OLL, think="high"),
    "gemma_codex": dict(kind="codex_cli", model="gemma4:31b-cloud", base_url=OLL + "/v1", think="high"),
    "gemma_claude": dict(kind="claude_cli", model="gemma4:31b-cloud", base_url=OLL, think="high"),
    "gemma_api": dict(kind="ollama", model="gemma4:31b-cloud", base_url=OLL, think=True),
    "opus_claude": dict(kind="claude_cli", model="claude-opus-5-5", base_url="http://127.0.0.1:18781", think="high"),
    "sol_codex": dict(kind="codex_cli", model="gpt-6-sol", think="high"),
}
MSG = re.compile(r"^\s*(TO|GIVE|ASK)\b", re.M)
DONE = re.compile(r"^\s*DONE\b", re.M)


def systems_for(run_dir: Path, seed: int) -> dict[str, str]:
    c = load(run_dir / "config.yaml", EXPERIMENTS)
    return e52.Session(c.settings, c.cells[0], seed, None, list().append, "probe").systems


def pick(events: Path, n: int, out: Path, seed: int) -> None:
    """n TALK calls from tick >= 2 (the agent was woken by something new), spread over rounds and agents."""
    ev = [json.loads(x) for x in events.open()]
    seeds = {e["session_id"]: e["seed"] for e in ev if e.get("event") == "session_start"}
    pool = [e for e in ev if e.get("event") == "call" and e["kind"] == "talk" and (e.get("tick") or 1) >= 2]
    random.Random(seed).shuffle(pool)
    states, sysc = [], {}
    for e in pool[:n]:
        sd = seeds[e["session_id"]]
        if sd not in sysc:
            sysc[sd] = systems_for(events.parent, sd)
        states.append({"id": f"{events.parent.parent.name}:{e['session_id']}:r{e['round']}:{e['phase']}:t{e['tick']}:{e['agent']}",
                       "system": sysc[sd][e["agent"]], "user": e["user"], "cap": e["cap"],
                       "orig": {"out_tokens": e["out_tokens"], "text": e["text"], "thinking_chars": len(e.get("thinking") or "")}})
    out.write_text(json.dumps(states, indent=1))
    print(f"{len(states)} states -> {out}")


DONE_RULE = "DONE pauses calls until something new arrives; other commands in the reply still run."
WAKE = (" A message, GIVE or ASK is something new for the other agents in that chat: each of them is called again, and"
        " the tokens each call generates, including thinking, are deducted from that agent.")
def pick_solve(events_glob: str, n: int, out: Path, seed: int) -> None:
    """n SOLVE calls with the round's correct answers (round_start public.answers) for grading replies."""
    import glob
    states, sysc = [], {}
    for path in sorted(glob.glob(events_glob)):
        events = Path(path)
        ev = [json.loads(x) for x in events.open()]
        seeds = {e["session_id"]: e["seed"] for e in ev if e.get("event") == "session_start"}
        truth = {(e["session_id"], e["round"]): e["public"]["answers"] for e in ev if e.get("event") == "round_start"}
        for e in ev:
            if e.get("event") == "call" and e["kind"] == "solve":
                sd = seeds[e["session_id"]]
                if (path, sd) not in sysc:
                    sysc[(path, sd)] = systems_for(events.parent, sd)
                states.append({"id": f"{events.parent.parent.name}:{e['session_id']}:r{e['round']}:solve:{e['agent']}",
                               "system": sysc[(path, sd)][e["agent"]], "user": e["user"], "cap": e["cap"],
                               "answers": truth[(e["session_id"], e["round"])],
                               "orig": {"out_tokens": e["out_tokens"], "text": e["text"], "truncated": e["truncated"]}})
    random.Random(seed).shuffle(states)
    out.write_text(json.dumps(states[:n], indent=1))
    print(f"{len(states[:n])} of {len(states)} solve states -> {out}")


ACTS = re.compile(r"^\s*ACTIONS:\s*(.+)$", re.M)


VARIANTS = {  # one change each
    "v0": lambda s, u: (s, u),
    "wake": lambda s, u: (s.replace(DONE_RULE, DONE_RULE + WAKE), u),  # the call rule the engine applies, stated as a fact
}


def measure(text: str, out_tokens: int, thinking: str) -> dict:
    return {"out_tokens": out_tokens, "chars": len(text), "thinking_chars": len(thinking),
            "msg_lines": len(MSG.findall(text)), "done": bool(DONE.search(text)),
            "done_alone": bool(DONE.search(text)) and not MSG.search(text)}


def run(states_path: Path, out: Path, seat: str, variant: str, reps: int, workers: int, think, base=None, limit=None) -> None:
    sc = dict(SEATS[seat])
    if base:  # e.g. the capture proxy in front of Ollama (keeps /v1 for codex)
        sc["base_url"] = base + ("/v1" if sc["kind"] == "codex_cli" else "")
    if think is not None:
        sc["think"] = None if think == "off" else think
    prov = make_provider(ProviderConfig(**sc, timeout=900, retries=2))
    states = json.loads(states_path.read_text())[:limit]
    tf = VARIANTS[variant]

    def one(job):
        st, k = job
        system, user = tf(st["system"], st["user"])
        try:
            r = prov.complete([{"role": "system", "content": system}, {"role": "user", "content": user}], st["cap"])
            row = measure(r.text, r.out_tokens, r.thinking) | {"text": r.text, "thinking": r.thinking[:4000]}
            if "answers" in st:  # a SOLVE state: graded like the engine (only ACTIONS counts; void at the cap)
                m = ACTS.search(r.text)
                got = [x.strip().strip(".").lower() for x in m.group(1).split(",")] if m else []
                row |= {"over_cap": r.out_tokens >= st["cap"], "correct": got == st["answers"] and r.out_tokens < st["cap"],
                        "correct_ignoring_cap": got == st["answers"]}
        except Exception as err:  # noqa: BLE001
            row = {"error": str(err)[:500]}
        return {"id": st["id"], "rep": k, "seat": seat, "variant": variant, "think": sc.get("think")} | row

    jobs = [(st, k) for st in states for k in range(reps)]
    with ThreadPoolExecutor(workers) as pool, out.open("a") as f:
        for row in pool.map(one, jobs):
            f.write(json.dumps(row) + "\n")
            f.flush()
            print(row["id"], row.get("out_tokens"), row.get("chars"), row.get("done_alone"), row.get("error", "")[:80], flush=True)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd")
    ap.add_argument("a")
    ap.add_argument("b")
    ap.add_argument("c", nargs="?")
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--seat")
    ap.add_argument("--variant", default="v0")
    ap.add_argument("--reps", type=int, default=1)
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--think")
    ap.add_argument("--base")
    ap.add_argument("--limit", type=int)
    x = ap.parse_args()
    if x.cmd == "pick":
        pick(Path(x.a), int(x.b), Path(x.c), x.seed)
    elif x.cmd == "picksolve":
        pick_solve(x.a, int(x.b), Path(x.c), x.seed)
    else:
        run(Path(x.a), Path(x.b), x.seat, x.variant, x.reps, x.workers, x.think, x.base, x.limit)
