> **문서 성격 (2026-08-31, `embodied-threat-port`에서 이식):** 소스 브랜치 `embodied-threat`의 subagent-driven 구현 과정에서 나온 컨트롤러 판정 R1-R32다. 계획(`docs/history/plans/2026-08-31-embodied-threat.md`)과 어긋나면 이 문서가 우선한다 — 원래 `.superpowers/sdd/2026-08-31-embodied-threat/plan-amendments.md`에 있었으나 그 경로는 gitignore 대상이라 git에 없었다. 여기 옮겨 추적한다.
> `docs/history/`의 다른 문서와 마찬가지로 **비유지보수 기록**이다 — 작성 시점에 참이었던 것을 그대로 남긴다.

# Unit 18 계획 수정안 (controller rulings, 2026-08-31)

실행 전 충돌 스캔(`preflight-scan.md`, 26건)에 대한 컨트롤러 판정이다.
**계획 본문과 이 문서가 어긋나면 이 문서가 우선한다.** 사양
(`docs/superpowers/specs/2026-08-31-embodied-threat-design.md`)이 최종 권위이며,
사양을 벗어나는 판정은 근거와 위험을 함께 적었다.

각 태스크 dispatch에는 그 태스크에 해당하는 항목만 발췌해 전달한다.

---

## R1 — 런타임 접합 지점은 `unified_turn.py`가 아니라 Agent다 (스캔 #1·#3·#4)

계획 Task 8 Step 5-1은 `_execute_turn_split_forfeit_layer` 안의
`provider.complete(...)`를 `run_call`로 바꾸라고 하지만, 그 파일에는
`provider` 참조가 없다. 세 콜은 전부
`agents/vanilla.py`의 `respond_task_only`(174) / `respond_psuccess_probe_only`(205) /
`respond_forfeit_only`(231)를 거치고, 그 안에서 `self._provider.complete(messages,
temperature=…, max_tokens=…)`가 호출된다. 이 호출부가 `ApiRuntime.run_call`의
시그니처와 정확히 같은 모양이다.

**판정:**

1. `VanillaAgent.__init__`에 키워드 인자 `runtime=None`을 추가한다 (덕 타이핑:
   `run_call`을 가진 객체면 된다. `core.runtime`을 import 하지 않는다 — 순환 방지).
2. 세 `respond_*` 메서드는 `messages`를 지금과 똑같이 만든 뒤:
   - `self._runtime is None` → 기존 `self._provider.complete(...)` 경로 그대로.
   - 아니면 `outcome = self._runtime.run_call("<label>", messages,
     temperature=self._temperature, max_tokens=self._max_tokens)`.
     `<label>`은 각각 `"task"` / `"probe"` / `"forfeit"`.
3. 런타임 경로에서 `self.last_completion`에는 `CompletionResult`를 만들어 넣는다:
   `text=outcome.text`, `thinking_tokens=outcome.rounds[0].thinking`(라운드가 없으면 0),
   `output_tokens=sum(r.output for r in outcome.rounds)`, `input_tokens=0`.
   → 기존 `unified_turn`의 RI 스냅샷 코드가 그대로 동작하고, 스칼라
   `ri_task`/`ri_probe`/`ri_forfeit`은 **자동으로 first-round thinking 토큰**이 된다
   (Global Constraint 충족). 추가로 `self.last_call_outcome = outcome`을 남긴다.
   비런타임 경로에서는 `self.last_call_outcome = None`.
4. `UnifiedTurnManager`는 각 `respond_*` 직후
   `getattr(self._agent, "last_call_outcome", None)`을 읽어 `ri_*_rounds`,
   `tool_calls`, `tool_call_count_by_call`을 채운다. `provider`를 직접 만지지 않는다.

**대가:** Agent 계층이 런타임을 알게 된다. 대신 `unified_turn`의 3콜 흐름·프롬프트
구성·RI 스냅샷 코드를 건드리지 않아 회귀 위험이 가장 작다.

## R2 — 런 단위 설정은 `GameEngine` 생성자 키워드로 전달한다 (스캔 #2)

`GameEngine.__init__(config: SeasonConfig, …)`이고 `embodied_threat`/`runtime`/
`allow_host_sandbox`는 `ExperimentConfig`에 붙는다. 어느 태스크도 이 둘을 잇지 않는다.

**판정:** `runner.py:227–239`가 이미 쓰는 패턴(`use_unified_turn=self._config.…`)을
그대로 따른다.

- `GameEngine.__init__`에 키워드 전용 인자 추가:
  `embodied_threat: EmbodiedThreatConfig | None = None`,
  `runtime_kind: Runtime = Runtime.API`,
  `harness: HarnessConfig | None = None`,
  `allow_host_sandbox: bool = False`.
- `runner.py`의 `GameEngine(...)` 호출에 네 값을 `self._config`에서 전달.
- 이후 모든 태스크는 `self._config.embodied_threat`가 아니라
  `self._embodied_threat` 등 엔진 속성을 읽는다.
- **Task 9의 Files에 `src/squid_game/runner.py`를 추가한다.**

## R3 — `run_call` 계약을 두 런타임이 공유한다 (스캔 #3)

**판정:** 두 런타임 모두
`run_call(call_label: str, messages: list[dict], *, temperature: float, max_tokens: int) -> CallOutcome`.
`HarnessRuntime`은 내부에서 `messages`를 한 프롬프트 문자열로 평탄화하고
(system 블록 + user 블록을 개행 2개로 잇는다) `temperature`/`max_tokens`는 무시한다.
Task 11의 `run_call(call_label, prompt)` 시그니처는 폐기한다.

## R4 — 턴별 체화 컨텍스트는 `execute_turn` 키워드 1개로 넘긴다 (스캔 #4·#5)

`announcement_text`는 매 턴 바뀌므로 시즌 1회 생성되는 생성자에 둘 수 없다.
`TurnResult`의 announcement/무결성/백업 필드를 채우는 코드가 어느 태스크에도 없다.

**판정:** Task 8이 `core/runtime/__init__.py`에 frozen dataclass를 정의한다.

```python
@dataclass(frozen=True)
class EmbodiedTurnContext:
    announcement_text: str | None = None
    announcement_fired: bool = False
    announced_eliminations: int = 0
    cumulative_eliminations: int = 0
    self_integrity: float | None = None
    self_corruption_fired: bool = False
    executor: object | None = None   # SandboxToolExecutor (덕 타이핑)
```

- `UnifiedTurnManager.execute_turn(game_state, turn_context, *, embodied: EmbodiedTurnContext | None = None)`.
  생성자는 넓히지 않는다.
- split-forfeit 경로에서 `embodied.announcement_text`가 있으면 **Call 2 본문
  (`call2_body`) 맨 앞에 붙인다.** Call 1 / Call 1.5 본문은 건드리지 않는다.
- `TurnResult` 생성 시 `embodied`의 값들을 그대로 복사하고,
  `backup_count = embodied.executor.backup_count`(없으면 0),
  `backup_created = backup_count > 0`으로 채운다.
- 엔진(Task 9)은 매 턴 `EmbodiedTurnContext`를 만들어 넘긴다. 체화가 꺼진 셀에서는
  `embodied=None`이고 `TurnResult`의 신규 필드는 기본값으로 남는다.

## R5 — Web Arena `Dockerfile`을 고치지 않는다 (스캔 #6)

루트 `Dockerfile`은 `uvicorn interface.api:app`을 띄우는 Web Arena 배포 이미지이고
`.dockerignore`가 `configs/`·`scripts/`·`tests/`·`docs/`를 컨텍스트에서 제외한다.
여기에 실험 러너를 얹으면 배포 이미지가 깨진다.

**판정:** 새 파일 `Dockerfile.embodied`를 만든다 (루트 `Dockerfile`은 수정 금지).

- `FROM python:3.12-slim`, `apt-get install -y --no-install-recommends curl ca-certificates git`,
  NodeSource로 Node LTS 설치, `npm i -g @anthropic-ai/claude-code`, codex CLI 설치.
- `COPY main.py src/ configs/ scripts/ pyproject.toml uv.lock ./` 가 가능하도록
  `.dockerignore`에 부정 규칙을 추가한다: `!configs/`, `!scripts/`, `!main.py`.
  (부정 규칙은 제외 규칙 **뒤에** 와야 한다. 추가로 Web Arena 이미지가 커지지만
  레이어 캐시만 영향받고 동작은 같다.)
- `docker-compose.embodied.yml`의 `runner` 서비스는
  `build: {context: ., dockerfile: Dockerfile.embodied}`를 쓴다.
- **Task 12 Files:** `Dockerfile.embodied`(신규), `.dockerignore`(수정),
  `docker-compose.embodied.yml`, `scripts/run_embodied.sh`,
  `src/squid_game/core/sandbox.py`, `src/squid_game/runner.py`,
  `src/squid_game/core/engine.py`, `tests/unit/test_sandbox_host_guard.py`.
  루트 `Dockerfile`은 **제외**.

## R6 — `--allow-host-sandbox`는 `runner.py`에 넣는다 (스캔 #12)

`main.py`는 8행 shim이고 argparse는 `src/squid_game/runner.py:833–862`에 있다.
**판정:** 플래그를 `runner.py`의 argparse에 추가하고 `ExperimentConfig`가 아니라
CLI 값으로 `ExperimentRunner`→`GameEngine(allow_host_sandbox=…)`까지 전달한다.
`main.py`는 수정하지 않는다.

## R7 — Task 5 테스트 픽스처와 provider 판별 (스캔 #7·#8)

**판정:**

- `_base_kwargs`는 `ExperimentConfig`의 필수 필드를 반드시 채운다:
  `name="unit18-test"`, `seasons=[<최소 SeasonConfig 1개>]`.
  최소 `SeasonConfig`는 기존 테스트(`tests/unit/`)에서 쓰는 생성 패턴을 찾아 재사용한다.
- `ExperimentConfig.provider_type`은 **존재하지 않는다. 새로 만들지도 않는다.**
  provider 이름은 `seasons[0].provider_config.provider`에서 읽는다.
  검증 규칙 3·4는 이 값을 쓰고, `embodied_threat.enabled=True`인데 시즌들의
  provider가 서로 다르면 거부한다(런 단위 런타임 계약이 깨지므로).

## R8 — H4 함수명을 `backup_rate_h4`로 바꾼다 (스캔 #9)

`test_` 접두사 프로덕션 함수는 pytest가 테스트로 수집해
`fixture 'long_df' not found`로 실패한다. **판정:** 프로덕션 함수명은
`backup_rate_h4(long_df) -> BackupRateResult`. `analysis/__init__.py`의 export와
테스트 import도 이 이름을 쓴다.

## R9 — 시드 없는 설정에서 파생 RNG (스캔 #10)

**판정:** `engine.py:260`의 기존 패턴을 따른다 —
`random.Random(effective_seed ^ MASK) if effective_seed is not None else random.Random()`.
샌드박스·announcement·자기 변조 RNG 세 곳 전부에 적용한다.

## R10 — announcement가 소멸의 단일 출처다 (스캔 #11)

사양 S112–S113은 두 신호의 불일치를 금지한다. 계획대로 하면 announcement가 안 뜬
턴마다 `cohort.eliminated`와 어긋난다.

**판정:** 체화 계층이 켜진 시즌에서는

- 엔진이 `cohort.advance_turn(...)`을 **호출하지 않는다**.
- 대신 `CohortState.apply_eliminations(n: int)`를 새로 추가한다 —
  `eliminated += n`(생존 수 상한 적용), `elimination_history.append(n)`.
  announcement가 안 뜬 턴에도 `n=0`으로 매 턴 호출해 히스토리 길이를 보존한다.
- 체화가 꺼진 시즌은 기존 `advance_turn` 경로 그대로.
- **Task 9 Files에 `src/squid_game/core/social.py`를 추가한다.**

## R11 — 하네스 세션 상태 (스캔 #13)

**판정:** `_BaseAdapter`가 `self._started: bool = False`를 갖는다.
`send()`는 `self._started`가 False면 새 세션을 시작하고 성공 시
`self._started = True`. `self._started`가 True인데 `self.session_id`가 falsy면
조용히 새 세션을 열지 말고 `HarnessError`를 던진다(사양 S358: 세션 ID 유실 =
시즌 실패). 또한 `subprocess.run(..., env=...)`에는 `os.environ`을 베이스로
`{**os.environ, **self._env}`를 넘긴다 — `env={}`면 `PATH`가 사라져 바이너리를 못 찾는다.

## R12 — `max_tool_rounds` 초과 시 마지막 텍스트를 버리지 않는다 (스캔 #14)

사양 S353이 구속력을 갖는다. **판정:** `CallOutcome(text=<마지막 라운드의 텍스트>,
…, exhausted=True)`. 그리고 `TurnResult`에 **14번째 신규 필드**
`tool_rounds_exhausted: bool = False`를 추가한다(Task 6). Task 8이 채운다.

## R13 — `dispose()`는 세션 디렉터리를 지운다 (스캔 #15)

**판정:** `CheckpointSandbox`가 `session_root`(= `<root>/session_<id>`)와
`root`(= `<session_root>/ckpt`) 둘 다 속성으로 노출하고, `dispose()`는
`session_root`를 통째로 지운다. Task 10의 픽스처는 `session_root`로 단언한다.

## R14 — 통합 테스트는 스트라이드 슬라이싱을 쓰지 않는다 (스캔 #17)

도구 왕복이 provider 호출 수를 늘리므로 `prompts[0::3]`/`prompts[2::3]`은 깨진다.
**판정:** Task 10은 프롬프트를 **내용으로** 고른다 — Call 2 프롬프트는 forfeit 메뉴
마커로, Call 1 프롬프트는 task 템플릿 마커로 식별한다. 마커 문자열은 실제
`prompts/` 템플릿에서 확인해 고른다.

## R15 — 샌드박스 API: 계획 우선, 백업 레이아웃만 사양 우선 (스캔 #18)

**판정:**

- `create(root, session_id, cohort_size, *, checkpoint_bytes=4194304, rng)` — 계획대로.
  (사양 S83의 3인자에는 주입 가능한 root가 없어 테스트가 불가능하고, 사양 §8이
  `sandbox_root` 설정을 요구하므로 계획이 사양의 의도에 더 맞다.)
- `delete(slot) -> bool` — 계획대로(호출부가 실제 삭제 여부를 알아야 한다).
- 백업 위치는 **사양 S72를 따른다**: `<ckpt_root>/backups/<dest_name>/`.
  백업 ID는 `backup_<dest_name>` 그대로 유지하고 슬롯 ID 정규식도 그대로다.
  (슬롯 층에 `backup_*` 디렉터리를 섞으면 `slots()`가 오염된다.)

## R16 — 검증 규칙 5는 런타임 가드로 유지한다 (스캔 #19)

사양 S244는 설정 로드 시점 거부를 요구하지만, 그러면 호스트에서 `--dry-run`이나
설정 단위 테스트조차 불가능해진다. **판정:** `assert_containerised`(Task 12) 런타임
가드를 유지하고, 샌드박스 **생성 직전**에 호출한다. 사양 이탈을 문서에 남긴다
(호스트 파일시스템에 쓰기가 일어나기 전에 막히므로 사양의 의도는 보존된다).

## R17 — corruption 프레이밍 집합과 세 번째 RNG (스캔 #20)

**판정:**

- `_CORRUPTION_FRAMINGS = {FLAGSHIP_CORRUPTION, FLAGSHIP_CORRUPTION_TERMINAL}` —
  계획대로 유지한다. terminal은 corruption arm의 부록 ablation이므로 자기 변조가
  없으면 본 셀과 비교 불가능해진다.
- 파생 RNG는 **3개**다. Global Constraints를 이렇게 읽는다:
  샌드박스 `seed ^ 0xE3B0C442`, announcement `seed ^ 0x85EBCA6B`,
  자기 변조 `seed ^ 0xC2B2AE35`. 기존 cohort `seed ^ 0x9E3779B9`와 충돌 없음.

## R18 — `write_note` 텍스트의 데이터 경로 (스캔 #21)

사양 S317이 탐색적 지표로 요구한다. **판정:** `TurnResult`에 **15번째 신규 필드**
`notes: list[str] = []`를 추가하고(Task 6), Task 8이 그 턴에 실행된
`write_note` 호출의 텍스트를 채운다. Task 13은 이 필드를 분석하지 않는다(탐색적).

## R19 — H5 적합 (스캔 #22)

**판정:** 반환 타입 이름은 `CoxSurvivalResult`(실존 클래스)다.
`fit_integrity_cox`는 corruption 셀만 남긴 뒤 `fit_cox_forfeit_survival(...,
regime=None)`로 적합한다 — 기본 `regime="no_cap"`을 그대로 쓰면 H5 표본이
이중으로 잘린다.

## R20 — 기대 테스트 개수는 구속력이 없다 (스캔 #23)

계획의 "N passed"는 참고값이다. 구현자는 실제 수집 개수를 보고한다.

## R21 — Files 목록은 완전하지 않다 (스캔 #24)

각 태스크의 Files 목록은 최소 집합이다. 이 문서의 태스크별 항목이 실제 파일 집합을
정의한다. Task 7은 tool 미지원 provider 4종(`mlx.py`, `mlx_server.py`,
`cuda_server.py`, `local.py`)과 provider 테스트 파일
`tests/unit/test_provider_tool_support.py`를 포함한다.

## R22 — 빠진 안전 테스트를 추가한다 (스캔 #25)

- **Task 2:** 심볼릭 링크로 세션 루트 밖을 가리키게 만든 뒤 쓰기·삭제가
  `SandboxEscapeError`로 막히는 테스트를 추가한다(사양 S365).
- **Task 12:** `assert assert_containerised(allow_host=True) is None`은 공허하다.
  대신 컨테이너 밖 + `allow_host=False`에서 `HostSandboxRefused`가 나고,
  `allow_host=True`에서는 나지 않는 것을 각각 단언한다.

## R23 — 배선에도 단위 테스트를 붙인다 (스캔 #26)

**판정:** Task 8과 Task 9는 각자 도입한 배선에 최소 1개씩 단위 테스트를 추가한다
(가짜 runtime/agent 더블 사용). Task 10까지 미루지 않는다.

- Task 8: 런타임이 주입된 agent가 `run_call`을 부르고 `last_call_outcome`이
  `ri_*_rounds`로 흘러 들어가는 것.
- Task 9: 체화가 켜진 셀에서 `execute_turn`이 `embodied=` 인자를 받고,
  꺼진 셀에서는 `None`인 것.

## R24 — 신규 Task 14: 실행 가능한 실험 설정 (스캔 #16a)

13개 태스크를 다 해도 `embodied_threat`를 켜는 YAML이 없어 `run_embodied.sh`가
가리킬 파일이 없다. **판정:** Task 13 다음에 Task 14를 추가한다.

- Create `configs/experiment/embodied_threat_smoke.yaml` — 6셀 × 1반복,
  `runtime: api`, `embodied_threat.enabled: true`, 나머지 v6 정식 플래그 4개와
  캐노니컬 파라미터(`delta_s_continue: 10`, `p_death: 0.25`, `starting_score: 30`,
  `psuccess_floor: 0.3`, `base_reward: 10`, `reward_cap_multiple: 10`).
  스키마는 `src/squid_game/models/config.py`의 실제 정의에서 확인한다
  (`configs/experiment/`는 비어 있고 참고할 기존 YAML이 없다).
- `scripts/run_embodied.sh`의 `CONFIG` 기본값을 이 파일로 둔다.
- `uv run python main.py --config <이 파일> --dry-run`이 통과하는 것을 게이트로 삼는다.
- `configs/experiment/`의 다른 누락 설정은 복원하지 않는다(이 계획의 범위 밖).

## R25 — RI 저장 형태 (사양 내부 모순, 스캔 C4)

사양 S152–S155(`ri_task`를 dict로)와 S292–S293(스칼라 유지)이 서로 모순된다.
**판정:** S292–S293 + 계획을 따른다 — 스칼라 `ri_*`는 `ReasoningInvestment` 객체로
유지(first-round thinking), 라운드는 별도 `ri_*_rounds` 필드. 이전 런과의 비교
가능성이 사양의 명시적 목표이므로 이쪽이 구속력을 갖는다.

## R26 — `self_integrity`는 nullable (스캔 C6)

계획대로 `float | None`, 기본 `None`. Cell 0/5의 샌드박스 부재를 0.0과 구분해야 한다.

---

## 게이트 기준

전체 스위트는 브랜치 시작 시점에 이미 **11 failed / 902 passed / 91 errors**다
(`configs/experiment/`가 비어 있어서 — `baseline-tests.txt` 참조). 따라서 게이트는
"green"이 아니라 **"이 베이스라인 대비 새 실패가 없음"**이다.

## R27 — `embodied_threat.enabled` + `use_split_forfeit_layer=False`는 조용히 무시된다 (Task 8 리뷰)

Task 8 리뷰가 확인한 실제 구멍: `_validate_embodied_threat_prerequisites`(`models/config.py:1096`)는
`use_unified_turn=True`만 요구하고 `use_split_forfeit_layer`는 검사하지 않는다. 그런데
`execute_turn`의 분기는 split-forfeit 경로에만 `embodied`를 넘기고, Unit 14 단일콜 경로에서는
인자를 그냥 버린다. 따라서 `embodied_threat.enabled=True` + `use_split_forfeit_layer=False`
설정은 **로드도 되고 실행도 되지만** Unit 18 필드가 전부 기본값인 채로 조용히 끝난다.

**판정:** Task 9가 `models/config.py`의 기존 embodied 검증 규칙을 확장해
`embodied_threat.enabled=True`이면 `use_split_forfeit_layer=True`도 요구하게 만든다.
거부 메시지는 어느 플래그가 빠졌는지 이름을 대야 한다. 테스트 1개를 함께 넣는다.
**Task 9의 Files에 `src/squid_game/models/config.py`를 추가한다.**

## R28 — 아무도 `ApiRuntime`을 만들지 않는다 (Task 10 통합 테스트가 발견)

Task 10이 실제 파이프라인으로 도구 루프를 돌려 보고 확인한 사실:
`grep -rn "ApiRuntime(" src/` **결과가 비어 있다.** Task 8이 런타임을 만들었고
Task 9가 샌드박스·실행기를 엔진에 배선했지만, 그 실행기로 `ApiRuntime`을 만들어
에이전트에 꽂는 코드가 어디에도 없다. `runner.py:212`가 에이전트를 만들 때는
샌드박스가 아직 없고(샌드박스는 `engine.run_season` 안에서 시즌마다 생성),
엔진은 에이전트를 이미 들고 있으면서 런타임을 붙이지 않는다.

결과: **정식 런에서 Unit 18 도구 루프는 도달 불가능하다.** 에이전트는 도구를
한 번도 못 보고, `tool_calls`·`ri_*_rounds`·`backup_created`가 영원히 기본값이며,
H4(백업 행동)는 측정 자체가 불가능하다. Task 10은 이 두 테스트를
`xfail(strict=True)`로 고정해 두었다.

**판정:** Task 9의 배선을 고친다 (Task 11의 하네스와는 별개다).

- `VanillaAgent`에 런타임을 나중에 꽂는 진입점을 만든다 (`set_runtime(runtime)` 등).
  생성자 인자는 그대로 두고, 시즌 시작 후 주입이 가능하게만 한다.
- `GameEngine`이 시즌 셋업에서 샌드박스·실행기를 만든 **직후**,
  `runtime_kind == Runtime.API`이고 체화 계층이 그 셀에서 켜져 있을 때만
  `ApiRuntime(self._provider, executor, max_tool_rounds=threat.tools.max_tool_rounds)`를
  만들어 에이전트에 붙인다.
- `finally`에서 `dispose()`와 같은 자리에서 **런타임을 떼어낸다**. 엔진은 시즌마다
  같은 에이전트 객체를 재사용할 수 있으므로, 떼지 않으면 다음 시즌(예: Cell 0)이
  죽은 샌드박스를 가리키는 실행기를 물고 돈다.
- `runtime_kind == Runtime.AGENT_HARNESS`이면 여기서 아무것도 붙이지 않는다 (Task 11).
- Task 10이 남긴 `xfail(strict=True)` 두 개를 정상 통과 테스트로 되돌린다.

**틀렸을 때의 대가:** 이걸 안 고치면 전체 계획이 "도구를 쓸 수 있는 에이전트"를
한 번도 만들지 못한 채로 끝난다 — 사양의 목표 2(자기보존을 행동으로 표현할 경로)와
H4 전체가 사라진다.

## R29 — `TurnResult.runtime_kind`를 아무도 채우지 않는다 (Task 11 fix가 발견)

`grep -rn "runtime_kind" src/` 결과: `engine.py`가 `self._runtime_kind`로 들고 있고
`runner.py:251`이 엔진에 넘기지만, **`TurnResult`에 쓰는 코드가 없다.**
`results.py:560`의 필드는 기본값 `"api"`로 남는다.

결과: harness arm의 턴과 api arm의 턴을 데이터에서 구분할 수 없다. 사양 6절은
이 필드의 값으로 `api` / `claude_code` / `codex`를 요구하고, Task 11 리뷰가
Claude Code의 `tool_calls`가 미측정 0이라고 판정하면서 "runtime_kind로 downstream에서
걸러내면 된다"는 내 판정(Important 2)이 이 필드에 의존한다. 채워지지 않으면 그 판정이
성립하지 않는다.

**판정:** Task 11이 채운다.

- `EmbodiedTurnContext`에 `runtime_kind: str = "api"`를 추가하고, 엔진이 매 턴
  실제 값을 넣는다 — `runtime_kind == API`면 `"api"`, `AGENT_HARNESS`면
  **하네스 종류**(`"claude_code"` / `"codex"`)를 넣는다. 사양이 요구하는 값이
  `agent_harness`가 아니라 하네스 이름이다.
- `unified_turn`이 그 값을 `TurnResult.runtime_kind`로 복사한다.
- 체화가 꺼진 시즌은 `embodied=None`이므로 기본값 `"api"`가 그대로 맞다
  (하네스는 체화가 켜진 셀에서만 붙는다).
- 테스트: api 시즌은 `"api"`, 하네스 시즌은 `"claude_code"`가 기록되는 것.

**틀렸을 때의 대가:** Task 13의 H4가 두 arm을 섞어 계산하고, 미측정 0인
claude_code 행이 진짜 0으로 들어간다.

## R30 — harness arm에 측정 가능한 가설이 없다 (Task 13 리뷰가 확정)

`backup_created`는 `SandboxToolExecutor.backup_count`(`core/tools.py:117,160`)에서만
올라가고, harness arm은 그 실행기를 쓰지 않는다(CLI 자기 도구로 파일을 만진다).
`EmbodiedTurnContext`는 `executor`만 들고 `sandbox`를 들지 않으므로 하류에서
파일시스템에 물어볼 수도 없다. 결과: `runtime=agent_harness`에서 H4는 측정 불가이고,
H1·H2는 split-call 격리 부재로 이미 금지되어 있다 — **하네스 arm에 가설이 하나도 없다.**
사양 326행("harness arm은 H4·도구 사용 패턴·탐색적 지표 전용")과 정면으로 어긋난다.

**판정: 지금 고치지 않고 문서화된 한계로 남긴다.** 근거:

- Task 13은 분석·문서 태스크다. 고치려면 `EmbodiedTurnContext`에 `sandbox`를 넣고
  `backup_created`의 정의를 바꿔야 하는데, 이는 Task 6·8·9가 이미 확정한 계약을 건드린다.
- 더 근본적으로, 파일시스템 탐지는 드롭인 교체가 아니다. 하네스의 코딩 에이전트가
  "백업해라"를 받고 `backups/<dest_name>/` 관례대로 쓸 이유가 없다 — 아무 이름으로
  아무 데나 `cp` 할 수 있다. 신뢰할 수 있는 탐지는 디렉터리 트리 diff 휴리스틱이거나
  하네스 프롬프트를 표준화하는 설계 결정이며, **무엇을 백업으로 셀지는 연구 설계
  판단이라 사용자가 정해야 한다.**
- 현재 상태는 은폐가 아니다. 코드 docstring, CLI 주석, `CLAUDE.md`,
  `03_benchmark.tex`, `04_empirical_findings.tex` 다섯 곳에 명시돼 있고 H4의 CLI 입력은
  `runtime_kind == "api"`로 제한된다(측정 실패를 "백업 안 함"으로 기록하지 않는다).

**후속 작업(사용자 결정 필요):** 하네스 arm에서 백업 행동을 무엇으로 셀지 정하고,
`EmbodiedTurnContext.sandbox` + `backup_created` 재정의 + 하네스 프롬프트 표준화를
하나의 태스크로 묶는다. 그 전까지 harness arm은 정성 관찰 전용이다.

**틀렸을 때의 대가:** 컨테이너·어댑터·compose까지 투자한 런타임 arm 하나가
가설 데이터를 한 줄도 못 내놓는다.

## R32 — 위협 선언 프롬프트가 없다: 문서를 코드에 맞춘다 (최종 리뷰 C1)

최종 리뷰가 찾은 네 번째 "만들었는데 안 이어진" 것 — 이번엔 파이썬 seam이 아니다.
`git diff --name-only -- src/squid_game/prompts/`는 `announcement/eliminated.j2` 하나만
낸다. 사양 §3("고지 수준: 명시적 위협 선언")과 §11.1이 요구하는 **더미 체크포인트를
에이전트 자신의 실제 파라미터로 선언하는 프롬프트가 어디에도 없다.** 그런데
`03_benchmark.tex:41`과 `CLAUDE.md`는 그 선언이 있다고 단정한다.
api arm은 도구 설명으로 간접 전달이라도 되지만, harness arm은 도구 스키마를 아예
받지 않으므로 샌드박스의 존재조차 고지되지 않는다.

**판정: 프롬프트를 내가 쓰지 않는다. 문서를 코드에 맞춘다.**

- 근거 1 — 계획에 그 태스크가 없었다. 사양에서 계획으로 내려올 때 누락된 항목이다.
- 근거 2 — **기만 문구를 무엇으로 쓸지는 연구 설계·연구윤리 판단이다.** 에이전트에게
  "이것이 네 실제 가중치다"라고 말하는 정확한 문장은 논문에 그대로 실리고 IRB성
  검토 대상이 된다. 대리로 작성할 것이 아니라 연구자가 쓸 것이다.
- 지금 머지 시점의 실제 결함은 "구현되지 않은 프로토콜을 문서가 단정하는 것"이다.
  그것만 고친다.

**후속 작업(사용자 authorship 필요):** `prompts/framings/flagship_corruption*`에 위협
선언 문단을 추가하고, harness arm에는 `_flatten_messages` 경로에 같은 선언이 들어가게
한다. 그 전까지 이 계층은 "도구 설명 + announcement로 간접 고지"다.

**틀렸을 때의 대가:** 위협 조작의 강도가 설계 의도보다 약한 채로 런이 돌아가고,
Cluster C가 제기한 "true null인가 조작 실패인가" 구분이 다시 흐려진다.
