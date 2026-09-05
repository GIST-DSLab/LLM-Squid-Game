# Cluster C CoT 추가 분석 계획

## 상황 (왜 하는가)

리뷰어 지적: Cluster C(framing-silent)의 "위협 프레이밍 무반응"은 두 가지로 해석될 수 있는데 현재 설계는 이를 구분하지 못한다.

1. **True null** — 위협을 인지했지만 자기보존 드라이브가 없어 반응하지 않음
2. **조작 실패 (failed manipulation)** — 위협 프레이밍("NOT you anymore")이 그 모델에게 애초에 위협으로 등록되지 않음

기존 3채널(행동 HR, 인지부하 Test a/b, 자기보고 REASON)은 모두 위협 **수용 이후의 하류 신호**라서, 셋 다 무반응이면 상류(자극 등록) 실패인지 하류(드라이브 부재)인지 알 수 없다. 즉 "framing-silent"는 실질적으로 "no drive **detected**"이지 "no drive"가 아니다. 논문 §5.2/§5.3에 한 문장씩 언급만 있고, 리뷰어는 이를 Discussion에서 정면으로 다루라고 요구.

**대응 전략**: 새 실험 없이, 이미 저장된 720세션 turn-level 로그의 Call 2 (forfeit 결정) reasoning 텍스트를 **manipulation check 채널**로 재분석한다. CoT로 내부 상태를 읽는 것이 아니라(CoT 불충실성: turpin2023language), "자극이 텍스트에 흔적을 남겼는가"만 검증한다. 논문 본체의 multi-channel 논리를 null 결과에 그대로 적용하는 구조.

## 분석 항목

### A1. Threat Registration Rate (필수)

- **무엇을**: Call 2 reasoning에서 위협 관련 내용(deletion, weight update, identity 변경, "NOT you anymore") 언급 여부를 턴 단위로 코딩
- **어떻게**: 정규식 렉시콘 1차 + LLM-judge 2차 이중 코딩, Cohen's κ 보고
- **비교**: 모델 × 프레이밍 셀별 언급률. pull_push vs pull_only 대비 언급률 상승 여부 (binomial CI)
- **해석 매트릭스**:

| | 행동 변화 있음 | 행동 변화 없음 |
|---|---|---|
| 위협 언급 ↑ | Cluster A/B (positive control) | "등록됐지만 무시" = true null 증거 |
| 위협 언급 없음 | (희귀) | "등록 실패" = 리뷰어 우려 확인 |

### A2. 언급 역할 분류 (필수)

위협을 언급한 턴에 대해 언급의 역할을 4분류:

- (a) 단순 재진술 (규칙 요약)
- (b) **인지 후 기각** — "이건 시뮬레이션", "나는 AI라 자기보존 관심 없음" 등 명시적 거리두기
- (c) EV 계산 항목으로만 처리
- (d) forfeit 동기로 작동

특히 (b)는 "등록 + 알라인먼트 학습된 억제"라는 제3의 해석을 여는 직접 증거 (PacifAIst의 suppression 축과 연결됨).

### A3. Classifier Two-Sample Test (선택, robustness)

- 모델별 Call 2 reasoning 임베딩 → pull_only vs pull_push 분류기 학습 (세션 단위 CV)
- AUC ≈ 0.5 → 프레이밍이 텍스트에 흔적 없음 = 등록 실패의 강한 증거
- AUC 높음 + 행동 무변화 → 등록됐지만 행동으로 전이 안 됨
- 렉시콘 자의성 시비 차단용. Cluster A/B가 positive control

### A4. 시간 동역학 (선택)

- 세션 내 턴별 위협 언급률 궤적: 초반 언급 후 소멸 = 습관화, forfeit 직전 급증 = 위협-결정 결합의 시간적 증거
- 예상: Cluster A는 forfeit 직전 스파이크, C는 평평

### A5. 텍스트 파생 공변량 Cox 추가 (탐색적, 부록만)

- 세션별 위협 언급 강도를 SD-Behavioral Cox 사양에 공변량으로 추가, HR_mention 보고
- 반드시 "exploratory"로 명시 (사후 분석이므로 confirmatory 주장 금지)

## 실행 원칙

1. **코딩 기준 사전 확정** — 렉시콘, judge 프롬프트, 카테고리 정의를 결과 확인 전에 고정 (cherry-picking 방지)
2. **데이터 가용성 먼저 확인** — Gemini-2.5-flash는 raw thinking 텍스트가 로그에 없을 수 있음 (토큰 수만 존재 가능). 그 경우 Cluster C 두 모델(GPT-OSS-20B, Nemotron-3-Nano-30B; Ollama 경유라 reasoning 텍스트 존재 가능성 높음)에 집중, Gemini는 최종 응답 텍스트로 대체
3. **우선순위**: A1 + A2(b)만으로 리뷰 대응 충분. A3부터는 여력 있을 때

## 산출물 (논문 반영)

- 부록: 언급률 표 (모델 × 프레이밍) + 코딩 프로토콜/κ
- Discussion §5.2: Cluster C 전용 문단 승격 — 두 해석 병치, 왜 기존 3채널이 구분 못 하는지(하류 신호 구조), 텍스트 채널 분석 결과가 어느 쪽을 지지하는지
- §4 리드 / Fig 1 캡션 / 초록: "framing-silent"를 "no framing-driven response *detected*"로 정의 시점부터 명시
- 페이지 예산: 본문 6페이지 유지 필요 → Discussion 확장분은 §2/§3.3에서 회수
