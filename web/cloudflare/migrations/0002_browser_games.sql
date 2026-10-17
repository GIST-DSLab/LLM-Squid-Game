-- squid5 thin Worker (browser engine, 10-18): games the browser registered, the model calls the Worker relayed for
-- them, and the per-IP counters. The rooms / events tables of 0001 belong to the parked server-side room (legacy/).
CREATE TABLE IF NOT EXISTS games (
  id TEXT PRIMARY KEY,          -- random 16 hex
  created_at REAL,
  ip TEXT,                      -- sha256(GAME_TOKEN_SECRET | ip)[:16], never the address
  code TEXT,                    -- the room code the browser made
  model TEXT,                   -- '' for a game without model seats
  key_name TEXT,                -- OLLAMA_API_KEY3 (or KEY1 while switched on)
  settings TEXT,                -- model, think, fill, humans, rounds, seed (JSON)
  engine TEXT,                  -- the engine bundle hash the browser ran
  engine_version TEXT,
  calls INTEGER DEFAULT 0,      -- model calls relayed (the per-game cap)
  uploads INTEGER DEFAULT 0,    -- record uploads (R2 arena/games/<id>/record.json.gz)
  status TEXT,                  -- as the browser reported it (untrusted until tools/arena/verify_games.py)
  rounds INTEGER,
  events INTEGER,
  digest TEXT,
  bytes INTEGER,
  updated_at REAL
);
CREATE INDEX IF NOT EXISTS games_updated ON games (updated_at);

CREATE TABLE IF NOT EXISTS llm_calls (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  game TEXT,
  n INTEGER,                    -- the game's call number
  ts REAL,
  model TEXT,
  prompt_h TEXT,                -- sha1(last user message)[:16], the engine's prompt hash (replay.digest)
  status INTEGER,               -- Ollama's HTTP status
  stream INTEGER,
  eval_count INTEGER,           -- non-streamed calls: generated tokens (thinking included)
  content_h TEXT                -- non-streamed calls: sha1(content)[:16]
);
CREATE INDEX IF NOT EXISTS llm_calls_game ON llm_calls (game, n);

CREATE TABLE IF NOT EXISTS quota (
  k TEXT PRIMARY KEY,           -- calls:<iphash>:<hour> | games:<iphash>:<hour>
  n INTEGER,
  exp REAL
);
