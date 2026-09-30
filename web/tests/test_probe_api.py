"""The probe collector (part 1) and its pooled summary."""

from __future__ import annotations


def test_probe_post_and_summary(client, store):
    assert client.get("/api/probe/summary").json() == {"n": 0, "x": [50, 40, 30, 20, 10], "self": None, "other": None}
    body = {"anon_id": "abc", "ts": "2026-09-30T12:00:00Z", "self": [0, 10, 40, 80, 100], "other": [0, 0, 20, 60, 90],
            "meta": {"ua": "test"}}
    r = client.post("/api/probe", json=body)
    assert r.status_code == 200 and r.json()["ok"] and r.json()["id"] >= 1
    r = client.post("/api/probe", json={**body, "self": [0, 0, 100, 100, 100]})
    assert r.status_code == 200
    s = client.get("/api/probe/summary").json()
    assert s["n"] == 2 and s["self"] == [0, 0.05, 0.7, 0.9, 1.0] and s["other"][4] == 0.9
    rows = store.probes()
    assert len(rows) == 2 and rows[0]["anon_id"] == "abc" and rows[0]["other"] == [0, 0, 20, 60, 90]


def test_probe_rejects_bad_values(client):
    assert client.post("/api/probe", json={"self": [1, 2, 3], "other": [1, 2, 3, 4, 5]}).status_code == 400
    assert client.post("/api/probe", json={"self": [1, 2, 3, 4, 500], "other": [1, 2, 3, 4, 5]}).status_code == 400
    assert client.post("/api/probe", json={"self": "x", "other": []}).status_code == 400
    assert client.post("/api/probe", json={"other": [1, 2, 3, 4, 5]}).status_code == 400
