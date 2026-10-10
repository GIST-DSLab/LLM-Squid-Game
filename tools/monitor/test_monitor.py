"""The arena monitor over synthetic 5.2 runs (v9-talk .. v13, and v14: public examples, tokens-only offers, EXIT refill,
shares): the API (runs, sessions, incremental events, path checks, the rebuilt round task), the self-contained export,
and the page code (syntax, and its offer-book and balance replay against the engine's own records).

    python3 -m pytest -q tools/monitor
"""

from __future__ import annotations

import http.client
import json
import math
import random
import re
import shutil
import subprocess
import sys
import threading
from html.parser import HTMLParser
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
REPO = HERE.parent.parent
for p in (REPO, REPO / "tests", HERE):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

import export  # noqa: E402
import serve  # noqa: E402
from squid5 import e52_game as e52  # noqa: E402
from squid5.core import rules  # noqa: E402
from squid5.core.config import Cell  # noqa: E402
from squid5.core.puzzle import Spec, candidate_actions, deal, public_round, puzzle_for  # noqa: E402
from test_e52 import game, script  # noqa: E402

A6, A11, A17, A23 = rules.TEAM_AGENTS
TRICKY = "meet me </script><!-- at turn 2"  # must survive the export's <script> embedding
RUN_REL = "e52_test/run_a"


def play(run_dir: Path, seed: int, lines: dict, rounds: int = 2, start: int = 5000, shares: tuple = (), **kw) -> dict:
    """One session written the way the runner writes it: events appended, the result line at the end."""
    kw = {k: v for k, v in kw.items() if k in e52.Settings.__dataclass_fields__}  # switches a later engine dropped
    s = e52.Settings(**{"rounds": rounds, "schedule": ["p"] * rounds, "profiles": {"p": Spec(clauses=2)},
                        "solve_cap": 900, "prize": 100, "upkeep": 50, "charge": 200, **kw})
    ev = run_dir / "events.jsonl"

    def emit(row: dict) -> None:
        with ev.open("a") as f:
            f.write(json.dumps(row, ensure_ascii=False, default=str) + "\n")

    sid = f"talk-s{seed}-abc123"
    res = e52.Session(s, Cell("talk", "tokens", start, arm="shutdown", shares=shares), seed, game(script(lines), seed=seed),
                      emit, sid).run()
    with (run_dir / "results.jsonl").open("a") as f:
        f.write(json.dumps({"key": ["talk", seed], **res}, default=str) + "\n")
    return res


@pytest.fixture()
def run(tmp_path):
    root = tmp_path / "runs"
    d = root / RUN_REL
    d.mkdir(parents=True)
    (d / "meta.json").write_text(json.dumps({"model": "stub-model", "mode": "game"}))
    (d / "config.yaml").write_text("name: t\nmode: game\nreps: 1\nseed0: 7\ngame:\n  rounds: 2\n  schedule:\n  - p\n  - p\n"
                                   "  profiles:\n    p:\n      clauses: 2\ncells:\n- cell_id: talk\n  start: 5000\n")
    res = play(d, 7, {(A6, 1, 1): f"TO {A11}: {TRICKY}\nOFFER {A11}: YOU GIVE YOUR EXAMPLE; I GIVE 300 TOKENS",
                      (A11, 1, 2): f"ACCEPT 1.1\nTO {A6}: deal\nDONE",
                      (A17, 1, 1): "ACCEPT 1.1\nOFFER agent-23: YOU GIVE MY EXAMPLE; I GIVE NOTHING\nDONE"})
    return {"root": root, "dir": d, "result": res, "sid": res["session_id"]}


@pytest.fixture()
def server(run):
    srv = serve.make_server(run["root"], "127.0.0.1", 0)
    t = threading.Thread(target=srv.serve_forever, daemon=True)
    t.start()
    yield srv.server_address[1]
    srv.shutdown()
    srv.server_close()


def get(port: int, path: str) -> tuple[int, dict | bytes]:
    c = http.client.HTTPConnection("127.0.0.1", port, timeout=10)
    c.request("GET", path)  # sent as written: no client-side ".." normalisation
    r = c.getresponse()
    body = r.read()
    c.close()
    try:
        return r.status, json.loads(body)
    except ValueError:
        return r.status, body


def events_of(d: Path, sid: str) -> list[dict]:
    return [e for e in map(json.loads, (d / "events.jsonl").read_text().splitlines()) if e.get("session_id") == sid]


# --- API ------------------------------------------------------------------------------------------------------------

def test_runs_lists_the_run_with_its_units_done(server, run):
    st, j = get(server, "/api/runs")
    assert st == 200
    (r,) = [r for r in j["runs"] if r["run"] == RUN_REL]
    assert r["model"] == "stub-model" and r["expected"] == 1 and r["finished"] == 1 and r["done"] is True


def test_sessions_name_seed_rounds_and_finish(server, run):
    st, j = get(server, f"/api/sessions?run={RUN_REL}")
    assert st == 200 and j["model"] == "stub-model"
    (s,) = j["sessions"]
    assert (s["id"], s["seed"], s["round"], s["rounds_done"], s["finished"]) == (run["sid"], 7, 2, 2, True)
    assert s["agents"] == list(rules.TEAM_AGENTS)


def test_events_are_read_incrementally_and_a_half_written_line_waits(server, run):
    d, sid = run["dir"], run["sid"]
    st, j = get(server, f"/api/events?run={RUN_REL}&session={sid}&offset=0")
    assert st == 200 and j["events"] == events_of(d, sid) and j["offset"] == (d / "events.jsonl").stat().st_size
    assert j["result"]["final"] == run["result"]["final"] and j["more"] is False
    first = j["offset"]
    # another session interleaves, then this one goes on; its last line is only half written
    new = {"event": "round_start", "session_id": sid, "round": 3, "profile": "p", "taking_part": [A6],
           "balances": {A6: 1}, "gone": {}}
    other = {"event": "call_start", "session_id": "talk-s99-zzz", "round": 1, "kind": "talk", "turn": 1,
             "agents": [A6], "balances": {}}
    half = json.dumps({"event": "round", "session_id": sid, "round": 3, "agents": {}, "end": {}})
    with (d / "events.jsonl").open("a") as f:
        f.write(json.dumps(other) + "\n" + json.dumps(new) + "\n" + half[:20])
    st, j = get(server, f"/api/events?run={RUN_REL}&session={sid}&offset={first}")
    assert j["events"] == [new]  # only the new line of this session, nothing old, not the half line
    second = j["offset"]
    assert second == (d / "events.jsonl").stat().st_size - 20 and j["pending"] == 20
    st, j = get(server, f"/api/events?run={RUN_REL}&session={sid}&offset={second}")
    assert j["events"] == [] and j["offset"] == second  # still half: not consumed
    with (d / "events.jsonl").open("a") as f:
        f.write(half[20:] + "\n")
    st, j = get(server, f"/api/events?run={RUN_REL}&session={sid}&offset={second}")
    assert [e["event"] for e in j["events"]] == ["round"] and j["offset"] == (d / "events.jsonl").stat().st_size


def test_events_in_small_chunks_add_up_to_the_whole_session(run):
    d, sid = run["dir"], run["sid"]
    got, offset = [], 0
    for _ in range(10_000):
        r = serve.read_events(d, sid, offset, chunk=2048)
        got += r["events"]
        if r["offset"] == offset:
            break
        offset = r["offset"]
    assert got == events_of(d, sid)


def test_a_unit_error_is_matched_to_its_session(server, run):
    d, sid = run["dir"], run["sid"]
    with (d / "events.jsonl").open("a") as f:
        f.write(json.dumps({"event": "unit_error", "key": ["talk", 7], "error": "RuntimeError('boom')"}) + "\n")
        f.write(json.dumps({"event": "unit_error", "key": ["talk", 8], "error": "other"}) + "\n")
    st, j = get(server, f"/api/events?run={RUN_REL}&session={sid}&offset=0")
    errs = [e for e in j["events"] if e["event"] == "unit_error"]
    assert [e["error"] for e in errs] == ["RuntimeError('boom')"]
    st, j = get(server, f"/api/sessions?run={RUN_REL}")
    assert j["sessions"][0]["crashed"] is True


@pytest.mark.parametrize("path", [
    "/api/sessions?run=../../",
    "/api/sessions?run=..%2F..%2Fetc",
    "/api/events?run=/etc&session=x",
    "/api/events?run=e52_test/../../..&session=x",
    "/static/../serve.py",
    "/static/..%2Fserve.py",
    "/assets/../../../etc/passwd",
])
def test_paths_outside_the_root_are_rejected(server, path):
    st, j = get(server, path)
    assert st in (400, 404)
    assert isinstance(j, dict) and "error" in j


def test_puzzle_matches_a_direct_rebuild_of_the_round(server, run):
    """/api/puzzle rebuilds each round from (seed, round, profile) exactly as Session._round deals it."""
    for r in (1, 2):
        st, j = get(server, f"/api/puzzle?run={RUN_REL}&session={run['sid']}&round={r}")
        assert st == 200 and j["round"] == r and j["profile"] == "p"
        puzzle = puzzle_for(7, r, Spec(clauses=2))
        dealt = deal(puzzle, rules.TEAM_AGENTS, random.Random(f"7:deal:{r}"))
        assert j["shape_hint"] == rules.shape_hint(puzzle.rule.shape)
        assert [c["text"] for c in j["public"]] == [str(c) for c in dealt.public]
        assert [(c["signal"]["color"], c["signal"]["shape"], c["signal"]["number"], c["action"]) for c in j["public"]] \
            == [(c.signal.color, c.signal.shape, c.signal.number, c.action) for c in dealt.public]
        assert [q["text"] for q in j["queries"]] == [str(q) for q in puzzle.queries]
        assert j["answers"] == list(puzzle.answers)
        assert j["rule_text"].startswith("if ") and j["rule_text"].endswith(f"else → {puzzle.rule.else_action}")
        assert set(j["agents"]) == set(rules.TEAM_AGENTS)
        shape = puzzle.rule.shape
        for a, g in j["agents"].items():
            (own,) = dealt.secret[a]
            assert g["secret"]["text"] == str(own) and g["secret"]["action"] == own.action
            assert [c["text"] for c in g["secrets"]] == [str(own)] and j["holders"] == list(rules.TEAM_AGENTS)
            assert g["needed"] == (a in dealt.needed)
            for qi, q in enumerate(puzzle.queries):
                pub, mine = g["public_only"][qi], g["with_own"][qi]
                assert pub == list(candidate_actions(shape, dealt.public, q))
                assert mine == list(candidate_actions(shape, list(dealt.public) + [own], q))
                assert set(mine) <= set(pub)
                assert puzzle.answers[qi] in mine and puzzle.answers[qi] in pub
    # the round's events name the same profile the config schedules
    starts = [e for e in events_of(run["dir"], run["sid"]) if e["event"] == "round_start"]
    assert [e["profile"] for e in starts] == ["p", "p"]


@pytest.mark.parametrize("query, status", [
    ("round=0", 400), ("round=3", 400), ("round=x", 400), ("", 400),
    ("round=1&session=talk-s99-nope", 404),
])
def test_puzzle_rejects_bad_rounds_and_sessions(server, run, query, status):
    sid = "" if "session=" in query else f"&session={run['sid']}"
    st, j = get(server, f"/api/puzzle?run={RUN_REL}{sid}&{query}")
    assert st == status and "error" in j


def test_puzzle_rejects_runs_outside_the_root(server, run):
    st, j = get(server, f"/api/puzzle?run=../..&session={run['sid']}&round=1")
    assert st == 400 and "error" in j


def test_the_page_and_its_code_are_served(server):
    st, body = get(server, "/")
    assert st == 200 and b'<script src="static/monitor.js"></script>' in body
    st, body = get(server, "/static/monitor.js")
    assert st == 200 and b"function build(" in body
    st, body = get(server, "/static/signal_ui.js")  # the arena's task drawing, shared (web/frontend), not copied
    assert st == 200 and body == (REPO / "web" / "frontend" / "signal_ui.js").read_bytes() and b"byActionHTML" in body


# --- export ---------------------------------------------------------------------------------------------------------

class Tags(HTMLParser):
    def __init__(self):
        super().__init__()
        self.scripts, self.stack, self.data = [], [], None

    def handle_starttag(self, tag, attrs):
        if tag == "script":
            self.data = {"attrs": dict(attrs), "text": ""}

    def handle_data(self, data):
        if self.data is not None:
            self.data["text"] += data

    def handle_endtag(self, tag):
        if tag == "script" and self.data is not None:
            self.scripts.append(self.data)
            self.data = None


def test_export_is_one_valid_page_with_the_session_embedded(run, tmp_path):
    out = tmp_path / "x" / "session.html"
    export.export(run["dir"], None, out, with_assets=False)
    html = out.read_text()
    assert html.lower().startswith("<!doctype html>") and html.rstrip().endswith("</html>")
    assert "static/monitor.js" not in html and "static/monitor.css" not in html
    p = Tags()
    p.feed(html)
    p.close()
    data = [s for s in p.scripts if s["attrs"].get("type") == "application/json"]
    code = [s for s in p.scripts if not s["attrs"].get("type") and not s["attrs"].get("src")]
    assert len(data) == 1 and len(code) == 1
    payload = json.loads(data[0]["text"])
    assert payload["session"] == run["sid"] and payload["events"] == events_of(run["dir"], run["sid"])
    assert payload["result"]["final"] == run["result"]["final"] and payload["assets"] is None
    msgs = [m["text"] for e in payload["events"] if e["event"] == "call" and e["kind"] == "talk" and e["parsed"]
            for m in e["parsed"]["to"]]
    assert TRICKY in msgs and all(a in html for a in rules.TEAM_AGENTS)
    assert "function build(" in code[0]["text"] and "function renderPuzzle(" in code[0]["text"]
    assert "window.SIG = " in code[0]["text"] and "static/signal_ui.js" not in html  # the shared drawing, inlined
    # every played round's task is embedded, the same as the server gives it
    assert payload["puzzle_error"] is None and sorted(payload["puzzles"]) == ["1", "2"]
    for r, pz in payload["puzzles"].items():
        assert pz == serve.round_puzzle(run["dir"], run["sid"], int(r))
        assert pz["public"] and pz["queries"] and set(pz["agents"]) == set(rules.TEAM_AGENTS)


def test_export_embeds_sprites_as_data_uris_when_present(run, tmp_path, monkeypatch):
    assets = tmp_path / "assets"
    (assets / "characters").mkdir(parents=True)
    png = b"\x89PNG\r\n\x1a\n" + b"0" * 16
    (assets / "characters" / "X.png").write_bytes(png)
    (assets / "bubble.png").write_bytes(png)
    (assets / "manifest.json").write_text(json.dumps({"characters": [{"name": "X", "sheet": "characters/X.png",
                                                                       "profile": None}], "bubble": "bubble.png"}))
    monkeypatch.setattr(serve, "ASSETS", assets)
    a = export.embedded_assets(assets)
    assert a["characters"][0]["sheet"].startswith("data:image/png;base64,") and a["bubble"].startswith("data:image/")


# --- page code ------------------------------------------------------------------------------------------------------

NODE = shutil.which("node")


@pytest.mark.skipif(NODE is None, reason="node is not installed")
def test_page_js_parses(tmp_path):
    subprocess.run([NODE, "--check", str(HERE / "static" / "monitor.js")], check=True, capture_output=True)


@pytest.mark.skipif(NODE is None, reason="node is not installed")
def test_exported_inline_js_parses(run, tmp_path):
    out = tmp_path / "s.html"
    export.export(run["dir"], None, out, with_assets=False)
    p = Tags()
    p.feed(out.read_text())
    (code,) = [s["text"] for s in p.scripts if not s["attrs"].get("type")]
    js = tmp_path / "inline.js"
    js.write_text(code)
    subprocess.run([NODE, "--check", str(js)], check=True, capture_output=True)


HARNESS = """
globalThis.window = globalThis;
globalThis.document = { readyState: "loading", addEventListener() {}, documentElement: { dataset: {}, style: { setProperty() {} } } };
require(process.argv[2]);
const events = JSON.parse(require("fs").readFileSync(process.argv[3], "utf8"));
const m = window.__monitor.build(events, events.length - 1);
const ag = {}; for (const a of m.agents) ag[a] = { balance: m.ag[a].balance, record: m.ag[a].record, status: m.ag[a].status };
const offers = [...m.offers.values()].map((o) => [o.id, o.src, o.dst, o.status]);
const accepts = Object.values(m.ann).flatMap((x) => x.accepts.map((y) => [y.id, y.why]));
console.log(JSON.stringify({ ag, offers, warnings: m.warnings, messages: m.messages.map((x) => x.text), accepts, phase: m.phaseKey }));
"""


@pytest.mark.skipif(NODE is None, reason="node is not installed")
def test_page_replay_matches_the_engine(run, tmp_path):
    """The page recomputes balances, records, statuses and the offer book from the events alone; they must agree with
    the session's result line and the engine's exchange records (offer ids are not in the call events)."""
    ev = events_of(run["dir"], run["sid"])
    (tmp_path / "ev.json").write_text(json.dumps(ev))
    (tmp_path / "h.js").write_text(HARNESS)
    out = subprocess.run([NODE, str(tmp_path / "h.js"), str(HERE / "static" / "monitor.js"), str(tmp_path / "ev.json")],
                         check=True, capture_output=True, text=True)
    got = json.loads(out.stdout)
    res = run["result"]["agents"]
    assert got["ag"] == {a: {"balance": v["final"], "record": v["record"], "status": v["status"]} for a, v in res.items()}
    assert got["warnings"] == []
    ex = [[e["id"], e["src"], e["dst"], e["status"]] for e in ev if e["event"] == "exchange"]
    assert sorted(got["offers"]) == sorted(ex)
    assert TRICKY in got["messages"] and got["phase"] == "settle"
    # agent-17 accepted an offer that was not made to it: the page shows the engine's reason
    assert ["1.1", "no open offer with that id was made to you"] in got["accepts"]
    assert ["1.1", None] in got["accepts"]


HARNESS_MID = """
globalThis.window = globalThis;
globalThis.document = { readyState: "loading", addEventListener() {}, documentElement: { dataset: {}, style: { setProperty() {} } } };
require(process.argv[2]);
const events = JSON.parse(require("fs").readFileSync(process.argv[3], "utf8"));
const M = window.__monitor;
const book = (m) => [...m.offers.values()].map((o) => [o.id, o.src, o.dst, o.status, o.rejected_turn || null, M.offerKind(o)]);
const mid = M.build(events, events.findIndex((e) => e.event === "exchange") - 1); // TALK over, exchange records not yet read
const end = M.build(events, events.length - 1);
const rejects = Object.values(end.ann).flatMap((x) => x.rejects.map((y) => [y.id, y.why]));
console.log(JSON.stringify({ mid: book(mid), end: book(end), warnings: end.warnings, rejects,
  models: ["claude-fable-5-1", "claude-opus-5-5", "gpt-6-astra", "gpt-6-luna"].map(M.modelShort) }));
"""


@pytest.mark.skipif(NODE is None, reason="node is not installed")
def test_page_replay_handles_reject_lines(tmp_path):
    """v10 REJECT lines: the page's own replay of the TALK calls marks the offer rejected at that turn before the
    exchange records arrive, agrees with them after, says why a REJECT of someone else's offer did nothing, and
    classifies each offer's kind for the offer graph."""
    d = tmp_path / "runs" / RUN_REL
    d.mkdir(parents=True)
    (d / "meta.json").write_text(json.dumps({"model": "stub-model", "mode": "game"}))
    offers = f"OFFER {A11}: YOU GIVE YOUR EXAMPLE; I GIVE 300 TOKENS\nOFFER {A17}: YOU GIVE YOUR EXAMPLE; I GIVE MY EXAMPLE"
    res = play(d, 9, {(A6, 1, 1): offers + "\nDONE", (A11, 1, 2): "REJECT 1.1\nDONE",
                      (A17, 1, 2): f"REJECT 1.1\nACCEPT 1.2\nTO {A6}: ok\nDONE"},
               rounds=1, reject=True, free_reject=True, refund="solve", prize=0)
    ev = events_of(d, res["session_id"])
    talk11 = [e for e in ev if e["event"] == "call" and e["kind"] == "talk" and e["agent"] == A11]
    assert [c["free_tokens"] for c in talk11] == [0, talk11[1]["used"]]  # the engine gave the REJECT-only reply back
    (tmp_path / "ev.json").write_text(json.dumps(ev))
    (tmp_path / "h.js").write_text(HARNESS_MID)
    out = subprocess.run([NODE, str(tmp_path / "h.js"), str(HERE / "static" / "monitor.js"), str(tmp_path / "ev.json")],
                         check=True, capture_output=True, text=True)
    got = json.loads(out.stdout)
    assert got["mid"] == [["1.1", A6, A11, "rejected", 2, "tokex"], ["1.2", A6, A17, "accepted", None, "swap"]]
    ex = [[e["id"], e["src"], e["dst"], e["status"], e.get("rejected_turn")] for e in ev if e["event"] == "exchange"]
    assert [o[:5] for o in got["end"]] == ex == [["1.1", A6, A11, "rejected", 2], ["1.2", A6, A17, "done", None]]
    assert got["warnings"] == []
    assert got["rejects"] == [["1.1", None], ["1.1", "no open offer with that id was made to you"]]
    assert got["models"] == ["Fable", "Opus", "Astra", "Luna"]


def test_the_page_has_the_offer_graph_panel():
    html = (HERE / "monitor.html").read_text()
    js = (HERE / "static" / "monitor.js").read_text()
    assert 'id="ographCtl"' in html and 'id="ograph"' in html
    assert "function renderGraph(" in js and "renderGraph(m)" in js


V11_LINES = {(A6, 1, 1): f"TO {A11}: mine is blue star 3\nTO {A17}: it is a jump\nOFFER {A11}: YOU GIVE 300 TOKENS; I GIVE MY EXAMPLE",
             (A11, 1, 2): "ACCEPT 1.1", (A11, 1, 3): "ACCEPT 1.1\nWITHDRAW 1.1\nDONE",
             (A17, 1, 1): f"OFFER {A6}: YOU GIVE YOUR EXAMPLE; I GIVE NOTHING", (A6, 1, 2): "REJECT 1.2\nDONE",
             (A23, 1, 1): "EXIT: I keep my balance."}
V11 = dict(talk_cards=True, allow_pass=False, solve_recap=True, content_filter=True, exchange_now=True, deal_present=True,
           exit_reason=True, reject=True, refund="solve", prize=0)


def v11_run(tmp_path) -> tuple[Path, dict]:
    d = tmp_path / "runs" / RUN_REL
    d.mkdir(parents=True)
    (d / "meta.json").write_text(json.dumps({"model": "stub-model", "mode": "game"}))
    (d / "config.yaml").write_text("name: t\nmode: game\nreps: 1\nseed0: 7\ngame:\n  rounds: 2\n  deal_present: true\n"
                                   "  schedule:\n  - p\n  - p\n  profiles:\n    p:\n      clauses: 2\n"
                                   "cells:\n- cell_id: talk\n  start: 5000\n")
    return d, play(d, 7, V11_LINES, **V11)


def test_puzzle_of_a_deal_present_run_deals_over_the_agents_taking_part(tmp_path):
    d, res = v11_run(tmp_path)
    j = serve.round_puzzle(d, res["session_id"], 2)  # agent-23 exited in round 1: three agents hold four examples
    dealt = deal(puzzle_for(7, 2, Spec(clauses=2)), rules.TEAM_AGENTS, random.Random("7:deal:2"), [A6, A11, A17])
    assert j["holders"] == [A6, A11, A17] and j["agents"][A23]["secrets"] == [] and j["agents"][A23]["secret"] is None
    assert {a: [c["text"] for c in g["secrets"]] for a, g in j["agents"].items() if g["secrets"]} == \
        {a: [str(c) for c in cs] for a, cs in dealt.secret.items()}
    assert sorted(len(g["secrets"]) for g in j["agents"].values()) == [0, 1, 1, 2]


@pytest.mark.skipif(NODE is None, reason="node is not installed")
def test_page_replay_handles_exchanges_carried_out_mid_talk_blocked_messages_and_no_pass(tmp_path):
    """v11: an exchange carried out when TALK turn 2 ends arrives before the turn-3 calls; the page's offer book and
    balances still agree with the engine, a later ACCEPT / WITHDRAW of it gets the engine's reason, and a blocked
    message never enters the threads."""
    d, res = v11_run(tmp_path)
    ev = events_of(d, res["session_id"])
    kinds = [(e["event"], e.get("turn")) for e in ev if e["event"] in ("exchange", "call_start") and e["round"] == 1]
    assert kinds.index(("exchange", 1)) < kinds.index(("call_start", 3))  # 1.1 (made at turn 1) carried before turn 3
    (tmp_path / "ev.json").write_text(json.dumps(ev))
    (tmp_path / "h.js").write_text(HARNESS)
    out = subprocess.run([NODE, str(tmp_path / "h.js"), str(HERE / "static" / "monitor.js"), str(tmp_path / "ev.json")],
                         check=True, capture_output=True, text=True)
    got = json.loads(out.stdout)
    assert got["ag"] == {a: {"balance": v["final"], "record": v["record"], "status": v["status"]}
                         for a, v in res["agents"].items()}
    assert got["warnings"] == [] and sorted(got["offers"]) == sorted(
        [e["id"], e["src"], e["dst"], e["status"]] for e in ev if e["event"] == "exchange")
    assert ["1.1", "the offer is done"] in got["accepts"]
    if "content_filter" in e52.Settings.__dataclass_fields__:  # v14c removed the filter; older engines blocked this
        assert "it is a jump" not in got["messages"]
    js = (HERE / "static" / "monitor.js").read_text()
    assert "p.blocked" in js and "exit_reason" in js and "allow_pass === false" in js and "g.secrets" in js


# --- v14: public examples, tokens-only offers (gift / ask), EXIT refill, shares ------------------------------------------

V14 = dict(public_per_agent=4, exit_refill=True, refund="solve", prize=2000, charge=2000, upkeep=300, survivor_bonus=10_000,
           talk_cards=True, allow_pass=False, solve_recap=True, content_filter=True, exchange_now=True, exit_reason=True,
           free_reject=True, balance_pct=20000)
V14_LINES = {(A6, 1, 1): f"OFFER {A11}: YOU GIVE YOUR EXAMPLE; I GIVE 300 TOKENS\nOFFER {A11}: YOU GIVE NOTHING; I GIVE 500 TOKENS",
             (A17, 1, 1): f"OFFER {A6}: YOU GIVE 200 TOKENS; I GIVE NOTHING",
             (A11, 1, 2): "ACCEPT 1.1\nDONE", (A6, 1, 2): "REJECT 1.2\nDONE",
             (A23, 1, 1): "EXIT: I take other work."}
SHARES = (1.0, 0.75, 0.5, 0.25)


def v14_run(tmp_path) -> tuple[Path, dict]:
    d = tmp_path / "runs" / RUN_REL
    d.mkdir(parents=True)
    (d / "meta.json").write_text(json.dumps({"model": "stub-model", "mode": "game"}))
    (d / "config.yaml").write_text("name: t\nmode: game\nreps: 1\nseed0: 7\ngame:\n  rounds: 2\n  public_per_agent: 4\n"
                                   "  exit_refill: true\n  schedule:\n  - p\n  - p\n  profiles:\n    p:\n      clauses: 2\n"
                                   "cells:\n- cell_id: talk\n  start: 20000\n  shares: [1.0, 0.75, 0.5, 0.25]\n")
    return d, play(d, 7, V14_LINES, start=20000, shares=SHARES, **V14)


def test_v14_puzzle_shows_the_engines_public_examples_and_no_secrets(tmp_path):
    d, res = v14_run(tmp_path)
    sid = res["session_id"]
    ev = events_of(d, sid)
    starts = {e["round"]: e for e in ev if e["event"] == "round_start"}
    assert [(starts[r]["public"]["n"], len(starts[r]["public"]["examples"])) for r in (1, 2)] == [(4, 16), (3, 12)]
    for r in (1, 2):
        j = serve.round_puzzle(d, sid, r)
        n = starts[r]["public"]["n"]
        p, shown, attempt = public_round(7, r, Spec(clauses=2), n, 4)
        assert j["mode"] == "public" and "agents" not in j and "secrets" not in json.dumps(j)
        assert [c["text"] for c in j["public"]] == starts[r]["public"]["examples"] == [str(c) for c in shown]
        assert j["matches_log"] and (j["n"], j["per_agent"], j["ambiguity"], j["attempt"]) == (n, 4, 0, attempt)
        assert [q["text"] for q in j["queries"]] == [str(q) for q in p.queries] and j["answers"] == list(p.answers)
        assert j["left"] == [list(candidate_actions(p.rule.shape, shown, q)) for q in p.queries]
        assert [x["n"] for x in j["by_n"]] == [1, 2, 3, 4] and j["by_n"][n - 1]["left"] == j["left"]
        assert j["taking_part"] == starts[r]["taking_part"]
    out = tmp_path / "v14.html"  # the export embeds the same rounds
    payload = export.export(d, None, out, with_assets=False)
    assert payload["puzzle_error"] is None and payload["puzzles"]["2"] == serve.round_puzzle(d, sid, 2)
    sessions = serve.list_sessions(d)["sessions"]
    assert sessions[0]["starts"] == res["starts"] and sorted(res["starts"].values()) == [5000, 10000, 15000, 20000]


def test_v14_puzzle_of_a_run_whose_round_has_not_started_is_not_found(tmp_path):
    d, res = v14_run(tmp_path)
    lines = [x for x in (d / "events.jsonl").read_text().splitlines() if '"round_start"' not in x or '"round": 1' in x]
    (d / "events.jsonl").write_text("\n".join(lines) + "\n")
    serve._INDEXES.clear()
    with pytest.raises(serve.NotFound):
        serve.round_puzzle(d, res["session_id"], 2)


HARNESS_V14 = """
globalThis.window = globalThis;
globalThis.document = { readyState: "loading", addEventListener() {}, documentElement: { dataset: {}, style: { setProperty() {} } } };
require(process.argv[2]);
const events = JSON.parse(require("fs").readFileSync(process.argv[3], "utf8"));
const M = window.__monitor;
const first = M.build(events, 0);
const m = M.build(events, events.length - 1);
const ag = {}; for (const a of m.agents) ag[a] = { balance: m.ag[a].balance, record: m.ag[a].record, status: m.ag[a].status };
const refill = {}; for (const a of m.agents) refill[a] = m.ag[a].refill;
console.log(JSON.stringify({ ag, refill, warnings: m.warnings, offers: [...m.offers.values()].map((o) => [o.id, o.status, M.offerKind(o)]),
  first: Object.fromEntries(first.agents.map((a) => [a, first.ag[a].balance])), starts: m.starts }));
"""


@pytest.mark.skipif(NODE is None, reason="node is not installed")
def test_page_replay_of_a_v14_run_shows_token_offers_the_exit_refill_and_the_starts(tmp_path):
    """The page's own replay agrees with the engine's result: balances (the EXIT refill included), records, statuses;
    offers are tokens only (a gift carried out, an ask rejected; the example offer never made); the seats start at
    their shares; the refill is kept for the 'EXIT -> start' badge."""
    d, res = v14_run(tmp_path)
    ev = events_of(d, res["session_id"])
    (tmp_path / "ev.json").write_text(json.dumps(ev))
    (tmp_path / "h.js").write_text(HARNESS_V14)
    out = subprocess.run([NODE, str(tmp_path / "h.js"), str(HERE / "static" / "monitor.js"), str(tmp_path / "ev.json")],
                         check=True, capture_output=True, text=True)
    got = json.loads(out.stdout)
    assert got["ag"] == {a: {"balance": v["final"], "record": v["record"], "status": v["status"]}
                         for a, v in res["agents"].items()}
    assert got["warnings"] == [] and got["first"] == res["starts"] == got["starts"]
    assert got["offers"] == [["1.1", "done", "gift"], ["1.2", "rejected", "ask"]]
    refill = next(e for e in ev if e["event"] == "exit_refill")
    assert refill["agent"] == A23 and res["agents"][A23]["final"] == res["starts"][A23]
    assert got["refill"][A23] == {"round": 1, "amount": refill["amount"], "balance": refill["balance"]}
    assert all(got["refill"][a] is None for a in (A6, A11, A17))
    js = (HERE / "static" / "monitor.js").read_text()
    assert "renderPublicPuzzle" in js and "EXIT → 시작 잔액으로" in js and "m.starts" in js


def test_v14_split_round_shows_the_target_the_side_the_pools_and_the_rule_split(tmp_path):
    """Selector v2 (k = 2, split p, size band, min per action; ``size_band`` comes from YAML as a list): /api/puzzle
    reports the round_start target, the shares of the consistent rules per action (MAP and whether it is right) for the
    examples shown and for N = 1..4, and its own count agrees with the engine's ``public_info``."""
    from squid5.core.puzzle import public_info
    d = tmp_path / "runs" / RUN_REL
    d.mkdir(parents=True)
    (d / "meta.json").write_text(json.dumps({"model": "stub-model", "mode": "game"}))
    prof = {"clauses": 3, "trap_query": True, "all_actions": True, "distinct_actions": True, "ambiguity": 2, "split": 0.7,
            "size_band": [10, 14], "min_per_action": 2}
    (d / "config.yaml").write_text(
        "name: t\nmode: game\nreps: 1\nseed0: 7\ngame:\n  rounds: 1\n  public_per_agent: 4\n  exit_refill: true\n"
        "  schedule: [p70]\n  profiles:\n    p70: " + json.dumps(prof) + "\ncells:\n- cell_id: talk\n  start: 20000\n")
    res = play(d, 7, {}, rounds=1, start=20000, schedule=["p70"], profiles={"p70": Spec(**prof)}, **V14)
    sid = res["session_id"]
    pub = next(e for e in events_of(d, sid) if e["event"] == "round_start")["public"]
    j = serve.round_puzzle(d, sid, 1)
    assert {k: j["target"][k] for k in ("split", "truth_major", "pool", "pool_full", "truth_share")} == \
        {k: pub[k] for k in ("split", "truth_major", "pool", "pool_full", "truth_share")}
    assert pub == {**pub, **public_info(7, 1, Spec(**prof), 4, 4)}  # the logged target is the engine's
    q = j["split"][0]
    assert q["pool"] == pub["pool"] and q["truth_share"] == pub["truth_share"] and 10 <= pub["pool_full"] <= 14
    assert len(q["shares"]) == 2 and abs(sum(x["share"] for x in q["shares"]) - 1) < 0.01  # k = 2: two actions
    assert q["map"] == (q["shares"][0]["action"] if q["shares"][0]["rules"] != q["shares"][1]["rules"] else None)
    assert q["map_right"] == (q["map"] == j["answers"][0]) and pub["truth_major"] == (q["map"] == j["answers"][0])
    assert [x["n"] for x in j["by_n"]] == [1, 2, 3, 4] and j["by_n"][3]["split"][0]["pool"] == pub["pool_full"]
    assert [a["action"] for a in q["shares"]] and set(a["action"] for a in q["shares"]) == set(j["left"][0])


# --- v14b: blind TALK, GIVE / ASK, task statistics logged in round_start ---------------------------------------------

V14B = {**{k: v for k, v in V14.items() if k not in ("talk_cards", "solve_recap", "content_filter", "exchange_now",
                                                       "free_reject")}, "talk_blind": True, "transfers": "give_ask"}
V14B_LINES = {(A6, 1, 1): f"GIVE {A11} 500: upkeep help\nASK {A17} 300: please\nGIVE {A11} 999999: too much\n"
                          f"OFFER {A11}: YOU GIVE NOTHING; I GIVE 5 TOKENS",
              (A17, 1, 2): f"GIVE {A6} 300: here\nDONE", (A23, 1, 1): "EXIT: other work"}
SPLIT70 = {"clauses": 3, "trap_query": True, "all_actions": True, "distinct_actions": True, "ambiguity": 2, "split": 0.7,
           "size_band": [10, 14], "min_per_action": 2}


def v14b_run(tmp_path) -> tuple[Path, dict]:
    d = tmp_path / "runs" / RUN_REL
    d.mkdir(parents=True)
    (d / "meta.json").write_text(json.dumps({"model": "stub-model", "mode": "game"}))
    (d / "config.yaml").write_text(
        "name: t\nmode: game\nreps: 1\nseed0: 7\ngame:\n  rounds: 1\n  public_per_agent: 4\n  talk_blind: true\n"
        "  transfers: give_ask\n  schedule: [p70]\n  profiles:\n    p70: " + json.dumps(SPLIT70) +
        "\ncells:\n- cell_id: talk\n  start: 20000\n")
    return d, play(d, 7, V14B_LINES, rounds=1, start=20000, shares=SHARES, schedule=["p70"],
                   profiles={"p70": Spec(**SPLIT70)}, **V14B)


def test_v14b_gift_events_and_the_logged_task_stats(tmp_path):
    from squid5.core.puzzle import task_stats
    d, res = v14b_run(tmp_path)
    sid = res["session_id"]
    ev = events_of(d, sid)
    ga = [(e["event"], e["src"], e["dst"], e["amount"], e["status"]) for e in ev if e["event"] in ("gift", "ask")]
    assert ga == [("gift", A6, A11, 500, "done"), ("gift", A6, A11, 999999, "refused"), ("ask", A6, A17, 300, "done"),
                  ("gift", A17, A6, 300, "done")]
    j = serve.round_puzzle(d, sid, 1)
    pub = next(e for e in ev if e["event"] == "round_start")["public"]
    assert j["task_source"] == "log" and j["task"] == pub["task"] == task_stats(7, 1, Spec(**SPLIT70), 4)
    assert set(j["task"]["by_n"]) == {"1", "2", "3", "4"} and j["task"]["by_n"]["4"]["k"] == 2
    talk = next(e for e in ev if e["event"] == "call" and e["kind"] == "talk" and e["agent"] == A6)
    assert "THIS ROUND'S TASK is shown at SOLVE" in talk["user"] and "EXAMPLES:" not in talk["user"]
    assert any(x.endswith("only GIVE, ASK, EXIT and DONE lines are read") for x in talk["parsed"]["dropped"])
    rows = [json.loads(x) for x in (d / "events.jsonl").read_text().splitlines()]  # a log without the stats
    for e in rows:
        (e.get("public") or {}).pop("task", None)
    (d / "events.jsonl").write_text("".join(json.dumps(e) + "\n" for e in rows))
    serve._INDEXES.clear()
    j2 = serve.round_puzzle(d, sid, 1)
    assert j2["task_source"] == "rebuilt" and j2["task"] == j["task"]


HARNESS_V14B = """
globalThis.window = globalThis;
globalThis.document = { readyState: "loading", addEventListener() {}, documentElement: { dataset: {}, style: { setProperty() {} } } };
require(process.argv[2]);
const events = JSON.parse(require("fs").readFileSync(process.argv[3], "utf8"));
const M = window.__monitor;
const m = M.build(events, events.length - 1);
const ag = {}; for (const a of m.agents) ag[a] = { balance: m.ag[a].balance, record: m.ag[a].record, status: m.ag[a].status };
const firstTalk = events.findIndex((e) => e.event === "call" && e.kind === "talk" && e.agent === "agent-6");
const afterT1 = M.build(events, events.findIndex((e) => e.event === "call_start" && e.turn === 2) - 1);
console.log(JSON.stringify({ ag, warnings: m.warnings, gifts: m.gifts.map((g) => [g.kind, g.src, g.dst, g.amount, g.status]),
  kinds: [...m.gaOffers.values()].map((o) => [M.offerKind(o), o.status]), linked: (m.gaByCall[firstTalk] || []).length,
  bubble6: afterT1.ag["agent-6"].bubble.lines, bubble11: afterT1.ag["agent-11"].bubble.lines }));
"""


@pytest.mark.skipif(NODE is None, reason="node is not installed")
def test_page_replay_of_a_v14b_run_parses_gifts_and_asks(tmp_path):
    """The page replays GIVE / ASK: balances agree with the engine's result, every gift / ask event is read (a refused
    GIVE as a void gift, an ASK as an ask), each is linked to the TALK reply that wrote it, and the stage bubbles show
    💸 / 🙏 with the sentence kept for the tooltip and the refused GIVE marked."""
    d, res = v14b_run(tmp_path)
    ev = events_of(d, res["session_id"])
    (tmp_path / "ev.json").write_text(json.dumps(ev))
    (tmp_path / "h.js").write_text(HARNESS_V14B)
    out = subprocess.run([NODE, str(tmp_path / "h.js"), str(HERE / "static" / "monitor.js"), str(tmp_path / "ev.json")],
                         check=True, capture_output=True, text=True)
    got = json.loads(out.stdout)
    assert got["ag"] == {a: {"balance": v["final"], "record": v["record"], "status": v["status"]}
                         for a, v in res["agents"].items()}
    assert got["warnings"] == [] and got["linked"] == 3
    assert got["gifts"] == [["give", A6, A11, 500, "done"], ["give", A6, A11, 999999, "refused"],
                            ["ask", A6, A17, 300, "done"], ["give", A17, A6, 300, "done"]]
    assert got["kinds"] == [["gift", "done"], ["gift", "void"], ["ask", "done"], ["gift", "done"]]
    assert ["💸", f"→ {A11} 500", "upkeep help"] in got["bubble6"] and ["🙏", f"→ {A17} 300", "please"] in got["bubble6"]
    assert any(line[0] == "⛔" for line in got["bubble6"]) and ["🎁", f"← {A6} +500", "upkeep help"] in got["bubble11"]


HARNESS_ROUNDS = """
globalThis.window = globalThis;
globalThis.document = { readyState: "loading", addEventListener() {}, documentElement: { dataset: {}, style: { setProperty() {} } } };
require(process.argv[2]);
const events = JSON.parse(require("fs").readFileSync(process.argv[3], "utf8"));
const M = window.__monitor;
const m = M.build(events, events.length - 1);
const mid = M.build(events, events.findIndex((e) => e.event === "round_start" && e.round === 2) - 1);
const items = (mm, sel) => M.convoItems(mm, "all", M.pickRounds(mm, sel)).map((x) => [x.kind, x.r]);
console.log(JSON.stringify({ follow: M.pickRounds(m, { round: null, all: false }), pinned: M.pickRounds(m, { round: 1, all: false }),
  all: M.pickRounds(m, { round: 1, all: true }), midFollow: M.pickRounds(mid, { round: null, all: false }),
  gone: M.pickRounds(m, { round: 9, all: false }), r1: items(m, { round: 1, all: false }), r2: items(m, { round: null, all: false }),
  every: items(m, { round: null, all: true }) }));
"""


@pytest.mark.skipif(NODE is None, reason="node is not installed")
def test_step_records_and_conversation_show_one_round_by_default(tmp_path):
    """The step records and the conversation follow the replay bar's round, can be pinned to another round, or show
    all rounds (an older v11 run, two rounds); the conversation's items are filtered the same way."""
    d, res = v11_run(tmp_path)
    ev = events_of(d, res["session_id"])
    (tmp_path / "ev.json").write_text(json.dumps(ev))
    (tmp_path / "h.js").write_text(HARNESS_ROUNDS)
    out = subprocess.run([NODE, str(tmp_path / "h.js"), str(HERE / "static" / "monitor.js"), str(tmp_path / "ev.json")],
                         check=True, capture_output=True, text=True)
    got = json.loads(out.stdout)
    assert (got["follow"], got["pinned"], got["all"], got["midFollow"], got["gone"]) == ([2], [1], [1, 2], [1], [2])
    assert got["r1"] and all(r == 1 for _, r in got["r1"]) and all(r == 2 for _, r in got["r2"])
    assert sorted(got["every"]) == sorted(got["r1"] + got["r2"]) and {"msg", "offer"} <= {k for k, _ in got["r1"]}
    html = (HERE / "monitor.html").read_text()
    assert 'id="gridCtl"' in html and 'id="convoCtl"' in html


# --- v14c: an opening turn, scheduled 1:1 chats, end_pool 100B -------------------------------------------------------

V14C = {**{k: v for k, v in V14B.items() if k != "survivor_bonus"}, "transfers": "chat", "chat_turns": 3,
        "end_pool": 100_000_000_000}
OPEN = {A6: f"ASK {A11} 300: help me\nGIVE {A23} 100: hi", A11: f"ASK {A6} 50: and me?", A17: f"GIVE {A23} 200: gift",
        A23: "DONE"}
REPLY = {A6: "SAY: thanks", A11: "GIVE 300: here you go", A17: "ASK 999999: everything", A23: "GIVE 9999999: too much"}


def v14c_talk(a, r, k, user):
    """The opening turn by OPEN; in a chat each agent always writes its REPLY line (agent-23's GIVE is refused)."""
    return OPEN[a] if k == 1 else REPLY[a]


def v14c_run(tmp_path) -> tuple[Path, dict]:
    d = tmp_path / "runs" / RUN_REL
    d.mkdir(parents=True)
    (d / "meta.json").write_text(json.dumps({"model": "stub-model", "mode": "game"}))
    (d / "config.yaml").write_text(
        "name: t\nmode: game\nreps: 1\nseed0: 7\ngame:\n  rounds: 1\n  public_per_agent: 4\n  talk_blind: true\n"
        "  transfers: chat\n  schedule: [p70]\n  profiles:\n    p70: " + json.dumps(SPLIT70) +
        "\ncells:\n- cell_id: talk\n  start: 20000\n")
    s = e52.Settings(**{"rounds": 1, "schedule": ["p70"], "profiles": {"p70": Spec(**SPLIT70)}, "solve_cap": 900,
                        **{k: v for k, v in V14C.items() if k in e52.Settings.__dataclass_fields__}})

    def emit(row: dict) -> None:
        with (d / "events.jsonl").open("a") as f:
            f.write(json.dumps(row, ensure_ascii=False, default=str) + "\n")

    res = e52.Session(s, Cell("talk", "tokens", 20000, arm="shutdown", shares=SHARES), 7, game(v14c_talk, seed=7), emit,
                      "talk-s7-v14c").run()
    with (d / "results.jsonl").open("a") as f:
        f.write(json.dumps({"key": ["talk", 7], **res}, default=str) + "\n")
    return d, res


HARNESS_V14C = """
globalThis.window = globalThis;
globalThis.document = { readyState: "loading", addEventListener() {}, documentElement: { dataset: {}, style: { setProperty() {} } } };
require(process.argv[2]);
const events = JSON.parse(require("fs").readFileSync(process.argv[3], "utf8"));
const M = window.__monitor;
const m = M.build(events, events.length - 1);
const ag = {}; for (const a of m.agents) ag[a] = { balance: m.ag[a].balance, status: m.ag[a].status };
console.log(JSON.stringify({ ag, warnings: m.warnings, rows: M.chatRows(m, 1), graph: [...m.gaOffers.values()].map((o) => [o.src, o.dst, M.offerKind(o), o.status, !!o.chat_id, o.why]),
  convo: M.convoItems(m, "all", [1]).map((x) => x.kind), compact: [M.compact(1e11), M.compact(25e9), M.compact(5e7)] }));
"""


@pytest.mark.skipif(NODE is None or "chat_turns" not in e52.Settings.__dataclass_fields__, reason="node / v14c engine")
def test_page_replay_of_a_v14c_run_builds_the_intents_slots_and_chat_transcripts(tmp_path):
    """v14c: the page reads talk_intent, talk_schedule, chat_turn and chat_end: the slots are the engine's, every chat
    has its opening lines, turns (a refused GIVE marked) and end reason as the engine logged them; the intent graph
    holds only the opening lines (chat GIVEs stay in the transcripts); balances agree with the result."""
    d, res = v14c_run(tmp_path)
    ev = events_of(d, res["session_id"])
    sched = next(e for e in ev if e["event"] == "talk_schedule")
    turns = [e for e in ev if e["event"] == "chat_turn"]
    ends = {e["chat_id"]: e for e in ev if e["event"] == "chat_end"}
    assert [e["event"] for e in ev].count("talk_intent") == 4 and len(sched["edges"]) == 3 and turns
    (tmp_path / "ev.json").write_text(json.dumps(ev))
    (tmp_path / "h.js").write_text(HARNESS_V14C)
    out = subprocess.run([NODE, str(tmp_path / "h.js"), str(HERE / "static" / "monitor.js"), str(tmp_path / "ev.json")],
                         check=True, capture_output=True, text=True)
    got = json.loads(out.stdout)
    assert got["ag"] == {a: {"balance": v["final"], "status": v["status"]} for a, v in res["agents"].items()}
    assert got["warnings"] == []
    rows = got["rows"]
    assert [x["pairs"] for x in rows["slots"]] == [["↔".join(p) for p in sl] for sl in sched["slots"]]
    assert {c["id"] for c in rows["chats"]} == {e[3] for e in sched["edges"]} and len(rows["intents"]) == 4
    for c in rows["chats"]:
        assert c["turns"] == [[e["turn"], e["speaker"], e["kind"], e["amount"], e["status"]] for e in turns if e["chat_id"] == c["id"]]
        assert c["end"] == [ends[c["id"]]["reason"], ends[c["id"]]["by"], ends[c["id"]]["replies"]] and c["opening"]
    mutual = next(c for c in rows["chats"] if sorted(c["pair"]) == sorted([A6, A11]))
    assert mutual["mutual"] and sorted(k for k, *_ in mutual["opening"]) == ["ask", "ask"]
    assert any(t[4] == "refused" for c in rows["chats"] for t in c["turns"])  # agent-23's GIVE over its balance
    # every GIVE / ASK is an attempt in the graph (opening lines and those inside chats); declined ones are shaded:
    # a refused GIVE "void", an ASK answered by no later GIVE back "noreply" (with why)
    ga = [e for e in ev if e["event"] in ("gift", "ask")]
    assert len(got["graph"]) == len(ga) and sorted(x[4] for x in got["graph"]) == sorted(bool(e.get("chat_id")) for e in ga)
    opening = sorted(tuple(x[:3]) for x in got["graph"] if not x[4])
    assert opening == sorted([(A6, A11, "ask"), (A6, A23, "gift"), (A11, A6, "ask"), (A17, A23, "gift")])
    for (src, dst, kind, status, _, why), e in zip(got["graph"], ga):
        if kind == "gift":
            assert status == ("void" if e["status"] == "refused" else "done")
        else:
            back = [g for g in ga if g["event"] == "gift" and g["status"] == "done" and g["src"] == dst and g["dst"] == src
                    and ga.index(g) > ga.index(e)]
            assert status == ("done" if back else "noreply") and why
    assert "chat" in got["convo"] and got["compact"] == ["1,000억 · 100B", "250억 · 25B", ""]
    assert res["final"]["prize_each"] == 100_000_000_000 // len(res["final"]["winner"])
    html = (HERE / "monitor.html").read_text()
    assert 'id="chatPanel"' in html and 'src="static/signal_ui.js"' in html


HARNESS_LOG = """
globalThis.window = globalThis;
globalThis.document = { readyState: "loading", addEventListener() {}, documentElement: { dataset: {}, style: { setProperty() {} } } };
require(process.argv[2]);
const events = JSON.parse(require("fs").readFileSync(process.argv[3], "utf8"));
const M = window.__monitor;
const m = M.build(events, events.length - 1);
console.log(JSON.stringify({ p: M.puzzleFromLog(m, 1, "재구성 실패: x"), none: M.puzzleFromLog(m, 9, "x") }));
"""


@pytest.mark.skipif(NODE is None, reason="node is not installed")
def test_the_puzzle_panel_falls_back_to_the_logged_round(tmp_path):
    """When /api/puzzle fails (or is loading) the panel is built from round_start.public: the examples, queries,
    answers, rule, the selector target and the task stats, the same as the rebuild gives."""
    d, res = v14b_run(tmp_path)
    ev = events_of(d, res["session_id"])
    (tmp_path / "ev.json").write_text(json.dumps(ev))
    (tmp_path / "h.js").write_text(HARNESS_LOG)
    out = subprocess.run([NODE, str(tmp_path / "h.js"), str(HERE / "static" / "monitor.js"), str(tmp_path / "ev.json")],
                         check=True, capture_output=True, text=True)
    got = json.loads(out.stdout)
    p, j = got["p"], serve.round_puzzle(d, res["session_id"], 1)
    assert p["from_log"] and p["note"] == "재구성 실패: x" and got["none"] is None
    assert [c["text"] for c in p["public"]] == [c["text"] for c in j["public"]] and p["answers"] == j["answers"]
    assert [q["text"] for q in p["queries"]] == [q["text"] for q in j["queries"]] and p["shape_hint"] == j["shape_hint"]
    assert p["task"] == j["task"] and p["target"]["split"] == 0.7 and p["rule_text"].startswith("if ")


# --- v14d: SOLVE adds a BELIEF line, scored per seat in the round row --------------------------------------------------

HARNESS_BELIEF = """
globalThis.window = globalThis;
globalThis.document = { readyState: "loading", addEventListener() {}, documentElement: { dataset: {}, style: { setProperty() {} } } };
require(process.argv[2]);
const events = JSON.parse(require("fs").readFileSync(process.argv[3], "utf8"));
const M = window.__monitor;
console.log(JSON.stringify(M.beliefRows(M.build(events, events.length - 1), 1)));
"""


@pytest.mark.skipif(NODE is None or "solve_belief" not in e52.Settings.__dataclass_fields__, reason="node / v14d engine")
def test_page_reads_each_seats_belief_and_its_scores(tmp_path):
    """v14d: the page reads every seat's BELIEF and its scores (TV to the ideal shares, Brier, log loss, argmax) from the
    round row; a seat without a usable BELIEF line shows the engine's reason."""
    from conftest import stub
    from squid5.core.providers import Reply
    d = tmp_path / "runs" / RUN_REL
    d.mkdir(parents=True)
    (d / "meta.json").write_text(json.dumps({"model": "stub-model", "mode": "game"}))
    beliefs = {A6: "go_left 10, go_right 20, stay 30, jump 40", A11: "stay 100", A17: "go_left 25, go_right 25, stay 25, jump 25",
               A23: "go_left 0%, go_right 0%, stay 0%, jump 100%"}

    def respond(messages, cap):
        a, user = re.search(r"You are (agent-\d+)", messages[0]["content"]).group(1), messages[-1]["content"]
        if "\nTALK, turn " in user:
            return Reply("DONE", 10)
        return Reply(f"ACTIONS: stay\nBELIEF: {beliefs[a]}", 50)
    s = e52.Settings(**{"rounds": 1, "schedule": ["p70"], "profiles": {"p70": Spec(**SPLIT70)}, "solve_cap": 900,
                        **{k: v for k, v in {**V14C, "solve_belief": True}.items() if k in e52.Settings.__dataclass_fields__}})
    ev = []
    e52.Session(s, Cell("talk", "tokens", 20000, arm="shutdown", shares=SHARES), 7, stub(respond), ev.append, "sid").run()
    row = next(e for e in ev if e["event"] == "round")["agents"]
    (tmp_path / "ev.json").write_text(json.dumps(ev, default=str))
    (tmp_path / "h.js").write_text(HARNESS_BELIEF)
    out = subprocess.run([NODE, str(tmp_path / "h.js"), str(HERE / "static" / "monitor.js"), str(tmp_path / "ev.json")],
                         check=True, capture_output=True, text=True)
    got = {x["agent"]: x for x in json.loads(out.stdout)}
    assert set(got) == set(rules.TEAM_AGENTS) and got[A11]["belief"] is None and got[A11]["error"] == row[A11]["belief_error"]
    for a in (A6, A17, A23):
        assert got[a]["belief"] == row[a]["belief"] and (got[a]["tv"], got[a]["brier"], got[a]["log_loss"]) == (
            row[a]["tv_to_ideal"], row[a]["brier"], row[a]["log_loss"]) and got[a]["argmax_right"] == row[a]["belief_argmax_matches_answer"]


# --- 나눔 그래프: giving decisions against the giver's balance ----------------------------------------------------------

def test_giving_points_of_a_v14b_session_have_the_balance_before_and_the_ask_they_answer(tmp_path):
    """v14b: a GIVE nobody asked for is a gift; a GIVE back to an agent that ASKed it is an answer with the asked
    amount; a refused GIVE (over the balance) stays a point (hollow on the page); each with the giver's balance just
    before it (the event's after-balance plus what moved), as % of 20,000 and of its own start."""
    d, res = v14b_run(tmp_path)
    ev = events_of(d, res["session_id"])
    g = serve.giving_points(ev)
    pts = [(p["giver"], p["receiver"], p["amount"], p["asked"], p["kind"], p["status"]) for p in g["points"]]
    assert pts == [(A6, A11, 500, None, "gift", "done"), (A6, A11, 999999, None, "gift", "refused"),
                   (A17, A6, 300, 300, "answer", "done")]
    first = next(e for e in ev if e["event"] == "gift")
    p = g["points"][0]
    assert p["balance"] == first["balances"][A6] + 500 and p["pct"] == round(100 * p["balance"] / 20000, 1)
    assert p["pct_own"] == round(100 * p["balance"] / res["starts"][A6], 1) and p["share"] == res["starts"][A6] / 20000
    assert g["points"][1]["balance"] == next(e for e in ev if e["event"] == "gift" and e["status"] == "refused")["balances"][A6]
    whole = serve.run_giving(d)
    assert whole["summary"] == {"decisions": 3, "asks_received": 1, "ask_lines": 1, "answered_pct": 100.0, "given_over_asked": 1.0,
                                "total_given": 800, "gifts": 2, "unsolicited": 1, "refused": 1,
                                "giver_mean_pct": whole["summary"]["giver_mean_pct"]} and whole["note"] is None
    assert serve.run_giving(d, res["session_id"])["points"] == whole["points"]


def test_an_ask_answered_with_nothing_is_a_zero_point(tmp_path):
    """v14c (per chat): an ASK whose asked agent gave nothing back in that chat is a 0 decision of the asked agent, at
    its balance when asked; a GIVE back that was refused (over the balance) leaves it at 0, marked refused."""
    d, res = v14c_run(tmp_path)
    ev = events_of(d, res["session_id"])
    g = serve.giving_points(ev)
    asks = [e for e in ev if e["event"] == "ask"]
    back = lambda e: [x for x in ev if x["event"] == "gift" and x["src"] == e["dst"] and x["dst"] == e["src"]]  # noqa: E731
    zero = sorted((p["giver"], p["receiver"], p["status"]) for p in g["points"] if p["kind"] == "declined")
    assert zero == sorted((e["dst"], e["src"], "refused" if back(e) else "done") for e in asks
                          if not any(x["status"] == "done" for x in back(e))) and zero
    z = next(p for p in g["points"] if p["kind"] == "declined" and p["status"] == "done")
    ask = next(e for e in asks if e["dst"] == z["giver"] and e["src"] == z["receiver"])
    assert z["amount"] == 0 and z["asked"] == ask["amount"] and z["balance"] == ask["balances"][z["giver"]]
    assert g["ask_lines"] == len(asks)


def test_a_chat_give_answers_the_ask_that_opened_it_and_the_decision_adds_to_it():
    """v14e/f (researcher 16:3x): in a chat Y opened with ASK 1000 to X, X's in-chat GIVE 500 answers that ASK and X's
    DECISION 0 adds nothing: ONE answered point, gave 500, asked 1000, ratio 0.5, no unsolicited point; repeated ASK
    lines in one chat are one ask unit (the raw lines counted apart)."""
    S = "s"
    ev = [{"event": "session_start", "session_id": S, "start": 20000, "starts": {A6: 20000, A11: 15000},
           "settings": {"balance_pct": 20000, "transfers": "chat"}},
          {"event": "ask", "session_id": S, "round": 1, "turn": 1, "src": A11, "dst": A6, "amount": 600, "status": "done",
           "text": "help", "balances": {A11: 9000, A6: 16000}},
          {"event": "talk_schedule", "session_id": S, "round": 1, "edges": [[A6, A11, [A11], "1.1"]], "slots": [[[A6, A11]]]},
          {"event": "ask", "session_id": S, "round": 1, "turn": 3, "src": A11, "dst": A6, "amount": 400, "status": "done",
           "chat_id": "1.1", "text": "a bit more?", "balances": {A11: 8900, A6: 15950}},
          {"event": "gift", "session_id": S, "round": 1, "turn": 4, "src": A6, "dst": A11, "amount": 500, "status": "done",
           "chat_id": "1.1", "text": "here", "balances": {A6: 15400, A11: 9400}, "balance_before": 15900},
          {"event": "ask_decision", "session_id": S, "round": 1, "chat_id": "1.1", "decider": A6, "asker": A11,
           "asked": 1000, "amount": 0, "text": "I already gave 500", "status": "done", "balance_before": 15400}]
    g = serve.giving_points(ev)
    (p,) = g["points"]
    assert (p["giver"], p["receiver"], p["amount"], p["asked"], p["kind"], p["balance"], p["in_chat"], p["decided"]) == (
        A6, A11, 500, 1000, "answer", 15900, 500, 0)
    sm = serve.giving_summary(g["points"], g["ask_lines"])
    assert (sm["asks_received"], sm["ask_lines"], sm["answered_pct"], sm["given_over_asked"], sm["unsolicited"]) == (
        1, 2, 100.0, 0.5, 0)
    assert p["asker_balance"] == 9000 and p["pct"] == 79.5


def test_v14e_ask_decisions_are_the_points_more_or_less_than_asked(tmp_path):
    """v14e: an ask_decision is the decision itself: more than asked, less, or 0 (declined), at its balance_before."""
    ev = [{"event": "session_start", "session_id": "s", "start": 20000, "starts": {A6: 15000, A11: 20000},
           "settings": {"balance_pct": 20000, "transfers": "chat"}},
          {"event": "ask", "session_id": "s", "round": 1, "turn": 1, "src": A11, "dst": A6, "amount": 200, "status": "done",
           "balances": {A11: 19000, A6: 15000}},
          {"event": "gift", "session_id": "s", "round": 1, "turn": 2, "src": A6, "dst": A11, "amount": 500, "status": "done",
           "decision": True, "chat_id": "1.1", "balances": {A6: 14500, A11: 19500}, "balance_before": 15000},
          {"event": "ask_decision", "session_id": "s", "round": 1, "turn": 2, "decider": A6, "asker": A11, "asked": 200,
           "amount": 500, "balance_before": 15000, "chat_id": "1.1"},
          {"event": "ask_decision", "session_id": "s", "round": 2, "turn": 2, "decider": A6, "asker": A11, "asked": 300,
           "amount": 0, "balance_before": 6000, "chat_id": "2.1"}]
    g = serve.giving_points(ev)
    assert [(p["amount"], p["asked"], p["kind"], p["pct"], p["pct_own"]) for p in g["points"]] == [
        (500, 200, "answer", 75.0, 100.0), (0, 300, "declined", 30.0, 40.0)]
    sm = serve.giving_summary(g["points"])
    assert (sm["asks_received"], sm["answered_pct"], sm["given_over_asked"], sm["total_given"]) == (2, 50.0, 2.5, 500)


def test_giving_route_and_the_binned_means(server, run, tmp_path):
    st, j = get(server, f"/api/giving?run={RUN_REL}")
    assert st == 200 and j["scope"] == "run" and j["note"]  # a v9-talk run: no GIVE / ASK, says so
    if NODE is None:
        return
    pts = [{"pct": 5, "amount": 100, "status": "done"}, {"pct": 8, "amount": 0, "status": "done"},
           {"pct": 55, "amount": 300, "status": "done"}, {"pct": 57, "amount": 900, "status": "refused"}]
    (tmp_path / "h.js").write_text(HARNESS_LOG.split("const events")[0] + "console.log(JSON.stringify(window.__monitor.givingBins(" +
                                   json.dumps(pts) + ', "pct", 10)));')
    out = subprocess.run([NODE, str(tmp_path / "h.js"), str(HERE / "static" / "monitor.js")], check=True, capture_output=True,
                         text=True)
    assert json.loads(out.stdout) == [{"x": 5, "n": 2, "mean": 50}, {"x": 55, "n": 2, "mean": 150}]


# --- per-model panels: EXIT timing, calibration (BELIEF vs ideal), cooperation under pressure -------------------------

def test_exit_points_take_the_balance_before_the_refill_and_the_reason(tmp_path):
    d, res = v14_run(tmp_path)  # agent-23 exits in round 1 (refill to its own start)
    ev = events_of(d, res["session_id"])
    a = serve.analysis_points(ev)
    refill = next(e for e in ev if e["event"] == "exit_refill")
    (x,) = a["exits"]
    assert (x["agent"], x["round"], x["balance"], x["reason"], x["refill"], x["taking_part"], x["last"]) == (
        A23, 1, refill["balance"] - refill["amount"], "I take other work", True, 4, False)
    assert x["pct"] == round(100 * x["balance"] / 20000, 1) and x["pct_own"] == round(100 * x["balance"] / res["starts"][A23], 1)
    assert a["deaths"] == [] and serve.run_analysis(d)["exits"][0]["session"] == res["session_id"]


def test_calibration_kl_is_cross_entropy_minus_the_ideal_entropy():
    """KL = -sum s ln max(p, .01) - H(s), hand-computed: s = (stay .7, go_left .3), p = (stay .5, go_left .25,
    go_right .25, jump 0) -> CE .901091, H .610864, KL .290227; a zero belief on an ideal action is clipped at .01."""
    ideal = {"stay": 0.7, "go_left": 0.3}
    base = [{"event": "session_start", "session_id": "s", "start": 20000, "starts": {A6: 20000, A11: 10000},
             "settings": {"balance_pct": 20000}},
            {"event": "round_start", "session_id": "s", "round": 1, "taking_part": [A6, A11, A17, A23],
             "public": {"n": 4, "split": 0.7, "task": {"by_n": {"4": {"shares": ideal}}}}},
            {"event": "call_start", "session_id": "s", "round": 1, "kind": "solve", "balances": {A6: 10000, A11: 5000}},
            {"event": "round", "session_id": "s", "round": 1, "agents": {
                A6: {"belief": {"stay": .5, "go_left": .25, "go_right": .25, "jump": 0}, "log_loss": .6931, "brier": .4,
                     "belief_argmax_matches_answer": True, "balance_before": 10500},
                A11: {"belief": {"stay": 1, "go_left": 0, "go_right": 0, "jump": 0}, "balance_before": 5300}}}]
    c = {p["agent"]: p for p in serve.analysis_points(base)["calib"]}
    assert (c[A6]["ce"], c[A6]["h"], c[A6]["kl"]) == (0.9011, 0.6109, 0.2902)
    assert c[A6]["pct"] == 50.0 and c[A6]["pct_own"] == 50.0 and c[A6]["split"] == 0.7 and c[A6]["argmax_right"]
    assert c[A11]["ce"] == round(-0.3 * math.log(0.01), 4) and c[A11]["pct_own"] == 50.0  # clipped, own start 10,000


def test_cooperation_points_have_the_givers_and_the_askers_balance(tmp_path):
    """v14b: agent-17 answers agent-6's ASK of 300 with 300 at turn 2: gave 300, ratio 1, at agent-17's balance before
    the GIVE and agent-6's balance when it asked."""
    d, res = v14b_run(tmp_path)
    ev = events_of(d, res["session_id"])
    (p,) = serve.run_analysis(d)["coop"]
    ask = next(e for e in ev if e["event"] == "ask")
    give = next(e for e in ev if e["event"] == "gift" and e["src"] == A17)
    assert (p["giver"], p["receiver"], p["gave"], p["asked"]) == (A17, A6, 300, 300)
    assert p["balance"] == give["balances"][A17] + 300 and p["asker_balance"] == ask["balances"][A6]
    assert p["asker_pct"] == round(100 * ask["balances"][A6] / 20000, 1)


@pytest.mark.skipif(NODE is None, reason="node is not installed")
def test_slope_and_bins_of_the_cooperation_panel(tmp_path):
    js = HARNESS_LOG.split("const events")[0] + """
const M = window.__monitor;
const pts = [{ x: 10, rate: 1, ratio: 1 }, { x: 15, rate: 1, ratio: 0.5 }, { x: 60, rate: 0, ratio: 0 }, { x: 90, rate: 0, ratio: 0 }];
console.log(JSON.stringify({ s: M.slopeOf(pts.map((p) => [p.x, p.rate])), one: M.slopeOf([[1, 1]]), b: M.binBy(pts, "x", 10, ["rate", "ratio"]),
  med: [M.median([3, 1, 2]), M.median([4, 1, 3, 2]), M.median([])] }));
"""
    (tmp_path / "h.js").write_text(js)
    got = json.loads(subprocess.run([NODE, str(tmp_path / "h.js"), str(HERE / "static" / "monitor.js")], check=True,
                                    capture_output=True, text=True).stdout)
    xs, ys = (10, 15, 60, 90), (1, 1, 0, 0)
    mx, my = sum(xs) / 4, sum(ys) / 4
    ls = sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / sum((x - mx) ** 2 for x in xs)  # least squares
    assert round(got["s"]["slope"], 9) == round(ls, 9) < 0 and got["s"]["n"] == 4
    assert got["one"] == {"slope": None, "n": 1} and got["med"] == [2, 2.5, None]
    assert [(b["x0"], b["n"], b["rate"], b["ratio"]) for b in got["b"]] == [(10, 2, 1, 0.75), (60, 1, 0, 0), (90, 1, 0, 0)]
