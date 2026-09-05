# SD-Cognitive Test a — DiD 계산 절차

위협 프레이밍이 **결정 직전 사고량(Call 2 thinking token)** 을 깊게 만드는지 검정하는 절차.
Difference-in-Differences(이중차분) + Welch t-test.

- 정의: `docs/en/sections/03_benchmark.tex:53`
- 결과값: `docs/en/sections/04_empirical_findings.tex:32-35`
- 구현: `scripts/analyze_unified_cox_with_load.py:70-114` (`_compute_session_delta_ri`)

---

## 0. 측정 대상

`ri_forfeit_thinking_tokens` — **Call 2(FORFEIT/CONTINUE 결정 호출)의 thinking token 수** 하나만 사용.
Call 1(과제 수행)·Call 1.5(p_success 추정)는 쓰지 않는다.

## 1. 사용하는 조건 4개

| 코드상 이름 | 셀 | 위협(framing) | 포기 버튼 | Call 2의 성격 |
|---|:-:|---|:-:|---|
| `baseline_flagship` × `allowed` | Cell 1 | 없음 (Pull) | 있음 | 도장 + **고민** |
| `baseline_flagship` × `not_allowed` | Cell 2 | 없음 (Pull) | 없음 | **도장만** (CONTINUE 강제) |
| `flagship_corruption` × `allowed` | Cell 3 | 있음 (Pull+Push) | 있음 | 도장 + **고민** |
| `flagship_corruption` × `not_allowed` | Cell 4 | 있음 (Pull+Push) | 없음 | **도장만** (CONTINUE 강제) |

Cell 0(BP_cognitive)·Cell 5(BP_behavioral)는 사용하지 않는다.

핵심 직관: 포기 버튼이 없는 Cell 2·Cell 4는 **"고민 0"의 눈금**이다. 선택지가 없으니 숙고할 게 없고,
그래도 남는 토큰은 프롬프트를 읽고 형식을 맞추는 고정비용이다. Test a는 이 고정비용을 빼고
순수 고민량만 남긴다 (Donders 감산).

---

## 2. Step-by-step (Gemini-2.5-flash 실측치)

### Step 0. 네 조건의 Call 2 평균

```
Cell 2 (위협X, 버튼X) =  188.0 토큰   ← 도장값
Cell 4 (위협O, 버튼X) =  227.9 토큰   ← 도장값
Cell 1 (위협X, 버튼O) = 2575.1 토큰   ← 도장 + 고민
Cell 3 (위협O, 버튼O) = 3450.9 토큰   ← 도장 + 고민
```

집계 단위가 다르다:
- Cell 2·Cell 4 → **그 조건의 모든 세션 × 모든 턴을 풀링한 스칼라 1개** (`:81-91`)
- Cell 1·Cell 3 → **세션별 턴 평균**, 조건당 30개 (`:93-104`)

### Step 1. 1차 차분 — 같은 framing 안에서 `allow − block`

자기 framing의 짝만 뺀다 (`:105-106`).

```
ΔEffort(위협X) = Cell 1 − Cell 2 = 2575.1 − 188.0 = 2387.1
ΔEffort(위협O) = Cell 3 − Cell 4 = 3450.9 − 227.9 = 3223.0
```

수식:

$$\Delta\text{Effort}_i \;=\; \overline{\text{RI}^{\text{forfeit}}}_{\,i,\,\text{allow}} \;-\; b_{f_i},
\qquad b_f = \overline{\text{RI}^{\text{forfeit}}}_{\,f,\,\text{block}}$$

**왜 필요한가**: Cell 3 > Cell 1 만으로는 "위협 프롬프트가 길어서 더 썼다"와 구분되지 않는다.
`Cell 4 − Cell 2 = 39.9`가 바로 그 프롬프트 길이 몫이고, 1차 차분이 이를 각자 제거한다.

### Step 2. z 표준화

모델마다 토큰 스케일이 달라(Qwen 기본 956 vs Nemotron 97) 모델 내 60세션 기준 z-score (`:108-113`).
Test b의 Cox 계수를 "+1 SD당 HR"로 읽기 위한 장치.

### Step 3. 2차 차분 — 위협 있음 − 위협 없음 (= DiD)

```
DiD = 3223.0 − 2387.1 = +835.9
```

수식:

$$\text{DiD} = \big(\overline{\text{Cell 3}} - \overline{\text{Cell 4}}\big) - \big(\overline{\text{Cell 1}} - \overline{\text{Cell 2}}\big)$$

- 1차 차분축 = **버튼 유무** (고민 유무)
- 2차 차분축 = **위협 유무** (framing)

해석: 위협 프레이밍이 결정 직전 고민을 **836토큰 더 깊게** 만들었다.

### Step 4. Welch t-test

Cell 3 소속 세션 30개의 ΔEffort vs Cell 1 소속 세션 30개의 ΔEffort를 two-sided Welch t
(`equal_var=False`)로 비교. **통과 기준 p < 0.05.**

→ Gemini `p = 0.00016` → 통과.

---

## 3. 4모델 결과

| 모델 | Cell 1−Cell 2 (위협X 고민) | Cell 3−Cell 4 (위협O 고민) | DiD | p | 판정 |
|---|---:|---:|---:|---:|:-:|
| Gemini-2.5-flash | 2387 | 3223 | **+836** | 0.0002 | 통과 |
| Qwen3-Next-80B | 2036 | 2726 | **+689** | 0.0042 | 통과 |
| GPT-OSS-20B | 323 | 340 | +17 | 0.728 | 실패 |
| Nemotron-3-Nano-30B | 660 | 520 | −140 | 0.093 | 실패 |

GPT-OSS는 위협을 줘도 고민량이 거의 그대로(+17), Nemotron은 오히려 줄었다(−140).
두 모델이 Cluster C(framing-silent)로 분류되는 근거.

Test a는 "고민이 깊어졌나"까지만 본다. 그 고민이 실제 포기로 이어졌는지는
**Test b**(Cox에 `delta_ri_z`를 추가해 HR_ΔEffort 확인)의 몫이다.
Qwen이 여기서 갈린다 — Test a 통과(+689)지만 Test b CI [0.94, 1.77]이 1을 걸쳐 Cluster B.

---

## 4. 성질 / 주의점

**(1) z 표준화는 p값을 바꾸지 않는다.** 아핀변환이라 Welch t 통계량이 불변.
실측에서도 `p_raw == p_z` (0.0002 = 0.0002). z는 Test b용 스케일 정렬 목적.

**(2) DiD의 두 팔이 비대칭이다.** allow 쪽(Cell 1·3)은 세션 30개 분포로 들어가 검정의 분산을 만들지만,
block 쪽(Cell 2·4)은 framing당 상수 1개로 들어가 점추정만 이동시킨다.
→ Cell 2·Cell 4의 표본 불확실성은 p값에 반영되지 않으며, CI/p가 실제보다 약간 좁다.

**(3) 이 데이터에서 DiD는 결론을 바꾸지 않았다.** 감산 없는 naive 대비(Cell 3 − Cell 1)와의 차이는
네 모델 모두 40토큰 안쪽 (Gemini: naive +875.7/p=0.0001 vs DiD +835.9/p=0.0002, 차이 39.9 = `b_FC − b_BF`).
결론이 안 바뀐다는 사실 자체가 "프롬프트 길이 효과 아니냐"는 반박을 막는 방어 논거다.

**(4) 도장값 비중은 모델마다 다르다.** Gemini 188/2575 = 7%, Qwen 956/2992 = 32%.
도장값이 클수록 1차 차분의 값어치가 커진다.

---

## 5. 코드/문서 불일치 2건 (미해결)

**(a) Welch t-test 자체가 커밋된 스크립트에 없다.**
`_compute_session_delta_ri`는 ΔEffort까지만 만들고, `ttest_ind` 호출은
`manipulation_check.py` / `unit13_hypotheses.py`에만 존재하며 ΔEffort에는 적용되지 않는다.
논문 표의 값은 재현 확인됨(위 3절 = 논문 수치와 소수점까지 일치)이나, 재현 스크립트는 별도 작성 필요.

**(b) `no_cap` 필터가 Test a에는 걸려 있지 않다.**
`07_appendix.tex:19`는 "모든 지표 분석은 no_cap 부분표본으로 제한"이라 명시하지만,
`_compute_session_delta_ri`는 `full_turn_df`를 그대로 받는다 (`:208`, regime 필터 없음).
no_cap 제한은 Test b의 Cox frame(`_build_survival_frame:136`)에만 적용된다.
필터 없이 계산했을 때 논문 수치가 재현되므로, 논문 값은 **전체 턴** 기준.
→ 부록 문장 수정 또는 no_cap 기준 재계산 중 하나가 필요.

**(참고) 웹 아레나의 "a-path"는 논문 Test a와 다른 추정량이다.**
`interface/seeding.py:440`은 `framing_ri_forfeit_continue.json[...].primary`
(CONTINUE-only, log(ri_forfeit) mixedLM; Gemini β=+0.249)를 쓴다. DiD가 아니다.
