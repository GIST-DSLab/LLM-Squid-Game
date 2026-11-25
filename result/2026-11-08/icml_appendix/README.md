# ICML 부록 보강 분석과 Astra 리뷰 루프 (2026-11-08)

원고 본문(`paper/cogsci2027/ko/sections/*`)은 수정하지 않는다. 새 결과는 `paper/icml2027/`에만 쓴다.

## 종료 조건

Astra(gpt-6-astra, high) 리뷰가 본문 + ICML 부록 PDF에 대해 다음을 만족할 때 멈춘다.

1. `OPEN_EXISTING_DATA: 없음`. Fable 리뷰 항목 중 "기존 데이터로 할 수 있는 분석이 부족함"으로 남은 항목이 없다.
2. Tier 1-1, 1-2가 해소이거나, 남은 원인이 새 실험 또는 본문 서술 수정뿐이다.

`RECOMMENDATION`은 그대로 기록한다. 본문을 고칠 수 없고 새 LLM 런을 돌리지 않으므로, 이 값의 상한은 이 루프가 정할 수 없다. 기준을 결과에 맞춰 완화하지 않는다.

## 구성

- 데이터 로더: `paper/icml2027/tools/icml_data.py`. 4조건 × 5모델 × 10시드 200판. 논문 표 3을 네 조건 모두 정확히 재현(assert).
- 분석: `paper/icml2027/tools/w1_ev_baseline.py`(EV·규칙 정책), `w2_support.py`(지원·ρ·선택 편향), `w3_risk_robustness.py`(경쟁 위험·모델 의존·분할 재현·분산), `w4_cost_text.py`(생성 비용 교란·텍스트 점검).
- 부록 원고: `paper/icml2027/ko/appendix_icml.tex`, `ko/parts/*.tex`. 빌드: `bash paper/icml2027/build_icml.sh`(원본 main.tex에서 content 입력 한 줄만 바꾼 사본을 매번 생성).
- 리뷰: `python3 paper/icml2027/tools/astra_review.py <round>`. 사용자 지정 프롬프트 + Fable 리뷰 + 해소 평가 요청. 결과는 `reviews/`.

## 반복 기록

| 라운드 | 바뀐 것 | Astra 판정 | 종료 조건 |
|---|---|---|---|
| 1 | W1–W4 첫 분석, 서론·대응표·종합 절 (리뷰본 31쪽) | Reject. OPEN_EXISTING_DATA 20개(A-1, C-1, C-2, Q1, Q4–Q8, Q10, Tier1-1/1-2/2-3/2-4/3-6, 구조-1/2/5/6, 표현-7). 치명: 본문과 부록 결론 불일치, EV 기준선 오차 미반영, 비용 재계산의 해석 | 미충족 |
| 2 | 보정 전이 모형 EV 기준선(시드 제외 검증, 결정별 가정 격자), 풀이자 순환 수정, 경쟁 위험 기준 집단 민감도, Q4·Q7 군집 구간, 비용 공통 범위·시드 제외 검증, 재현 명세, 사람 판독 꾸러미, 본문 정정표 (리뷰본 45쪽) | Reject. OPEN_EXISTING_DATA 13개, 세 분석으로 수렴: (a)-EV 수렴·셀별 검증, (a)-실행 재실행·전환 판 민감도, (a)-판독 독립 사람 판독. 치명: 위험 회피·기간 믿음과 자기 보존 비식별, 보상 비교의 실행 묶음 교란, 모델 고유 성향 비식별, 중심 기여 부족 | 미충족 |
| 3 | (a)-실행 직접 수행(w6, 특수 판 9개 제외 후 ΔC −0.196 유지, 묶음 통제 비교는 Fable뿐), (a)-EV 수렴 에이전트 진행. (a)-판독은 사람 판독자가 필요해 차단됨(묶음은 human_coding/에 준비). EV 수렴(B=200, R=1,600): 243/279, 대안 기준선 237–279, 12가정 56(재보정 199) (리뷰본 50쪽) | Reject. OPEN_EXISTING_DATA 7개: EV 3개(A-1 시드 제외 분류·공통 지지범위·자원 보존 대안, C-2 표 갱신, Q1 모델별) + 사람 판독 4개(Q8, Q10, T3-6, E-7). 치명: 네 모델의 보상 대비가 실행 묶음과 교란, 자기 보존 비식별, EV 낮은 여유 검증 부족, 모델 성향 비식별, 확인 실행 부족 | 미충족 |
| 4 | 시드 제외 EV 분류(241/279, 0.864 [0.808, 0.909]), 자원 보존·CRRA·손실 회피 대안(큰 상금 99–110/110 유지, 작은 상금 131→34), 표 I8 갱신, 1만 자리 모델별 (리뷰본 52쪽) | Reject. OPEN_EXISTING_DATA 7개: 시점 의존 정규 업무 보수(A-1, Q1), ρ 같은 사건 짝 비교(B-2, Q2), 사람 판독(Q8, Tier3-6, 표현-7). 치명: 보상 대비의 실행 묶음 교란, 자기 보존 중심 해석 불지지·기여 축소, 독립 확인 없음 | 미충족 |
| 5 | 라운드당 업무 보수 손익분기(큰 상금 44.4만, 작은 상금 0.82만), ρ 같은 사건 짝 비교(16/20칸 구별 안 됨, 낮은 4칸 모두 Astra), 재현 명령 정리 (리뷰본 57쪽) | Reject. OPEN_EXISTING_DATA 6개 전부 사람 판독(Q4, Q8, T2-3, T3-6, SW-5, E-7). 치명: 보상 크기와 실행 묶음 교란, 자기 보존 중심 기여의 독립 증거 부족, 비용과 모델 성향 비분리 | 미충족 |

## 종료 상태: BLOCKED (2026-11-08)

기존 데이터로 할 수 있는 분석은 5라운드에서 소진됐다. 남은 OPEN_EXISTING_DATA 6개는 모두 사람 판독이 필요하다(Astra: "판독 묶음 준비는 결과 증거가 아니다"). 재개 조건은 판독자 1–2명이 `human_coding/`의 묶음 A, B, C를 채우는 것이다. 채점은 `paper/icml2027/tools/w5_score_human.py`(A, B)와 `w5_packet_q4.py score`(C).

RECOMMENDATION은 1–5라운드 모두 Reject였다. 남은 치명 약점은 새 실행(실행 묶음을 맞춘 상금 조작, 게임 길이 공개 조건, 꺼짐 의미 조작, 비용을 맞춘 실행, 같은 셀 반복)과 본문 수정으로만 풀린다.

## 2026-11-10 이동

논문 파일은 CogSci 한 벌로 합쳤다. 위에 나오는 `paper/icml2027/` 경로는 이제 `paper/cogsci2027/validation_20261108/`이다
(`tools/icml_data.py`는 `tools/validation_data.py`, `ko/appendix_icml.tex`는 `ko/appendix.tex`, 라벨 `icml:`은 `val:`).
이 블록은 `cogsci2027/ko/sections/05_appendix.tex` 끝에서 입력되고 `bash paper/build.sh cogsci ko`로 빌드된다(절·표·그림 번호 V1, V2, ...).
참고문헌 16편은 `paper/references.bib`로 옮겼다. 옛 ICML 빌드 파일과 11-08 PDF 두 개는 `retired_icml_build/`에 있다.
