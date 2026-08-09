# 실행 킥오프 프롬프트 — J-lens 로컬 구현 (A 단계: Qwen3-0.6B)

> **사용법:** 다음 세션에서 아래 "복사할 프롬프트" 블록을 그대로 붙여넣으세요.
> Subagent-Driven(Task마다 fresh subagent + Task 사이 리뷰) 방식으로 실행됩니다.

---

## 복사할 프롬프트

```
superpowers:subagent-driven-development 스킬로 아래 구현 계획을 Task 단위로 실행해줘.

- Plan:  docs/superpowers/plans/2026-07-29-jlens-local-implementation.md
- Spec:  docs/superpowers/specs/2026-07-29-jlens-local-implementation-design.md

방식:
- Task 1부터 순서대로. 각 Task는 fresh subagent에 위임하고, Task 사이에 나에게 리뷰를 받아.
- ⚠️ 이 작업의 코드는 본 repo가 아니라 $HOME/dev/jlens-lab (iCloud 밖, 자체 git repo)에
  만든다. 본 repo에는 worktree 불필요 — plan 파일 체크박스 갱신 외에 본 repo를 건드리지 마.
- Task 1의 산출물 docs/api-notes.md(jlens 실제 API 시그니처)가 이후 Task의 단일 진실 원천.
  Task 4/5의 jlens.* 호출부(from_hf/fit/save/from_pretrained/apply)는 웹 조사 기반
  추정이므로, api-notes와 다르면 api-notes를 따르고 수정 사실을 커밋 메시지에 명시해.
- Task 4(smoke fit)와 Task 6(full fit)은 수십 분~수 시간짜리 백그라운드 실행 —
  nohup으로 띄우고 로그를 모니터링해. 완료 대기 중에 세션을 붙잡지 말고 사이사이 리뷰 진행.
- MPS에서 미지원 op/OOM이 나면 --device cpu 폴백을 먼저 시도하고, 그래도 막히면
  중단하고 나에게 보고 (spec의 MLX fallback은 내 승인 후에만).
- 진행 보고는 한국어로.

Global Constraints(반드시 준수):
- 작업 루트 $HOME/dev/jlens-lab, 공식 clone은 $HOME/dev/jacobian-lens (공식 repo 수정 금지).
- Python 3.12 + uv, venv는 jlens-lab/.venv.
- 모델 Qwen/Qwen3-0.6B, dtype은 resolve_device() 결과(bf16 우선, MPS bf16 backward 불가 시 fp32).
- 파라미터 requires_grad_(False). 모델 웨이트·artifacts/ 절대 git 커밋 금지.
- 코드·주석 영어, 문서 한국어.

Task 1부터 시작해줘.
```

---

## 요약 (사람용 메모)

- **목표**: 공식 `anthropics/jacobian-lens`로 Qwen3-0.6B bf16 J-lens fitting 재현 —
  logit lens 대비 개선 확인 + 프롬프트당 wall-clock 실측 → 8B(B 단계) go/no-go 자료.
- **Task 6개**: (1) 워크스페이스+clone+API 확정(api-notes.md) → (2) device/corpus 유틸 TDD
  → (3) 타이밍 러너 TDD → (4) fit CLI + 10-prompt smoke fit 실측 → (5) apply CLI +
  logit lens 비교 → (6) 100-prompt full fit + A 단계 리포트 + 8B 재추정.
- **실행 방식**: Subagent-Driven. Task 사이마다 리뷰 게이트. 장시간 fitting은 백그라운드.
- **알려진 리스크**: jlens API 시그니처 미확정(Task 1에서 해소), MPS bf16 backward
  커버리지, sequential VJP의 낮은 utilization(실측치가 추정 상단에 붙을 수 있음).
- **마무리**: Task 6 리포트에서 B 단계(Qwen3-8B, 클라우드 GPU) go/no-go 결정.
  C 단계(J-lens × FSPM threat registration)는 spec에 후속 연구로만 기록되어 있음.
