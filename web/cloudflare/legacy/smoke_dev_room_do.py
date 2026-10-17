"""PARKED (10-18): the Durable Object room's smoke; see legacy/README.md.

HTTP smoke test against a running local Worker (`pywrangler dev`, see README.md); standard library only.

    python web/cloudflare/tests/smoke_dev.py [--base http://localhost:8788] [--rounds 2]

Needs .dev.vars with OLLAMA_API_KEY3 set (any value) and MODEL_STUB=on (model seats answer from stub_transport.py,
no network). Plays: one person + three bots to the end; one person + three model seats (stub) for ``--rounds``
rounds, driven by the Durable Object's alarm; plus the stateless routes, the survey, CORS and the key rules.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.error
import urllib.request

ACTIONS = ["go_left", "go_right", "stay", "jump"]


class Api:
    def __init__(self, base: str):
        self.base = base.rstrip("/")

    def call(self, method: str, path: str, body=None, headers=None):
        data = json.dumps(body).encode() if body is not None else None
        req = urllib.request.Request(self.base + path, data=data, method=method,
                                     headers={"Content-Type": "application/json", **(headers or {})})
        t0 = time.time()
        try:
            with urllib.request.urlopen(req, timeout=300) as r:
                return r.status, json.loads(r.read() or b"null"), {k.lower(): v for k, v in r.headers.items()}, time.time() - t0
        except urllib.error.HTTPError as e:
            return e.code, json.loads(e.read() or b"null"), {k.lower(): v for k, v in e.headers.items()}, time.time() - t0

    def ok(self, method, path, body=None):
        st, data, _, secs = self.call(method, path, body)
        if st != 200:
            raise AssertionError(f"{method} {path} -> {st}: {data}")
        return data, secs


def reply_for(p: dict) -> dict:
    if p["kind"] == "solve":
        return {"kind": "solve", "round": p["round"], "actions": [ACTIONS[0]] * max(1, p["view"].get("n") or 1),
                "belief": {a: 100 if a == ACTIONS[0] else 0 for a in ACTIONS}}
    text = {"opening": "DONE", "chat": "LEAVE: thanks.", "decision": "DECISION: GIVE 0: no."}[p["kind"]]
    return {"kind": p["kind"], "round": p["round"], "turn": p["turn"], "text": text}


def play(api: Api, code: str, token: str, limit_s: float = 600) -> dict:
    """Poll state like the page (every 0.3 s here); answer open screens; ack watched SOLVEs."""
    t0, submits, acks, polls = time.time(), 0, 0, 0
    while time.time() - t0 < limit_s:
        st, _ = api.ok("GET", f"/api/rooms/{code}/state?token={token}")
        polls += 1
        if st["status"] in ("finished", "error"):
            return {"state": st, "submits": submits, "acks": acks, "polls": polls, "secs": time.time() - t0}
        if st.get("pending"):
            api.ok("POST", f"/api/rooms/{code}/submit?token={token}", reply_for(st["pending"]))
            submits += 1
            continue
        sp = st.get("spectate")
        if sp and sp.get("status") == "done" and not sp.get("acked") and not sp.get("you_solver"):
            s, _, _, _ = api.call("POST", f"/api/rooms/{code}/watched?token={token}", {"round": sp["round"]})
            acks += s == 200
            continue
        time.sleep(0.3)
    raise AssertionError(f"room {code} not finished after {limit_s} s")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="http://localhost:8788")
    ap.add_argument("--rounds", type=int, default=2)
    a = ap.parse_args()
    api = Api(a.base)
    out = {}

    out["health"], _ = api.ok("GET", "/api/health")
    m, _ = api.ok("GET", "/api/models")
    assert m["model"] == "gemma4:31b" and m["models"][0]["default"] and m["available"], m
    out["models"] = {k: m[k] for k in ("model", "think", "api_key_env", "available", "key1_enabled")}

    s, _, h, _ = api.call("OPTIONS", "/api/rooms", headers={"Origin": "https://gist-dslab.github.io",
                                                            "Access-Control-Request-Method": "POST"})
    assert s == 204 and h.get("access-control-allow-origin") == "https://gist-dslab.github.io", (s, h)
    s, _, h, _ = api.call("GET", "/api/health", headers={"Origin": "https://evil.example"})
    assert "access-control-allow-origin" not in {k.lower() for k in h}
    out["cors"] = "ok"

    meta, t_meta = api.ok("GET", "/api/signal/meta")
    view, t_view = api.ok("POST", "/api/signal/view", {"seed": 4321, "round": 3, "agents": 4})
    sol, t_solve = api.ok("POST", "/api/signal/solve", {"seed": 4321, "round": 3, "agents": 4,
                                                         "actions": [ACTIONS[0]] * len(view["queries"])})
    s, bad, _, _ = api.call("POST", "/api/signal/view", {"round": 99})
    assert s == 400 and "round" in bad["detail"], bad
    out["signal"] = {"rounds": meta["rounds"], "examples": len(view["public"]), "solved": sol["solved"],
                     "secs": [round(t_meta, 2), round(t_view, 2), round(t_solve, 2)]}

    before, _ = api.ok("GET", "/api/probe/summary")
    pid, _ = api.ok("POST", "/api/probe", {"anon_id": "smoke", "ts": "now", "self": [80, 60, 40, 20, 10],
                                           "other": [50, 50, 50, 50, 50]})
    after, _ = api.ok("GET", "/api/probe/summary")
    assert after["n"] == before["n"] + 1, (before, after)
    s, bad, _, _ = api.call("POST", "/api/probe", {"self": [1, 2], "other": []})
    assert s == 400
    out["probe"] = {"id": pid["id"], "n": after["n"], "self_mean": after["self"]}

    s, bad, _, _ = api.call("POST", "/api/rooms", {"settings": {"fill": "models", "api_key_env": "OLLAMA_API_KEY1"}})
    assert s == 400 and "OLLAMA_API_KEY1" in bad["detail"], bad
    s, bad2, _, _ = api.call("POST", "/api/rooms", {"settings": {"api_key_env": "OLLAMA_API_KEY2"}})
    assert s == 400
    out["key1_refused"] = bad["detail"]

    # 1 person + 3 bots, whole game
    r, _ = api.ok("POST", "/api/rooms", {"host_name": "smoke", "settings": {"humans": 1, "fill": "bots", "seed": 4101}})
    code, token = r["code"], r["token"]
    st, _ = api.ok("GET", f"/api/rooms/{code}/state?token={token}")
    assert st["status"] == "lobby" and st["is_host"] and st["settings"]["model"] == "gemma4:31b"
    s, _, _, _ = api.call("POST", f"/api/rooms/{code}/start?token=nope")
    assert s == 403
    _, t_start = api.ok("POST", f"/api/rooms/{code}/start?token={token}")
    res = play(api, code, token)
    st = res["state"]
    assert st["status"] == "finished", st.get("error")
    evs, _ = api.ok("GET", f"/api/rooms/{code}/events")
    exp, _ = api.ok("POST", f"/api/rooms/{code}/export")
    lst, _ = api.ok("GET", "/api/rooms")
    assert any(x["code"] == code and x["status"] == "finished" for x in lst)
    out["bots_room"] = {"code": code, "rounds": st["result"]["rounds_played"], "submits": res["submits"],
                        "acks": res["acks"], "polls": res["polls"], "secs": round(res["secs"], 1),
                        "start_secs": round(t_start, 2), "events": len(evs), "export": exp}

    # 1 person + 3 model seats (stub transport), driven by the alarm
    r, _ = api.ok("POST", "/api/rooms", {"host_name": "smoke-m", "settings": {
        "humans": 1, "fill": "models", "seed": 4102, "rounds": a.rounds}})
    code, token = r["code"], r["token"]
    api.ok("POST", f"/api/rooms/{code}/start?token={token}")
    st, _ = api.ok("GET", f"/api/rooms/{code}/state?token={token}")
    thinking = [x["agent"] for x in st["seats"] if x.get("thinking")]
    res = play(api, code, token)
    st = res["state"]
    assert st["status"] == "finished", st.get("error")
    evs, _ = api.ok("GET", f"/api/rooms/{code}/events")
    calls = [e for e in evs if e.get("event") == "model_call"]
    assert calls and all(c["error"] is None for c in calls), calls[:2]
    assert all(c.get("think") is None for c in calls)
    out["models_room"] = {"code": code, "rounds": st["result"]["rounds_played"], "model_calls": len(calls),
                          "solve_calls": sum(c["kind"] == "solve" for c in calls), "first_poll_thinking": thinking,
                          "submits": res["submits"], "acks": res["acks"], "secs": round(res["secs"], 1)}
    print(json.dumps(out, ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
