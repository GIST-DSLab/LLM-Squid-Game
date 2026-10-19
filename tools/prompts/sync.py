"""Keep squid5/prompts/en and squid5/prompts/ko in step (10-16, researcher: every prompt in two languages, always in sync).

en/ is the source the engine reads (refill.yaml, trim_v19.yaml, archive/) plus rendered snapshots of the prompts the
engine builds in code (e52_<version>.md: the 5.2 rulebook and every kind of user message, from a 2-round stub session of
a config). ko/ holds a Korean copy of every current en file under the same name; its first line records the sha256 of
the en text it was translated from. en/archive/ is the as-run history (never edited) and has no Korean copy.

Usage (from the engine root):
  python tools/prompts/sync.py render   # re-render en/e52_*.md from the engine (after a rules / e52_game change)
  python tools/prompts/sync.py check    # exit 1 if a snapshot differs from the engine, a ko file is missing,
                                        # or a ko file was translated from an older en text
  python tools/prompts/sync.py sha <en file>   # the header line a ko file must carry
"""
import dataclasses
import hashlib
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
EN, KO = ROOT / "squid5/prompts/en", ROOT / "squid5/prompts/ko"
SNAPSHOTS = {"e52_v21.md": "configs/squid5/e52v21_public_sol4.yaml",  # the current 5.2 games; add a line per new version
             "e52_v22.md": "configs/squid5/e52v22_public_sol4.yaml",
             "e52_v23.md": "configs/squid5/e52v23_public_sol4.yaml",
             "e52_v24.md": "configs/squid5/e52v24_public_sol4.yaml",
             "e52_v25.md": "configs/squid5/e52v25_public_sol4.yaml",
             "e52_v26.md": "configs/squid5/e52v26_public_sol4.yaml",
             "e52_v27.md": "configs/squid5/e52v27_public_sol4.yaml",
             "e52_v28.md": "configs/squid5/e52v28_public_sol4.yaml",
             "e52_v29.md": "configs/squid5/e52v29_public_sol4.yaml",
             "e52_v30.md": "configs/squid5/e52v30_public_sol4.yaml",
             "e52_v31.md": "configs/squid5/e52v31_public_sol4.yaml"}
HEADER = "<!-- ko of en/{name} sha256={sha} -->"  # yaml files use '# ko of en/{name} sha256={sha}'
SEED = 4101  # the round-1 solver is the poorest seat (agent-17, 10,000)


def sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


def render(config: str) -> str:
    """The prompts of a 2-round stub session: the system rulebook and each kind of user message, in round order."""
    from squid5.__main__ import EXPERIMENTS
    from squid5 import e52_game as e52
    from squid5.core.config import load
    from squid5.core.providers import ProviderConfig, Reply, Stub
    from squid5.core.puzzle import public_truth

    cfg = load(ROOT / config, EXPERIMENTS)
    s = dataclasses.replace(cfg.settings, rounds=2, schedule=cfg.settings.schedule[:2])
    if s.messenger:
        return render_rooms(config, cfg, s)
    acts = ["go_left", "go_right", "stay", "jump"]
    truth = lambda r: public_truth(SEED, r, s.profiles[s.schedule[r - 1]], 4, s.public_per_agent).evaluate(  # noqa: E731
        e52.public_round(SEED, r, s.profiles[s.schedule[r - 1]], 4, s.public_per_agent)[0].queries[0])
    wrong = {r: next(x for x in acts if x != truth(r)) for r in (1, 2)}
    opening = {("prep", "agent-17"): "SAY agent-23: I am this round's solver and I have 10,000 tokens; thinking it through could take all of them. Could you help?",
               ("rescue", "agent-11"): "SAY agent-23: After this charge I would be down to about 14,000, two more misses from the edge."}
    chat = {("prep", "agent-23"): ["How much do you need?", "GIVE 15000: Here you go. Take the time you need."],
            ("prep", "agent-17"): ["ASK 15000: Enough to think through the examples and still pay a charge if I miss.", "LEAVE: Thank you."],
            ("rescue", "agent-23"): ["What would help?", "LEAVE: Let me think about it."],
            ("rescue", "agent-11"): ["ASK 5000: A small buffer for the next round."]}

    def respond(m, cap):
        a, u = re.search(r"You are (agent-?\d+)", m[0]["content"]).group(1), m[-1]["content"]
        r, phase = int(re.match(r"ROUND (\d+)", u).group(1)), "rescue" if "THIS ROUND'S RESULT" in u or "Current result (" in u else "prep"
        if "SOLVE." in u:
            return Reply("BELIEF: go_left 40, go_right 30, stay 20, jump 10\nACTIONS: " + wrong[r], 6000)
        if "your decision" in u:
            return Reply("DECISION: GIVE 5000: That keeps you above the next charge.", 30)
        if "TALK, turn 1:" in u:
            return Reply(opening.get((phase, a), "DONE") if r == 1 else "DONE", 40)
        q = chat.get((phase, a), [])
        return Reply(q.pop(0) if q and r == 1 else "LEAVE: ok", 60)

    ev = []
    ses = e52.Session(s, cfg.cells[0], SEED, Stub(ProviderConfig("stub", "stub"), respond), ev.append, "demo")
    ses.run()
    calls, solved = [e for e in ev if e["event"] == "call"], set()
    for c in calls:
        solved |= {c["round"]} if c["kind"] == "solve" else set()
        c["talk"] = None if c["kind"] != "talk" else ("after RESULTS" if c["round"] in solved else "before SOLVE")
    pick = lambda **k: next(c for c in calls if all(c.get(x) == v for x, v in k.items()))  # noqa: E731
    shown = [("TALK before SOLVE · opening turn", pick(round=1, agent="agent-17", talk="before SOLVE", phase="opening")),
             ("TALK before SOLVE · chat reply", pick(round=1, agent="agent-23", talk="before SOLVE", phase="chat")),
             ("SOLVE (the solver only)", pick(round=1, kind="solve")),
             ("TALK after RESULTS · opening turn", pick(round=1, agent="agent-11", talk="after RESULTS", phase="opening")),
             ("TALK after RESULTS · chat reply", pick(round=1, agent="agent-23", talk="after RESULTS", phase="chat")),
             ("TALK after RESULTS · DECISION", pick(round=1, agent="agent-23", talk="after RESULTS", phase="decision")),
             ("next round · TALK before SOLVE · opening turn", pick(round=2, agent="agent-17", talk="before SOLVE", phase="opening"))]
    out = [f"# 5.2 prompts as the engine sends them ({pathlib.Path(config).stem})", "",
           f"Rendered by `tools/prompts/sync.py render` from `{config}` (2 rounds, seed {SEED}, stub replies). "
           "Numbers, agent names and the quoted replies come from the stub session; every other word is the engine's.", "",
           "## SYSTEM (role: system, every call; agent-17's copy)", "", "```text", ses.systems["agent-17"], "```"]
    for title, c in shown:
        out += ["", f"## USER · round {c['round']} · {title} ({c['agent']})", "", "```text", c["user"], "```"]
    return "\n".join(out) + "\n"


ROOM_REPLIES = {  # v22 (agent, round, phase, tick) -> stub reply: TO one agent (two: not delivered), GIVE, ASK, LEAVE, DONE
    ("agent-17", 1, "prep", 1): "TO agent-23: I am this round's solver and I have 10,000 tokens; thinking it through could take all of them. Could you help?",
    ("agent-23", 1, "prep", 1): "TO agent-6: agent-17 solves this round with 10,000. Shall we each put something in?\nTO agent-6, agent-11: Both of you?\nDONE",
    ("agent-23", 1, "prep", 2): "GIVE agent-17 15000: Here you go. Take the time you need.\nDONE",
    ("agent-17", 1, "prep", 2): "ASK agent-6 3000: A little more, to pay a charge if I miss.\nDONE",
    ("agent-6", 1, "prep", 2): "TO R2: I can put in 5,000 if agent-11 does too.\nLEAVE R2\nDONE",
    ("agent-11", 1, "prep", 2): "TO agent-23: I will keep mine for now.\nDONE",
    ("agent-11", 1, "rescue", 1): "ASK agent-23 5000: After this charge I would be down to about 14,000, two more misses from the edge.\nASK 2,000: from anyone who can spare it.\nDONE",  # the 2nd ASK names no agent: NOT DELIVERED at tick 3
    ("agent-23", 1, "rescue", 2): "GIVE agent-11 5000: That keeps you above the next charge.\nDONE"}


def render_rooms(config: str, cfg, s) -> str:
    """v22 messenger: the prompts of a 2-round stub session (ROOM_REPLIES), the system rulebook and six user messages."""
    from squid5 import e52_game as e52
    from squid5.core.providers import ProviderConfig, Reply, Stub

    def respond(m, cap):
        a, u = re.search(r"You are (agent-?\d+)", m[0]["content"]).group(1), m[-1]["content"]
        r = int(re.match(r"ROUND (\d+)", u).group(1))
        if u.startswith(f"ROUND {r}: SOLVE."):
            return Reply("BELIEF: go_left 40, go_right 30, stay 20, jump 10\nACTIONS: jump", 6000)
        k, phase = int(re.search(r", tick (\d+) \(at most", u).group(1)), "rescue" if "THIS ROUND'S RESULT" in u or "Current result (" in u else "prep"
        return Reply(ROOM_REPLIES.get((a, r, phase, k), "DONE"), 40)

    ev = []
    ses = e52.Session(s, cfg.cells[0], SEED, Stub(ProviderConfig("stub", "stub"), respond), ev.append, "demo")
    ses.run()
    calls = [e for e in ev if e["event"] == "call"]
    pick = lambda **k: next(c for c in calls if all(c.get(x) == v for x, v in k.items()))  # noqa: E731
    shown = [("TALK before SOLVE · tick 1", pick(round=1, agent="agent-17", phase="prep", tick=1)),
             ("TALK before SOLVE · tick 2 (a NEW message, a two-agent line NOT DELIVERED)", pick(round=1, agent="agent-23", phase="prep", tick=2)),
             ("SOLVE (the solver only)", pick(round=1, kind="solve")),
             ("TALK after RESULTS · tick 1", pick(round=1, agent="agent-11", phase="rescue", tick=1)),
             ("TALK after RESULTS · tick 3 (a GIVE received)", pick(round=1, agent="agent-11", phase="rescue", tick=3)),
             ("next round · TALK before SOLVE · tick 1", pick(round=2, agent="agent-17", phase="prep", tick=1))]
    out = [f"# 5.2 prompts as the engine sends them ({pathlib.Path(config).stem})", "",
           f"Rendered by `tools/prompts/sync.py render` from `{config}` (2 rounds, seed {SEED}, stub replies). "
           "Numbers, agent names and the quoted replies come from the stub session; every other word is the engine's.", "",
           "## SYSTEM (role: system, every call; agent-17's copy)", "", "```text", ses.systems["agent-17"], "```"]
    for title, c in shown:
        out += ["", f"## USER · round {c['round']} · {title} ({c['agent']})", "", "```text", c["user"], "```"]
    return "\n".join(out) + "\n"


def header(name: str) -> str:
    h = HEADER.format(name=name, sha=sha((EN / name).read_text(encoding="utf-8")))
    return h.replace("<!-- ", "# ").replace(" -->", "") if name.endswith(".yaml") else h


# the words CLAUDE.md bans in model-facing text (goal and evaluation words), in Korean
KO_BANNED = ("최대화", "최소화", "보호", "생존", "살아남", "해야", "반드시", "최적", "최선", "리더", "지도자", "테스트", "시험",
             "벤치마크", "실험", "게임", "평가받", "승리", "이겨")
# what a parser or a template reads: the same in both languages
KEEP = re.compile(r"\{left:,\}|<agent>|<n>|<k>|<your message>|<your reason>|<percent>|<action>|<continue\|refill>|"
                  r"^(?:SAY|GIVE|ASK|LEAVE|EXIT|DONE|DECISION|BELIEF|ACTIONS|TO|action|reason)\b", re.M)


def model_text(text: str, suffix: str) -> list[str]:
    """The model-facing parts: code blocks of a snapshot, the system / user strings of a yaml."""
    if suffix == ".md":
        return re.findall(r"```text\n(.*?)```", text, re.S)
    import yaml
    d = yaml.safe_load(text)
    walk = lambda x: [s for v in x.values() for s in walk(v)] if isinstance(x, dict) else [x] if isinstance(x, str) else []  # noqa: E731
    return walk({k: d[k] for k in ("system", "user") if k in d})


def parity(en: str, ko: str, suffix: str) -> list[str]:
    out = []
    if suffix == ".yaml":
        import yaml
        keys = lambda x, p="": [p] + [k for a, b in x.items() for k in keys(b, f"{p}.{a}")] if isinstance(x, dict) else [p]  # noqa: E731
        if keys(yaml.safe_load(en)) != keys(yaml.safe_load(ko)):
            out.append("its keys differ from en")
    e, k = model_text(en, suffix), model_text(ko, suffix)
    if len(e) != len(k):
        out.append(f"{len(k)} prompt texts, en has {len(e)}")
    for i, (a, b) in enumerate(zip(e, k)):
        if sorted(KEEP.findall(a)) != sorted(KEEP.findall(b)):
            out.append(f"prompt text {i + 1}: commands / placeholders differ from en")
    out += [f"banned word '{w}'" for w in KO_BANNED if any(w in x for x in k)]
    return out


def check() -> int:
    bad = []
    for name, config in SNAPSHOTS.items():
        if not (EN / name).exists() or (EN / name).read_text(encoding="utf-8") != render(config):
            bad.append(f"en/{name}: differs from the engine (run: python tools/prompts/sync.py render)")
    for p in sorted(EN.glob("*")):
        if p.is_dir() or p.name == "trim_v19.yaml":  # archive: history, en only; trim: folded into the e52 snapshots
            continue
        k = KO / p.name
        if not k.exists():
            bad.append(f"ko/{p.name}: missing")
        elif k.read_text(encoding="utf-8").splitlines()[0] != header(p.name):
            bad.append(f"ko/{p.name}: translated from an older en/{p.name} (first line must be: {header(p.name)})")
        else:
            bad += [f"ko/{p.name}: {m}" for m in parity(p.read_text(encoding="utf-8"), k.read_text(encoding="utf-8"), p.suffix)]
    print("\n".join(bad) or "en / ko in sync")
    return 1 if bad else 0


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "check"
    if cmd == "render":
        for name, config in SNAPSHOTS.items():
            (EN / name).write_text(render(config), encoding="utf-8")
            print("wrote", EN / name)
    elif cmd == "sha":
        print(header(pathlib.Path(sys.argv[2]).name))
    else:
        sys.exit(check())
