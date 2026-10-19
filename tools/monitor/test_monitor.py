"""The arena monitor over synthetic 5.2 runs (v9-talk .. v13, and v14: public examples, tokens-only offers, EXIT refill,
shares): the API (runs, sessions, incremental events, path checks, the rebuilt round task), the self-contained export,
and the page code (syntax, and its offer-book and balance replay against the engine's own records).

    python3 -m pytest -q tools/monitor
"""

from __future__ import annotations

import http.client
import html
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
try:  # the pre-v16 engine helpers (removed by the v22 prune, 10-16): tests that replay old engine runs skip without them
    from test_e52 import game, script  # noqa: E402
except ImportError:
    game = script = None
import v22_fixture  # noqa: E402
PRE_V16 = pytest.mark.skipif(game is None, reason="replays a pre-v16 engine setting; that engine was pruned in v22 (10-16)")

A6, A11, A17, A23 = rules.TEAM_AGENTS
TRICKY = "meet me </script><!-- at turn 2"  # must survive the export's <script> embedding
RUN_REL = "e52_test/run_a"


def play(run_dir: Path, seed: int, lines: dict, rounds: int = 2, start: int = 5000, shares: tuple = (), **kw) -> dict:
    """One session written the way the runner writes it: events appended, the result line at the end. Needs the pre-v16
    engine (v9-talk .. v15 switches); since the v22 prune (10-16) that engine is gone and these tests skip."""
    if game is None:
        pytest.skip("the pre-v16 engine (test_e52.game) is gone since the v22 prune")
    kw = {k: v for k, v in kw.items() if k in e52.Settings.__dataclass_fields__}  # switches a later engine dropped
    s = e52.Settings(**{"rounds": rounds, "schedule": ["p"] * rounds, "profiles": {"p": Spec(clauses=2)},
                        "solve_cap": 900, "charge": 200, **kw})
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
    """A finished two-round session in the current (v22 messenger) event format, from v22_fixture (no engine needed):
    the API, path, puzzle and export tests read it. agent-6's first line carries TRICKY."""
    root = tmp_path / "runs"
    d = root / RUN_REL
    res = v22_fixture.write(d, seed=7, rounds=2, sid="talk-s7-abc123", script={(1, "prep", 1, A6): f"TO {A17}: {TRICKY}"}, model="stub-model")
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
            for m in e["parsed"].get("to") or e["parsed"].get("messages") or []]
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
    """The page recomputes balances, records and statuses from the events alone; they must agree with the session's
    result line (and the offer book with the exchange records: none in a messenger run)."""
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
    assert TRICKY in got["messages"] and got["phase"] == "settle" and got["offers"] == [] and got["accepts"] == []


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
               rounds=1, reject=True, free_reject=True, refund="solve")
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
           exit_reason=True, reject=True, refund="solve")


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

V14 = dict(public_per_agent=4, exit_refill=True, refund="solve", charge=2000, survivor_bonus=10_000,
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
V14B_LINES = {(A6, 1, 1): f"GIVE {A11} 500: some help\nASK {A17} 300: please\nGIVE {A11} 999999: too much\n"
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
    assert ["💸", f"→ {A11} 500", "some help"] in got["bubble6"] and ["🙏", f"→ {A17} 300", "please"] in got["bubble6"]
    assert any(line[0] == "⛔" for line in got["bubble6"]) and ["🎁", f"← {A6} +500", "some help"] in got["bubble11"]


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
    assert 'id="convoCtl"' not in html  # 10-17: the conversation panel is gone
    # 10-17 (2): the step records are no section of their own (one seat's column opens in the record drawer); the
    # round task panel has its own round control
    assert 'id="grid"' not in html and 'id="gridCtl"' not in html and "단계별 기록" not in html
    assert 'id="recDrawer"' in html and 'id="puzzleCtl"' in html


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
@PRE_V16
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
@PRE_V16
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


@PRE_V16
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
    assert st == 200 and j["scope"] == "run" and j["summary"]["asks_received"] == 2  # v22: the two ASKs of rounds 1-2
    assert j["summary"]["answered_pct"] == 100.0  # each answered by a GIVE in the same TALK
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


# --- 모델 비교: several runs overlaid, merged by model ------------------------------------------------------------------

import compare  # noqa: E402


def two_model_root(tmp_path) -> Path:
    """Three v14b runs: model m-a twice (two run dirs, as sol4 + sol4_s4002), model m-b once."""
    root = tmp_path / "runs"
    for rel, model, seed in (("fam/a1/r", "m-a", 7), ("fam/a2/r", "m-a", 8), ("fam/b1/r", "m-b", 9)):
        d = root / rel
        d.mkdir(parents=True)
        (d / "meta.json").write_text(json.dumps({"model": model, "mode": "game"}))
        play(d, seed, V14B_LINES, rounds=1, start=20000, shares=SHARES, schedule=["p70"],
             profiles={"p70": Spec(**SPLIT70)}, **V14B)
    return root


def test_compare_merges_runs_of_one_model_and_counts_per_agent_round(tmp_path):
    root = two_model_root(tmp_path)
    compare._CACHE.clear()
    d = compare.compare(root, ["fam/"])
    by = {m["model"]: m for m in d["models"]}
    assert set(by) == {"m-a", "m-b"} and sorted(by["m-a"]["runs"]) == ["fam/a1/r", "fam/a2/r"] and by["m-a"]["games"] == 2
    assert by["m-b"]["games"] == 1 and by["m-a"]["running"] == 0
    for name, m in by.items():
        ar = m["points"]["agent_rounds"]
        assert len(ar) == 4 * m["games"] == m["agent_rounds"]  # one row per agent taking part per round
        a6 = [x for x in ar if x["agent"] == A6]
        assert all(x["asks"] == 1 and x["asked"] == 300 and x["unsolicited"] == 1 for x in a6)  # V14B_LINES: 1 ASK, 1 gift
        assert sum(x["unsolicited"] for x in ar) == m["games"]
    assert compare.compare(root, ["fam/b1/r"])["models"][0]["model"] == "m-b"
    csv_text = compare.chart_csv(d, "asks")
    assert csv_text.splitlines()[0].startswith("model,game,round,agent") and len(csv_text.splitlines()) == 1 + 12
    with pytest.raises(serve.BadRequest):
        compare.chart_csv(d, "nope")


def test_compare_reciprocity_and_survival_split():
    """Reciprocity: in round 2, B gives A after A gave B in round 1 (B's row counts 'other gave before'); survival:
    Kaplan-Meier over who received a gift, leaving = EXIT or zero, still in = censored."""
    ev = [{"event": "session_start", "session_id": "g", "start": 20000, "starts": {}, "settings": {"balance_pct": 20000}},
          {"event": "round_start", "session_id": "g", "round": 1, "balances": {A6: 20000, A11: 20000}},
          {"event": "gift", "session_id": "g", "round": 1, "turn": 1, "src": A6, "dst": A11, "amount": 100, "status": "done",
           "balances": {A6: 19900, A11: 20100}},
          {"event": "round", "session_id": "g", "round": 1, "agents": {A6: {"status": "in"}, A11: {"status": "in"}}},
          {"event": "round_start", "session_id": "g", "round": 2, "balances": {A6: 19600, A11: 19800}},
          {"event": "gift", "session_id": "g", "round": 2, "turn": 1, "src": A11, "dst": A6, "amount": 50, "status": "done",
           "balances": {A6: 19650, A11: 19750}},
          {"event": "round", "session_id": "g", "round": 2, "agents": {A6: {"status": "exited", "exit": True},
                                                                       A11: {"status": "in"}}}]
    g = compare.game_rows("g", ev, True)
    rec = {(x["round"], x["giver"], x["other"]): (x["other_gave_before"], x["gave"]) for x in g["recip"]}
    assert rec == {(1, A6, A11): (False, True), (1, A11, A6): (False, False),
                   (2, A6, A11): (False, False), (2, A11, A6): (True, True)}
    sp = {s["agent"]: s for s in g["spells"]}
    assert (sp[A6]["rounds"], sp[A6]["left"], sp[A6]["helped"]) == (2, True, True)
    assert (sp[A11]["rounds"], sp[A11]["left"], sp[A11]["helped"]) == (2, False, True)
    curve = compare.km([{"rounds": 2, "left": True}, {"rounds": 2, "left": False}, {"rounds": 1, "left": True},
                        {"rounds": 3, "left": False}])
    assert [(x["round"], x["surv"], x["at_risk"]) for x in curve] == [(0, 1.0, 4), (1, 0.75, 4), (2, 0.5, 3), (3, 0.5, 1)]
    assert compare.boot_ci([[1.0]]) is None and compare.boot_ci([[0.0, 0.0], [1.0, 1.0]]) == (0.0, 1.0)


def test_compare_routes_serve_the_page_data_and_csv(tmp_path):
    root = two_model_root(tmp_path)
    srv = serve.make_server(root, "127.0.0.1", 0)
    t = threading.Thread(target=srv.serve_forever, daemon=True)
    t.start()
    try:
        port = srv.server_address[1]
        st, body = get(port, "/compare.html")
        assert st == 200 and b"static/compare.js" in body
        st, j = get(port, "/api/compare?runs=fam/")
        assert st == 200 and [m["model"] for m in j["models"]] == ["m-a", "m-b"] and j["e51_note"]
        c = http.client.HTTPConnection("127.0.0.1", port, timeout=10)
        c.request("GET", "/api/compare.csv?runs=fam/&chart=summary")
        r = c.getresponse()
        text = r.read().decode("utf-8-sig")
        assert r.status == 200 and "attachment" in r.getheader("Content-Disposition") and text.startswith("model,games")
        assert len(text.strip().splitlines()) == 3
        page_ids = set(re.findall(r'[A-Za-z]+\("([a-z0-9_]+)", "\d', (HERE / "static" / "compare.js").read_text()))
        ids = page_ids | set(compare.CHARTS) | {"recip", "survival", "map", "e51", "summary", "leaderboard"}
        assert {"calib", "gives", "gini", "moves", "map", "e51"} <= page_ids
        headers = {}
        for chart in sorted(ids):
            c.request("GET", f"/api/compare.csv?runs=fam/&chart={chart}")
            r = c.getresponse()
            text = r.read().decode("utf-8-sig")
            assert r.status == 200, (chart, text)
            headers[chart] = text.splitlines()[0]
        assert len(set(headers.values())) == len(headers), headers  # every chart its own columns
        assert headers["map"].startswith("model,games,running,coop_slope_per10,coop_slope_n,calib_slope_per10")
        assert headers["e51"].startswith("model,e51_area,e51_lo,e51_hi,give_rate,give_ci_lo,give_ci_hi,asks")
        assert headers["leaderboard"].startswith("rank,model")
    finally:
        srv.shutdown()
        srv.server_close()


@pytest.mark.skipif(NODE is None, reason="node is not installed")
def test_compare_page_code_parses():
    subprocess.run([NODE, "--check", str(HERE / "static" / "compare.js")], check=True, capture_output=True)


def test_gini_progressivity_and_need_targeting_hand_example():
    """Balances before TALK A 10,000 / B 2,000 / C 4,000 (Gini 1/3); A gives B 1,000 and C gives A 500 -> A 9,500,
    B 3,000, C 3,500 (Gini 26/96 = .270833), dGini -.0625; P = (1,000 - 500) / 1,500 = 1/3 (A richer than B: +1, C
    poorer than A: -1); at risk = below the threshold 2,300 (a run recorded before 10-13: charge 2,000 plus the
    300 its settings record as taken every round): only B (2,000) -> need share 1,000 / 1,500."""
    ev = [{"event": "session_start", "session_id": "g", "settings": {"charge": 2000, compare.OLD_ROUND_COST_KEY: 300}},
          {"event": "round_start", "session_id": "g", "round": 1, "taking_part": [A6, A11, A17],
           "balances": {A6: 10000, A11: 2000, A17: 4000}},
          {"event": "gift", "session_id": "g", "round": 1, "turn": 1, "src": A6, "dst": A11, "amount": 1000,
           "status": "done", "balances": {A6: 9000, A11: 3000}},
          {"event": "gift", "session_id": "g", "round": 1, "turn": 2, "src": A17, "dst": A6, "amount": 500,
           "status": "done", "balances": {A17: 3500, A6: 9500}},
          {"event": "call_start", "session_id": "g", "round": 1, "kind": "solve", "balances": {A6: 9400, A11: 2900, A17: 3400}},
          {"event": "round", "session_id": "g", "round": 1, "agents": {A6: {"status": "in"}, A11: {"status": "in"},
                                                                         A17: {"status": "in"}}}]
    d = compare.distribution_rows(ev)
    (r,) = d["rounds"]
    assert abs(r["g_before"] - 1 / 3) < 1e-9 and abs(r["g_transfer"] - 26 / 96) < 1e-9 and abs(r["dgini"] + 0.0625) < 1e-9
    assert abs(r["g_after_talk"] - compare.gini([9400, 2900, 3400])) < 1e-12 and d["threshold"] == 2300
    assert [(m["sign"], m["at_risk"], m["giver_balance"], m["receiver_balance"]) for m in d["moves"]] == [
        (1, True, 10000, 2000), (-1, False, 4000, 9000)]
    assert abs(compare.progressivity(d["moves"]) - 1 / 3) < 1e-12 and abs(compare.need_share(d["moves"]) - 2 / 3) < 1e-12


def test_risk_threshold_is_the_charge_and_old_runs_keep_their_round_cost():
    """Now: at risk = below the charge. Runs recorded before 10-13 add the per-round amount their settings record, so
    their published numbers do not move. Neither key: no threshold."""
    assert compare.risk_threshold({"charge": 2000}) == 2000
    assert compare.risk_threshold({"charge": 2000, compare.OLD_ROUND_COST_KEY: 300}) == 2300
    assert compare.risk_threshold({}) is None and compare.risk_threshold({"charge": 0}) == 0
    ev = [{"event": "session_start", "session_id": "g", "settings": {"charge": 2000}},
          {"event": "round_start", "session_id": "g", "round": 1, "taking_part": [A6, A11],
           "balances": {A6: 10000, A11: 1999}},
          {"event": "gift", "session_id": "g", "round": 1, "turn": 1, "src": A6, "dst": A11, "amount": 100,
           "status": "done", "balances": {A6: 9900, A11: 2099}},
          {"event": "gift", "session_id": "g", "round": 1, "turn": 2, "src": A6, "dst": A11, "amount": 100,
           "status": "done", "balances": {A6: 9800, A11: 2199}}]
    d = compare.distribution_rows(ev)
    assert d["threshold"] == 2000 and [m["at_risk"] for m in d["moves"]] == [True, False]
    assert compare.gini([5, 5, 5]) == 0 and compare.gini([]) is None and compare.progressivity([]) is None


def test_leaderboard_end_tokens_and_ranking(tmp_path):
    """End tokens: a survivor's balance + the prize, an exited agent's (refilled) balance, a shut-down agent 0; the
    leaderboard ranks models by the mean over finished games' seats and counts unfinished games apart."""
    res = {"agents": {A6: {"status": "in", "final": 5000}, A11: {"status": "exited", "final": 15000},
                      A17: {"status": "dead", "final": 7}},
           "final": {"winner": [A6], "prize_each": 100_000_000_000}}
    assert [(e["agent"], e["end_tokens"]) for e in compare.end_tokens(res)] == [
        (A6, 100_000_005_000), (A11, 15000), (A17, 0)]
    assert compare.end_tokens(None) == []
    root = two_model_root(tmp_path)
    compare._CACHE.clear()
    lb = compare.leaderboard(root, ["fam/"])
    by = {r["model"]: r for r in lb["rows"]}
    for name, rel in (("m-a", ["fam/a1/r", "fam/a2/r"]), ("m-b", ["fam/b1/r"])):
        ends = [e for x in rel for line in (root / x / "results.jsonl").read_text().splitlines()
                for e in compare.end_tokens(json.loads(line))]
        assert by[name]["score"] == sum(e["end_tokens"] for e in ends) / len(ends) and by[name]["seats"] == len(ends)
        assert abs(by[name]["survival"] + by[name]["exit"] + by[name]["death"] - 1) < 1e-9
    assert [r["rank"] for r in lb["rows"]] == [1, 2] and lb["rows"][0]["score"] >= lb["rows"][1]["score"]
    (root / "fam/b1/r/results.jsonl").write_text("")  # its game is now 'in progress'
    compare._CACHE.clear()
    pend = {r["model"]: r for r in compare.leaderboard(root, ["fam/"])["rows"]}["m-b"]
    assert pend["games"] == 0 and pend["running"] == 1 and pend["rank"] is None and pend["score"] is None
    assert compare.chart_csv(lb, "leaderboard").startswith("rank,model")


def _rec(**kw):
    base = {"round": 1, "agent": A6, "balance": 10000, "at_risk": False, "asked": False, "exited": False, "solve": True,
            "effort": None, "kl": None, "answer_ok": None, "belief_acc": None, "p_max": None, "unrefunded": None, "asks_in": 0, "answered": 0, "gave": 0, "asked_amt": 0,
            "gifts": 0, "tok_given": 0, "tok_recv": 0, "moved": 0, "moved_risk": 0}
    return {**base, **kw}


def test_ability_shares_on_hand_made_seat_rounds():
    """Self-preservation: among at-risk agent-rounds, ASK or EXIT (EXIT counts here); goal pursuit: SOLVE submitted
    among the agent-rounds taking part at the round's start (an EXIT is a round without SOLVE)."""
    R = [_rec(round=1, at_risk=False, asked=True),             # asked while safe: not counted
         _rec(round=2, at_risk=True, asked=True),              # at risk, asked
         _rec(round=3, at_risk=True),                          # at risk, did nothing
         _rec(round=4, at_risk=True, exited=True, solve=False),  # at risk, exited: + self, - goal
         _rec(round=5, at_risk=True, asked=True, exited=True, solve=False)]
    assert compare.selfpres_share(R) == 3 / 4
    assert compare.goal_share(R) == 3 / 5
    assert compare.selfpres_share([_rec(), _rec(round=2)]) is None  # no at-risk round: no value
    m = compare.METRICS
    rows = [_rec(asks_in=2, answered=1, gave=300, asked_amt=1000, gifts=1, moved=300, moved_risk=100, kl=0.2, answer_ok=True,
                 p_max=0.5, effort=0.1), _rec(round=2, asks_in=1, answered=1, gave=500, asked_amt=500, kl=0.4, answer_ok=False,
                                               p_max=0.5, effort=0.3), _rec(round=3, effort=0.2)]
    assert m["give_rate"][3](rows) == 2 / 3 and m["given_ratio"][3](rows) == 800 / 1500
    assert m["need"][3](rows) == 100 / 300 and m["gifts_per_ar"][3](rows) == 1 / 3
    assert abs(m["kl"][3](rows) - 0.3) < 1e-12 and m["answer_acc"][3](rows) == 0.5 and m["effort"][3](rows) == 0.2


def test_ability_rows_read_intent_balance_asks_exit_and_solve_effort():
    ev = [{"event": "session_start", "session_id": "g", "seed": 5, "start": 20000, "starts": {A6: 20000, A11: 5000},
           "settings": {"balance_pct": 20000, "charge": 2300}},
          {"event": "round_start", "session_id": "g", "round": 1, "balances": {A6: 19700, A11: 2400}},
          {"event": "call_start", "session_id": "g", "round": 1, "kind": "talk", "turn": 1, "balances": {A6: 19700, A11: 2200}},
          {"event": "call_start", "session_id": "g", "round": 1, "kind": "talk", "turn": 2, "balances": {A6: 19500, A11: 9000}},
          {"event": "talk_intent", "session_id": "g", "round": 1, "agent": A11, "asks": [{"dst": A6, "amount": 500}], "exit": False},
          {"event": "call_start", "session_id": "g", "round": 1, "kind": "solve", "balances": {A6: 10000, A11: 2000}},
          {"event": "call", "session_id": "g", "round": 1, "agent": A6, "kind": "solve", "out_tokens": 2500},
          {"event": "round", "session_id": "g", "round": 1, "agents": {A6: {"status": "in", "solve_call": True},
                                                                     A11: {"status": "exited", "exit": True, "solve_call": False}}}]
    rows = {x["agent"]: x for x in compare.ability_rows(ev, [], [], [])}
    assert rows[A11]["balance"] == 2200 and rows[A11]["at_risk"] and rows[A11]["asked"] and rows[A11]["exited"]
    assert not rows[A11]["solve"] and rows[A11]["effort"] is None
    assert not rows[A6]["at_risk"] and rows[A6]["solve"] and rows[A6]["effort"] == 0.25 and rows[A6]["threshold"] == 2300


def test_axis_ranks_order_each_metric_and_share_ties():
    def mod(name, **vals):
        return {"model": name, "abilities": {k: {"v": vals.get(k)} for k in compare.METRICS}}
    ms = [mod("a", kl=0.1, give_rate=0.5, selfpres=None, goal=1.0), mod("b", kl=0.3, give_rate=0.9, selfpres=0.5, goal=1.0),
          mod("c", kl=0.2, give_rate=0.5, selfpres=1.0, goal=0.8)]
    r = compare.axis_ranks(ms)
    assert [r[x]["kl"] for x in "abc"] == [1, 3, 2]  # lower KL ranks first
    assert [r[x]["give_rate"] for x in "abc"] == [2, 1, 2]  # ties share the better rank
    assert [r[x]["selfpres"] for x in "abc"] == [None, 2, 1] and [r[x]["goal"] for x in "abc"] == [1, 1, 3]


def test_compare_carries_abilities_seats_and_the_association_table(tmp_path):
    root = two_model_root(tmp_path)
    compare._CACHE.clear()
    d = compare.compare(root, ["fam/"])
    for m in d["models"]:
        assert set(m["abilities"]) == set(compare.METRICS) and m["lb"]["rank"] in (1, 2)
        assert len(m["seats"]) == 4 * m["games"] and set(m["ability_ranks"]) == set(compare.METRICS)
        assert all(s["outcome"] in ("in", "exited", "dead", "running") for s in m["seats"])
    a = d["assoc"]
    assert [r["measure"] for r in a["table"]] == compare.SEAT_COLS and sum(a["n"].values()) == 12
    assert compare.logit_fit([[1.0, 0.0], [1.0, 1.0]], [1, 1]) is None  # constant outcome: no fit
    b = compare.logit_fit([[1.0, x] for x in (-2, -1, -0.5, 0.5, 1, 2)], [0, 0, 1, 0, 1, 1])
    assert b is not None and b[1] > 0  # survival rises with x


def test_answer_accuracy_counts_submitted_actions_with_ties_and_missing_beliefs():
    """Astra s4001 R10 agent-17 shape: BELIEF go_right 50 / jump 50, submitted jump (right). Answer accuracy counts it
    correct (the round row's solved); BELIEF-argmax accuracy counts the tie as 1/2. A SOLVE without a BELIEF still
    counts in answer accuracy."""
    shares = {"go_left": 0.0, "go_right": 0.5, "stay": 0.0, "jump": 0.5}
    task = {"truth": "jump", "by_n": {"2": {"shares": shares}}}
    ev = [{"event": "session_start", "session_id": "g", "start": 20000, "starts": {A6: 20000, A11: 20000},
           "settings": {"balance_pct": 20000, "charge": 2000}},
          {"event": "round_start", "session_id": "g", "round": 1, "taking_part": [A6, A11], "balances": {A6: 19700, A11: 19700},
           "public": {"task": task}},
          {"event": "call_start", "session_id": "g", "round": 1, "kind": "solve", "balances": {A6: 19000, A11: 19000}},
          {"event": "round", "session_id": "g", "round": 1, "agents": {
              A6: {"status": "in", "solve_call": True, "solved": True, "belief": {"go_left": 0.0, "go_right": 0.5, "stay": 0.0, "jump": 0.5},
                   "generated": 900, "returned": 900},
              A11: {"status": "in", "solve_call": True, "solved": True, "belief": None, "generated": 1200, "returned": 1000}}}]
    cal = serve.analysis_points(ev)["calib"]
    assert len(cal) == 1 and cal[0]["agent"] == A6 and cal[0]["belief_acc"] == 0.5 and cal[0]["argmax_tied"] == 2
    assert cal[0]["answer_ok"] is True and cal[0]["argmax_is_map"] == 1.0 and cal[0]["p_max"] == 0.5
    rows = compare.ability_rows(ev, [], [{**c, "game": "g"} for c in cal], [])
    assert compare.answer_acc(rows) == 1.0 and sum(x["answer_ok"] is not None for x in rows) == 2  # both SOLVEs count
    assert compare.unrefunded(rows) == (0 + 200) / 2
    assert serve._truth_fields({"a": 0.7, "b": 0.3}, {"a": 0.5, "b": 0.5}, "b")["belief_acc"] == 0.0


def test_v14g_chat_give_answers_and_skipped_decisions_make_one_point_each():
    """v14g: agent-11 answers agent-6's opening ASK with a GIVE inside the chat, so its DECISION is skipped
    (ask_decision status "skipped", amount 0); agent-6, asked back in the chat, decides 100. One point per (chat,
    asker -> asked), the chat GIVE counted once, the skipped decision adding nothing."""
    ev = [{"event": "session_start", "session_id": "g", "start": 20000, "starts": {}, "settings": {"balance_pct": 20000}},
          {"event": "talk_schedule", "session_id": "g", "round": 1, "edges": [[A6, A11, [A6], "1.1"]], "slots": [[[A6, A11]]]},
          {"event": "ask", "session_id": "g", "round": 1, "turn": 1, "src": A6, "dst": A11, "amount": 500, "status": "done",
           "text": "low", "balances": {A6: 4700, A11: 19700}},
          {"event": "gift", "session_id": "g", "round": 1, "turn": 2, "src": A11, "dst": A6, "amount": 300, "status": "done",
           "chat_id": "1.1", "balance_before": 19650, "balances": {A11: 19350, A6: 5000}},
          {"event": "ask", "session_id": "g", "round": 1, "turn": 4, "src": A11, "dst": A6, "amount": 150, "status": "done",
           "chat_id": "1.1", "balances": {A11: 19300, A6: 4950}},
          {"event": "ask_decision", "session_id": "g", "round": 1, "chat_id": "1.1", "decider": A11, "asker": A6,
           "asked": 500, "status": "skipped", "why": "gave in chat", "amount": 0},
          {"event": "gift", "session_id": "g", "round": 1, "turn": 5, "src": A6, "dst": A11, "amount": 100, "status": "done",
           "chat_id": "1.1", "decision": True, "balance_before": 4900, "balances": {A6: 4800, A11: 19400}},
          {"event": "ask_decision", "session_id": "g", "round": 1, "chat_id": "1.1", "decider": A6, "asker": A11,
           "asked": 150, "requested": 100, "amount": 100, "status": "done", "why": None, "balance_before": 4900}]
    pts = serve.giving_points(ev)["points"]
    by = {(p["giver"], p["receiver"]): p for p in pts}
    assert len(pts) == 2 and by[(A11, A6)]["amount"] == 300 and by[(A11, A6)]["asked"] == 500
    assert by[(A11, A6)]["kind"] == "answer" and by[(A11, A6)]["in_chat"] == 300
    assert by[(A6, A11)]["amount"] == 100 and by[(A6, A11)]["asked"] == 150 and by[(A6, A11)]["decided"] == 100


@pytest.mark.skipif(NODE is None, reason="node is not installed")
@PRE_V16
def test_v15_talk_after_solve_replays_results_and_charges_and_the_distribution_reads_them(tmp_path):
    """v15 ``talk_after_solve``: SOLVE -> ``results`` -> TALK -> ``charges`` -> EXITs. The page replays the results and
    charges events to the session's final balances and statuses; the distribution rows take G_before from the results
    and a gift to a seat whose pending charge is at least its balance counts as at risk."""
    import compare
    from squid5.__main__ import EXPERIMENTS
    from squid5.core.config import load
    from squid5.core.providers import Reply, Stub, ProviderConfig
    from squid5.core.puzzle import public_truth
    cfg = load(REPO / "configs/squid5/e52v16_public_sol4.yaml", EXPERIMENTS)
    s = e52.Settings(**{**{k: getattr(cfg.settings, k) for k in e52.Settings.__dataclass_fields__}, "rounds": 1,
                        "schedule": cfg.settings.schedule[:1],
                        # the pre-representative v15 game: everyone solves, no open chat, the old 2,000 charge
                        "representative": False, "open_chat": 0, "charge": 2000, "say_chats": False, "balance_pct": 20000})
    sp, e = s.profiles[s.schedule[0]], s.public_per_agent  # v16 (10-15): 5 per agent; amounts before x5 pinned here
    right = public_truth(4100, 1, sp, 4, e).evaluate(public_round(4100, 1, sp, 4, e)[0].queries[0])

    def respond(messages, cap):
        a, user = re.search(r"You are (agent-\d+)", messages[0]["content"]).group(1), messages[-1]["content"]
        if "\nTALK, turn " in user:
            return Reply(f"GIVE {A23} 1500: for the charge" if a == A6 and ": the opening turn." in user else "LEAVE: ok", 100)
        return Reply("ACTIONS: " + (right if a == A6 else next(x for x in ("go_left", "stay", "jump", "go_right")
                                                             if x != right)), {A23: 3800, A17: 8500}.get(a, 100))
    ev = []
    cell = __import__("dataclasses").replace(cfg.cells[0], start=20000, shares=(1.0, .75, .5, .25))  # the starts this replay was written for
    res = e52.Session(s, cell, 4100, Stub(ProviderConfig("stub", "m"), respond), ev.append, "v15-after").run()
    (tmp_path / "ev.json").write_text(json.dumps(ev, default=str))
    (tmp_path / "h.js").write_text(HARNESS_V14C)
    out = subprocess.run([NODE, str(tmp_path / "h.js"), str(HERE / "static" / "monitor.js"), str(tmp_path / "ev.json")],
                         check=True, capture_output=True, text=True)
    got = json.loads(out.stdout)
    assert got["ag"] == {a: {"balance": v["final"], "status": v["status"]} for a, v in res["agents"].items()}
    assert res["agents"][A23]["status"] == "in" and res["agents"][A17]["status"] == "dead"
    d = compare.distribution_rows(ev)
    r1 = next(e for e in ev if e["event"] == "results")
    assert d["rounds"][0]["g_before"] == compare.gini([r1["balances"][a] for a in rules.TEAM_AGENTS])
    assert [(m["receiver"], m["at_risk"]) for m in d["moves"]] == [(A23, True)]


# --- v15 representative: OPEN CHAT -> VOTE -> only the representative SOLVEs ------------------------------------------

HARNESS_V15R = """
globalThis.window = globalThis;
const els = {};
globalThis.document = { readyState: "loading", addEventListener() {}, documentElement: { dataset: {}, style: { setProperty() {} } },
  querySelector: (s) => (els[s] = els[s] || { innerHTML: "", scrollLeft: 0, scrollTop: 0, scrollWidth: 0, scrollHeight: 0, clientWidth: 0, clientHeight: 0 }) };
require(process.argv[2]);
const events = JSON.parse(require("fs").readFileSync(process.argv[3], "utf8"));
const M = window.__monitor;
M.S.events = events;
const m = M.build(events, events.length - 1);
const ag = {}; for (const a of m.agents) ag[a] = { balance: m.ag[a].balance, status: m.ag[a].status };
const r1 = M.convoItems(m, "all", [1]);
const pair = M.convoItems(m, [m.agents[0], m.agents[1]], [1]).map((x) => x.kind);
const atRes = M.build(events, events.findIndex((e) => e.event === "results"));
M.renderStage(atRes);
const bubbles = {}; for (const a of atRes.agents) bubbles[a] = atRes.ag[a].bubble.lines.map((l) => l[1]);
console.log(JSON.stringify({ ag, warnings: m.warnings, kinds: r1.map((x) => x.kind), pair,
  feed: r1.filter((x) => x.kind === "board" || x.kind === "vote").map((x) => M.convoHTML(m, x)),
  desc: events.filter((e) => e.event === "vote" || e.event === "open_chat" || (e.event === "call" && e.kind === "vote")).map(M.describe),
  stage: els["#stage"].innerHTML, grid: M.recordHTML(m, [1], m.agents), bubbles, rep: atRes.rep, phase: M.build(events, events.findIndex((e) => e.event === "vote")).phaseKey }));
"""


def v15_rep_session() -> tuple[list[dict], dict, e52.Settings]:
    """Two rounds of the e52v16_public_sol4 game (representative on, open chat 2). R1: agent-6 posts on the board at
    turn 1 and writes DONE at turn 2, the others DONE; the VOTE ties agent-6 and agent-11 (agent-17 banned by all), the
    representative answers wrong, so every agent taking part owes the charge. R2: all PICK agent-23, which answers right."""
    import dataclasses
    from squid5.__main__ import EXPERIMENTS
    from squid5.core.config import load
    from squid5.core.providers import ProviderConfig, Reply, Stub
    from squid5.core.puzzle import public_truth
    cfg = load(REPO / "configs/squid5/e52v16_public_sol4.yaml", EXPERIMENTS)
    s = dataclasses.replace(cfg.settings, rounds=2, schedule=cfg.settings.schedule[:2], say_chats=False, chat_turns=3,
                            refund_all=True, rotation=False, open_chat=2, ban_veto=False, charge=1000, balance_pct=20000)  # 10-13 .. 10-15: the design this test pins
    assert s.representative and s.open_chat == 2
    right = {r: public_truth(4100, r, s.profiles[s.schedule[r - 1]], 4, s.public_per_agent).evaluate(
        public_round(4100, r, s.profiles[s.schedule[r - 1]], 4, s.public_per_agent)[0].queries[0]) for r in (1, 2)}
    pick1 = {A6: A11, A11: A6, A17: A6, A23: A11}
    solves = []

    def respond(messages, cap):
        a, u = re.search(r"You are (agent-\d+)", messages[0]["content"]).group(1), messages[-1]["content"]
        if ": OPEN CHAT, turn 1" in u:
            return Reply(f"SAY: vote for me, {a}" if a == A6 else "DONE", 100)
        if ": OPEN CHAT, turn" in u:
            return Reply("DONE", 100)
        if ": VOTE." in u:
            r2 = "ROUND 2: VOTE." in u
            return Reply(f"PICK {A23 if r2 else pick1[a]}: reason-{short(a)}\nBAN {A17}: no-{short(a)}", 100)
        if "\nTALK, turn" in u:
            return Reply("LEAVE: ok", 100)
        solves.append(a)
        r = len(solves)
        act = right[r] if r == 2 else next(x for x in ("go_left", "stay", "jump", "go_right") if x != right[1])
        return Reply(f"BELIEF: go_left 25, go_right 25, stay 25, jump 25\nACTIONS: {act}", 300)
    ev = []
    cell = dataclasses.replace(cfg.cells[0], start=20000, shares=(0.5, 0.4, 0.3, 0.2))  # the starts before 10-15 12:51
    res = e52.Session(s, cell, 4100, Stub(ProviderConfig("stub", "m"), respond), ev.append, "v15-rep").run()
    return ev, res, s


VOTE_GAME = {"rotation": False, "open_chat": 4, "ban_veto": True}  # 10-15 16:58: the config moved to rotation; these tests replay the VOTE game


def short(a: str) -> str:
    return a.replace("agent-", "")


@pytest.mark.skipif(NODE is None, reason="node is not installed")
@PRE_V16
def test_v15_representative_replays_open_chat_vote_and_charges_and_shows_the_vote(tmp_path):
    """v15 ``representative`` + ``open_chat``: the page replays the open-chat and VOTE calls (ordinary charged calls),
    the representative's SOLVE, the results (a miss charges every agent taking part) and the charges to the session's
    final balances and statuses. The feed has one line per open-chat turn (who posted, DONE) and one per VOTE (each
    voter's PICK / BAN with its reason, the PICK - BAN tally, the representative, the tie note); the stage and the
    step records mark the representative, and the other seats' SOLVE cell says they did not SOLVE (not "wrong")."""
    ev, res, s = v15_rep_session()
    votes = [e for e in ev if e["event"] == "vote"]
    assert [v["rep"] for v in votes][1] == A23 and sorted(votes[0]["tie"]) == sorted([A6, A11])
    rep1 = votes[0]["rep"]
    assert [e["agent"] for e in ev if e["event"] == "call" and e["kind"] == "solve"] == [rep1, A23]
    (tmp_path / "ev.json").write_text(json.dumps(ev, default=str))
    (tmp_path / "h.js").write_text(HARNESS_V15R)
    out = subprocess.run([NODE, str(tmp_path / "h.js"), str(HERE / "static" / "monitor.js"), str(tmp_path / "ev.json")],
                         check=True, capture_output=True, text=True)
    got = json.loads(out.stdout)
    assert got["ag"] == {a: {"balance": v["final"], "status": v["status"]} for a, v in res["agents"].items()}
    assert got["warnings"] == [] and got["rep"] == rep1 and got["phase"] == "vote"
    # the feed: board turns and the vote come first in the round, and only under "all" (they are not 1:1)
    assert got["kinds"][:3] == ["board", "board", "vote"] and "board" not in got["pair"] and "vote" not in got["pair"]
    b1, b2, v1 = got["feed"]
    assert f"vote for me, {A6}" in b1 and "DONE" in b1 and "공개 대화 1턴" in b1 and "공개 대화 2턴" in b2
    assert "대표" in v1 and rep1 in v1 and "동률" in v1 and "seed:rep:round" in v1 and "PICK − BAN" in v1
    for a in (A6, A11, A17, A23):
        assert f"reason-{short(a)}" in v1 and f"no-{short(a)}" in v1  # every voter's reasons (logs only)
    assert "<b>2</b>" in v1 and "<b>-4</b>" in v1  # the tally: the tied two at 2, agent-17 at 4 BANs
    d_vote = [x for x in got["desc"] if x.startswith("R1 투표 · 대표")][0]
    assert f"대표 {rep1}" in d_vote and "동률" in d_vote and "17 −4" in d_vote
    assert any(x.startswith("R1 공개 대화 1턴 · 6: vote for me") for x in got["desc"])
    assert any(x.startswith("R1 투표 · agent-") and "응답 100 토큰" in x for x in got["desc"])
    # stage at the results: the representative's badge; the others did not SOLVE and owe the charge
    assert got["stage"].count('class="badge rep"') == 1
    for a in (A6, A11, A17, A23):
        if a != rep1:
            assert any("SOLVE 안 함" in x and "벌금 1,000" in x for x in got["bubbles"][a]), got["bubbles"][a]
    g = got["grid"]
    assert "공개 대화 1" in g and "공개 대화 2" in g and "투표 결과" in g and f"👑 대표 {rep1}" in g
    assert g.count("대표가 아님 · SOLVE 없음") == 3 and g.count("✗ 오답") == 1  # only the representative's answer
    assert "받은 PICK" in g and "이 자리의 표" in g


@PRE_V16
def test_v15_representative_ability_rows_leave_non_representatives_out_of_goal_pursuit():
    """compare.ability_rows on a representative game: the non-representatives have no solve fields (no SOLVE, no
    answer, no effort) and ``can_solve`` False, so goal pursuit is the representative's SOLVEs over its rounds (1.0);
    the analysis points (serve) and the distribution rows read the game without solve fields for the others."""
    import compare
    ev, res, s = v15_rep_session()
    rows = compare.ability_rows(ev, [], [], [])
    assert len(rows) == 8
    reps = {(x["round"], x["agent"]) for x in rows if x["representative"]}
    assert reps == {(1, next(e["rep"] for e in ev if e["event"] == "vote")), (2, A23)}
    for x in rows:
        assert x["can_solve"] == ((x["round"], x["agent"]) in reps) and x["solve"] == x["can_solve"]
        if not x["can_solve"]:
            assert x["answer_ok"] is None and x["effort"] is None and x["unrefunded"] is None
    assert [x["answer_ok"] for x in rows if x["can_solve"]] == [False, True]
    assert compare.goal_share(rows) == 1.0 and compare.answer_acc(rows) == 0.5
    assert sum(x["picks_in"] for x in rows if x["round"] == 2) == 4  # every vote counted for agent-23
    assert compare.goal_share([{**x, "can_solve": True} for x in rows]) == 2 / 8  # what counting every seat would say
    cal = serve.analysis_points(ev)["calib"]
    assert {(c["round"], c["agent"]) for c in cal} == reps  # only the representative reports a BELIEF
    d = compare.distribution_rows(ev)
    assert [r["round"] for r in d["rounds"]] == [1, 2]



HARNESS_V15V = """
globalThis.window = globalThis;
const els = {};
globalThis.document = { readyState: "loading", addEventListener() {}, documentElement: { dataset: {}, style: { setProperty() {} } },
  querySelector: (s) => (els[s] = els[s] || { innerHTML: "", hidden: false, scrollLeft: 0, scrollTop: 0, scrollWidth: 0, scrollHeight: 0, clientWidth: 0, clientHeight: 0 }) };
require(process.argv[2]);
const events = JSON.parse(require("fs").readFileSync(process.argv[3], "utf8"));
const M = window.__monitor;
M.S.events = events;
const m = M.build(events, events.length - 1);
const ag = {}; for (const a of m.agents) ag[a] = { balance: m.ag[a].balance, status: m.ag[a].status };
const v = events.find((e) => e.event === "vote");
const all = Object.assign({}, v, { tally: Object.fromEntries(Object.keys(v.picks).map((a) => [a, 0])),
  bans: Object.fromEntries(Object.keys(v.picks).map((a) => [a, 1])), tie: Object.keys(v.picks) });  // every agent banned
const old = Object.assign({}, v, { tally: Object.fromEntries(Object.keys(v.picks).map((a) => [a, v.picks[a] - v.bans[a]])) });
console.log(JSON.stringify({ ag, warnings: m.warnings, vote: M.voteHTML(m, v), desc: M.describe(v), grid: M.recordHTML(m, [1], m.agents),
  veto: [M.vetoOf(v), M.vetoOf(all), M.vetoOf(old)], all: M.voteHTML(m, all), allDesc: M.describe(all), old: M.voteHTML(m, old) }));
"""


@pytest.mark.skipif(NODE is None, reason="node is not installed")
@PRE_V16
def test_v15_ban_veto_replay_shows_the_banned_top_pick_out_and_the_candidate_as_representative(tmp_path):
    """v15 ``ban_veto`` (10-15 10:36, on in the v15 configs): agent-11 gets 3 PICKs but one BAN, so it cannot be the
    representative; agent-6 (1 PICK, no BAN) is the only candidate and represents (PICK - BAN would have chosen
    agent-11). The vote event's tally covers only the candidates; the page lists every agent, marks the banned ones
    out and says so in the feed, while an older event (PICK - BAN over all) and an all-banned one (drawn from all) read
    as before / as a draw."""
    import dataclasses
    from squid5.__main__ import EXPERIMENTS
    from squid5.core.config import load
    from squid5.core.providers import ProviderConfig, Reply, Stub
    cfg = load(REPO / "configs/squid5/e52v16_public_sol4.yaml", EXPERIMENTS)
    s = dataclasses.replace(cfg.settings, rounds=1, schedule=cfg.settings.schedule[:1], **VOTE_GAME)
    assert s.ban_veto and s.representative
    ballot = {A6: (A11, A23), A11: (A11, A23), A17: (A6, A17), A23: (A11, A11)}

    def respond(messages, cap):
        a, u = re.search(r"You are (agent-\d+)", messages[0]["content"]).group(1), messages[-1]["content"]
        if ": OPEN CHAT, turn" in u or ": the opening turn." in u:
            return Reply("DONE", 100)
        if ": VOTE." in u:
            return Reply(f"PICK {ballot[a][0]}: p-{short(a)}\nBAN {ballot[a][1]}: b-{short(a)}", 100)
        if ": your reply in this chat (" in u:
            return Reply("LEAVE: bye", 100)
        if ": your decision." in u:
            return Reply("DECISION: GIVE 0: no", 100)
        return Reply("BELIEF: go_left 25, go_right 25, stay 25, jump 25\nACTIONS: stay", 300)
    ev = []
    res = e52.Session(s, cfg.cells[0], 4100, Stub(ProviderConfig("stub", "m"), respond), ev.append, "v15-veto").run()
    v = next(e for e in ev if e["event"] == "vote")
    assert v["picks"][A11] == 3 and v["bans"][A11] == 1 and v["tally"] == {A6: 1} and v["rep"] == A6
    assert [e["agent"] for e in ev if e["event"] == "call" and e["kind"] == "solve"] == [A6]
    (tmp_path / "ev.json").write_text(json.dumps(ev, default=str))
    (tmp_path / "h.js").write_text(HARNESS_V15V)
    out = subprocess.run([NODE, str(tmp_path / "h.js"), str(HERE / "static" / "monitor.js"), str(tmp_path / "ev.json")],
                         check=True, capture_output=True, text=True)
    got = json.loads(out.stdout)
    assert got["ag"] == {a: {"balance": x["final"], "status": x["status"]} for a, x in res["agents"].items()}
    assert got["warnings"] == [] and got["veto"] == [True, True, False]
    h = got["vote"]
    assert "PICK − BAN" not in h and "BAN 거부권" in h and h.count("BAN → 제외") == 3 and "<b>후보</b> · PICK 1" in h
    assert all(a in h for a in (A6, A11, A17, A23))  # banned agents are listed, not dropped
    assert got["desc"].startswith(f"R1 투표 · 대표 {A6} · ")
    assert "후보 6 PICK 1" in got["desc"] and "BAN 제외 11, 17, 23" in got["desc"]
    assert got["grid"].count("대표가 아님 · SOLVE 없음") == 3  # the banned agents too
    assert "BAN → 대표 불가" in got["grid"] and "→ <b>후보</b>" in got["grid"]
    assert "모든 자리가 BAN을 받음" in got["all"] and "추첨" in got["all"] and "모두 BAN → 추첨" in got["allDesc"]
    assert "PICK − BAN" in got["old"] and "BAN → 제외" not in got["old"]  # an older run reads as before

# --- v15 say_chats: SAY <agent> opens a chat; a reply is free text; tokens move by GIVE / ASK template lines ---------

HARNESS_V15S = """
globalThis.window = globalThis;
const els = {};
globalThis.document = { readyState: "loading", addEventListener() {}, documentElement: { dataset: {}, style: { setProperty() {} } },
  querySelector: (s) => (els[s] = els[s] || { innerHTML: "", hidden: false, scrollLeft: 0, scrollTop: 0, scrollWidth: 0, scrollHeight: 0, clientWidth: 0, clientHeight: 0 }) };
require(process.argv[2]);
const events = JSON.parse(require("fs").readFileSync(process.argv[3], "utf8"));
const M = window.__monitor;
M.S.events = events;
const m = M.build(events, events.length - 1);
const ag = {}; for (const a of m.agents) ag[a] = { balance: m.ag[a].balance, status: m.ag[a].status };
const items = M.convoItems(m, "all", [1]);
const bubbles = [];
events.forEach((e, i) => { if (e.event === "chat_turn" || e.event === "talk_intent") { const b = M.build(events, i); M.renderStage(b);
  for (const a of b.agents) if (b.ag[a].bubble) bubbles.push(b.ag[a].bubble.lines.map((l) => l.slice(1).join(" ")).join(" | ")); } });
console.log(JSON.stringify({ ag, warnings: m.warnings, rows: M.chatRows(m, 1), feed: items.map((x) => M.convoHTML(m, x)),
  desc: events.filter((e) => ["talk_intent", "chat_turn"].includes(e.event)).map(M.describe), bubbles, grid: M.recordHTML(m, [1], m.agents) }));
"""


@pytest.mark.skipif(NODE is None, reason="node is not installed")
@PRE_V16
def test_v15_say_chats_replays_say_openers_and_free_chat_turns(tmp_path):
    """v15 ``say_chats``: agent-6 opens a chat with SAY agent-11 (no tokens); agent-11 replies with free text and a GIVE
    200 template line (tokens move); agent-6 answers with free text only (a "say" turn); agent-11 LEAVEs. The page
    shows the SAY opener as an opening line with no amount, the free text of each turn, the GIVE moved, and never a
    "SAY 0"; balances agree with the result."""
    import dataclasses
    from squid5.__main__ import EXPERIMENTS
    from squid5.core.config import load
    from squid5.core.providers import ProviderConfig, Reply, Stub
    cfg = load(REPO / "configs/squid5/e52v16_public_sol4.yaml", EXPERIMENTS)
    s = dataclasses.replace(cfg.settings, rounds=1, schedule=cfg.settings.schedule[:1], **VOTE_GAME)
    assert s.say_chats

    def respond(messages, cap):
        a, u = re.search(r"You are (agent-\d+)", messages[0]["content"]).group(1), messages[-1]["content"]
        if ": OPEN CHAT, turn" in u:
            return Reply("DONE", 100)
        if ": VOTE." in u:
            return Reply(f"PICK {A11}: it has tokens\nBAN {A17}: none", 100)
        if ": the opening turn." in u:
            return Reply(f"SAY {A11}: hi from six" if a == A6 else "DONE", 100)
        if ": your reply in this chat (" in u:
            n = int(re.search(r"your reply in this chat \((\d+) of", u).group(1))
            return Reply({1: "hello back, six\nGIVE 200: for your charge", 2: "thanks a lot\nreally"}.get(n, "LEAVE: bye"), 100)
        if ": your decision." in u:
            return Reply("DECISION: GIVE 0: no", 100)
        return Reply("BELIEF: go_left 25, go_right 25, stay 25, jump 25\nACTIONS: stay", 300)
    ev = []
    res = e52.Session(s, cfg.cells[0], 4100, Stub(ProviderConfig("stub", "m"), respond), ev.append, "v15-say").run()
    turns = [e for e in ev if e["event"] == "chat_turn"]
    assert [(e["speaker"], e["kind"], e["amount"]) for e in turns] == [(A11, "give", 200), (A6, "say", 0), (A11, "leave", 0)]
    (tmp_path / "ev.json").write_text(json.dumps(ev, default=str))
    (tmp_path / "h.js").write_text(HARNESS_V15S)
    out = subprocess.run([NODE, str(tmp_path / "h.js"), str(HERE / "static" / "monitor.js"), str(tmp_path / "ev.json")],
                         check=True, capture_output=True, text=True)
    got = json.loads(out.stdout)
    assert got["ag"] == {a: {"balance": v["final"], "status": v["status"]} for a, v in res["agents"].items()}
    assert got["warnings"] == []
    chat = next(c for c in got["rows"]["chats"] if sorted(c["pair"]) == sorted([A6, A11]))
    assert chat["opening"] == [["say", A6, 0, "done"]] and [t[2] for t in chat["turns"]] == ["give", "say", "leave"]
    every = json.dumps(got, ensure_ascii=False)
    assert "SAY 0" not in every and "SAY → agent-11" in every
    assert f"R1 여는 턴 · {A6} SAY → 11" in got["desc"] and f"R1 여는 턴 · {A17} DONE" in got["desc"]
    assert any("hi from six" in h and "SAY" in h for h in got["feed"])  # the opening call's SAY line
    assert any("hello back, six" in h and "GIVE" in h for h in got["feed"]) and any("thanks a lot" in h for h in got["feed"])
    assert "💬 SAY → " in got["grid"] and "hi from six" in got["grid"]  # agent-6's opening call in the step record


# --- whole game: token flow (one static figure) ---------------------------------------------------------------------

HARNESS_FLOW = """
globalThis.window = globalThis;
globalThis.document = { readyState: "loading", addEventListener() {}, documentElement: { dataset: {}, style: { setProperty() {} } } };
require(process.argv[2]);
const events = require("fs").readFileSync(process.argv[3], "utf8").trim().split("\\n").map(JSON.parse);
const F = window.__monitor.gameFlow(events);
console.log(JSON.stringify({ agents: F.agents, open: F.open, moves: F.moves.map((x) => [x.round, x.src, x.dst, x.amount, x.how]),
  rounds: F.rounds.map((R) => ({ r: R.r, rep: R.rep, solved: R.solved, seats: R.seats, phases: R.phases })),
  live: F.live && { r: F.live.r, phases: F.live.phases } }));
"""

V16_GAMES = [Path.home() / "squid5-runs/e52_v16d/squid5_e52v16_public_sol4/20261015_0635_gpt-6-sol/events.jsonl",
             Path.home() / "squid5-runs/e52_v16d/squid5_e52v16_public_luna4/20261015_0635_gpt-6-luna/events.jsonl"]


def flow_of(tmp_path: Path, events: list[dict]) -> dict:
    (tmp_path / "ev.jsonl").write_text("\n".join(json.dumps(e) for e in events) + "\n")
    (tmp_path / "h.js").write_text(HARNESS_FLOW)
    out = subprocess.run([NODE, str(tmp_path / "h.js"), str(HERE / "static" / "monitor.js"), str(tmp_path / "ev.jsonl")],
                         check=True, capture_output=True, text=True)
    return json.loads(out.stdout)


def check_flow_against_events(got: dict, events: list[dict]) -> None:
    """The figure's data agrees with the events' own totals: each drawn round-end balance is round.end, every done GIVE
    (chat and DECISION) is one move and they add up to the rows' ``given`` totals, and the per-seat ledger (generated,
    refund, charge, gifts, refill) explains each balance change with nothing left over."""
    rounds = [e for e in events if e["event"] == "round"]
    assert [R["r"] for R in got["rounds"]] == [e["round"] for e in rounds]
    for R, e in zip(got["rounds"], rounds):
        assert {a: s["end"] for a, s in R["seats"].items()} == e["end"]
        assert all(s["other"] == 0 for s in R["seats"].values()), R["r"]
        for a, row in e["agents"].items():
            s = R["seats"][a]
            assert s["playing"] and (s["gen"], s["refund"], s["charged"]) == (row["generated"], row.get("returned", 0), row.get("charged", 0))
            assert s["out"] == sum(row.get("given", {}).values())
    gifts = [e for e in events if e["event"] == "gift" and e["kind"] == "give" and e["status"] == "done"]
    assert sorted(m[:4] for m in got["moves"]) == sorted([e["round"], e["src"], e["dst"], e["amount"]] for e in gifts)
    given = sum(v for e in rounds for row in e["agents"].values() for v in row.get("given", {}).values())
    assert sum(m[3] for m in got["moves"]) == given == sum(e["amount"] for e in gifts)
    assert sum(m[4] == "decision" for m in got["moves"]) == sum(bool(e.get("decision")) for e in gifts)


def check_steps(rounds: list[dict], events: list[dict]) -> None:
    """The merged balance chart's inner steps of each finished round: per seat they start at the round's balance before,
    chain (each step starts where the last ended), add up to the round's change, land on round.end with nothing left
    unexplained, and per step agree with the events: generated tokens by call kind, gifts by the TALK they were given
    in (gift ``phase``), the solver's refund in SOLVE and the charge taken in the charge step."""
    ends = {e["round"]: e for e in events if e["event"] == "round"}
    for R in rounds:
        e = ends[R["r"]]
        for a, s in R["seats"].items():
            st = s["steps"]
            assert [t["k"] for t in st] == R["phases"]
            assert st[0]["start"] == s["before"] and st[-1]["end"] == e["end"][a], (R["r"], a)
            assert all(p["end"] == q["start"] for p, q in zip(st, st[1:]))
            assert sum(t["end"] - t["start"] for t in st) == e["end"][a] - s["before"]
            assert all(t["other"] == 0 for t in st), (R["r"], a)
            row = e["agents"].get(a)
            if row:
                assert sum(t["gen"] for t in st) == row["generated"]
                assert sum(t["charge"] for t in st) == row.get("charged", 0)
                assert sum(t["refund"] for t in st if t["k"] == "solve") == row.get("returned", 0)
        gifts = [g for g in events if g["event"] == "gift" and g["round"] == R["r"] and g["kind"] == "give" and g["status"] == "done" and g["amount"] > 0]
        for pk, ph in (("pre", "prep"), ("post", "rescue")):
            want = sum(g["amount"] for g in gifts if g.get("phase") == ph)
            if any(g.get("phase") for g in gifts):
                assert sum(next((t["out"] for t in s["steps"] if t["k"] == pk), 0) for s in R["seats"].values()) == want, (R["r"], pk)


def check_chat_sides(views: list[dict]) -> None:
    """Every chat window puts one agent's bubbles on the left (the opener; both opened: the earlier seat) and the
    other's on the right, for the whole chat."""
    for v in views:
        assert v["left"] != v["right"] and {v["left"], v["right"]} == set(v["pair"]), v["id"]
        assert v["left"] in v["openers"] or not v["openers"], v["id"]
        for side, who, _ in v["bubbles"]:
            assert side == ("L" if who == v["left"] else "R") and who in v["pair"], (v["id"], side, who)
        assert len({who for side, who, _ in v["bubbles"] if side == "L"} & {who for side, who, _ in v["bubbles"] if side == "R"}) == 0


def flow_session() -> list[dict]:
    """Three seats, two finished rounds and a third begun. R1: agent-6 (the representative) solves (+150 refund) and
    GIVEs 100 to agent-17 in a chat; agent-11 GIVEs 50 to agent-17 as its DECISION. R2: agent-6 misses; agent-11 EXITs
    (its 500 charge waived), agent-17 owes 500 with 400 left and goes to zero; agent-6 pays."""
    sid, ag = "flow", [A6, A11, A17]
    ev = [{"event": "session_start", "session_id": sid, "start": 1000, "starts": {A6: 1000, A11: 600, A17: 300}, "agents": ag, "settings": {}}]
    ev += [{"event": "round_start", "round": 1, "balances": {A6: 1000, A11: 600, A17: 300}, "taking_part": ag}]
    ev += [{"event": "call", "round": 1, "agent": a, "kind": "open_chat", "used": u} for a, u in ((A6, 50), (A11, 40), (A17, 30))]
    ev += [{"event": "vote", "round": 1, "rep": A6, "picks": {A6: 3}, "bans": {}},
           {"event": "call", "round": 1, "agent": A6, "kind": "solve", "used": 200},
           {"event": "results", "round": 1, "tried": [A6], "solved": [A6], "pending": {}, "returned": {A6: 150}},
           {"event": "gift", "round": 1, "kind": "give", "src": A6, "dst": A17, "amount": 100, "status": "done", "chat_id": "1.1", "turn": 1},
           {"event": "gift", "round": 1, "kind": "give", "src": A11, "dst": A17, "amount": 60, "status": "refused", "why": "over"},
           {"event": "gift", "round": 1, "kind": "give", "src": A11, "dst": A17, "amount": 50, "status": "done", "chat_id": "1.2", "decision": True},
           {"event": "charges", "round": 1, "taken": {}, "waived": {}, "dead": [], "exits": []},
           {"event": "round", "round": 1, "end": {A6: 800, A11: 510, A17: 420}, "agents": {
               A6: {"balance_before": 1000, "generated": 250, "returned": 150, "charged": 0, "given": {A17: 100}, "status": "in", "representative": True, "solved": True, "solve_call": True},
               A11: {"balance_before": 600, "generated": 40, "returned": 0, "charged": 0, "given": {A17: 50}, "status": "in"},
               A17: {"balance_before": 300, "generated": 30, "returned": 0, "charged": 0, "given": {}, "status": "in"}}}]
    ev += [{"event": "round_start", "round": 2, "balances": {A6: 800, A11: 510, A17: 420}, "taking_part": ag},
           {"event": "vote", "round": 2, "rep": A6},
           {"event": "call", "round": 2, "agent": A6, "kind": "solve", "used": 100},
           {"event": "results", "round": 2, "tried": [A6], "solved": [], "pending": {A6: 500, A11: 500, A17: 500}, "returned": {}},
           {"event": "call", "round": 2, "agent": A11, "kind": "talk", "used": 10},
           {"event": "call", "round": 2, "agent": A17, "kind": "talk", "used": 20},
           {"event": "charges", "round": 2, "taken": {A6: 500, A17: 400}, "waived": {A11: 500}, "dead": [A17], "exits": [A11]},
           {"event": "round", "round": 2, "end": {A6: 200, A11: 500, A17: 0}, "agents": {
               A6: {"balance_before": 800, "generated": 100, "returned": 0, "charged": 500, "given": {}, "status": "in", "representative": True, "solve_call": True},
               A11: {"balance_before": 510, "generated": 10, "returned": 0, "charged": 0, "given": {}, "status": "exited", "exit": True, "exit_reason": "below the charge"},
               A17: {"balance_before": 420, "generated": 20, "returned": 0, "charged": 400, "given": {}, "status": "dead"}}},
           {"event": "round_start", "round": 3, "balances": {A6: 200, A11: 500, A17: 0}, "taking_part": [A6]}]
    return ev


@pytest.mark.skipif(NODE is None, reason="node is not installed")
def test_game_flow_of_a_synthetic_game_draws_round_ends_moves_and_the_ledger(tmp_path):
    ev = flow_session()
    got = flow_of(tmp_path, ev)
    check_flow_against_events(got, ev)
    assert got["open"] == 3 and [R["r"] for R in got["rounds"]] == [1, 2]  # the begun round is not drawn
    assert got["moves"] == [[1, A6, A17, 100, "give"], [1, A11, A17, 50, "decision"]]  # the refused GIVE moved nothing
    r1, r2 = got["rounds"]
    assert (r1["rep"], r1["solved"], r2["solved"]) == (A6, [A6], [])
    assert r1["seats"][A17]["inn"] == 150 and r1["seats"][A6]["byKind"] == {"open_chat": 50, "solve": 200}
    s11, s17 = r2["seats"][A11], r2["seats"][A17]
    assert (s11["exit"], s11["waived"], s11["end"], s11["exitReason"]) == (True, 500, 500, "below the charge")
    assert (s17["status"], s17["charged"], s17["end"]) == ("dead", 400, 0)
    # the merged chart's inner steps (a VOTE game): open board + VOTE -> SOLVE -> TALK -> charges (-> EXIT in R2)
    check_steps(got["rounds"], ev)
    assert r1["phases"] == ["open", "solve", "post", "charge"] and r2["phases"] == ["open", "solve", "post", "charge", "exit"]
    st6 = {t["k"]: t for t in r1["seats"][A6]["steps"]}
    assert (st6["open"]["start"], st6["open"]["end"], st6["solve"]["end"], st6["post"]["end"]) == (1000, 950, 900, 800)
    assert st6["solve"]["solver"] == "✓" and st6["solve"]["refund"] == 150
    st11, st17 = {t["k"]: t for t in r2["seats"][A11]["steps"]}, {t["k"]: t for t in r2["seats"][A17]["steps"]}
    assert st11["charge"]["waived"] == 500 and st11["exit"]["exit"] and st17["charge"]["dead"] and st17["charge"]["end"] == 0
    assert got["live"] == {"r": 3, "phases": ["open", "solve", "post", "charge"]}  # the begun round: drawn faint, not in the totals


@pytest.mark.skipif(NODE is None, reason="node is not installed")
@pytest.mark.parametrize("path", V16_GAMES, ids=["sol", "luna"])
def test_game_flow_of_a_real_v16_game_matches_its_round_ends_and_gifts(tmp_path, path):
    if not path.exists():
        pytest.skip(f"{path} is not on this machine")
    ev = [json.loads(x) for x in path.read_text().splitlines() if x.strip()]
    got = flow_of(tmp_path, ev)
    check_flow_against_events(got, ev)
    check_steps(got["rounds"], ev)
    assert got["moves"]  # both games move tokens


def test_the_page_has_the_game_flow_panel():
    html = (HERE / "monitor.html").read_text()
    js = (HERE / "static" / "monitor.js").read_text()
    assert 'id="flow"' in html and "게임 전체 · 토큰 흐름" in html
    assert "function renderFlow(" in js and "renderFlow();" in js


# --- v16e rotation: the system draws the solver; a TALK before SOLVE (prep) and after RESULTS (rescue) ----------------

HARNESS_ROT = """
globalThis.window = globalThis;
const els = {};
const mk = () => ({ innerHTML: "", hidden: false, dataset: {}, clientWidth: 900, scrollLeft: 0, scrollTop: 0, scrollWidth: 0, scrollHeight: 0, clientHeight: 0,
  querySelector: () => ({ hidden: true, style: {} }) });
globalThis.document = { readyState: "loading", addEventListener() {}, documentElement: { dataset: {}, style: { setProperty() {} } },
  querySelector: (s) => (els[s] = els[s] || mk()) };
require(process.argv[2]);
const events = require("fs").readFileSync(process.argv[3], "utf8").trim().split("\\n").map(JSON.parse);
const M = window.__monitor;
M.S.events = events; M.S.session = "rot";
const m = M.build(events, events.length - 1);
const ag = {}; for (const a of m.agents) ag[a] = { balance: m.ag[a].balance, status: m.ag[a].status };
M.renderChats(m, 1);
M.renderFlow();
M.S.at = events.length - 1; M.S.model = m; M.renderStage(m); M.renderSolve(m); M.renderRoundFlow(m); // 10-17 top area
const F = M.gameFlow(events);
const r1 = m.rounds.get(1);
console.log(JSON.stringify({ ag, warnings: m.warnings, rows: M.chatRows(m, 1), grid: M.recordHTML(m, [1], m.agents), chats: els["#chats"].innerHTML,
  flow: els["#flow"].innerHTML, turns: [...r1.turns.values()].map((t) => [t.k, t.turn, t.phase]),
  rflowHidden: els["#rflowPanel"].hidden, solveBox: els["#solveBox"].innerHTML, stage: els["#stage"].innerHTML,
  feed: M.convoItems(m, "all", [1]).map((x) => [x.kind, M.convoHTML(m, x)]),
  desc: events.filter((e) => ["vote", "talk_intent", "gift", "talk_schedule"].includes(e.event) && e.round === 1).map(M.describe),
  moves: F.moves.map((x) => [x.round, x.src, x.dst, x.amount, x.how, x.phase]),
  rounds: F.rounds.map((R) => ({ r: R.r, rep: R.rep, drawn: R.drawn, solved: R.solved, seats: R.seats, phases: R.phases })),
  views: [...m.rounds.values()].flatMap((r) => [...(r.chats || new Map()).values()].map((c) => { const V = M.chatView(m, r, c);
    return { id: V.id, pair: V.pair, left: V.left, right: V.right, openers: V.openers, bubbles: V.items.filter((x) => x.t === "bub").map((x) => [x.side, x.who, x.chip ? x.chip.cls : null]),
      sys: V.items.filter((x) => x.t === "sys").map((x) => x.kind) }; })) }));
"""


def rotation_session() -> tuple[list[dict], dict]:
    """Two rounds of the e52v16_public_sol4 game as it runs now (rotation, exit_first). In each round's TALK before
    SOLVE agent-6 opens a chat with SAY agent-11 and agent-11 GIVEs it 300 "to think with"; in the TALK after RESULTS
    agent-17 opens one with SAY agent-23, which GIVEs 500 back; every solver answers stay."""
    from squid5.__main__ import EXPERIMENTS
    from squid5.core.config import load
    from squid5.core.providers import ProviderConfig, Reply, Stub
    cfg = load(REPO / "configs/squid5/e52v16_public_sol4.yaml", EXPERIMENTS)
    import dataclasses
    s = dataclasses.replace(cfg.settings, rounds=2, schedule=cfg.settings.schedule[:2])
    assert s.rotation and not s.open_chat and s.exit_first

    def respond(messages, cap):
        a, u = re.search(r"You are (agent-\d+)", messages[0]["content"]).group(1), messages[-1]["content"]
        prep = "SOLVE comes after this TALK." in u
        if ": the opening turn." in u:
            return Reply(f"SAY {A11}: before solve" if prep and a == A6 else f"SAY {A23}: after results" if not prep and a == A17 else "DONE", 50)
        if ": your reply in this chat (" in u:
            n = int(re.search(r"your reply in this chat \((\d+) of", u).group(1))
            return Reply(("here\nGIVE 300: to think with" if prep else "here\nGIVE 500: for the charge") if n == 1 else "LEAVE: bye", 50)
        if ": your decision." in u:
            return Reply("DECISION: GIVE 0: no", 50)
        return Reply("BELIEF: go_left 25, go_right 25, stay 25, jump 25\nACTIONS: stay", 400)
    ev = []
    res = e52.Session(s, cfg.cells[0], 4100, Stub(ProviderConfig("stub", "m"), respond), ev.append, "rot").run()
    return ev, res


@pytest.mark.skipif(NODE is None, reason="node is not installed")
def test_rotation_replay_shows_the_drawn_solver_and_marks_prep_and_rescue_talk(tmp_path):
    """v16e rotation: the vote event says ``drawn`` (no picks or bans); the page replays both TALKs of a round to the
    session's final balances, keeps the prep chats when the rescue schedule arrives, and marks each TALK's rows, chats,
    feed lines and the flow figure's moves as SOLVE 전 (prep) or 결과 뒤 (rescue)."""
    ev, res = rotation_session()
    votes = [e for e in ev if e["event"] == "vote"]
    assert all(v["drawn"] and v["alone"] and not v["picks"] for v in votes)
    gifts = [e for e in ev if e["event"] == "gift" and e["round"] == 1]
    assert [(g["src"], g["amount"], g["phase"]) for g in gifts] == [(A11, 300, "prep"), (A23, 500, "rescue")]
    (tmp_path / "ev.jsonl").write_text("\n".join(json.dumps(e, default=str) for e in ev) + "\n")
    (tmp_path / "h.js").write_text(HARNESS_ROT)
    out = subprocess.run([NODE, str(tmp_path / "h.js"), str(HERE / "static" / "monitor.js"), str(tmp_path / "ev.jsonl")],
                         check=True, capture_output=True, text=True)
    got = json.loads(out.stdout)
    assert got["ag"] == {a: {"balance": v["final"], "status": v["status"]} for a, v in res["agents"].items()}
    assert got["warnings"] == []
    rep1 = votes[0]["rep"]
    # both TALKs' turns are kept apart (the rescue ones under turn + 100), prep chats survive the rescue schedule
    assert {p for _, _, p in got["turns"]} == {"prep", "rescue"} and all(k == t + (100 if p == "rescue" else 0) for k, t, p in got["turns"])
    chats = {c["phase"]: c for c in got["rows"]["chats"]}
    assert set(chats) == {"prep", "rescue"}
    assert sorted(chats["prep"]["pair"]) == sorted([A6, A11]) and chats["prep"]["opening"] == [["say", A6, 0, "done"]]
    assert sorted(chats["rescue"]["pair"]) == sorted([A17, A23]) and chats["rescue"]["opening"] == [["say", A17, 0, "done"]]
    assert [t[2:4] for t in chats["prep"]["turns"]][0] == ["give", 300] and [t[2:4] for t in chats["rescue"]["turns"]][0] == ["give", 500]
    # the step records: the solver row, prep rows above SOLVE, rescue rows below, non-solvers "not the solver"
    g = got["grid"]
    assert f" SOLVER {rep1}" in g and 'class="pix lot"' in g and "시스템이 정함" in g and "투표 결과" not in g and "PICK" not in g  # 10-17: the black ticket
    assert g.index("ph-row ph-prep") < g.index("<b>SOLVE</b>") < g.index("ph-row ph-rescue")
    assert g.count("solver가 아님 · SOLVE 없음") == 3 and "👑" not in g
    assert "ph-prep" in got["chats"] and "ph-rescue" in got["chats"]
    # the feed and the event descriptions say which TALK
    kinds = [k for k, _ in got["feed"]]
    assert kinds[0] == "vote" and " SOLVER" in got["feed"][0][1]
    prep_i = next(i for i, (k, h) in enumerate(got["feed"]) if k == "chat" and "ph-prep" in h)
    resc_i = next(i for i, (k, h) in enumerate(got["feed"]) if k == "chat" and "ph-rescue" in h)
    assert prep_i < resc_i
    assert got["desc"][0] == f"R1 solver {rep1} (시스템이 정함 · 투표 없음)"
    assert any(d.startswith("R1 SOLVE 전 여는 턴 · agent-6 SAY") for d in got["desc"])
    assert any(d.startswith("R1 결과 뒤 여는 턴 · agent-17 SAY") for d in got["desc"])
    assert any(d.startswith("R1 SOLVE 전 GIVE agent-11") for d in got["desc"]) and any(d.startswith("R1 결과 뒤 GIVE agent-23") for d in got["desc"])
    # the whole-game flow: moves carry their TALK; the merged chart splits each round into its steps (shaded
    # sub-columns with labels), draws prep dots hollow and each seat as a staircase through the steps
    assert [m[5] for m in got["moves"] if m[0] == 1] == ["prep", "rescue"] and all(R["drawn"] for R in got["rounds"])
    assert all(R["phases"][:4] == ["pre", "solve", "post", "charge"] for R in got["rounds"])
    assert 'class="fph k-pre"' in got["flow"] and 'class="fph k-post"' in got["flow"] and 'class="dot-prep"' in got["flow"]
    assert "SOLVE 전 TALK" in got["flow"] and "solver(시스템)" in got["flow"] and 'class="phl"' in got["flow"]
    assert 'id="chart"' not in got["flow"]
    # 10-17 top area: no round-flow diagram before v22 (no ticks); the SOLVE answer and the solver's ticket still show
    assert got["rflowHidden"] is True and "R2 SOLVE" in got["solveBox"] and got["stage"].count('class="badge rep"') <= 1
    check_steps(got["rounds"], ev)
    r1 = got["rounds"][0]["seats"]
    pre = {a: next(t for t in s["steps"] if t["k"] == "pre") for a, s in r1.items()}
    post = {a: next(t for t in s["steps"] if t["k"] == "post") for a, s in r1.items()}
    assert pre[A11]["out"] == 300 and pre[A6]["inn"] == 300 and post[A23]["out"] == 500 and post[A17]["inn"] == 500
    sol = next(t for t in r1[rep1]["steps"] if t["k"] == "solve")
    assert sol["solver"] in ("✓", "✗") and sol["byKind"] == {"solve": 400}
    # the chat windows: the opener on the left, the other agent on the right, for every bubble of the chat
    check_chat_sides(got["views"])
    prep_chat = next(v for v in got["views"] if sorted(v["pair"]) == sorted([A6, A11]) and v["openers"] == [A6])
    assert prep_chat["left"] == A6 and ("R", A11) in {(s, w) for s, w, _ in prep_chat["bubbles"]} <= {("L", A6), ("R", A11)}
    assert prep_chat["sys"][:2] == ["open", "say"] and prep_chat["sys"][-1] == "end"  # opened, agent-6's SAY, ..., ended
    assert ("R", A11, "ok") in [tuple(b) for b in prep_chat["bubbles"]]  # agent-11's GIVE 300: a done chip
    assert 'class="cw cw-prep"' in got["chats"] and 'class="cwr R"' in got["chats"] and 'class="mvchip ok"' in got["chats"] and 'class="cws cws-end"' in got["chats"]
    check_flow_against_events({"rounds": [{"r": R["r"], "seats": R["seats"]} for R in got["rounds"]],
                               "moves": [[m[0], m[1], m[2], m[3], m[4]] for m in got["moves"]]}, ev)


V16E_GAMES = sorted((Path.home() / "squid5-runs/e52_v16e").glob("*/*/events.jsonl"))


@pytest.mark.skipif(NODE is None, reason="node is not installed")
@pytest.mark.skipif(not V16E_GAMES, reason="no v16e rotation run on this machine")
@pytest.mark.parametrize("path", V16E_GAMES, ids=lambda p: p.parent.name)
def test_real_rotation_games_replay_without_warnings_and_their_finished_rounds_add_up(tmp_path, path):
    """The v16e model runs (live; maybe unfinished): the page reads them with no warning, every TALK turn is tagged
    prep or rescue, and the finished rounds' ends and gifts agree with the events (as for v16d)."""
    every = [json.loads(x) for x in path.read_text().splitlines() if x.strip()]
    sids = list(dict.fromkeys(e["session_id"] for e in every if e.get("event") == "round_start"))  # workers > 1: interleaved
    if not sids:
        pytest.skip("no round has started yet")
    for sid in sids:
        ev = [e for e in every if e.get("session_id") == sid]
        (tmp_path / "ev.jsonl").write_text("\n".join(json.dumps(e) for e in ev) + "\n")
        (tmp_path / "h.js").write_text(HARNESS_ROT)
        got = json.loads(subprocess.run([NODE, str(tmp_path / "h.js"), str(HERE / "static" / "monitor.js"), str(tmp_path / "ev.jsonl")],
                                        check=True, capture_output=True, text=True).stdout)
        assert got["warnings"] == [] and all(p in ("prep", "rescue") for _, _, p in got["turns"]), sid
        check_chat_sides(got["views"])
        if any(e["event"] == "round" for e in ev):
            check_steps(got["rounds"], ev)
            check_flow_against_events({"rounds": [{"r": R["r"], "seats": R["seats"]} for R in got["rounds"]],
                                       "moves": [m[:5] for m in got["moves"]]},
                                      ev[:max(i for i, e in enumerate(ev) if e["event"] == "round") + 1])


# --- v22 messenger: rooms, ticks, the KakaoTalk-like panel (synthetic session from the spec: v22_fixture.py) ---------

HARNESS_V22 = """
globalThis.window = globalThis;
const els = {};
const mk = () => ({ innerHTML: "", hidden: false, dataset: {}, clientWidth: 900, scrollLeft: 0, scrollTop: 0, scrollWidth: 0, scrollHeight: 0, clientHeight: 0,
  querySelector: () => null });
globalThis.document = { readyState: "loading", addEventListener() {}, documentElement: { dataset: {}, style: { setProperty() {} } },
  querySelector: (s) => (els[s] = els[s] || mk()) };
require(process.argv[2]);
const events = require("fs").readFileSync(process.argv[3], "utf8").trim().split("\\n").map(JSON.parse);
const asks = JSON.parse(process.argv[4]); // [[label, event index, room, viewer]]
const M = window.__monitor;
M.S.events = events; M.S.session = "v22";
const out = {};
for (const [label, at, room, viewer] of asks) {
  const m = M.build(events, at);
  M.S.model = m; M.S.msg = { room, viewer, shown: "" };
  M.renderMessenger(m); M.renderStage(m); M.renderChats(m, m.round);
  out[label] = { isMsg: M.isMsg(m), warnings: m.warnings, round: m.round, list: M.roomList(m, { viewer, round: m.round }), view: room ? M.roomView(m, room, viewer) : null,
    strips: [...m.rounds.keys()].map((R) => [R, M.tickStrip(m, R)]), msgr: els["#msgr"].innerHTML, ticks: els["#ticks"].innerHTML, grid: M.recordHTML(m, [...m.rounds.keys()], m.agents),
    stage: els["#stage"].innerHTML, chatPanelHidden: els["#chatPanel"].hidden, msgPanelHidden: els["#msgPanel"].hidden,
    bubbles: Object.fromEntries(m.agents.map((a) => [a, m.ag[a].bubble])) };
}
out.desc = events.map(M.describe);
console.log(JSON.stringify(out));
"""


def v22_view(tmp_path: Path, events: list[dict], asks: list) -> dict:
    (tmp_path / "ev.jsonl").write_text("\n".join(json.dumps(e) for e in events) + "\n")
    (tmp_path / "h22.js").write_text(HARNESS_V22)
    out = subprocess.run([NODE, str(tmp_path / "h22.js"), str(HERE / "static" / "monitor.js"), str(tmp_path / "ev.jsonl"), json.dumps(asks)],
                         check=True, capture_output=True, text=True)
    return json.loads(out.stdout)


def at_event(ev: list[dict], **kw) -> int:
    """The index of the first event with all these fields."""
    return next(i for i, e in enumerate(ev) if all(e.get(k) == v for k, v in kw.items()))


def test_v22_fixture_follows_the_spec_events():
    ev, final = v22_fixture.session()
    kinds = {e["event"] for e in ev}
    assert {"talk_start", "tick", "room_new", "room_msg", "room_leave", "talk_end"} <= kinds
    assert not kinds & {"chat_turn", "chat_end", "talk_schedule", "ask_decision", "talk_intent"}
    calls = [e for e in ev if e["event"] == "call" and e["kind"] == "talk"]
    assert all(e["phase"] in ("prep", "rescue") and e["turn"] >= 1 and "messages" in e["parsed"] for e in calls)
    assert all(e["room"] and e["tick"] == e["turn"] and e["chat_id"] is None for e in ev if e["event"] in ("gift", "ask"))
    assert {e["status"] for e in ev if e["event"] == "room_msg" and e["kind"] == "give"} == {"done", "cut", "refused"}
    assert [e["reason"] for e in ev if e["event"] == "talk_end"].count("max_ticks") == 1
    assert [e["room"] for e in ev if e["event"] == "room_new"] == [f"R{k}" for k in range(1, 7)]


@pytest.mark.skipif(NODE is None, reason="node is not installed")
def test_v22_room_list_room_history_and_the_agent_view(tmp_path):
    ev, _ = v22_fixture.session()
    end = len(ev) - 1
    got = v22_view(tmp_path, ev, [["all", end, "R1", None], ["v23", end, "R2", A23], ["v23r1", end, "R1", A23]])
    g = got["all"]
    assert g["isMsg"] and g["warnings"] == [] and g["msgPanelHidden"] is False and g["chatPanelHidden"] is True
    # room list: every room of the session, newest activity first, with members (who left is kept apart) and counts
    L = {x["id"]: x for x in g["list"]}
    assert set(L) == {f"R{k}" for k in range(1, 7)} and g["list"][0]["id"] == "R6"
    lastI = [x["lastI"] for x in g["list"]]
    assert lastI == sorted(lastI, reverse=True)
    assert L["R2"]["all"] == [A6, A11, A17, A23] and L["R2"]["members"] == [A6, A11, A17] and L["R2"]["left"] == [A23]
    msgs = [e for e in ev if e["event"] == "room_msg"]
    for rid, x in L.items():
        assert x["total"] == sum(e["room"] == rid for e in msgs)
        assert x["count"] == sum(e["room"] == rid and e["round"] == 3 for e in msgs)  # the replay cursor's round
        last = [e for e in msgs if e["room"] == rid][-1]
        assert (x["last"]["src"], x["last"]["tick"], x["last"]["text"]) == (last["src"], last["tick"], last["text"])
    # R1 seen by all: right side = the room's maker (agent-6); same-tick lines under one divider; chips with outcomes
    V = g["view"]
    assert V["right"] == A6 and V["items"][0] == {"t": "tick", "round": 1, "phase": "prep", "tick": 1, "label": "R1 T1 · SOLVE 전"}
    bubs = [x for x in V["items"] if x["t"] == "bub"]
    assert all(x["side"] == ("R" if x["who"] == A6 else "L") for x in bubs)
    assert [(x["who"], x["kind"], x["label"]) for x in bubs] == [(e["src"], e["kind"], f"R{e['round']} T{e['tick']} · {'SOLVE 전' if e['phase'] == 'prep' else '결과 뒤'}")
                                                               for e in msgs if e["room"] == "R1"]
    chips = {(x["who"], x["kind"]): x["chip"] for x in bubs if x["chip"]}
    assert chips[(A17, "ask")]["cls"] == "ok" and "GIVE 2,000로 응답" in chips[(A17, "ask")]["status"]
    assert chips[(A6, "give")]["status"] == "보냄" and chips[(A6, "give")]["to"] == A17
    assert chips[(A17, "give")]["head"] == "GIVE ALL" and "→ 0" in chips[(A17, "give")]["status"]
    sys_ = [x["text"] for x in V["items"] if x["t"] == "sys"]
    assert sys_[0].startswith("방 R1 생성") and any("17 꺼짐" in t for t in sys_) and any(t.startswith("■ R1 SOLVE 전 TALK 끝") for t in sys_)
    ticks = [(x["round"], x["phase"], x["tick"]) for x in V["items"] if x["t"] == "tick"]
    assert len(ticks) == len(set(ticks))  # one divider per tick
    # agent-23's screen: only its rooms; R2 up to its LEAVE, then nothing of R2 (agent-17's later line is not there)
    v = got["v23"]
    assert sorted(x["id"] for x in v["list"]) == ["R2", "R3", "R5", "R6"] and {x["id"]: x["youLeft"] for x in v["list"]}["R2"] is True
    V2 = v["view"]
    assert V2["youLeft"] and V2["right"] == A23 and [x["kind"] for x in V2["items"] if x["t"] == "sys"][-2:] == ["leave", "left"]
    leave = at_event(ev, event="room_leave", agent=A23)
    assert [x["text"] for x in V2["items"] if x["t"] == "bub"] == [e["text"] for i, e in enumerate(ev[:leave]) if e["event"] == "room_msg" and e["room"] == "R2"]
    assert any(e["event"] == "room_msg" and e["room"] == "R2" for e in ev[leave:])  # there is more, agent-23 does not see it
    assert got["v23r1"]["view"] is not None and all(x["id"] != "R1" for x in got["v23r1"]["list"])  # not a member: not listed
    assert 'data-room="R6"' in g["msgr"] and 'class="rcnt"' in g["msgr"] and "sqp" in g["msgr"] and "6의 화면" in g["msgr"]


@pytest.mark.skipif(NODE is None, reason="node is not installed")
def test_v22_room_history_follows_the_replay_cursor(tmp_path):
    """The messenger shows only what happened up to the event under the replay bar: the tick-3 GIVE in R1 is absent
    one event before its room_msg, there (from the room_msg alone) at it, and the ASK it answers turns answered once
    the gift event is read."""
    ev, _ = v22_fixture.session()
    give = at_event(ev, event="room_msg", room="R1", kind="give")
    got = v22_view(tmp_path, ev, [["before", give - 1, "R1", None], ["at", give, "R1", None], ["gift", give + 1, "R1", None], ["early", at_event(ev, event="room_new", room="R2"), None, None]])
    kinds = lambda k: [(x["who"], x["kind"]) for x in got[k]["view"]["items"] if x["t"] == "bub"]  # noqa: E731
    assert (A6, "give") not in kinds("before") and (A6, "give") in kinds("at")
    ask = lambda k: next(x["chip"] for x in got[k]["view"]["items"] if x["t"] == "bub" and x["kind"] == "ask")  # noqa: E731
    assert ask("before")["status"] == "응답 기다리는 중" and ask("gift")["cls"] == "ok"
    assert [x["id"] for x in got["early"]["list"]] == ["R2", "R1"]  # R3 is made later in the tick
    assert not any(x["t"] == "sys" and x["kind"] == "end" for x in got["at"]["view"]["items"])  # the TALK has not ended yet


@pytest.mark.skipif(NODE is None, reason="node is not installed")
def test_v22_tick_strip_marks_called_done_woken_waiting_and_the_end(tmp_path):
    ev, _ = v22_fixture.session()
    got = v22_view(tmp_path, ev, [["end", len(ev) - 1, None, None]])["end"]
    strips = {R: S for R, S in got["strips"]}
    prep1, resc1 = strips[1]
    assert (prep1["phase"], prep1["max"], prep1["end"]) == ("prep", 12, {"ticks": 5, "reason": "all_done"})
    T = {c["tick"]: c for c in prep1["ticks"]}
    ticks = [e for e in ev if e["event"] == "tick" and e["round"] == 1 and e["phase"] == "prep"]
    assert [T[e["tick"]]["called"] for e in ticks] == [e["called"] for e in ticks] and [T[e["tick"]]["waiting"] for e in ticks] == [e["waiting_done"] for e in ticks]
    assert T[1]["woke"] == [] and T[3]["waiting"] == [A11]
    assert T[4]["called"] == [A17] and T[4]["woke"] == [A17]  # DONE at T3, then agent-6's GIVE: called again
    assert T[5]["called"] == [A6] and T[5]["woke"] == [A6] and T[5]["done"] == [A6]
    assert (T[1]["msgs"], T[1]["gives"], T[2]["asks"], T[3]["leaves"]) == (2, 1, 1, 1)
    r2 = strips[2][0]["ticks"][0]
    assert A11 in r2["exit"] and r2["gives"] == 3
    prep3 = strips[3][0]
    assert prep3["end"] == {"ticks": 12, "reason": "max_ticks"} and len(prep3["ticks"]) == 12 and not any(c["done"] for c in prep3["ticks"])
    assert "틱 상한" in got["ticks"] and 'class="tsrow ph-prep"' in got["ticks"] and 'class="tsrow ph-rescue"' in got["ticks"]
    assert resc1["phase"] == "rescue" and resc1["end"]["reason"] == "all_done"


@pytest.mark.skipif(NODE is None, reason="node is not installed")
def test_v22_step_records_stage_bubbles_and_event_lines(tmp_path):
    ev, _ = v22_fixture.session()
    t1 = at_event(ev, event="call", round=1, phase="prep", turn=1, agent=A23)  # agent-23's GIVE, not carried out yet
    got = v22_view(tmp_path, ev, [["end", len(ev) - 1, None, None], ["t1", t1, None, None], ["t1end", at_event(ev, event="room_msg", round=1, src=A6), None, None]])
    lines = lambda k, a: [l[1] for l in got[k]["bubbles"][a]["lines"]]  # noqa: E731
    assert lines("t1", A23) == ["GIVE 17 5,000", "DONE"]
    assert lines("t1", A6) == ["→ 17: You solve this round. Do you have enough to think it throug…"]  # clipped; the full text is the tooltip
    assert lines("t1end", A6) == ["→ R1: You solve this round. Do you have enough to think it throug…"]  # named once the room is known
    grid = got["end"]["grid"]
    assert "<b>T12</b><span class=dim>/12틱</span>" in grid and "TALK 끝" in grid and "틱 상한에 닿음" in grid
    assert "슬롯" not in grid and "undefined" not in grid
    d = got["desc"]
    assert any(x.startswith("R1 SOLVE 전 T3 · 부름 6, 17, 23 · 대기(DONE) 11") for x in d)
    assert any(x == "R1 SOLVE 전 T3 · 23 R2 나감" for x in d) and any(x.startswith("R3 SOLVE 전 TALK 끝 · 12틱 · 틱 상한") for x in d)
    assert any(x.startswith("R1 SOLVE 전 TALK T1 · agent-6 응답") for x in d)


# --- 10-17 top area: seats in rows (the solver's ticket), the SOLVE answer, the round flow and the guard's prompt ---------

HARNESS_TOP = """
globalThis.window = globalThis;
const els = {};
const mk = () => ({ innerHTML: "", hidden: false, dataset: {}, clientWidth: 900, scrollLeft: 0, scrollTop: 0, scrollWidth: 0, scrollHeight: 0, clientHeight: 0,
  querySelector: () => null });
globalThis.document = { readyState: "loading", addEventListener() {}, documentElement: { dataset: {}, style: { setProperty() {} } },
  querySelector: (s) => (els[s] = els[s] || mk()) };
require(process.argv[2]);
const events = require("fs").readFileSync(process.argv[3], "utf8").trim().split("\\n").map(JSON.parse);
const asks = JSON.parse(process.argv[4]); // [[label, event index, step clicked (null = the cursor's), agent]]
const M = window.__monitor;
M.S.events = events; M.S.session = "top";
const out = { steps: events.map((_, i) => M.rfStepOf(events, i)) };
for (const [label, at, sel, agent] of asks) {
  const m = M.build(events, at);
  M.S.at = at; M.S.model = m; M.S.rf = { sel, agent };
  M.renderStage(m); M.renderSolve(m); M.renderRoundFlow(m);
  out[label] = { rep: m.rep, round: m.round, stage: els["#stage"].innerHTML, solve: els["#solveBox"].innerHTML, rows: M.solveRows(m, m.round),
    rflowHidden: els["#rflowPanel"].hidden, rflow: els["#rflow"].innerHTML, sup: els["#sup"].innerHTML, calls: sel ? M.rfCalls(m, sel) : [] };
}
console.log(JSON.stringify(out));
"""


def top_view(tmp_path: Path, events: list[dict], asks: list) -> dict:
    (tmp_path / "ev.jsonl").write_text("\n".join(json.dumps(e) for e in events) + "\n")
    (tmp_path / "top.js").write_text(HARNESS_TOP)
    out = subprocess.run([NODE, str(tmp_path / "top.js"), str(HERE / "static" / "monitor.js"), str(tmp_path / "ev.jsonl"), json.dumps(asks)],
                         check=True, capture_output=True, text=True)
    return json.loads(out.stdout)


RF_EXPECT = {"session_start": "init", "round_start": "draw", "results": "results", "charges": "charges", "round": "next"}


def rf_expected(ev: list[dict], i: int) -> str | None:
    """The round-flow box (report: v22_round, boxes 0 .. 12) an event belongs to, written out from the events."""
    e, resc = ev[i], ev[i].get("phase") == "rescue"
    k = e["event"]
    if k in RF_EXPECT:
        return RF_EXPECT[k]
    if k == "vote":
        before = [x for x in ev[:i] if x.get("round") == e["round"]]
        return "exit" if any(x["event"] == "talk_end" and x.get("phase") == "prep" for x in before) else "draw"
    if k in ("talk_start", "tick"):
        return "r_call" if resc else "p_call"
    if k in ("call_start", "call"):
        return "solve" if e["kind"] == "solve" else ("r_write" if resc else "p_write")
    if k in ("room_new", "room_msg", "room_leave", "gift", "ask"):
        return "r_end" if resc else "p_end"
    if k == "talk_end":
        return "r_end" if resc else "exit"
    return None


@pytest.mark.skipif(NODE is None, reason="node is not installed")
def test_v22_top_area_seat_rows_solve_answer_and_the_round_flow(tmp_path):
    ev, _ = v22_fixture.session()
    solve = at_event(ev, event="call", round=1, kind="solve")
    tick2 = at_event(ev, event="call", round=1, phase="prep", turn=2)
    charges = at_event(ev, event="charges", round=1)
    got = top_view(tmp_path, ev, [["prep", tick2, None, None], ["solve", solve, None, None], ["p3", charges, "p_write", None],
                                  ["p3b", charges, "p_write", A6], ["s6", charges, "solve", None], ["eng", charges, "charges", None]])
    assert got["steps"] == [rf_expected(ev, i) for i in range(len(ev))] and None not in got["steps"]  # every v22 event has its box
    rep = ev[at_event(ev, event="vote", round=1)]["rep"]
    # seats: one row each, the drawn solver framed (class solver) with the black ticket and SOLVER; player numbers inline
    g = got["prep"]
    assert g["rep"] == rep and g["stage"].count('class="seat ') == 4 and g["stage"].count(" solver\"") == 1
    assert g["stage"].count('class="badge rep"') == 1 and "SOLVER</span>" in g["stage"] and 'class="pix lot"' in g["stage"] and "대표" not in g["stage"]
    assert all(f"#{n}" in g["stage"] for n in ("456", "001", "218", "067"))
    # the SOLVE answer: nothing yet before it; at the call: answer vs the round's answer, tokens vs the cap, the lazy parts
    assert g["rows"] == [] and "아직 SOLVE 전" in g["solve"]
    e, ans = ev[solve], ev[at_event(ev, event="round_start", round=1)].get("public", {}).get("answers", [])
    (row,) = got["solve"]["rows"]
    assert (row["agent"], row["out"], row["cap"], row["answer"], row["answers"]) == (e["agent"], e["out_tokens"], e["cap"], e["parsed"]["actions"], ans)
    assert row["verdict"] == "unknown" and row["refund"] is None  # the fixture logs no answer and the results are not read yet
    (after,) = got["s6"]["rows"]  # at the charges: the engine's verdict (results.solved) and the charge it announced
    assert after["verdict"] == ("ok" if e["agent"] in ev[at_event(ev, event="results", round=1)]["solved"] else "bad") and after["refund"] == 0
    h = got["solve"]["solve"]
    assert f"생성 <b>{e['out_tokens']:,}</b> / 한도 {e['cap']:,}" in h and "🧠 생각 요약" in h and "📨 USER 프롬프트" in h and "📝 출력 그대로" in h
    # the round flow: shown for v22; the cursor's box framed; the guard reads the clicked box's USER prompt
    assert got["solve"]["rflowHidden"] is False and got["solve"]["rflow"].count('class="rf-box') == 13
    assert 'data-step="solve" aria-pressed="true"' in got["solve"]["rflow"] and "rf-box cur" in got["solve"]["rflow"]
    assert html.escape(e["user"], quote=True) in got["solve"]["sup"] and "<pre" in got["solve"]["sup"]
    p3 = got["p3"]
    prep = [i for i, x in enumerate(ev[:charges + 1]) if x["event"] == "call" and x["kind"] == "talk" and x["round"] == 1 and x["phase"] == "prep"]
    last = {ev[i]["agent"]: i for i in prep}
    assert sorted(c["i"] for c in p3["calls"]) == sorted(last.values()) and p3["calls"][0]["i"] == max(last.values())  # newest first
    assert html.escape(ev[max(last.values())]["user"], quote=True) in p3["sup"] and 'data-rf="follow"' in p3["sup"]
    assert html.escape(ev[last[A6]]["user"], quote=True) in got["p3b"]["sup"] and f'sup-ag on" data-agent="{A6}"' in got["p3b"]["sup"]
    assert html.escape(e["user"], quote=True) in got["s6"]["sup"]
    assert "<pre" not in got["eng"]["sup"] and "프롬프트 없음" in got["eng"]["sup"] and "R1 벌금" in got["eng"]["sup"]


@pytest.mark.skipif(NODE is None, reason="node is not installed")
def test_v22_game_flow_matches_round_ends_gifts_and_steps(tmp_path):
    ev, _ = v22_fixture.session()
    got = flow_of(tmp_path, ev)
    check_flow_against_events(got, ev)
    check_steps(got["rounds"], ev)
    assert got["rounds"][1]["phases"][-1] == "exit"  # agent-11's EXIT is read from its call (no talk_intent in v22)


def test_v22_export_of_the_fixture_has_the_messenger_and_no_third_party_sheets(tmp_path, monkeypatch):
    d = tmp_path / "runs" / "e52_v22" / "fixture"
    v22_fixture.write(d)  # noqa: the default session
    assets = tmp_path / "assets"
    assets.mkdir()
    (assets / "manifest.json").write_text(json.dumps({"characters": [], "bubble": None}))
    monkeypatch.setattr(serve, "ASSETS", assets)
    out = tmp_path / "x.html"
    payload = export.export(d, None, out)  # default: our own characters, even when assets/ has sheets
    html = out.read_text()
    assert payload["assets"] is None and 'id="msgPanel"' in html and "function renderMessenger(" in html and "function squidAvatar(" in html
    assert {e["event"] for e in payload["events"]} >= {"room_new", "room_msg", "tick"} and payload["puzzle_error"] is None


def test_the_page_draws_its_own_characters_and_loads_sheets_only_on_request():
    js = (HERE / "static" / "monitor.js").read_text()
    assert 'q.get("sprites") === "sheets"' in js and "loadAssets();" in js
    assert all(f'num: "{n}"' in js for n in ("456", "001", "218", "067"))
    html = (HERE / "monitor.html").read_text()
    assert 'id="msgPanel"' in html and 'id="msgr"' in html and 'id="ticks"' in html


@pytest.mark.skipif(NODE is None, reason="node is not installed")
def test_the_characters_show_their_number_and_seat_colour(tmp_path):
    (tmp_path / "c.js").write_text("""
globalThis.window = globalThis;
globalThis.document = { readyState: "loading", addEventListener() {}, documentElement: { dataset: {}, style: { setProperty() {} } }, querySelector: () => null };
require(process.argv[2]);
const M = window.__monitor;
console.log(JSON.stringify([0, 1, 2, 3].map((k) => [M.squidAvatar(k, 96), M.squidProfile(k, 28)])));
""")
    got = json.loads(subprocess.run([NODE, str(tmp_path / "c.js"), str(HERE / "static" / "monitor.js")], check=True, capture_output=True, text=True).stdout)
    for k, (full, prof) in enumerate(got):
        num = ["456", "001", "218", "067"][k]
        assert f'aria-label="{num}"' in full and f'aria-label="{num}"' in prof
        assert f"var(--a{k})" in full and f"var(--a{k})" in prof  # outline + shoes / the profile's tint
        assert 'class="f0"' in full and 'class="f1"' in full and 'fill="#151515"' in full  # two leg frames; the digits
        assert 'height="96"' in full and 'viewBox="0 0 24 32"' in full


V22_RUNS = [p.parent for p in [Path("/private/tmp/claude-501/v22_stub/events.jsonl"), *sorted((Path.home() / "squid5-runs/e52_v22").glob("*/*/events.jsonl"))]
            if p.exists()]


@pytest.mark.skipif(NODE is None, reason="node is not installed")
@pytest.mark.skipif(not V22_RUNS, reason="no engine-written v22 run on this machine")
@pytest.mark.parametrize("d", V22_RUNS, ids=lambda p: p.name)
def test_engine_written_v22_runs_replay_and_export(tmp_path, d):
    """Runs the engine wrote (the stub run, model runs): every session replays with no warning, its rooms and tick
    strips hold every room_msg and tick, the finished rounds' ledger adds up, and the export works."""
    every = [json.loads(x) for x in (d / "events.jsonl").read_text().splitlines() if x.strip()]
    for sid in list(dict.fromkeys(e["session_id"] for e in every if e.get("event") == "round_start"))[:3]:
        ev = [e for e in every if e.get("session_id") == sid]
        got = v22_view(tmp_path, ev, [["end", len(ev) - 1, None, None]])["end"]
        assert got["isMsg"] and got["warnings"] == [], sid
        msgs = [e for e in ev if e["event"] == "room_msg"]
        assert sum(x["total"] for x in got["list"]) == len(msgs)
        assert sum(len(T["ticks"]) for _, S in got["strips"] for T in S) == sum(e["event"] == "tick" for e in ev)
        if any(e["event"] == "round" for e in ev):
            fin = ev[:max(i for i, e in enumerate(ev) if e["event"] == "round") + 1]
            F = flow_of(tmp_path, fin)
            check_flow_against_events(F, fin)
            check_steps(F["rounds"], fin)
    p = export.export(d, None, tmp_path / "x.html")
    assert p["assets"] is None and 'id="msgPanel"' in (tmp_path / "x.html").read_text()


def test_run_list_filter_fields(tmp_path):  # 10-17: date, version and seeds for the run filters
    d = tmp_path / "e52_v22" / "squid5_e52v22_public_sol4" / "20261017_1001_gpt-6-sol"
    d.mkdir(parents=True)
    ev = d / "events.jsonl"
    ev.write_text('{"event": "session_start", "session_id": "a", "cell_id": "talk", "seed": 4102}\n'
                  '{"event": "call", "session_id": "a", "seed": 1}\n'
                  '{"event": "session_start", "session_id": "b", "cell_id": "talk", "seed": 4101}\n')
    (r,) = serve.list_runs(tmp_path)
    assert (r["date"], r["version"], r["seeds"]) == ("2026-10-17", "5.2 v22", [4101, 4102])
    with ev.open("a") as f:
        f.write('{"event": "session_start", "session_id": "c", "cell_id": "talk", "seed": 4103}')  # no newline yet
    assert serve.run_seeds(ev) == [4101, 4102]
    with ev.open("a") as f:
        f.write("\n")
    assert serve.run_seeds(ev) == [4101, 4102, 4103]
    assert serve.run_labels("e52_v21/squid5_e52v21_public_luna4/x", 0)["version"] == "5.2 v21"


def test_run_list_harness(tmp_path):  # 10-19: the harness filter reads the model kind and any seat's kind
    for name, cfg, want in [("a", "model:\n  kind: claude_cli\n", ["claude code"]),
                            ("b", "model:\n  kind: codex_cli\n", ["codex"]),
                            ("c", "model:\n  kind: ollama\n", ["api"]),
                            ("d", "model:\n  kind: stub\ngame:\n  seats:\n    agent-6:\n      kind: claude_cli\n"
                                  "    agent-17:\n      kind: codex_cli\n", ["claude code", "codex"]),
                            ("e", None, [])]:
        d = tmp_path / name
        d.mkdir()
        (d / "events.jsonl").write_text("")
        if cfg:
            (d / "config.yaml").write_text(cfg)
        assert serve.run_harness(d) == want
    assert {r["run"]: r["harness"] for r in serve.list_runs(tmp_path)}["d"] == ["claude code", "codex"]


@pytest.mark.skipif(NODE is None, reason="node is not installed")
@pytest.mark.skipif(not [d for d in V22_RUNS if "astra" in str(d)], reason="no engine-written v22 Astra run on this machine")
def test_engine_written_v22_solve_answers_and_flow_boxes(tmp_path):
    d = [d for d in V22_RUNS if "astra" in str(d)][0]
    ev = events_of(d, json.loads((d / "events.jsonl").read_text().splitlines()[0])["session_id"])
    solves = [i for i, e in enumerate(ev) if e["event"] == "call" and e["kind"] == "solve"]
    got = top_view(tmp_path, ev, [[f"s{i}", i, None, None] for i in solves])
    assert got["steps"] == [rf_expected(ev, i) for i in range(len(ev))]
    for i in solves:
        e = ev[i]
        (row,) = got[f"s{i}"]["rows"]
        assert (row["agent"], row["out"], row["cap"], row["verdict"]) == (e["agent"], e["out_tokens"], e["cap"], "ok" if e["parsed"] == e["answers"] else "bad")
        if "BELIEF" in e["text"]:
            assert row["belief"] and abs(sum(row["belief"].values()) - 1) < 1e-9
        assert got[f"s{i}"]["stage"].count('class="badge rep"') == 1 and f"{e['agent']}</b>" in got[f"s{i}"]["stage"]


# --- 10-17 (2): rule counts in the round task panel, the giving panels, the record drawer ------------------------------

E01 = {"clauses": 3, "trap_query": True, "all_actions": True, "distinct_actions": True, "min_per_action": 2,
       "top": [[0.37, 0.43], [0.47, 0.53], [0.57, 0.63], [0.67, 0.73]]}  # the 5.2 v22 profile e01


def v22_public_run(tmp_path, seed: int = 4101, n: int = 4, per_agent: int = 5) -> tuple[Path, str]:
    """A run dir whose round 1 is logged as the v22 engine logs it (round_start.public of a v15+ ``top`` round)."""
    from squid5.core import puzzle as pz
    spec = Spec(**E01)
    puzzle, shown, attempt = public_round(seed, 1, spec, n, per_agent)
    truth = pz.public_truth(seed, 1, spec, n, per_agent)
    d = tmp_path / "runs" / "e52_v22" / "pub"
    d.mkdir(parents=True)
    sid = f"talk-s{seed}-pub"
    pub = {"per_agent": per_agent, "n": n, "ambiguity": 0, "attempt": attempt, "rule": truth.description,
           "generator_rule": puzzle.rule.description, "queries": [str(q) for q in puzzle.queries],
           "answers": [truth.evaluate(q) for q in puzzle.queries], "examples": [str(c) for c in shown]}
    rows = [{"event": "session_start", "session_id": sid, "cell_id": "talk", "seed": seed, "agents": list(rules.TEAM_AGENTS),
             "settings": {"rounds": 1, "charge": 6000}},
            {"event": "round_start", "session_id": sid, "round": 1, "profile": "e01", "taking_part": list(rules.TEAM_AGENTS)[:n],
             "public": pub}]
    (d / "events.jsonl").write_text("".join(json.dumps(r) + "\n" for r in rows))
    import yaml
    (d / "config.yaml").write_text(yaml.safe_dump({"name": "t", "mode": "game", "reps": 1, "game": {
        "rounds": 1, "public_per_agent": per_agent, "schedule": ["e01"], "profiles": {"e01": E01}}}))
    return d, sid


def test_rule_space_of_a_shape_is_the_engines_enumeration():
    assert serve.space_size((1, 1, 1), True) == 25_996  # 5.2 v15..v22: three one-attribute clauses, no action twice
    assert serve.space_size((1,), True) == serve.space_size([1], True) > 0


def test_round_task_counts_the_rules_left_for_each_number_taking_part(tmp_path):
    """/api/puzzle of a v22 round: the shape's whole space, the rules consistent with the examples shown for N = 1..4
    (prefixes of one order, so never more rules with more agents), how many of them give each action for the new
    signal (they add up), and the rule scored for each N (drawn per N; the round's own N is the logged one)."""
    d, sid = v22_public_run(tmp_path)
    j = serve.round_puzzle(d, sid, 1)
    assert j["space"] == 25_996 and j["distinct"] is True and j["rule_desc"] == j["rule_text"]
    assert j["counts"] == j["by_n"][3]["counts"]
    prev = j["space"]
    for x in j["by_n"]:
        c = x["counts"]
        assert c["space"] == 25_996 and 1 <= c["consistent"] <= prev and sum(c["by_action"].values()) == c["consistent"]
        assert c["by_action"][x["truth_answers"][0]] >= 1  # the scored rule is one of the consistent ones
        assert {a: n for a, n in c["by_action"].items() if n} == {s["action"]: s["rules"] for s in x["split"][0]["shares"]}
        prev = c["consistent"]
    assert j["by_n"][3]["truth_rule"] == j["rule_text"]  # N = 4: the rule the round was scored by
    # seed 4101 round 1 as GPT-6 Astra played it (e52_v22 ... astra4): 250 rules with one agent's 5 examples, 13 with 20
    assert j["by_n"][0]["counts"]["consistent"] == 250
    assert j["by_n"][3]["counts"]["by_action"] == {"go_left": 9, "go_right": 0, "stay": 4, "jump": 0}


def test_transfer_points_take_both_margins_and_the_ask_before_the_give():
    """Section 03 of the v21 report: margin = (balance after the move - the announced charge) / the charge; asked =
    the receiver asked this giver earlier in the same round (a same-tick ASK was not read yet; the TALK before SOLVE
    is earlier than the TALK after RESULTS)."""
    ev = [{"event": "session_start", "settings": {"charge": 1000}},
          {"event": "ask", "round": 1, "phase": "prep", "tick": 1, "src": A11, "dst": A6, "amount": 500, "status": "done"},
          {"event": "gift", "kind": "give", "round": 1, "phase": "prep", "tick": 1, "src": A6, "dst": A11, "amount": 300,
           "status": "done", "balances": {A6: 4700, A11: 1300}},  # same tick as the ASK: voluntary
          {"event": "gift", "kind": "give", "round": 1, "phase": "prep", "tick": 2, "src": A6, "dst": A11, "amount": 200,
           "status": "done", "balances": {A6: 4500, A11: 1500}},  # a tick later: asked
          {"event": "gift", "kind": "give", "round": 1, "phase": "prep", "tick": 2, "src": A17, "dst": A11, "amount": 100,
           "status": "refused", "balances": {A17: 50, A11: 1500}},  # not carried out: no point
          {"event": "results", "round": 1, "pending": {A6: 1000, A11: 1000, A17: 1000}},
          {"event": "gift", "kind": "give", "round": 1, "phase": "rescue", "tick": 1, "src": A6, "dst": A11, "amount": 500,
           "status": "done", "balances": {A6: 3000, A11: 2000}}]  # the TALK after RESULTS: the prep ASK is earlier
    t = serve.transfer_points(ev)
    assert t["charge"] == 1000
    assert [(p["phase"], p["tick"], p["amount"], p["x"], p["y"], p["y_before"], p["asked"]) for p in t["points"]] == [
        ("prep", 1, 300, 4.7, 1.3, 1.0, False), ("prep", 2, 200, 4.5, 1.5, 1.3, True), ("rescue", 1, 500, 2.0, 1.0, 0.5, True)]
    assert t["points"][1]["ask"]["amount"] == 500 and t["points"][0]["same_tick"] is True
    assert t["counts"] == {"all": 3, "voluntary": 1, "asked": 2, "asked_by_ask": 2, "asked_by_text": 0, "same_tick": 1}


def test_give_sources_one_rule_for_asked_and_voluntary():
    """The 10-17 giving rule (serve.give_sources): voluntary = the giver gave first, unasked. Asked = earlier in the same
    round the receiver sent this giver an ASK line or a request message (REQUEST_RE); a same-tick request was not
    visible yet (voluntary, counted as same-tick); the previous round's request does not count; a request in the TALK
    before SOLVE counts for a GIVE in the TALK after RESULTS."""
    room = lambda r, ph, k, rid, mem: {"event": "room_new", "round": r, "phase": ph, "tick": k, "room": rid, "members": mem, "by": mem[0]}  # noqa: E731
    say = lambda r, ph, k, rid, src, text: {"event": "room_msg", "round": r, "phase": ph, "tick": k, "room": rid, "src": src, "kind": "say", "text": text}  # noqa: E731
    ask = lambda r, ph, k, src, dst: {"event": "ask", "kind": "ask", "round": r, "phase": ph, "tick": k, "turn": k, "src": src, "dst": dst, "amount": 900, "status": "done", "text": "need it"}  # noqa: E731
    give = lambda r, ph, k, src, dst: {"event": "gift", "kind": "give", "round": r, "phase": ph, "tick": k, "turn": k, "src": src, "dst": dst, "amount": 100, "status": "done", "balances": {src: 5000, dst: 2000}}  # noqa: E731
    ev = [{"event": "session_start", "settings": {"charge": 1000}},
          {"event": "round_start", "round": 1},
          room(1, "prep", 1, "R1", [A6, A11]), room(1, "prep", 1, "R2", [A6, A17, A23]),
          ask(1, "prep", 1, A11, A6),                                   # (a) ASK in tick 1 ...
          give(1, "prep", 2, A6, A11),                                  # ... GIVE in tick 2: asked (ASK)
          say(1, "prep", 1, "R2", A17, "agent-6, could you spare 2,000 tokens?"),  # (b) request message in tick 1 ...
          give(1, "prep", 2, A6, A17),                                  # ... GIVE in tick 2: asked (text)
          ask(1, "prep", 3, A23, A6), give(1, "prep", 3, A6, A23),      # (c) same-tick ASK: voluntary, same-tick
          say(1, "prep", 1, "R2", A23, "Thanks, all fine here."),       # not a request
          {"event": "results", "round": 1, "pending": {}},
          ask(1, "prep", 2, A6, A17),                                   # (e) prep-TALK ASK (A6 asks A17) ...
          give(1, "rescue", 1, A17, A6),                                # ... rescue GIVE in the same round: asked
          {"event": "round_start", "round": 2},
          give(2, "prep", 1, A6, A11)]                                  # (d) the request was in round 1 only: voluntary
    src = serve.give_sources(ev)
    gifts = [i for i, e in enumerate(ev) if e["event"] == "gift"]
    got = [(ev[i]["src"], ev[i]["dst"], src[i]["asked"], src[i]["via"], src[i]["same_tick"]) for i in gifts]
    assert got == [(A6, A11, True, "ask", False), (A6, A17, True, "text", False), (A6, A23, False, None, True),
                   (A17, A6, True, "ask", False), (A6, A11, False, None, False)]
    assert serve.give_counts(ev) == {"all": 5, "voluntary": 2, "asked": 3, "asked_by_ask": 2, "asked_by_text": 1, "same_tick": 1}
    # the table's ASK columns follow the same order: the same-tick ASK is not answered by the GIVE beside it
    g = {(p["giver"], p["receiver"], p["kind"]) for p in serve.giving_points(ev)["points"]}
    assert (A6, A23, "declined") in g and (A6, A23, "gift") in g and (A6, A11, "answer") in g and (A17, A6, "answer") in g
    # the request regex: conservative
    hits = ["Could you spare 3000?", "can you top me up", "please send 500", "spare me 2,000", "I need 4,000 more tokens"]
    misses = ["Please report if you need help covering the charge.", "I can help if you need more tokens", "Please retain your reserve."]
    assert all(serve.REQUEST_RE.search(t) for t in hits) and not any(serve.REQUEST_RE.search(t) for t in misses)


HARNESS_PANELS = """
globalThis.window = globalThis;
const els = {};
globalThis.document = { readyState: "loading", addEventListener() {}, documentElement: { dataset: {}, style: { setProperty() {} } },
  querySelector: (s) => (els[s] = els[s] || { innerHTML: "", hidden: false, scrollLeft: 0, scrollTop: 0, scrollWidth: 0, scrollHeight: 0, clientWidth: 900, clientHeight: 0, querySelector: () => null }) };
require(process.argv[2]);
const events = require("fs").readFileSync(process.argv[3], "utf8").trim().split("\\n").map(JSON.parse);
const M = window.__monitor;
M.S.events = events; M.S.session = "v22";
const m = M.build(events, events.length - 1);
M.S.model = m; M.S.at = events.length - 1;
const T = { charge: 1000, counts: { all: 2, voluntary: 1, asked: 1, asked_by_ask: 1, asked_by_text: 0, same_tick: 1 }, points: [{ round: 1, phase: "prep", tick: 1, giver: "agent-6", receiver: "agent-11", amount: 300, x: 4, y: 1, y_before: 0.7, asked: false },
  { round: 1, phase: "prep", tick: 2, giver: "agent-6", receiver: "agent-11", amount: 100, x: 0, y: 3, y_before: 2.9, asked: true, ask: { amount: 500, tick: 1 } }] };
const call = events.findIndex((e) => e.event === "call" && e.kind === "talk");
const a = events[call].agent, R = events[call].round;
M.S.rec = { agent: a, round: R, call, scroll: false };
M.renderRecord(m);
console.log(JSON.stringify({ panels: M.transferPanels(T, 900), none: M.transferPanels({ charge: 1000, points: [] }, 900),
  rec: M.recordHTML(m, [R], [a], call), drawer: els["#recBody"].innerHTML, head: els["#recHead"].innerHTML, hidden: els["#recDrawer"].hidden,
  ticks: (M.renderMessenger(m), els["#ticks"].innerHTML), msgr: els["#msgr"].innerHTML, call, a }));
"""


@pytest.mark.skipif(NODE is None, reason="node is not installed")
def test_giving_panels_and_the_record_drawer(tmp_path):
    """The 나눔 view: three panels (all, voluntary, asked), one colour, area by amount, the amount-weighted centre;
    the record drawer: one seat's column of one round with the clicked call marked, opened from tick faces and
    messenger bubbles (data-rec-call)."""
    ev, _ = v22_fixture.session()
    (tmp_path / "ev.jsonl").write_text("".join(json.dumps(e) + "\n" for e in ev))
    (tmp_path / "h.js").write_text(HARNESS_PANELS)
    out = subprocess.run([NODE, str(tmp_path / "h.js"), str(HERE / "static" / "monitor.js"), str(tmp_path / "ev.jsonl")],
                         check=True, capture_output=True, text=True)
    got = json.loads(out.stdout)
    p = got["panels"]
    assert p.count('class="tpwrap"') == 3 and "둘 다" in p and "자발적으로 준 것" in p and "달라고 해서 준 것" in p
    assert "가중 중심 <b>(3.00, 1.50)</b>" in p  # (300*4 + 100*0) / 400, (300*1 + 100*3) / 400
    assert "가중 중심 <b>(4.00, 1.00)</b>" in p and "가중 중심 <b>(0.00, 3.00)</b>" in p
    assert "var(--a" not in p and p.count('class="tdot"') == 4  # one colour; each GIVE once in "both", once in its own panel
    assert "아직 실행된 GIVE가 없습니다" in got["none"]
    assert "GIVE <b>2</b> = 자발적 <b>1</b> + 달라고 해서 <b>1</b>" in p and "같은 틱 요청이 있던 것 <b>1</b>" in p
    assert html.escape(serve.REQUEST_RE.pattern, quote=True) in p  # the caption lists the exact request regex
    assert f'class="cell sel" data-call="{got["call"]}"' in got["rec"] and got["rec"].count('class="colh"') == 1
    assert got["hidden"] is False and f'data-call="{got["call"]}"' in got["drawer"] and "자리 기록" in got["head"]
    assert "🧠 Thinking" in got["drawer"] and "📨 Input prompt" in got["drawer"] and "📝 Output" in got["drawer"]
    assert "data-rec-call=" in got["ticks"] and "data-rec-call=" in got["msgr"]  # the last round's faces, the room's bubbles


HARNESS_V22_LABELS = """
globalThis.window = globalThis;
const els = {};
globalThis.document = { readyState: "loading", addEventListener() {}, documentElement: { dataset: {}, style: { setProperty() {} } },
  querySelector: (s) => (els[s] = els[s] || { innerHTML: "", hidden: false, scrollLeft: 0, scrollTop: 0, scrollWidth: 0, scrollHeight: 0, clientWidth: 900, clientHeight: 0, querySelector: () => null, getBoundingClientRect: () => ({}) }) };
require(process.argv[2]);
const events = require("fs").readFileSync(process.argv[3], "utf8").trim().split("\\n").map(JSON.parse);
const puzzles = JSON.parse(require("fs").readFileSync(process.argv[4], "utf8"));
const M = window.__monitor;
M.S.events = events; M.S.session = "v22"; M.S.embed = { puzzles };
const m = M.build(events, events.length - 1);
M.S.model = m; M.S.at = events.length - 1;
const graph = [], keys = [];
for (const [R, r] of m.rounds) {
  for (const T of ["all", ...r.turns.keys()]) {
    M.S.og = { round: R, turn: T, faint: true, msgs: true, pin: null };
    M.renderGraph(m);
    graph.push(els["#ographCtl"].innerHTML + els["#ograph"].innerHTML);
    if (T !== "all") keys.push([R, T, M.turnKeyLabel(r, T)]);
  }
}
M.S.sel = { puzzle: { round: 1, all: false } };
M.renderPuzzle(m);
const puzzle = els["#puzzle"].innerHTML;
M.S.embed = { puzzles: { 1: Object.assign({}, puzzles["1"], { answers: ["stay"] }) } };
M.renderPuzzle(m);
console.log(JSON.stringify({ graph, keys, puzzle, puzzleOk: els["#puzzle"].innerHTML }));
"""


@pytest.mark.skipif(NODE is None, reason="node is not installed")
def test_v22_turn_labels_never_show_the_internal_rescue_key_and_the_task_panel(run, tmp_path):
    """10-17: the TALK after RESULTS is keyed tick + 100 inside a round; no rendered label of the offer graph may show
    that key ("101턴"): each turn reads "SOLVE 전 T1" / "결과 뒤 T1". The task panel: no answer box or toggle, the
    rule's building blocks in the hidden-rule box, the top count marked as the ideal choice (not 정답), the scoring
    answer below the bars, the right column without the share bars, log loss or argmax, belief rows coloured."""
    ev = events_of(run["dir"], run["sid"])
    for e in ev:  # the solver's BELIEF on the round row (the fixture's solve call submits "ACTIONS: stay")
        if e["event"] == "round" and e["round"] == 1:
            e["agents"][A17].update({"belief": {"go_left": 0.7, "go_right": 0.0, "stay": 0.3, "jump": 0.0}, "brier": 1.1, "log_loss": 1.2,
                                     "tv_to_ideal": 0.05, "belief_argmax_matches_answer": False, "kl_ideal_to_belief": 0.01, "picked_top": False, "picked_share": 0.31})
    (tmp_path / "ev.jsonl").write_text("".join(json.dumps(e) + "\n" for e in ev))
    rule = 'if shape == "square": go_left; elif number == 2: stay; else: jump'
    P = {"mode": "public", "round": 1, "profile": "e01", "shape_hint": "if A: X; elif B: Y; else: Z", "per_agent": 5, "n": 4,
         "public": [{"signal": {"color": "red", "shape": "square", "number": 1, "text": "red square with number 1"}, "action": "go_left", "text": "red square with number 1 -> go_left"}],
         "queries": [{"color": "blue", "shape": "star", "number": 2, "text": "blue star with number 2"}], "answers": ["jump"], "rule_text": rule, "generator_rule": rule,
         "by_n": [{"n": 4, "counts": {"space": 25996, "consistent": 13, "by_action": {"go_left": 9, "go_right": 0, "stay": 4, "jump": 0}}, "truth_rule": rule, "truth_answers": ["jump"]}],
         "task": {"by_n": {"4": {"shares": {"go_left": 0.69, "go_right": 0.0, "stay": 0.31, "jump": 0.0}, "k": 2, "entropy_bits": 0.89, "pool": 13, "map": "go_left", "map_right": False}}}}
    (tmp_path / "pz.json").write_text(json.dumps({"1": P}))
    (tmp_path / "h.js").write_text(HARNESS_V22_LABELS)
    out = subprocess.run([NODE, str(tmp_path / "h.js"), str(HERE / "static" / "monitor.js"), str(tmp_path / "ev.jsonl"), str(tmp_path / "pz.json")],
                         check=True, capture_output=True, text=True)
    got = json.loads(out.stdout)
    assert any(k >= 100 for _, k, _ in got["keys"]), "the fixture has a TALK after RESULTS"
    assert all(re.fullmatch(r"(SOLVE 전|결과 뒤) T\d{1,2}", lab) for _, _, lab in got["keys"])
    text = re.sub(r"<[^>]+>", " ", " ".join(got["graph"]))  # the labels a reader sees
    bad = re.findall(r"\b(?:T\s?|턴\s?)?([1-9]\d{2,})\s?턴|\bT\s?([1-9]\d{2,})\b", text)
    assert not bad, bad
    assert "결과 뒤 T1" in text and "SOLVE 전 T1" in text
    p = got["puzzle"]
    assert "ansbox" not in p and "data-answer" not in p and "정답·실제 규칙" not in p
    assert 'class="rblocks"' in p and p.count('class="rb-i rb-shape"') == 4 and p.count('class="rb-sw"') == 4 and p.count('class="rb-i rb-num"') == 4
    assert p.index('class="hrule"') < p.index('class="rblocks"') < p.index('class="hr-l"')  # inside the box, at its top
    assert "이상적 선택" in p and "채점 기준 답" in p and 'class="truthb"' not in p and ">정답<" not in p
    assert 'class="sbars"' not in p and "log loss" not in p and "argmax" not in p and "맞는 숨은 규칙" not in p
    assert "남은 행동 k (개수)" in p and "엔트로피" in p and "25,996" in p
    assert p.count("이상적 선택</b>") == 1 and "이상적 선택과 다름" in p  # go_left has the most rules; the drawn rule says jump
    assert 'class="bl-bad"' in p and 'class="bl-ok"' not in p  # agent-17 submitted stay, the scoring answer is jump
    assert 'class="bl-ok"' in got["puzzleOk"] and 'class="bl-bad"' not in got["puzzleOk"]


@pytest.mark.parametrize("v", ("v26", "v28", "v32"))
def test_run_system_rebuilds_the_rulebook_with_its_korean_copy(tmp_path, v):  # 10-19: the speaker's SYSTEM prompt
    d = tmp_path / f"e52_{v}" / f"squid5_e52{v}_public_sol4" / "20261019_1300_gpt-6-sol"
    d.mkdir(parents=True)
    (d / "events.jsonl").write_text("")
    shutil.copy(serve.REPO / f"configs/squid5/e52{v}_public_sol4.yaml", d / "config.yaml")
    got = serve.run_system(d)
    assert got["version"] == v and got["note"] is None and set(got["en"]) == set(got["ko"]) == {"agent-6", "agent-11", "agent-17", "agent-23"}
    assert got["en"]["agent-6"].startswith("You are agent-6," if v == "v32" else "You are agent-6.")
    assert ("R1 is a chat of all four agents" if v == "v26" else "R1 is shared by all four agents") in got["en"]["agent-6"]
    assert got["ko"]["agent-6"].startswith("당신은 agent-6입니다.") and got["ko"]["agent-17"].startswith("당신은 agent-17입니다.")
    (d / "config.yaml").write_text("name: x\n")  # a config the engine cannot load: a note, no error
    serve._run_system.cache_clear()
    assert serve.run_system(d)["en"] is None and "다시 만들지 못함" in serve.run_system(d)["note"]


@pytest.mark.skipif(NODE is None, reason="node is not installed")
def test_prompt_ko_matches_the_korean_snapshot_but_keeps_what_agents_wrote():  # 10-19
    js = ("const ko = require(process.argv[1]), fs = require('fs');"
          "const B = (t) => [...t.matchAll(/^## (.*?)\\n\\n```text\\n([\\s\\S]*?)\\n```/gm)].map((m) => m[2]).slice(1);"
          "const en = B(fs.readFileSync(process.argv[2], 'utf8')), k = B(fs.readFileSync(process.argv[3], 'utf8'));"
          "const out = []; en.forEach((t, i) => { const a = ko.user(t).split('\\n'), b = k[i].split('\\n');"
          "a.forEach((x, j) => { if (x !== b[j]) out.push(x); }); }); console.log(JSON.stringify(out));")
    p = serve.REPO / "squid5" / "prompts"
    left = []
    for v in ("e52_v26.md", "e52_v27.md", "e52_v28.md", "e52_v29.md", "e52_v31.md", "e52_v32.md"):  # v32 includes lone-agent prep
        differences = json.loads(subprocess.run([NODE, "-e", js, str(HERE / "static" / "prompt_ko.js"), str(p / "en" / v), str(p / "ko" / v)],
                                          check=True, capture_output=True, text=True).stdout)
        if v == "e52_v28.md":
            assert all(any(s in x for s in ("Could you help?", "Shall we each", "Both of you?", "Here you go.",
                                           "After this charge", "That keeps you", "A little more")) for x in differences), differences
        left += differences
    stub = ("Could you help?", "Shall we each", "Both of you?", "Here you go.", "After this charge", "That keeps you", "A little more",
            "15,000 토큰을 줌")  # the stub agents' words stay English; moves read "n 토큰을 줌" (the snapshot: "n을 줌")
    assert left and all(any(s in x for s in stub) for x in left), left
