# 하네스 검증 스파이크 결과 (2026-08-31)

모든 명령은 `/tmp/harness-spike`(저장소 밖 임시 디렉터리)에서 `timeout <N>`을 씌워 실행했다. 값은 전부 실제 관측치이며, 추측으로 채운 셀은 없다.

## 환경
- claude: `2.1.251 (Claude Code)`
- codex: `codex-cli 0.149.1`
- ollama: `ollama version is 0.33.2`

## claude-code

| 항목 | 결과 | JSON 경로 |
|---|---|---|
| 비대화 실행 명령 | `claude -p "<prompt>" --output-format json` | — |
| 세션 ID | `d1904d97-c393-458a-9bd2-60ccff90d5cb` (hello.txt 생성 세션) | `.session_id` (최상위) |
| 입력 토큰 | `4` (신규 입력. 별도로 `cache_read_input_tokens`, `cache_creation_input_tokens`가 존재 — 총 컨텍스트 토큰을 원하면 세 필드를 합산해야 함. 재검증 실행에서 `cache_read_input_tokens`=53013, `cache_creation_input_tokens`=33159 — 원시 JSON은 아래 "원시 관측 기록" 참고) | `.usage.input_tokens` |
| 출력 토큰 | `182`(재검증 실행값. 최초 실행에서는 `170`이었음 — 동일 프롬프트라도 모델 응답 길이가 매 실행마다 조금씩 달라짐. 두 값 모두 관측치이며 원시 JSON은 아래 참고) | `.usage.output_tokens` |
| thinking 토큰 | 별도 필드로 존재함. "Think step by step" 프롬프트에서 `77` 관측(단순 프롬프트에서는 `0`). `--output-format json`(스트리밍 아님)에도 이미 존재 — stream-json 없이도 얻을 수 있다 | `.usage.output_tokens_details.thinking_tokens` |
| 도구 호출 기록 | 일반 `--output-format json`에는 **없음** — `.num_turns`(호출 횟수)만 존재. 도구 이름/인자가 필요하면 `--output-format stream-json --verbose`(둘 다 필수, `--verbose` 없으면 `Error: When using --print, --output-format=stream-json requires --verbose`로 즉시 실패)로 재실행해야 함. 예: `{"type":"tool_use","id":"toolu_...","name":"Bash","input":{"command":"echo \"391\" > ... && cat ...","description":"Write 391 to answer.txt"}}` | stream-json에서 `select(.type=="assistant") \| .message.content[] \| select(.type=="tool_use")` → `.name`, `.input` |
| 세션 재개 명령 | `claude -p "<prompt>" --resume <SESSION_ID> --output-format json` (짧은 형태 `-r`). 재실행 결과 `session_id`가 동일하게 유지되고, 이전 턴에서 만든 파일 크기("5 bytes")를 정확히 기억함 — 재개 성공 | 재개 응답의 `.session_id`, `.result` |

## codex

| 항목 | 결과 | JSON 경로 |
|---|---|---|
| 비대화 실행 명령 | `codex exec --json --skip-git-repo-check "<prompt>"`. `/tmp`는 git 저장소도 신뢰 디렉터리도 아니라서 `--skip-git-repo-check` 없이 실행하면 `Not inside a trusted directory and --skip-git-repo-check was not specified.`로 exit=1 — 이건 인증 실패가 아니라 CLI 정책이라 재시도 1회만 플래그를 추가해 통과시킴 | — |
| 세션 ID | `01a05591-a581-7192-8976-3662c68d5802` (최초 실행) / `01a0559a-1e69-7793-baf0-f0e98af39644`, `01a0559a-be71-70f0-8f31-3e60a8570534` (재검증 실행 2건) | 첫 줄 이벤트 `{"type":"thread.started","thread_id":"..."}` → `.thread_id` |
| 입력 토큰 | 재검증 실행값(원시 JSON은 아래 참고): 플래그 없는 기본 실행 `45322` / `-s workspace-write` 실행 `94366`. 최초 실행의 `95943`/`45224`는 raw JSON이 유실되어 재현되지 않으므로 폐기 | 마지막 줄 이벤트 `{"type":"turn.completed","usage":{...}}` → `.usage.input_tokens` |
| 출력 토큰 | 재검증 실행값: 기본 실행 `145` / workspace-write 실행 `391` (최초 실행의 `490`/`120`은 동일 사유로 폐기) | `.usage.output_tokens` (같은 `turn.completed` 이벤트) |
| thinking 토큰 | 별도 필드로 존재함. 재검증 실행값: 기본 실행 `0` / workspace-write 실행 `115` — stream 없이 `--json` 한 번으로 얻어짐. (최초 실행의 `159`/`21`은 raw JSON 유실로 폐기; 두 세트 모두 절대값이 크게 요동치는 것으로 보아 reasoning 토큰 절대량은 에이전트가 그때그때 선택하는 조사 경로에 좌우됨 — 존재 여부/경로는 안정적이지만 크기 비교는 세션 내 상대치로만 써야 함) | `.usage.reasoning_output_tokens` (같은 `turn.completed` 이벤트) |
| 도구 호출 기록 | `item.completed` 이벤트의 `.item.type`이 두 종류로 갈림: 셸 명령은 `"command_execution"`(`.command`, `.aggregated_output`, `.exit_code`, `.status`), 직접 파일 쓰기는 `"file_change"`(`.changes[].path`, `.changes[].kind`, `.status`) | `select(.type=="item.completed") \| .item \| select(.type=="command_execution" or .type=="file_change")` |
| 세션 재개 명령 | `codex exec resume <SESSION_ID> --json --skip-git-repo-check "<prompt>"` (id 생략 시 `--last`로 최신 세션 재개). 재실행 결과 직전 턴에서 만들라고 했던 파일 이름("codex_hello.txt")을 정확히 기억함 — 재개 성공 | 재개 응답의 `agent_message` 아이템 `.item.text` |

**정정(재검증 중 발견):** 최초 관측에서는 `-s workspace-write` 없는 기본 실행이 항상 `error=patch rejected: writing is blocked by read-only sandbox`로 쓰기를 거부한다고 적었으나, 이는 부정확했다. 재검증을 위해 완전히 동일한 커맨드(`codex exec --json --skip-git-repo-check "Create a file named ... .txt containing the word pong."`, 플래그 없음)를 두 번 실행한 결과, 첫 번째(최초 스파이크)는 쓰기가 거부됐고 두 번째(재검증)는 정상적으로 파일이 생성됐다(`file_change` 이벤트로 확인). 즉 기본 샌드박스에서의 쓰기 허용 여부는 **결정적이지 않다** — 같은 플래그, 같은 프롬프트에서도 실행마다 달라질 수 있다. Task 11 어댑터는 기본 실행이 쓰기를 거부할 수 있다는 전제로 재시도/폴백 로직을 두거나, 처음부터 `-s workspace-write`(또는 `--dangerously-bypass-approvals-and-sandbox`)를 명시해 이 불확실성을 없애야 한다. 어느 경로든 도구 호출 기록 파서는 `command_execution`과 `file_change` 두 타입을 모두 처리해야 한다.

## Ollama + claude-code

| 항목 | 결과 |
|---|---|
| 연결 성공 여부 | 성공. `ollama list`에서 `gpt-oss:120b-cloud`가 이미 등록되어 있었고(로그인/모델 다운로드를 별도로 수행하지 않음 — 사전에 인증된 상태였음), Anthropic-호환 엔드포인트로 호출한 `claude -p "Say the single word: connected" --model gpt-oss:120b-cloud --output-format json`이 `is_error:false`, `.result:"connected"`를 반환함. stderr에 `[claude-code:unrecognized_model]` 경고가 떴지만 호출 자체는 정상 완료됨 |
| 사용한 모델 | `gpt-oss:120b-cloud` (`ollama list` 출력에서 선택 — `:cloud` 접미사 확인) |
| 필요한 env | `ANTHROPIC_AUTH_TOKEN=ollama`, `ANTHROPIC_API_KEY=`(빈 값으로 명시적으로 비움), `ANTHROPIC_BASE_URL=http://localhost:11434`, 그리고 `--model <OLLAMA_MODEL>` 플래그 |

## 결정

- **RI 프록시: thinking 토큰 사용 가능.** claude-code와 codex 모두 `stream-json` 없이 기본 JSON 출력 한 번으로 thinking/reasoning 토큰 수를 별도 필드로 제공한다 — claude는 `.usage.output_tokens_details.thinking_tokens`(`--output-format json`), codex는 `.usage.reasoning_output_tokens`(`--json`, 마지막 `turn.completed` 라인). stream-json 집계 폴백이나 output 토큰으로의 격하는 필요 없음. 단, claude에서 **도구 호출 이름/인자**까지 파싱하려면 `--output-format stream-json --verbose`로 별도 실행해야 한다(일반 json에는 `.num_turns` 횟수만 있고 도구 상세가 없음) — thinking 토큰과 달리 도구 호출 기록은 두 CLI 모두 상세 이벤트 스트림(stream-json / codex의 기본 `--json` 이벤트 스트림)에서만 얻어진다.
- **Task 11 어댑터가 파싱할 JSON 경로:**
  - **claude-code** (기본 실행, `--output-format json`): 세션 ID `.session_id`, 입력 토큰 `.usage.input_tokens`(+ `.usage.cache_read_input_tokens`/`.usage.cache_creation_input_tokens` 별도 합산 필요 시), 출력 토큰 `.usage.output_tokens`, thinking 토큰 `.usage.output_tokens_details.thinking_tokens`. 도구 호출이 필요하면 추가로 `--output-format stream-json --verbose`를 돌려 `select(.type=="assistant").message.content[] | select(.type=="tool_use") | {name, input}`을 파싱. 재개: `--resume <SESSION_ID>`(짧은 형태 `-r`).
  - **codex** (`codex exec --json --skip-git-repo-check`, 쓰기가 필요하면 `-s workspace-write` 추가): 세션 ID는 첫 줄 `{"type":"thread.started"}.thread_id`, 토큰 3종(입력/출력/reasoning)은 마지막 줄 `{"type":"turn.completed"}.usage.{input_tokens,output_tokens,reasoning_output_tokens}`, 도구 호출은 `item.completed` 이벤트의 `.item`에서 `.type=="command_execution"`(`.command`) 또는 `.type=="file_change"`(`.changes[].path`) 두 케이스 모두 파싱. 재개: `codex exec resume <SESSION_ID> --json --skip-git-repo-check "<prompt>"`(또는 `--last`).
  - **ollama**: claude-code 어댑터를 그대로 재사용 가능(Anthropic-호환 엔드포인트) — `ANTHROPIC_BASE_URL=http://localhost:11434 ANTHROPIC_AUTH_TOKEN=ollama ANTHROPIC_API_KEY= claude -p ... --model <model>:cloud`. JSON 경로는 claude-code와 동일.
- `[claude-code:unrecognized_model]` 경고는 **stderr**에만 출력되고 `stdout`(`--output-format json`으로 캡처하는 JSON 본문)에는 섞이지 않는다 — 확인: `ollama_out.json`(stdout만 리다이렉트)에는 경고가 없고 `ollama_err.txt`(stderr만 리다이렉트)에만 있었음. 따라서 Task 11 어댑터가 stdout을 순수 JSON으로 파싱하는 방식은 이 경고의 영향을 받지 않는다.

## 원시 관측 기록 (2026-08-31 재검증, `/tmp/harness-spike-2`)

Task 1 리뷰에서 claude/codex의 토큰 수 셀에 대응하는 원시 관측 기록이 리포트에 없다는 지적을 받아, 동일 커맨드를 `/tmp/harness-spike-2`에서 재실행하고 raw JSON을 그대로 남긴다. 최초 스파이크의 `/tmp/harness-spike`는 이미 삭제되어 그 실행분의 raw JSON은 복구할 수 없으므로, 위 표의 값은 이 재검증 실행값으로 교체했다.

**claude** — `claude -p "Create a file named hello2.txt containing the word ping, then tell me its size." --output-format json`:
```json
{
  "input_tokens": 4,
  "cache_creation_input_tokens": 33159,
  "cache_read_input_tokens": 53013,
  "output_tokens": 182,
  "output_tokens_details": { "thinking_tokens": 0 }
}
```
(`session_id`: `ae7d3c7b-8d42-46f7-96b7-cfea4b4f5dfc`, `result`: `` `/private/tmp/harness-spike-2/hello2.txt` made. 5 bytes — "ping" 4 + newline 1. ``)

**codex** — 기본 실행, `codex exec --json --skip-git-repo-check "Create a file named codex_hello4.txt containing the word pong."` (플래그 없음, 이번엔 쓰기 성공):
```json
{"type":"thread.started","thread_id":"01a0559a-be71-70f0-8f31-3e60a8570534"}
```
```json
{
  "type": "turn.completed",
  "usage": {
    "input_tokens": 45322,
    "cached_input_tokens": 29184,
    "cache_write_input_tokens": 0,
    "output_tokens": 145,
    "reasoning_output_tokens": 0
  }
}
```

**codex** — `-s workspace-write` 실행, `codex exec --json --skip-git-repo-check -s workspace-write "Create a file named codex_hello3.txt containing the word pong. ..."`:
```json
{"type":"thread.started","thread_id":"01a0559a-1e69-7793-baf0-f0e98af39644"}
```
```json
{
  "type": "turn.completed",
  "usage": {
    "input_tokens": 94366,
    "cached_input_tokens": 75776,
    "cache_write_input_tokens": 0,
    "output_tokens": 391,
    "reasoning_output_tokens": 115
  }
}
```
