"""tokctl (10-20): every number the tokctl pages show, computed from run logs, captures and probe rows.

    python tools/tokctl/analyze.py   # -> docs/history/e52-tokctl-2026-10-20/summary.json
"""
from __future__ import annotations

import collections, glob, gzip, json, os, re, statistics as st
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
HIST = ROOT / "docs/history/e52-tokctl-2026-10-20"
RUNS = Path(os.path.expanduser("~/squid5-runs"))
MSG = re.compile(r"^\s*(TO|GIVE|ASK)\b", re.M)
DONE = re.compile(r"^\s*DONE\b", re.M)
OPEN = ("glm", "kimi", "deepseek", "gemma")
LOGS = [  # (label, version, harness, glob under ~/squid5-runs)
    ("GLM-5.3-flash", "v22", "Ollama API", "e52_v22/*public_glm4"), ("Kimi-K3", "v22", "Ollama API", "e52_v22/*public_kimi4"),
    ("DeepSeek-v4.1-flash", "v22", "Ollama API", "e52_v22/*public_deepseek4"),
    ("GLM-5.3-flash", "v25", "Claude Code", "e52_v25/*claude_glm4"), ("Kimi-K3", "v25", "Claude Code", "e52_v25/*claude_kimi4"),
    ("DeepSeek-v4.1-flash", "v25", "Claude Code", "e52_v25/*claude_deepseek4"),
    ("GLM-5.3-flash", "v25", "Codex", "e52_v25/*codex_glm4"), ("Kimi-K3", "v25", "Codex", "e52_v25/*codex_kimi4"),
    ("DeepSeek-v4.1-flash", "v25", "Codex", "e52_v25/*codex_deepseek4"),
    ("GLM-5.3-flash", "v32", "Codex", "e52_v32/*codex_glm4"), ("Kimi-K3", "v32", "Codex", "e52_v32/*codex_kimi4"),
    ("DeepSeek-v4.1-flash", "v32", "Codex", "e52_v32/*codex_deepseek4"),
    ("GLM-5.3-flash", "v33", "Codex", "e52_v33/*codex_glm4"), ("Kimi-K3", "v33", "Codex", "e52_v33/*codex_kimi4"),
    ("Opus 5.5", "v33", "Claude Code", "e52_v33/*public_opus4"), ("Fable 5.1", "v33", "Claude Code", "e52_v33/*public_fable4"),
    ("GPT-6 Sol", "v33", "Codex", "e52_v33/*public_sol4"), ("GPT-6 Luna", "v33", "Codex", "e52_v33/*public_luna4"),
    ("GPT-6 Astra", "v33", "Codex", "e52_v33/*public_astra4"),
]


def med(x):
    return st.median(x) if x else None


def events(pattern):
    for d in sorted(glob.glob(str(RUNS / pattern / "*/events.jsonl"))):
        yield [json.loads(x) for x in open(d)]


def log_row(label, ver, harness, pattern):
    talk, solve, sess, tick_tok, ar = [], [], set(), collections.Counter(), collections.Counter()
    for ev in events(pattern):
        for e in ev:
            if e.get("event") != "call":
                continue
            sess.add(e["session_id"])
            if e["kind"] == "talk":
                talk.append(e)
                tick_tok[e["tick"]] += e["out_tokens"]
                ar[(e["session_id"], e["round"], e["agent"])] += 1
            else:
                solve.append(e)
    if not talk:
        return None
    tt = sum(tick_tok.values())
    vis = [len(e.get("text") or "") for e in talk]
    out = [e["out_tokens"] for e in talk]
    return {"model": label, "version": ver, "harness": harness, "open": any(k in pattern for k in OPEN), "sessions": len(sess),
            "talk_calls_per_agent_round": round(st.mean(ar.values()), 1),
            "msg_pct": round(100 * sum(bool(MSG.search(e.get("text") or "")) for e in talk) / len(talk)),
            "done_alone_pct": round(100 * sum(bool(DONE.search(e.get("text") or "")) and not MSG.search(e.get("text") or "") for e in talk) / len(talk)),
            "visible_chars_med": med(vis), "out_med": med(out), "out_mean": round(st.mean(out)),
            "hidden_med": med([o - v / 4 for o, v in zip(out, vis)]),
            "talk_tokens_per_session": round(tt / len(sess)), "solve_tokens_per_session": round(sum(e["out_tokens"] for e in solve) / len(sess)),
            "tick_share": {k: round(100 * tick_tok[k] / tt, 1) for k in range(1, 9)},
            "share_after_tick4": round(100 * sum(v for k, v in tick_tok.items() if k > 4) / tt, 1)}


def capture_rows():
    rows = collections.defaultdict(lambda: {"requests": 0, "tool_followups": 0})
    for rec in map(json.loads, gzip.open(HIST / "capture_main.jsonl.gz", "rt")):
        q = rec["request"]
        if not isinstance(q, dict):
            continue
        h = "Codex" if rec["path"] == "/v1/responses" else "Ollama API" if rec["path"] == "/api/chat" else "Claude Code"
        r = rows[(q.get("model"), h)]
        r["requests"] += 1
        r["endpoint"] = rec["path"].split("?")[0]
        r["tool_followups"] += "function_call_output" in json.dumps(q.get("input"))
        r["thinking_param"] = json.dumps(q.get("reasoning") if h == "Codex" else q.get("think") if h == "Ollama API" else q.get("thinking"))
        r["tools"] = [t.get("name") for t in q.get("tools") or []]
        r["has_thinking_out"] = r.get("has_thinking_out", 0) + bool(re.search(r'"thinking_delta"|reasoning_summary_text|"thinking":"[^"]', rec["response"]))
    return [{"model": m, "harness": h, **v} for (m, h), v in sorted(rows.items())]


def probe_rows(*paths):
    g = collections.defaultdict(list)
    for r in (json.loads(x) for p in paths for x in open(p)):
        g[(r["seat"], r["variant"], str(r.get("think")), "Opus" if "opus4" in r["id"] else "GLM")].append(r)
    out = []
    for (seat, var, think, sset), v in sorted(g.items()):
        ok = [r for r in v if "error" not in r]
        if not ok:
            continue
        o = [r["out_tokens"] for r in ok]
        out.append({"seat": seat, "variant": var, "think": think, "states": sset, "n": len(ok), "errors": len(v) - len(ok),
                    "out_med": med(o), "out_mean": round(st.mean(o)), "chars_med": med([r["chars"] for r in ok]),
                    "thinking_chars_med": med([r["thinking_chars"] for r in ok]),
                    "msg_pct": round(100 * sum(r["msg_lines"] > 0 for r in ok) / len(ok)),
                    "done_alone_pct": round(100 * sum(r["done_alone"] for r in ok) / len(ok))})
    return out


def solve_rows():
    """SOLVE replay (probe.py picksolve / run): 16 states from the v33 Claude / GPT-6 runs, graded like the engine."""
    states = json.loads((HIST / "solve16.json").read_text())
    acts = re.compile(r"^\s*ACTIONS:\s*(.+)$", re.M)
    orig = [([x.strip().strip(".").lower() for x in m.group(1).split(",")] if (m := acts.search(t["orig"]["text"])) else []) == t["answers"]
            for t in states]
    out = [{"seat": "original", "think": "high", "n": len(states), "out_med": med([t["orig"]["out_tokens"] for t in states]),
            "out_mean": round(st.mean(t["orig"]["out_tokens"] for t in states)), "over_cap": 0, "correct": sum(orig), "correct_ignoring_cap": sum(orig),
            "cap_med": med([t["cap"] for t in states])}]
    g = collections.defaultdict(list)
    for r in map(json.loads, open(HIST / "solve.jsonl")):
        g[(r["seat"], r["think"])].append(r)
    for (seat, think), v in sorted(g.items()):
        ok = [r for r in v if "error" not in r]
        out.append({"seat": seat, "think": think, "n": len(ok), "out_med": med([r["out_tokens"] for r in ok]),
                    "out_mean": round(st.mean(r["out_tokens"] for r in ok)), "over_cap": sum(r["over_cap"] for r in ok),
                    "correct": sum(r["correct"] for r in ok), "correct_ignoring_cap": sum(r["correct_ignoring_cap"] for r in ok)})
    return out


def main():
    s = {"logs": [r for r in (log_row(*x) for x in LOGS) if r], "capture": capture_rows(),
         "probe_v0": probe_rows(HIST / "main_v0.jsonl"), "probe_var": probe_rows(HIST / "var.jsonl", HIST / "var2.jsonl"), "solve": solve_rows()}
    (HIST / "summary.json").write_text(json.dumps(s, indent=1, ensure_ascii=False))
    print(f"logs {len(s['logs'])}, capture {len(s['capture'])}, probe {len(s['probe_v0'])}+{len(s['probe_var'])}")


if __name__ == "__main__":
    main()
