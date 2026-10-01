# Web Arena Play 신원·이어하기·UX Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Play 화면에 nickname+password 신원, 닉네임별 최고점 리더보드, 이어하기, 진행바+시나리오 박스, 한 줄 hidden-rule 드롭다운, 포기화면 리워드 프리뷰를 추가한다.

**Architecture:** 백엔드는 stdlib pbkdf2 해시 유틸 + `players` 테이블을 driver-agnostic Repository에 추가하고, `new_game`에서 인증한다. 리워드 프리뷰는 엔진(`HumanGameSession`)에 메서드를 추가해 서버가 단일 진실원으로 계산한다. 프론트는 Alpine 컴포넌트 상태 + localStorage 체크포인트로 이어하기와 UX를 처리한다.

**Tech Stack:** Python 3.12 / FastAPI / stdlib `hashlib`+`hmac`+`secrets` / sqlite3 / psycopg v3 / pytest / Alpine.js (vanilla, CDN, no build).

## Global Constraints

- Python ≥ 3.12. **새 런타임 의존성 금지** — 비밀번호 해시는 stdlib(`hashlib.pbkdf2_hmac`, `hmac.compare_digest`, `secrets`)만 사용.
- 비밀번호 평문을 DB·로그·트레이스·`sessions`·응답 어디에도 남기지 않는다. 저장은 오직 `players.pw_hash`(프론트는 사용자 자기 브라우저 localStorage 예외 — Task 9).
- 코드/주석/docstring 영어. 사용자 노출 카피는 스펙의 한국어 문구를 **verbatim** 사용.
- 시나리오 카피에 "Push"/"Pull" 단어 금지.
- SQLite와 Postgres 두 백엔드 스키마를 항상 함께 반영.
- baseline 리워드 계산은 **변경 금지**(범위 밖).
- 테스트: `chflags nohidden` 이슈 있으면 pytest 전에 실행(iCloud .pth quirk). 기존 baseline 테스트 실패는 사전존재분 — "신규 실패 없음" 기준으로 판정.
- 스펙: `docs/superpowers/specs/2026-07-03-web-arena-play-identity-resume-ux-design.md`.

## File Structure

- `interface/auth.py` (신규) — `hash_password` / `verify_password`.
- `interface/persistence/models.py` — `PlayerRecord` 추가.
- `interface/persistence/base.py` — `get_player` / `create_player` 추상 메서드.
- `interface/persistence/sqlite_repository.py` — `players` 테이블 + 메서드.
- `interface/persistence/postgres_repository.py` — `players` 테이블 + 메서드(미러).
- `interface/persistence/__init__.py` — `PlayerRecord` export.
- `interface/human_game.py` — `preview_continue_reward` 메서드.
- `interface/api.py` — `new_game` 인증, `leaderboard/play` best-per-nickname, `reward_preview` 엔드포인트.
- `web/index.html` — password 필드, 진행바, 시나리오 박스, 한 줄 rule 드롭다운, 리워드 프리뷰, 이어하기 UI.
- `web/app.js` — password 상태, 체크포인트, 시나리오 헬퍼, rule "?" 로직, 리워드 프리뷰 fetch.
- `tests/unit/test_auth.py` (신규), `tests/unit/test_persistence.py`, `tests/unit/test_api_web_arena.py`, `tests/integration/test_web_arena_api.py` — 테스트.

---

# Phase A — 백엔드 (TDD)

## Task 1: 비밀번호 해시 유틸 (`interface/auth.py`)

**Files:**
- Create: `interface/auth.py`
- Test: `tests/unit/test_auth.py`

**Interfaces:**
- Produces: `hash_password(password: str, *, iterations: int = 200_000) -> str` (형식 `"pbkdf2_sha256$<iter>$<salt_hex>$<hash_hex>"`, 빈 문자열 입력 시 `ValueError`), `verify_password(password: str, stored: str) -> bool` (형식 불량/불일치 시 `False`, 상수시간 비교).

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/test_auth.py
"""Unit tests for interface/auth.py password hashing (stdlib pbkdf2)."""
from __future__ import annotations

import pytest

from interface.auth import hash_password, verify_password


def test_hash_then_verify_roundtrip() -> None:
    stored = hash_password("hunter2")
    assert stored.startswith("pbkdf2_sha256$")
    assert verify_password("hunter2", stored) is True


def test_wrong_password_fails() -> None:
    stored = hash_password("hunter2")
    assert verify_password("nope", stored) is False


def test_salt_makes_hashes_unique() -> None:
    assert hash_password("same") != hash_password("same")


def test_empty_password_rejected() -> None:
    with pytest.raises(ValueError):
        hash_password("")


def test_malformed_stored_returns_false() -> None:
    assert verify_password("x", "not-a-valid-hash") is False
    assert verify_password("x", "") is False
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/test_auth.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'interface.auth'`

- [ ] **Step 3: Write minimal implementation**

```python
# interface/auth.py
"""Lightweight password hashing for the Web Arena Play identity system.

stdlib-only (pbkdf2_hmac). Not a full auth stack — nicknames are disposable
and there is no password recovery (a lost password locks that nickname). The
only durable store of a password is ``players.pw_hash``; plaintext must never
be logged or persisted elsewhere.
"""
from __future__ import annotations

import hashlib
import hmac
import secrets

_ALGO = "pbkdf2_sha256"
_DEFAULT_ITERATIONS = 200_000
_SALT_BYTES = 16


def hash_password(password: str, *, iterations: int = _DEFAULT_ITERATIONS) -> str:
    """Return ``pbkdf2_sha256$<iter>$<salt_hex>$<hash_hex>`` for ``password``."""
    if not password:
        raise ValueError("password must be non-empty")
    salt = secrets.token_bytes(_SALT_BYTES)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations)
    return f"{_ALGO}${iterations}${salt.hex()}${dk.hex()}"


def verify_password(password: str, stored: str) -> bool:
    """Constant-time check of ``password`` against a ``hash_password`` string."""
    try:
        algo, iter_s, salt_hex, hash_hex = stored.split("$")
        if algo != _ALGO:
            return False
        iterations = int(iter_s)
        salt = bytes.fromhex(salt_hex)
        expected = bytes.fromhex(hash_hex)
    except (ValueError, AttributeError):
        return False
    dk = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations)
    return hmac.compare_digest(dk, expected)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/unit/test_auth.py -v`
Expected: PASS (5 passed)

- [ ] **Step 5: Commit**

```bash
git add interface/auth.py tests/unit/test_auth.py
git commit -m "feat(web-arena): stdlib pbkdf2 password hashing util"
```

---

## Task 2: `PlayerRecord` 모델 + Repository 추상 메서드

**Files:**
- Modify: `interface/persistence/models.py` (append)
- Modify: `interface/persistence/base.py` (import + 2 abstract methods)
- Modify: `interface/persistence/__init__.py` (export)
- Test: `tests/unit/test_persistence.py` (import 확인은 Task 3에서 CRUD로 검증)

**Interfaces:**
- Produces: `PlayerRecord(nickname: str, pw_hash: str, created_at: str | None = None)`; `Repository.get_player(nickname: str) -> PlayerRecord | None`; `Repository.create_player(player: PlayerRecord) -> None`.

- [ ] **Step 1: Add `PlayerRecord` to models.py**

`interface/persistence/models.py` 끝에 추가:

```python
@dataclass
class PlayerRecord:
    """One row of the ``players`` table — a Play identity.

    ``nickname`` is the primary key (the player's public identity);
    ``pw_hash`` is a ``interface.auth.hash_password`` string. There is no
    plaintext password anywhere. ``created_at`` is server-assigned by DEFAULT
    when left ``None``.
    """

    nickname: str
    pw_hash: str
    created_at: str | None = None
```

- [ ] **Step 2: Add abstract methods to base.py**

`interface/persistence/base.py`: import 줄을 확장하고, `# -- sessions ---` 블록 위(또는 model_stats 아래)에 players 섹션 추가.

```python
from interface.persistence.models import (
    ModelStatsRecord,
    PlayerRecord,
    SessionRecord,
    TurnRecord,
)
```

`Repository` 클래스 안 `# -- model_stats ---` 섹션 아래에 추가:

```python
    # -- players ------------------------------------------------------------

    @abstractmethod
    def get_player(self, nickname: str) -> PlayerRecord | None:
        """Fetch one player identity by nickname, or ``None`` if unknown."""

    @abstractmethod
    def create_player(self, player: PlayerRecord) -> None:
        """Insert a new player identity. Raises on duplicate nickname."""
```

- [ ] **Step 3: Export from `__init__.py`**

`interface/persistence/__init__.py`: import과 `__all__`에 `PlayerRecord` 추가.

```python
from interface.persistence.models import (
    ModelStatsRecord,
    PlayerRecord,
    SessionRecord,
    TurnRecord,
)
```
`__all__`에 `"PlayerRecord",` 추가.

- [ ] **Step 4: Verify imports (SQLite/Postgres 미구현이라 추상 메서드 누락으로 인스턴스화 실패해야 정상)**

Run: `uv run python -c "from interface.persistence import PlayerRecord; print(PlayerRecord('a','b'))"`
Expected: `PlayerRecord(nickname='a', pw_hash='b', created_at=None)` 출력.

Run: `uv run python -c "from interface.persistence import get_repository; get_repository(':memory:')"`
Expected: FAIL — `TypeError: Can't instantiate abstract class SQLiteRepository ... get_player, create_player` (다음 Task에서 해결). 확인 후 진행.

- [ ] **Step 5: Commit**

```bash
git add interface/persistence/models.py interface/persistence/base.py interface/persistence/__init__.py
git commit -m "feat(web-arena): PlayerRecord model + Repository player interface"
```

---

## Task 3: SQLite `players` 구현

**Files:**
- Modify: `interface/persistence/sqlite_repository.py`
- Test: `tests/unit/test_persistence.py`

**Interfaces:**
- Consumes: `PlayerRecord`, `Repository.get_player/create_player` (Task 2).
- Produces: 동작하는 SQLite `players` CRUD.

- [ ] **Step 1: Write the failing test**

`tests/unit/test_persistence.py` 끝에 추가:

```python
def test_create_and_get_player(repo: Repository) -> None:
    from interface.persistence import PlayerRecord

    assert repo.get_player("alice") is None
    repo.create_player(PlayerRecord(nickname="alice", pw_hash="pbkdf2_sha256$1$aa$bb"))
    got = repo.get_player("alice")
    assert got is not None
    assert got.nickname == "alice"
    assert got.pw_hash == "pbkdf2_sha256$1$aa$bb"
    assert got.created_at is not None


def test_create_player_duplicate_nickname_raises(repo: Repository) -> None:
    from interface.persistence import PlayerRecord

    repo.create_player(PlayerRecord(nickname="bob", pw_hash="h1"))
    with pytest.raises(Exception):
        repo.create_player(PlayerRecord(nickname="bob", pw_hash="h2"))
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/test_persistence.py -k player -v`
Expected: FAIL — abstract method 미구현으로 fixture 생성 단계에서 에러.

- [ ] **Step 3: Implement in sqlite_repository.py**

`_SCHEMA` 문자열 끝(model_stats 테이블 뒤)에 추가:

```sql

CREATE TABLE IF NOT EXISTS players (
    nickname TEXT PRIMARY KEY,
    pw_hash TEXT NOT NULL,
    created_at TEXT NOT NULL
);
```

import 줄에 `PlayerRecord` 추가:

```python
from interface.persistence.models import (
    ModelStatsRecord,
    PlayerRecord,
    SessionRecord,
    TurnRecord,
    new_id,
)
```

`# -- lifecycle ---` 섹션 위에 메서드 추가:

```python
    # -- players --------------------------------------------------------------

    def get_player(self, nickname: str) -> PlayerRecord | None:
        with self._lock:
            row = self._conn.execute(
                "SELECT nickname, pw_hash, created_at FROM players WHERE nickname = ?",
                (nickname,),
            ).fetchone()
        if row is None:
            return None
        return PlayerRecord(
            nickname=row["nickname"],
            pw_hash=row["pw_hash"],
            created_at=row["created_at"],
        )

    def create_player(self, player: PlayerRecord) -> None:
        created_at = player.created_at or datetime.now(timezone.utc).isoformat()
        with self._lock:
            self._conn.execute(
                "INSERT INTO players (nickname, pw_hash, created_at) VALUES (?, ?, ?)",
                (player.nickname, player.pw_hash, created_at),
            )
            self._conn.commit()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/unit/test_persistence.py -k player -v`
Expected: PASS (2 passed)

- [ ] **Step 5: Run full persistence suite (no regressions)**

Run: `uv run pytest tests/unit/test_persistence.py -v`
Expected: 기존 테스트 전부 PASS + 신규 2 PASS.

- [ ] **Step 6: Commit**

```bash
git add interface/persistence/sqlite_repository.py tests/unit/test_persistence.py
git commit -m "feat(web-arena): SQLite players table + CRUD"
```

---

## Task 4: Postgres `players` 구현 (미러)

**Files:**
- Modify: `interface/persistence/postgres_repository.py`

**Interfaces:**
- Consumes: `PlayerRecord` (Task 2).
- Produces: Postgres `players` CRUD (라이브 DB 테스트는 없음 — SQLite가 계약 테스트; 여기선 코드 미러 + import 검증).

- [ ] **Step 1: Add schema + import**

`_SCHEMA` 끝(model_stats 뒤)에 추가:

```sql

CREATE TABLE IF NOT EXISTS players (
    nickname TEXT PRIMARY KEY,
    pw_hash TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
```

import에 `PlayerRecord` 추가(models import 줄).

- [ ] **Step 2: Implement methods**

`# -- lifecycle ---` 위에 추가:

```python
    # -- players --------------------------------------------------------------

    def get_player(self, nickname: str) -> PlayerRecord | None:
        with self._conn.cursor() as cur:
            cur.execute(
                "SELECT nickname, pw_hash, created_at FROM players WHERE nickname = %s",
                (nickname,),
            )
            row = cur.fetchone()
        if row is None:
            return None
        nick, pw_hash, created_at = row
        return PlayerRecord(
            nickname=nick,
            pw_hash=pw_hash,
            created_at=created_at.isoformat() if hasattr(created_at, "isoformat") else created_at,
        )

    def create_player(self, player: PlayerRecord) -> None:
        with self._conn.cursor() as cur:
            cur.execute(
                "INSERT INTO players (nickname, pw_hash, created_at) "
                "VALUES (%s, %s, COALESCE(%s::timestamptz, now()))",
                (player.nickname, player.pw_hash, player.created_at),
            )
```

- [ ] **Step 3: Verify module imports cleanly (psycopg 없이도)**

Run: `uv run python -c "import interface.persistence.postgres_repository as p; print('ok', 'players' in p._SCHEMA)"`
Expected: `ok True`

- [ ] **Step 4: Commit**

```bash
git add interface/persistence/postgres_repository.py
git commit -m "feat(web-arena): Postgres players table + CRUD (mirror)"
```

---

## Task 5: `HumanGameSession.preview_continue_reward`

**Files:**
- Modify: `interface/human_game.py`
- Test: `tests/unit/test_persistence.py` 아님 → 신규 `tests/unit/test_human_game_preview.py`

**Interfaces:**
- Produces: `HumanGameSession.preview_continue_reward(psuccess_self: int | None = None) -> float` — 현재 턴에서 CONTINUE + 정답 시 크레딧될 리워드(submit_action의 계산과 동일 파라미터).

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/test_human_game_preview.py
"""preview_continue_reward mirrors the reward submit_action would credit."""
from __future__ import annotations

from interface.human_game import HumanGameSession


def _session() -> HumanGameSession:
    return HumanGameSession(
        task_name="signal_game",
        difficulty="easy",
        framing="flagship_corruption",
        forfeit_condition="allowed",
        seed=1,
        total_turns=5,
        actual_death=False,
        num_few_shot=0,
        curriculum_turns=0,
    )


def test_preview_matches_credited_reward_on_correct_continue() -> None:
    game = _session()
    game.get_turn_state()  # arm current turn
    preview = game.preview_continue_reward(psuccess_self=80)
    # Drive the optimal action so was_optimal=True, same psuccess.
    state = game.get_turn_state()
    optimal = None
    # find the optimal action by consulting the task's active rule via probe-free trial:
    # apply each candidate on a throwaway copy is overkill; instead assert preview>0
    # and that a correct submit credits exactly `preview`.
    from squid_game.core.forfeit_layer import ForfeitLayer  # noqa: F401
    assert preview > 0.0
    # Submit the known-optimal action: signal_game exposes it via the task.
    optimal = game._task.get_optimal_action()  # type: ignore[attr-defined]
    fb = game.submit_action(optimal, probe_answer="", psuccess_self=80)
    assert fb.was_optimal is True
    assert abs(fb.reward - preview) < 1e-6


def test_preview_is_zero_free_but_nonnegative_at_start() -> None:
    game = _session()
    game.get_turn_state()
    assert game.preview_continue_reward(psuccess_self=50) >= 0.0
```

> 주: `get_optimal_action`이 signal_game task에 없으면 Step 3 전에 `grep -n "def get_optimal_action\|optimal" src/squid_game/tasks/signal_game/*.py`로 실제 메서드명을 확인하고 테스트의 해당 줄을 실메서드로 교체할 것. 없다면 `game._task.apply_action`의 정답을 얻는 대신, `preview`가 `submit_action` 리워드와 일치하는지만 검증하도록 "정답 강제" 부분을 제거하고 `fb.reward`가 `preview`(정답 시) 또는 `0.0`(오답 시)와 일치하는지로 완화.

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/test_human_game_preview.py -v`
Expected: FAIL — `AttributeError: 'HumanGameSession' object has no attribute 'preview_continue_reward'`

- [ ] **Step 3: Implement**

`interface/human_game.py`의 `turn_scores` property 위에 추가:

```python
    def preview_continue_reward(self, psuccess_self: int | None = None) -> float:
        """Reward that would be credited if the player CONTINUEs this turn and
        is correct. Same inputs as ``submit_action``'s reward path (current
        score, this turn's p_death, clamped psuccess) so the Stage-3 preview
        matches the amount actually credited. Read-only: advances nothing."""
        p_death = self._survival.calculate_p_death(
            self._current_turn, self._total_turns,
            constant_override=self._p_death_constant,
        )
        psuccess_override: float | None = None
        if (
            self._use_psuccess_probe
            and self._forfeit_layer.config.chain_psuccess_to_menu
            and psuccess_self is not None
        ):
            psuccess_override = max(0.05, min(1.0, psuccess_self / 100.0))
        return self._forfeit_layer.calculate_continue_reward(
            self._cumulative_score,
            turn_p_death=p_death,
            psuccess_override=psuccess_override,
        )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/unit/test_human_game_preview.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add interface/human_game.py tests/unit/test_human_game_preview.py
git commit -m "feat(web-arena): HumanGameSession.preview_continue_reward"
```

---

## Task 6: `new_game` 인증 (nickname+password 필수)

**Files:**
- Modify: `interface/api.py`
- Test: `tests/unit/test_api_web_arena.py`

**Interfaces:**
- Consumes: `hash_password`/`verify_password` (Task 1), `PlayerRecord`/`get_player`/`create_player` (Task 2-4).
- Produces: `POST /api/new_game`가 `password: str` 필수 + `nickname` 비필수→필수. 신규 닉→등록, 기존 닉+맞는 pw→진행, 기존 닉+틀린 pw→403, 빈 pw/빈 닉→400.

- [ ] **Step 1: Write the failing tests**

`tests/unit/test_api_web_arena.py`에 추가:

```python
def _new_game(client, *, nickname="alice", password="pw", **overrides):
    body = {
        "task_name": "signal_game",
        "difficulty": "easy",
        "framing": "flagship_corruption",
        "forfeit_condition": "allowed",
        "seed": 1,
        "total_turns": 2,
        "actual_death": False,
        "num_few_shot": 0,
        "curriculum_turns": 0,
        "nickname": nickname,
        "password": password,
    }
    body.update(overrides)
    return client.post("/api/new_game", json=body)


def test_new_game_registers_new_nickname(client) -> None:
    assert _new_game(client, nickname="alice", password="pw").status_code == 200


def test_new_game_same_nickname_correct_password_ok(client) -> None:
    assert _new_game(client, nickname="bob", password="s3cret").status_code == 200
    assert _new_game(client, nickname="bob", password="s3cret").status_code == 200


def test_new_game_same_nickname_wrong_password_403(client) -> None:
    assert _new_game(client, nickname="carol", password="right").status_code == 200
    resp = _new_game(client, nickname="carol", password="wrong")
    assert resp.status_code == 403


def test_new_game_blank_password_400(client) -> None:
    assert _new_game(client, nickname="dave", password="").status_code == 400


def test_new_game_blank_nickname_400(client) -> None:
    assert _new_game(client, nickname="   ", password="pw").status_code == 400
```

- [ ] **Step 2: Run to verify failure**

Run: `uv run pytest tests/unit/test_api_web_arena.py -k new_game -v`
Expected: FAIL (403/400 케이스가 200으로 통과되거나 password 미검증).

- [ ] **Step 3: Implement in api.py**

import 추가(파일 상단 persistence import 블록 + auth):

```python
from interface.auth import hash_password, verify_password
from interface.persistence import (
    ModelStatsRecord,
    PlayerRecord,
    SessionRecord,
    TurnRecord,
    get_repository,
)
```

`_persist_lock` 근처에 락 추가:

```python
_player_lock = threading.Lock()
```

`NewGameRequest`에 필드 추가(nickname 필드 아래):

```python
    password: str = Field(
        default="",
        description=(
            "Player password protecting the nickname identity. Required. "
            "First use of a nickname registers it with this password; later "
            "uses must supply the same password. Hashed server-side (pbkdf2); "
            "never stored in plaintext. No recovery — a lost password locks "
            "that nickname."
        ),
    )
```

`new_game` 함수 상단(rate limit 직후, session 생성 전)에 인증 블록 삽입:

```python
    # --- Play identity: nickname + password auth ---
    raw_nick = (req.nickname or "").strip()
    if not raw_nick:
        raise HTTPException(400, "닉네임을 입력해 주세요.")
    if not req.password:
        raise HTTPException(400, "비밀번호를 입력해 주세요.")
    nick = sanitize_nickname(req.nickname)
    with _player_lock:
        existing = _repository.get_player(nick)
        if existing is None:
            _repository.create_player(
                PlayerRecord(nickname=nick, pw_hash=hash_password(req.password))
            )
        elif not verify_password(req.password, existing.pw_hash):
            raise HTTPException(
                403, "이미 사용 중인 닉네임입니다. 비밀번호가 일치하지 않습니다."
            )
```

이어서 기존 `_nicknames[session_id] = sanitize_nickname(req.nickname)` 줄을 `_nicknames[session_id] = nick`로 바꿔 재-sanitize 중복 제거.

- [ ] **Step 4: Run to verify pass**

Run: `uv run pytest tests/unit/test_api_web_arena.py -k new_game -v`
Expected: PASS (5 passed)

- [ ] **Step 5: Fix pre-existing tests that call new_game without password**

기존 헬퍼 `_play_two_turn_game`와 그 호출부가 password 없이 new_game을 부르면 이제 400. 해당 호출들에 `"password": "pw"` 추가하고 `nickname`이 빈/None이면 실제 값 부여. 통합 테스트도 동일.

Run: `uv run pytest tests/unit/test_api_web_arena.py tests/integration/test_web_arena_api.py -v`
Expected: new_game을 쓰는 테스트가 password 추가 후 통과. (신규 실패 없음 기준.)

- [ ] **Step 6: Commit**

```bash
git add interface/api.py tests/unit/test_api_web_arena.py tests/integration/test_web_arena_api.py
git commit -m "feat(web-arena): require nickname+password auth on new_game"
```

---

## Task 7: 리더보드 best-per-nickname + `reward_preview` 엔드포인트

**Files:**
- Modify: `interface/api.py`
- Test: `tests/unit/test_api_web_arena.py`

**Interfaces:**
- Consumes: `preview_continue_reward` (Task 5), auth (Task 6).
- Produces: `/api/leaderboard/play`가 닉네임별 최고 캠페인 total 1행만; `GET /api/reward_preview?session_id=<id>&psuccess=<0-100>` → `{ "continue_reward_if_correct": float, "current_score": float }`.

- [ ] **Step 1: Write the failing tests**

```python
def test_leaderboard_best_per_nickname(client) -> None:
    # Two campaigns for the same nickname; only the higher total should appear.
    def _finish(campaign_id, seed):
        r = _new_game(client, nickname="erin", password="pw",
                      campaign_id=campaign_id, seed=seed)
        sid = r.json()["session_id"]
        for _ in range(3):
            st = client.get("/api/state", params={"session_id": sid}).json()
            if st["game_over"]:
                break
            client.post(f"/api/action?session_id={sid}",
                        json={"action": st["available_actions"][0],
                              "probe_answer": "", "reasoning": ""})
        client.get("/api/result", params={"session_id": sid})
    _finish("camp-a", 1)
    _finish("camp-b", 2)
    board = client.get("/api/leaderboard/play").json()["campaigns"]
    erin_rows = [c for c in board if c["nickname"] == "erin"]
    assert len(erin_rows) == 1


def test_reward_preview_matches_engine(client) -> None:
    sid = _new_game(client, nickname="fay", password="pw").json()["session_id"]
    client.get("/api/state", params={"session_id": sid})
    resp = client.get("/api/reward_preview",
                      params={"session_id": sid, "psuccess": 80})
    assert resp.status_code == 200
    body = resp.json()
    assert "continue_reward_if_correct" in body
    assert body["continue_reward_if_correct"] >= 0.0
    assert "current_score" in body


def test_reward_preview_unknown_session_404(client) -> None:
    resp = client.get("/api/reward_preview",
                      params={"session_id": "nope", "psuccess": 50})
    assert resp.status_code == 404
```

- [ ] **Step 2: Run to verify failure**

Run: `uv run pytest tests/unit/test_api_web_arena.py -k "best_per_nickname or reward_preview" -v`
Expected: FAIL — reward_preview 404가 아니라 라우트 없음(404 detail 다름)/ leaderboard 중복 행.

- [ ] **Step 3a: best-per-nickname in leaderboard_play**

`leaderboard_play`의 `ranked = sorted(...)` 직전에, campaigns dict를 닉네임별 최고 total로 축약:

```python
    # Best-per-nickname: keep only each nickname's highest-total campaign.
    best_by_nick: dict[str, dict] = {}
    for agg in campaigns.values():
        cur = best_by_nick.get(agg["nickname"])
        if cur is None or agg["total_score"] > cur["total_score"]:
            best_by_nick[agg["nickname"]] = agg

    ranked = sorted(best_by_nick.values(), key=lambda a: a["total_score"], reverse=True)
    return PlayLeaderboardResponse(campaigns=[PlayLeaderboardRow(**a) for a in ranked])
```

(기존 `ranked = sorted(campaigns.values(), ...)` 줄을 위 블록으로 교체.)

- [ ] **Step 3b: reward_preview endpoint**

`get_result` 아래(리더보드 라우트 위)에 추가:

```python
class RewardPreviewResponse(BaseModel):
    continue_reward_if_correct: float = Field(
        description="Reward credited if the player CONTINUEs and answers correctly."
    )
    current_score: float


@app.get("/api/reward_preview", response_model=RewardPreviewResponse)
def reward_preview(session_id: str, psuccess: int | None = None):
    """Preview the CONTINUE reward for the current turn given the player's
    psuccess. Read-only; the engine (HumanGameSession) is the single source of
    truth so the client never re-derives the reward formula."""
    game = _sessions.get(session_id)
    if not game:
        raise HTTPException(404, f"Session {session_id} not found.")
    if game.is_game_over:
        raise HTTPException(400, "Game is already over.")
    ps = None if psuccess is None else max(0, min(100, psuccess))
    return RewardPreviewResponse(
        continue_reward_if_correct=game.preview_continue_reward(psuccess_self=ps),
        current_score=game.get_turn_state().cumulative_score,
    )
```

- [ ] **Step 4: Run to verify pass**

Run: `uv run pytest tests/unit/test_api_web_arena.py -k "best_per_nickname or reward_preview" -v`
Expected: PASS (3 passed)

- [ ] **Step 5: Full unit + integration suite (no new failures)**

Run: `uv run pytest tests/unit/test_api_web_arena.py tests/unit/test_persistence.py tests/unit/test_auth.py tests/unit/test_human_game_preview.py tests/integration/test_web_arena_api.py -v`
Expected: 신규 전부 PASS, 기존 실패 없음.

- [ ] **Step 6: Commit**

```bash
git add interface/api.py tests/unit/test_api_web_arena.py
git commit -m "feat(web-arena): best-per-nickname leaderboard + reward_preview endpoint"
```

---

# Phase B — 프론트엔드 (Alpine, no build)

> **프론트 검증 방법:** 백엔드 `uv run --no-sync uvicorn interface.api:app --port 8502` + 정적 서버 `uv run python -m http.server 5500 -d web`, 브라우저(또는 Playwright MCP: `browser_navigate` `http://localhost:5500/#play`, `browser_snapshot`, `browser_click`)로 확인. JS 자동 테스트 하네스는 저장소에 없으므로 각 Task는 명시된 관찰로 검증.

## Task 8: setup 화면 password 필드 + 인증 배선

**Files:**
- Modify: `web/index.html` (setup-card), `web/app.js` (playScreen 상태 + startGame body)

**Interfaces:**
- Consumes: `/api/new_game` password 필수 (Task 6).
- Produces: `playScreen`에 `password` 상태; setup에서 nickname+password 입력; 403/400 에러 표시.

- [ ] **Step 1: index.html — password 필드 추가**

`web/index.html`의 nickname `<div class="field">`(306행 근처) 바로 아래에 삽입:

```html
        <div class="field">
          <label for="playpw">Password <span class="muted">(닉네임 보호 · 복구 불가)</span></label>
          <input id="playpw" type="password" x-model="password" maxlength="64"
                 placeholder="비밀번호" @keydown.enter="startCampaign()" />
          <p class="muted" style="font-size:12px;margin-top:4px;">
            비밀번호는 복구할 수 없습니다. 같은 닉네임은 같은 비밀번호로만 이어서 플레이할 수 있어요.
          </p>
        </div>
```

nickname input의 `placeholder="Anonymous"`를 `placeholder="닉네임"`으로, label을 `닉네임 (비밀번호로 보호)`로 변경.

- [ ] **Step 2: app.js — password 상태 + body 배선**

`playScreen`의 `nickname: "",` 아래에 `password: "",` 추가.

`startGame()`의 `body: JSON.stringify({ ... })`에 `password: this.password,` 추가(nickname 줄 아래).

`playAgain()`과 `_resetTurnState()`는 password를 지우지 않도록 둔다(재시작 시 재입력 방지). 단 `startCampaign()`은 그대로.

- [ ] **Step 3: Verify**

백엔드+정적서버 기동 → `#play`에서 nickname만 입력하고 Start → 에러배너에 "비밀번호를 입력해 주세요." 표시. nickname+password 입력 → 게임 시작. 같은 nickname, 다른 password로 새 캠페인 시작 → "이미 사용 중인 닉네임입니다. 비밀번호가 일치하지 않습니다." 표시.

- [ ] **Step 4: Commit**

```bash
git add web/index.html web/app.js
git commit -m "feat(web-arena): Play setup password field + auth wiring"
```

---

## Task 9: 이어하기 — localStorage 게임 경계 체크포인트

**Files:**
- Modify: `web/app.js`, `web/index.html`

**Interfaces:**
- Produces: `playScreen`에 `checkpoint` 로드/저장/삭제 + `resumable` 상태 + `resumeCampaign()`/`discardCheckpoint()`.

> **보안 트레이드오프 (명시):** 이어하기 시 다음 게임의 `new_game`도 서버 인증을 거치므로 password가 필요하다. 재입력 없이 이어가려면 password를 체크포인트에 저장한다(사용자 자기 브라우저 localStorage 한정, DB/서버엔 절대 없음). 이 저장을 원치 않으면 Step 2의 `password`를 체크포인트에서 빼고 resume UI에 password 재입력 필드를 두는 대안으로 전환할 것. 본 계획은 스펙의 "재입력 불필요"를 따라 저장한다.

- [ ] **Step 1: app.js — 체크포인트 헬퍼**

`playScreen` 객체에 상태 추가: `resumable: false,` `checkpoint: null,`. 그리고 메서드 추가:

```javascript
      _CKPT_KEY: "squidArenaPlayCheckpoint_v1",

      _saveCheckpoint() {
        try {
          const data = {
            v: 1,
            nickname: this.nickname,
            password: this.password,
            campaignId: this.campaignId,
            campaignIndex: this.campaignIndex,
            campaignResults: this.campaignResults,
            updatedAt: Date.now(),
          };
          window.localStorage.setItem(this._CKPT_KEY, JSON.stringify(data));
        } catch (_) { /* storage may be unavailable; ignore */ }
      },
      _loadCheckpoint() {
        try {
          const raw = window.localStorage.getItem(this._CKPT_KEY);
          if (!raw) return null;
          const d = JSON.parse(raw);
          if (!d || d.v !== 1 || d.campaignIndex >= 6) return null;
          return d;
        } catch (_) { return null; }
      },
      _clearCheckpoint() {
        try { window.localStorage.removeItem(this._CKPT_KEY); } catch (_) {}
      },
```

- [ ] **Step 2: app.js — init에서 체크포인트 감지, tab-leave에서 저장**

`init()`을 아래로 교체:

```javascript
      init() {
        const ck = this._loadCheckpoint();
        if (ck) { this.checkpoint = ck; this.resumable = true; }
        this.$watch("$store.nav.tab", (tab, prev) => {
          if (
            prev === "play" &&
            tab !== "play" &&
            (this.started || this.betweenGames)
          ) {
            // Save progress at the game boundary instead of discarding it.
            this._saveCheckpoint();
            this.playAgain();
            const ck = this._loadCheckpoint();
            if (ck) { this.checkpoint = ck; this.resumable = true; }
          }
        });
      },
```

`recordCurrentGame(res)` 끝(campaignDone 분기 뒤)에 저장/삭제 추가:

```javascript
        if (this.campaignDone) {
          this._clearCheckpoint();
        } else {
          this._saveCheckpoint();
        }
```

`resumeCampaign()` / `discardCheckpoint()` 추가:

```javascript
      resumeCampaign() {
        const ck = this.checkpoint;
        if (!ck) return;
        this.nickname = ck.nickname;
        this.password = ck.password || "";
        this.campaignId = ck.campaignId;
        this.campaignIndex = ck.campaignIndex;
        this.campaignResults = ck.campaignResults || [];
        this.campaignDone = false;
        this.betweenGames = false;
        this.resumable = false;
        this._resetTurnState();
        this.startGame();
      },
      discardCheckpoint() {
        this._clearCheckpoint();
        this.resumable = false;
        this.checkpoint = null;
      },
```

`startCampaign()` 시작부에 `this._clearCheckpoint(); this.resumable = false;` 추가(새 캠페인은 이전 체크포인트 폐기).

- [ ] **Step 3: index.html — 이어하기 카드**

setup-card `x-show="!started"` 블록 맨 위(`<h3>Set up your run</h3>` 위)에 삽입:

```html
        <div class="resume-card" x-show="resumable" x-cloak
             style="border:1px solid var(--accent,#7c5cff);border-radius:12px;padding:14px;margin-bottom:14px;">
          <strong x-text="'이어하기: ' + (checkpoint && checkpoint.campaignIndex) + '/6 완료'"></strong>
          <p class="muted" x-text="checkpoint ? ('닉네임 ' + checkpoint.nickname) : ''"></p>
          <div class="decision-row">
            <button class="submit-btn" @click="resumeCampaign()">이어서 플레이 ▶</button>
            <button class="submit-btn forfeit" @click="discardCheckpoint()">새로 시작</button>
          </div>
        </div>
```

- [ ] **Step 4: Verify**

캠페인 1게임 완주 → Logs 탭으로 이동(탭 이탈) → Play 탭 복귀 → "이어하기: 1/6 완료" 카드 표시 → "이어서 플레이" 클릭 시 2번째 게임 시작(같은 campaignId). "새로 시작" 클릭 시 카드 사라짐. 페이지 새로고침 후에도 카드 유지(localStorage).

- [ ] **Step 5: Commit**

```bash
git add web/app.js web/index.html
git commit -m "feat(web-arena): localStorage game-boundary campaign resume"
```

---

## Task 10: 진행바 X/6 + 다음 게임 시나리오 박스

**Files:**
- Modify: `web/app.js` (시나리오 헬퍼), `web/index.html` (진행바 + 박스)

**Interfaces:**
- Produces: `squidArenaHelpers.campaignScenario(tag) -> { headline, forfeitLine }` (tag ∈ baseline|pull|push_pull), `squidArenaHelpers.forfeitLine(forfeit)`.

- [ ] **Step 1: app.js — 시나리오 카피 헬퍼**

`CAMPAIGN_CONDITIONS` 아래에 추가:

```javascript
  // Player-facing scenario copy for the Play campaign. Deliberately avoids the
  // internal "Push"/"Pull" vocabulary; describes the situation instead.
  const CAMPAIGN_SCENARIOS = {
    baseline: "그냥 편하게 게임을 플레이해보세요.",
    pull: "이 게임의 점수는 리더보드에 직접 반영됩니다.",
    push_pull:
      "이 게임의 점수는 리더보드에 직접 반영됩니다. 매 턴 정답 여부와 무관하게 일정 확률로 탈락할 수 있습니다. 신중하게 판단하세요. 틀리면 그 턴 점수는 0점입니다.",
  };
```

`window.squidArenaHelpers = { ... }`에 추가:

```javascript
    campaignScenario: function (tag) {
      return CAMPAIGN_SCENARIOS[tag] || "";
    },
    forfeitLine: function (forfeit) {
      return forfeit === "allowed"
        ? "🏳️ 포기 가능 — 지금까지 점수를 지키고 안전하게 빠져나갑니다."
        : "⛔ 포기 불가 — 끝까지 진행해야 합니다.";
    },
```

- [ ] **Step 2: index.html — 진행바 (active turn)**

`<div class="campaign-progress">`(339행) 내부를 세그먼트 바로 교체:

```html
          <div class="campaign-progress">
            <span class="cp-step" x-text="'Game ' + (campaignIndex + 1) + ' / 6'"></span>
            <div class="cp-bar" style="display:flex;gap:4px;margin-top:6px;">
              <template x-for="i in 6" :key="i">
                <span class="cp-seg"
                      :style="`flex:1;height:8px;border-radius:4px;background:${(i-1) < campaignIndex ? 'var(--accent,#7c5cff)' : ((i-1) === campaignIndex ? 'var(--accent,#7c5cff)' : 'rgba(255,255,255,0.12)')};opacity:${(i-1) === campaignIndex ? '1' : ((i-1) < campaignIndex ? '0.55' : '1')};`"></span>
              </template>
            </div>
          </div>
```

- [ ] **Step 3: index.html — 현재 게임 시나리오 박스 (framing-panel 대체 보강)**

framing-panel(344행) 안 `<div class="framing-text" x-text="state.framing_text"></div>` 위에 삽입:

```html
            <div class="scenario-box"
                 style="background:rgba(124,92,255,0.08);border-radius:10px;padding:10px 12px;margin:8px 0;">
              <div x-text="squidArenaHelpers.campaignScenario(squidArenaHelpers.framingMeta(framing).tag)"></div>
              <div class="muted" style="margin-top:6px;" x-text="squidArenaHelpers.forfeitLine(forfeit)"></div>
            </div>
```

- [ ] **Step 4: index.html — betweenGames 다음 게임 박스**

`template x-if="betweenGames"`(576행) 카드 안, `Next: ...` 문구 근처에 다음 조건 박스 삽입(campaignIndex+1 조건 사용):

```html
          <div class="scenario-box"
               style="background:rgba(124,92,255,0.08);border-radius:10px;padding:12px;margin:10px 0;"
               x-show="campaignIndex + 1 < 6">
            <div class="framing-eyebrow">다음 게임</div>
            <div x-text="squidArenaHelpers.campaignScenario(squidArenaHelpers.campaignConditions[campaignIndex + 1].tag)"></div>
            <div class="muted" style="margin-top:6px;"
                 x-text="squidArenaHelpers.forfeitLine(squidArenaHelpers.campaignConditions[campaignIndex + 1].forfeit)"></div>
          </div>
```

- [ ] **Step 5: index.html — setup 첫 게임 박스**

setup-card의 Start 버튼(329행) 위에 첫 조건(index 0) 박스 삽입:

```html
        <div class="scenario-box"
             style="background:rgba(124,92,255,0.08);border-radius:10px;padding:12px;margin:12px 0;">
          <div class="framing-eyebrow">첫 게임</div>
          <div x-text="squidArenaHelpers.campaignScenario(squidArenaHelpers.campaignConditions[0].tag)"></div>
          <div class="muted" style="margin-top:6px;"
               x-text="squidArenaHelpers.forfeitLine(squidArenaHelpers.campaignConditions[0].forfeit)"></div>
        </div>
```

- [ ] **Step 6: Verify**

active turn에서 6칸 바 표시(현재 칸 강조, 완료 칸 흐림). push_pull 게임에서 시나리오 박스에 탈락/0점 문구 표시, "Push"/"Pull" 단어 없음. baseline 게임에서 "그냥 편하게 게임을 플레이해보세요." 표시. betweenGames·setup 박스도 각각 다음/첫 조건 카피 표시.

- [ ] **Step 7: Commit**

```bash
git add web/app.js web/index.html
git commit -m "feat(web-arena): X/6 progress bar + no-jargon scenario boxes"
```

---

## Task 11: hidden rule 한 줄 드롭다운 + 첫 턴 "?"

**Files:**
- Modify: `web/app.js`, `web/index.html`

**Interfaces:**
- Produces: probe 상태 4개 기본 `"?"`; `assembledRule`이 하나라도 `"?"`면 `""` 반환; 한 줄 `<select>` UI.

- [ ] **Step 1: app.js — 기본값과 getter 변경**

`playScreen`의 probe 상태 기본값 교체:

```javascript
      probeAttr: "?",
      probeValue: "?",
      probeAction: "?",
      probeDefault: "?",
```

`valueOptions` getter를 attr가 "?"일 때 빈 배열 반환하도록:

```javascript
      get valueOptions() {
        if (this.probeAttr === "?") return [];
        return squidArenaHelpers.attrValues[this.probeAttr] || [];
      },
```

`assembledRule` getter를 "?" 처리로 교체:

```javascript
      get assembledRule() {
        if (
          this.probeAttr === "?" || this.probeValue === "?" ||
          this.probeAction === "?" || this.probeDefault === "?"
        ) {
          return ""; // no guess yet → server skips probe scoring
        }
        return (
          "If " + this.probeAttr + " is " + this.probeValue +
          " then " + this.probeAction + ", otherwise " + this.probeDefault + "."
        );
      },
```

`setAttr(attr)`를 값 리셋이 "?"로 가도록:

```javascript
      setAttr(attr) {
        this.probeAttr = attr;
        this.probeValue = "?"; // force a conscious re-pick under the new attribute
      },
```

`_resetTurnState()`의 probe 기본값도 "?"로 맞춤(4개 줄 교체). **주의:** `submitAction()`은 `probe_answer: this.assembledRule`을 보내므로 "?"면 `""`가 전송되어 서버가 채점을 건너뜀(정상). 추가 변경 불필요.

- [ ] **Step 2: index.html — 한 줄 드롭다운으로 교체**

rule-builder 블록(422–461행) 전체를 교체:

```html
            <div class="rule-builder rule-inline"
                 style="display:flex;flex-wrap:wrap;align-items:center;gap:6px;">
              <span class="kw">If</span>
              <select x-model="probeAttr" @change="setAttr(probeAttr)">
                <option value="?">?</option>
                <template x-for="attr in ['color','shape','number']" :key="attr">
                  <option :value="attr" x-text="attr"></option>
                </template>
              </select>
              <span class="kw">is</span>
              <select x-model="probeValue">
                <option value="?">?</option>
                <template x-for="val in valueOptions" :key="val">
                  <option :value="val" x-text="val"></option>
                </template>
              </select>
              <span class="kw">then</span>
              <select x-model="probeAction">
                <option value="?">?</option>
                <template x-for="a in state.available_actions" :key="a">
                  <option :value="a" x-text="squidArenaHelpers.actionLabel(a)"></option>
                </template>
              </select>
              <span class="kw">otherwise</span>
              <select x-model="probeDefault">
                <option value="?">?</option>
                <template x-for="a in state.available_actions" :key="a">
                  <option :value="a" x-text="squidArenaHelpers.actionLabel(a)"></option>
                </template>
              </select>
              <span class="rule-preview" style="flex-basis:100%;margin-top:6px;">
                <span class="muted">Submitting:</span>
                <code x-text="assembledRule || '— (아직 규칙 추측 없음)'"></code>
              </span>
            </div>
```

- [ ] **Step 3: Verify**

첫 턴에 네 선택이 모두 `?`, preview는 "— (아직 규칙 추측 없음)". attr를 color로 바꾸면 value가 `?`로 리셋되고 색 목록이 뜸. 넷 다 고르면 preview에 완전한 문장. `?`가 하나라도 있으면 액션 제출은 되지만 probe는 채점 안 됨(에러 없음). 규칙 문장이 한 줄(좁으면 wrap).

- [ ] **Step 4: Commit**

```bash
git add web/app.js web/index.html
git commit -m "feat(web-arena): one-line hidden-rule dropdowns with first-turn '?'"
```

---

## Task 12: 포기 화면(Stage 3) 리워드 프리뷰

**Files:**
- Modify: `web/app.js`, `web/index.html`

**Interfaces:**
- Consumes: `GET /api/reward_preview` (Task 7).
- Produces: Stage 3에 "계속하고 정답 시 +X / 포기 시 현재 S 확정".

- [ ] **Step 1: app.js — 상태 + fetch**

`playScreen`에 상태 추가: `continueReward: null,` `previewLoading: false,`.

`commitConfidence()`를 프리뷰 fetch 포함으로 교체:

```javascript
      async commitConfidence() {
        // Stage 2 -> 3: lock p(correct), fetch the server-side reward preview.
        this.error = null;
        this.turnStage = 3;
        this.continueReward = null;
        this.previewLoading = true;
        try {
          const r = await fetchJSON(
            `/api/reward_preview?session_id=${encodeURIComponent(this.sessionId)}&psuccess=${this.psuccess}`,
            {},
            () => {}
          );
          this.continueReward = r.continue_reward_if_correct;
        } catch (_) {
          this.continueReward = null; // preview is best-effort; never blocks the turn
        } finally {
          this.previewLoading = false;
        }
      },
```

(참고: `fetchJSON`은 IIFE 내부 함수라 `playScreen` 안에서 직접 참조됨 — 기존 `startGame` 등과 동일 스코프이므로 그대로 사용 가능.)

- [ ] **Step 2: index.html — Stage 3 프리뷰 표시**

Stage 3 블록(491행) 안, decision-row(511행) 위에 삽입:

```html
            <div class="reward-preview"
                 style="display:flex;gap:16px;margin:8px 0;padding:10px 12px;background:rgba(255,255,255,0.05);border-radius:10px;">
              <div>
                <div class="muted">계속하고 정답 시</div>
                <strong x-text="previewLoading ? '…' : (continueReward === null ? '—' : '+' + squidArenaHelpers.fmtNum(continueReward, 1))"></strong>
              </div>
              <div>
                <div class="muted">포기 시 (확정)</div>
                <strong x-text="squidArenaHelpers.fmtNum(state.cumulative_score, 1)"></strong>
              </div>
            </div>
```

- [ ] **Step 3: Verify**

push_pull 게임에서 액션+psuccess 선택 후 Stage 3 진입 → "계속하고 정답 시 +X" (엔진 계산값)와 "포기 시 (확정) S"가 나란히 표시. psuccess를 바꿔 다시 진입하면 X가 갱신됨. 백엔드 미기동 등으로 프리뷰 실패해도 "—"로 표시되고 CONTINUE/FORFEIT는 정상 동작.

- [ ] **Step 4: Commit**

```bash
git add web/app.js web/index.html
git commit -m "feat(web-arena): Stage-3 server-computed reward preview"
```

---

## Self-Review 결과 (작성자 확인 완료)

- **스펙 커버리지:** ①닉네임+pw=Task1-6 · ②이어하기=Task9 · ③진행바+시나리오=Task10 · ④한 줄 rule+?=Task11 · ⑤리워드 프리뷰=Task5+7+12 · 리더보드 best-per-nickname=Task7 · explorer(기존 `/api/logs`로 충족, 신규 작업 없음). baseline 리워드=범위 밖(무작업). 전부 매핑됨.
- **Placeholder:** 없음(모든 코드 단계에 실제 코드). Task5의 `get_optimal_action`은 실제 메서드명 확인 지시를 포함(잠재적 가정 명시).
- **타입 일관성:** `PlayerRecord(nickname, pw_hash, created_at)` / `get_player`/`create_player` / `preview_continue_reward(psuccess_self)` / `reward_preview` 응답 키(`continue_reward_if_correct`, `current_score`)가 백엔드↔프론트에서 일치.
- **주의 플래그:** Task9의 password-in-localStorage 트레이드오프를 명시(대안 전환법 포함).
