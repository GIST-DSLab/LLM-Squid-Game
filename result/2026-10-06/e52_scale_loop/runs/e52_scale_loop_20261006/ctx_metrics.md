연구자가 모아 둔 협력 지표 보고서(10-06, 논문 11편 전문 정리)의 요지. **이 목록은 이미 널리 쓰이는 것**이다.
그대로 가져다 쓰는 것은 새로움이 아니다. 빌려 쓸 수는 있지만, 우리 아레나에서만 가능한 새 구조·새 지표를 내야 한다.

알려진 실패 (지표 하나로 잴 때):
- 협력만 배운 모델은 낯선 상대에게 착취당함 (Melting Pot: self-play 1.0 → 낯선 상대 0.1)
- 대회 1등은 협력이 필요 없는 판에서 점수를 벌었음 (Beyond the high score: base chance가 상하위를 가름)
- 똑똑한 모델이 협력을 안 함 (More Capable, Less Cooperative?: o3 완벽 플레이의 16.9%, 능력 자동화 94.9%, Arena Elo와 r=0.16)
- 평화로운 모델은 배신자에게 무방비 (Welfare Diplomacy: exploitability > 0, 전 모델)
- 평등 지표는 집단이 망해도 만점 (GovSim Equality 100 with 1개월 붕괴)
- 집단 보상은 게으른 구성원을 숨김 (Perolat 2017)
- Elo는 복제 모델로 조작됨 (Social choice 논문: 승률 0.9 → 0.631 예측)
- 평균 순위는 상대 구성이 바뀌면 뒤집힘 (CoopEval: 균등 집단 2위 → 진화 후 5위)

이미 쓰이는 지표·구조:
- 생존: GovSim survival time / survival rate
- 능력 분리: Competence Rate(상대 협력을 시스템이 보장), base chance ρ(협력 불필요 통제 게임)
- 협력 결과: 효율 u, 평등 1−Gini, 과용률 o, Melting Pot background per-capita return(외부효과), Nash welfare Π u_i
- 협력 과정: Shapley 기여 φ(리플레이로 한 명 빼기), Response Rate
- 협력 성향: Cooperation Rate(능력을 시스템이 대신), SODE Δ_reg(관대한 상대 − 착취 상대 협력률), ρ_drop(배신 직후 협력 감소),
  G_rep(평판 기울기), E_Ω(공개 − 비공개 협력률), Welfare Diplomacy exploitability E
- 합치기: 축 곱셈 결합 (S·I·C)^(1/3) (Beyond the high score의 non-compensatory 능력 모델)
- 판 집계: Deviation Ratings(CCE 기반 clone-invariant), Maximal Lotteries(VasE), 진화 Fitness(CoopEval replicator 1000 step)
- 실험 조건: 스크립트 배경 봇(무조건 협력/배신, TFT, ZD extortion), resident·visitor, 짝 조건 둘, 착취자·탐욕 신참 투입,
  공개·비공개 판, self-play와 cross-play 분리·제공사 균형
- 그래프: 능력×협력 사분면, Kaplan-Meier 생존 곡선, 공유 자원 궤적, 조건부 협력 프로필(평판 x), cross-play 히트맵,
  평균 대 진화 Fitness, Shapley 기여 대 보상 산점도, 포레스트 플롯, 복지×착취 산점도, 압박 강도 대 협력(Yerkes-Dodson 역U)
- 5.2 페이지의 기존 제안(부록 B): 개인 성과 x × 동료 기여 y + 파레토 앞줄, 얼린 패널 3자리 + focal 1자리(= Melting Pot
  focal/background), AG(2,4) 또래 리그, 가법(Shapley식) 테이블 효과 — 이것들도 "이미 있는 것"에 넣는다.
