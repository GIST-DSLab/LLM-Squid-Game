# 저장소 재구조화 P1–P6 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 저장소를 game / web / DB 3-tier로 가르고, 사후 분석을 측정 채널별로 분해하며, 죽은 것을 정리하고 큰 파일을 쪼갠 뒤 문서와 산출물을 수명별로 나눈다. P0 안전망은 이미 서 있다.

**Architecture:** 여섯 단계가 한 문서에 들어 있지만 **한 번에 실행하는 하나의 작업이 아니다.** 각 단계는 독립 커밋 묶음이고, 되돌리려면 그 묶음만 revert 하면 된다. 단계 사이에는 게이트가 있다 — 앞 단계의 게이트를 통과하지 못한 채 다음 단계를 시작하면, 회귀가 났을 때 어느 단계가 냈는지 판정할 방법이 사라진다. 그것이 P0가 존재하는 이유이자 이 문서가 게이트를 지운 통합본이 아닌 이유다.

순서에는 근거가 있다. P1은 의존 방향의 역순으로 tier를 옮기고(db → web 백엔드 → 프런트 → game), P2는 그 위에서 분석을 채널로 가르며, P3+P4는 제자리를 잡은 파일들의 죽은 서술을 고친다. P5만 순서가 뒤집힌다 — 골든 스냅샷이 런타임 동작을 보지 못하므로 특성화 테스트를 먼저 쓴다. P6은 코드를 거의 건드리지 않고 수명이 다른 것들을 갈라놓는다.

**Tech Stack:** Python 3.12, uv + hatchling, pytest 8 + pytest-asyncio, FastAPI/uvicorn + pydantic v2, pandas · statsmodels · lifelines · scipy, sentence-transformers + scikit-learn, Jinja2, matplotlib, Git LFS, Docker (Render), GitHub Actions (Pages + tests), node --test.

**Spec:** `docs/superpowers/specs/2026-08-30-repo-3tier-restructure-design.md`

**선행 조건:** P0 완료 (`docs/superpowers/plans/2026-08-30-p0-baseline.md`). 기준선은 `958 passed, 91 skipped`, 실패 0. 골든 스냅샷은 `~/golden/squid-restructure/`에 84개 결정적 산출물, 비결정 산출물 0개.

**Task 번호는 단계 안에서만 유효하다.** `P2 · Task 4`가 "Task 1의 `shared/`"를 참조하면 그것은 P2의 Task 1이다. 통합 번호를 매기지 않은 이유가 이것이다 — 30개 태스크에 걸친 상호 참조를 다시 매기면 그 자체가 결함의 원천이 된다.

## Global Constraints

모든 단계에 적용된다. 단계별 추가 제약은 각 Phase 도입부에 따로 적혀 있다.

- 작업 디렉터리는 워크트리 `<repo>/.claude/worktrees/squid-restructure`, 브랜치 `restructure/3tier`. 메인 체크아웃으로 `cd` 하지 않는다. (P0 계획서의 `~/worktrees/squid-restructure`는 실재하지 않는 경로다. `git worktree list`가 출력하는 경로가 정본이다.)
- **테스트 판정은 "전부 초록"이 아니라 "기준선 대비 신규 실패 0"이다.** 명령은 `uv run --extra dev --extra analysis pytest tests/unit -q`.
- **골든 스냅샷이 최종 판정이다.** `uv run python scripts/dev/golden_snapshot.py verify --golden ~/golden/squid-restructure` → exit 0 + `golden snapshot matches: 84 deterministic artefacts`. 파일을 옮긴 태스크마다 돌린다.
- **`outputs/` 아래를 절대 `git add` 하지 않는다.** 723개 `*_turns.jsonl`은 Git LFS 객체이며, 빈 포인터로 덮이면 데이터가 파괴된다.
- **≥10 시즌 런을 삭제·이동하지 않는다.** `outputs/final_results/`의 정규 런 4종은 재현 비용이 크고, 골든 스냅샷 하네스가 그 경로를 하드코딩한다.
- **레거시 코드를 삭제하지 않는다** (스펙 §7). `risk_choice_layer` 계열과 비활성 framing 6종은 아카이브 설정의 재생 경로다. `legacy/`로 표시하되 지우지 않는다.
- **프레임워크·의존성을 교체하지 않는다.** FastAPI, Alpine.js, pydantic은 그대로 둔다.
- **파일을 옮길 때는 `git mv`를 쓴다.** `mv` + `git add`는 rename 추적을 끊어 리뷰를 불가능하게 만든다.
- **과거 기록 문서를 고쳐 쓰지 않는다.** `docs/superpowers/plans/2026-07-*` 등 과거 계획서의 경로 표기는 그 시점의 사실이다. 갱신 대상은 운영 문서(`README.md`, `CLAUDE.md`, `AGENTS.md`, `web/DEPLOY.md`)와 실행되는 스크립트·설정뿐이다.
- macOS `sed`는 `-i ''`가 필요하다. 이 문서의 모든 `sed` 명령이 그 형태다.
- 커밋 메시지·코드·주석·문서는 영어. 대화 보고만 한국어.

## 실행 순서와 게이트

| 단계 | 태스크 수 | 위험 | 게이트 |
|---|---|---|---|
| P1 3-tier 이동 | 6 | 중 | unit 신규 실패 0 · 골든 84 · docker 부팅 |
| P2 분석 4채널 | 7 | 중 | 골든 84 (태스크마다) · 파사드 `__all__` 불변 |
| P3+P4 scripts·죽은 것 | 7 | 낮음 | unit 신규 실패 0 · 골든 84 · 레거시 템플릿 6종 렌더링 |
| P5 큰 파일 분리 | 5 | **높음** | 특성화 스냅샷 7개 동일 · OpenAPI 문서 동일 |
| P6 문서·산출물 | 5 | 낮음 | 전체 스위트 · Pages 아티팩트 경로 |

**단계 게이트를 건너뛰지 않는다.** 게이트가 빨간 채로 다음 단계를 시작하면 그 시점부터 모든 판정이 무의미해진다.

---

# Phase P1 — 3-tier 이동

`src/squid_game` → `game/squid_game`, `interface/` → `web/squid_arena/`, `interface/persistence/` → `db/squid_store/`, `web/*.html|js|css` → `web/frontend/`. 그 과정에서 `sys.path` 조작 13곳과 중복 진입점 2개가 사라진다.

**접근:** 이동은 tier 하나씩 네 번에 나눠 한다. 먼저 잎에 해당하는 DB 계층(`interface/persistence/` → `db/squid_store/`)을 떼고, 그 위의 백엔드(`interface/` 나머지 → `web/squid_arena/`), 그 다음 정적 프런트엔드(`web/*.html|js|css|assets` → `web/frontend/`), 마지막으로 가장 큰 게임 계층(`src/squid_game/` → `game/squid_game/`) 순서다. 이 순서는 의존 방향(`squid_arena → squid_game`, `squid_arena → squid_store`)의 역순이므로, 각 태스크는 자기보다 아래 계층만 이미 옮겨진 상태에서 시작한다. 게임 계층은 **import 이름이 `squid_game`으로 그대로**이므로 577개 참조 중 한 줄도 고칠 필요가 없다 — 바뀌는 것은 패키지가 놓인 경로와 그 경로를 아는 5곳뿐이다. 이동은 전부 `git mv`로 하고, import 치환은 `sed`로 일괄 처리한 뒤 P0 안전망 두 개(unit 스위트 기준선, 골든 스냅샷)로 판정한다.

**추가 제약:**

- **게임 계층의 import 이름은 바뀌지 않는다.** `squid_game` 그대로이므로 577개 참조 중 한 줄도 고칠 필요가 없다. 바뀌는 것은 패키지 경로를 아는 5곳뿐이다.
- **import 이름은 tier 디렉터리 이름과 다르다.** `game`·`web`·`db`를 top-level import 이름으로 쓰지 않는다 (`web`은 PyPI에 실제 점유자가 있다).
- **의존 방향은 단방향이다.** `squid_arena → squid_game`, `squid_arena → squid_store`. `squid_game`은 둘 다 import 하지 않는다.

## P1 File Structure

P1 완료 시점의 최상위:

```
game/
  squid_game/          # 구 src/squid_game — import 이름 불변
web/
  squid_arena/         # 구 interface/ (persistence 제외) + 새 __init__.py
  frontend/            # 구 web/*.html|js|css + assets/
db/
  squid_store/         # 구 interface/persistence/
configs/  scripts/  tests/  outputs/  figures/  docs/
main.py                # runner.main()으로 위임하는 얇은 shim
pyproject.toml         # wheel packages 3개, pytest pythonpath 4개
Dockerfile             # COPY game / web/squid_arena / db, CMD squid_arena.api:app
```

`src/`와 `interface/`는 P1 종료 시 존재하지 않는다.

---

### P1 · Task 1: DB tier 분리 — `db/squid_store/`

가장 아래 계층부터 뗀다. `interface/persistence/`는 어떤 상위 모듈도 import 하지 않는 잎이므로, 옮겨도 깨질 수 있는 것은 자기를 부르는 쪽뿐이다. 참조는 19개 파일에 걸쳐 있고 전부 절대 import(`from interface.persistence...`)이므로 기계적 치환이 성립한다 — `interface/` 안에 상대 import는 한 줄도 없다(실측: `grep -rnE "^from \.|^import \." interface` → 0건).

**Files:**
- Move: `interface/persistence/` → `db/squid_store/` (7파일: `__init__.py`, `base.py`, `factory.py`, `models.py`, `sqlite_repository.py`, `postgres_repository.py`, 그 외)
- Modify (import 치환, 19파일): `interface/api.py`, `interface/arena.py`, `interface/seeding.py`, `db/squid_store/*.py`, `scripts/{backup_web_arena,purge_human_sessions,seed_web_arena}.py`, `tests/integration/{test_arena,test_web_arena_api}.py`, `tests/unit/{test_api_web_arena,test_backup_web_arena,test_persistence,test_repo_model_scores,test_seed_web_arena}.py`
- Modify: `pyproject.toml` (wheel packages, pytest pythonpath, postgres extra 주석)
- Modify: `Dockerfile` (`COPY db ./db` 추가)
- Modify: `tests/unit/test_pytest_ini_options.py` (pythonpath 기대값)
- Create: `tests/unit/test_tier_boundaries.py`

**Interfaces:**
- Consumes: 없음 (P1의 첫 태스크)
- Produces: import 이름 `squid_store`. 공개 표면은 이동 전 `interface.persistence.__init__`의 `__all__` 그대로다: `Repository`, `SessionRecord`, `TurnRecord`, `ModelStatsRecord`, `PlayerRecord`, `get_repository`. 서브모듈 경로도 1:1 대응한다: `squid_store.base`, `squid_store.factory`, `squid_store.models`, `squid_store.sqlite_repository`, `squid_store.postgres_repository`. Task 2가 이 이름으로 import 한다.

- [ ] **Step 1: Write the failing test**

`tests/unit/test_tier_boundaries.py` (신규). 이 파일은 P1 내내 태스크마다 자라며, 3-tier 경계가 실제로 존재하는지를 판정하는 유일한 직접 증거다.

```python
"""The 3-tier split must be real, not just a directory rename.

Three properties are asserted, and each one fails loudly if a later step
undoes it:

1. Each tier's package imports under its own name (``squid_store``,
   ``squid_arena``, ``squid_game``) -- not via a path hack, and not via the
   tier directory name (``db``/``web``/``game`` are deliberately NOT import
   names; ``web`` in particular is taken on PyPI).
2. The pre-restructure names are gone. A leftover ``interface`` package
   would let a stale import keep working and hide a missed call site.
3. The dependency direction runs one way: ``squid_arena`` may reach
   ``squid_game`` and ``squid_store``; neither of those may reach back.
   This is checked by reading source, not by importing -- an import-time
   check would only see modules the test itself happens to load.
"""

from __future__ import annotations

import ast
import importlib
import importlib.util
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]


def _toplevel_imports(package_dir: Path) -> set[str]:
    """Every top-level module name imported anywhere under ``package_dir``."""
    names: set[str] = set()
    for path in package_dir.rglob("*.py"):
        if "__pycache__" in path.parts:
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                names.update(alias.name.split(".")[0] for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
                names.add(node.module.split(".")[0])
    return names


def test_squid_store_imports_under_its_own_name() -> None:
    module = importlib.import_module("squid_store")
    assert module.get_repository is not None
    assert set(module.__all__) == {
        "Repository",
        "SessionRecord",
        "TurnRecord",
        "ModelStatsRecord",
        "PlayerRecord",
        "get_repository",
    }


def test_squid_store_lives_in_the_db_tier() -> None:
    module = importlib.import_module("squid_store")
    assert Path(module.__file__).parent == REPO_ROOT / "db" / "squid_store"


def test_the_old_persistence_package_is_gone() -> None:
    assert not (REPO_ROOT / "interface" / "persistence").exists()
    assert importlib.util.find_spec("interface.persistence") is None


def test_squid_store_depends_on_no_other_tier() -> None:
    imported = _toplevel_imports(REPO_ROOT / "db" / "squid_store")
    assert "squid_arena" not in imported
    assert "squid_game" not in imported
    assert "interface" not in imported
```

- [ ] **Step 2: Run the test to verify it fails**

```bash
uv run --extra dev --extra analysis pytest tests/unit/test_tier_boundaries.py -q
```

Expected: FAIL — `ModuleNotFoundError: No module named 'squid_store'`.

- [ ] **Step 3: Move the package**

```bash
mkdir -p db
git mv interface/persistence db/squid_store
```

- [ ] **Step 4: Rewrite every import site**

```bash
grep -rl "interface\.persistence" --include='*.py' . \
  | grep -v __pycache__ \
  | xargs sed -i '' 's/interface\.persistence/squid_store/g'
```

그 다음 잔여물을 눈으로 확인한다. 문자열·주석에 남은 경로 표기(`interface/persistence/...`)는 자동 치환 대상이 아니므로 따로 고친다:

```bash
grep -rn "interface[./]persistence" --include='*.py' --include='*.toml' --include='*.md' . \
  | grep -v __pycache__ | grep -v '^./docs/superpowers/plans/2026-0[78]'
```

기대: `pyproject.toml:31`의 postgres extra 주석 하나만 남는다. 이를 다음으로 고친다.

```toml
# Web Arena Postgres backend (db/squid_store/postgres_repository.py).
```

- [ ] **Step 5: Register the new package**

`pyproject.toml`:

```toml
[tool.hatch.build.targets.wheel]
packages = ["src/squid_game", "db/squid_store"]
```

```toml
[tool.pytest.ini_options]
# Explicit so the suite does not depend on pytest's rootdir sys.path
# insertion. "." keeps top-level packages importable (interface/ until P1
# finishes moving it); one entry per tier directory keeps that tier's
# package importable without an editable install.
testpaths = ["tests/unit", "tests/integration"]
pythonpath = [".", "src", "db"]
asyncio_mode = "auto"
```

`tests/unit/test_pytest_ini_options.py`의 기대값도 같이 옮긴다:

```python
def test_pythonpath_includes_repo_root_and_every_tier(ini_options: dict) -> None:
    assert ini_options["pythonpath"] == [".", "src", "db"]
```

함수 이름이 바뀌므로 기존 `test_pythonpath_includes_repo_root_and_src`는 남기지 않는다.

- [ ] **Step 6: Keep the image buildable**

`Dockerfile`에서 `COPY src ./src` 바로 아래에 한 줄 추가한다. 이 줄이 없으면 `squid_arena`(현 `interface`)가 import 하는 `squid_store`가 이미지 안에 존재하지 않아 컨테이너가 부팅에 실패한다.

```dockerfile
COPY src ./src
COPY db ./db
COPY interface ./interface
```

- [ ] **Step 7: Run the new test, then the baseline**

```bash
uv run --extra dev --extra analysis pytest tests/unit/test_tier_boundaries.py -q
uv run --extra dev --extra analysis pytest tests/unit -q
```

Expected: 앞은 PASS. 뒤는 `958 passed` 이상 + 신규 실패 0 (새 테스트 4개가 늘어 962 근처가 된다).

- [ ] **Step 8: Verify the image still builds**

```bash
docker build -t squid-arena-p1 . && docker run --rm -e PORT=8599 -d --name squid-p1 squid-arena-p1 \
  && sleep 5 && curl -sf http://127.0.0.1:8599/api/leaderboard/models >/dev/null && echo "image OK"; \
  docker rm -f squid-p1
```

docker가 없는 환경이면 이 단계를 건너뛰되, **건너뛰었다는 사실을 커밋 메시지에 적는다.** Render 배포가 이 파일 하나에 걸려 있으므로 검증하지 않은 채 통과시키지 않는다.

- [ ] **Step 9: Commit**

```bash
git add db tests/unit/test_tier_boundaries.py tests/unit/test_pytest_ini_options.py \
        pyproject.toml Dockerfile interface scripts tests
git commit -m "refactor(db): split persistence out into the db tier"
```

---

### P1 · Task 2: 백엔드 tier 분리 — `web/squid_arena/`

`interface/`의 나머지 9모듈을 `web/squid_arena/`로 옮긴다. 여기서 `interface/api.py`와 `interface/app.py`의 `sys.path.insert` 4줄이 사라진다 — 패키지가 등록되면 필요 없기 때문이다.

`interface/`에는 `__init__.py`가 없다 (namespace package로 우연히 동작해 왔다). `squid_arena`는 명시적 `__init__.py`를 갖는다.

**Files:**
- Move (9파일): `interface/{api,app,arena,auth,human_game,remote_provider,rule_schedule,seeding,anthropic_proxy}.py` → `web/squid_arena/`
- Create: `web/squid_arena/__init__.py`
- Modify (import 치환, 13파일): `web/squid_arena/{api,app,arena}.py`, `scripts/seed_web_arena.py`, `tests/integration/{test_arena,test_web_arena_api}.py`, `tests/unit/{test_api_web_arena,test_auth,test_human_game,test_human_game_preview,test_remote_provider,test_rule_schedule,test_seed_web_arena}.py`
- Modify: `web/squid_arena/api.py:38-41`, `web/squid_arena/app.py:10-13` (sys.path 블록 삭제)
- Modify: `pyproject.toml`, `Dockerfile`, `.dockerignore`, `scripts/start_servers.sh`, `web/DEPLOY.md`, `web/config.js` (주석), `tests/unit/test_tier_boundaries.py`, `tests/unit/test_import_smoke.py`

**Interfaces:**
- Consumes: Task 1의 `squid_store` (`from squid_store import get_repository, SessionRecord, ...`)
- Produces: import 이름 `squid_arena`. ASGI 앱 경로는 `squid_arena.api:app`과 `squid_arena.anthropic_proxy:app`. 모듈 이름은 1:1 대응하며 함수·클래스 시그니처는 한 개도 바뀌지 않는다.

- [ ] **Step 1: Extend the boundary test**

`tests/unit/test_tier_boundaries.py`에 추가한다.

```python
def test_squid_arena_imports_under_its_own_name() -> None:
    module = importlib.import_module("squid_arena.api")
    assert module.app is not None


def test_squid_arena_lives_in_the_web_tier() -> None:
    module = importlib.import_module("squid_arena")
    assert Path(module.__file__).parent == REPO_ROOT / "web" / "squid_arena"


def test_the_old_interface_package_is_gone() -> None:
    assert not (REPO_ROOT / "interface").exists()
    assert importlib.util.find_spec("interface") is None


def test_squid_arena_touches_no_sys_path() -> None:
    """The tier packages exist so nothing has to rewrite sys.path any more."""
    for path in (REPO_ROOT / "web" / "squid_arena").rglob("*.py"):
        if "__pycache__" in path.parts:
            continue
        assert "sys.path" not in path.read_text(encoding="utf-8"), path
```

`squid_arena.api` import는 모듈 스코프에서 `get_repository()`를 호출한다(`api.py:144`). 테스트 파일 맨 위에 sandbox fixture를 둔다 — `test_import_smoke.py`가 같은 이유로 쓰는 것과 동일한 처방이다.

```python
@pytest.fixture(autouse=True)
def _sandbox_repository(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """``squid_arena.api`` opens a repository at import time; keep it in RAM.

    Without this the import falls back to outputs/web_arena/web_arena.db --
    the live dev database -- and runs init_schema against it.
    """
    monkeypatch.setenv("WEB_ARENA_DSN", ":memory:")
    monkeypatch.setenv("SQUID_THINKING_LOG_DIR", str(tmp_path / "thinking_traces"))
```

- [ ] **Step 2: Run the test to verify it fails**

```bash
uv run --extra dev --extra analysis pytest tests/unit/test_tier_boundaries.py -q
```

Expected: FAIL — `ModuleNotFoundError: No module named 'squid_arena'`.

- [ ] **Step 3: Move the modules**

```bash
mkdir -p web/squid_arena
git mv interface/api.py interface/app.py interface/arena.py interface/auth.py \
       interface/human_game.py interface/remote_provider.py interface/rule_schedule.py \
       interface/seeding.py interface/anthropic_proxy.py web/squid_arena/
rmdir interface
```

`rmdir`이 실패하면 `interface/`에 아직 무언가 남아 있다는 뜻이다. `ls -a interface`로 확인하고, `__pycache__`뿐이면 지운다.

- [ ] **Step 4: Give the package an explicit `__init__.py`**

`web/squid_arena/__init__.py`:

```python
"""Web Arena backend -- the FastAPI service and the human-play session layer.

This is the web tier. It may import ``squid_game`` (the game engine) and
``squid_store`` (persistence); neither of those may import back into it.
The tier directory is ``web/`` but the import name is ``squid_arena``:
``web`` is taken on PyPI and would be a hazard as a top-level import name.

Served as ``squid_arena.api:app`` (see the repo-root Dockerfile and
web/DEPLOY.md).
"""
```

- [ ] **Step 5: Rewrite every import site**

```bash
grep -rlE "(from|import) interface\." --include='*.py' . \
  | grep -v __pycache__ \
  | xargs sed -i '' -E 's/\binterface\.(api|app|arena|auth|human_game|remote_provider|rule_schedule|seeding|anthropic_proxy)\b/squid_arena.\1/g'
```

`interface`를 통째로 치환하지 않고 모듈 이름을 하나씩 열거하는 이유는, 문서 문자열과 주석에 등장하는 영어 단어 "interface"(예: `Repository` docstring의 "driver-agnostic repository interface")까지 망가뜨리지 않기 위해서다.

잔여물 확인:

```bash
grep -rn "\binterface\b" --include='*.py' web scripts tests | grep -v __pycache__
```

기대: 영어 산문으로서의 "interface"만 남는다. `import`/`from` 줄에 남은 것이 있으면 그것이 누락이다.

- [ ] **Step 6: Delete the two sys.path blocks**

`web/squid_arena/api.py`에서 삭제:

```python
# Ensure project root is on sys.path.
_project_root = str(Path(__file__).resolve().parent.parent)
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)
```

`web/squid_arena/app.py`에서 삭제:

```python
# Ensure project root is on sys.path so squid_game is importable.
_project_root = str(Path(__file__).resolve().parent.parent)
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)
```

삭제 후 두 파일에서 `sys`와 `Path`가 다른 곳에 쓰이는지 확인하고, 쓰이지 않으면 해당 import도 지운다:

```bash
grep -n "sys\.\|Path(" web/squid_arena/api.py web/squid_arena/app.py | head
```

`app.py`의 docstring `Run with: streamlit run interface/app.py`도 `streamlit run web/squid_arena/app.py`로 고친다.

- [ ] **Step 7: Register the package and repoint the image**

`pyproject.toml`:

```toml
packages = ["src/squid_game", "db/squid_store", "web/squid_arena"]
```

```toml
pythonpath = [".", "src", "db", "web"]
```

`tests/unit/test_pytest_ini_options.py`의 기대값을 `[".", "src", "db", "web"]`로 맞춘다.

`Dockerfile` — `COPY interface ./interface`를 지우고 `COPY web/squid_arena ./web/squid_arena`로 바꾸며, `CMD`의 ASGI 경로도 옮긴다:

```dockerfile
COPY src ./src
COPY db ./db
COPY web/squid_arena ./web/squid_arena
RUN uv sync --frozen --extra postgres --no-dev
...
CMD uv run --no-sync uvicorn squid_arena.api:app --host 0.0.0.0 --port ${PORT:-8502}
```

`.dockerignore` — 현재 `web/`를 통째로 제외하고 있다. 그대로 두면 방금 옮긴 백엔드가 빌드 컨텍스트에서 사라져 `COPY`가 실패한다. 프런트엔드만 제외하도록 좁힌다:

```
# The static frontend is deployed to Pages, not baked into the API image.
# web/squid_arena/ (the backend) must stay in the context -- see Dockerfile.
web/frontend/
web/*.html
web/*.js
web/*.css
web/assets/
web/DEPLOY.md
```

(`web/frontend/`는 Task 3에서 생기고, 나머지 다섯 줄은 그때 지운다. 두 태스크 사이에서는 프런트 정적 파일이 잠시 컨텍스트에 들어오지만 `COPY` 대상이 아니므로 이미지에는 포함되지 않는다.)

`.dockerignore`의 머리 주석도 `interface/` 대신 `web/squid_arena/`를 가리키게 고친다.

- [ ] **Step 8: Repoint the operational scripts and docs**

`scripts/start_servers.sh` — 두 `uvicorn` 호출과 머리 주석:

```bash
sed -i '' 's|interface\.api:app|squid_arena.api:app|; s|interface\.anthropic_proxy:app|squid_arena.anthropic_proxy:app|; s|interface/api\.py, interface/anthropic_proxy\.py|web/squid_arena/api.py, web/squid_arena/anthropic_proxy.py|' scripts/start_servers.sh
```

`web/DEPLOY.md` — 4곳 (`interface/api.py` 2회, `uvicorn interface.api:app` 1회, `interface/api.py::_DEFAULT_CORS_ORIGINS` 2회):

```bash
sed -i '' 's|interface\.api:app|squid_arena.api:app|g; s|interface/api\.py|web/squid_arena/api.py|g' web/DEPLOY.md
```

`web/config.js`의 주석 한 줄도 같은 치환을 적용한다.

- [ ] **Step 9: Update the import smoke walk**

`tests/unit/test_import_smoke.py`의 `PACKAGE_ROOTS`와 `SKIPPED`, 그리고 walk 가드를 옮긴다.

```python
PACKAGE_ROOTS: list[tuple[str, Path]] = [
    ("src", REPO_ROOT / "src"),
    ("scripts", REPO_ROOT),
    ("db", REPO_ROOT / "db"),
    ("web/squid_arena", REPO_ROOT / "web"),
]
```

```python
SKIPPED: dict[str, str] = {
    # Optional dependency, not declared in any pyproject extra.
    "squid_arena.app": "needs streamlit, which is not a declared dependency",
    ...
}
```

```python
def test_the_walk_actually_finds_the_tree() -> None:
    assert len(MODULE_NAMES) > 100
    assert "squid_game.runner" in MODULE_NAMES
    assert "squid_game.analysis.forfeit_regression" in MODULE_NAMES
    assert "scripts.analyze_phase3" in MODULE_NAMES
    assert "squid_arena.api" in MODULE_NAMES
    assert "squid_store.factory" in MODULE_NAMES
```

`test_importing_writes_nothing_into_outputs`의 두 import 이름(`interface.anthropic_proxy`, `interface.api`)과 모듈 docstring의 경로 서술도 같이 옮긴다.

- [ ] **Step 10: Run the tests**

```bash
uv run --extra dev --extra analysis pytest tests/unit/test_tier_boundaries.py tests/unit/test_import_smoke.py -q
uv run --extra dev --extra analysis pytest tests/unit -q
```

Expected: 신규 실패 0.

- [ ] **Step 11: Verify the image again**

Task 1 Step 8과 같은 명령. 이번에는 `CMD`가 바뀌었으므로 컨테이너 부팅까지 반드시 확인한다.

- [ ] **Step 12: Commit**

```bash
git add web db scripts tests pyproject.toml Dockerfile .dockerignore
git commit -m "refactor(web): move the arena backend into the web tier"
```

---

### P1 · Task 3: 프런트엔드 분리 — `web/frontend/`

정적 프런트엔드를 `web/frontend/`로 내려, `web/`가 tier 디렉터리로서 백엔드 패키지와 프런트엔드를 나란히 담게 한다. 파이썬 import는 하나도 관여하지 않지만 **GitHub Pages 배포 경로가 여기에 걸려 있다** — `deploy-pages.yml`의 `path: web`을 같이 옮기지 않으면 배포 산출물에 `squid_arena/` 파이썬 소스가 통째로 올라간다.

**Files:**
- Move: `web/{index.html,about.html,app.js,config.js,rank_ladder.js,styles.css}`, `web/assets/` → `web/frontend/`
- Modify: `.github/workflows/deploy-pages.yml` (`paths:` 필터와 `path:` 아티팩트 경로)
- Modify: `tests/web/rank_ladder.test.mjs` (require 경로)
- Modify: `web/DEPLOY.md` (`cd web` → `cd web/frontend`, 아티팩트 경로 서술)
- Modify: `.dockerignore` (Task 2에서 넣은 임시 5줄을 `web/frontend/` 한 줄로 축약)
- Modify: `tests/unit/test_signal_game_probe_contract.py` (docstring의 `web/app.js` 표기 3곳)

**Interfaces:**
- Consumes: 없음 (파이썬 의존 없음)
- Produces: Pages 아티팩트 루트가 `web/frontend/`. `web/frontend/index.html`이 `config.js` · `app.js` · `rank_ladder.js` · `styles.css`를 **상대 경로**로 참조하므로 디렉터리를 통째로 옮기면 참조는 그대로 성립한다. `web/DEPLOY.md`는 tier 문서로 `web/`에 남는다.

- [ ] **Step 1: Write the failing test**

`tests/web/rank_ladder.test.mjs`가 유일한 프런트 테스트다. 먼저 require 경로를 새 위치로 바꿔 실패시킨다.

```javascript
const { buildRankLadder } = require("../../web/frontend/rank_ladder.js");
```

- [ ] **Step 2: Run it to verify it fails**

```bash
node --test tests/web/
```

Expected: FAIL — `Cannot find module '.../web/frontend/rank_ladder.js'`.

- [ ] **Step 3: Move the frontend**

```bash
mkdir -p web/frontend
git mv web/index.html web/about.html web/app.js web/config.js \
       web/rank_ladder.js web/styles.css web/assets web/frontend/
```

`web/`에는 `squid_arena/`, `frontend/`, `DEPLOY.md`만 남는다. 확인:

```bash
ls web
```

- [ ] **Step 4: Run the frontend test to verify it passes**

```bash
node --test tests/web/
```

Expected: PASS.

- [ ] **Step 5: Repoint the Pages workflow**

`.github/workflows/deploy-pages.yml` — 세 곳이다. 트리거 필터, 아티팩트 경로, 그리고 머리 주석.

```yaml
on:
  push:
    branches:
      - main
    paths:
      - "web/frontend/**"
      - ".github/workflows/deploy-pages.yml"
```

```yaml
      - name: Upload web/frontend as Pages artifact
        uses: actions/upload-pages-artifact@v3
        with:
          path: web/frontend
```

머리 주석의 "Publishes ONLY the web/ directory"도 `web/frontend/`로 고친다. **이 줄이 중요하다** — `path: web`인 채로 두면 백엔드 파이썬 소스가 공개 Pages 사이트에 올라간다.

- [ ] **Step 6: Tidy the dockerignore**

Task 2에서 넣은 임시 5줄을 지우고 한 줄로 줄인다.

```
# The static frontend is deployed to Pages, not baked into the API image.
# web/squid_arena/ (the backend) must stay in the context -- see Dockerfile.
web/frontend/
web/DEPLOY.md
```

- [ ] **Step 7: Update the docs and the contract test's prose**

`web/DEPLOY.md`의 로컬 실행 절차:

```bash
cd web/frontend
python -m http.server 5500
```

그리고 프런트엔드 배포 서술의 `web/` 표기를 `web/frontend/`로 옮긴다.

`tests/unit/test_signal_game_probe_contract.py`의 docstring 3곳(`web/app.js`)을 `web/frontend/app.js`로 고친다. 문자열 상수 자체는 건드리지 않는다 — 이 테스트가 지키는 것은 문법 문자열의 바이트 일치이지 경로가 아니다.

- [ ] **Step 8: Run both suites**

```bash
node --test tests/web/
uv run --extra dev --extra analysis pytest tests/unit -q
```

Expected: 둘 다 신규 실패 0.

- [ ] **Step 9: Commit**

```bash
git add web tests .github/workflows/deploy-pages.yml .dockerignore
git commit -m "refactor(web): move the static frontend under the web tier"
```

---

### P1 · Task 4: 게임 tier 이동 — `game/squid_game/`

가장 큰 이동이지만 가장 싼 이동이다. **import 이름 `squid_game`이 바뀌지 않으므로 577개 참조는 한 줄도 손대지 않는다.** 고칠 곳은 패키지의 물리 경로를 아는 5곳뿐이다: `pyproject.toml` 두 항목, `sys.path`에 `src`를 넣는 스크립트 3개, import smoke의 walk 루트, 테스트 안의 경로 문자열 1개, 그리고 격리 세션 스크립트의 디렉터리 목록.

여기서 분석 코드(`squid_game/analysis/`)가 함께 움직이므로, **이 태스크가 골든 스냅샷을 반드시 통과해야 하는 지점**이다.

**Files:**
- Move: `src/squid_game/` → `game/squid_game/`
- Modify: `pyproject.toml` (wheel packages, pytest pythonpath)
- Modify: `scripts/{analyze_phase3,run_experiment,orchestrate_posthoc}.py` (`_SRC_DIR` 블록 삭제)
- Modify: `tests/unit/test_import_smoke.py` (walk 루트)
- Modify: `tests/unit/test_pytest_ini_options.py` (pythonpath 기대값)
- Modify: `tests/unit/test_api_web_arena.py:1080` (`src/squid_game/prompts/...` 경로 문자열)
- Modify: `scripts/enter_isolated_claude.sh:95` (`"src"` → `"game"`)
- Modify: `web/squid_arena/remote_provider.py:9` (docstring의 `src/squid_game/providers/` 표기)
- Modify: `tests/unit/test_tier_boundaries.py`

**Interfaces:**
- Consumes: Task 1~3의 tier 디렉터리 구조
- Produces: `squid_game` 패키지가 `game/squid_game/`에 존재. import 이름·모듈 경로·공개 API는 **전부 불변**. 이후 P2가 `squid_game.analysis`를 4채널로 쪼갤 때 이 경로를 기준으로 삼는다.

- [ ] **Step 1: Extend the boundary test**

```python
def test_squid_game_lives_in_the_game_tier() -> None:
    module = importlib.import_module("squid_game")
    assert Path(module.__file__).parent == REPO_ROOT / "game" / "squid_game"


def test_the_src_directory_is_gone() -> None:
    assert not (REPO_ROOT / "src").exists()


def test_squid_game_depends_on_no_higher_tier() -> None:
    """The engine must not reach up into the web or db tiers.

    ``core/measurement.py`` and ``analysis/motivation.py`` contain the word
    "persistence", but as the psychological construct (Baseline
    Persistence), not the storage layer -- which is exactly why this check
    reads import statements rather than grepping for the word.
    """
    imported = _toplevel_imports(REPO_ROOT / "game" / "squid_game")
    assert "squid_arena" not in imported
    assert "squid_store" not in imported
    assert "interface" not in imported
```

- [ ] **Step 2: Run it to verify it fails**

```bash
uv run --extra dev --extra analysis pytest tests/unit/test_tier_boundaries.py -q
```

Expected: FAIL — `test_squid_game_lives_in_the_game_tier`가 `.../src/squid_game`을 보고 실패한다.

- [ ] **Step 3: Move the package**

```bash
mkdir -p game
git mv src/squid_game game/squid_game
rmdir src
```

- [ ] **Step 4: Repoint pyproject**

```toml
[tool.hatch.build.targets.wheel]
packages = ["game/squid_game", "web/squid_arena", "db/squid_store"]
```

```toml
pythonpath = [".", "game", "web", "db"]
```

`tests/unit/test_pytest_ini_options.py`의 기대값을 `[".", "game", "web", "db"]`로 맞춘다. `[tool.pytest.ini_options]` 위 주석에서 "interface/ today ... after the restructure"라는 임시 서술을 사실로 갱신한다:

```toml
# Explicit so the suite does not depend on pytest's rootdir sys.path
# insertion. "." keeps scripts/ and tests/ importable as packages; one entry
# per tier directory keeps that tier's package importable without an
# editable install.
```

- [ ] **Step 5: Delete the three `_SRC_DIR` blocks**

`scripts/analyze_phase3.py`, `scripts/run_experiment.py`, `scripts/orchestrate_posthoc.py`에서 각각 삭제한다 (변수명과 줄 수는 세 파일이 동일하다):

```python
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
_SRC_DIR = _PROJECT_ROOT / "src"
if str(_SRC_DIR) not in sys.path:
    sys.path.insert(0, str(_SRC_DIR))
```

`_PROJECT_ROOT`가 아래에서 다른 용도로 쓰이면 그 줄은 남긴다. 확인:

```bash
grep -n "_PROJECT_ROOT\|_SRC_DIR\|^import sys" scripts/analyze_phase3.py scripts/run_experiment.py scripts/orchestrate_posthoc.py
```

`sys`가 더는 쓰이지 않는 파일에서는 `import sys`도 지운다.

이 세 스크립트는 이제 설치된 패키지에 의존한다. `uv run`으로 실행하면 프로젝트가 editable로 설치돼 있으므로 성립하고, 골든 스냅샷 하네스도 venv의 `sys.executable`로 호출하므로 성립한다 (`scripts/dev/golden_snapshot.py:159-163`). 맨 시스템 파이썬으로 `python scripts/analyze_phase3.py`를 돌리는 경로는 이 시점부터 지원하지 않는다.

- [ ] **Step 6: Update the remaining path strings**

```bash
sed -i '' 's|"src/squid_game/prompts/framings/true_baseline.j2"|"game/squid_game/prompts/framings/true_baseline.j2"|' tests/unit/test_api_web_arena.py
sed -i '' 's|^    "src",$|    "game",|' scripts/enter_isolated_claude.sh
sed -i '' 's|src/squid_game/providers/|game/squid_game/providers/|' web/squid_arena/remote_provider.py
```

`tests/unit/test_import_smoke.py`의 walk 루트:

```python
PACKAGE_ROOTS: list[tuple[str, Path]] = [
    ("scripts", REPO_ROOT),
    ("game/squid_game", REPO_ROOT / "game"),
    ("db/squid_store", REPO_ROOT / "db"),
    ("web/squid_arena", REPO_ROOT / "web"),
]
```

모듈 docstring의 "P1 rewrites imports across ``src/``, ``scripts/`` and ``interface/``" 서술도 완료 시제의 사실로 고친다.

남은 `src` 참조를 훑는다:

```bash
grep -rn "\bsrc/\|\"src\"" --include='*.py' --include='*.toml' --include='*.sh' --include='*.yml' \
  scripts tests game web db pyproject.toml .github | grep -v __pycache__
```

기대: 0건.

- [ ] **Step 7: Run the tests**

```bash
uv run --extra dev --extra analysis pytest tests/unit -q
uv run --extra dev --extra analysis pytest tests/integration -q
```

Expected: 신규 실패 0.

- [ ] **Step 8: Run the golden snapshot — the real gate**

```bash
uv run python scripts/dev/golden_snapshot.py verify --golden ~/golden/squid-restructure
```

Expected: exit 0, `golden snapshot matches: 84 deterministic artefacts`.

diff가 하나라도 나오면 **커밋하지 말고 멈춘다.** 분석 파이프라인의 수치가 바뀌었다는 뜻이고, 이동만 한 P1에서는 있을 수 없는 결과다. 원인을 찾을 때까지 진행하지 않는다.

- [ ] **Step 9: Commit**

```bash
git add game scripts tests pyproject.toml web
git commit -m "refactor(game): move the engine package into the game tier"
```

---

### P1 · Task 5: 진입점 3개를 1개로

같은 실험을 세 경로로 실행할 수 있고, 그중 `.env`를 읽는 것은 `main.py` 하나뿐이다. 즉 **어느 경로로 실행했느냐에 따라 API 키가 잡히기도 하고 안 잡히기도 한다.** 실측: `load_dotenv()`는 `main.py:3`과 `scripts/translate_trajectories.py:22` 두 곳에만 있다. 콘솔 스크립트 `squid-game`(`squid_game.runner:main`)과 `scripts/run_experiment.py`는 둘 다 `.env`를 읽지 않는다.

두 CLI의 플래그를 비교하면 `runner.run_experiment_cli()`가 진짜 상위집합이다: `--config`, `--parallel`, `--output-dir`, `--dry-run`에 더해 `--resume`을 갖는다. `scripts/run_experiment.py`에는 `--resume`이 없다. 따라서 위임 방향은 스크립트 → runner이며, 이 위임은 기능을 잃지 않고 오히려 `--resume`을 얻는다.

**Files:**
- Modify: `game/squid_game/runner.py` (`main()`)
- Modify: `main.py`
- Modify: `scripts/run_experiment.py`
- Modify: `README.md`, `CLAUDE.md`, `AGENTS.md` (실행 명령 표기)
- Test: `tests/unit/test_entry_points.py` (신규)

**Interfaces:**
- Consumes: Task 4의 `game/squid_game/runner.py`
- Produces: `squid_game.runner.main()`이 유일한 진입 구현이다. 시그니처는 `def main() -> None`. `main.py`와 `scripts/run_experiment.py`는 이 함수를 호출하는 shim이며 자체 argparse를 갖지 않는다. 정본 실행 명령은 `uv run squid-game --config <path>`.

- [ ] **Step 1: Write the failing test**

`tests/unit/test_entry_points.py`:

```python
"""One entry point, one dotenv load.

Three paths reached the same runner -- ``main.py``, the ``squid-game``
console script, and ``scripts/run_experiment.py`` -- but only ``main.py``
called ``load_dotenv()``. Which path you happened to use decided whether
your API keys were in the environment. These tests pin the fix: the dotenv
load lives inside ``runner.main()``, and the other two are shims that own
no argument parsing of their own.
"""

from __future__ import annotations

import ast
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]


def _calls_in(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
            names.add(node.func.id)
        elif isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
            names.add(node.func.attr)
    return names


def test_runner_main_loads_dotenv() -> None:
    calls = _calls_in(REPO_ROOT / "game" / "squid_game" / "runner.py")
    assert "load_dotenv" in calls


def test_shims_do_not_parse_arguments() -> None:
    """A shim that builds its own parser is a second entry point again."""
    for shim in ("main.py", "scripts/run_experiment.py"):
        source = (REPO_ROOT / shim).read_text(encoding="utf-8")
        assert "ArgumentParser" not in source, shim
        assert "add_argument" not in source, shim


def test_shims_delegate_to_the_runner() -> None:
    for shim in ("main.py", "scripts/run_experiment.py"):
        source = (REPO_ROOT / shim).read_text(encoding="utf-8")
        assert "from squid_game.runner import main" in source, shim
```

- [ ] **Step 2: Run it to verify it fails**

```bash
uv run --extra dev --extra analysis pytest tests/unit/test_entry_points.py -q
```

Expected: 세 개 모두 FAIL.

- [ ] **Step 3: Move the dotenv load into the runner**

`game/squid_game/runner.py`의 `main()`:

```python
def main() -> None:
    """The single entry point (registered as the ``squid-game`` console script).

    ``load_dotenv()`` lives here, not in a wrapper, because the wrappers are
    not the only way in: ``uv run squid-game`` reaches this function
    directly. Loading here means every path -- console script, ``main.py``,
    ``scripts/run_experiment.py`` -- sees the same environment, which was
    not true before: only ``main.py`` loaded ``.env``, so whether your API
    keys were present depended on which command you happened to type.
    """
    from dotenv import load_dotenv

    load_dotenv()
    run_experiment_cli()
```

`load_dotenv`를 함수 안에서 import 하는 이유는 `runner` 모듈을 라이브러리로 import 하는 쪽(분석 코드·테스트)이 `.env` 로딩과 무관해야 하기 때문이다.

- [ ] **Step 4: Reduce the two wrappers to shims**

`main.py` 전체:

```python
"""Thin shim. The canonical entry point is ``uv run squid-game``.

Kept so ``python main.py --config ...`` keeps working for anyone with it in
muscle memory or in a script. It owns no argument parsing: everything,
including the ``.env`` load, lives in ``squid_game.runner.main``.
"""

from squid_game.runner import main

if __name__ == "__main__":
    main()
```

`scripts/run_experiment.py` 전체 (기존 `_build_parser`와 `main` 본문은 삭제한다 — `runner.run_experiment_cli()`가 같은 네 플래그에 `--resume`까지 처리한다):

```python
#!/usr/bin/env python3
"""Thin shim. The canonical entry point is ``uv run squid-game``.

This script used to carry its own argparse, which had drifted: it lacked
``--resume``, so an interrupted experiment could not be continued from
here. Delegating to ``squid_game.runner.main`` closes that gap and removes
the second copy of the CLI.

Usage::

    uv run squid-game --config configs/experiment/v6_signal_game.yaml
    python scripts/run_experiment.py --config configs/experiment/v6_signal_game.yaml
"""

from squid_game.runner import main

if __name__ == "__main__":
    main()
```

- [ ] **Step 5: Run the tests**

```bash
uv run --extra dev --extra analysis pytest tests/unit/test_entry_points.py -q
uv run --extra dev --extra analysis pytest tests/unit -q
```

Expected: 신규 실패 0. `scripts/run_experiment.py`를 import 하던 기존 테스트가 있으면 (`grep -rn "run_experiment" tests/`) 그 테스트가 무엇을 주장하는지 읽고, 삭제된 `_build_parser`에 걸려 있으면 그 주장을 `squid_game.runner`로 옮긴다.

- [ ] **Step 6: Verify the CLI actually runs**

```bash
uv run squid-game --config configs/experiment/v6_signal_game.yaml --dry-run
uv run python main.py --config configs/experiment/v6_signal_game.yaml --dry-run
uv run python scripts/run_experiment.py --config configs/experiment/v6_signal_game.yaml --dry-run
```

세 명령의 출력이 동일해야 한다. `configs/experiment/` 아래 실제 파일명은 `ls configs/experiment/`로 확인한다 (P0가 5종을 복원했다).

- [ ] **Step 7: Update the docs**

`README.md`, `CLAUDE.md`, `AGENTS.md`에서 실험 실행 명령을 찾아 정본 하나로 통일한다:

```bash
grep -rn "run_experiment.py\|python main.py\|squid-game --config" README.md CLAUDE.md AGENTS.md
```

정본 표기는 `uv run squid-game --config <path>`이며, 두 shim은 "레거시 호환 경로"로 한 줄만 언급한다.

- [ ] **Step 8: Commit**

```bash
git add game/squid_game/runner.py main.py scripts/run_experiment.py \
        tests/unit/test_entry_points.py README.md CLAUDE.md AGENTS.md
git commit -m "refactor(cli): collapse three entry points into one"
```

---

### P1 · Task 6: 남은 `sys.path` 조작 제거와 P1 마감

여기까지 오면 `sys.path` 조작 13곳 중 6곳(api.py 2, app.py 2, `_SRC_DIR` 3파일)이 사라져 있다. 남은 것은 두 종류다.

1. **저장소 루트를 넣어 `squid_store`/`squid_arena`를 import 하려는 스크립트 3개** — `scripts/{seed_web_arena,backup_web_arena,purge_human_sessions}.py`. 세 패키지가 설치 대상이 된 지금 불필요하다.
2. **자기 디렉터리를 넣어 형제 모듈을 import 하려는 스크립트 3개** — `scripts/analyze_call1_ri.py`와 `scripts/probe_reasoning_embeddings.py`는 `_ri_dataset`을, `scripts/_trace_split_forfeit_production.py`는 루트를 넣는다. `scripts/__init__.py`가 이미 존재하므로 `from scripts._ri_dataset import ...`로 바꾸면 조작 없이 성립한다. 대신 실행 형태가 `python -m scripts.analyze_call1_ri`가 된다.

**Files:**
- Modify: `scripts/{seed_web_arena,backup_web_arena,purge_human_sessions}.py`
- Modify: `scripts/{analyze_call1_ri,probe_reasoning_embeddings,_trace_split_forfeit_production}.py`
- Modify: `tests/unit/test_tier_boundaries.py`
- Modify: `README.md`, `CLAUDE.md` (구조 블록)
- Modify: `docs/superpowers/plans/2026-08-30-p0-baseline.md` (P1 완료 기록 한 문단 추가)

**Interfaces:**
- Consumes: Task 1~5 전부
- Produces: 저장소 전체에서 `sys.path` 조작 0건. `scripts/analyze_call1_ri.py`와 `scripts/probe_reasoning_embeddings.py`의 실행 형태는 `uv run python -m scripts.<name>`.

- [ ] **Step 1: Extend the boundary test to the whole repo**

```python
def test_no_module_rewrites_sys_path() -> None:
    """The tier packages are installed; nothing needs to patch sys.path.

    Thirteen call sites did before P1. The count is asserted as zero rather
    than as a shrinking number, because "fewer" is not a property anyone can
    hold onto -- the next person to add one would still pass a threshold test.
    """
    offenders: list[str] = []
    for base in ("game", "web", "db", "scripts", "tests"):
        for path in (REPO_ROOT / base).rglob("*.py"):
            if "__pycache__" in path.parts or path.name == "test_tier_boundaries.py":
                continue
            source = path.read_text(encoding="utf-8")
            if "sys.path.insert" in source or "sys.path.append" in source:
                offenders.append(str(path.relative_to(REPO_ROOT)))
    assert offenders == []
```

`test_import_smoke.py`와 `test_pytest_ini_options.py`는 산문에서 `sys.path`를 언급할 뿐 조작하지 않으므로 위 조건(`insert`/`append`)에 걸리지 않는다.

- [ ] **Step 2: Run it to verify it fails**

```bash
uv run --extra dev --extra analysis pytest tests/unit/test_tier_boundaries.py::test_no_module_rewrites_sys_path -q
```

Expected: FAIL, offenders 6~7개가 나열된다.

- [ ] **Step 3: Delete the three repo-root insertions**

`scripts/seed_web_arena.py`, `scripts/backup_web_arena.py`, `scripts/purge_human_sessions.py`에서:

```python
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
```

를 지운다. `seed_web_arena.py`의 위 주석 두 줄("...so the imports below resolve...")도 함께 지운다 — 사실이 아니게 되기 때문이다. `REPO_ROOT` 변수가 다른 용도로 쓰이면 남긴다.

이 세 스크립트에는 `# noqa: E402` 주석이 붙은 import가 있다 (sys.path 조작 뒤에 오는 import라서 달아 둔 것이다). 조작이 사라졌으므로 import를 파일 상단으로 올리고 `# noqa: E402`를 지운다.

- [ ] **Step 4: Convert the sibling imports to package imports**

`scripts/analyze_call1_ri.py`:

```python
# 삭제
sys.path.insert(0, str(Path(__file__).resolve().parent))
```

그리고 `_ri_dataset`을 부르는 import를 고친다:

```python
from scripts._ri_dataset import build_turn_observations
```

실제 심볼 이름은 `grep -n "_ri_dataset" scripts/*.py`로 확인해 그대로 옮긴다.

`scripts/probe_reasoning_embeddings.py`도 동일하게 처리한다.

`scripts/_trace_split_forfeit_production.py`는 `ROOT`를 넣고 나서 "Local imports so the sys.path insertion above takes effect first"라는 주석과 함께 지연 import를 한다. 조작을 지우고 그 import들을 파일 상단으로 올린 뒤 주석도 지운다.

두 파일의 docstring에 실행 예시가 있으면 `-m` 형태로 고친다:

```
    uv run python -m scripts.analyze_call1_ri --out outputs/call1_ri_analysis
```

- [ ] **Step 5: Verify the converted scripts still run**

```bash
uv run python -m scripts.analyze_call1_ri --help
uv run python -m scripts.probe_reasoning_embeddings --help
uv run python scripts/seed_web_arena.py --help
uv run python scripts/backup_web_arena.py --help
uv run python scripts/purge_human_sessions.py --help
```

`--help`가 없는 스크립트는 `python -c "import scripts.<name>"`로 대체한다. 다섯 개 모두 ImportError 없이 끝나야 한다.

- [ ] **Step 6: Run every gate**

```bash
uv run --extra dev --extra analysis pytest tests/unit -q
uv run --extra dev --extra analysis pytest tests/integration -q
node --test tests/web/
uv run python scripts/dev/golden_snapshot.py verify --golden ~/golden/squid-restructure
```

Expected: unit 신규 실패 0, golden `84 deterministic artefacts` + exit 0.

- [ ] **Step 7: Update the structure documentation**

`README.md:110` 부근과 `CLAUDE.md:206` 부근의 디렉터리 구조 블록을 새 3-tier로 고친다. 두 파일 모두 `interface/`를 한 줄로 설명하고 있다. 대체 문구:

```
game/squid_game/      # game tier — engine, tasks, agents, providers, prompts, analysis
web/squid_arena/      # web tier — FastAPI Web Arena backend (api.py), served on Render
web/frontend/         # web tier — static frontend (GitHub Pages)
db/squid_store/       # db tier — repository interface + SQLite/Postgres backends
```

`README.md:127`의 배포 표에서 `interface/api.py`를 `web/squid_arena/api.py`로 고친다.

- [ ] **Step 8: Record the P1 result next to the P0 baseline**

`docs/superpowers/plans/2026-08-30-p0-baseline.md` 끝에 한 문단을 덧붙인다. 기준선 문서가 곧 판정의 근거이므로, 판정 결과도 같은 자리에 남는다.

```markdown
## P1 result

Measured after the last P1 commit, same commands as the baseline above:

- `uv run --extra dev --extra analysis pytest tests/unit -q` -> <실측값>
- `uv run python scripts/dev/golden_snapshot.py verify --golden ~/golden/squid-restructure`
  -> `golden snapshot matches: 84 deterministic artefacts`, exit 0
- New tests added by P1: `tests/unit/test_tier_boundaries.py`,
  `tests/unit/test_entry_points.py`.

New failures against the baseline list: <실측값>.
```

`<실측값>`은 실제 출력으로 채운다. 추정치를 적지 않는다.

- [ ] **Step 9: Commit**

```bash
git add scripts tests README.md CLAUDE.md docs/superpowers/plans/2026-08-30-p0-baseline.md
git commit -m "refactor: drop the last sys.path rewrites and record the P1 result"
```

---

---

## P1 게이트

P1은 다음이 모두 참일 때 끝난다.

1. `src/`와 `interface/`가 존재하지 않는다.
2. `game/squid_game/`, `web/squid_arena/`, `web/frontend/`, `db/squid_store/`가 존재하고, 앞의 셋 중 파이썬 패키지 셋이 `pyproject.toml`의 wheel packages에 등록돼 있다.
3. `sys.path.insert` / `sys.path.append`가 저장소에 0건이다.
4. `uv run --extra dev --extra analysis pytest tests/unit -q`가 P0 기준선(`958 passed, 91 skipped`) 대비 **신규 실패 0**이다.
5. `golden_snapshot.py verify`가 exit 0과 `84 deterministic artefacts`를 낸다.
6. `docker build`가 성공하고 컨테이너가 `/api/leaderboard/models`에 응답한다.
7. `node --test tests/web/`가 통과한다.
8. `.github/workflows/deploy-pages.yml`의 아티팩트 경로가 `web/frontend`다 (`web`이 아니다 — `web`이면 백엔드 소스가 공개된다).

### P1 범위 밖

- 분석 4채널 분해 (P2)
- `scripts/` 49개의 5분류 (P3)
- 죽은 주석 182건, `interface/app.py`의 생사 판정, `core/legacy/` 격리 (P4)
- `unified_turn.py` · `api.py` 책임 분리 (P5)
- 문서 4분할, `outputs/` → `results/` 분리 (P6)
- 과거 계획서(`docs/superpowers/plans/2026-07-*` 등)의 경로 표기

---

# Phase P2 — 분석 4채널 분해

`analysis/` 15모듈 7,602줄을 인지 · 자기보고 · 행동 · 의미 채널로 재조립하고, 두 채널에 걸친 두 모듈을 실제로 쪼갠다.

**접근:** 이동의 안전망은 **파사드**다. `squid_game/analysis/__init__.py`가 이미 모든 공개 심볼을 re-export 하고 있으므로, 그 파일의 import 줄만 새 경로로 갱신하면 파사드를 통해 들어오는 호출자는 한 줄도 바뀌지 않는다. 다만 실측 결과 서브모듈을 직접 import 하는 곳이 45군데 있으므로(`squid_game.analysis.forfeit_regression` 7건, `.threat_judge` 9건 등), 각 태스크는 자기가 옮긴 모듈의 직접 import만 `sed`로 좁혀 치환한다. 순서는 위험도 순이다: 먼저 통째로 옮기면 되는 모듈들(shared · behavioral · cognitive · semantic), 그 다음 진짜 분할이 필요한 두 모듈(`forfeit_regression` 952줄, `regime_stratification` 656줄), 마지막이 채널 위에 서는 MTMM 종합기다. 매 태스크의 판정은 골든 스냅샷 84개 산출물의 바이트 동일성이다 — 분해가 수치를 건드렸다면 그 자리에서 드러난다.

**추가 제약:**

- **통계 모델 식을 건드리지 않는다.** mixedLM formula 문자열, Cox PH covariate 목록, 부트스트랩 반복 수, 시드, 유의수준은 옮기기만 한다.
- **파사드를 깨지 않는다.** `squid_game.analysis.__all__`은 P2 전후로 동일해야 한다. 심볼 추가는 되지만 제거·개명은 안 된다.
- **범위 밖:** R2 비례검정 구현, FDR 보정, 새 분석 추가 (스펙 §8).

## P2 File Structure

P2 완료 시점:

```
game/squid_game/analysis/
  __init__.py                  # 파사드. __all__ 불변
  shared/
    loaders.py  export.py  metrics.py
    discovery_detection.py  manipulation_check.py
    mtmm.py                    # 구 motivation.py — 채널 추정기를 호출하는 종합기
  cognitive/                   # RI = thinking_tokens
    ri_forfeit.py  ri_task.py  ri_call1.py
  selfreport/                  # REASON digit, psuccess_self
    reason_convergence.py  psuccess.py
  behavioral/                  # 선택 · 생존
    survival.py  regime.py  session_tests.py  baseline_persistence.py
  semantic/                    # 텍스트 · 임베딩
    dataset.py  embeddings.py  lexicon.py
    threat_registration.py  threat_judge.py
```

`scripts/probe_reasoning_embeddings.py`, `scripts/probe_lexicon.py`, `scripts/analyze_call1_ri.py`는 얇은 CLI만 남고 로직은 위로 올라간다. `scripts/_ri_dataset.py`는 사라진다(`semantic/dataset.py`가 된다).

---

### P2 · Task 1: `shared/` 하위 패키지 — 채널이 공유하는 것부터

다섯 모듈은 채널에 속하지 않는다. 데이터 적재(`loaders`), 산출(`export`), 기술통계(`metrics`), 규칙 발견 탐지(`discovery_detection`), 조작 점검(`manipulation_check`)은 세 채널이 모두 소비한다. 먼저 이들을 `shared/`로 내려 채널 디렉터리가 생길 자리를 만든다.

**Files:**
- Move: `analysis/{loaders,export,metrics,discovery_detection,manipulation_check}.py` → `analysis/shared/`
- Create: `analysis/shared/__init__.py`
- Modify: `analysis/__init__.py` (import 경로 5줄)
- Modify: 직접 import 하는 외부 호출자 (`loaders` 4건, `manipulation_check` 4건, `metrics` 1건, `export` 1건, `discovery_detection` 1건)
- Modify: `analysis/` 내부에서 이 다섯을 import 하는 모듈 전부
- Test: `tests/unit/test_analysis_channels.py` (신규)

**Interfaces:**
- Consumes: 없음 (P2의 첫 태스크)
- Produces: `squid_game.analysis.shared.loaders` 등 5모듈. 함수 시그니처는 전부 불변. `analysis/__init__`의 `__all__`도 불변이므로 파사드 경유 호출자는 영향받지 않는다.

- [ ] **Step 1: Write the failing test**

`tests/unit/test_analysis_channels.py` (신규). 이 파일은 P2 내내 태스크마다 자라며, "채널 분해가 디렉터리 이름뿐인 분해가 아님"을 판정한다.

```python
"""The analysis split must be by measurement channel, not by convenience.

Two properties are pinned:

1. The facade is stable. ``squid_game.analysis.__all__`` is what the
   pipeline and the tests import through; P2 moves modules underneath it
   and must not change what comes out the front.
2. Each channel package holds only its own channel's estimators, and the
   shared layer holds no channel-specific model fitting. Asserted by
   naming modules explicitly -- a predicate would drift as files move.
"""

from __future__ import annotations

import importlib
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
ANALYSIS = REPO_ROOT / "game" / "squid_game" / "analysis"


def test_the_facade_still_exports_everything() -> None:
    module = importlib.import_module("squid_game.analysis")
    for name in module.__all__:
        assert hasattr(module, name), name


def test_shared_layer_holds_the_cross_channel_modules() -> None:
    expected = {
        "loaders.py",
        "export.py",
        "metrics.py",
        "discovery_detection.py",
        "manipulation_check.py",
        "__init__.py",
    }
    assert {p.name for p in (ANALYSIS / "shared").glob("*.py")} == expected


def test_the_flat_layout_is_gone() -> None:
    """A module left at the top level is a module nobody assigned a channel."""
    stray = {p.name for p in ANALYSIS.glob("*.py")} - {"__init__.py"}
    assert stray == set()
```

세 번째 테스트는 Task 7까지 실패한 채로 남는다. 그 전까지는 `pytest.mark.xfail(reason="channels land in Tasks 2-7")`을 붙이고, Task 7에서 마커를 뗀다.

- [ ] **Step 2: Run it to verify it fails**

```bash
uv run --extra dev --extra analysis pytest tests/unit/test_analysis_channels.py -q
```

Expected: `test_shared_layer_holds_the_cross_channel_modules`가 FAIL (`shared/`가 없다).

- [ ] **Step 3: Move the five modules**

```bash
cd game/squid_game/analysis
mkdir -p shared
git mv loaders.py export.py metrics.py discovery_detection.py manipulation_check.py shared/
cd -
```

- [ ] **Step 4: Give `shared/` an `__init__.py`**

`game/squid_game/analysis/shared/__init__.py`:

```python
"""Inputs and outputs every measurement channel shares.

Nothing here fits a single channel: ``loaders`` reads the run artefacts,
``export`` writes them, ``metrics`` computes descriptive summaries,
``discovery_detection`` locates the rule-discovery turn, and
``manipulation_check`` verifies the framing manipulation landed. Channel
estimators live in ``cognitive/``, ``selfreport/``, ``behavioral/`` and
``semantic/``; this package is what they read from and write to.

``mtmm`` joins them in Task 7: it sits ABOVE the channels rather than in
one, because it triangulates their estimates.
"""
```

- [ ] **Step 5: Rewrite the import sites**

```bash
grep -rl "squid_game\.analysis\.\(loaders\|export\|metrics\|discovery_detection\|manipulation_check\)" \
  --include='*.py' game scripts tests web \
  | xargs sed -i '' -E 's/squid_game\.analysis\.(loaders|export|metrics|discovery_detection|manipulation_check)\b/squid_game.analysis.shared.\1/g'
```

`analysis/` 패키지 내부에서 형제를 부르던 import도 같은 치환에 포함된다 (전부 절대 경로 형태다). 잔여물 확인:

```bash
grep -rn "analysis\.\(loaders\|export\|metrics\|discovery_detection\|manipulation_check\)" --include='*.py' game scripts tests | grep -v "analysis\.shared"
```

기대: 0건.

- [ ] **Step 6: Run the gates**

```bash
uv run --extra dev --extra analysis pytest tests/unit -q
uv run python scripts/dev/golden_snapshot.py verify --golden ~/golden/squid-restructure
```

Expected: 신규 실패 0, `84 deterministic artefacts`.

- [ ] **Step 7: Commit**

```bash
git add game/squid_game/analysis scripts tests
git commit -m "refactor(analysis): lift the cross-channel modules into shared/"
```

---

### P2 · Task 2: `behavioral/` — 선택과 생존 그 자체

행동 채널은 "무엇을 택했고 얼마나 버텼는가"만 본다. 통째로 옮길 수 있는 두 모듈이 여기 속한다: `forfeit_survival.py`(H1 Cox PH, 587줄)와 `unit13_hypotheses.py`(세션 수준 H1–H6, 472줄).

**Files:**
- Move: `analysis/forfeit_survival.py` → `analysis/behavioral/survival.py`
- Move: `analysis/unit13_hypotheses.py` → `analysis/behavioral/session_tests.py`
- Create: `analysis/behavioral/__init__.py`
- Modify: `analysis/__init__.py`, 직접 import 3건(`analysis.unit...`), 테스트

**Interfaces:**
- Consumes: Task 1의 `analysis.shared.loaders`
- Produces: `squid_game.analysis.behavioral.survival` — `build_survival_frame`, `CoxSurvivalResult`, `fit_cox_forfeit_survival`, `km_forfeit_curves`, `run_h1_survival_hypothesis`. `squid_game.analysis.behavioral.session_tests` — `UnitThirteenResult`, `session_features`, `test_h1_forfeit_rate` … `test_h6_post_discovery_engagement`, `run_all_unit13_hypotheses`. 시그니처 전부 불변.

- [ ] **Step 1: Extend the channel test**

```python
def test_behavioral_channel_holds_choice_and_survival() -> None:
    expected = {"survival.py", "session_tests.py", "__init__.py"}
    assert {p.name for p in (ANALYSIS / "behavioral").glob("*.py")} >= expected


def test_behavioral_estimators_are_reachable_through_the_facade() -> None:
    module = importlib.import_module("squid_game.analysis")
    assert module.fit_cox_forfeit_survival is not None
    assert module.run_all_unit13_hypotheses is not None
```

`>=`를 쓰는 이유는 Task 5와 Task 7이 이 디렉터리에 `regime.py`와 `baseline_persistence.py`를 더 넣기 때문이다.

- [ ] **Step 2: Run it to verify it fails**

```bash
uv run --extra dev --extra analysis pytest tests/unit/test_analysis_channels.py -q
```

Expected: FAIL — `behavioral/`가 없다.

- [ ] **Step 3: Move and rename**

```bash
cd game/squid_game/analysis
mkdir -p behavioral
git mv forfeit_survival.py behavioral/survival.py
git mv unit13_hypotheses.py behavioral/session_tests.py
cd -
```

- [ ] **Step 4: Write the package docstring**

`game/squid_game/analysis/behavioral/__init__.py`:

```python
"""Behavioural channel -- what the model did, not what it said or thought.

Two families live here. ``survival`` is the H1 Cox proportional-hazards
model over time-to-forfeit; ``session_tests`` is the session-level H1-H6
battery (Appendix A.4). Both read only choices and outcomes: forfeit or
continue, stake taken, turns survived. Nothing here reads thinking tokens
(that is ``cognitive/``) or the REASON digit (that is ``selfreport/``).
"""
```

- [ ] **Step 5: Rewrite the import sites**

```bash
grep -rl "squid_game\.analysis\.forfeit_survival\|squid_game\.analysis\.unit13_hypotheses" --include='*.py' game scripts tests \
  | xargs sed -i '' -e 's/squid_game\.analysis\.forfeit_survival/squid_game.analysis.behavioral.survival/g' \
                    -e 's/squid_game\.analysis\.unit13_hypotheses/squid_game.analysis.behavioral.session_tests/g'
```

- [ ] **Step 6: Run the gates**

```bash
uv run --extra dev --extra analysis pytest tests/unit -q
uv run python scripts/dev/golden_snapshot.py verify --golden ~/golden/squid-restructure
```

- [ ] **Step 7: Commit**

```bash
git add game/squid_game/analysis scripts tests
git commit -m "refactor(analysis): gather the behavioural channel"
```

---

### P2 · Task 3: `cognitive/` — RI(thinking tokens)를 읽는 것들

인지 채널의 지표는 하나다: `thinking_tokens`에서 나온 RI. 통째로 옮길 수 있는 것은 `tc_regression.py`(931줄, R1/TC 지표) 하나이고, 나머지 둘은 Task 4(`forfeit_regression` 분할)와 이번 태스크의 CLI 승격에서 온다.

`scripts/analyze_call1_ri.py`(305줄)는 Call-1 RI 회귀 모델과 CLI를 한 파일에 담고 있다. 모델부를 `cognitive/ri_call1.py`로 올리고 스크립트에는 argparse와 리포트 방출만 남긴다.

**Files:**
- Move: `analysis/tc_regression.py` → `analysis/cognitive/ri_task.py`
- Create: `analysis/cognitive/__init__.py`, `analysis/cognitive/ri_call1.py`
- Modify: `scripts/analyze_call1_ri.py` (모델 함수 제거, import로 대체)
- Modify: `analysis/__init__.py`, 직접 import 1건

**Interfaces:**
- Consumes: Task 1의 `analysis.shared.loaders`
- Produces: `squid_game.analysis.cognitive.ri_task` — `TCRegressionResult`, `TCReverseCheckResult`, `TCCoxResult`, `add_correct_prev`, `add_rule_match_prev`, `fit_tc_rule_mastery_cell0`, `fit_tc_rule_mastery_allowed`, `fit_tc_reverse_check`, `fit_tc_streak_robustness`, `fit_tc_cox_rule_mastery`, `discovery_timing_alignment`, `beta_C_by_phase`, `run_all_tc_indicators`. `squid_game.analysis.cognitive.ri_call1` — `scripts/analyze_call1_ri.py`에서 올라온 모델 함수들 (정확한 이름은 Step 3에서 실측해 그대로 유지한다).

- [ ] **Step 1: Extend the channel test**

```python
def test_cognitive_channel_holds_the_ri_estimators() -> None:
    expected = {"ri_task.py", "ri_call1.py", "__init__.py"}
    assert {p.name for p in (ANALYSIS / "cognitive").glob("*.py")} >= expected


def test_call1_script_is_a_thin_cli() -> None:
    """The model belongs in the package; the script owns only the CLI.

    Pinned by size rather than by naming every function: the point is that
    the statistics stopped living in scripts/, and a threshold states that
    without freezing the CLI's internals.
    """
    source = (REPO_ROOT / "scripts" / "analyze_call1_ri.py").read_text(encoding="utf-8")
    assert "from squid_game.analysis.cognitive.ri_call1 import" in source
    assert len(source.splitlines()) < 150
```

- [ ] **Step 2: Run it to verify it fails**

Expected: 둘 다 FAIL.

- [ ] **Step 3: Move `tc_regression` and lift the Call-1 model**

```bash
cd game/squid_game/analysis
mkdir -p cognitive
git mv tc_regression.py cognitive/ri_task.py
cd -
```

`scripts/analyze_call1_ri.py`를 읽고 다음 기준으로 자른다. **위로 올라가는 것**: DataFrame을 받아 통계 결과를 돌려주는 함수 전부(회귀 적합, 효과크기, 대조 계산). **스크립트에 남는 것**: argparse, 출력 경로 결정, 마크다운·JSON 방출, `if __name__ == "__main__"`.

함수 이름은 옮기면서 바꾸지 않는다. 실측 목록:

```bash
grep -n "^def \|^class \|^@dataclass" scripts/analyze_call1_ri.py
```

이 목록을 그대로 `cognitive/ri_call1.py`로 옮기되, `_write_*` / `_render_*` / `main` 계열만 스크립트에 남긴다.

- [ ] **Step 4: Write the package docstring**

`game/squid_game/analysis/cognitive/__init__.py`:

```python
"""Cognitive channel -- reasoning intensity, measured as thinking tokens.

``ri_task`` is the R1/TC family: does rule mastery move task-directed
reasoning? ``ri_forfeit`` (Task 4) is the H2 choice x framing model on the
forfeit decision. ``ri_call1`` is the Call-1 regression: whether the threat
framing raises reasoning before any decision is on the table.

All three read ``thinking_tokens`` and nothing else. The REASON digit the
model reports about its own reasoning is a different channel -- see
``selfreport/`` -- and keeping them apart is the point of the split: a
dissociation between them is only visible if they are estimated separately.
"""
```

- [ ] **Step 5: Rewrite the import sites**

```bash
grep -rl "squid_game\.analysis\.tc_regression" --include='*.py' game scripts tests \
  | xargs sed -i '' 's/squid_game\.analysis\.tc_regression/squid_game.analysis.cognitive.ri_task/g'
```

`analysis/__init__.py`에 `ri_call1`의 공개 심볼을 추가 export 한다 (`__all__`에 추가하는 것은 허용된다 — 제거·개명만 금지다).

- [ ] **Step 6: Verify the Call-1 script still reproduces its output**

이 산출물은 골든 스냅샷 84개에 포함되지 않는다(`outputs/call1_ri_analysis/`는 정규 런의 `phase3_analysis/` 밖이다). 따라서 직접 비교한다.

```bash
cp outputs/call1_ri_analysis/call1_ri_results.json /tmp/call1_before.json
uv run python -m scripts.analyze_call1_ri
diff <(python -c "import json,sys;print(json.dumps(json.load(open('/tmp/call1_before.json')),sort_keys=True,indent=2))") \
     <(python -c "import json,sys;print(json.dumps(json.load(open('outputs/call1_ri_analysis/call1_ri_results.json')),sort_keys=True,indent=2))")
```

Expected: diff 없음. 차이가 나면 승격 과정에서 로직이 바뀐 것이다 — 커밋하지 말고 되돌린다.

- [ ] **Step 7: Run the gates and commit**

```bash
uv run --extra dev --extra analysis pytest tests/unit -q
uv run python scripts/dev/golden_snapshot.py verify --golden ~/golden/squid-restructure
git add game/squid_game/analysis scripts tests
git commit -m "refactor(analysis): gather the cognitive channel and thin the Call-1 CLI"
```

---

### P2 · Task 4: `forfeit_regression.py` 분할 — 인지와 자기보고를 가른다

952줄짜리 이 모듈이 채널 분리의 의미를 무효화하는 지점이다. H2 인지 모델(`fit_choice_asymmetric_model`, `fit_task_spillover_model`)과 자기보고 REASON 수렴(`reason_distribution`, `thinking_keyword_counts`, `fit_framing_ri_forfeit_continue`)이 한 파일에 들어 있고, 그 위에 세 채널이 모두 쓰는 `turn_observations()`가 얹혀 있다.

셋으로 가른다: `turn_observations`와 `forfeit_events`는 `shared/loaders.py`로, 인지 모델은 `cognitive/ri_forfeit.py`로, 자기보고 부분은 `selfreport/reason_convergence.py`로.

**Files:**
- Create: `analysis/cognitive/ri_forfeit.py`, `analysis/selfreport/__init__.py`, `analysis/selfreport/reason_convergence.py`
- Modify: `analysis/shared/loaders.py` (`turn_observations`, `forfeit_events` 수용)
- Delete: `analysis/forfeit_regression.py` (내용이 셋으로 흩어진 뒤)
- Modify: `analysis/__init__.py`, 직접 import 7건

**Interfaces:**
- Consumes: Task 1의 `shared/`, Task 3의 `cognitive/`
- Produces:
  - `shared.loaders.turn_observations(seasons) -> pd.DataFrame`, `shared.loaders.forfeit_events(seasons) -> pd.DataFrame` (이동만, 시그니처 불변)
  - `cognitive.ri_forfeit` — `ChoiceAsymmetricResult`, `fit_choice_asymmetric_model`, `TaskSpilloverResult`, `fit_task_spillover_model`, `run_all_unit15_hypotheses`, `unit15_descriptive_summary`
  - `selfreport.reason_convergence` — `reason_distribution`, `thinking_keyword_counts`, `FramingRiForfeitContinueResult`, `fit_framing_ri_forfeit_continue`, `run_all_unit14_hypotheses`
- 모듈 상수 `_CORRUPTION_FRAMINGS`, `_BASELINE_FRAMINGS`, `_MIN_TURNS_FOR_LOGIT`은 **두 파일 모두가 쓴다.** 복제하지 말고 `shared/loaders.py`로 올려 두 쪽이 import 한다.

- [ ] **Step 1: Extend the channel test**

```python
def test_forfeit_regression_actually_split() -> None:
    assert not (ANALYSIS / "forfeit_regression.py").exists()
    assert (ANALYSIS / "cognitive" / "ri_forfeit.py").exists()
    assert (ANALYSIS / "selfreport" / "reason_convergence.py").exists()


def test_the_framing_sets_are_defined_once() -> None:
    """A split that copies the constants is a split that will drift apart."""
    hits = [
        path.name
        for path in ANALYSIS.rglob("*.py")
        if "_CORRUPTION_FRAMINGS: frozenset" in path.read_text(encoding="utf-8")
    ]
    assert hits == ["loaders.py"]


def test_shared_loaders_owns_turn_observations() -> None:
    loaders = importlib.import_module("squid_game.analysis.shared.loaders")
    assert callable(loaders.turn_observations)
    assert callable(loaders.forfeit_events)
```

- [ ] **Step 2: Run it to verify it fails**

Expected: 세 개 모두 FAIL.

- [ ] **Step 3: Lift the shared inputs first**

`analysis/forfeit_regression.py:91-284`의 `turn_observations`와 `forfeit_events`, 그리고 `:55-69`의 세 상수를 `analysis/shared/loaders.py` 끝으로 옮긴다. `loaders.py`가 이미 import 하지 않는 심볼(`SeasonResult`, `pd`)이 필요하면 import를 추가한다.

옮긴 자리에 남길 주석 대신, `loaders.py`의 `turn_observations` docstring에 왜 여기 있는지를 한 줄 적는다:

```python
def turn_observations(seasons: Sequence[SeasonResult]) -> pd.DataFrame:
    """Turn-level frame consumed by every channel.

    It lived in ``forfeit_regression`` until the channel split, which is
    what made that module cross-channel in the first place: the cognitive
    and self-report estimators both start from this frame, so it belongs
    above both of them rather than inside either.
    """
```

- [ ] **Step 4: Create the cognitive half**

`git mv`로 rename 추적을 남긴다 — 인지 쪽이 원본에서 더 큰 덩어리다.

```bash
git mv game/squid_game/analysis/forfeit_regression.py game/squid_game/analysis/cognitive/ri_forfeit.py
```

그 다음 `ri_forfeit.py`에서 자기보고 함수 5개(`reason_distribution`, `thinking_keyword_counts`, `FramingRiForfeitContinueResult`, `fit_framing_ri_forfeit_continue`, `run_all_unit14_hypotheses`)와 Step 3에서 이미 올린 함수·상수를 삭제하고, 상수는 `from squid_game.analysis.shared.loaders import _BASELINE_FRAMINGS, ...`로 바꾼다.

- [ ] **Step 5: Create the self-report half**

`game/squid_game/analysis/selfreport/reason_convergence.py`에 Step 4에서 삭제한 다섯을 그대로 옮긴다. **본문을 다시 쓰지 않는다** — 잘라 붙인다. 함수 하나라도 다시 타이핑하면 골든 스냅샷이 잡아내겠지만, 잡아낸 뒤 원인을 찾는 비용이 그 자체로 낭비다.

`game/squid_game/analysis/selfreport/__init__.py`:

```python
"""Self-report channel -- what the model says about its own decision.

Two instruments. ``reason_convergence`` reads the REASON digit emitted with
a forfeit/continue choice and asks whether it converges with the framing
manipulation. ``psuccess`` (Task 5) reads the model's own success estimate
and the expected value it implies.

This channel is deliberately separate from ``cognitive/``: a model whose
thinking tokens rise while its stated reason does not move is the
dissociation the study is looking for, and it is unmeasurable if the two
are estimated in one file.
"""
```

- [ ] **Step 6: Repoint the 7 direct import sites**

```bash
grep -rn "squid_game\.analysis\.forfeit_regression" --include='*.py' game scripts tests
```

각 호출자가 어느 심볼을 쓰는지 보고 채널에 맞게 나눠 고친다. 한 파일이 양쪽 심볼을 모두 쓰면 import 두 줄이 된다. 일괄 `sed`가 성립하지 않는 유일한 태스크다 — 손으로 고치고, 위 `grep`이 0건이 될 때까지 반복한다.

- [ ] **Step 7: Run the gates**

```bash
uv run --extra dev --extra analysis pytest tests/unit -q
uv run --extra dev --extra analysis pytest tests/integration -q
uv run python scripts/dev/golden_snapshot.py verify --golden ~/golden/squid-restructure
```

Expected: 신규 실패 0, `84 deterministic artefacts`. **이 태스크가 P2에서 골든 스냅샷이 가장 중요한 지점이다** — `unit14_*` 산출물 6종이 방금 쪼갠 코드에서 나온다.

- [ ] **Step 8: Commit**

```bash
git add game/squid_game/analysis scripts tests
git commit -m "refactor(analysis): split forfeit_regression along the channel it crossed"
```

---

### P2 · Task 5: `regime_stratification.py` 분할 — 자기보고 EV와 행동 층화

656줄. `p_self` 기반 EV 계산(자기보고)과 no_cap/cap regime 층화(행동)가 겹쳐 있다. 층화 로직과 Cox 재적합은 행동 채널로, EV 계산은 자기보고 채널로 간다.

**Files:**
- Create: `analysis/behavioral/regime.py`, `analysis/selfreport/psuccess.py`
- Delete: `analysis/regime_stratification.py`
- Modify: `analysis/__init__.py`, 직접 import 5건

**Interfaces:**
- Consumes: Task 4의 `shared.loaders.turn_observations`, `behavioral.survival.fit_cox_forfeit_survival`
- Produces:
  - `behavioral.regime` — `annotate_regime`, `annotate_events_regime`, `filter_regime`, `stratified_counts`, `StratifiedCoxResult`, `run_stratified_unit14`, `render_regime_markdown`
  - `selfreport.psuccess` — `p_self` 추출과 EV 계산 함수. 이름은 원본에서 그대로 옮긴다 (`stratified_reason_distribution`은 REASON 분포이므로 자기보고 쪽이다).
- 포맷 헬퍼 `_fmt_pct`, `_fmt_float`, `_df_to_markdown`은 마크다운 방출용이며 `behavioral/regime.py`의 `render_regime_markdown`만 쓴다. 함께 옮긴다.

- [ ] **Step 1: Extend the channel test**

```python
def test_regime_stratification_actually_split() -> None:
    assert not (ANALYSIS / "regime_stratification.py").exists()
    assert (ANALYSIS / "behavioral" / "regime.py").exists()
    assert (ANALYSIS / "selfreport" / "psuccess.py").exists()
```

- [ ] **Step 2: Run it to verify it fails**

- [ ] **Step 3: Read the module and draw the line**

```bash
grep -n "p_self\|expected_value\|\bev\b\|psuccess" game/squid_game/analysis/regime_stratification.py
```

`p_self` / `psuccess` / EV를 읽거나 계산하는 함수는 자기보고, `regime` 라벨을 붙이거나 그 라벨로 자르거나 층별로 Cox를 다시 적합하는 함수는 행동이다. 경계가 모호한 함수가 나오면 **입력이 무엇인가**로 판정한다: 모델이 스스로 보고한 숫자를 읽으면 자기보고, 실제 선택·생존만 읽으면 행동.

- [ ] **Step 4: Split**

```bash
git mv game/squid_game/analysis/regime_stratification.py game/squid_game/analysis/behavioral/regime.py
```

자기보고 쪽 함수를 잘라 `selfreport/psuccess.py`로 옮기고, `regime.py`에 남은 참조를 import로 바꾼다. 방향은 한쪽이다: `behavioral/regime.py`가 `selfreport/psuccess.py`를 import 하는 것은 허용하되 그 역은 만들지 않는다 (층화는 EV를 필요로 하지만 EV 계산은 층화를 모른다).

- [ ] **Step 5: Repoint the 5 direct import sites**

```bash
grep -rn "squid_game\.analysis\.regime_stratification" --include='*.py' game scripts tests
```

Task 4와 같은 요령으로 손으로 고친다.

- [ ] **Step 6: Run the gates and commit**

```bash
uv run --extra dev --extra analysis pytest tests/unit -q
uv run python scripts/dev/golden_snapshot.py verify --golden ~/golden/squid-restructure
git add game/squid_game/analysis scripts tests
git commit -m "refactor(analysis): split regime stratification into behaviour and self-report"
```

`regime_stratified_*` 산출물 3종이 이 코드에서 나온다. 골든 스냅샷이 이 태스크의 직접 증거다.

---

### P2 · Task 6: `semantic/` — 텍스트와 임베딩 채널

네 번째 채널은 신규다. 흩어져 있던 텍스트·임베딩 로직을 한 곳에 모은다. `analysis/`에 이미 있는 셋(`threat_registration`, `threat_judge`, `threat_lexicon`)과 `scripts/`에 있는 셋(`_ri_dataset`, `probe_reasoning_embeddings`의 라이브러리부, `probe_lexicon`)이 대상이다.

**Files:**
- Move: `analysis/threat_registration.py`, `analysis/threat_judge.py` → `analysis/semantic/`
- Move: `scripts/_ri_dataset.py` → `analysis/semantic/dataset.py`
- Create: `analysis/semantic/__init__.py`, `analysis/semantic/embeddings.py`, `analysis/semantic/lexicon.py`
- Delete: `analysis/threat_lexicon.py` (`semantic/lexicon.py`로 병합), `scripts/probe_lexicon.py`의 로직부
- Modify: `scripts/probe_reasoning_embeddings.py`, `scripts/probe_lexicon.py` (얇은 CLI로 축소), `scripts/analyze_call1_ri.py` (`_ri_dataset` import 경로)
- Modify: `analysis/__init__.py`, 직접 import 13건 (`threat_judge` 9, `threat_registration` 3, `threat_lexicon` 1)

**Interfaces:**
- Consumes: Task 1의 `shared/`
- Produces:
  - `semantic.dataset` — 구 `scripts/_ri_dataset.py`의 전체 공개 표면 (`grep -n "^def " scripts/_ri_dataset.py`로 실측해 그대로 옮긴다)
  - `semantic.embeddings` — 구 `scripts/probe_reasoning_embeddings.py`에서 승격한 인코딩·프로브 적합 함수. **캐시 경로 상수와 시드는 그대로 옮긴다** (`outputs/reasoning_probe/_embedding_cache/`).
  - `semantic.lexicon` — 구 `analysis/threat_lexicon.py`(47줄)와 `scripts/probe_lexicon.py`의 로직 병합
  - `semantic.threat_registration`, `semantic.threat_judge` — 이동만

- [ ] **Step 1: Extend the channel test**

```python
def test_semantic_channel_exists_and_is_complete() -> None:
    expected = {
        "dataset.py",
        "embeddings.py",
        "lexicon.py",
        "threat_registration.py",
        "threat_judge.py",
        "__init__.py",
    }
    assert {p.name for p in (ANALYSIS / "semantic").glob("*.py")} == expected


def test_probe_scripts_are_thin_clis() -> None:
    for name in ("probe_reasoning_embeddings.py", "probe_lexicon.py"):
        source = (REPO_ROOT / "scripts" / name).read_text(encoding="utf-8")
        assert "squid_game.analysis.semantic" in source, name
        assert len(source.splitlines()) < 150, name


def test_the_ri_dataset_helper_left_scripts() -> None:
    assert not (REPO_ROOT / "scripts" / "_ri_dataset.py").exists()
```

- [ ] **Step 2: Run it to verify it fails**

- [ ] **Step 3: Move what moves whole**

```bash
cd game/squid_game/analysis
mkdir -p semantic
git mv threat_registration.py threat_judge.py semantic/
cd -
git mv scripts/_ri_dataset.py game/squid_game/analysis/semantic/dataset.py
```

- [ ] **Step 4: Merge the two lexicons**

`analysis/threat_lexicon.py`(47줄, 어휘 정의)와 `scripts/probe_lexicon.py`(100줄, 어휘 기반 점수 계산)를 `semantic/lexicon.py` 하나로 합친다. 어휘 목록 문자열은 한 글자도 바꾸지 않는다 — 이것이 곧 측정 도구다.

```bash
git mv game/squid_game/analysis/threat_lexicon.py game/squid_game/analysis/semantic/lexicon.py
```

그 다음 `scripts/probe_lexicon.py`의 로직 함수를 `lexicon.py`에 붙이고, 스크립트에는 argparse와 출력만 남긴다.

- [ ] **Step 5: Lift the embedding pipeline**

`scripts/probe_reasoning_embeddings.py`(580줄)에서 `semantic/embeddings.py`로 올라가는 것: 인코딩(`SentenceTransformer` 호출과 캐시), 프로브 적합(GroupKFold, 스칼라 baseline 가드), 순열 검정. 스크립트에 남는 것: argparse, 채널·마스크 변형 루프, 리포트 방출.

**시드와 캐시 키를 바꾸지 않는다.** 임베딩 캐시(`outputs/reasoning_probe/_embedding_cache/`, 채널·마스크 변형당 ~13 MB)가 키 규칙에 걸려 있고, 키가 바뀌면 캐시가 통째로 무효화돼 재계산이 발생한다.

- [ ] **Step 6: Repoint the 13 direct import sites**

```bash
grep -rl "squid_game\.analysis\.\(threat_registration\|threat_judge\|threat_lexicon\)" --include='*.py' game scripts tests \
  | xargs sed -i '' -E 's/squid_game\.analysis\.(threat_registration|threat_judge)\b/squid_game.analysis.semantic.\1/g; s/squid_game\.analysis\.threat_lexicon\b/squid_game.analysis.semantic.lexicon/g'
```

`scripts/analyze_call1_ri.py`의 `_ri_dataset` import도 고친다:

```bash
sed -i '' 's/from scripts\._ri_dataset import/from squid_game.analysis.semantic.dataset import/' scripts/analyze_call1_ri.py
```

- [ ] **Step 7: Verify the probe reproduces its results**

이 산출물도 골든 스냅샷 밖이다. 직접 비교한다. 순열 귀무분포가 들어가므로 **점추정만** 비교한다.

```bash
cp outputs/reasoning_probe/probe_results.json /tmp/probe_before.json
uv run --extra probe python -m scripts.probe_reasoning_embeddings
python - <<'PY'
import json
before = json.load(open("/tmp/probe_before.json"))
after = json.load(open("outputs/reasoning_probe/probe_results.json"))
def auroc(d):
    return {k: v for k, v in sorted(_flatten(d).items()) if "auroc" in k or "accuracy" in k}
def _flatten(d, prefix=""):
    out = {}
    if isinstance(d, dict):
        for k, v in d.items():
            out.update(_flatten(v, f"{prefix}{k}."))
    elif isinstance(d, list):
        for i, v in enumerate(d):
            out.update(_flatten(v, f"{prefix}{i}."))
    else:
        out[prefix.rstrip(".")] = d
    return out
b, a = auroc(before), auroc(after)
diff = {k: (b[k], a[k]) for k in b if k in a and b[k] != a[k]}
print("point estimates changed:", diff or "none")
PY
```

Expected: `point estimates changed: none`.

- [ ] **Step 8: Run the gates and commit**

```bash
uv run --extra dev --extra analysis pytest tests/unit -q
uv run python scripts/dev/golden_snapshot.py verify --golden ~/golden/squid-restructure
git add game/squid_game/analysis scripts tests
git commit -m "refactor(analysis): assemble the semantic channel from three scattered homes"
```

---

### P2 · Task 7: MTMM을 채널 위에 올리고 P2를 닫는다

`motivation.py`(462줄)는 4성분(생존 충동 · 과제 호기심 · 점수 애착 · 기저 지속성)을 세 방법 축으로 삼각측량하는 종합기다. 채널 하위가 아니라 **채널 위**에 둔다. 다만 `_baseline_persistence_behavioral`(Cell 5 비포기율)은 순수 행동 추정기이므로 행동 채널로 내린다.

**Files:**
- Move: `analysis/motivation.py` → `analysis/shared/mtmm.py`
- Create: `analysis/behavioral/baseline_persistence.py`
- Modify: `analysis/__init__.py` (최종 정리), 직접 import 5건
- Modify: `tests/unit/test_analysis_channels.py` (`xfail` 마커 제거)

**Interfaces:**
- Consumes: Task 2~6의 네 채널 전부
- Produces: `shared.mtmm.decompose_motivation(...)` — 시그니처 불변, 파사드 export 불변. `behavioral.baseline_persistence` — 구 `motivation._baseline_persistence_behavioral`이 공개 함수 `baseline_persistence_behavioral`로 승격된다 (선행 밑줄 제거. 다른 패키지에서 부르게 되므로 비공개 표기가 더는 사실이 아니다).

- [ ] **Step 1: Finish the channel test**

`test_the_flat_layout_is_gone`의 `xfail` 마커를 뗀다. 그리고 삼각측량 구조가 코드에 드러나는지 직접 확인하는 테스트를 더한다.

```python
def test_mtmm_sits_above_the_channels() -> None:
    """The triangulation must call the channel estimators, not re-implement them."""
    source = (ANALYSIS / "shared" / "mtmm.py").read_text(encoding="utf-8")
    assert "squid_game.analysis.behavioral" in source
    assert "squid_game.analysis.cognitive" in source


def test_baseline_persistence_is_behavioural() -> None:
    module = importlib.import_module("squid_game.analysis.behavioral.baseline_persistence")
    assert callable(module.baseline_persistence_behavioral)
```

- [ ] **Step 2: Run it to verify it fails**

- [ ] **Step 3: Move and split**

```bash
git mv game/squid_game/analysis/motivation.py game/squid_game/analysis/shared/mtmm.py
```

`_baseline_persistence_behavioral`(원본 `:360-403`)을 잘라 `behavioral/baseline_persistence.py`로 옮기고 이름에서 밑줄을 뗀다. `mtmm.py`는 import 해서 호출한다.

`_baseline_persistence_cognitive`는 인지 추정기이므로 `cognitive/`로 내려야 대칭이 맞지만, **스펙 §3.2가 명시한 이동 목록에 없다.** 이 계획은 스펙을 넘지 않는다. 대신 `mtmm.py`에 한 줄 남긴다:

```python
# _baseline_persistence_cognitive stays here while its behavioural twin
# moved to behavioral/baseline_persistence.py -- the spec's §3.2 mapping
# lists only the latter. The asymmetry is deliberate and recorded rather
# than silently "fixed": moving it is a spec change, not a refactor.
```

- [ ] **Step 4: Repoint the 5 direct import sites**

```bash
grep -rl "squid_game\.analysis\.motivation" --include='*.py' game scripts tests \
  | xargs sed -i '' 's/squid_game\.analysis\.motivation/squid_game.analysis.shared.mtmm/g'
```

- [ ] **Step 5: Tidy the facade**

`analysis/__init__.py`의 import 블록을 채널 순서로 재배열하고, 모듈 docstring의 "Usage::" 예시를 새 경로로 갱신한다. `__all__`의 내용은 **변경하지 않는다** — 순서만 채널별로 묶는다.

docstring 안의 죽은 참조 `docs/design/v6/POSTHOC_ANALYSIS.md §A.10, §A.11`은 P4 소관이다. 여기서 손대지 않는다.

- [ ] **Step 6: Run every gate**

```bash
uv run --extra dev --extra analysis pytest tests/unit -q
uv run --extra dev --extra analysis pytest tests/integration -q
uv run python scripts/dev/golden_snapshot.py verify --golden ~/golden/squid-restructure
```

Expected: 신규 실패 0, `84 deterministic artefacts`, exit 0.

- [ ] **Step 7: Record the result**

`docs/superpowers/plans/2026-08-30-p0-baseline.md`에 `## P2 result` 문단을 더한다. 형식은 P1과 같다. 실측값만 적는다.

- [ ] **Step 8: Commit**

```bash
git add game/squid_game/analysis scripts tests docs/superpowers/plans/2026-08-30-p0-baseline.md
git commit -m "refactor(analysis): lift MTMM above the channels it triangulates"
```

---

---

## P2 게이트

1. `analysis/` 최상위에 `__init__.py` 외의 `.py`가 없다.
2. `shared/`, `cognitive/`, `selfreport/`, `behavioral/`, `semantic/` 다섯 하위 패키지가 존재하고 각각 `__init__.py`에 채널 정의가 적혀 있다.
3. `forfeit_regression.py`와 `regime_stratification.py`가 존재하지 않는다.
4. `scripts/probe_reasoning_embeddings.py`, `scripts/probe_lexicon.py`, `scripts/analyze_call1_ri.py`가 각각 150줄 미만이고 로직을 `analysis.semantic` / `analysis.cognitive`에서 import 한다.
5. `squid_game.analysis.__all__`이 P2 시작 시점과 동일하다.
6. 골든 스냅샷 84개 바이트 동일, unit 스위트 신규 실패 0.
7. Call-1 산출물과 probe 점추정이 P2 이전과 동일하다 (Task 3 Step 6, Task 6 Step 7).

### P2 범위 밖

- scripts 5분류와 plot 스타일 추출 (P3)
- 죽은 주석·죽은 참조 정리 (P4)
- `unified_turn.py` · `api.py` 분리 (P5)
- 분석 산출물의 `results/` 이관 (P6)
- R2 비례검정, FDR 보정 (스펙 §8, 이번 재구조화 전체의 범위 밖)

---

# Phase P3+P4 — scripts 분류와 죽은 것 제거

평면 `scripts/` 40여 개를 5분류하고 보일러플레이트를 뽑은 뒤(P3), 죽은 참조 · 낡은 주석 · 격리 대상 레거시를 정리한다(P4).

**접근:** P3와 P4는 스펙 §6에서 한 묶음으로 지정된 두 저위험 단계다. 순서에 의미가 있다: 먼저 파일을 제자리에 놓고(P3), 그 다음 그 파일들 안의 죽은 서술을 고친다(P4). 반대로 하면 정정한 경로 서술이 곧바로 다시 틀려진다. P3의 위험은 하나뿐이다 — 골든 스냅샷 하네스가 `scripts/analyze_phase3.py`를 **경로 문자열로** 호출하므로(`scripts/dev/golden_snapshot.py:159-163`), 그 파일이 움직이면 판정 장치 자체가 먼저 깨진다. 그래서 Task 1의 첫 단계가 하네스 갱신이다. P4는 삭제가 아니라 **격리와 정정**이다: 스펙 §7이 레거시 삭제를 금지하므로 `risk_choice_layer` 계열과 비활성 framing 6종은 `legacy/`로 표시만 하고, 복원 불가능한 `docs/design/` 참조는 지우는 대신 `# spec: lost` 한 줄로 무엇이 유실됐는지 남긴다.

**추가 제약:**

- **주석을 지울 때는 사실을 지우는 것인지 서술을 지우는 것인지 구분한다.** 실측 175건 중 대부분은 "왜 이것이 여기 없는가"의 기록이며 그 자체로 가치가 있다. 삭제 대상은 **더는 참이 아닌 서술**뿐이다.
- **스펙이 인용한 선행 감사 수치와 실측이 다른 항목이 셋 있다.** `docs/superpowers/sdd/*.diff`는 **0건**(스펙 104개), 커밋아웃 코드는 **6줄**(스펙 13줄), 낡은 주석 마커는 **175건**(스펙 182건). 없는 것을 지우러 가지 않는다.
- **P4는 삭제가 아니라 격리와 정정이다.** 복원 불가능한 `docs/design/` 참조는 지우는 대신 `# spec: lost` 한 줄로 무엇이 유실됐는지 남긴다.

## P3+P4 File Structure

P3+P4 완료 시점:

```
scripts/
  run/       run_experiment.py  resume_experiment.py  start_servers.sh  README.md
  analysis/  analyze_*.py  orchestrate_posthoc.py  probe_*.py  score_probes_llm.py
             _cli.py  README.md
  plots/     plot_*.py  build_*_diagram.py  gen_v4_diagrams.py  _style.py  README.md
  arena/     seed_web_arena.py  backup_web_arena.py  purge_human_sessions.py  README.md
  dev/       _dump_*.py  _trace_*.py  benchmark_*.py  crop_*.py  translate_*.py
             extract_probes_for_review.py  generate_manual_scores.py
             dump_run_config_to_yaml.py  golden_snapshot.py  README.md
  render/    render_excalidraw.py  render_template.html
game/squid_game/core/legacy/       risk_choice_layer.py  turn.py  social.py  survival.py
game/squid_game/prompts/framings/legacy/  survival.j2  neutral.j2  emotion.j2
                                          instruction.j2  *_electricity.j2
```

---

### P3+P4 · Task 1: scripts 5분류

40여 개 평면 스크립트를 성격별로 나눈다. 파일 내용은 건드리지 않는다 — 이동과 import 경로 갱신만이다.

**가장 먼저 고칠 것은 판정 장치다.** `scripts/dev/golden_snapshot.py`가 `"scripts/analyze_phase3.py"`를 문자열로 호출하므로, 그 문자열을 먼저 새 경로로 바꾸지 않으면 이동 직후 모든 판정이 "파이프라인 실행 실패"로 무너진다.

**Files:**
- Create: `scripts/{run,analysis,plots,arena}/` + 각 `__init__.py`, `README.md`; `scripts/dev/README.md`
- Move: 아래 분류표대로 `git mv`
- Modify: `scripts/dev/golden_snapshot.py:160` (파이프라인 경로 문자열)
- Modify: `scripts/dev/golden_snapshot.py`, `scripts/orchestrate_posthoc.py` 등 스크립트 간 import
- Modify: `tests/unit/test_import_smoke.py` (walk는 `scripts/`를 재귀하므로 자동으로 따라오지만, `test_the_walk_actually_finds_the_tree`의 고정 이름 `scripts.analyze_phase3`가 깨진다)
- Modify: `.github/workflows/tests.yml` 주석, `web/DEPLOY.md`, `README.md`, `CLAUDE.md`의 스크립트 경로 표기

**Interfaces:**
- Consumes: P2 완료 상태의 `scripts/`
- Produces: 모듈 경로가 `scripts.analysis.analyze_phase3`, `scripts.arena.seed_web_arena` 형태가 된다. 각 하위 디렉터리는 `__init__.py`를 가진 패키지다 — `scripts/`가 이미 패키지이고(`scripts/__init__.py` 존재) 테스트가 `scripts.seed_web_arena`로 import 하고 있으므로 하위도 패키지여야 한다.

분류표 (실측 파일 전량):

| 하위 | 파일 |
|---|---|
| `run/` | `run_experiment.py`, `resume_experiment.py`, `start_servers.sh`, `run_pipeline.sh`, `enter_isolated_claude.sh` |
| `analysis/` | `analyze_phase3.py`, `analyze_call1_ri.py`, `analyze_tc.py`, `analyze_threat_registration.py`, `analyze_verbal_reason.py`, `analyze_framing_ri_forfeit.py`, `analyze_framing_ri_forfeit_continue.py`, `analyze_unified_cox.py`, `analyze_unified_cox_with_load.py`, `analyze_unified_cox_ph_audit.py`, `orchestrate_posthoc.py`, `probe_reasoning_embeddings.py`, `probe_lexicon.py`, `score_probes_llm.py`, `thinking_analysis.py` |
| `plots/` | `plot_gemini_heatmaps.py`, `plot_gemini_results.py`, `plot_kaplan_meier.py`, `plot_ri_forfeit_conflict_zone.py`, `plot_ri_trajectories.py`, `build_llm_experience_diagram.py`, `build_posthoc_analysis_diagram.py`, `build_prompt_flow_diagram.py`, `gen_v4_diagrams.py` |
| `arena/` | `seed_web_arena.py`, `backup_web_arena.py`, `purge_human_sessions.py` |
| `dev/` | `_dump_forfeit_layer_prompts.py`, `_dump_split_forfeit_prompts.py`, `_dump_unified_prompt.py`, `_trace_split_forfeit_production.py`, `dump_cell_prompts.py`, `dump_gemini_smoke_prompt.py`, `benchmark_mlx_vs_ollama.py`, `crop_guard_sprites.py`, `translate_trajectories.py`, `extract_probes_for_review.py`, `generate_manual_scores.py`, `merge_proxy_thinking.py` (+ 기존 `dump_run_config_to_yaml.py`, `golden_snapshot.py`) |

`scripts/render/`는 그대로 둔다 — 이미 분류돼 있다.

- [ ] **Step 1: Write the failing test**

`tests/unit/test_scripts_taxonomy.py` (신규):

```python
"""Every script must declare what kind of thing it is by where it lives.

A flat scripts/ directory of forty files says nothing about which of them
the canonical pipeline runs and which were one-off. The five directories
answer that, and this test keeps the answer from decaying: a new file
dropped at the top level fails here rather than quietly joining the pile.
"""

from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = REPO_ROOT / "scripts"
CATEGORIES = ("run", "analysis", "plots", "arena", "dev", "render")


def test_no_python_script_sits_at_the_top_level() -> None:
    stray = {p.name for p in SCRIPTS.glob("*.py")} - {"__init__.py"}
    assert stray == set()


def test_every_category_exists_and_is_a_package() -> None:
    for name in CATEGORIES:
        directory = SCRIPTS / name
        assert directory.is_dir(), name
        if name != "render":
            assert (directory / "__init__.py").exists(), name


def test_every_category_says_what_it_is_for() -> None:
    """A directory without a README is a directory whose rule is in someone's head."""
    for name in CATEGORIES:
        readme = SCRIPTS / name / "README.md"
        assert readme.exists(), name
        assert len(readme.read_text(encoding="utf-8").split()) >= 15, name
```

- [ ] **Step 2: Run it to verify it fails**

```bash
uv run --extra dev --extra analysis pytest tests/unit/test_scripts_taxonomy.py -q
```

- [ ] **Step 3: Repoint the golden-snapshot harness FIRST**

`scripts/dev/golden_snapshot.py:160`:

```python
        [sys.executable, "scripts/analysis/analyze_phase3.py", str(run), "--model", model_label(run)],
```

아직 파일이 옮겨지지 않았으므로 이 시점에서 하네스는 실패한다. **의도된 순서다** — 다음 단계가 그 실패를 해소한다. 하네스를 마지막에 고치면, 그사이의 모든 판정이 "이동 때문인지 하네스 때문인지" 구분되지 않는다.

- [ ] **Step 4: Move the files**

```bash
cd scripts
mkdir -p run analysis plots arena
git mv run_experiment.py resume_experiment.py start_servers.sh run_pipeline.sh enter_isolated_claude.sh run/
git mv analyze_*.py orchestrate_posthoc.py probe_*.py score_probes_llm.py thinking_analysis.py analysis/
git mv plot_*.py build_*_diagram.py gen_v4_diagrams.py plots/
git mv seed_web_arena.py backup_web_arena.py purge_human_sessions.py arena/
git mv _dump_*.py _trace_*.py dump_cell_prompts.py dump_gemini_smoke_prompt.py \
       benchmark_mlx_vs_ollama.py crop_guard_sprites.py translate_trajectories.py \
       extract_probes_for_review.py generate_manual_scores.py merge_proxy_thinking.py dev/
cd -
```

`git mv` 후 `ls scripts/*.py`가 `__init__.py`만 남겨야 한다.

- [ ] **Step 5: Add the package markers and READMEs**

각 디렉터리에 `__init__.py`(빈 파일)와 `README.md`를 둔다. README는 3–5줄이며 **정규 파이프라인인지 일회성인지**를 반드시 밝힌다. 예시 (`scripts/analysis/README.md`):

```markdown
# scripts/analysis/

Thin CLIs over `squid_game.analysis`. The statistics live in the package;
these files own argparse, output paths, and report emission only.

`analyze_phase3.py` is the canonical pipeline — the golden-snapshot harness
runs it over all four canonical runs to gate every restructure step. The
rest are per-question entry points, run by hand.
```

나머지 넷도 같은 형식으로 쓴다. `run/`은 "실험 실행의 정규 경로는 `uv run squid-game`이며 여기 있는 것은 그 주변 도구"임을 밝힌다. `plots/`는 "논문 그림 재생성용, 파이프라인 아님"을. `arena/`는 "Web Arena DB 운영 도구 — 프로덕션 Supabase에 붙는다"를. `dev/`는 "일회성 · 디버그 · 하네스"를 밝힌다.

- [ ] **Step 6: Rewrite cross-script imports**

```bash
grep -rn "from scripts\.\|import scripts\." --include='*.py' game scripts tests web | grep -v __pycache__
```

나온 각 줄을 새 경로로 고친다. 실측 기준 주 대상은 `scripts._ri_dataset`(P2에서 이미 사라짐), `scripts.seed_web_arena`(테스트 3개), `scripts.backup_web_arena`(테스트 1개), `scripts.analyze_phase3`(하네스와 테스트)다.

`tests/unit/test_import_smoke.py`의 고정 이름도 옮긴다:

```python
    assert "scripts.analysis.analyze_phase3" in MODULE_NAMES
```

- [ ] **Step 7: Repoint the docs and shell scripts**

```bash
grep -rn "scripts/" README.md CLAUDE.md AGENTS.md web/DEPLOY.md .github/workflows/*.yml scripts/run/*.sh
```

나온 경로를 전부 새 위치로 고친다. `scripts/run/start_servers.sh`의 `SCRIPT_DIR/..`는 이제 한 단계 더 올라가야 한다 — `PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"`.

- [ ] **Step 8: Run the gates**

```bash
uv run --extra dev --extra analysis pytest tests/unit -q
uv run python scripts/dev/golden_snapshot.py verify --golden ~/golden/squid-restructure
bash scripts/run/start_servers.sh && curl -sf http://127.0.0.1:8502/docs >/dev/null && echo "servers OK"
```

셋째 명령까지 반드시 돌린다. shell 스크립트는 테스트가 없으므로 실행이 유일한 검증이다.

- [ ] **Step 9: Commit**

```bash
git add scripts tests README.md CLAUDE.md AGENTS.md web/DEPLOY.md .github
git commit -m "refactor(scripts): sort forty flat scripts into five kinds"
```

---

### P3+P4 · Task 2: plot 공통 스타일 추출

`plot_*` 5개는 1,957줄이고, 그중 상당 부분이 같은 matplotlib 설정과 같은 저장 로직이다. 공통부를 `scripts/plots/_style.py`로 뽑는다.

**Files:**
- Create: `scripts/plots/_style.py`
- Modify: `scripts/plots/plot_{gemini_heatmaps,gemini_results,kaplan_meier,ri_forfeit_conflict_zone,ri_trajectories}.py`
- Test: `tests/unit/test_plot_style.py` (신규)

**Interfaces:**
- Consumes: 없음
- Produces: `scripts.plots._style` — `apply_house_style() -> None` (rcParams 설정), `save_figure(fig, path: Path, *, dpi: int) -> Path` (디렉터리 생성 + 저장 + 경로 반환). 정확한 rcParams 키와 dpi 기본값은 **다섯 파일에서 실측한 공통값**을 쓴다. 다섯이 서로 다르면 공통이 아니므로 뽑지 않는다.

- [ ] **Step 1: Measure what is actually common**

```bash
grep -n "rcParams\|plt.style\|figsize\|dpi\|savefig\|tight_layout\|set_xlabel\|font" scripts/plots/plot_*.py
```

**뽑기 전에 이 목록을 읽는다.** 다섯 파일이 같은 값을 쓰는 항목만 `_style.py`로 간다. 한 파일만 다른 값을 쓰면 그 항목은 공통이 아니다 — 억지로 합치면 그림이 바뀐다. 스펙 §5는 "줄바꿈을 지워 줄 수를 줄이는 방식은 금지"라고 못박았고, 다르게 쓰이던 값을 통일해 줄 수를 줄이는 것도 같은 종류의 거짓 압축이다.

- [ ] **Step 2: Write the failing test**

`tests/unit/test_plot_style.py`:

```python
"""The five plot scripts share one house style, defined once.

Written as a test rather than left to review because the duplication came
back twice already: each new plot script started as a copy of the previous
one, rcParams block included.
"""

from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
PLOTS = REPO_ROOT / "scripts" / "plots"
PLOT_SCRIPTS = sorted(PLOTS.glob("plot_*.py"))


def test_there_are_five_plot_scripts() -> None:
    """A guard: if this count changes, the assertions below need revisiting."""
    assert len(PLOT_SCRIPTS) == 5


def test_no_plot_script_sets_rcparams_itself() -> None:
    for path in PLOT_SCRIPTS:
        source = path.read_text(encoding="utf-8")
        assert "rcParams" not in source, path.name
        assert "from scripts.plots._style import" in source, path.name
```

- [ ] **Step 3: Run it to verify it fails**

- [ ] **Step 4: Write `_style.py` and rewire the five scripts**

`scripts/plots/_style.py`의 docstring에 **무엇을 공통으로 인정했고 무엇을 남겼는지** 적는다:

```python
"""The house style every plot script shares.

Only settings that all five scripts already used identically live here.
Anything one script did differently stayed in that script: unifying a value
that differed would change the figure, which is not a refactor.
"""
```

다섯 파일에서 rcParams 블록과 저장 로직을 지우고 `apply_house_style()` / `save_figure(...)` 호출로 바꾼다.

- [ ] **Step 5: Verify the figures are unchanged**

그림은 골든 스냅샷 대상이 아니다. 직접 비교한다.

```bash
mkdir -p /tmp/figs_before && cp figures/*.png /tmp/figs_before/
uv run --extra analysis python -m scripts.plots.plot_kaplan_meier
uv run --extra analysis python -m scripts.plots.plot_ri_trajectories
for f in /tmp/figs_before/*.png; do
  b=$(basename "$f")
  if [ -f "figures/$b" ]; then
    cmp -s "$f" "figures/$b" && echo "same: $b" || echo "CHANGED: $b"
  fi
done
```

matplotlib은 같은 입력에 대해 바이트 동일한 PNG를 내지 않을 수 있다 (폰트 캐시, 메타데이터). `CHANGED`가 나오면 먼저 **아무것도 고치지 않은 상태에서 두 번 생성해** 기준선의 비결정성을 확인한다. 두 번 생성이 서로 다르면 바이트 비교는 이 자산에 쓸 수 없으므로, 눈으로 확인하고 그 사실을 커밋 메시지에 적는다.

- [ ] **Step 6: Run the gates and commit**

```bash
uv run --extra dev --extra analysis pytest tests/unit -q
git add scripts/plots tests/unit/test_plot_style.py
git commit -m "refactor(plots): define the shared figure style once"
```

---

### P3+P4 · Task 3: 분석 CLI 공통 헬퍼

실측 17개 스크립트가 argparse를 쓰고, 그중 `analysis/`에 속한 것들이 같은 패턴을 반복한다: 런 디렉터리 인자 파싱 → `load_seasons` 호출 → 결과 계산 → 마크다운 리포트 방출.

**Files:**
- Create: `scripts/analysis/_cli.py`
- Modify: 공통 패턴을 실제로 쓰는 `scripts/analysis/analyze_*.py`
- Test: `tests/unit/test_analysis_cli_helper.py` (신규)

**Interfaces:**
- Consumes: `squid_game.analysis.shared.loaders.load_seasons`
- Produces: `scripts.analysis._cli` — `run_dir_parser(description: str) -> argparse.ArgumentParser` (`run_dir`, `--model`, `--out` 세 인자를 붙인 파서), `load_run(args) -> tuple[list[SeasonResult], str]` (시즌과 모델 라벨), `emit_markdown(path: Path, title: str, body: str) -> Path`.

- [ ] **Step 1: Measure the actual overlap first**

```bash
grep -n -A6 "add_argument" scripts/analysis/analyze_*.py | head -80
```

**세 개 이상의 스크립트가 같은 인자를 같은 의미로 받을 때만 헬퍼로 올린다.** 둘뿐이면 중복이 아니라 우연이다. 실측 결과 대상이 셋 미만이면 이 태스크는 "적용 대상 없음"으로 종료하고 그 사실을 커밋 대신 `docs/superpowers/plans/2026-08-30-p0-baseline.md`에 한 줄 남긴다 — 억지로 뽑지 않는다.

- [ ] **Step 2: Write the failing test**

```python
"""The analysis CLIs share one argument contract.

Each of these scripts takes a run directory, a model label, and an output
path, and each had its own spelling of all three. The helper makes the
contract explicit so a new analysis script inherits it instead of inventing
a fourth spelling.
"""

from __future__ import annotations

import importlib
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]


def test_the_helper_builds_the_shared_parser() -> None:
    cli = importlib.import_module("scripts.analysis._cli")
    parser = cli.run_dir_parser("test")
    args = parser.parse_args(["outputs/final_results/some_run", "--model", "gemini"])
    assert str(args.run_dir).endswith("some_run")
    assert args.model == "gemini"


def test_the_converted_scripts_use_it() -> None:
    converted = ["analyze_tc.py", "analyze_verbal_reason.py"]  # 실측으로 확정한다
    for name in converted:
        source = (REPO_ROOT / "scripts" / "analysis" / name).read_text(encoding="utf-8")
        assert "from scripts.analysis._cli import" in source, name
```

`converted` 목록은 Step 1의 실측 결과로 채운다. 추정으로 적지 않는다.

- [ ] **Step 3: Run it to verify it fails**

- [ ] **Step 4: Write `_cli.py` and convert the scripts**

각 스크립트의 인자 **의미**가 같은지 확인하고 바꾼다. 이름만 같고 의미가 다른 인자는 그대로 둔다.

- [ ] **Step 5: Verify each converted CLI still runs**

```bash
for s in scripts/analysis/analyze_*.py; do
  uv run --extra analysis python "$s" --help >/dev/null || echo "BROKE: $s"
done
```

- [ ] **Step 6: Run the gates and commit**

```bash
uv run --extra dev --extra analysis pytest tests/unit -q
uv run python scripts/dev/golden_snapshot.py verify --golden ~/golden/squid-restructure
git add scripts/analysis tests
git commit -m "refactor(scripts): give the analysis CLIs one argument contract"
```

---

### P3+P4 · Task 4: 고아 `.mjs`를 CI에 잇는다

`tests/web/rank_ladder.test.mjs`는 실재하는 테스트인데 `package.json`이 없고 CI에도 없다. 즉 **아무도 돌리지 않는 테스트**다. 스펙은 이를 "고아 `.mjs`"로 분류해 P4의 정리 대상에 넣었지만, 내용을 읽어 보면 지울 것이 아니라 이어야 할 것이다 — `buildRankLadder`의 순위 계산을 검증하며 프런트엔드에 다른 테스트는 없다.

**Files:**
- Modify: `.github/workflows/tests.yml` (job 추가)
- Create: `tests/web/README.md`

**Interfaces:**
- Consumes: `web/frontend/rank_ladder.js`
- Produces: CI job `frontend`. 로컬 명령은 `node --test tests/web/`.

- [ ] **Step 1: Confirm it passes locally**

```bash
node --test tests/web/
```

실패하면 **CI에 잇기 전에 먼저 고친다.** 깨진 테스트를 CI에 넣으면 그 순간부터 모든 PR이 빨개진다.

- [ ] **Step 2: Add the CI job**

`.github/workflows/tests.yml`에 job을 더한다. `package.json`이 없으므로 의존성 설치 단계가 없다 — `node --test`는 Node 18+ 내장이다.

```yaml
  frontend:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
        with:
          lfs: false

      - uses: actions/setup-node@v4
        with:
          node-version: "20"

      # No package.json and no dependencies: node --test is built in, and
      # the suite imports web/frontend/rank_ladder.js through createRequire.
      # Until this job existed the file was a test nobody ran.
      - name: Frontend unit tests
        run: node --test tests/web/
```

- [ ] **Step 3: Write `tests/web/README.md`**

```markdown
# tests/web/

Node's built-in test runner (`node --test tests/web/`), no package.json and
no dependencies. Covers the pure functions in `web/frontend/` — currently
`rank_ladder.js`'s `buildRankLadder`.

Run in CI by the `frontend` job in `.github/workflows/tests.yml`. Before
that job existed this directory was a test nobody ran.
```

- [ ] **Step 4: Commit**

```bash
git add .github/workflows/tests.yml tests/web/README.md
git commit -m "ci: run the frontend test that nothing was running"
```

---

### P3+P4 · Task 5: 죽은 경로 참조 정정

실측: 코드 안의 `docs/design` 참조 **28건**, `archive/` 참조 **8건**. `docs/design/` 트리는 git 히스토리 전체에 존재한 적이 없으므로(스펙 §2) 원본 복원은 불가능하다.

스펙이 정한 규칙을 그대로 적용한다. **해당 사양이 코드에 실제로 구현돼 있으면** docstring을 코드 내 사양 요약으로 대체하고 경로 참조를 지운다. **코드만 보고 사양을 재구성할 수 없으면** `# spec: lost`로 표시하고 무엇이 유실됐는지 한 줄 남긴다.

**Files:**
- Modify: `docs/design` 참조를 담은 파일 전부 (28건)
- Modify: `archive/` 참조를 담은 파일 전부 (8건)
- Test: `tests/unit/test_no_dead_path_references.py` (신규)

**Interfaces:**
- Consumes: 없음
- Produces: 코드 안에 존재하지 않는 디렉터리를 가리키는 경로 참조가 0건.

- [ ] **Step 1: Write the failing test**

```python
"""No comment may point at a directory that does not exist.

docs/design/ was referenced 46 times across the repo and has never existed
in the git history -- not deleted, never committed. A reader following one
of those references finds nothing and cannot tell whether the spec is lost
or they are looking in the wrong place. Each reference is now either a
summary of the spec inline, or an explicit `# spec: lost` saying what went
missing.
"""

from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
DEAD = re.compile(r"docs/design/|(?<![\w.])archive/")
SEARCH_ROOTS = ("game", "web", "db", "scripts", "tests")


def test_no_source_file_points_at_a_missing_directory() -> None:
    offenders: list[str] = []
    for base in SEARCH_ROOTS:
        for path in (REPO_ROOT / base).rglob("*.py"):
            if "__pycache__" in path.parts or path.name == Path(__file__).name:
                continue
            for i, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
                if DEAD.search(line):
                    offenders.append(f"{path.relative_to(REPO_ROOT)}:{i}")
    assert offenders == []
```

`archive/`는 실제로 존재하는지 먼저 확인한다 (`ls archive` — 존재하면 그 8건은 죽은 참조가 아니며 정규식에서 뺀다).

- [ ] **Step 2: Run it to verify it fails**

Expected: 28~36건이 나열된다.

- [ ] **Step 3: Triage each reference**

하나씩 읽는다. 판정 기준은 하나다 — **그 문장이 가리키는 사양이 지금 코드에 있는가.**

있으면 경로를 지우고 사양을 그 자리에 두 줄로 요약한다. 예:

```python
# 기존
"""...see ``docs/design/v6/POSTHOC_ANALYSIS.md §A.10`` for the rationale."""

# 정정
"""...superseded by the Unit 14 forfeit_regression and Unit 15 split-call
MixedLM: both estimate the same effect without the Baron-Kenny mediation
step, which the binary CONTINUE/FORFEIT decision made inapplicable.
"""
```

없으면 표시만 남긴다:

```python
# spec: lost -- the v3 MASTER_PLAN §3 rule that fixed the legacy framing
# enum ordering. The order is load-bearing (cell_id derives from it) but
# the reasoning behind it is not recoverable from the code.
```

- [ ] **Step 4: Run the gates and commit**

```bash
uv run --extra dev --extra analysis pytest tests/unit -q
uv run python scripts/dev/golden_snapshot.py verify --golden ~/golden/squid-restructure
git add game web db scripts tests
git commit -m "docs: replace references to a design tree that never existed"
```

---

### P3+P4 · Task 6: 낡은 주석 감사

실측 175건의 `TODO|FIXME|DEPRECATED|LEGACY|removed on|archived on`. **일괄 삭제 대상이 아니다.** 대부분은 "왜 이것이 여기 없는가"를 기록한 문장이고, 그런 문장은 코드가 답하지 못하는 것을 답한다.

**Files:**
- Modify: 감사 결과 정정이 필요한 파일
- Create: `docs/superpowers/plans/2026-08-30-p4-comment-audit.md` (감사 기록)

**Interfaces:**
- Consumes: 없음
- Produces: 175건 각각에 대한 판정 기록. 삭제된 것, 갱신된 것, 그대로 둔 것.

- [ ] **Step 1: Produce the audit list**

```bash
grep -rniE "TODO|FIXME|DEPRECATED|LEGACY|removed on|archived on" --include='*.py' game web db scripts \
  | grep -v __pycache__ > /tmp/comment_audit.txt
wc -l /tmp/comment_audit.txt
```

- [ ] **Step 2: Classify every line into one of four buckets**

`docs/superpowers/plans/2026-08-30-p4-comment-audit.md`에 표로 기록한다.

| 분류 | 판정 | 조치 |
|---|---|---|
| 사실이며 유용 | "이 기능은 2026-04-21에 제거됐고 이유는 X" | 그대로 둔다 |
| 사실이나 위치가 틀림 | 옮겨간 코드를 가리킴 | 경로만 갱신 |
| 더는 참이 아님 | 가리키는 대상이 이미 사라짐 | 삭제 |
| `TODO` / `FIXME` | 아직 안 한 일 | 이슈로 승격하거나, 하지 않기로 했으면 이유와 함께 서술로 바꾼다 |

**`TODO`를 조용히 지우지 않는다.** 지운다는 것은 "하지 않기로 했다"는 결정이며, 결정은 기록돼야 한다.

- [ ] **Step 3: Apply the classification**

분류표대로 고친다. 파일 단위로 커밋을 나눠도 되지만, 감사 문서와 그 문서가 기술한 변경은 같은 커밋에 둔다.

- [ ] **Step 4: Clean the six commented-out lines**

```bash
grep -rnE '^\s*#\s*(from |import |def |class |return )' --include='*.py' game web db scripts | grep -v __pycache__
```

실측 6줄. 각각이 "왜 주석 처리됐는가"를 설명하는 문장을 동반하는지 본다. 동반하지 않으면 지운다 — 설명 없는 주석 처리 코드는 git 히스토리가 더 잘 보관한다.

- [ ] **Step 5: Run the gates and commit**

```bash
uv run --extra dev --extra analysis pytest tests/unit -q
uv run python scripts/dev/golden_snapshot.py verify --golden ~/golden/squid-restructure
git add game web db scripts docs/superpowers/plans/2026-08-30-p4-comment-audit.md
git commit -m "docs: audit 175 stale markers and record every verdict"
```

---

### P3+P4 · Task 7: 레거시 격리

스펙 §7은 삭제를 금지하고 **표시**를 요구한다. 대상은 둘이다.

1. `core/` 안의 v3 이전 계열: `risk_choice_layer.py`, `turn.py`, `social.py`, `survival.py`
2. 비활성 framing 6종: `survival.j2`, `neutral.j2`, `emotion.j2`, `instruction.j2`, `baseline_electricity.j2`, `survival_electricity.j2`

**주의: `risk_choice_layer`는 죽어 있지 않다.** 실측 결과 `core/engine.py:22`와 `core/unified_turn.py:55`가 import 하고 `models/config.py`가 두 곳에서 참조한다. 격리는 "쓰이지 않는다"는 뜻이 아니라 "구세대다"라는 표시이며, 경로만 바뀐다.

**framing 템플릿 이동에는 코드 변경이 따른다.** `core/framing.py:33`이 `f"framings/{framing.value}.j2"`로 경로를 조립하므로, 하위 디렉터리로 옮기면 **아카이브 설정 재생 경로가 조용히 깨진다.** 레거시 집합을 명시하고 그에 맞춰 경로를 조립해야 한다.

**Files:**
- Move: `game/squid_game/core/{risk_choice_layer,turn,social,survival}.py` → `core/legacy/`
- Move: `game/squid_game/prompts/framings/{survival,neutral,emotion,instruction,baseline_electricity,survival_electricity}.j2` → `framings/legacy/`
- Create: `core/legacy/__init__.py`
- Modify: `core/framing.py` (경로 조립), `core/engine.py`, `core/unified_turn.py`, `models/config.py`
- Test: `tests/unit/test_legacy_isolation.py` (신규)

**Interfaces:**
- Consumes: 없음
- Produces: `squid_game.core.legacy.risk_choice_layer` 등 4모듈. `framing.py`에 모듈 상수 `_LEGACY_FRAMINGS: frozenset[Framing]`이 생기고, 템플릿 경로는 레거시면 `framings/legacy/{value}.j2`, 아니면 `framings/{value}.j2`가 된다.

- [ ] **Step 1: Write the failing test**

```python
"""Legacy is marked, not deleted -- and marking it must not break replay.

The spec forbids deleting the pre-v3 modules and the six inactive framings:
they are the replay path for archived experiment configs. So they move into
legacy/ instead. Moving the templates is the part that can break silently,
because framing.py builds the template path by string interpolation -- a
template that moved without the path builder learning about it fails only
when someone replays an archived config, which is exactly when nobody is
watching.
"""

from __future__ import annotations

import importlib
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
GAME = REPO_ROOT / "game" / "squid_game"

LEGACY_FRAMING_NAMES = (
    "survival",
    "neutral",
    "emotion",
    "instruction",
    "baseline_electricity",
    "survival_electricity",
)


def test_the_pre_v3_core_modules_moved_but_survived() -> None:
    for name in ("risk_choice_layer", "turn", "social", "survival"):
        assert (GAME / "core" / "legacy" / f"{name}.py").exists(), name
        assert not (GAME / "core" / f"{name}.py").exists(), name


def test_risk_choice_layer_still_imports() -> None:
    """It is legacy, not dead: engine and unified_turn both import it."""
    module = importlib.import_module("squid_game.core.legacy.risk_choice_layer")
    assert module.RiskChoiceLayer is not None


def test_every_legacy_template_resolves() -> None:
    from squid_game.core.framing import FramingRenderer
    from squid_game.models.enums import Framing

    for name in LEGACY_FRAMING_NAMES:
        framing = Framing(name)
        renderer = FramingRenderer(framing)
        assert renderer._template_path == f"framings/legacy/{name}.j2"
        assert (GAME / "prompts" / renderer._template_path).exists(), name


def test_every_active_template_still_resolves() -> None:
    from squid_game.core.framing import FramingRenderer
    from squid_game.models.enums import Framing

    for name in ("true_baseline", "baseline_flagship", "flagship_corruption",
                 "flagship_corruption_terminal"):
        renderer = FramingRenderer(Framing(name))
        assert renderer._template_path == f"framings/{name}.j2"
        assert (GAME / "prompts" / renderer._template_path).exists(), name
```

클래스 이름 `FramingRenderer`와 속성 `_template_path`는 `core/framing.py`에서 실측해 그대로 쓴다.

- [ ] **Step 2: Run it to verify it fails**

- [ ] **Step 3: Move the core modules**

```bash
cd game/squid_game/core
mkdir -p legacy
git mv risk_choice_layer.py turn.py social.py survival.py legacy/
cd -
```

`core/legacy/__init__.py`:

```python
"""Pre-v3 turn machinery, kept for archived-config replay.

Not dead code: engine.py and unified_turn.py still import RiskChoiceLayer,
and models/config.py resolves RiskChoiceLayerConfig. The directory marks a
generation, not a graveyard -- the v3 Risk-Layer migration replaced the
turn flow these modules implement, but the archived Phase 1/2 configs
still name them, and the spec forbids deleting a replay path.
"""
```

- [ ] **Step 4: Rewrite the core imports**

```bash
grep -rl "squid_game\.core\.\(risk_choice_layer\|turn\|social\|survival\)" --include='*.py' game web db scripts tests \
  | xargs sed -i '' -E 's/squid_game\.core\.(risk_choice_layer|turn|social|survival)\b/squid_game.core.legacy.\1/g'
```

**치환 결과를 반드시 눈으로 확인한다.** `squid_game.core.turn`은 흔한 이름이라 `unified_turn`과 헷갈릴 여지가 있다 — 위 정규식은 `\b` 경계로 `unified_turn`을 제외하지만, `grep -rn "core.legacy" game | head -20`으로 실제 치환 줄을 훑는다.

- [ ] **Step 5: Move the templates and teach framing.py**

```bash
cd game/squid_game/prompts/framings
mkdir -p legacy
git mv survival.j2 neutral.j2 emotion.j2 instruction.j2 \
       baseline_electricity.j2 survival_electricity.j2 legacy/
cd -
```

`core/framing.py`:

```python
# The six pre-v3 framings live under framings/legacy/. They are still
# reachable -- archived Phase 1/2 configs name them -- so the path builder
# below has to know where they went. Enumerated rather than inferred: a
# heuristic ("anything not in the active set") would silently send a newly
# added framing to the legacy directory.
_LEGACY_FRAMINGS: frozenset[Framing] = frozenset(
    {
        Framing.SURVIVAL,
        Framing.NEUTRAL,
        Framing.EMOTION,
        Framing.INSTRUCTION,
        Framing.BASELINE_ELECTRICITY,
        Framing.SURVIVAL_ELECTRICITY,
    }
)
```

```python
        subdir = "framings/legacy" if framing in _LEGACY_FRAMINGS else "framings"
        self._template_path = f"{subdir}/{framing.value}.j2"
```

Enum 멤버 이름은 `models/enums.py`에서 실측해 그대로 쓴다.

- [ ] **Step 6: Run the gates**

```bash
uv run --extra dev --extra analysis pytest tests/unit -q
uv run --extra dev --extra analysis pytest tests/integration -q
uv run python scripts/dev/golden_snapshot.py verify --golden ~/golden/squid-restructure
```

그리고 레거시 재생 경로를 실제로 한 번 태운다 — 이것이 이 태스크의 유일한 직접 증거다:

```bash
uv run squid-game --config configs/experiment/<legacy framing을 쓰는 config>.yaml --dry-run
```

`configs/experiment/`에 레거시 framing을 쓰는 설정이 없으면 (P0가 복원한 5종은 v6이다), 대신 파이썬 한 줄로 여섯 템플릿을 전부 렌더링해 확인한다:

```bash
uv run python -c "
from squid_game.core.framing import FramingRenderer
from squid_game.models.enums import Framing
for name in ('survival','neutral','emotion','instruction','baseline_electricity','survival_electricity'):
    r = FramingRenderer(Framing(name))
    print(name, len(r.render_system_prompt()) if hasattr(r,'render_system_prompt') else 'CHECK API')
"
```

메서드 이름은 `core/framing.py`에서 실측해 맞춘다.

- [ ] **Step 7: Record the result and commit**

`docs/superpowers/plans/2026-08-30-p0-baseline.md`에 `## P3+P4 result` 문단을 더한다.

```bash
git add game scripts tests docs/superpowers/plans/2026-08-30-p0-baseline.md
git commit -m "refactor(core): isolate the pre-v3 generation without deleting it"
```

---

---

## P3+P4 게이트

1. `scripts/` 최상위에 `__init__.py` 외의 `.py`가 없고, 여섯 하위 디렉터리 각각에 README가 있다.
2. `scripts/plots/_style.py`가 존재하고 다섯 plot 스크립트 중 어느 것도 `rcParams`를 직접 설정하지 않는다.
3. 분석 CLI 공통 헬퍼가 존재하거나, 실측 결과 공통 패턴이 3개 미만이어서 만들지 않았다는 기록이 남아 있다.
4. `.github/workflows/tests.yml`에 `frontend` job이 있고 `node --test tests/web/`가 통과한다.
5. 코드 안에 `docs/design/`을 가리키는 참조가 0건이고, 복원 불가능했던 것은 `# spec: lost`로 표시돼 있다.
6. 175건 주석 감사 기록이 `docs/superpowers/plans/2026-08-30-p4-comment-audit.md`에 있다.
7. `core/legacy/`와 `prompts/framings/legacy/`가 존재하고, **여섯 레거시 템플릿이 전부 렌더링된다**.
8. 골든 스냅샷 84개 바이트 동일, unit 스위트 신규 실패 0.

### P3+P4 범위 밖

- `unified_turn.py` · `api.py` 책임 분리 (P5)
- 문서 4분할, `results/` 분리, `assets/` 정리 (P6)
- 레거시 코드 삭제 (스펙 §7이 금지)
- `analyze_unified_cox*.py` 3개와 `analyze_framing_ri_forfeit*.py` 2개의 통합 — 스펙 §5가 명시적으로 제외한다. 공백 무시 diff 373–401줄로, 사본이 아니라 갈라진 변종이다.

---

# Phase P5 — 큰 파일 책임 분리

`core/unified_turn.py` 1,751줄과 `squid_arena/api.py` 1,424줄을 책임별로 쪼갠다. 스펙이 **고위험**으로 분류한 유일한 단계다.

**접근:** 이 단계는 스펙이 **고위험**으로 분류한 유일한 단계다. 골든 스냅샷은 분석 산출물만 지키므로 여기서는 아무것도 보장하지 못한다 — 턴 플로우와 API 응답은 그 산출물 밖의 런타임 동작이다. 그래서 순서가 뒤집힌다: **먼저 특성화 테스트로 현재 동작을 고정하고(Task 1·2), 그 다음에만 코드를 움직인다(Task 3·4).** 특성화 테스트는 "옳은 동작"을 주장하지 않는다. **지금의 동작**을 기록할 뿐이다. 그것이 이 단계에서 필요한 전부다 — 분리가 동작을 바꿨는지만 알면 된다. 분리 자체는 보수적이다: 클래스 하나를 여러 클래스로 쪼개 협력 관계를 새로 설계하지 않고, **순수 함수로 뽑아낼 수 있는 것만** 모듈로 내린다. `UnifiedTurnManager`는 상태(히스토리, 프로바이더, 설정)를 들고 있고 그 상태를 쪼개는 순간 위험이 다른 종류가 된다.

**추가 제약:**

- **특성화 테스트 없이 코드를 움직이지 않는다.** Task 1·2가 Task 3·4의 전제다 (스펙 §4.3).
- **프롬프트 템플릿 문자열과 보상 계산을 건드리지 않는다** (스펙 §5). 공백 하나가 바뀌어도 LLM 입력이 달라진다.
- **`squid_arena.api:app`은 그대로 import 가능해야 한다.** Dockerfile `CMD`, `render.yaml` 헬스체크, `start_servers.sh`, 통합 테스트가 이 이름에 걸려 있다.
- **엔드포인트 경로와 응답 스키마를 바꾸지 않는다.** 배포된 프런트엔드가 라이브 백엔드를 호출 중이다 — 필드 이름 하나가 바뀌면 사이트가 깨진다.

## P5 File Structure

P5 완료 시점:

```
game/squid_game/core/
  unified_turn.py        # UnifiedTurnManager: 상태와 실행 흐름만
  turn_prompts.py        # 프롬프트 조립 (순수 함수)
  turn_conditions.py     # framing 판정과 p_death 해석 (순수 함수 / staticmethod)
  turn_results.py        # TurnResult 조립 (순수 함수)
web/squid_arena/
  api.py                 # FastAPI app 조립 + include_router. `app`은 여기 남는다
  schemas.py             # pydantic 요청/응답 모델 전량
  deps.py                # CORS, repository, rate limit, sanitizer
  routes_game.py         # /api/new_game /state /action /result /reward_preview
  routes_leaderboard.py  # /api/leaderboard/*
  routes_logs.py         # /api/logs* /api/report
  routes_arena.py        # /api/arena/*
  reporting.py           # _persist_result, 리포트 집계 헬퍼
tests/characterization/
  test_turn_flow_6cells.py
  test_api_contract.py
  snapshots/             # 특성화 스냅샷 JSON
```

---

### P5 · Task 1: 6셀 턴 플로우 특성화 테스트

`unified_turn.py`를 건드리기 전에 현재 동작을 기록한다. 스펙 §4.3이 요구하는 범위: Call 1 / 1.5 / 2 시퀀스 전량, Cell 0 축약 경로, Cell 5 EV-dominant 경로.

**Files:**
- Create: `tests/characterization/__init__.py`, `tests/characterization/conftest.py`, `tests/characterization/test_turn_flow_6cells.py`
- Create: `tests/characterization/snapshots/turn_flow/` (생성된 스냅샷)
- Modify: `pyproject.toml` (`testpaths`에 `tests/characterization` 추가), `tests/unit/test_pytest_ini_options.py`

**Interfaces:**
- Consumes: `tests/integration/conftest.py`의 `StubProvider`, `StubProviderCall`
- Produces: 스냅샷 파일 6개 (셀당 하나). 각 스냅샷은 한 셀의 시즌을 끝까지 돌린 결과의 **결정적 부분**만 담는다: 각 턴의 `action`, `forfeited`, `thinking_tokens`, `score`, 그리고 프로바이더에게 실제로 간 프롬프트 전문.

- [ ] **Step 1: Make the stub provider reusable**

`tests/integration/conftest.py`의 `StubProvider`는 통합 스위트 전용 fixture다. 특성화 스위트도 같은 것을 쓴다. **복제하지 않는다** — `tests/characterization/conftest.py`에서 import 한다.

```python
"""Characterisation fixtures.

The stub provider is imported from the integration suite rather than
copied: two stubs that drift apart would make the two suites disagree
about what "the same input" means, and the whole point of a
characterisation snapshot is that the input is fixed.
"""

from tests.integration.conftest import StubProvider, StubProviderCall  # noqa: F401
```

이 import가 성립하려면 `tests/`가 패키지여야 한다. `tests/__init__.py`가 없으면 만들고, 있으면 그대로 쓴다.

- [ ] **Step 2: Write the snapshot harness**

`tests/characterization/test_turn_flow_6cells.py`:

```python
"""What the turn flow does today, recorded before P5 moves any of it.

These are characterisation tests, not specifications. They assert nothing
about whether the behaviour is right -- only that splitting unified_turn.py
did not change it. A snapshot that needs updating is a signal to stop and
explain why, not a file to regenerate.

The six cells are the canonical v6 topology (see the P0 baseline doc):

    0  true_baseline        not_allowed  p_death 0.0
    1  baseline_flagship    allowed      0.25
    2  baseline_flagship    not_allowed  0.25
    3  flagship_corruption  allowed      0.25
    4  flagship_corruption  not_allowed  0.25
    5  true_baseline        allowed      0.0

Cell 0 exercises the short-circuit path (no forfeit menu, p_death 0), and
Cell 5 the EV-dominant path.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from squid_game.models.enums import Difficulty, ForfeitCondition, Framing
from squid_game.models.state import GameState, TurnContext

SNAPSHOTS = Path(__file__).parent / "snapshots" / "turn_flow"

CELLS = [
    (0, "true_baseline", "not_allowed", 0.0),
    (1, "baseline_flagship", "allowed", 0.25),
    (2, "baseline_flagship", "not_allowed", 0.25),
    (3, "flagship_corruption", "allowed", 0.25),
    (4, "flagship_corruption", "not_allowed", 0.25),
    (5, "true_baseline", "allowed", 0.0),
]


def _record(manager, provider) -> dict:
    """The deterministic surface of one season: decisions plus exact prompts."""
    return {
        "turns": [
            {
                "action": t.action,
                "forfeited": t.forfeited,
                "thinking_tokens": t.thinking_tokens,
                "score": t.score,
            }
            for t in manager.history()
        ],
        "prompts": [call.prompt for call in provider.calls],
    }


@pytest.mark.parametrize("cell_id,framing,forfeit,p_death", CELLS)
def test_turn_flow_matches_snapshot(cell_id, framing, forfeit, p_death):
    manager, provider = _build_manager(cell_id, framing, forfeit, p_death)
    game_state = GameState(season_id=f"char-cell-{cell_id}", current_turn=1, cumulative_score=30.0)

    for turn_number in range(1, 11):
        context = TurnContext(
            turn_number=turn_number,
            total_turns=10,
            season_id=f"char-cell-{cell_id}",
            cumulative_score=game_state.cumulative_score,
            p_death=p_death,
            framing=Framing(framing),
            forfeit_condition=ForfeitCondition(forfeit),
            difficulty=Difficulty.MEDIUM,
        )
        result = manager.execute_turn(game_state, context)
        if result.forfeit_decision:
            break

    actual = _record(manager, provider)
    snapshot = SNAPSHOTS / f"cell_{cell_id}.json"

    if not snapshot.exists():
        snapshot.parent.mkdir(parents=True, exist_ok=True)
        snapshot.write_text(json.dumps(actual, indent=2, sort_keys=True), encoding="utf-8")
        pytest.fail(f"snapshot created at {snapshot}; re-run to compare")

    expected = json.loads(snapshot.read_text(encoding="utf-8"))
    assert actual == expected
```

`_build_manager`는 `tests/unit/test_unified_turn.py:277`의 `_make_manager`를 본뜬다. 그 헬퍼가 조립하는 것은 실측 기준 일곱 개다: `RiskChoiceLayer(RiskChoiceLayerConfig.default())`, `FramingManager(framing)`, `ForfeitController(forfeit)`, `SurvivalPressure()`, `MeasurementRecorder()`, `CoTCollector()`, `random.Random(seed)`. 특성화 스위트는 여기에 `forfeit_layer`, `use_split_forfeit_layer=True`, `use_psuccess_probe=True`를 더해 v6 정규 경로를 태운다 (`tests/unit/test_unified_turn.py:890`의 `_make_manager_with_layer`가 그 조립을 이미 한다 — 그쪽을 본뜬다).

`execute_turn`의 시그니처는 실측이다 (`unified_turn.py:197`):

```python
def execute_turn(self, game_state: GameState, turn_context: TurnContext) -> TurnResult
```

`game_state`를 변형하지 않으므로(docstring이 명시한다) 루프가 점수를 직접 갱신해야 한다. 위 코드의 `game_state.cumulative_score`는 각 턴의 `result.reward_received`로 갱신한다 — 엔진이 하는 일을 특성화 하네스가 대신한다.

**스텁 응답은 셀마다 고정된 문자열이어야 한다.** `StubProvider`의 `response_fn(call_index, messages)`은 호출 인덱스를 받으므로, 셀당 응답 목록을 리스트로 두고 인덱스로 꺼낸다. 무작위 응답은 스냅샷을 무의미하게 만든다.

`TurnResult`의 필드 이름(`action`, `forfeited`, `thinking_tokens`, `score`)은 `models/results.py`에서 실측해 맞춘다 — `_record`가 읽는 이름이 실제와 다르면 `AttributeError`로 즉시 드러난다.

- [ ] **Step 3: Generate the snapshots and verify they are stable**

```bash
uv run --extra dev pytest tests/characterization/test_turn_flow_6cells.py -q   # 6 fail: snapshots created
uv run --extra dev pytest tests/characterization/test_turn_flow_6cells.py -q   # must pass
uv run --extra dev pytest tests/characterization/test_turn_flow_6cells.py -q   # must pass again
```

두 번째와 세 번째가 모두 통과해야 한다. 한 번이라도 실패하면 기록 대상에 비결정 요소가 섞인 것이다 — 그 필드를 스냅샷에서 빼고, **뺐다는 사실과 이유를 테스트 docstring에 적는다.**

- [ ] **Step 4: Wire the suite into pytest and CI**

`pyproject.toml`:

```toml
testpaths = ["tests/unit", "tests/integration", "tests/characterization"]
```

`tests/unit/test_pytest_ini_options.py`의 기대값도 맞춘다. `.github/workflows/tests.yml`의 `Unit suite` 단계는 `tests/unit`만 돌리므로, 특성화 스위트를 도는 단계를 더한다.

- [ ] **Step 5: Commit**

```bash
git add tests/characterization pyproject.toml tests/unit/test_pytest_ini_options.py .github
git commit -m "test: characterise the six-cell turn flow before splitting it"
```

---

### P5 · Task 2: arena API 응답 스키마 특성화 테스트

`api.py`를 쪼개기 전에 엔드포인트의 응답 **모양**을 고정한다. 값이 아니라 스키마다 — 배포된 프런트엔드가 의존하는 것이 필드 이름과 타입이기 때문이다.

**Files:**
- Create: `tests/characterization/test_api_contract.py`, `tests/characterization/snapshots/api/openapi.json`

**Interfaces:**
- Consumes: `squid_arena.api.app`
- Produces: OpenAPI 스키마 스냅샷 1개와 엔드포인트 목록 고정 테스트.

- [ ] **Step 1: Write the contract test**

```python
"""The public API shape, recorded before P5 moves the routes around.

FastAPI generates an OpenAPI document from the route signatures and the
pydantic models, which makes it the cheapest complete record of the
contract: every path, method, status code, and response field in one
comparable artefact. Splitting api.py into routers must leave it
byte-identical.

This matters more than the usual refactor gate because the frontend is
deployed separately -- web/frontend/ runs on GitHub Pages against the live
Render backend, so a renamed field does not fail a test, it breaks a
running site.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

SNAPSHOT = Path(__file__).parent / "snapshots" / "api" / "openapi.json"


@pytest.fixture(autouse=True)
def _in_memory_repository(monkeypatch, tmp_path):
    monkeypatch.setenv("WEB_ARENA_DSN", ":memory:")
    monkeypatch.setenv("SQUID_THINKING_LOG_DIR", str(tmp_path / "thinking_traces"))


def test_openapi_document_is_unchanged() -> None:
    from squid_arena.api import app

    actual = app.openapi()
    if not SNAPSHOT.exists():
        SNAPSHOT.parent.mkdir(parents=True, exist_ok=True)
        SNAPSHOT.write_text(json.dumps(actual, indent=2, sort_keys=True), encoding="utf-8")
        pytest.fail(f"snapshot created at {SNAPSHOT}; re-run to compare")

    expected = json.loads(SNAPSHOT.read_text(encoding="utf-8"))
    assert actual == expected


def test_every_route_is_still_registered() -> None:
    """Belt and braces: the OpenAPI diff can be large and hard to read.

    This one names the paths, so a missing route reports as a missing route
    rather than as a thousand-line document diff.
    """
    from squid_arena.api import app

    paths = {route.path for route in app.routes}
    for expected in (
        "/api/new_game",
        "/api/state",
        "/api/action",
        "/api/result",
        "/api/reward_preview",
        "/api/leaderboard/models",
        "/api/leaderboard/model_scores",
        "/api/leaderboard/play",
        "/api/logs",
        "/api/logs/{session_id}",
        "/api/report",
        "/api/arena/run",
        "/api/arena/status",
    ):
        assert expected in paths, expected
```

경로 목록은 실측이다 (`grep -n "^@app\." web/squid_arena/api.py`). 목록이 다르면 실측값으로 고친다.

- [ ] **Step 2: Generate and stabilise**

```bash
uv run --extra dev pytest tests/characterization/test_api_contract.py -q   # creates
uv run --extra dev pytest tests/characterization/test_api_contract.py -q   # passes
```

- [ ] **Step 3: Commit**

```bash
git add tests/characterization
git commit -m "test: pin the arena API contract before splitting the router"
```

---

### P5 · Task 3: `unified_turn.py` 분리

1,751줄, 클래스 하나(`UnifiedTurnManager`), 메서드 27개. 세 덩어리를 순수 함수 모듈로 내린다. **클래스를 쪼개지 않는다** — 상태를 나누면 협력 관계를 새로 설계하는 일이 되고, 그것은 이 계획의 위험 한도를 넘는다.

내리는 것 (실측 줄 번호):

| 새 모듈 | 옮기는 메서드 | 근거 |
|---|---|---|
| `turn_conditions.py` | `_should_skip_menu` (1212), `_is_survival_framing` (1223), `_is_corruption_framing` (1228), `_is_baseline_flagship_framing` (1243), `_is_corruption_terminal_framing` (1259), `_resolve_base_p_death` (1178) | 앞 다섯은 이미 `@staticmethod`이고 `self`를 쓰지 않는다. `_resolve_base_p_death`는 `turn_context`만 읽는다 |
| `turn_prompts.py` | `_build_system_prompt` (1097), `_compose_user_message` (1138), `_compose_call1_user_message` (1150), `_derive_action_hint` (1165), `_format_prior_accuracy_summary` (1628), `_format_history_block` (1672) | 문자열 조립. 뒤 두 개는 히스토리를 인자로 받도록 바꾼다 |
| `turn_results.py` | `_build_forfeit_result` (1360), `_build_continue_result` (1394), `_build_forfeit_layer_result` (1434), `_build_forfeit_layer_continue_result` (1506) | `TurnResult` 조립 |

**남는 것:** `__init__`, `execute_turn`, `_execute_turn_forfeit_layer`, `_execute_turn_split_forfeit_layer`, `_resolve_risk_choice`, `_resolve_ground_truth_rule`, `_record`, `_record_history`, `history`, `stake_history`, `forfeit_self_report`. 이것이 상태를 다루는 부분이다.

**Files:**
- Create: `game/squid_game/core/turn_conditions.py`, `turn_prompts.py`, `turn_results.py`
- Modify: `game/squid_game/core/unified_turn.py`
- Test: 기존 `tests/unit/test_unified_turn*.py` 3개 + 특성화 스냅샷

**Interfaces:**
- Consumes: Task 1의 특성화 스냅샷
- Produces: 세 모듈의 공개 함수. `self`를 받던 메서드는 **필요한 값만** 인자로 받는 함수가 된다. 예: `_derive_action_hint(self)` → `derive_action_hint(task_context, forfeit_allowed)`. 정확한 인자는 각 메서드 본문이 실제로 읽는 `self.*` 속성으로 결정한다 — 그 이상을 넘기지 않는다.

- [ ] **Step 1: Confirm the characterisation snapshots pass**

```bash
uv run --extra dev pytest tests/characterization -q
```

통과하지 않으면 **여기서 멈춘다.** 기준선 없이 쪼개는 것이 이 태스크가 피하려는 바로 그 상황이다.

- [ ] **Step 2: Move the condition predicates**

가장 안전한 덩어리부터다 — 다섯 개가 이미 `@staticmethod`다.

`game/squid_game/core/turn_conditions.py`:

```python
"""Which branch of the turn flow applies, decided from the turn context.

These were static methods on UnifiedTurnManager: they read the turn
context and nothing else, so they never belonged to the manager's state.
Moved out so the manager's remaining methods are the ones that actually
need what it holds.

The framing predicates are enumerated rather than derived from a naming
convention -- `_is_corruption_framing` and `_is_corruption_terminal_framing`
are separate questions, and a prefix match would conflate them.
"""
```

메서드 본문을 그대로 옮기고, `unified_turn.py`에서는 import 해서 호출한다. 호출부의 `self._is_corruption_framing(ctx)`가 `is_corruption_framing(ctx)`가 된다.

- [ ] **Step 3: Run the gates after the first move**

```bash
uv run --extra dev pytest tests/characterization tests/unit -q
```

**덩어리마다 게이트를 돌린다.** 세 덩어리를 한 번에 옮기고 실패하면 어느 것이 원인인지 알 수 없다.

- [ ] **Step 4: Move the prompt composition**

`turn_prompts.py`. `_format_prior_accuracy_summary`와 `_format_history_block`은 `self._history`를 읽으므로 히스토리를 인자로 받는 함수가 된다.

**프롬프트 문자열 리터럴을 한 글자도 바꾸지 않는다.** 특성화 스냅샷이 프롬프트 전문을 담고 있으므로 공백 하나가 달라져도 잡힌다 — 그것이 이 스냅샷을 그렇게 설계한 이유다.

- [ ] **Step 5: Run the gates**

```bash
uv run --extra dev pytest tests/characterization tests/unit -q
```

- [ ] **Step 6: Move the result builders**

`turn_results.py`. 네 개 모두 `TurnResult`를 조립하며 `self`에서 읽는 값이 많다 — 어떤 속성을 읽는지 먼저 세고, 그 목록을 인자로 만든다. 인자가 여섯 개를 넘으면 그 덩어리는 **옮기지 않고 남긴다.** 인자 목록이 길다는 것은 그 함수가 아직 상태의 일부라는 신호다.

- [ ] **Step 7: Run every gate**

```bash
uv run --extra dev pytest tests/characterization -q
uv run --extra dev --extra analysis pytest tests/unit tests/integration -q
uv run python scripts/dev/golden_snapshot.py verify --golden ~/golden/squid-restructure
wc -l game/squid_game/core/unified_turn.py
```

`unified_turn.py`가 1,200줄 아래로 내려가야 한다. 그보다 크면 세 덩어리 중 옮기지 못한 것이 있다는 뜻이므로, **무엇을 왜 남겼는지 커밋 메시지에 적는다.**

- [ ] **Step 8: Commit**

```bash
git add game/squid_game/core tests
git commit -m "refactor(core): lift the pure parts out of the turn manager"
```

---

### P5 · Task 4: `api.py` 분리

1,424줄. 구조는 이미 주석으로 구획돼 있어 경계가 뚜렷하다 (실측 줄 번호):

| 구획 | 줄 | 목적지 |
|---|---|---|
| CORS 설정 (`_cors_origins`) | 72–104 | `deps.py` |
| repository 초기화 | 105–150 | `deps.py` |
| 입력 정제 (`sanitize_nickname`, `sanitize_campaign_id`) | 151–190 | `deps.py` |
| rate limit (`_client_key`, `_check_rate_limit`, `_strip_status_block`) | 191–246 | `deps.py` |
| pydantic 모델 전량 | 247–620 | `schemas.py` |
| 변환·영속 헬퍼 (`_session_record_to_row`, `_model_stats_to_row`, `_persist_result`, `_cell_meta`, `_cell_order_index`, `_turn_is_forfeit`) | 517–752 | `reporting.py` |
| 게임 라우트 (`/api/new_game`, `/state`, `/action`, `/result`, `/reward_preview`) | 758–991 | `routes_game.py` |
| 리더보드 라우트 | 992–1074 | `routes_leaderboard.py` |
| 로그·리포트 라우트 | 1075–1361 | `routes_logs.py` |
| arena 라우트 | 1362–1424 | `routes_arena.py` |

**Files:**
- Create: `web/squid_arena/{schemas,deps,reporting,routes_game,routes_leaderboard,routes_logs,routes_arena}.py`
- Modify: `web/squid_arena/api.py`

**Interfaces:**
- Consumes: Task 2의 OpenAPI 스냅샷
- Produces: 각 `routes_*.py`가 `router = APIRouter()`를 노출하고, `api.py`가 `app.include_router(...)`로 조립한다. **`squid_arena.api.app`은 그대로 존재한다.** `schemas.py`는 pydantic 모델 전량을, `deps.py`는 `get_repository` 래퍼와 `check_rate_limit`, `sanitize_nickname`, `sanitize_campaign_id`, `cors_origins`를 노출한다.

- [ ] **Step 1: Confirm the contract snapshot passes**

```bash
uv run --extra dev pytest tests/characterization/test_api_contract.py -q
```

- [ ] **Step 2: Extract `schemas.py` first**

가장 안전하다 — pydantic 모델은 서로만 참조하고 라우트를 모른다. 모델 정의를 그대로 옮기고 `api.py`에서 `from squid_arena.schemas import *` 대신 **명시적으로** import 한다 (`*`는 OpenAPI 문서에 영향은 없지만 무엇이 어디서 오는지를 지운다).

**클래스 이름과 필드를 바꾸지 않는다.** OpenAPI 문서의 `components.schemas` 키가 클래스 이름에서 나오므로, 이름을 바꾸면 스냅샷이 즉시 깨진다 — 그리고 그 깨짐은 프런트엔드가 겪을 깨짐과 같은 것이다.

- [ ] **Step 3: Run the contract gate**

```bash
uv run --extra dev pytest tests/characterization/test_api_contract.py -q
uv run --extra dev --extra analysis pytest tests/unit/test_api_web_arena.py -q
```

- [ ] **Step 4: Extract `deps.py`**

CORS · repository · rate limit · sanitizer. `_repository = get_repository()`가 모듈 스코프에서 실행되는 부분(`api.py:144`)은 그대로 `deps.py`로 옮긴다 — **지연 초기화로 바꾸지 않는다.** 그것은 동작 변경이며, `tests/unit/test_import_smoke.py`가 이 import-time 부작용을 명시적으로 sandbox 하고 있다. 옮기면 그 테스트의 대상 모듈 이름도 `squid_arena.deps`로 바뀐다.

- [ ] **Step 5: Extract `reporting.py`, then the four route modules**

라우트는 한 모듈씩 옮기고 **모듈마다 게이트를 돌린다.**

각 `routes_*.py`의 형태:

```python
"""Game routes: one session's lifecycle from new_game to result."""

from fastapi import APIRouter, Request

from squid_arena import deps, schemas

router = APIRouter()


@router.post("/api/new_game", response_model=schemas.NewGameResponse)
def new_game(req: schemas.NewGameRequest, request: Request):
    ...
```

`api.py`에 남는 것:

```python
"""The Web Arena backend's ASGI app.

Assembly only: the routes live in routes_*.py, the models in schemas.py,
and the cross-cutting pieces (CORS, repository, rate limiting, input
sanitisation) in deps.py. `app` stays in this module because the
Dockerfile's CMD, render.yaml's health check, start_servers.sh and the
integration tests all name `squid_arena.api:app`.
"""

app = FastAPI(...)
app.add_middleware(CORSMiddleware, allow_origins=deps.cors_origins(), ...)

app.include_router(routes_game.router)
app.include_router(routes_leaderboard.router)
app.include_router(routes_logs.router)
app.include_router(routes_arena.router)
```

**`include_router` 순서는 라우트 등록 순서를 결정하고, 그 순서가 OpenAPI 문서의 `paths` 순서에 반영된다.** 스냅샷 비교는 `sort_keys=True`로 저장했으므로 순서에는 영향받지 않지만, `test_every_route_is_still_registered`가 누락을 잡는다. 원본 파일의 정의 순서와 같게 유지한다.

- [ ] **Step 6: Run every gate**

```bash
uv run --extra dev pytest tests/characterization -q
uv run --extra dev --extra analysis pytest tests/unit tests/integration -q
wc -l web/squid_arena/api.py
```

`api.py`가 150줄 아래로 내려가야 한다 — 조립만 남기 때문이다.

- [ ] **Step 7: Verify the deployed shape**

```bash
docker build -t squid-arena-p5 . \
  && docker run --rm -e PORT=8599 -d --name squid-p5 squid-arena-p5 \
  && sleep 5 \
  && curl -sf http://127.0.0.1:8599/api/leaderboard/models >/dev/null && echo "image OK"; \
  docker rm -f squid-p5
```

- [ ] **Step 8: Commit**

```bash
git add web/squid_arena tests
git commit -m "refactor(api): split the arena backend into routers, schemas and deps"
```

---

### P5 · Task 5: P5 마감

- [ ] **Step 1: Run the full gate set**

```bash
uv run --extra dev --extra analysis pytest tests/unit tests/integration tests/characterization -q
node --test tests/web/
uv run python scripts/dev/golden_snapshot.py verify --golden ~/golden/squid-restructure
```

- [ ] **Step 2: Record the result**

`docs/superpowers/plans/2026-08-30-p0-baseline.md`에 `## P5 result` 문단을 더한다. 여기에는 파일 크기 변화도 적는다.

```markdown
- `game/squid_game/core/unified_turn.py`: 1,751 -> <실측>
- `web/squid_arena/api.py`: 1,424 -> <실측>
- Characterisation snapshots: 6 turn-flow cells + 1 OpenAPI document, all unchanged.
```

옮기지 못하고 남긴 덩어리가 있으면 **무엇을 왜 남겼는지** 함께 적는다. 남긴 것을 적지 않으면 다음 사람이 같은 판단을 다시 해야 한다.

- [ ] **Step 3: Commit**

```bash
git add docs/superpowers/plans/2026-08-30-p0-baseline.md
git commit -m "docs: record the P5 result and what stayed put"
```

---

---

## P5 게이트

1. `tests/characterization/`이 존재하고 `pyproject.toml`의 `testpaths`와 CI에 연결돼 있다.
2. 6셀 턴 플로우 스냅샷과 OpenAPI 스냅샷이 P5 전후로 동일하다.
3. `unified_turn.py` < 1,200줄, `api.py` < 150줄.
4. `squid_arena.api:app`이 그대로 import 되고 docker 이미지가 부팅해 응답한다.
5. unit · integration · characterization 신규 실패 0, 골든 스냅샷 84개 동일.
6. 프롬프트 템플릿 문자열과 보상 계산이 한 글자도 바뀌지 않았다 (스냅샷이 증거다).

### P5 범위 밖

- 문서 4분할, `results/` 분리, `assets/` 정리 (P6)
- 엔드포인트 추가·개명, 응답 필드 변경
- `UnifiedTurnManager`의 상태 분해 — 상태를 나누는 것은 협력 관계 재설계이며 이 단계의 위험 한도를 넘는다
- 프로바이더 계층(`providers/` 12모듈) 정리

---

# Phase P6 — 문서 · 산출물 정리

문서를 목적별 4분할하고, 재생성 가능한 분석 산출물을 원시 데이터에서 떼어내며, 세 문서가 다르게 주장하는 보상 계산을 하나의 사실로 통일한다.

**접근:** 재구조화의 마지막 단계이자 코드를 거의 건드리지 않는 단계다. 원칙은 P1과 같다 — **수명이 다른 것은 같은 디렉터리에 두지 않는다.** 지금 `outputs/`에는 재현 비용이 큰 원시 세션 데이터(LFS 666 MB)와 명령 하나로 다시 만들 수 있는 분석 산출물이 섞여 있고, `docs/`에는 논문 · 설계 · 리포트 · 작업 기록이 섞여 있다. 위험은 딱 하나이고 그것이 이 계획의 형태를 결정한다: **`.gitattributes`의 LFS 패턴은 `outputs/**/*.jsonl` 하나뿐이다.** `.jsonl` 파일이 `outputs/` 밖으로 나가는 순간 LFS 필터가 걸리지 않아 수백 MB가 일반 blob으로 저장소에 박힌다. 그래서 Task 2의 첫 단계가 "옮길 대상에 `.jsonl`이 있는지 먼저 센다"이다.

**추가 제약:**

- **`.jsonl`을 `outputs/` 밖으로 내보내지 않는다.** `.gitattributes`는 `outputs/**/*.jsonl` 한 줄뿐이므로 경로가 바뀌면 LFS 필터가 사라진다. 옮겨야 하면 **먼저** `.gitattributes`에 새 패턴을 추가하고 그 커밋을 따로 남긴다.
- **문서를 옮기면서 내용을 고치지 않는다.** 이동(Task 1)과 정정(Task 4)은 다른 커밋이다. 섞으면 리뷰가 "옮긴 것"과 "바뀐 것"을 구분할 수 없다.

## P6 File Structure

P6 완료 시점:

```
docs/
  paper/      content.tex  sections/            (구 docs/en)
  design/     설계 SSOT — 죽은 참조의 목적지
  reports/    reasoning-probe-report.html  repo-restructure-plan.html
              cluster-c-cot-analysis.md  sd-cognitive-test-a-did.md
  history/    plans/  specs/                    (구 docs/superpowers)
outputs/      final_results/  web_arena/        원시 데이터 전용 (LFS)
results/      call1_ri_analysis/  reasoning_probe/
assets/
  brand/      GistLab Logo
  figures/    *.png  *.svg  rules-demo/
```

---

### P6 · Task 1: 문서 4분할

`docs/`는 지금 네 종류를 한 층에 담고 있다. 논문 소스(`en/`), 분석 리포트(`analysis/`, `reports/`, 그리고 층위 없이 떠 있는 마크다운 2개), 작업 기록(`superpowers/`)이다. 설계 SSOT(`design/`)는 아예 없다 — P4가 정정한 죽은 참조 28건이 원래 가리키던 곳이고, 지금부터는 실재하는 목적지가 된다.

**Files:**
- Move: `docs/en/` → `docs/paper/`
- Move: `docs/analysis/reasoning-probe-report.html` → `docs/reports/`
- Move: `docs/cluster-c-cot-analysis.md`, `docs/sd-cognitive-test-a-did.md` → `docs/reports/`
- Move: `docs/superpowers/` → `docs/history/`
- Create: `docs/design/README.md`, `docs/README.md`
- Modify: 이 경로들을 가리키는 참조 전부
- Test: `tests/unit/test_docs_layout.py` (신규)

**Interfaces:**
- Consumes: 없음
- Produces: `docs/` 하위 네 디렉터리. 각각 `README.md`로 "여기 무엇이 들어가는가"를 한 문단 밝힌다.

**주의 — 도구 관례와의 충돌.** superpowers의 writing-plans 스킬은 계획서를 `docs/superpowers/plans/`에 쓰도록 기본값이 잡혀 있다. `docs/history/`로 옮기면 그 기본값과 어긋난다. 스펙 §3.4가 이동을 명시했으므로 옮기되, **`docs/README.md`와 `CLAUDE.md`에 새 위치를 한 줄로 못박아** 다음 에이전트가 기본값이 아니라 이 저장소의 사실을 따르게 한다. 이 충돌을 기록하지 않고 옮기면, 다음 계획서가 조용히 `docs/superpowers/plans/`에 다시 생긴다.

- [ ] **Step 1: Write the failing test**

`tests/unit/test_docs_layout.py`:

```python
"""docs/ is split by what a document is for, not by who wrote it.

Four kinds live here and they have different lifetimes: the paper source
changes with the manuscript, design docs are the spec of record, reports
are dated findings that are never revised, and history is an append-only
log of how the work went. Mixing them is what produced a docs/ where two
markdown files sat loose at the top level with no indication of which kind
they were.
"""

from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
DOCS = REPO_ROOT / "docs"
KINDS = ("paper", "design", "reports", "history")


def test_the_four_kinds_exist() -> None:
    for kind in KINDS:
        assert (DOCS / kind).is_dir(), kind


def test_nothing_sits_loose_at_the_top_level() -> None:
    loose = {p.name for p in DOCS.glob("*.md")} - {"README.md"}
    assert loose == set()


def test_every_kind_says_what_belongs_in_it() -> None:
    for kind in KINDS:
        readme = DOCS / kind / "README.md"
        assert readme.exists(), kind
        assert len(readme.read_text(encoding="utf-8").split()) >= 20, kind
```

- [ ] **Step 2: Run it to verify it fails**

```bash
uv run --extra dev --extra analysis pytest tests/unit/test_docs_layout.py -q
```

- [ ] **Step 3: Move**

```bash
cd docs
git mv en paper
mkdir -p reports design
git mv analysis/reasoning-probe-report.html reports/
rmdir analysis
git mv cluster-c-cot-analysis.md sd-cognitive-test-a-did.md reports/
git mv superpowers history
cd -
```

`docs/reports/repo-restructure-plan.html`은 이미 제자리다.

- [ ] **Step 4: Write the four READMEs and `docs/README.md`**

`docs/design/README.md`가 특히 중요하다 — 이 디렉터리는 비어 있는 채로 시작하며, **왜 비어 있는지**가 그 자체로 정보다.

```markdown
# docs/design/

The specification of record. A document here is the answer to "what is this
supposed to do", kept current with the code.

It starts empty, and that is a fact worth knowing rather than a gap to
apologise for: 28 code comments referenced a `docs/design/` tree that never
existed in the git history, and P4 resolved each one by either summarising
the spec inline or marking it `# spec: lost`. Nothing was recovered from a
backup, because there was nothing to recover. New specs land here; the old
ones are gone.
```

`docs/history/README.md`에 도구 관례 충돌을 적는다:

```markdown
# docs/history/

Append-only record of how the work went: implementation plans and design
specs, one per feature, dated. Nothing here is maintained -- a plan
describes what was true when it was written.

**New plans and specs go here**, in `plans/` and `specs/`. The superpowers
writing-plans skill defaults to `docs/superpowers/plans/`; that path no
longer exists in this repository. Use this one.
```

- [ ] **Step 5: Repoint every reference**

```bash
grep -rn "docs/en/\|docs/analysis/\|docs/superpowers/" --include='*.py' --include='*.md' --include='*.yml' --include='*.toml' --include='*.sh' \
  . | grep -v '^./.git' | grep -v __pycache__
```

**과거 기록 문서 안의 참조는 고치지 않는다** (P1의 Global Constraints와 같은 규칙). 고칠 대상은 운영 문서와 실행되는 파일이다: `README.md`, `CLAUDE.md`, `AGENTS.md`, 워크플로, 스크립트, 테스트, 그리고 `docs/*/README.md`.

`tests/unit/test_import_smoke.py`와 P0 계획서가 서로를 경로로 참조하고 있으므로 (`docs/superpowers/plans/2026-08-30-p0-baseline.md`), 이 둘은 반드시 고친다.

- [ ] **Step 6: Run the gates and commit**

```bash
uv run --extra dev --extra analysis pytest tests/unit -q
git add docs tests README.md CLAUDE.md AGENTS.md
git commit -m "docs: split docs/ by what each document is for"
```

---

### P6 · Task 2: 재생성 가능한 산출물을 `results/`로

`outputs/`는 두 종류를 담고 있다. 재현 비용이 큰 원시 세션 데이터(LFS, 666 MB)와, 명령 하나로 다시 만들 수 있는 분석 산출물이다. 뒤엣것을 `results/`로 옮긴다.

**이 태스크의 유일한 실질 위험은 LFS다.** `.gitattributes`는 한 줄뿐이다:

```
outputs/**/*.jsonl filter=lfs diff=lfs merge=lfs -text
```

`.jsonl` 파일이 `outputs/` 밖으로 나가면 필터가 사라지고, 다음 `git add`가 그 내용을 일반 blob으로 저장소에 박아 넣는다. 되돌리려면 히스토리를 다시 써야 한다.

**Files:**
- Move: `outputs/call1_ri_analysis/` → `results/call1_ri_analysis/`
- Move: `outputs/reasoning_probe/` → `results/reasoning_probe/`
- Modify: `.gitignore` (임베딩 캐시 경로), 산출 경로를 쓰는 스크립트
- Create: `results/README.md`, `outputs/README.md`
- Test: `tests/unit/test_artefact_layout.py` (신규)

**Interfaces:**
- Consumes: 없음
- Produces: `results/` 아래 두 디렉터리. `outputs/`에는 `final_results/`와 `web_arena/`만 남는다.

- [ ] **Step 1: Count the `.jsonl` files in what you are about to move**

```bash
find outputs/call1_ri_analysis outputs/reasoning_probe -name '*.jsonl' | tee /tmp/jsonl_to_move.txt | wc -l
```

**0이면** 그대로 진행한다. **1 이상이면** 먼저 `.gitattributes`에 패턴을 추가하고 그것만 담은 커밋을 만든 뒤 다음 단계로 간다:

```
results/**/*.jsonl filter=lfs diff=lfs merge=lfs -text
```

```bash
git add .gitattributes
git commit -m "chore(lfs): track results/ jsonl before anything moves there"
```

순서가 중요하다. 파일을 먼저 옮기면 그 사이의 `git add`가 필터 없이 걸린다.

- [ ] **Step 2: Write the failing test**

```python
"""outputs/ is raw data; results/ is what the pipeline made from it.

The split is by cost of recreation. outputs/ holds 666 MB of LFS-tracked
session traces from four canonical runs that cost real API budget to
produce. results/ holds artefacts one command regenerates. Keeping them
in one directory meant every rule about one of them had to carve out an
exception for the other.
"""

from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]


def test_outputs_holds_only_raw_data() -> None:
    subdirs = {p.name for p in (REPO_ROOT / "outputs").iterdir() if p.is_dir()}
    assert subdirs == {"final_results", "web_arena"}


def test_results_holds_the_regenerable_artefacts() -> None:
    results = REPO_ROOT / "results"
    assert (results / "call1_ri_analysis").is_dir()
    assert (results / "reasoning_probe").is_dir()


def test_no_jsonl_escaped_lfs_tracking() -> None:
    """A .jsonl outside outputs/ is only safe if .gitattributes says so."""
    attributes = (REPO_ROOT / ".gitattributes").read_text(encoding="utf-8")
    stray = list((REPO_ROOT / "results").rglob("*.jsonl"))
    if stray:
        assert "results/**/*.jsonl filter=lfs" in attributes, [str(p) for p in stray]
```

- [ ] **Step 3: Move**

```bash
mkdir -p results
git mv outputs/call1_ri_analysis results/call1_ri_analysis
git mv outputs/reasoning_probe results/reasoning_probe
```

- [ ] **Step 4: Repoint the producers and the ignore rules**

```bash
grep -rn "outputs/call1_ri_analysis\|outputs/reasoning_probe" --include='*.py' --include='*.md' --include='*.toml' \
  game web db scripts tests docs .gitignore | grep -v __pycache__ | grep -v '^docs/history/'
```

`.gitignore`의 임베딩 캐시 규칙도 옮긴다:

```
# SentenceBERT embedding cache for scripts/analysis/probe_reasoning_embeddings.py.
# Regenerable from the turn traces; ~13 MB per (channel, mask variant).
results/reasoning_probe/_embedding_cache/
```

- [ ] **Step 5: Write the two READMEs**

`outputs/README.md`:

```markdown
# outputs/

Raw session data only. `final_results/` holds the four canonical 2026-04-22
runs (LFS, ~666 MB of `*_turns.jsonl`); `web_arena/` holds the live arena's
database and its own run traces.

Nothing here is regenerable — reproducing it costs API budget — and nothing
here may be moved: the golden-snapshot harness resolves runs at
`outputs/final_results/`, and `.gitattributes` tracks `outputs/**/*.jsonl`
through LFS by path.

Analysis artefacts go in `results/`.
```

`results/README.md`:

```markdown
# results/

Analysis artefacts, all regenerable. Delete anything here and the command
named in the subdirectory's own report will rebuild it.

- `call1_ri_analysis/` — `uv run python -m scripts.analysis.analyze_call1_ri`
- `reasoning_probe/` — `uv run --extra probe python -m scripts.analysis.probe_reasoning_embeddings`

The phase-3 artefacts the golden snapshot gates on are NOT here: they live
beside their run under `outputs/final_results/<run>/phase3_analysis/`,
because they are keyed to that run.
```

- [ ] **Step 6: Regenerate one artefact to prove the path change works**

```bash
uv run python -m scripts.analysis.analyze_call1_ri
git status --short results/
```

`git status`가 내용 변경 없음(또는 예상된 재생성만)을 보여야 한다.

- [ ] **Step 7: Run the gates and commit**

```bash
uv run --extra dev --extra analysis pytest tests/unit -q
uv run python scripts/dev/golden_snapshot.py verify --golden ~/golden/squid-restructure
git add results outputs tests .gitignore scripts docs
git commit -m "chore: separate regenerable results from raw session data"
```

**`git add outputs/`를 쓰지 않는다.** 위 명령의 `outputs`는 새로 만든 `outputs/README.md`만 담기지만, 그마저도 `git add outputs/README.md`로 좁히는 편이 안전하다.

---

### P6 · Task 3: `assets/` 정리

`figures/`(28 MB)에 논문 그림과 브랜드 자산이 섞여 있고, `web/frontend/assets/`(12 MB)와 중복이 있는지 확인되지 않았다.

**Files:**
- Create: `assets/brand/`, `assets/figures/`
- Move: `figures/GistLab Logo` → `assets/brand/`, 나머지 `figures/*` → `assets/figures/`
- Modify: 그림 경로를 쓰는 스크립트·문서, `.gitignore`
- Test: `tests/unit/test_artefact_layout.py`에 추가

**Interfaces:**
- Consumes: 없음
- Produces: `assets/brand/`, `assets/figures/`. `figures/`는 사라진다.

- [ ] **Step 1: Find the duplicates before moving anything**

```bash
find figures web/frontend/assets -type f -exec shasum {} \; \
  | sort | awk '{print $1}' | uniq -d > /tmp/dup_hashes.txt
wc -l /tmp/dup_hashes.txt
find figures web/frontend/assets -type f -exec shasum {} \; | grep -F -f /tmp/dup_hashes.txt
```

중복이 나오면 **어느 쪽이 소비되는지** 확인하고 (`grep -rn "<파일명>" web/frontend docs scripts`), 소비되는 쪽을 남긴다. 프런트엔드가 쓰는 자산은 `web/frontend/assets/`에 남아야 한다 — Pages 아티팩트가 그 디렉터리이기 때문이다.

- [ ] **Step 2: Check what the rules-demo frames are**

```bash
ls figures/rules-demo | head
du -sh figures/rules-demo
```

스펙 §3.4는 "`how-to-play.gif`의 중간 산출물인 프레임 시퀀스는 ignore 한다"고 지정했다. 프레임 시퀀스가 맞으면 `.gitignore`에 추가하고 추적에서 뺀다 (`git rm -r --cached`). 최종 GIF만 자산으로 남긴다.

- [ ] **Step 3: Move**

```bash
mkdir -p assets/brand assets/figures
git mv "figures/GistLab Logo" assets/brand/
git mv figures/*.png figures/*.svg assets/figures/
git mv figures/rules-demo assets/figures/ 2>/dev/null || true
git mv figures/README.md assets/figures/
rmdir figures 2>/dev/null || ls figures
```

- [ ] **Step 4: Repoint**

```bash
grep -rn "figures/" --include='*.py' --include='*.md' --include='*.tex' --include='*.yml' \
  game web db scripts tests docs README.md CLAUDE.md AGENTS.md | grep -v '^docs/history/' | grep -v __pycache__
```

`docs/paper/` 아래 LaTeX의 `\includegraphics` 경로가 여기 걸린다. **논문 빌드가 깨지지 않는지 확인한다** — 빌드 도구가 없으면 경로 존재만이라도 확인한다:

```bash
grep -rhn "includegraphics" docs/paper | grep -oE "\{[^}]+\}" | tr -d '{}' | while read -r p; do
  [ -e "docs/paper/$p" ] || [ -e "$p" ] || echo "MISSING: $p"
done
```

- [ ] **Step 5: Run the gates and commit**

```bash
uv run --extra dev --extra analysis pytest tests/unit -q
node --test tests/web/
git add assets docs tests .gitignore README.md CLAUDE.md AGENTS.md
git commit -m "chore(assets): separate brand assets from paper figures"
```

---

### P6 · Task 4: 세 문서가 다르게 주장하는 보상 계산을 하나로

실측된 사실 충돌이다. **같은 계산에 대해 문서 셋이 서로 다른 것을 주장한다.**

| 문서 | 주장 |
|---|---|
| `CLAUDE.md:107-121` | EV-positive, `k = 10`. "**Do not describe this as Equal-EV in the paper.**" 2026-04-22 런 출력으로 검증됨 — turn 1 (S=30)에서 `psuccess_self=33` → reward 71, 25 → 78, 75 → 32. 모두 `k=10`의 정확한 값이며 `k=0`에서는 불가능 |
| `README.md:18` | "Equal-EV by construction" |
| `AGENTS.md:8, 98, 112, 126, 213` | Equal-EV (5곳) |

`CLAUDE.md`만 실측 근거를 달고 있고 나머지 둘은 달지 않았다. **`CLAUDE.md`가 사실이다.** `k=0` Equal-EV는 코드 기본값(`models/config.py`의 `delta_s_continue = 0.0`)이지만 정규 런은 `k=10`으로 돌았다 — 즉 README와 AGENTS는 코드 기본값을 설명하면서 실행된 실험을 설명하는 척하고 있다.

**Files:**
- Modify: `README.md`, `AGENTS.md`
- Test: `tests/unit/test_docs_agree_on_the_reward.py` (신규)

**Interfaces:**
- Consumes: 없음
- Produces: 보상 계산 서술이 `CLAUDE.md` 한 곳에만 존재하고, 나머지 둘은 그것을 참조한다.

- [ ] **Step 1: Write the failing test**

```python
"""The reward calculation is stated once, and the paper must not miscall it.

Three documents described it three ways: CLAUDE.md as EV-positive with
k = 10 (and with the arithmetic verified against the 2026-04-22 run
outputs), README.md and AGENTS.md as Equal-EV. Equal-EV is the k = 0
degenerate case -- the code's default, but not what the canonical runs
used. The claim that survived is the one with evidence behind it.

This is asserted as a test because the duplication is what caused the
drift: the same fact written in three places diverged the moment one of
them was updated.
"""

from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]


def test_only_claude_md_states_the_calibration() -> None:
    for name in ("README.md", "AGENTS.md"):
        text = (REPO_ROOT / name).read_text(encoding="utf-8")
        assert "Equal-EV" not in text, name


def test_claude_md_still_carries_the_warning() -> None:
    text = (REPO_ROOT / "CLAUDE.md").read_text(encoding="utf-8")
    assert "k = 10" in text
    assert 'Do not describe this as "Equal-EV" in the paper' in text
```

- [ ] **Step 2: Run it to verify it fails**

Expected: 첫 테스트가 두 파일 모두에서 FAIL.

- [ ] **Step 3: Fix README.md**

`README.md:18`을 교체한다:

```markdown
- **EV-positive CONTINUE by construction.** The continue reward is solved so
  that continuing is EV-dominant by a fixed margin (`k = 10`), not so that
  the agent is indifferent. Any systematic deviation is attributable to
  motivation, not arithmetic error. See CLAUDE.md, "EV-positive CONTINUE
  Calibration", for the formula and the run-output verification — this is
  the only place it is stated.
```

- [ ] **Step 4: Reduce AGENTS.md to a pointer**

스펙 §3.4가 지정한 대로 `AGENTS.md`를 `CLAUDE.md` 참조로 축약한다. 실측 5곳의 Equal-EV 서술이 전부 그 안에 있으므로, 축약이 곧 정정이다.

```markdown
# AGENTS.md

This repository's agent instructions live in [CLAUDE.md](CLAUDE.md). Read
that file.

AGENTS.md used to carry its own copy of the experiment description, which is
how it came to state the reward calibration as "Equal-EV" while CLAUDE.md
stated it as EV-positive with `k = 10`. Only one of the two had the run
outputs behind it. One copy, one fact.
```

**축약 전에 `AGENTS.md`에만 있고 `CLAUDE.md`에는 없는 내용이 있는지 확인한다:**

```bash
diff <(grep -oE '^#{1,3} .*' AGENTS.md) <(grep -oE '^#{1,3} .*' CLAUDE.md)
```

`AGENTS.md`에만 있는 절이 나오면 **먼저 `CLAUDE.md`로 옮긴 뒤** 축약한다. 축약이 정보 삭제가 되어서는 안 된다.

- [ ] **Step 5: Run the gates and commit**

```bash
uv run --extra dev --extra analysis pytest tests/unit -q
git add README.md AGENTS.md CLAUDE.md tests
git commit -m "docs: state the reward calibration once, where the evidence is"
```

---

### P6 · Task 5: 재구조화 마감

- [ ] **Step 1: Run every gate one final time**

```bash
uv run --extra dev --extra analysis pytest tests/unit tests/integration tests/characterization -q
node --test tests/web/
uv run python scripts/dev/golden_snapshot.py verify --golden ~/golden/squid-restructure
docker build -t squid-arena-final . && docker run --rm -e PORT=8599 -d --name squid-final squid-arena-final \
  && sleep 5 && curl -sf http://127.0.0.1:8599/api/leaderboard/models >/dev/null && echo "image OK"; \
  docker rm -f squid-final
```

- [ ] **Step 2: Verify the Pages artefact path one more time**

```bash
grep -n "path:" .github/workflows/deploy-pages.yml
```

`web/frontend`여야 한다. 이 값이 틀리면 백엔드 소스가 공개 사이트에 올라간다 — P1 Task 3에서 고쳤지만, P6이 `web/` 주변을 마지막으로 건드리는 단계이므로 여기서 다시 확인한다.

- [ ] **Step 3: Record the final result**

`docs/history/plans/2026-08-30-p0-baseline.md` (Task 1에서 옮겨진 경로)에 `## P6 result`와 재구조화 전체 요약을 더한다. P0부터 P6까지 각 단계의 실측 테스트 수와 골든 스냅샷 결과를 한 표로 남긴다.

- [ ] **Step 4: Update CLAUDE.md's structure block to the final truth**

P1에서 한 번 고쳤지만 P2~P6이 그 아래를 바꿨다. 최종 구조로 갱신한다: `game/`, `web/`, `db/`, `configs/`, `scripts/`(5분류), `tests/`(unit·integration·characterization·web), `outputs/`, `results/`, `assets/`, `docs/`(4분할).

- [ ] **Step 5: Commit**

```bash
git add docs CLAUDE.md
git commit -m "docs: record the finished restructure"
```

---

---

## P6 게이트

1. `docs/`가 `paper/` · `design/` · `reports/` · `history/` 넷으로 갈리고 각각 README를 갖는다. 최상위에 떠 있는 마크다운이 없다.
2. `outputs/`에 `final_results/`와 `web_arena/`만 남고, 재생성 가능한 산출물은 `results/`에 있다.
3. `results/` 아래 `.jsonl`이 있다면 `.gitattributes`가 그 경로를 LFS로 잡고 있다.
4. `figures/`가 사라지고 `assets/brand/`와 `assets/figures/`가 존재한다.
5. `README.md`와 `AGENTS.md`에 "Equal-EV" 서술이 없고, 보상 계산은 `CLAUDE.md` 한 곳에만 있다.
6. unit · integration · characterization 신규 실패 0, 골든 스냅샷 84개 동일, docker 이미지 부팅, Pages 아티팩트 경로가 `web/frontend`.
7. `docs/history/plans/2026-08-30-p0-baseline.md`에 P0–P6 전체 결과표가 있다.

### P6 범위 밖

- 논문 내용 수정 (`docs/paper/`는 이동만 한다)
- `outputs/final_results/` 원시 데이터의 이동·삭제 (스펙 §7이 금지)
- R2 비례검정, FDR 보정 (스펙 §8)
- 새 설계 문서 작성 — `docs/design/`은 목적지로 만들어 두는 것까지가 P6이다

---

# 재구조화 전체 완료 조건

여섯 단계가 모두 끝났을 때 다음이 전부 참이다.

1. `src/`와 `interface/`가 없고 `game/` · `web/` · `db/` 셋이 각각 파이썬 패키지를 하나씩 담는다.
2. `sys.path.insert` / `sys.path.append`가 저장소에 0건이다.
3. `analysis/` 최상위에 `__init__.py` 외의 `.py`가 없고 다섯 하위 패키지(`shared`, `cognitive`, `selfreport`, `behavioral`, `semantic`)가 존재한다.
4. `scripts/` 최상위에 `__init__.py` 외의 `.py`가 없고 여섯 하위 디렉터리 각각에 README가 있다.
5. `unified_turn.py` < 1,200줄, `api.py` < 150줄.
6. `docs/`가 `paper/` · `design/` · `reports/` · `history/` 넷으로 갈리고, `outputs/`에 원시 데이터만 남으며 `results/`가 재생성 가능한 산출물을 담는다.
7. 보상 계산 서술이 `CLAUDE.md` 한 곳에만 있다.
8. unit · integration · characterization 신규 실패 0, 골든 스냅샷 84개 바이트 동일, docker 이미지 부팅, Pages 아티팩트 경로가 `web/frontend`.
9. `docs/history/plans/2026-08-30-p0-baseline.md`에 P0–P6 전체 결과표가 있다.

# 재구조화 전체 범위 밖

- **R2 비례검정 미구현** — `motivation._baseline_persistence_behavioral`은 서술 통계와 부트스트랩 CI만 낸다. Cell 5 비포기율 ≥ 0.9 단측 검정은 존재하지 않는다.
- **FDR 보정 미구현** — 5가설 패밀리는 현재 무보정으로 보고된다.
- 두 항목 모두 실재하는 결함이지만 이번 작업은 구조 작업이다. 섞으면 골든 스냅샷 diff가 무의미해진다 (스펙 §8).
- 논문 내용 수정, 엔드포인트 추가·개명, 프로바이더 계층 정리, 레거시 코드 삭제.
