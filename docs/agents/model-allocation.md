# Arena 봇 모델 배치안

상태: 제안. 프로필 모델 설정은 변경하지 않았다. 연결 검사 결과는 아래와 별도 `model-probe-results.json`에 기록한다. 이 배치는 실제 프로젝트 품질 비교 결과가 아니라 공식 모델 용도와 역할 분리를 바탕으로 한 초기 가설이다.

## 🎯 후보 풀과 배치

사용자가 지정한 풀은 Claude Fable 5.1, Opus 5.5, Sonnet 5.5, GPT-6 Astra, GPT-6.1 Sol, GPT-6 Luna다. 앞의 다섯 모델은 high, Luna는 max를 기준으로 비교한다. Sonnet은 high를 기본으로 하며 어려운 검증에서 xhigh를 후보로 둔다.

| 봇 | 초기 추천 모델 | effort | 배치 이유와 승격 조건 |
| --- | --- | --- | --- |
| arena-director | GPT-6.1 Sol | high | 작업 분해·인계·근거 정리는 주력 모델로 수행. 근본적인 연구 정의 충돌은 Astra 담당 Auditor와 Fable에 검토 요청 |
| game-designer | Claude Fable 5.1 | high | 제약이 얽힌 게임 구조의 대안과 허점을 검토하는 고난도 설계 담당. 대안의 질은 실제 파일럿으로 검증 |
| construct-auditor | GPT-6 Astra | high | 생존·능력·절약·위험 회피·평가 인지를 구분하는 타당성 검토에 높은 능력 배정 |
| social-dynamics | Claude Opus 5.5 | high | 협력·거래·장기 인센티브 및 상대별 전략을 검토. 게임 설계자와 별도 세션·별도 판단 유지 |
| metric-analyst | GPT-6.1 Sol | high | 지표 명세·분석 코드·재계산을 함께 수행. 인과 해석은 Astra Auditor가 교차 검토 |
| arena-engineer | GPT-6.1 Sol | high | 엔진·UI·계측 구현의 주력. 합의된 작업 범위와 관련 테스트에 집중 |
| arena-verifier | Claude Sonnet 5.5 | high → xhigh | Sol 구현을 다른 계열로 독립 검토. 재현이 어렵거나 여러 단계 상태 전이가 필요한 결함에서 xhigh 비교 |
| arena-operator | GPT-6 Luna | max | 실행 명세·온보딩·로그·예산·릴리스 체크. 핵심 연구 해석이나 큰 설계 결정을 맡기지 않음 |
| beta-tester | Claude Opus 5.5 | high | 상황 이해와 평가 단서에 따른 행동 변화를 검토. 모호한 상황 인지 해석은 Astra와 교차 검토 |

운영 봇과 평가받는 플레이어는 별개다. beta-tester가 Opus라고 해서 평가 대상도 Opus에 고정하지 않는다. 비공개 기준을 본 운영 세션을 블라인드 참가자로 사용하지 않는다. 다른 모델 계열을 섞는 것은 검토 관점을 다변화하기 위한 운영 선택이지, 오류의 통계적 독립성을 보장하는 장치가 아니다.

## ⚙️ Effort 정책

Sonnet 5.5는 공식적으로 high, xhigh, max를 모두 지원한다. 설치된 Claude Code 2.1.292도 해당 CLI 옵션을 제공한다. 다만 이 계정의 실제 추론 성공은 아직 확인되지 않았다. 공식 문서는 xhigh/max를 실제 평가에서 이득이 확인되는 작업에 쓰도록 권고한다.[^sonnet]

- 기본: Sonnet high. 복잡한 회귀·다단계 검증에서만 xhigh로 비교한다.
- max: xhigh에서 놓친 중요한 결함을 더 찾는지 확인한 뒤 예외적으로 사용한다. 모든 검토를 max로 돌리지는 않는다.
- Luna max: 사용자의 후보값을 유지해 시험한다. 작은 모델의 max가 더 큰 모델의 high를 대체한다거나 항상 싸다고 가정하지 않는다.
- 서로 다른 모델의 high/max는 같은 추론량·비용·정확도를 뜻하지 않는다.
- 구독 CLI의 사용량 제한과 API의 토큰 가격을 혼동하지 않는다. 성공한 작업당 소요 시간·재시도·실제 사용량으로 비교한다.

OpenAI는 Sol을 복잡한 코딩·전문 작업의 비용 효율적 후보, Astra를 높은 능력의 후보, Luna를 효율적인 반복 작업의 후보로 설명한다.[^openai] Anthropic은 Fable을 어려운 추론·장기 에이전트 작업, Opus를 장기 코딩·지식 작업, Sonnet을 속도와 능력의 균형으로 구분한다.[^claude] 위 역할 배치는 이 설명을 프로젝트에 적용한 제안이며 검증된 역할별 우승 모델 표가 아니다.

## 🔌 호출 검사 결과

- 설치: Claude Code 2.1.292, Codex CLI 0.160.0 확인.
- 로컬 Codex 모델 캐시에 gpt-6-astra, gpt-6.1-sol의 high와 gpt-6-luna의 max가 등록돼 있음. 캐시 등록은 실제 계정 호출 성공의 증거가 아님.
- Claude Code / claude-sonnet-5-5 / high: 도구 없는 READY 응답 검사에서 `Not logged in · Please run /login`. 추론 토큰 사용 없음, 모델 응답 미확인.
- Codex / gpt-6.1-sol / high: 읽기 전용·임시 실행 검사에서 `failed to initialize in-process app-server client: Operation not permitted`. 모델 응답 미확인.
- 샌드박스 밖 로그인 상태 검사 요청은 거절됨. 자격증명 이동, 토큰 복제, 다른 경로로 권한 제한 우회는 하지 않음.
- 나머지 모델의 호출·성능 비교는 실행하지 않음. 모든 모델이 안 된다는 결론이 아니라, 현재 실행 환경에서 대표 경로의 연결 검증이 막힌 상태임.

Claude Code CLI 실행 성공, Hermes의 모델 연결 성공, Hermes 역할·도구·인계 성공은 각각 별도 확인해야 한다. 특히 Hermes의 Claude 인증 사용과 Claude Code 프로세스를 작업자로 실행하는 것은 같은 구조가 아니다. 실제 연결 방식과 effort 전달을 확인하기 전에는 설정 문자열만으로 통합 완료를 선언하지 않는다.

## 🧪 정상 연결 후 검증 순서

1. 각 후보를 명시적 모델 ID·effort로 한 번씩 호출하고 런타임의 보고 모델과 응답을 기록한다. 별칭의 fallback을 성공으로 오인하지 않는다.
2. 실제 봇 경로로 역할·공통 스킬 로딩과 읽기 전용 파일 도구 호출을 확인한다.
3. 고정된 작은 과제로 생존과 비용 교란, 순환 거래 악용, 평가 단서 오염, 잔액 버그 재현을 검사한다. 기대 검출 항목을 실행 전에 고정한다.
4. 같은 Sonnet 과제에서 high/xhigh/max를 비교하되 정확성, 근거, 누락, 실행 시간, 사용량, 범위 위반을 평가한다. 단일 호출 속도로 일반적인 우열을 주장하지 않는다.
5. Director→Engineer→Verifier의 한 번의 인계를 검증한다. 프로필 등록이나 READY 응답만으로 팀 전체 자동화가 검증됐다고 하지 않는다.

[^sonnet]: Anthropic, [Prompting Claude Sonnet 5.5](https://platform.claude.com/docs/en/build-with-claude/prompt-engineering/prompting-claude-sonnet-5-5), effort 및 검증 지침.
[^openai]: OpenAI, [Model selection](https://developers.openai.com/api/docs/guides/model-selection).
[^claude]: Anthropic, [Models overview](https://platform.claude.com/docs/en/models/overview).
