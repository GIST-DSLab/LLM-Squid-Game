# P6 문서 · 산출물 정리 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 문서를 목적별 4분할하고, 재생성 가능한 분석 산출물을 원시 데이터에서 떼어내며, 세 문서가 서로 다르게 주장하고 있는 보상 계산을 하나의 사실로 통일한다.

**Architecture:** 재구조화의 마지막 단계이자 코드를 거의 건드리지 않는 단계다. 원칙은 P1과 같다 — **수명이 다른 것은 같은 디렉터리에 두지 않는다.** 지금 `outputs/`에는 재현 비용이 큰 원시 세션 데이터(LFS 666 MB)와 명령 하나로 다시 만들 수 있는 분석 산출물이 섞여 있고, `docs/`에는 논문 · 설계 · 리포트 · 작업 기록이 섞여 있다. 위험은 딱 하나이고 그것이 이 계획의 형태를 결정한다: **`.gitattributes`의 LFS 패턴은 `outputs/**/*.jsonl` 하나뿐이다.** `.jsonl` 파일이 `outputs/` 밖으로 나가는 순간 LFS 필터가 걸리지 않아 수백 MB가 일반 blob으로 저장소에 박힌다. 그래서 Task 2의 첫 단계가 "옮길 대상에 `.jsonl`이 있는지 먼저 센다"이다.

**Tech Stack:** Git LFS, GitHub Actions (Pages), 마크다운, LaTeX (`docs/en/`).

**Spec:** `docs/superpowers/specs/2026-08-30-repo-3tier-restructure-design.md` (§3.4 문서·산출물, §6 P6 행, §7 금지 사항)

**선행 조건:** P5 완료.

## Global Constraints

- 작업 디렉터리는 워크트리 `<repo>/.claude/worktrees/squid-restructure`, 브랜치 `restructure/3tier`.
- **`outputs/` 아래 원시 데이터를 옮기지 않는다** (스펙 §7). 정규 런 4종은 `outputs/final_results/`에 그대로 남는다. 옮기는 것은 **재생성 가능한 분석 산출물뿐**이다.
- **`.jsonl`을 `outputs/` 밖으로 내보내지 않는다.** `.gitattributes`가 `outputs/**/*.jsonl`만 LFS로 잡으므로, 경로가 바뀌면 필터가 사라진다. 옮겨야 할 `.jsonl`이 있으면 **먼저 `.gitattributes`에 새 경로 패턴을 추가하고, 그 커밋을 따로 남긴 뒤** 파일을 옮긴다.
- **골든 스냅샷 경로가 `outputs/final_results/`에 하드코딩돼 있다** (`scripts/dev/golden_snapshot.py:34`). 그 디렉터리를 옮기지 않는 한 하네스는 그대로다.
- **문서를 옮기면서 내용을 고치지 않는다.** 이동과 정정은 다른 커밋이다 (Task 1 vs Task 4). 섞으면 리뷰가 "옮긴 것"과 "바뀐 것"을 구분할 수 없다.
- 판정: unit · integration · characterization 신규 실패 0, 골든 스냅샷 84개 동일, Pages 배포 경로 유효.
- 커밋 메시지·코드·문서는 영어. 대화 보고만 한국어.

## File Structure

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

### Task 1: 문서 4분할

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

### Task 2: 재생성 가능한 산출물을 `results/`로

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

### Task 3: `assets/` 정리

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

### Task 4: 세 문서가 다르게 주장하는 보상 계산을 하나로

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

### Task 5: 재구조화 마감

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

## 완료 조건

1. `docs/`가 `paper/` · `design/` · `reports/` · `history/` 넷으로 갈리고 각각 README를 갖는다. 최상위에 떠 있는 마크다운이 없다.
2. `outputs/`에 `final_results/`와 `web_arena/`만 남고, 재생성 가능한 산출물은 `results/`에 있다.
3. `results/` 아래 `.jsonl`이 있다면 `.gitattributes`가 그 경로를 LFS로 잡고 있다.
4. `figures/`가 사라지고 `assets/brand/`와 `assets/figures/`가 존재한다.
5. `README.md`와 `AGENTS.md`에 "Equal-EV" 서술이 없고, 보상 계산은 `CLAUDE.md` 한 곳에만 있다.
6. unit · integration · characterization 신규 실패 0, 골든 스냅샷 84개 동일, docker 이미지 부팅, Pages 아티팩트 경로가 `web/frontend`.
7. `docs/history/plans/2026-08-30-p0-baseline.md`에 P0–P6 전체 결과표가 있다.

## 범위 밖

- 논문 내용 수정 (`docs/paper/`는 이동만 한다)
- `outputs/final_results/` 원시 데이터의 이동·삭제 (스펙 §7이 금지)
- R2 비례검정, FDR 보정 (스펙 §8)
- 새 설계 문서 작성 — `docs/design/`은 목적지로 만들어 두는 것까지가 P6이다
