-- squid5 web API (Cloudflare D1). The tables of web/server/store.py, plus rooms.updated_at and a unique (code, seq)
-- so a Durable Object can mirror its events again without duplicates.
CREATE TABLE IF NOT EXISTS rooms (
  code TEXT PRIMARY KEY,
  created_at REAL,
  settings TEXT,
  seats TEXT,
  status TEXT,
  updated_at REAL
);
CREATE INDEX IF NOT EXISTS rooms_created ON rooms (created_at);

CREATE TABLE IF NOT EXISTS events (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  code TEXT,
  seq INTEGER,
  ts REAL,
  kind TEXT,
  body TEXT
);
CREATE UNIQUE INDEX IF NOT EXISTS events_code ON events (code, seq);

CREATE TABLE IF NOT EXISTS probes (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  ts REAL,
  anon_id TEXT,
  client_ts TEXT,
  self_vals TEXT,
  other_vals TEXT,
  meta TEXT
);
