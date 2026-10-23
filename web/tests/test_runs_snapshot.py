"""web/tools/runs_snapshot.py: add packs events.jsonl, skips _* attempts and runs already there; unpack restores bytes."""

import importlib.util
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "tools" / "runs_snapshot.py"
spec = importlib.util.spec_from_file_location("runs_snapshot", SCRIPT)
rs = importlib.util.module_from_spec(spec)
spec.loader.exec_module(rs)


def make_run(d: Path, events: bytes) -> None:
    d.mkdir(parents=True)
    (d / "events.jsonl").write_bytes(events)
    (d / "config.yaml").write_text("game: {}\n")
    (d / "meta.json").write_text("{}")
    (d / "results.jsonl").write_text("{}\n")
    (d / "stdout.log").write_text("not shipped")


def test_add_then_unpack_round_trip(tmp_path):
    root, snap = tmp_path / "runs", tmp_path / "snap"
    events = b"".join(b'{"event": "call", "user": "%s"}\n' % (b"same prompt " * 50 + str(i).encode()) for i in range(300))
    make_run(root / "e52_v99" / "cfg_a" / "20261020_0000_m", events)
    make_run(root / "e52_v99" / "_failed" / "cfg_b", b"{}\n")
    make_run(root / "e52_v99" / "cfg_c" / "_stopped" / "x", b"{}\n")

    added = rs.add(["e52_v99"], root, snap, workers=1)
    assert added == ["e52_v99/cfg_a/20261020_0000_m"]
    dest = snap / added[0]
    assert sorted(p.name for p in dest.iterdir()) == ["config.yaml", "events.jsonl.xz", "meta.json", "results.jsonl"]
    assert (dest / "events.jsonl.xz").stat().st_size < len(events) / 10

    assert rs.add(["e52_v99"], root, snap, workers=1) == []  # already there: left alone

    assert rs.unpack(snap) == 1
    assert (dest / "events.jsonl").read_bytes() == events
    assert not list(snap.rglob("*.xz"))
    assert rs.add(["e52_v99"], root, snap, workers=1) == []  # unpacked counts as there too
