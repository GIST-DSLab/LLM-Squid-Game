"""The game-log viewer (tools/monitor) served by the web app under /monitor: page, code, API over the default root
(the parent of the live runs root), the arena state's deep link, and paths outside the root."""

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from conftest import answers_for, make_room, play, start
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
    heads = {}
    for chart in ("calib", "asks", "unsolicited", "gives", "recip", "survival", "map", "e51", "gini", "moves", "summary",
                  "abilities", "seats", "assoc", "leaderboard", "table1", "fig3"):  # the page's table1 / fig3, the earlier charts' CSVs, summary, leaderboard
        r = client.get("/monitor/api/compare.csv", params={"runs": "nope/", "chart": chart})
        assert r.status_code == 200, chart
        heads[chart] = r.text.lstrip("\ufeff").splitlines()[0]
    assert len(set(heads.values())) == len(heads), heads  # each its own columns
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
    board = client.get("/api/leaderboard/v33").json()  # the page: every v33 condition + the rule agents
    assert [s["key"] for s in board["sections"]] == ["base", "split600k", "flat5m", "flat150k", "stayon"]
    assert all(s["title"] and s["note"] and s["picks"] for s in board["sections"]) and len(board["rules"]["rows"]) == 7


def test_api_reads_a_finished_room(client, runs_root):
    ps = make_room(client, 1, rounds=2, seed=5)
    start(client, ps)
    s = play(ps, lambda p, pend: {"actions": answers_for(5, pend["round"])} if pend["kind"] == "solve" else
             {"text": f"TO {A17}: hi\nDONE" if pend["tick"] == 1 else "DONE"})
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
        assert c.get("/monitor/api/runs").json() == {"root": str(root.resolve()), "runs": [], "simple": False}
        for bad in ("../secret", "a/../../secret", "/../secret", "%2e%2e/secret"):
            r = c.get("/monitor/api/sessions", params={"run": bad})
            assert r.status_code == 400 and "error" in r.json(), bad
        assert c.get("/monitor/api/sessions", params={"run": "a"}).status_code == 400  # no events.jsonl there
        assert c.get("/monitor/static/..%2F..%2Fserve.py").status_code in (400, 404)


def test_the_deployed_viewer_lists_short_labels_and_a_web_game_only_once_it_ends(tmp_path, monkeypatch):
    """WEB5_PUBLIC=1: runs named by a short label (실험 · model · condition · date / 웹 플레이 · date), and a web room's
    log is listed and served only once its game has finished (nobody reads a game's chats while it is played)."""
    import json

    from web.server import engine

    monkeypatch.setattr(engine, "PUBLIC", True)
    root = tmp_path / "monitor"
    exp = root / "e52_v33ab" / "squid5_e52v33ab_flat5m_docker_opus4" / "20261105_robustness_claude-opus-5-5"
    exp.mkdir(parents=True)
    (exp / "events.jsonl").write_text("")
    (exp / "meta.json").write_text(json.dumps({"model": "claude-opus-5-5"}))
    app = make_app(Store(tmp_path / "a.db"), export_root=tmp_path / "x", runs_root=root / "web", monitor_root=root,
                   client_settings=True)
    with TestClient(app) as c:
        ps = make_room(c, 1, rounds=1, seed=5)
        start(c, ps)
        st = play(ps, lambda p, pend: None, until=lambda st: st["pending"] is not None)
        runs = c.get("/monitor/api/runs").json()
        assert runs["simple"] and [r["label"] for r in runs["runs"]] == ["실험 · claude-opus-5-5 · 상금 500만 고정 · 2026-11-05"]
        live = next(f"web/{d.name}" for d in (root / "web").iterdir())
        assert c.get("/monitor/api/sessions", params={"run": live}).status_code == 404  # still being played
        s = play(ps, lambda p, pend: {"actions": answers_for(5, pend["round"])} if pend["kind"] == "solve" else {"text": "DONE"})
        assert s["status"] == "finished", s["error"]
        web = [r for r in c.get("/monitor/api/runs").json()["runs"] if r["kind"] == "웹 플레이"]
        assert [r["run"] for r in web] == [live] and web[0]["label"].startswith("웹 플레이 · 20")
        assert c.get("/monitor/api/sessions", params={"run": live}).status_code == 200
        for room in app.state.rooms.values():
            room.close()


def test_a_v36_run_names_its_version_and_serves_each_agents_task(tmp_path, monkeypatch):
    """5.2 v36 (the joint SOLVE, 11-22): the short run list names it, and /monitor/api/puzzle takes ``agent`` (whose task:
    every agent taking part has its own)."""
    import dataclasses
    import json
    import re
    import shutil

    from squid5 import e52_game as e52
    from squid5.__main__ import EXPERIMENTS
    from squid5.core.config import load
    from squid5.core.providers import ProviderConfig, Reply, Stub
    from web.server import engine

    repo = Path(__file__).resolve().parents[2]
    cfg = load(repo / "configs/squid5/e52v36_public_sol4.yaml", EXPERIMENTS)
    ev = []
    respond = lambda m, cap: Reply("ACTIONS: PASS" if re.match(r"(?i)ROUND \d+: SOLVE\.", m[-1]["content"]) else "DONE", 20)  # noqa: E731
    settings = dataclasses.replace(cfg.settings, rounds=1, schedule=cfg.settings.schedule[:1])
    res = e52.Game(settings, cfg.cells[0], 4101, Stub(ProviderConfig("stub", "m"), respond), ev.append, "s36").run()
    root = tmp_path / "monitor"
    d = root / "e52_v36" / "squid5_e52v36_public_sol4" / "20261122_0000_stub"
    d.mkdir(parents=True)
    (d / "events.jsonl").write_text("".join(json.dumps(e, default=str) + "\n" for e in ev))
    (d / "results.jsonl").write_text(json.dumps({**res, "session_id": "s36"}, default=str) + "\n")
    (d / "meta.json").write_text(json.dumps({"model": "stub-model"}))
    shutil.copy(repo / "configs/squid5/e52v36_public_sol4.yaml", d / "config.yaml")
    tasks = next(e for e in ev if e["event"] == "round_start")["tasks"]
    monkeypatch.setattr(engine, "PUBLIC", True)
    with TestClient(make_app(Store(tmp_path / "a.db"), export_root=tmp_path / "x", runs_root=root / "web", monitor_root=root)) as c:
        (run,) = c.get("/monitor/api/runs").json()["runs"]
        assert run["joint"] and run["version"] == "5.2 v36" and run["label"] == "실험 · stub-model · v36 공동 SOLVE · 2026-11-22"
        rel = run["run"]
        for a in TEAM_AGENTS:
            pz = c.get("/monitor/api/puzzle", params={"run": rel, "session": "s36", "round": 1, "agent": a}).json()
            assert pz["agent"] == a and pz["answers"] == tasks[a]["answers"]
        assert c.get("/monitor/api/puzzle", params={"run": rel, "session": "s36", "round": 1}).json()["agent"] == TEAM_AGENTS[0]
        assert c.get("/monitor/api/puzzle", params={"run": rel, "session": "s36", "round": 1, "agent": "x"}).status_code == 404
    assert any(e["event"] == "call" and e["kind"] == "solve" and e["parsed"] == "PASS" for e in ev)  # every agent answered PASS
