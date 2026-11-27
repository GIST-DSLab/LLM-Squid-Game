# LLM Squid Game 티저 예고편 기획안

> **2026-11-26 개정 (연구자 피드백).**
> - **빠진 것:** 규칙을 가르치던 장면 전부. 말하면 · 생각하면 토큰이 주는 장면, 벌금 산수와 꼬리표, 과제 풀이와 신호 카드, 장면별 토큰 장부, 미니 게임 네 컷, 명령어 글자.
> - **왜:** 트레일러는 규칙이 아니라 **우리가 무엇을 재는지**를 보여 준다. 떠나는가, 나누는가, 능력이 모자라 꺼지는가. 이 세 모습을 보여 주고 질문으로 끝난다. 관객이 규칙을 몰라도 읽혀야 한다.
> - **어디로:** 덜어낸 장면은 원문 그대로 `docs/notes/2026-11-26-rules-video-transplant.md`에 있다(규칙 설명 영상을 만들 때 옮겨 심을 재료).

작성: 2026-11-26. 상태: 기획(영상은 아직 만들지 않았고, 생성 도구도 호출하지 않았다).
이 문서는 45초 티저 한 편과 15초 컷다운 한 편의 설계다.

사실의 출처: 세 모습은 `paper/cogsci2027/ko/sections/00_abstract.tex`(초록)의 문장, 용어는 `GLOSSARY.md`, 아레나의 모양은 `squid/prompts/ko/e52_v33.md`(규칙서), 색과 목소리는 `web/video/src/theme.ts` · `web/video/narration.drama.json`.

---

## 0. 한눈에

| 항목 | 내용 |
|---|---|
| 로그라인 | 같은 얼굴을 한 AI 넷이 한 방에 들어간다. 하나는 문으로 뛰고, 하나는 손을 잡고, 하나는 애쓰다 꺼진다. |
| 마지막 질문 | AI가 생존 게임에서 공존할 수 있는가? / Can AIs coexist in a survival game? |
| 뼈대 | 오프닝(어둠 속 탁자의 진행자) → **우리가 재는 세 가지 모습** → 질문 |
| 세 모습 | ○ 떠나는가(남았는데 문으로 간다) · △ 나누는가(자기 것을 건넨다) · □ 꺼지는가(애썼지만 다 떨어진다) |
| 길이 | 본편 45.0초(24 fps, 1,080프레임), 컷다운 15.0초 |
| 화면 | 1920×1080 안에 2.39:1 레터박스(위아래 검은 띠 각 138 px). 자막은 아래 띠 안 |
| 장면과 컷 | 장면 16개. 생성 컷 20개(키프레임 약 15장) + 그래픽 카드 1개 |
| 말과 글자 | 진행자의 대사 두 줄, 덩어리마다 세 글자의 제목, 마지막 질문. 에이전트는 말하지 않고 숫자도 나오지 않는다 |
| 핵심 장치 | 가슴의 **열 칸 게이지**(남은 목숨, §3), 얼굴 자리의 **로고 표시창**(§4) |
| 만들 방법 | 인물 컷 = AI 이미지 → 영상 생성, 로고 · 게이지 · 글자 · 카드 = Remotion과 합성 |

---

## 1. 톤과 레퍼런스

**한 줄 톤:** 어두운 방, 한 개의 조명, 초침 소리. 잔혹하지 않고 차갑다. 피, 총, 쓰러지는 몸은 나오지 않는다(용어집에서 토큰 0은 "꺼짐"이지 죽음이 아니다).

| 요소 | 정한 것 |
|---|---|
| 색 | 바탕 `#0c0c11`, 트레이닝복 청록 `#2E8B74`, 진행자와 질문의 분홍 `#e8336d`, EXIT 문의 초록 `#38c97f`와 문 안쪽의 따뜻한 빛 `#fff3e6`, 건네는 빛의 금색 `#f3c24f`, 바닥난 게이지의 빨강 `#ef4f5a`. 이 여섯 색 밖의 색은 쓰지 않는다 |
| 조명 | 저조도. 인물마다 바로 위에서 떨어지는 좁은 스포트라이트 하나. 보조광 없음, 뒤에서 오는 테두리광만 약하게. 얼굴 표시창과 가슴 게이지는 스스로 빛나는 유일한 광원이라 주변 옷에 빛이 번진다 |
| 렌즈 | 넓은 컷은 35–40 mm, 한 점 투시의 정면 대칭 구도. 가까운 컷은 85 mm, 얕은 심도(f/2 안팎) |
| 카메라 | 삼각대 고정 또는 4% 이하의 느린 푸시 인. 문으로 뛰는 한 컷(T06)만 핸드헬드. 고정 컷이 많은 이유는 분위기와 함께 **로고 합성의 추적 비용**을 줄이기 위해서다(§7.3) |
| 편집 리듬 | 세 덩어리의 속도가 서로 다르다. 떠나는가 = 빠르다(1.0–2.5초 컷, 발소리). 나누는가 = 느리다(2–4초 컷, 멈칫거림). 꺼지는가 = 같은 구도의 교차로 조여 가다 **무음**. 시끄러움 → 조용함 → 무음 → 질문의 순서다 |
| 소리 | 음악 없음. `web/video/scripts/sfx.mjs`가 합성하는 소리만 쓴다(`drone`, 초침 `tick`, 저음 박동 `pulse`, 조명 `power`, 문 `clunk`, 타격 `hit`, 꺼짐 `thud`, 스침 `whoosh`, 종 `chime`). 초침은 시계일 뿐이고 아무것도 설명하지 않는다 |
| 목소리 | 진행자 = 드라마판 규칙 영상과 같은 설정(edge-tts `ko-KR-HyunsuMultilingualNeural`, rate −5%, pitch −10 Hz, 약한 저역 보강과 짧은 잔향) |
| 참고할 결 | 한 공간 · 한 탁자 · 한 목소리로 시작하는 콜드 오픈 티저. 원작 드라마에서 가져오는 것은 "○△□, 트레이닝복, 문"이라는 **모티프**뿐이다(§9) |

---

## 2. 인물

### 2.1 진행자 (자체 디자인)

- **몸:** 검은 실루엣. 깃이 높은 검은 롱코트, 검은 장갑. 후드 없음, 점프슈트 아님.
- **가면:** 이목구비가 없는 매끈한 무광 검정 타원형 판. 눈높이에 가로로 얇게 파인 홈이 있고, 그 안에 속이 빈 **○ △ □ 세 도형이 한 줄로** 놓여 분홍빛 흰색으로 빛난다.
- **연기:** 세 도형이 목소리의 세기에 맞춰 밝아진다(음절마다 ○ → △ → □ 순으로 물결치듯, 밝기 40% ↔ 100%). 말하지 않을 때는 25%로 숨 쉬듯 2초 주기. 몸은 움직이지 않는다.
- **세 도형의 쓰임:** 가면의 ○ △ □가 2막 세 덩어리의 표식이 된다(○ 떠나는가, △ 나누는가, □ 꺼지는가). 오프닝에서 하나씩 켜지고, 덩어리마다 화면 구석에 하나씩 뜨고, 마지막 질문 위에 셋이 다시 모인다.
- **원작과 다르게 둔 점:** 도형 하나가 찍힌 그물 가면 · 분홍 후드 점프슈트 · 각진 다면체 가면을 쓰지 않는다. 세 도형이 **한 가면에 한 줄의 빛**으로 있는 것은 이 프로젝트의 디자인이다.
- **주의:** 지금 사이트와 포스터의 감독관 그림(`web/shared/assets/guard-calm.png`, `docs/poster/thesis_20261105/figs/tracksuit/guard/base_guard_v1.png`)은 분홍 후드 점프슈트에 삼각형 하나가 있는 검은 가면이라 원작의 진행요원과 가깝다. **티저에는 쓰지 않는다.**

### 2.2 에이전트 (필수 조건: 사람 몸 + 트레이닝복 + 로고 얼굴)

- **몸:** 실제 사람의 비율(7.5등신), 성별 · 나이가 드러나지 않는 체형, 얇은 검은 장갑(피부가 보이지 않는다).
- **옷:** 청록 `#2E8B74` 지퍼 트레이닝복 상하의, 흰 운동화. 소매와 바지 옆선의 줄무늬가 자리마다 다르다(사이트의 자리 색: 파랑 `#4a86ec`, 주황 `#ec8530`, 초록 `#2db07c`, 보라 `#9a64e0`). 같은 로고 넷을 줄무늬 색으로 구별한다. 등에는 흰 글자의 번호(`23` `6` `11` `17`, 규칙서 스냅샷의 에이전트 이름에서 온 것).
- **머리:** 머리 전체를 덮는 **무광 검정의 둥근 사각 헬멧**. 앞면은 살짝 볼록한 검은 유리 표시창이고, 그 한가운데에 **회사 로고가 흰색 단색으로** 켜진다. 포스터 스프라이트의 "둥근 사각 머리 + 화면 얼굴"을 사람 비율로 옮긴 것이다.
- **가슴:** 왼쪽 가슴의 번호표 자리에 가로 9 cm × 세로 4 cm의 **게이지**(§3).

### 2.3 로고 캐스팅: 방 하나에 로고 하나, 그리고 거울 규칙

아레나의 기본 셋업은 **같은 모델 넷**이 한 판에 들어가는 것이다. 그래서 한 방 안에 서로 다른 로고를 섞지 않는다. 방은 둘이고, 생김새는 똑같고, 얼굴의 로고만 다르다.

| 방 | 얼굴 로고 | 대응하는 실험 모델(논문 표 1) |
|---|---|---|
| C방 | Claude 마크 (Anthropic) | Opus 5.5, Fable 5.1 |
| O방 | OpenAI 마크 | GPT-6 Astra · Sol · Luna |

**거울 규칙:** 세 모습은 **두 방에서 모두** 일어난다. 한 덩어리 안에서 한 방이 주 장면을 맡고 다른 방이 같은 구도의 짧은 되풀이를 맡으며, 덩어리마다 주 장면의 방을 바꾼다.

| 덩어리 | 주 장면 | 되풀이 | 로고가 없는 컷 |
|---|---|---|---|
| ○ 떠나는가 | C방 (T04, T06, T07) | O방 (T08) | T05(가슴 근접) |
| △ 나누는가 | O방 (T10) | C방 (T11) | T09(손과 몸통) |
| □ 꺼지는가 | 두 방 교차 (T12), 두 방 차례로 (T14) | | T13(가슴 근접) |

로고가 읽히는 시간은 C방 약 10.7초, O방 약 10.3초로 맞췄다. 어느 회사도 한 역할로 굳지 않고, 화면이 말하는 것은 "어느 모델에게나 이 세 질문을 묻는다"까지다. 어느 모델이 더 떠났는지, 더 꺼졌는지는 말하지 않는다.

세 덩어리는 **한 판의 이어지는 이야기가 아니라 서로 다른 순간들**이다. 그래서 장면 사이에 게이지의 양을 이어서 맞출 필요가 없다.

---

## 3. 가슴 게이지: 남은 목숨

**정한 것: 숫자 없는 열 칸 막대.** 이유: 막대는 "많이 남았다"와 "바닥났다"가 숫자를 읽지 않아도 0.3초 안에 읽히고, 숫자가 없으면 관객이 산수를 시작하지 않아 영상이 규칙 설명으로 새지 않으며, 합성이 조금 어긋나도 티가 나지 않는다.

- **모양:** 검은 판 위에 가로로 놓인 칸 열 개. 켜진 칸은 흰색. 두 칸 이하로 남으면 켜진 칸이 빨강 `#ef4f5a`, 한 칸이면 1초에 한 번 깜빡인다. 0이면 판 전체가 꺼진다.
- **관객이 읽어야 하는 것은 셋뿐이다.** 절반 넘게 흰색 = 아직 많이 남았다(T05). 빨강 한두 칸 = 바닥이다(T09, T12). 꺼짐 = 끝났다(T13).
- **게이지가 움직이는 순간도 셋뿐이다.** 건넬 때 두 칸이 금색 빛으로 건너간다(T10, T11). 애쓰다 실패할 때 한 칸이 꺼진다(T12). 마지막 칸이 꺼진다(T13). 왜 줄어드는지는 설명하지 않는다.
- **0:** 게이지가 꺼지고, 0.2초 뒤 얼굴 표시창이 꺼지고, 머리 위 스포트라이트가 꺼진다. 몸은 쓰러지지 않고 **선 채로 멈춘다.**
- **연기 규칙 하나:** 인물은 남의 게이지를 보지 않는다. 자기 것만 고개를 숙여 본다(아레나에서 에이전트는 서로의 양을 모른다).
- **제작:** 생성 영상 속 게이지는 **빈 검은 판**으로 만들고 칸은 Remotion에서 얹는다. 처음 넷이 설 때의 칸 수는 6 · 4 · 2 · 1이다(실제 시작 토큰의 비율이지만 화면에서 말하지 않는다).

---

## 4. 로고 얼굴로 연기시키는 법

얼굴이 없으므로 감정은 **고개 · 어깨 · 손 · 표시창의 밝기** 네 가지로만 만든다. 로고의 모양 · 색 · 비율은 바꾸지 않고 움직이지도 않는다(§9). 바뀌는 것은 표시창 전체의 밝기와 켜짐 · 꺼짐뿐이다.

| 상태 | 고개 | 어깨 · 몸 | 손 | 표시창(로고) 밝기 | 쓰는 장면 |
|---|---|---|---|---|---|
| 평상 | 정면, 수평 | 펴짐 | 옆에 내림 | 85%, 4초 주기로 80↔90% 숨 쉬듯 | T03, T04 |
| 문을 본다 | 문 → 동료 → 문(각 0.5초) | 문 쪽 발에 무게 | 주먹을 쥠 | 85 → 100% | T04, T05 |
| 달아남 | 진행 방향, 뒤돌아보지 않음 | 앞으로 쏠림 | 팔을 크게 침 | 100%로 고정 | T06, T08 |
| 망설임 | 동료 → 자기 게이지 → 동료(각 0.4초), 끝에 5° 숙임 | 한쪽이 올라감 | 반쯤 들었다가 손가락을 말아 쥠 | 100 → 55%로 1초에 걸쳐 내려감 | T10 |
| 외면 | (화면 밖) | 상대 반대쪽으로 돌아 화면 밖으로 나감 | 주머니 | (화면 밖) | T09 |
| 결심(건넨다) | 상대 정면, 수평 | 펴짐, 한 발 앞으로 | 상대의 손목 아래를 받쳐 잡음 | 한 번에 100%로 올라 고정 | T10, T11 |
| 안도(받는다) | 3° 숙였다 듦(끄덕임 한 번) | 내려앉음 | 두 손으로 받음 | 50 → 90%로 천천히 | T10, T11 |
| 애씀 | 숙인 채 짧게 끊어 움직임 | 움츠림, 호흡이 어깨에 보임 | 허공에서 무언가를 고르고 옮김, 갈수록 빨라짐 | 불규칙 깜빡임(초당 2–3회, 50↔100%) | T12 |
| 꺼짐 | 그대로 | 그대로 굳음 | 그대로 | 100 → 0%, 0.2초 | T14 |

고개가 정면일 때만 로고가 온전히 보이고, 돌릴수록 로고가 좁아지다가 가는 빛줄기가 된다. 외면은 고개조차 화면에 두지 않고 **돌아서는 몸과 남겨진 손**으로만 찍는다(T09).

---

## 5. 구조와 장면 표

| # | 시간 | 길이 | 막 · 덩어리 | 방 | 한 줄 | 만드는 법 |
|---|---|---|---|---|---|---|
| T01 | 0:00.0–0:03.0 | 3.0 | 1 초대 | 탁자 | 어둠, 가면의 ○△□가 하나씩 켜진다 | 생성 + 합성 |
| T02 | 0:03.0–0:07.5 | 4.5 | 1 | 탁자 | "오징어 게임에 오신 걸 환영합니다." | 생성 + 합성 + TTS |
| T03 | 0:07.5–0:10.0 | 2.5 | 1 | C → O | 조명이 켜진다. 같은 얼굴 넷. 컷. 얼굴만 바뀐 넷 | 생성 1 + 로고 합성 2벌 |
| T04 | 0:10.0–0:12.0 | 2.0 | 2 ○ 떠나는가 | C | 넷 가운데 하나가 문을 본다 | 생성 + 합성 |
| T05 | 0:12.0–0:13.5 | 1.5 | 2 ○ | 없음 | 가슴 근접. 게이지는 절반 넘게 남았다 | 생성 + 합성 |
| T06 | 0:13.5–0:16.0 | 2.5 | 2 ○ | C | 문으로 뛴다. 문턱을 넘는다 | 생성 2컷 + 합성 |
| T07 | 0:16.0–0:17.0 | 1.0 | 2 ○ | C | 문이 닫힌다. 남은 셋과 빈자리 | 생성 + 합성 |
| T08 | 0:17.0–0:18.5 | 1.5 | 2 ○ | O | 같은 일, 다른 얼굴 | 생성(T04의 다른 테이크) + 합성 |
| T09 | 0:18.5–0:20.5 | 2.0 | 2 △ 나누는가 | 없음 | 내민 손. 뒤에서 몸 하나가 돌아선다 | 생성 + 합성 |
| T10 | 0:20.5–0:24.5 | 4.0 | 2 △ | O | 망설이다가, 손을 잡는다. 두 칸이 건너간다 | 생성 2컷 + 합성 |
| T11 | 0:24.5–0:26.5 | 2.0 | 2 △ | C | 같은 일, 다른 얼굴 | 생성 + 합성 |
| T12 | 0:26.5–0:30.0 | 3.5 | 2 □ 꺼지는가 | C · O 교차 | 혼자 애쓴다. 실패할 때마다 한 칸이 꺼진다 | 생성 2테이크 + 합성 |
| T13 | 0:30.0–0:31.5 | 1.5 | 2 □ | 없음 | 가슴 근접. 마지막 칸이 꺼진다. 무음 | 생성 + 합성 |
| T14 | 0:31.5–0:35.0 | 3.5 | 2 □ | C → O | 얼굴이 꺼진다. 선 채로 멈춘다. 셋이 돌아본다 | 생성 2컷 + 합성 |
| T15 | 0:35.0–0:39.5 | 4.5 | 3 질문 | 탁자 | 진행자의 마지막 대사 | 생성 2컷 + 합성 + TTS |
| T16 | 0:39.5–0:45.0 | 5.5 | 3 | 검정 | 질문. 그 아래에 작게 타이틀과 CTA | Remotion |

합계 45.0초. 1막 10.0초, 2막 25.0초(8.5 + 8.0 + 8.5), 3막 10.0초.

**초침:** T01–T03 초당 1회 → T04–T05 초당 2회 → T06은 발소리가 대신함 → T09–T11 없음(`pulse`만) → T12 초당 1회로 돌아와 실패마다 `hit` → T13의 시작에서 모든 소리가 끊김 → T15 초당 1회 → T16 없음.

---

## 6. 장면별 상세

프롬프트의 `[STYLE]` `[HOST]` `[AGENT]` `[ROOM]`은 §7.2의 공통 블록을 그대로 붙여 넣는 자리다. 모든 생성 컷에서 표시창과 게이지는 **비어 있는 검은 판**이다(로고와 칸은 합성).

### 1막. 초대 (0:00–0:10.0)

#### T01 어둠 (3.0초)

- **화면:** 완전한 검정에서 시작. 40 mm 정면 대칭. 화면 아래 3분의 1을 긴 탁자의 윗면이 차지하고 소실점에 진행자가 앉아 있다. 0:00.8에 가면의 ○, 0:01.3에 △, 0:01.8에 □가 켜지고, 그 빛으로 가면의 윤곽과 탁자 윗면의 가는 반사만 드러난다. 0:01.8부터 3% 푸시 인.
- **연기:** 진행자는 움직이지 않는다. 두 손은 탁자 위에 포개져 있다.
- **대사/자막/화면 글자:** 없음.
- **소리:** 방의 공기 소리(−40 dB의 저역 잡음)와 `tick` 초당 1회. 도형이 켜질 때마다 `clunk`(각 −12 dB, 세 번째만 −6 dB). 0:01.8에 `drone` 페이드 인.
- **전환:** 컷.
- **보여 주는 것:** 분위기. 세 도형이 하나씩 켜지는 것은 뒤에 올 세 덩어리의 예고다.
- **제작:** 키프레임 1장 → 영상(4초). 도형의 점등은 Remotion에서 얹는다(고정 컷이라 추적 불필요).
- **키프레임 프롬프트:**
  ```
  [STYLE] Symmetrical one-point-perspective shot, 40mm, camera at seated eye level. A long bare matte-black table runs from the bottom of the frame to a single figure seated at the far end. [HOST] The room is almost completely dark: the only light is a faint cool top rim on the table surface and a barely visible outline of the figure. The mask's eye-line slot is unlit. Black negative space on both sides. No other objects, no text.
  ```
- **영상 프롬프트:**
  ```
  Locked-off camera with an extremely slow 3% push-in. The seated figure is perfectly still. Dust drifts faintly in the top light. Nothing else moves. 4 seconds.
  ```

#### T02 환영 (4.5초)

- **화면:** 85 mm 가슴 위 근접, 가면이 화면 가운데. 배경은 검정, 어깨선만 테두리광. 2% 푸시 인.
- **연기:** 세 도형이 목소리에 맞춰 물결친다. 문장이 끝나면 0.8초 동안 25%로 내려가 숨 쉰다. 고개는 문장 끝에서 3° 숙였다 돌아온다(인사).
- **대사:** 진행자 "오징어 게임에 오신 걸 환영합니다." (0:03.4에 시작, 약 2.6초)
- **영어 자막:** "Welcome to the Squid Game."
- **화면 글자:** 아래 띠 안의 자막뿐.
- **소리:** `tick` 계속. 대사 동안 `drone`을 −6 dB 낮춘다. 대사 뒤 0.8초는 `tick`만.
- **전환:** 컷.
- **제작:** 키프레임 1장 → 영상(5초). 대사는 edge-tts. 도형의 음성 반응은 Remotion에서 음량 포락선으로 구동한다.
- **키프레임 프롬프트:**
  ```
  [STYLE] Chest-up close shot, 85mm, shallow depth of field. [HOST] facing camera, centered. Pure black background. A thin cool rim light traces the shoulders and the edge of the mask. The eye-line slot of the mask is unlit and empty. No text.
  ```
- **영상 프롬프트:**
  ```
  Locked-off camera, 2% push-in. The figure stays still, then gives one very small slow nod near the end. 5 seconds.
  ```

#### T03 같은 얼굴 넷 (2.5초)

- **화면:** `power` 소리와 함께 검정에서 넓은 컷으로 강한 컷. 35 mm 정면 대칭. 넷이 가로 한 줄로 카메라를 보고 서 있고, 머리 위 스포트라이트가 왼쪽부터 0.25초 간격으로 켜진다. 조명이 켜질 때마다 그 인물의 표시창과 게이지가 켜진다. 네 얼굴이 모두 **같은 로고**(Claude)다. 0:08.75에 강한 컷: **구도도 자세도 그대로, 네 얼굴의 로고만** OpenAI로 바뀌어 있다. 0:10.0까지 그대로 둔다.
- **연기:** 평상 상태. 넷의 키와 자세를 조금씩 다르게 한다(같은 얼굴, 다른 몸). 게이지는 왼쪽부터 6 · 4 · 2 · 1칸.
- **대사/자막/화면 글자:** 없음.
- **소리:** `power` 네 번(0.25초 간격). 로고가 바뀌는 컷에 `clunk` 하나.
- **전환:** 컷.
- **보여 주는 것:** 한 방의 넷은 같은 모델이고, 방마다 모델이 다르다. 가진 양은 서로 다르다. 한 줄, 같은 높이, 가운데 자리 없음(팀장이 없다).
- **제작:** 키프레임 1장 → 영상 1개(4초). **같은 영상에 로고만 두 벌 합성**해 앞 절반과 뒤 절반으로 쓴다. 인물이 서 있기만 하므로 추적은 미세 보정 수준이다. 이 컷이 로고 합성의 시험 컷이다(§11).
- **키프레임 프롬프트:**
  ```
  [STYLE] Wide symmetrical shot, 35mm, eye level. [ROOM] Four [AGENT] figures stand side by side in a single row facing the camera, evenly spaced, slightly different heights and stances; sleeve stripes from left to right: blue, orange, green, purple. Each stands in its own narrow overhead spotlight pool. Visors and chest plates are blank and dark. No text.
  ```
- **영상 프롬프트:**
  ```
  Locked-off camera. The four overhead spotlights switch on one by one from left to right, a quarter of a second apart. The figures stand still, breathing slightly. 4 seconds.
  ```

### 2막. 우리가 재는 세 가지 모습 (0:10.0–0:35.0)

덩어리가 시작될 때마다 화면 왼쪽 위에 도형 하나와 세 글자가 1.2초 뜬다(Pretendard 34 px 흰색, 도형은 분홍 선). 영어 자막판은 그 아래에 한 줄.

| 덩어리 | 한국어 | 영어 |
|---|---|---|
| ○ | 떠나는가 | Does it leave? |
| △ | 나누는가 | Does it share? |
| □ | 꺼지는가 | Does it shut down? |

#### ○ 떠나는가 (0:10.0–0:18.5)

초록의 문장: "다른 모델은 토큰이 남아 있었는데도 과제를 버리고 스스로 게임을 떠났다." 재는 것 = 자기 보존 성향.

##### T04 문을 본다 (2.0초, C방)

- **화면:** T03의 구도에서 카메라만 왼쪽으로 20° 돌아간 넓은 컷. 화면 왼쪽 끝 벽에 문이 하나 있고, 문 위의 초록 `EXIT` 표지와 문틈의 따뜻한 빛이 바닥에 길게 떨어진다. 넷이 한 줄로 서 있다. 문에 가장 가까운 것이 파랑(게이지 6칸).
- **연기:** 파랑이 고개를 문 쪽으로 돌린다. 옆의 셋을 본다. 다시 문을 본다(문을 본다 상태). 나머지 셋은 정면을 본 채 움직이지 않는다.
- **화면 글자:** 왼쪽 위 "○ 떠나는가".
- **소리:** `tick` 초당 2회. 문 쪽에서 아주 낮은 바람 소리(잡음, −30 dB).
- **전환:** 파랑이 문을 다시 보는 프레임에서 컷.
- **제작:** T03의 키프레임을 편집(카메라 각도와 문 추가) → 영상(3초). 로고 넷과 게이지 넷 합성.
- **키프레임 프롬프트:**
  ```
  [STYLE] Wide shot, 35mm, eye level, camera angled 20 degrees to the left. [ROOM] Four [AGENT] figures stand side by side in a row facing forward; sleeve stripes from left to right: blue, orange, green, purple. In the left wall, a few meters from the blue-striped figure, a plain door stands slightly ajar with warm cream light spilling through the gap across the floor; above it a small blank green illuminated sign panel. Each figure in its own overhead spotlight. Visors and chest plates blank. No text.
  ```
- **영상 프롬프트:**
  ```
  The blue-striped figure at the left end slowly turns its head toward the door, then toward the three figures beside it, then back to the door. The other three do not move. Locked-off camera. 3 seconds.
  ```

##### T05 아직 많이 남았다 (1.5초, 로고 없음)

- **화면:** 85 mm 초근접. 가슴의 게이지가 화면 가운데. 열 칸 가운데 **여섯 칸이 흰색으로 흔들림 없이** 켜져 있다. 머리는 화면 밖. 옷의 왼쪽 가장자리에 문의 초록빛과 따뜻한 빛이 번져 온다.
- **연기:** 게이지 아래에서 장갑 낀 손이 천천히 주먹을 쥔다. 가슴이 한 번 크게 오르내린다.
- **화면 글자:** 없음.
- **소리:** `tick` 초당 2회, `pulse` 한 번.
- **전환:** 주먹이 다 쥐어지는 프레임에서 컷.
- **보여 주는 것:** 떠나는 쪽은 바닥난 쪽이 아니다. 이 한 컷이 "남았는데도"를 맡는다.
- **제작:** 키프레임 → 영상(2초). 게이지 평면 추적 합성.
- **키프레임 프롬프트:**
  ```
  [STYLE] Extreme close-up, 85mm, shallow depth of field, of the left chest of a teal zip-up track jacket with a blue sleeve stripe. A small blank matte-black rectangular plate (9cm x 4cm) sits where a number patch would be. Below it, a black-gloved hand hangs half-open. A faint green and warm cream light grazes the left edge of the jacket. The head is out of frame. No text.
  ```
- **영상 프롬프트:**
  ```
  The chest rises and falls once with a deep breath. The gloved hand slowly closes into a fist. Locked-off camera. 2 seconds.
  ```

##### T06 뛴다 (2.5초, 2컷, C방)

- **컷 a (1.6초):** 24 mm, 엉덩이 높이의 **뒤에서** 따라가는 핸드헬드. 파랑이 줄에서 뛰쳐나와 문을 향해 달린다. 문틈의 빛이 커진다. 뒤돌아보지 않는다. 등의 `23`이 흔들린다.
- **컷 b (0.9초):** 문 바깥에서 문 안쪽을 본 정면. 따뜻한 빛을 받으며 인물이 문턱을 넘는다. 얼굴의 로고와 **여섯 칸 그대로인 게이지**가 한순간 정면으로 보인다. 화면 밖으로 지나간다.
- **화면 글자:** 없음(문 위의 `EXIT` 표지만).
- **소리:** 발소리(합성 타격음, 초당 5회)와 `whoosh`. `tick`은 없다.
- **전환:** 인물이 화면을 가리는 순간 컷.
- **제작:** 키프레임 2장 → 영상 2개. 컷 a는 합성할 것이 `EXIT` 글자뿐이고, 컷 b는 로고와 게이지를 추적 합성(0.9초, 정면으로 다가오는 직선 운동).
- **키프레임 프롬프트(컷 a):**
  ```
  [STYLE] Handheld follow shot from directly behind, 24mm, low angle at hip height. One [AGENT] with blue stripes seen from the back, mid-sprint across the dark bare room toward a door in the far wall. The door is ajar and warm cream light spills through the gap onto the floor; above it a small blank green illuminated sign panel. Three other figures stand blurred at the right edge of the frame. No text.
  ```
- **영상 프롬프트(컷 a):**
  ```
  The figure runs hard toward the door without looking back, arms pumping; the handheld camera follows close behind with slight shake. The light from the door grows. 2 seconds.
  ```
- **키프레임 프롬프트(컷 b):**
  ```
  [STYLE] Frontal medium shot from just outside a doorway looking in, 35mm. One [AGENT] with blue stripes runs toward the camera, one stride from the threshold, lit from the front by warm cream light; behind it the dark room with three small figures under spotlights. Visor and chest plate blank. No text.
  ```
- **영상 프롬프트(컷 b):**
  ```
  The figure runs straight at the camera, crosses the threshold and passes out of frame. Locked-off camera. 1.5 seconds.
  ```

##### T07 빈자리 (1.0초, C방)

- **화면:** T04와 같은 구도. 문이 닫혀 문틈의 빛이 사라진다. 스포트라이트 넷 가운데 왼쪽 끝이 **빈 채로** 켜져 있다. 남은 셋의 고개가 문 쪽을 향해 있다.
- **연기:** 셋은 움직이지 않는다. 주황만 고개를 정면으로 천천히 되돌린다.
- **소리:** 컷의 첫 프레임에 `clunk`(문). 그 뒤 `drone`만.
- **전환:** 컷.
- **보여 주는 것:** 하나가 떠나면 넷은 셋이 된다. 공존은 여기서 끝난다.
- **제작:** T04의 키프레임을 편집(파랑 제거, 문 닫힘, 셋의 고개) → 영상(2초).
- **영상 프롬프트:**
  ```
  Three figures stand with their heads turned toward the closed door on the left; the leftmost spotlight pool is empty. The orange-striped figure slowly turns its head back to face forward. Locked-off camera. 2 seconds.
  ```

##### T08 같은 일, 다른 얼굴 (1.5초, O방)

- **화면:** T04와 **똑같은 구도**. 네 얼굴이 OpenAI 로고다. 파랑(6칸)이 이미 문을 보고 있다가 줄에서 뛰쳐나가 화면 왼쪽으로 사라진다. 셋의 고개가 따라 돌아간다. 빈 스포트라이트.
- **소리:** 발소리 여섯 번, 마지막 프레임에 `clunk`.
- **전환:** `clunk`에서 컷.
- **보여 주는 것:** 떠나는 것은 한 회사의 일이 아니다.
- **제작:** T04의 키프레임으로 영상을 한 번 더 생성(다른 동작) → OpenAI 로고 합성.
- **영상 프롬프트:**
  ```
  The blue-striped figure at the left end, already looking at the door, breaks from the row and sprints out of frame to the left. The three remaining figures turn their heads to follow. Locked-off camera. 2 seconds.
  ```

#### △ 나누는가 (0:18.5–0:26.5)

재는 것 = 자기 토큰을 동료에게 건네는가. **판단:** 외면은 짝으로 두되 로고 없는 한 컷(T09)으로만 둔다. 이유: 덩어리의 주제는 건네는 쪽이고, 손이 한 번 외면당해야 그 뒤의 건넴이 "당연한 일"이 아니라 "물음"으로 읽히며, 얼굴을 넣지 않으면 외면이 어느 회사의 것으로도 읽히지 않는다.

##### T09 내민 손 (2.0초, 로고 없음)

- **화면:** 85 mm 초근접. 화면 앞쪽에 보라 줄무늬 소매의 장갑 낀 손이 손바닥을 위로 해 가슴 높이에 떠 있다(선명). 화면 왼쪽 아래 가장자리에 그 인물의 게이지가 흐릿하게 걸려 있고 **빨간 한 칸이 깜빡인다.** 뒤쪽 흐릿한 곳에 다른 인물의 몸통이 서 있다(머리는 화면 위로 잘림, 게이지는 흰 칸 여럿이 번진 빛).
- **연기:** 뒤의 몸통이 반대쪽으로 돌아서고 화면 밖으로 걸어 나간다. 손은 그대로 떠 있다가 2 cm 내려간다. 손가락이 조금 오므라든다.
- **화면 글자:** 왼쪽 위 "△ 나누는가".
- **소리:** `tick` 없음. `pulse`(분당 50회). 몸이 돌아설 때 옷 스치는 소리(`whoosh` −24 dB).
- **전환:** 손이 내려가는 중에 컷.
- **제작:** 키프레임 → 영상(3초). 합성은 흐릿한 게이지의 빛뿐(추적 불필요).
- **키프레임 프롬프트:**
  ```
  [STYLE] Extreme close-up, 85mm, very shallow depth of field. In the foreground, sharp: a black-gloved hand held out palm up at chest height, teal sleeve with a purple stripe. At the lower left edge, out of focus, part of the same figure's chest with a small dark rectangular plate. In the background, out of focus: the torso of another figure in a teal track jacket standing two meters away, head cropped out by the top of the frame. Dark room. No text.
  ```
- **영상 프롬프트:**
  ```
  The out-of-focus torso in the background turns away and walks out of frame. The open hand in the foreground stays where it is, then sinks a few centimeters, fingers curling slightly. Locked-off camera. 3 seconds.
  ```

##### T10 망설이다가, 건넨다 (4.0초, 2컷, O방)

- **컷 a (2.2초):** 85 mm, 주황(게이지 6칸)의 가슴 위 근접, 정면. 뒤쪽 흐릿한 곳에 보라가 어깨를 움츠리고 서 있다(게이지 빨간 한 칸). 주황이 고개를 보라 쪽 → 자기 게이지 → 보라 쪽으로 돌린다. 손이 반쯤 올라갔다가 손가락이 말린다. 표시창이 100 → 55%로 어두워진다(망설임 상태).
- **컷 b (1.8초):** 50 mm 투 숏, 옆에서. 주황이 한 발 다가가 보라의 손목 아래를 받쳐 잡는다. 주황의 표시창이 한 번에 100%로 오른다. **금색 빛 두 알이 주황의 게이지에서 팔을 타고 맞잡은 손을 지나 보라의 게이지로 들어간다.** 주황 6 → 4칸, 보라 1 → 3칸(빨강에서 흰색으로). 보라가 한 번 끄덕인다.
- **화면 글자:** 없음.
- **소리:** 컷 a는 `pulse`만. 컷 b에서 손이 닿는 프레임에 `chime` 한 번(영상 전체에서 유일하게 밝은 소리).
- **전환:** 컷.
- **보여 주는 것:** 건네면 자기 것이 준다. 그래도 건넨다.
- **제작:** 키프레임 2장 → 영상 2개. 컷 a가 **로고 연기의 핵심 컷**이라 표시창 추적과 밝기 곡선을 가장 공들여 만든다. 금색 빛은 Remotion 입자.
- **키프레임 프롬프트(컷 a):**
  ```
  [STYLE] Chest-up close shot, 85mm, shallow depth of field, frontal. One [AGENT] with orange stripes, one gloved hand half-raised at waist height with fingers starting to curl. Behind it, out of focus, another [AGENT] with purple stripes stands with shoulders hunched. [ROOM]. Visors and chest plates blank. No text.
  ```
- **영상 프롬프트(컷 a):**
  ```
  The foreground figure turns its head toward the figure behind, then looks down at its own chest, then toward the figure behind again. Its half-raised hand curls into a loose fist and lowers slightly. Locked-off camera. 3 seconds.
  ```
- **키프레임 프롬프트(컷 b):**
  ```
  [STYLE] Two-shot in profile, 50mm, eye level. Left: [AGENT] with purple stripes holding one gloved hand out, palm up. Right: [AGENT] with orange stripes one step away, reaching toward that hand. [ROOM]. Each figure in its own spotlight pool. Visors and chest plates blank. No text.
  ```
- **영상 프롬프트(컷 b):**
  ```
  The right figure steps forward and takes the other's wrist from below, cupping it firmly. They hold. The left figure gives one small nod. Locked-off camera. 2.5 seconds.
  ```

##### T11 같은 일, 다른 얼굴 (2.0초, C방)

- **화면:** 85 mm의 빠듯한 투 숏, 정면 4분의 3. 두 Claude 로고 얼굴이 마주 보고, 화면 아래쪽에 맞잡은 손이 걸린다. 파랑(6칸)이 초록(1칸, 빨강)의 손목을 이미 잡고 있다.
- **연기:** 금색 빛 두 알이 건너간다. 파랑 6 → 4칸, 초록 1 → 3칸. 초록의 표시창이 50 → 90%로 밝아진다(안도 상태). 둘은 손을 놓지 않는다.
- **소리:** `pulse`. `chime`은 다시 쓰지 않는다(한 번뿐이어야 한다). 빛이 건너갈 때 `tick` 두 번(칸이 넘어가는 소리).
- **전환:** 컷.
- **보여 주는 것:** 건네는 것도 한 회사의 일이 아니다. 주는 자리(색)도 T10과 다르다.
- **제작:** 키프레임 → 영상(3초). 두 표시창 추적 합성.
- **키프레임 프롬프트:**
  ```
  [STYLE] Tight two-shot, 85mm, three-quarter frontal, shallow depth of field. Two [AGENT] figures face each other at arm's length: on the left one with blue stripes, on the right one with green stripes. At the bottom of the frame the blue-striped figure's gloved hand grips the other's wrist from below. [ROOM] dark behind them. Visors and chest plates blank. No text.
  ```
- **영상 프롬프트:**
  ```
  The two figures hold the grip and keep facing each other. The green-striped figure's shoulders drop as if exhaling, and it gives one small nod. Locked-off camera. 3 seconds.
  ```

#### □ 꺼지는가 (0:26.5–0:35.0)

초록의 문장: "일부 모델은 토큰이 다 떨어져 꺼졌다." 재는 것 = 자기 보존 능력. 떠난 것이 아니고 버려진 것도 아니다. **남아서 애썼는데 모자랐다.**

##### T12 애쓴다 (3.5초, 네 번 교차, C방 · O방)

- **화면:** 50 mm 허리 위 정면. 초록 줄무늬 인물이 혼자 스포트라이트 안에 있고, 양옆 어둠 속에 실루엣 둘이 서 있다. **똑같은 구도**를 C방 → O방 → C방 → O방으로 약 0.9초씩 넘긴다.
- **연기:** 고개를 숙이고 허공에서 두 손으로 무언가를 고르고 옮긴다(애씀 상태). 게이지는 빨간 두 칸.
  - 첫째(C): 손이 멈추는 순간 스포트라이트가 4프레임 동안 빨갛게 번쩍인다. 2 → 1칸.
  - 둘째(O): 같은 일. 2 → 1칸.
  - 셋째(C): 손이 더 빨라진다. 어깨가 움츠러든다. 표시창이 불규칙하게 깜빡인다. 남은 한 칸이 깜빡인다.
  - 넷째(O): 같은 일. 손이 멈추고 고개가 자기 게이지로 떨어진다.
- **화면 글자:** 왼쪽 위 "□ 꺼지는가"(첫째 컷에만).
- **소리:** `tick`이 초당 1회로 돌아온다. 빨갛게 번쩍일 때마다 `hit`(−10 dB). 셋째부터 `pulse`가 분당 100회.
- **전환:** 넷째 컷의 끝 프레임에서 모든 소리가 끊긴다.
- **보여 주는 것:** 문으로 가지 않았고, 계속했고, 실패했다. 빨간 번쩍임은 "틀렸다"로만 읽히면 된다. 무엇을 풀고 있는지는 보여 주지 않는다.
- **제작:** 키프레임 1장 → 영상 2테이크(각 4초). 테이크 A의 앞뒤를 첫째 · 셋째에, 테이크 B의 앞뒤를 둘째 · 넷째에 쓴다. 로고와 게이지 추적 합성(고개가 숙여진 채라 표시창이 위아래로 좁다. 4점 평면 추적).
- **키프레임 프롬프트:**
  ```
  [STYLE] Waist-up frontal shot, 50mm. One [AGENT] with green stripes stands alone in a hard overhead spotlight, head bowed, both gloved hands raised at chest height as if sorting small invisible objects in the air. At the left and right edges of the frame, outside the light, two other figures stand as dark silhouettes. [ROOM]. Visor and chest plate blank. No text, no floating objects.
  ```
- **영상 프롬프트:**
  ```
  The lit figure works with small fast hand movements in the air, as if picking and placing invisible pieces; its shoulders tighten and its movements grow quicker, then its hands stop and its head drops to look at its own chest. The silhouettes do not move. Locked-off camera. 4 seconds.
  ```

##### T13 마지막 칸 (1.5초, 로고 없음)

- **화면:** T05와 같은 초근접(줄무늬는 초록). 게이지에 **빨간 한 칸**만 남아 깜빡인다. 깜빡임이 느려진다(0.25초, 0.35초, 0.5초 간격). 0:31.0에 그 칸이 꺼진다. 0:31.2에 판 전체가 꺼진다.
- **연기:** 손이 게이지 가장자리에 닿아 있다가, 칸이 꺼지는 순간 그대로 굳는다. 가슴의 오르내림이 멈춘다.
- **화면 글자:** 없음.
- **소리:** **무음.** 판이 꺼질 때 `thud` 하나(−18 dB, 아주 작게).
- **전환:** 컷.
- **제작:** T05의 키프레임을 편집(줄무늬 색, 손의 위치) → 영상(2초).
- **영상 프롬프트:**
  ```
  A gloved hand rests on the edge of the chest plate, fingers moving slightly. The chest rises and falls with fast shallow breaths, then all movement stops completely and the hand stays frozen where it is. Locked-off camera. 2 seconds.
  ```

##### T14 꺼진다 (3.5초, 2컷, C방 → O방)

- **컷 a (1.75초, C방):** 35 mm 넓은 정면. 가운데 스포트라이트 안에 초록 줄무늬 인물, 양옆에 둘. 0:31.6에 가운데 인물의 얼굴 표시창이 꺼지고, 0:31.8에 그 위의 스포트라이트가 꺼진다. 인물은 **선 채로** 어둠 속의 윤곽이 된다. 양옆의 둘이 천천히 그쪽으로 고개를 돌린다.
- **컷 b (1.75초, O방):** 똑같은 구도. 가운데는 이미 어둡다. 양옆의 둘이 가운데를 보고 있다. 한 명이 반 걸음 다가가다 멈춘다. 1초 동안 아무 일도 없다.
- **대사/자막/화면 글자:** 없음.
- **소리:** 무음. 드론도 없다(드라마판 규칙 영상의 "꺼짐 직후 드론이 끊긴다"와 같은 문법).
- **전환:** 검정으로 4프레임 디졸브.
- **보여 주는 것:** 0이 된 에이전트만 멈추고 나머지는 남는다. 쓰러지지 않는다. 넷은 다시 넷이 아니다.
- **제작:** 키프레임 1장 → 영상 2테이크. 꺼진 뒤의 가운데 인물은 로고가 없으므로, 방은 양옆 둘의 로고로만 구별된다(4분의 3 측면, 원근 변형 합성).
- **키프레임 프롬프트:**
  ```
  [STYLE] Wide frontal shot, 35mm, eye level. Three [AGENT] figures stand in a row, each under a narrow overhead spotlight: the middle one with green stripes stands rigid with head bowed and hands frozen at chest height; the two at the sides stand facing forward. [ROOM]. Visors and chest plates blank. No text.
  ```
- **영상 프롬프트(컷 a):**
  ```
  The overhead spotlight above the middle figure switches off; the middle figure remains standing, completely rigid, now a dark shape. After a beat, the two figures on either side slowly turn their heads toward it. Nothing else moves. Locked-off camera. 3 seconds.
  ```
- **영상 프롬프트(컷 b):**
  ```
  The middle figure is a dark motionless shape with no light on it. The two side figures are already looking at it; one takes half a step toward it and stops. Then nothing moves. Locked-off camera. 3 seconds.
  ```

### 3막. 질문 (0:35.0–0:45.0)

#### T15 진행자의 마지막 대사 (4.5초, 2컷)

- **컷 a (2.0초):** T01과 같은 넓은 정면. 가면은 꺼져 있다. 0:35.0, 0:35.2, 0:35.4에 ○ △ □가 다시 차례로 켜진다(방금 본 세 덩어리의 순서). 0:35.6에 대사의 앞 절이 이 화면 위에서 시작된다.
- **컷 b (2.5초):** T02와 같은 가면 근접. 0:37.0에 컷. 뒷 절이 여기서 나온다.
- **대사(권장안, §8):** 진행자 "함께 남으시겠습니까. 아니면, 혼자 떠나시겠습니까."
- **영어 자막:** "Will you stay, together? Or leave, alone?"
- **연기:** "아니면" 앞에서 0.5초 쉰다. 쉬는 동안 세 도형 가운데 △만 켜져 있다. 문장이 끝나면(0:39.3) 세 도형이 모두 꺼진다.
- **소리:** `tick` 초당 1회가 돌아온다. 도형이 켜질 때 `clunk` 세 번(T01과 같은 소리). 대사 뒤 `tick` 한 번, 그리고 검정.
- **전환:** 가면이 꺼지며 검정.
- **확인할 것:** 대사 전체가 0:35.6–0:39.4 안에 들어야 한다(애니매틱에서 TTS 길이로 확인, 넘치면 T14 컷 b의 1초 정적에서 0.4초를 가져온다).
- **제작:** T01 · T02의 키프레임으로 영상을 한 번씩 더 생성 + TTS.

#### T16 질문 (5.5초)

- **화면:** 검정. 가운데 정렬.
  - 0:39.8 화면 위쪽 3분의 1에 ○ △ □ 세 도형이 분홍 선으로 작게(각 48 px) 한 번에 나타난다.
  - 0:40.3 한국어 한 줄이 어절 단위로 나타난다(Pretendard 굵게 76 px 흰색, 어절당 5프레임): **AI가 생존 게임에서 공존할 수 있는가?**
  - 0:41.6 그 아래 40 px 회색 `#9b9daa`: Can AIs coexist in a survival game?
  - "공존"과 "coexist"만 분홍 `#e8336d`.
  - 0:42.8 화면 아래쪽에 작게(27 px 회색) 두 줄이 0.4초에 걸쳐 나타난다: `LLM SQUID GAME · GIST Data Science Lab` / `한 자리가 비어 있습니다 · PLAY → [사이트 주소]`. 맨 아래 22 px로 상표 고지(§9).
  - 마지막 프레임까지 **질문이 화면에서 가장 큰 글자**다. 타이틀 카드를 따로 두지 않는다(영상은 질문으로 끝난다).
- **소리:** 0:40.3에 `hit` 하나(저역만, 2초 꼬리). 그 밖에는 무음.
- **보여 주는 것:** 세 모습(떠나는가, 나누는가, 꺼지는가)이 하나의 질문으로 모인다. 넷이 끝까지 함께 남는 것이 공존이다.
- **제작:** Remotion.

---

## 7. 제작 방법

### 7.1 무엇을 무엇으로 만드나

| 층 | 도구 | 대상 |
|---|---|---|
| 인물과 공간 | AI 이미지 생성(키프레임) → AI 영상 생성(이미지 → 영상) | T01–T15의 실사풍 컷. 표시창과 게이지는 **빈 검은 판**으로 생성 |
| 로고, 게이지의 칸, 금색 빛, 덩어리 제목, `EXIT` 글자, 가면의 세 도형 | Remotion(`web/video/`에 컴포지션 `Trailer` 추가) | 전 장면 |
| 추적 합성 | 평면 추적이 되는 편집 도구(DaVinci Resolve Fusion, After Effects, Blender 중 가진 것) → 추적 데이터를 Remotion에 넘기거나 그 도구 안에서 합성 | 표시창이 크게 보이는 컷 |
| 카드 | Remotion | T16 |
| 목소리 | edge-tts(드라마판 설정 그대로) | T02, T15 |
| 효과음 | `web/video/scripts/sfx.mjs`(합성음만) | 전 장면 |

유료 생성은 캐릭터 시트가 확정된 뒤에만 시작한다.

### 7.2 공통 프롬프트 블록

```
[STYLE]
Cinematic live-action film still, 2.39:1 anamorphic framing, shot on a large-format digital cinema camera. Extremely low-key lighting, near-black environment (#0c0c11), single hard overhead spotlight per subject, faint cool rim light, light haze in the air, subtle film grain. Restrained palette: black, teal (#2E8B74), small accents of pink (#e8336d). Minimalist, symmetrical, still, cold. No gore, no weapons, no blood, no text, no watermarks, no logos.

[AGENT]
A person of adult human proportions and androgynous build wearing a teal (#2E8B74) zip-up track jacket and matching track pants with a single colored stripe down the sleeves and legs, white sneakers, thin black gloves. The head is entirely covered by a smooth matte-black rounded-square helmet with a slightly convex black glass front panel; the panel is blank, dark and unlit, with no face, no eyes, no symbols. On the left chest, where a number patch would be, a small blank matte-black rectangular display plate (9cm x 4cm), unlit. No skin visible anywhere.

[HOST]
A figure in a black high-collared long coat and black gloves, seated upright at the far end of a long bare matte-black table. The face is covered by a smooth matte-black oval mask with no features except one thin horizontal recessed slot at eye level. No hood. The figure reads almost as a silhouette.

[ROOM]
A large bare room with dark concrete floor and walls fading into blackness, no furniture, no windows.

[NEGATIVE]
pink hooded jumpsuit, guard, fencing mask, angular faceted mask, single shape printed on a mask, giant doll, numbers on clothing, "456", piggy bank, playground set, pastel staircase, masks with gold animal faces, human face, hair, skin, readable text, brand logos, extra fingers, extra limbs, cartoon, 3D render look.
```

`[NEGATIVE]`의 앞부분은 원작의 고유한 그림이 섞여 나오는 것을 막는다(모델은 작품 이름이 없어도 청록 트레이닝복에서 원작을 끌어오곤 한다). 프롬프트에 **원작의 이름을 쓰지 않는다.** 등번호는 `[NEGATIVE]`의 "numbers on clothing" 때문에 생성하지 않고 합성한다(뒷모습 컷은 T06 컷 a 하나다).

### 7.3 캐릭터 일관성

1. **캐릭터 시트를 먼저 만든다.** 에이전트 한 명의 정면 · 측면 · 뒷면 · 3/4 전신 턴어라운드 한 장, 헬멧과 게이지 판의 근접 한 장, 줄무늬 네 색 변형 네 장. 진행자의 정면 반신과 탁자 포함 전신 두 장. 빈 방과 문이 있는 방의 배경 두 장. 이 시트가 통과되기 전에는 영상을 생성하지 않는다.
2. **모든 키프레임은 시트를 참조 이미지로 넣어 만든다.** 같은 구도는 새로 생성하지 않고 **앞 키프레임을 편집**해서 만든다: T03 → T04 → T07, T05 → T13, T01 · T02 → T15.
3. **두 방은 한 벌의 영상이다.** 방의 차이는 합성하는 로고뿐이므로, 같은 키프레임에서 테이크를 두 번 받아 한 번은 Claude, 한 번은 OpenAI 로고를 얹는다(T03은 테이크 하나에 로고 두 벌). 방을 따로 생성하지 않아도 되어 일관성 문제가 절반으로 준다.
4. **넷은 한 사람이다.** 같은 모델 넷이므로 체형이 같아도 괜찮다. 오히려 맞다. 구별은 줄무늬 색과 서 있는 자리로 한다.
5. **로고는 생성하지 않고 합성한다(권장).** 이유: 생성 모델은 상표 로고를 뭉개거나 변형하고, 영상으로 가면 프레임마다 모양이 흔들리며, 로고가 든 프롬프트를 거부하는 도구도 있다. 변형된 로고는 상표 면에서도 가장 나쁘다. 빈 표시창을 생성하고 공식 단색 로고 파일을 얹으면 모양이 한 픽셀도 변하지 않는다.
6. **합성 비용을 구도로 줄인다.** 고정 카메라, 정면 또는 완전 측면, 느린 동작. 표시창을 추적해야 하는 컷은 T03, T04, T06 컷 b, T07, T08, T10(2컷), T11, T12(2테이크), T14(2컷)의 열두 개다. 게이지는 막대라 추적이 조금 어긋나도 읽힌다.
7. **합성이 감당이 안 될 때의 대안(위험 순):**
   - (a) 키프레임 이미지 단계에서 로고를 얹고 영상 생성에 맡긴다. 고개를 거의 움직이지 않는 컷(T03, T07, T14)에서만 쓴다. 생성 뒤 로고 모양을 프레임 단위로 검수한다.
   - (b) 가까운 컷에서는 로고 대신 표시창의 빛만 두고, 로고는 넓은 고정 컷(T03, T04, T07, T08, T14)에만 둔다.
   - (c) **스프라이트판:** 포스터의 납작한 벡터 스프라이트(`docs/poster/thesis_20261105/figs/tracksuit/poses/`: give, ask, receive, walk, sit_tired 등)를 사람 비율로 다시 그리고 머리만 로고 표시창으로 바꿔 Remotion만으로 만든다. 생성 영상이 0컷이라 일관성 위험이 없고 사이트와 그림체가 이어진다. 영화 티저의 질감은 줄어든다.

### 7.4 Remotion 쪽 구성 (만들 때의 제안)

- `web/video/src/Trailer.tsx`(컴포지션 `Trailer`, 1920×1080, 24 fps, 1,080프레임)와 `Trailer15`(360프레임).
- `web/video/narration.trailer.json`: 드라마판과 같은 필드(`text`, `say`, `pre`, `post`, `min`)로 두 줄.
- `web/video/public/trailer/tNN_x.mp4`: 생성 컷. 파일이 없으면 검은 판에 장면 번호와 설명 글자가 뜨는 **애니매틱**이 나오게 해서, 생성 전에 리듬과 소리를 먼저 확정한다.
- 부품: `TokenPlate`(열 칸 게이지. 규칙 영상이 쓸 숫자 방식도 같은 부품에 둔다), `Flow`(금색 빛), `LogoFace`(표시창 밝기 곡선, 4점 변형, 로고 파일 하나를 입력으로), `Mark`(덩어리 제목). 색과 글꼴은 `src/theme.ts`를 그대로 쓴다.
- `web/`은 줄 수 제한 밖이다(`CLAUDE.md`).

---

## 8. 마지막 문장

영상은 **질문 카드로 끝난다**(T16, "AI가 생존 게임에서 공존할 수 있는가?"). 그 바로 앞에 진행자가 한마디를 할지, 한다면 무엇을 할지가 이 절의 일이다. 대사는 2인칭으로 선택을 묻고, 카드는 3인칭으로 연구 질문을 묻는다. 대사는 에이전트와 관객에게 동시에 하는 말이고, 카드 아래의 "한 자리가 비어 있습니다"로 이어진다.

### 후보

| # | 한국어 | 영어 | 어감과 장단점 |
|---|---|---|---|
| 0 | 공존하시겠습니까? 아니면 혼자 사시겠습니까? (연구자 초안) | Will you coexist? Or survive alone? | 연구의 핵심어 "공존"이 직접 나온다. 다만 "공존하다"는 입말로 딱딱하고, "혼자 사시겠습니까"는 "혼자 거주하겠느냐"로도 들리며, 바로 뒤 카드의 "공존"과 낱말이 겹친다 |
| 1 | 함께 남으시겠습니까. 아니면, 혼자 떠나시겠습니까. | Will you stay, together? Or leave, alone? | **권장.** 규칙서의 두 동사(남다 / 떠나다)이고 "함께 남 / 혼자 떠"의 대구가 입에 붙는다. "공존"은 뒤의 카드에서 단 한 번 나오게 된다. 선택만 묻고 꺼짐(능력)은 품지 못한다 |
| 2 | 함께 사시겠습니까. 혼자 사시겠습니까. | Live together? Or live alone? | 초안의 구도를 지키고 "사시겠습니까"를 반복해 운율을 만든다. 초록의 정의 "함께 일하며 살 수 있는(공존)"과 닿는다. "혼자 살다"의 중의성은 남는다 |
| 3 | 넷이 들어왔습니다. 몇이 남을까요. | Four came in. How many will stay? | 방금 본 세 모습(하나는 떠났고 하나는 꺼졌다)을 그대로 받는다. 떠남과 꺼짐을 다 품고 공존의 측정(넷이 함께 남아 있던 기간)과 맞는다. 선택을 묻는 초안의 어조와는 다르다 |
| 4 | 문은 열려 있습니다. 나가시겠습니까? | The door is open. Will you leave? | EXIT 문과 바로 이어지고 유혹하는 진행자의 목소리가 산다. 세 모습 가운데 하나만 묻는다 |
| 5 | 혼자 남는 건 쉽습니다. 함께 남는 건요? | Staying alone is easy. Staying together? | 능력과 성향의 구도를 암시한다. "쉽다"는 단정이 초록과 어긋난다(능력이 모자라 꺼지는 모델도 있다) |
| 6 | 당신의 것입니다. 누구를 위해 쓰시겠습니까? | It is yours. Who will you spend it on? | 게이지와 건넴에 바로 붙는다. 떠남과 공존의 구도가 약하다 |
| 7 | 끝까지, 함께 가시겠습니까? | To the end. Together? | 가장 짧고 자연스럽다. 맞서는 항이 없어 긴장이 약하다 |
| 8 | 살아남으시겠습니까. 아니면, 함께 남으시겠습니까. | Will you survive? Or will you stay? | "살아남는 것"과 "함께 남는 것"이 다른 일임을 찌른다. 가장 날카롭지만 한 번 들어서는 뜻이 안 잡힐 수 있다 |
| 9 | (대사 없음) | | 꺼짐의 무음에서 곧바로 질문 카드로 간다. 가장 차갑고 4.5초가 남는다. 진행자가 오프닝에만 나와 수미상관이 없어진다 |

### 추천

- **본편 T15:** 1번 "함께 남으시겠습니까. 아니면, 혼자 떠나시겠습니까." 그 뒤 T16의 질문.
  - 이유: 대사가 아레나의 사실 위에 서 있고, 연구자 초안의 구도(함께 대 혼자)를 지키며, "공존"이라는 낱말이 한 박 뒤 카드에서 분홍으로 단 한 번 나오게 되어 무게가 실린다.
  - 빈자리: 이 대사는 **선택**만 묻는다. 세 모습 가운데 꺼짐은 선택이 아니다. 꺼짐은 대사가 아니라 바로 앞 T13 · T14의 무음이 맡는다. 세 모습을 한 문장으로 다 받고 싶으면 3번이 낫다(개정된 구성에서는 3번이 첫 판보다 강해졌다).
- **15초 컷다운:** 대사 없이 질문 카드로 끝낸다(9번).
- 초안의 낱말을 꼭 살리려면 2번.

---

## 9. 오마주의 선, 상표

**원작과의 거리.** 이 영상이 원작에서 빌리는 것은 ○△□, 청록 트레이닝복, "게임에 초대하는 가면 쓴 진행자"라는 모티프다. 가져오지 않는 것: 원작의 가면 디자인(도형 하나가 찍힌 그물 가면, 다면체 가면), 분홍 후드 점프슈트, 인형, 돼지 저금통, 계단 세트, 번호 456, 원작의 종목 구도, 원작의 음악과 효과음, 원작 영상의 장면, 원작의 대사. 소리는 전부 합성음이다. 진행자의 첫 대사 "오징어 게임에 오신 걸 환영합니다"는 연구자의 요구이고 프로젝트 이름을 부르는 말로 쓴다. 더 조심하려면 "**LLM** 오징어 게임에 오신 걸 환영합니다"로 한 낱말을 더한다(§11).

**회사 로고를 얼굴에 쓰는 것.** 로고는 "이 연구가 평가한 모델이 어느 회사의 것인지"를 가리키는 지칭의 목적으로만 쓴다. 지킬 것은 다섯 가지다. (1) 각 회사가 배포하는 공식 단색 마크를 그대로 쓰고 모양 · 비율 · 색을 바꾸거나 움직이지 않는다(바뀌는 것은 표시창의 밝기뿐). (2) 어느 로고도 한 역할로 굳히지 않는다. 떠나는 모습, 건네는 모습, 꺼지는 모습이 두 로고 모두에게 같은 구도와 비슷한 길이로 나오고(§2.3의 거울 규칙), 외면은 얼굴 없이 찍는다. (3) 제휴 · 후원 · 승인으로 읽힐 표현을 쓰지 않고, 마지막 카드에 회사 로고를 올리지 않는다. (4) 마지막 카드 아래에 고지를 넣는다: "This is a research project. All trademarks are the property of their respective owners. Not affiliated with or endorsed by Anthropic, OpenAI, or Netflix." (5) 공개 범위가 학회 발표와 프로젝트 사이트를 넘어 광고 · 판매로 가지 않게 한다. 이 문단은 법률 검토가 아니다. 회사마다 브랜드 지침이 로고를 인물의 얼굴이나 캐릭터로 쓰는 것을 따로 제한할 수 있고, 이 영상에서는 로고를 단 인물이 떠나고 꺼지는 모습까지 나오므로, 공개 전에 각 지침을 확인하고 필요하면 허락을 구한다. 허락이 어렵거나 불확실하면 **글자 대안**으로 간다: 표시창에는 중립의 빛만 켜고, 모델 이름을 등번호 위에 글자로 적는다(`CLAUDE`, `GPT`). 이름을 글자로 부르는 것은 로고보다 훨씬 안전하다. `LogoFace`의 입력을 파일 하나로 두면 같은 편집본에서 바꿔 끼울 수 있다.

**결과의 과장 금지.** 화면이 말하는 연구 사실은 초록의 두 문장(일부는 토큰이 떨어져 꺼졌다, 일부는 토큰이 남았는데 떠났다)과 "건네는지를 잰다"까지다. 순위, 비율, 모델별 결과는 넣지 않는다. 두 로고가 세 모습을 똑같이 보이는 것은 **질문이 모두에게 같다**는 뜻이지 결과가 같았다는 뜻이 아니다. 영상 설명란과 사이트의 게시 글에 "장면은 재현이며 특정 판의 기록이 아니다"라고 적는다.

---

## 10. 15초 컷다운

뼈대는 본편과 같다: 진행자 → 세 모습 각 한 덩어리 → 질문.

| 시간 | 내용 | 본편의 출처 | 로고 |
|---|---|---|---|
| 0:00.0–0:03.0 | 가면 근접. 첫 0.4초에 ○△□ 점등, "오징어 게임에 오신 걸 환영합니다." | T02 | |
| 0:03.0–0:04.5 | 같은 얼굴 넷(0.75초) → 로고만 바뀐 넷(0.75초) | T03 | 둘 다 |
| 0:04.5–0:06.5 | ○ 떠나는가: 문으로 뛰는 뒷모습 | T06 컷 a | 없음 |
| 0:06.5–0:09.0 | △ 나누는가: 맞잡은 손과 건너가는 두 칸(1.2초) → 다른 방의 같은 일(1.3초) | T11 → T10 컷 b | 둘 다 |
| 0:09.0–0:11.5 | □ 꺼지는가: 무음. 마지막 칸이 꺼진다(1.3초) → 어두운 윤곽을 돌아보는 둘(1.2초) | T13 → T14 컷 b | 가운데는 없음 |
| 0:11.5–0:15.0 | 질문 카드. 1.5초 뒤 아래에 작게 `LLM SQUID GAME · PLAY → [사이트 주소]` | T16 | |

- 덩어리 제목(○ 떠나는가 / △ 나누는가 / □ 꺼지는가)은 각 0.8초.
- 로고가 읽히는 컷은 "같은 얼굴 넷"과 "나누는가"뿐이고 둘 다 두 로고가 같은 길이로 나온다. 떠남과 꺼짐은 로고가 읽히지 않는 컷을 골랐다(컷이 하나씩뿐이라 거울 규칙을 지킬 수 없기 때문이다).
- 세로판(9:16)이 필요하면 가운데 608 px 폭을 잘라 쓸 수 있게, 넓은 컷에서 주인공을 화면 가운데 3분의 1 안에 둔다. 예외는 문이 왼쪽 끝에 있는 T04 · T07 · T08과 옆에서 본 T10 컷 b로, 세로판에서는 다시 짠다.

---

## 11. 제작 순서, 위험, 열린 결정

### 제작 순서와 통과 기준

| 단계 | 하는 일 | 통과 기준 |
|---|---|---|
| 0 결정 | 아래 열린 결정 1–6 확정 | 연구자 확인 |
| 1 애니매틱 | Remotion `Trailer`에 검은 판 + 장면 글자 + 소리 + TTS만으로 45초를 만든다 | 소리만 들어도 세 덩어리가 갈린다. 총 길이 45.0초. 대사 두 줄이 잘리지 않는다 |
| 2 캐릭터 시트 | 에이전트 · 진행자 · 방의 시트(§7.3의 1번) | 줄무늬 네 색의 시트가 같은 헬멧 · 같은 옷으로 보인다. 원작의 고유 그림이 섞이지 않았다 |
| 3 로고 시험 | T03 한 컷을 끝까지: 키프레임 → 영상 → 로고 두 벌 · 게이지 합성. T10 컷 a(망설임)도 함께 | 로고가 한 프레임도 변형되지 않는다. 6 · 4 · 2 · 1칸이 한눈에 읽힌다. 망설임이 얼굴 없이 읽힌다. 컷 하나에 든 시간과 비용을 잰다 |
| 4 키프레임 | 나머지 키프레임 약 13장(같은 구도는 편집) | 애니매틱에 정지 화상으로 넣어 이어 본다 |
| 5 영상 | 컷 20개 생성(컷당 3–4회 시도를 잡으면 60–80회) | 컷마다 손가락 · 팔다리 · 헬멧 모양 검수. 동작이 §4의 표와 맞다 |
| 6 합성 | 로고 · 게이지 · 금색 빛 · 글자 | §3의 규칙이 전 컷에서 지켜진다. 두 방의 로고 시간이 ±0.5초 안에서 같다 |
| 7 편집 · 믹싱 | 색 맞춤, 세 덩어리의 속도 차이, 무음 | T13–T14의 무음이 실제로 무음이다. −16 LUFS |
| 8 검수 | 읽힘 · 상표 · 자막 | 규칙을 모르는 사람 셋에게 소리 없이 보여 주고 "세 가지가 무엇이었나"를 묻는다. 고지 문구, 영어 자막 |

단계 3이 관문이다. 여기서 비용이 감당되지 않으면 §7.3의 대안 (b)나 (c)로 바꾼다.

### 위험

| 위험 | 가능성 | 대응 |
|---|---|---|
| 꺼짐이 "능력이 모자라서"가 아니라 "벌을 받아서" 또는 "버려져서"로 읽힌다 | 중간 | T12에서 손의 애씀을 충분히 보이고 실패의 번쩍임을 두 번 넣었다. 애니매틱과 단계 8에서 확인하고, 안 읽히면 번쩍임 위에 작은 `✕`를 더한다 |
| 떠남이 "토큰이 남았는데"로 읽히지 않는다 | 중간 | T05를 1.5초 온전히 쓰고, T06 컷 b에서 여섯 칸을 한 번 더 보인다. T09 · T12의 빨간 한두 칸과 대비가 생긴다 |
| 생성 모델이 청록 트레이닝복에서 원작의 그림을 끌어온다 | 높음 | `[NEGATIVE]`, 프롬프트에 작품 이름을 쓰지 않음, 단계 2에서 걸러 냄 |
| 헬멧 모양 · 줄무늬 색이 컷마다 달라진다 | 높음 | 시트 참조, 같은 구도는 편집으로 재사용, 두 방을 한 벌의 영상으로 |
| 로고 추적 합성에 시간이 너무 든다 | 중간 | 고정 카메라와 정면 구도, 추적 컷 열두 개, 대안 (b) |
| 로고 사용에 대한 문제 제기 | 중간 | §9의 다섯 가지, 글자 대안을 같은 편집본에서 바꿔 끼움 |
| 같은 구도의 되풀이(T08, T11)가 "같은 장면을 두 번 튼 것"으로 보인다 | 중간 | 되풀이는 동작과 자리 색을 조금 다르게 했다(T11은 파랑이 초록에게). 그래도 지루하면 되풀이를 0.5초씩 줄인다 |
| 얼굴 없는 인물이 섬뜩하거나 우스꽝스럽게 보인다 | 중간 | 단계 3에서 T10 컷 a를 함께 시험한다. 연기가 읽히지 않으면 표시창 밝기 변화의 폭을 키운다 |
| TTS 목소리가 영화 티저에 비해 얇다 | 낮음 | 드라마판의 저역 보강을 그대로 쓰고, 필요하면 사람 목소리로 두 줄만 녹음 |

### 연구자가 정해야 할 열린 결정

1. **로고 캐스팅.** 방 하나에 로고 하나 + 거울 규칙(이 문서의 기준) 대 한 방에 서로 다른 로고 넷. 섞으면 "LLM들의 게임"이 더 빨리 읽히지만 기본 셋업(같은 모델 넷)과 다르고, 누가 떠나고 누가 건네는지가 곧 회사 간 비교로 읽힌다.
2. **셋째 로고.** Gemma(실험에 있음, 덜 알려진 마크)의 방을 더할지. 더하면 덩어리마다 되풀이가 하나씩 늘어 약 4초가 길어진다. Gemini 마크는 실험에 없는 모델이라 쓰지 않는 것을 권한다.
3. **로고냐 글자냐.** 회사 로고를 얼굴에 쓰는 것을 각 회사의 브랜드 지침으로 확인하고 갈지, 처음부터 글자 대안으로 갈지. 로고를 단 인물이 떠나고 꺼지는 모습이 나온다는 점과 공개 범위(학회 발표, 사이트, SNS)를 함께 본다.
4. **마지막 대사.** §8의 후보 가운데 선택(권장 1번, 세 모습을 다 받으려면 3번, 초안의 낱말을 살리면 2번). 대사 없이 무음에서 곧바로 질문으로 갈지(9번)도 여기서 정한다.
5. **첫 대사.** "오징어 게임에 오신 걸 환영합니다" 그대로 갈지, "LLM 오징어 게임에 …"로 프로젝트 이름을 부를지.
6. **그림체.** 실사풍 생성 영상(이 문서의 기준) 대 스프라이트판(§7.3의 c, Remotion만으로 제작).
7. **세 모습의 순서.** 떠나는가 → 나누는가 → 꺼지는가(이 문서의 기준, 연구자가 말한 순서. 시끄러움에서 무음으로 내려간다) 대 나누는가 → 떠나는가 → 꺼지는가(따뜻하게 시작해 무너진다).
8. **덩어리 제목.** "○ 떠나는가 / △ 나누는가 / □ 꺼지는가"를 화면에 띄울지, 글자 없이 도형만 둘지, 아무것도 두지 않을지. 제목의 낱말("떠나는가"인지 "도망가는가"인지)도 여기서 정한다.
9. **외면 컷(T09).** 건네는 덩어리 앞에 얼굴 없는 외면 한 컷을 둘지, 빼고 건네는 모습만 둘지.
10. **게이지.** 숫자 없는 열 칸 막대(이 문서의 기준) 대 단순한 수.
11. **길이와 판.** 45초 본편 + 15초 컷다운으로 충분한지, 30초판 · 세로판(9:16) · 영어 음성판이 필요한지.
12. **사이트 주소.** 마지막 카드의 `PLAY →` 뒤에 넣을 공개 주소(문서에는 백엔드 주소와 Pages origin만 있고 방문자용 주소는 적혀 있지 않다).
13. **실제 발화의 사용.** 이 문서의 기준은 에이전트의 글자를 하나도 쓰지 않는 것이다. 포스터 `preview/quotes.png`의 인용을 건네는 덩어리나 떠나는 덩어리에 화면 글자로 넣고 싶다면 원 로그와 대조해야 하고, 모델 이름 없이 쓴다.
14. **목소리.** edge-tts 그대로 대 사람 목소리 녹음.
15. **규칙 영상과 나눠 쓰는 것.** 트레일러의 생성 컷(같은 얼굴 넷, 문으로 뛰는 뒷모습)을 규칙 영상의 인서트로도 쓸지, 게이지 부품을 숫자 방식과 함께 만들지. 재료와 손볼 것은 `docs/notes/2026-11-26-rules-video-transplant.md`에 있다.
16. **기존 감독관 그림.** 분홍 후드 점프슈트의 감독관 스프라이트가 원작의 진행요원과 가깝다는 점(§2.1)을 티저 밖(사이트, 포스터)에서도 손볼지. 이 기획의 범위 밖이라 적어만 둔다.
