# ICML 관점 독립 리뷰 — 2026-11-07

**Astra와 Fable 5.1 리뷰, 원문 대조, 통합 진단과 실험 계획을 완료했다. 새 실험은 실행하지 않았고 원고·엔진도 수정하지 않았다.**

- [두 리뷰 통합 및 지적의 검증](combined_review.md)
- [종료 조건과 비용 통제의 실험 계획](experiment_plan.md)
- [기존 50판의 L 구간별 소모율 표](analysis/token_cost_by_L.md)
- [Astra 리뷰 원문](reviews/astra_review.md): gpt-6-astra, high. Weak Reject.
- [Fable 5.1 리뷰 원문](reviews/fable51_review.md): claude-fable-5-1, high. Reject, 자체 점수 3/10. 사용자가 지정한 claude-irregular6612 런처.
- [Astra 수치 지적의 대조](astra_findings_audit.md), [동일 프롬프트](review_prompt.txt), [원본 명세](source_manifest.json), [진행 상태](review_status.json).

검토본은 paper/dist/ko_cogsci2027_2026-11-07_no_appendix.pdf의 20:36:39 생성본(9쪽)이다. reviewed_no_appendix.pdf는 같은 바이트의 보존 사본이며 SHA-256을 기록했다. 두 독립 디렉터리의 사본 및 원본과 해시가 같다.

각 리뷰는 저장소 밖에서 새로 만든 다음 디렉터리에서 진행했다. PDF·기계 추출 텍스트·페이지 이미지와 같은 프롬프트를 제공하고, 기존 대화·개인 메모리·저장소·상대 리뷰·외부 자료를 사용하지 않도록 지정했다.

- Astra: /private/tmp/icml-independent-20261107-qnlwb3gn/astra
- Fable: /private/tmp/icml-independent-20261107-qnlwb3gn/fable51

기본 Claude 계정의 첫 시도는 인증, 두 번째는 주간 한도로 실패했다. 사용자 지정 런처를 통한 세 번째 실행에서 Fable 리뷰를 실제 수신했다. 실패한 호출은 리뷰로 세지 않았다. 모델과 런처, 이벤트 기록은 evidence/에 있다.

소모율 분석은 현재 원고의 기본 v33 cohort 50판만 사용했다. 명시된 원시 이벤트 파일 10개의 해시, 기존 모델별 호출 수·평균, L<1의 풀이 19개를 확인했다. 모든 호출을 포함한 TALK 분모는 5,990이며 SOLVE는 386이다. 표의 기술통계는 호출 가중이며 독립 호출의 유의성 검정이 아니다. 분석 코드·원자료 위치·수치·검증 기록은 analysis/에 있다.
