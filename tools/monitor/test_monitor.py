"""The arena monitor over a synthetic 5.2 v9-talk run: the API (runs, sessions, incremental events, path checks, the
rebuilt round task), the self-contained export, and the page code (syntax, and its offer-book replay against the
engine's own records).

    python3 -m pytest -q tools/monitor
"""

from __future__ import annotations

import http.client
import json
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
from squid5.core.puzzle import Spec, candidate_actions, deal, puzzle_for  # noqa: E402
from test_e52 import ROW, game, script  # noqa: E402

A6, A11, A17, A23 = rules.TEAM_AGENTS
TRICKY = "meet me </script><!-- at turn 2"  # must survive the export's <script> embedding
RUN_REL = "e52_test/run_a"


def play(run_dir: Path, seed: int, lines: dict, rounds: int = 2, start: int = 5000, **kw) -> dict:
    """One session written the way the runner writes it: events appended, the result line at the end."""
    s = e52.Settings(**{"rounds": rounds, "schedule": ["p"] * rounds, "profiles": {"p": Spec(clauses=2)},
                        "table": {"p": ROW}, "solve_cap": 900, "prize": 100, "upkeep": 50, "charge": 200, **kw})
    ev = run_dir / "events.jsonl"

    def emit(row: dict) -> None:
        with ev.open("a") as f:
            f.write(json.dumps(row, ensure_ascii=False, default=str) + "\n")

    sid = f"talk-s{seed}-abc123"
    res = e52.Session(s, Cell("talk", "tokens", start, arm="shutdown"), seed, game(script(lines), seed=seed), emit,
                      sid).run()
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
    assert ["1.1", "the offer is done"] in got["accepts"] and "it is a jump" not in got["messages"]
    js = (HERE / "static" / "monitor.js").read_text()
    assert "p.blocked" in js and "exit_reason" in js and "allow_pass === false" in js and "g.secrets" in js
