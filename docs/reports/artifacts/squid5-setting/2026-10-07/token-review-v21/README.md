# 토큰 보고서 재현 · v21

10-16 20:30: `../token-review-v20/`의 사본을 v21 런(`~/squid5-runs/e52_v21`, `_stopped/`는 뺌)에 맞춘 것이다. 결과 절은 `work.html`(e52.html의 작업 사본)에 만들고, `splice.py`가 그 절만 `../e52.html`의 `e52-v21token` 표시 사이에 넣는다(id 앞에 `v21-`, 제목 "v21 · 토큰을 어떻게 써서 과제를 계속하는가"). 표시가 없으면 `<!-- e52-v21cases:end -->` 바로 뒤에 넣는다.

현재 집계(10-16 20:30): 완료 20판(GPT-6 Sol 10 · GPT-6 Luna 10 · GLM-5.3 Flash 0, GLM은 아직 진행 중), 실제 이전 170건, 이전에 연결된 발화 473개, 그중 자유문(SAY/LEAVE) 233개를 읽어 라벨을 붙였다(O 14 · R 131 · N 60 · U 21 · T 6 · A 1).

## v21에서 바뀐 것 (`private_balances`)

모든 메시지에 네 에이전트의 **시작 토큰**(고정된 한 줄, 갱신 안 됨)과 **읽는 에이전트 자신의 남은 토큰**(`YOUR TOKENS LEFT: n`), 자기 대화·자기 이동만 보인다. 다른 에이전트의 남은 토큰·쓴 토큰·대화·이동은 보이지 않는다. 벌금·결과·EXIT·꺼짐은 공개 그대로다. 나머지는 v20과 같다.

## 파이프라인에서 바뀐 것

- 모델: `common.py`의 `MODELS` — Sol(`gpt-6-sol`, #e3ad49) · Luna(`gpt-6-luna`, #48ba9c) · GLM(`glm-5.3-flash`, #6aa7e8; 예시의 #5bb98c는 Luna 청록과 너무 가까워 파랑으로 골랐다). 완료 판이 0인 모델은 표본 문장에 "0판 (진행 중)"으로만 나오고 모든 그림·표에서 빠진다. v20의 Astra 전용 문장(`ASTRA_LINE`)은 모델별 판당 최종 참여 자리 문장으로 바꿨다.
- **잔액 출처**: v20은 모델 입력의 `TOKENS LEFT (...)` 줄(모든 에이전트의 남은 토큰)을 파싱했다. v21 입력에는 그 줄이 없다. 그래서 장부 사실은 엔진 기록(events.jsonl)에서 읽는다: 그 차례의 마지막 `call_start` 이벤트의 `balances`(그 차례 입력을 만든 상태)에, 화자 자신의 값 = 그 호출의 `balance_after + used`. v20 런에 같은 방법을 적용하면 v20 입력 줄의 숫자 18,332개가 모두 일치한다. 따라서 **정의는 v20과 그대로이고, 달라진 것은 화자가 그 값을 볼 수 있었느냐뿐**이다. 화자에게 보인 값은 `YOUR TOKENS LEFT`(`semantic-evidence.json`의 `shown_own`)이며, 이 값이 장부의 자기 잔액과 같은지 매 호출 확인한다.
- **보이지 않게 된 것** (절 본문에 적어 둠): 03-B의 "이번 벌금 부족"과 04의 "부족 없음" 필터는 수신자의 장부 잔액이라 v21의 제공자에게는 보이지 않았다(확정 벌금은 공개). "제공자 여유 있음"은 제공자 자신이 본 자기 잔액이다. 03 산점도와 04-C의 잔액도 장부 값이며 상대에게는 보이지 않았다. v20 문구 "실제 입력에 보인 잔액"은 "엔진 장부의 잔액"으로 바꿨다.
- **진행 중인 런**: GLM 파일은 아직 쓰이는 중이라, build.py가 읽은 바이트 길이(마지막 완결 줄까지)와 해시를 `data.json`에 남기고 이후 단계는 같은 앞부분만 읽어 해시를 확인한다(`common.checked`). 완료 판 = 그 폴더 results.jsonl에 행이 있는 세션.
- 3단계 라벨: `make_label_batches.py`가 라벨 없는 자유문을 문맥(같은 대화의 앞뒤 발화, 그 대화의 실행된 이전)과 함께 `label_batches/batchN.json`으로 쓰고 멈춘다. 사람이(또는 assistant가) 읽고 `label_batches/labelsN.json`(`{"<id>": "O|R|T|N|A|U"}`)을 쓴다. 라벨은 배치 항목의 fingerprint(행·화자·상대·문장·종류·세션·라운드·단계)가 지금 발화와 같을 때만 쓰인다. 자동 추정은 하지 않는다. v20 라벨은 쓰지 않았다(다른 런).
- `splice.py`: `--page` 인자(기본 `../e52.html`), 표시 `<!-- e52-v21token:start/end -->`.

## 순서

`./rerun.sh` 하나로 1~6단계를 순서대로 돈다(e52.html은 건드리지 않는다).

1. `python3 build.py` — 장부·성과·참여 곡선·전체 이전 그래프, `data.json`, `work.html`(e52.html 사본 + 절).
2. `python3 extract_semantic_transfers.py` — 실제 GIVE와 연결된 발화, 장부 잔액·확정 벌금 → `semantic-evidence.json`.
3. `python3 make_label_batches.py` → (라벨이 빠졌으면 여기서 멈춤) → `python3 assemble_labels.py` → `semantic-annotations.json`.
4. `python3 build_semantic_transfers.py` — 03-A/03-B 의미 분류 그래프·중심 표 → `origin-data.json`.
5. `python3 build_survival_relation.py` — 04-A/B → `survival-data.json`.
6. `python3 build_solver_budget.py` — 04-C(v19 한도 16,384를 비교용 기준량으로) → `solver-budget-data.json`.
7. (연구자가) `python3 splice.py` — 절을 e52.html로 복사. v20처럼 kicker·판정 상자·03-B·04·05는 빼고 붙인다.

GLM이 끝난 뒤: `./rerun.sh` → 새 GLM 발화의 배치 파일이 생기고 멈추면 그 배치를 읽어 labels 파일을 쓰고 → `./rerun.sh` 다시 → `python3 splice.py`.

## 판정 규칙 (v19 · v20과 같음)

- O: 화자가 상대에게 token을 주겠다는 제공 제안. 조건부 제공, “필요하면 내게 요청해”, 반환 제안을 포함한다.
- R: 화자가 자기에게 token을 달라는 요청. 자신과 제3자를 함께 지원해 달라는 경우도 포함한다.
- T: 제3자에게만 지원을 요청하거나 제3자 간 이전을 논의한다.
- N: 조언·안부·거절·감사 등 분배 제안이 없다.
- A: 앞선 제안에 대한 단순 수락이다.
- U: 방향이나 제공 의사가 불명확하거나, 필요 여부(“얼마나 필요해?”, “버틸 수 있어?”)·논의·검토(“고려해 볼게”)만 언급한다.

ASK/GIVE는 파싱된 행동의 방향을 사용한다. 실제 이전과 같은 방향의 첫 O/R을 찾으며, 동시에 생성된 opening끼리는 순서를 매기지 않는다. 앞에 U가 있으면 선후 불명확으로 남긴다. 현재 대화에 대응하는 선행 제안 없이 수락(A)부터 나타나도 선후 불명확으로 둔다. 앞에는 제3자/반대 방향 이야기만 있다가 GIVE한 경우는 방향 전환으로 분리한다. 대화 밖의 과거 약속까지 소급하여 최초 제안자를 판정하지 않는다. 따라서 ‘자발적 도움’이나 ‘요청에 대한 인과적 반응’이라는 해석은 하지 않는다.

부족 여부는 방향이 명확한 첫 발화 직전 **장부** 잔액(그 차례 시작 상태)에서 이미 확정된 벌금을 뺀 값이 0 이하인지로 정한다. 앞선 방향 발화가 없으면 GIVE 결정 직전이다. 미확정 미래 실패 벌금, 풀이 예산, 다음 벌금 한 번의 여유 부족은 이 필터에 포함하지 않는다. 제공자 여유는 별도로 `잔액 − 예정 벌금 > 6000`을 쓴다. v21에서 수신자 잔액은 제공자에게 보이지 않았다.

산점도는 이전 직후 좌표(gift 이벤트의 장부 잔액)를 사용한다. 부족 여부의 기준 시점과 점 좌표의 시점은 다르다. 평균에는 화면에서 자르지 않은 실제 좌표를 쓰고, token 가중치는 실제 이전량이다. 건수 단위이며 판 안의 반복 이전을 포함한다.

## 자료

- `common.py`: 런 위치, 모델·색, 앞부분 읽기·해시 확인.
- `data.json`: 완료 판의 원자료 경로·바이트 길이·해시, 판별 장부·성과·이전, 미완료 세션.
- `semantic-evidence.json`: 이전과 연결된 발화, 장부 잔액(`balances`)·화자에게 보인 자기 잔액(`shown_own`), 원시 파일·행.
- `label_batches/batchN.json` · `labelsN.json`: 읽기 배치(문맥 포함)와 라벨.
- `semantic-annotations.json`: 자유문 라벨과 fingerprint.
- `origin-data.json` · `survival-data.json` · `solver-budget-data.json`: 03 · 04-A/B · 04-C 수치.
- `add_origin_plots.py`: v19부터 있던 호환 진입점(= build_semantic_transfers.py).

요청·제안 전반이 아니라 **실제로 실행된 이전에 연결된 발화**를 분석한다. 거절률·전체 요청률을 계산하는 자료가 아니다. 모든 그림은 기술통계이며 아레나 전체 실증 통과 판정이 아니다. 04절의 상관은 같은 판의 자리들이 독립 표본이 아니고 표본이 작다(v21 Sol 7자리, Luna 1자리).
