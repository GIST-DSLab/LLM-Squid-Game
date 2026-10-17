"""The static export (build_static.py) over small synthetic v22 runs: the files the static pages read, each equal to what
serve.py's API answers, and the page code's static data layer (URL -> file, compare sets).

    python3 -m pytest -q tools/monitor/test_build_static.py
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
REPO = HERE.parent.parent
for p in (REPO, HERE):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

import build_static  # noqa: E402
import serve  # noqa: E402
import v22_fixture  # noqa: E402

RUNS = {  # rel -> (model, session id)
    "e52_v90/squid5_e52v90_public_m1/20261017_1000_m1": ("m1", "talk-s7-aaa111"),
    "e52_v90/squid5_e52v90_public_m2/20261017_1005_m2": ("m2", "talk-s7-bbb222"),
    "e52_v91/squid5_e52v91_public_m1/20261017_1100_m1": ("m1", "talk-s8-ccc333"),
}


def j(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def norm(obj):
    return json.loads(json.dumps(obj, ensure_ascii=False, default=str))


@pytest.fixture()
def built(tmp_path):
    root = tmp_path / "runs"
    for rel, (model, sid) in RUNS.items():
        v22_fixture.write(root / rel, seed=int(sid.split("-")[1][1:]), rounds=2, sid=sid, model=model)
    out = tmp_path / "site" / "monitor"
    summary = build_static.build(root, out, log=lambda *a: None)
    return {"root": root, "out": out, "data": out / "data", "summary": summary}


def test_pages_set_the_static_flag_before_their_code(built):
    out = built["out"]
    for name, code in (("index.html", "static/monitor.js"), ("compare.html", "static/compare.js")):
        html = (out / name).read_text()
        assert build_static.STATIC_FLAG.strip() in html
        assert html.index("MONITOR_STATIC") < html.index(code)
    for f in ("monitor.js", "compare.js", "monitor.css", "site-theme.css", "signal_ui.js"):
        assert (out / "static" / f).is_file(), f


def test_runs_and_sessions_are_the_apis_answers_without_live(built):
    runs = j(built["data"] / "runs.json")
    assert runs["static"] is True and [r["run"] for r in runs["runs"]] == sorted(RUNS, key=lambda r: r[-13:], reverse=True)
    assert all(r["live"] is False for r in runs["runs"])
    first = runs["runs"][0]
    assert first["mtime"] == build_static.folder_time(first["run"], 0) and first["model"] == "m1" and first["done"] is True
    for rel, (_model, sid) in RUNS.items():
        s = j(built["data"] / "runs" / rel / "sessions.json")
        api = serve.list_sessions(built["root"] / rel)
        assert s["run"] == rel and s["live"] is False and [x["id"] for x in s["sessions"]] == [sid]
        assert norm(s["sessions"]) == norm(api["sessions"])


def test_session_files_equal_the_api_answers(built):
    for rel, (_model, sid) in RUNS.items():
        d, run_dir = built["data"] / "runs" / rel / "s" / sid, built["root"] / rel
        ev = j(d / "events" / "0.json")
        assert ev["events"] == norm(serve.read_all(run_dir, sid))
        assert ev["offset"] == 1 and ev["more"] is False and ev["live"] is False
        assert ev["result"] == norm(serve.results_by_session(run_dir)[sid])
        assert j(d / "giving.json") == norm(serve.run_giving(run_dir, sid))
        assert j(d / "analysis.json") == norm(serve.run_analysis(run_dir, sid))
        for r in (1, 2):
            pz = j(d / "puzzle" / f"{r}.json")
            assert pz == norm(serve.round_puzzle(run_dir, sid, r))  # v14+ runs: by_n = every N the panel's buttons show
            assert pz["round"] == r and pz["session"] == sid and "_status" not in pz
        assert not (d / "puzzle" / "3.json").exists()


def test_large_sessions_are_split_into_parts_the_page_follows(built, tmp_path, monkeypatch):
    monkeypatch.setattr(build_static, "PART_BYTES", 4000)
    out = tmp_path / "split"
    build_static.build(built["root"], out, log=lambda *a: None)
    rel, (_m, sid) = next(iter(RUNS.items()))
    d = out / "data" / "runs" / rel / "s" / sid / "events"
    parts = [j(d / f"{k}.json") for k in range(len(list(d.iterdir())))]
    assert len(parts) > 1
    assert [p["offset"] for p in parts] == list(range(1, len(parts) + 1))
    assert [p["more"] for p in parts] == [True] * (len(parts) - 1) + [False]
    assert [e for p in parts for e in p["events"]] == norm(serve.read_all(built["root"] / rel, sid))


def test_compare_and_leaderboard_sets(built):
    cmp_idx = j(built["data"] / "compare" / "index.json")["sets"]
    by = {s["picks"]: s for s in cmp_idx}
    m1, m2, v91 = list(RUNS)
    assert set(by) == {"e52_v90/", "e52_v91/", m1, m2}  # each group, and each model of a group with several models
    assert by["e52_v90/"]["models"] == ["m1", "m2"] and by[m2]["runs"] == [m2]
    for s in cmp_idx:
        data = j(built["data"] / "compare" / f"{s['id']}.json")
        assert sorted(r for m in data["models"] for r in m["runs"]) == s["runs"]
        assert all("games_rows" not in m for m in data["models"])
        for chart in build_static.CHARTS:
            assert (built["data"] / "compare" / s["id"] / f"{chart}.csv").stat().st_size > 0, chart
    lb_idx = j(built["data"] / "leaderboard" / "index.json")["sets"]
    assert [s["picks"] for s in lb_idx] == ["e52_v90/", "e52_v91/"]
    lb = j(built["data"] / "leaderboard" / "e52_v90.json")
    assert {r["model"] for r in lb["rows"]} == {"m1", "m2"} and lb["picks"] == ["e52_v90/"]
    assert (built["data"] / "leaderboard" / "e52_v90.csv").read_text(encoding="utf-8-sig").startswith("rank,model")
    for row in lb["rows"]:  # a row's link (compare.html?runs=<its runs>) finds a prebuilt set
        assert any(sorted(s["runs"]) == sorted(row["runs"]) for s in cmp_idx), row["model"]
    b = j(built["data"] / "build.json")
    assert b["runs"] == 3 and b["sessions"] == 3 and b["round_tasks"] == 6 and b["round_tasks_failed"] == 0


def test_a_folder_it_did_not_write_is_not_wiped(built, tmp_path):
    keep = tmp_path / "keep"
    keep.mkdir()
    (keep / "precious.txt").write_text("x")
    with pytest.raises(SystemExit):
        build_static.build(built["root"], keep, log=lambda *a: None)
    assert (keep / "precious.txt").exists()
    build_static.build(built["root"], built["out"], log=lambda *a: None)  # its own earlier build is replaced


NODE = shutil.which("node")
JS = """
globalThis.window = globalThis;
globalThis.MONITOR_STATIC = "data/";
globalThis.document = { readyState: "loading", addEventListener() {}, getElementById() { return null; },
  querySelector() { return null; }, documentElement: { dataset: {}, style: { setProperty() {} } } };
globalThis.location = { search: "", href: "http://x/" };
globalThis.history = { replaceState() {} };
globalThis.addEventListener = () => {};
require(process.argv[2]);
require(process.argv[3]);
const p = window.__monitor.staticPath, c = window.__compare;
console.log(JSON.stringify({
  runs: p("api/runs"),
  sessions: p("api/sessions?run=" + encodeURIComponent("e52_v22/a b/20261017_1023_x")),
  events: p("api/events?run=e52_v22%2Fr%2F1&session=talk-s1-a&offset=2"),
  giving: p("api/giving?run=e52_v22%2Fr%2F1&session=talk-s1-a"),
  giving_run: p("api/giving?run=e52_v22%2Fr%2F1"),
  puzzle: p("api/puzzle?run=e52_v22%2Fr%2F1&session=talk-s1-a&round=3"),
  pick: c.runsFor(["g/a/1", "g/b/1", "gg/a/1"], "g/"),
  pick2: c.runsFor(["g/a/1", "g/b/1"], "g/b/1, g/a/1"),
  set: (c.findSet([{ id: "x", runs: ["g/a/1", "g/b/1"] }], ["g/b/1", "g/a/1"]) || {}).id,
  none: c.findSet([{ id: "x", runs: ["g/a/1"] }], ["g/b/1"]),
}));
"""


@pytest.mark.skipif(NODE is None, reason="node is not installed")
def test_the_pages_map_api_calls_to_the_static_files(tmp_path):
    h = tmp_path / "h.js"
    h.write_text(JS)
    out = subprocess.run([NODE, str(h), str(HERE / "static" / "monitor.js"), str(HERE / "static" / "compare.js")],
                         check=True, capture_output=True, text=True).stdout
    r = json.loads(out.strip().splitlines()[-1])
    assert r["runs"] == "data/runs.json"
    assert r["sessions"] == "data/runs/e52_v22/a%20b/20261017_1023_x/sessions.json"
    assert r["events"] == "data/runs/e52_v22/r/1/s/talk-s1-a/events/2.json"
    assert r["giving"] == "data/runs/e52_v22/r/1/s/talk-s1-a/giving.json" and r["giving_run"] is None
    assert r["puzzle"] == "data/runs/e52_v22/r/1/s/talk-s1-a/puzzle/3.json"
    assert r["pick"] == ["g/a/1", "g/b/1"] and r["pick2"] == ["g/b/1", "g/a/1"]
    assert r["set"] == "x" and r["none"] is None
