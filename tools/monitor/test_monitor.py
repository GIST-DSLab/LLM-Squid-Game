"""The arena monitor over a synthetic 5.2 v9-talk run: the API (runs, sessions, incremental events, path checks), the
self-contained export, and the page code (syntax, and its offer-book replay against the engine's own records).

    python3 -m pytest -q tools/monitor
"""

from __future__ import annotations

import http.client
import json
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
from squid5.core.puzzle import Spec  # noqa: E402
from test_e52 import ROW, game, script  # noqa: E402

A6, A11, A17, A23 = rules.TEAM_AGENTS
TRICKY = "meet me </script><!-- at turn 2"  # must survive the export's <script> embedding
RUN_REL = "e52_test/run_a"


def play(run_dir: Path, seed: int, lines: dict, rounds: int = 2, start: int = 5000) -> dict:
    """One session written the way the runner writes it: events appended, the result line at the end."""
    s = e52.Settings(rounds=rounds, schedule=["p"] * rounds, profiles={"p": Spec(clauses=2)}, table={"p": ROW},
                     solve_cap=900, prize=100, upkeep=50, charge=200)
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
    (d / "config.yaml").write_text("name: t\nmode: game\nreps: 1\nseed0: 7\ncells:\n- cell_id: talk\n  start: 5000\n")
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
    assert "function build(" in code[0]["text"]


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
