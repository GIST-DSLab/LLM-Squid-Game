"""The game-log viewer (tools/monitor) served by the web app under /monitor: page, code, API over the default root
(the parent of the live runs root), the arena state's deep link, and paths outside the root."""

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from conftest import answers_for, done, make_room, play, start
from web.server.app import make_app
from web.server.store import Store
from squid5.core.rules import TEAM_AGENTS

A17 = TEAM_AGENTS[2]


def test_page_and_code(client):
    r = client.get("/monitor/")
    assert r.status_code == 200 and "ARENA&nbsp;MONITOR" in r.text and 'src="static/monitor.js"' in r.text
    assert 'href="../arena.html"' in r.text  # the way back to the site
    assert client.get("/monitor", follow_redirects=False).headers["location"].endswith("monitor/")
    js = client.get("/monitor/static/monitor.js")
    assert js.status_code == 200 and 'getJSON("api/runs")' in js.text  # relative: works here and standalone
    assert client.get("/monitor/static/nope.js").status_code == 404
    cmp = client.get("/monitor/compare.html")  # 모델 비교 page, its code, its (empty) data and CSV
    assert cmp.status_code == 200 and "static/compare.js" in cmp.text
    assert client.get("/monitor/static/compare.js").status_code == 200
    assert client.get("/monitor/api/compare", params={"runs": "nope/"}).json()["models"] == []
    csv = client.get("/monitor/api/compare.csv", params={"runs": "nope/", "chart": "summary"})
    assert csv.status_code == 200 and csv.text.lstrip("\ufeff").startswith("model,games")
    assert client.get("/monitor/api/compare.csv", params={"runs": "nope/", "chart": "x"}).status_code == 400
    sig = client.get("/monitor/static/signal_ui.js")  # the arena's task drawing, shared with the viewer (one file)
    assert sig.status_code == 200 and sig.text == client.get("/signal_ui.js").text and "byActionHTML" in sig.text
    assert client.get("/monitor/assets/nope.png").status_code == 404  # no sprites: the page falls back silently
    assert client.get("/api/health").status_code == 200  # the arena's own /api is untouched
    for page in ("index.html", "probe.html", "arena.html", "signal.html", "leaderboard.html"):
        text = client.get(f"/{page}").text
        assert 'data-api-href="monitor/"' in text and 'href="leaderboard.html"' in text, page
    lb = client.get("/api/leaderboard", params={"runs": "nope/"})
    assert lb.status_code == 200 and lb.json()["rows"] == [] and "자가 대국" in lb.json()["note"]
    assert client.get("/api/leaderboard", params={"runs": "nope/", "csv": 1}).text.lstrip("\ufeff").startswith("rank,model")


def test_api_reads_a_finished_room(client, runs_root):
    ps = make_room(client, 1, rounds=2, seed=5)
    start(client, ps)
    s = play(ps, lambda p, pend: done(f"TO {A17}: hi") if pend["kind"] == "talk" else {"actions": answers_for(5, pend["round"])})
    assert s["status"] == "finished", s["error"]
    rel = f"{runs_root.name}/{Path(s['run_dir']).name}"
    sid = f"web-{ps[0].code}-s5"
    assert s["monitor"] == {"run": rel, "session": sid}  # the end screen's deep link
    runs = client.get("/monitor/api/runs").json()
    assert [r["run"] for r in runs["runs"]] == [rel] and runs["runs"][0]["done"]
    ses = client.get("/monitor/api/sessions", params={"run": rel}).json()["sessions"]
    assert [x["id"] for x in ses] == [sid] and ses[0]["rounds_done"] == 2
    ev = client.get("/monitor/api/events", params={"run": rel, "session": sid, "offset": 0}).json()
    assert ev["events"][0]["event"] == "session_start" and ev["result"]["rounds_played"] == 2
    pz = client.get("/monitor/api/puzzle", params={"run": rel, "session": sid, "round": 1}).json()
    assert pz["answers"] == answers_for(5, 1)
    assert client.get("/monitor/api/events", params={"run": rel}).status_code == 400  # session is required
    assert client.get("/monitor/api/events", params={"run": rel, "session": sid, "offset": "x"}).status_code == 400
    assert client.get("/monitor/api/puzzle", params={"run": rel, "session": "nope", "round": 1}).status_code == 404


def test_paths_outside_the_root_are_refused(tmp_path):
    root = tmp_path / "root"
    (root / "a").mkdir(parents=True)
    (tmp_path / "secret").mkdir()
    (tmp_path / "secret" / "events.jsonl").write_text("")
    with TestClient(make_app(Store(tmp_path / "a.db"), export_root=tmp_path / "x", runs_root=tmp_path / "live",
                             monitor_root=root)) as c:
        assert c.get("/monitor/api/runs").json() == {"root": str(root.resolve()), "runs": []}
        for bad in ("../secret", "a/../../secret", "/../secret", "%2e%2e/secret"):
            r = c.get("/monitor/api/sessions", params={"run": bad})
            assert r.status_code == 400 and "error" in r.json(), bad
        assert c.get("/monitor/api/sessions", params={"run": "a"}).status_code == 400  # no events.jsonl there
        assert c.get("/monitor/static/..%2F..%2Fserve.py").status_code in (400, 404)
