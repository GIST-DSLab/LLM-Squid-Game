"""Event store: SQLite (``outputs/web5/arena.db`` by default) or Postgres when ``WEB5_DSN`` is set.

Every engine event of a room is appended in the same shape as ``events.jsonl`` (one JSON document per row, in order),
so a room can be exported as a squid5 run directory later. Probe answers (part 1) go to their own table.
"""

from __future__ import annotations

import json
import os
import sqlite3
import threading
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
DEFAULT_DB = REPO / "outputs" / "web5" / "arena.db"

SCHEMA = [
    "CREATE TABLE IF NOT EXISTS rooms (code TEXT PRIMARY KEY, created_at REAL, settings TEXT, seats TEXT, status TEXT)",
    "CREATE TABLE IF NOT EXISTS events (id INTEGER PRIMARY KEY AUTOINCREMENT, code TEXT, seq INTEGER, ts REAL, "
    "kind TEXT, body TEXT)",
    "CREATE INDEX IF NOT EXISTS events_code ON events (code, seq)",
    "CREATE TABLE IF NOT EXISTS probes (id INTEGER PRIMARY KEY AUTOINCREMENT, ts REAL, anon_id TEXT, client_ts TEXT, "
    "self_vals TEXT, other_vals TEXT, meta TEXT)",
]


class Store:
    def __init__(self, path: str | os.PathLike | None = None, dsn: str | None = None):
        """Nothing is opened until the first query, so importing the app creates no file."""
        self.dsn = dsn if dsn is not None else os.environ.get("WEB5_DSN", "")
        self.path = Path(path or os.environ.get("WEB5_DB_PATH") or DEFAULT_DB)
        self.lock = threading.Lock()
        self.seq: dict[str, int] = {}
        self._conn = None
        self.q = lambda sql: sql

    @property
    def conn(self):
        if self._conn is None:
            if self.dsn:
                import psycopg  # optional dependency, only with WEB5_DSN

                self._conn = psycopg.connect(self.dsn, autocommit=True)
                self.q = lambda sql: sql.replace("?", "%s").replace("INTEGER PRIMARY KEY AUTOINCREMENT",
                                                                    "BIGSERIAL PRIMARY KEY")
            else:
                self.path.parent.mkdir(parents=True, exist_ok=True)
                self._conn = sqlite3.connect(self.path, check_same_thread=False)
            for sql in SCHEMA:
                self._exec(sql)
        return self._conn

    def _exec(self, sql: str, params: tuple = ()):
        cur = self.conn.cursor()
        cur.execute(self.q(sql), params)
        if not self.dsn:
            self.conn.commit()
        return cur

    # rooms ---------------------------------------------------------------------------------------------------------
    def create_room(self, code: str, settings: dict) -> None:
        with self.lock:
            self._exec("INSERT INTO rooms (code, created_at, settings, seats, status) VALUES (?, ?, ?, ?, ?)",
                       (code, time.time(), json.dumps(settings), "{}", "lobby"))

    def update_room(self, code: str, seats: dict | None = None, status: str | None = None) -> None:
        with self.lock:
            if seats is not None:
                self._exec("UPDATE rooms SET seats = ? WHERE code = ?", (json.dumps(seats), code))
            if status is not None:
                self._exec("UPDATE rooms SET status = ? WHERE code = ?", (status, code))

    def append_event(self, code: str, ev: dict) -> None:
        with self.lock:
            seq = self.seq.get(code, 0) + 1
            self.seq[code] = seq
            self._exec("INSERT INTO events (code, seq, ts, kind, body) VALUES (?, ?, ?, ?, ?)",
                       (code, seq, time.time(), str(ev.get("event")), json.dumps(ev, ensure_ascii=False, default=str)))

    def room(self, code: str) -> dict | None:
        with self.lock:
            row = self._exec("SELECT code, created_at, settings, seats, status FROM rooms WHERE code = ?",
                             (code,)).fetchone()
        if not row:
            return None
        return {"code": row[0], "created_at": row[1], "settings": json.loads(row[2]), "seats": json.loads(row[3]),
                "status": row[4]}

    def rooms(self, limit: int = 50) -> list[dict]:
        with self.lock:
            rows = self._exec("SELECT code, created_at, status FROM rooms ORDER BY created_at DESC LIMIT ?",
                              (limit,)).fetchall()
        return [{"code": c, "created_at": t, "status": s} for c, t, s in rows]

    def events(self, code: str) -> list[dict]:
        with self.lock:
            rows = self._exec("SELECT body FROM events WHERE code = ? ORDER BY seq", (code,)).fetchall()
        return [json.loads(r[0]) for r in rows]

    # probes --------------------------------------------------------------------------------------------------------
    def add_probe(self, anon_id: str, client_ts: str, self_vals: list, other_vals: list, meta: dict) -> int:
        with self.lock:
            cur = self._exec("INSERT INTO probes (ts, anon_id, client_ts, self_vals, other_vals, meta) VALUES "
                             "(?, ?, ?, ?, ?, ?)", (time.time(), anon_id, client_ts, json.dumps(self_vals),
                                                   json.dumps(other_vals), json.dumps(meta)))
            if self.dsn:
                return int(self._exec("SELECT MAX(id) FROM probes").fetchone()[0])
            return int(cur.lastrowid)

    def probes(self) -> list[dict]:
        with self.lock:
            rows = self._exec("SELECT id, ts, anon_id, client_ts, self_vals, other_vals FROM probes ORDER BY id").fetchall()
        return [{"id": i, "ts": t, "anon_id": a, "client_ts": c, "self": json.loads(s), "other": json.loads(o)}
                for i, t, a, c, s, o in rows]

    def close(self) -> None:
        if self._conn is not None:
            self._conn.close()
            self._conn = None


def write_run_dir(out: Path, files: dict[str, object]) -> Path:
    """``files`` as ``engine.export_files`` returns them."""
    import yaml

    out.mkdir(parents=True, exist_ok=True)
    (out / "config.yaml").write_text(yaml.safe_dump(files["config.yaml"], sort_keys=False))
    (out / "meta.json").write_text(json.dumps(files["meta.json"]))
    for name in ("events.jsonl", "results.jsonl"):
        (out / name).write_text("".join(json.dumps(e, ensure_ascii=False, default=str) + "\n" for e in files[name]))
    return out
