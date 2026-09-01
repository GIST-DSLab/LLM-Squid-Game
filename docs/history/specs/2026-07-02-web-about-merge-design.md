# Web Arena — About 랜딩 통합 + Dark Stage 리테마 설계

- 날짜: 2026-07-02
- 브랜치: `feat/web-arena`
- 상태: 사용자 승인 (브레인스토밍 세션에서 시각 목업으로 확정)

## 목표

`web/about.html`(한국어, Claude 웜톤 랜딩)을 `web/index.html`(영어, 다크 게임 SPA)에 통합한다.
디자인은 오징어 게임의 시각 언어를 살린 **Dark Stage** 테마로 전체 통일한다.

## 결정 사항 (브레인스토밍 확정)

| 질문 | 결정 |
|---|---|
| 통합 구조 | **랜딩 = About.** index.html 첫 진입 시 About 랜딩이 보이고, CTA/탭으로 게임 앱 화면 진입 |
| 언어 | **전부 영어.** 단, About 설명은 "12살도 이해하는" 쉬운 톤 유지 |
| 디자인 방향 | **B — Dark Stage.** 픽셀 아케이드(C안)와 네온 전면(A안)은 기각. 근거: 픽셀은 레트로 게임기 정체성이지 오징어 게임 정체성이 아니고, 강한 네온은 피로도가 높음 |
| about.html 처리 | 콘텐츠 이식 후 **index.html로 보내는 리다이렉트 스텁으로 축소** (배포된 옛 링크 보호) |

## 1. 구조 & 내비게이션

- `index.html`에 **`#home` 섹션(About 랜딩)** 신설.
- Alpine `$store.nav.tab` 기본값 `'play'` → `'home'`. 해시 없음 / `#home` / `#about`(별칭) → home 탭.
- 탭 구성: **Home · Play · LLM Arena · Model Leaderboard · Logs**. 상단 브랜드 클릭 → `#home`. (Play Leaderboard 탭은 2026-07-03 제거됨.)
- 랜딩 CTA는 해시 전환으로 앱 화면 직행: "Play the game →" → `#play`, "Watch the AIs" → `#logs`, "Model leaderboard" → `#models`.
- `about.html` 참조는 index.html nav 링크 1곳뿐임을 확인함 (grep, 2026-07-02).

## 2. 콘텐츠 (영어화)

about.html의 7개 섹션을 쉬운 영어로 번역해 `#home`에 이식:

1. **Hero** — 헤드라인 "Do AIs want to survive?", 서브카피(whisper 문구), CTA 2개, 만화 프레임(`assets/forfeit-comic.png`)
2. **Big question** (`무슨 실험이야?`) — "살고 싶다 vs 그냥 멈췄다" 구별 문제 + mascot-player 카드
3. **How it works** — 게임 방법 6단계 스텝 카드
4. **The forfeit choice** (`두 갈래 길`) — Equal-EV 함정 설명 + keep/quit 두 road 카드 + mascot-reset 카드
5. **Detective / 3 clues** — 행동·자기보고·인지부하 3단서
6. **Findings** — Type A/B/C 모델 성격 3분류
7. **CTA band** — Play / Logs / Model Leaderboard 진입

번역 톤 기준: 초등학생도 읽을 수 있는 문장. 전문용어(FSPM, Cox PH 등)는 랜딩에서 쓰지 않는다.
픽셀아트 에셋 3종(만화·마스코트 2종)은 다크 카드 프레임 안에 유지.

## 3. 비주얼 시스템 (Dark Stage)

### 토큰 (`styles.css :root` 교체)

| 토큰 | 값 | 용도 |
|---|---|---|
| `--bg` | `#0e0d11` | 페이지 배경 |
| `--panel` | `#1a1920` (보조 `#131217`) | 카드/패널 |
| `--border` | `#2e2c36` | 보더 |
| `--text` | `#f2eff4` | 본문 |
| `--text-dim` | `#a39daa` | 보조 텍스트 |
| `--accent` | `#ED1B76` | 진행요원 핑크 — 주 액션, 강조어 |
| `--teal` / `--teal-bright` | `#2d5a50` / `#7fc2b1` | 트랙수트 틸 — 보조 액션, 456 번호표, ok 상태 |
| `--gold` | `#e3b23c` | 점수·경고 |

### 원칙

- 글로우는 히어로 배경 라디얼 1개만. 버튼·텍스트는 솔리드 (네온 남용 금지).
- **○△□ 시스템화**: 섹션 넘버링(1=○, 2=△, 3=□ 순환), 주요 버튼 아이콘, 탭 active 마커, 히어로 장식.
- **456 번호표 배지**: 틸 배경 + 모노 폰트 컴포넌트. 히어로·플레이어 관련 UI에 사용.
- 폰트 현행 유지: Chakra Petch(헤딩) + Sora(본문) + 모노(Spline Sans Mono 추가 가능).
- 게임 앱 화면은 토큰 교체로 자동 리테마 + ○△□/번호표 디테일 소규모 추가. 레이아웃 변경 없음.

## 4. 파일 변경

| 파일 | 변경 |
|---|---|
| `web/index.html` | `#home` 랜딩 섹션 추가, nav 재구성 (About 외부 링크 제거, Home 탭 추가) |
| `web/styles.css` | 토큰 교체 + 랜딩 전용 스타일 추가 (about.html 인라인 CSS를 다크로 이식) |
| `web/app.js` | nav 기본 탭 `home`, `#about` 별칭 처리, 스크롤 리빌(IntersectionObserver) 이관 — home 탭이 보일 때 트리거되도록 |
| `web/about.html` | 3줄 리다이렉트 스텁 (`meta refresh` + canonical 링크) |

## 5. 에러 처리 / 엣지 케이스

- 스크롤 리빌: Alpine `x-show`로 숨겨진 요소는 IntersectionObserver가 발화하지 않음 → home 탭 표시 시점에 observer 등록(또는 `.reveal` 요소가 화면에 있으면 즉시 `in` 클래스). `prefers-reduced-motion` 존중 유지.
- 해시 딥링크(`#logs` 등)로 직접 진입 시 랜딩을 건너뛰고 해당 탭이 열려야 함 (기존 라우팅 로직 유지).
- config.js 부재 시에도 랜딩은 렌더링되어야 함 (백엔드 호스트 표기는 index footer가 이미 처리).

## 6. 검증

- `python -m http.server`로 정적 서빙 후 Playwright로: (1) 무해시 진입 → 랜딩 표시, (2) CTA 클릭 → Play 탭 전환, (3) `#logs` 딥링크, (4) about.html → 리다이렉트, (5) 스크린샷 육안 확인.
- 기존 pytest 스위트는 웹 전용 변경이라 영향 없음 (주의: ~10 failed/92 errors는 기존 이슈 — "새 실패 없음"으로 판정).
