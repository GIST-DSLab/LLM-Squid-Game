# Spec: J-lens (Jacobian Lens) 로컬 구현 — Qwen3 + HF transformers

- 작성: 2026-07-29, /office-hours 세션에서 승인된 설계를 spec으로 이관
- 원본: `~/.gstack/projects/llm-squid-game-ds-lab/bagjuhyeon-feat-how-to-play-gif-design-20260729-165153.md` (Status: APPROVED, 적대적 리뷰 2라운드 9/10)
- Status: APPROVED

## 목표

Anthropic의 J-lens(Jacobian Lens, "Verbalizable Representations Form a Global Workspace
in Language Models", Transformer Circuits 2026-07-06)를 로컬 환경에서 재현한다.
HuggingFace bf16 웨이트 + `transformers`/PyTorch로 activation을 추출하고 야코비안을
계산해, 각 층·위치에서 모델이 "verbalize할 준비가 된" 토큰을 읽어내는 도구를 확보한다.

핵심 수식:

```
J_ℓ = 𝔼[∂h_final,t' / ∂h_ℓ,t]          # source 위치 t, 이후 target 위치 t', 코퍼스 평균
lens(h_ℓ) = softmax(W_U · norm(J_ℓ · h_ℓ))
```

## 확정된 전제 (사용자 동의, 2026-07-29)

1. **학습 불필요** — fitting은 VJP(backward pass) 평균일 뿐, tuned lens류 최적화가 없다.
2. **Ollama 배제** — autograd 부재. HF `transformers` + PyTorch로 진행한다.
3. **공식 구현 기반** — `anthropics/jacobian-lens`(Apache 2.0, Qwen 데모, standalone
   PyTorch)를 기반으로 시작. 밑바닥 구현 금지.
4. **~100 프롬프트 × 128 토큰이면 usable** (repo 명시; 논문은 1,000 × 128).

## 채택 접근: A → B 단계적

- **A (이번 구현 범위)**: Qwen3-0.6B(필요시 1.7B) bf16으로 공식 repo 재현.
  ~10 프롬프트 smoke fit → ~100 프롬프트 full fit → slice 시각화를 logit lens
  베이스라인과 비교. MPS 동작 여부·프롬프트당 wall-clock 실측이 핵심 산출물.
- **B (A 실측 후)**: Qwen3-8B를 클라우드 GPU 1장에서 fitting. 코퍼스를 disjoint
  프롬프트 슬라이스로 나눠 병렬 fit 후 merge API로 평균 합산. fitted lens 아티팩트
  (층당 d² fp32, 총 ~2.4GB) 저장.
- **C (후속 연구, 이번 범위 아님)**: fitted lens로 Squid Game Call-2 forfeit reasoning
  프롬프트를 apply — threat 개념의 J-space 등록 여부 검증 (Cluster C 연결).

## 제약

- 로컬은 Apple Silicon Mac — CUDA 없음. MPS backward 가능하나 느림. MPS bf16
  backward op 커버리지 미확인(미지원 op 시 fp32 fallback → 메모리 2×).
- 작업 디렉토리는 **iCloud 밖** (git/venv/모델 캐시 성능 — iCloud git 이슈 기지사항).
- 본 repo(LLM-Squid-Game-DS-Lab)에 코드 침습 없음 — 별도 디렉토리에서 구현.
  spec/plan 문서만 본 repo에 둔다.
- 파라미터 `requires_grad=False` (weight grad 불필요), 야코비안 누산은 fp32.
- 대용량(모델 웨이트, fitted lens 아티팩트)은 git 커밋 금지.
- MLX 커뮤니티 포트(`WeZZard/jlens-qwen36`)는 MPS가 막힐 때만 fallback으로 검토.

## 연산량 추정 (A 단계에서 실측 검증)

프롬프트당 ≈ 4·P·T·d FLOPs (T=128). 비용은 d_model개의 VJP가 지배 — cotangent를
target 위치들에 합산하므로 output 차원당 backward 1회로 모든 층·source 위치의
야코비안 행을 동시 획득(층 수 L 거의 무관). backward ≈ 2×forward, ±3× 허용 추정:

| 모델 | d_model | 프롬프트당 | 100 prompts | 체감 |
|---|---|---|---|---|
| Qwen3-0.6B | 1024 | ~0.3 PFLOPs | ~30 PFLOPs | 4090 수십 분 / Mac 몇 시간 |
| Qwen3-1.7B | 2048 | ~1.8 PFLOPs | ~180 PFLOPs | 4090 ~1시간 |
| Qwen3-8B | 4096 | ~17 PFLOPs | ~1.7 EFLOPs | H100 1–2h, 4090 ~6h |

sequential batch-1 VJP는 utilization이 낮아 체감치가 상단에 붙을 수 있음(특히 MPS).
cotangent chunk 배칭이 1차 완화책. `apply()`는 forward 1회 + 층별 행렬곱으로 무시 가능.

## 성공 기준

1. Qwen3-0.6B(또는 1.7B)에서 walkthrough 재현 — 층×위치 slice 출력에서 초기~중간 층의
   해석 가능한 토큰이 logit lens 대비 개선됨을 확인.
2. 프롬프트당 fitting wall-clock 실측치 확보, 추정치의 ±3× 이내면 추정 모델 검증.
3. fitted lens 아티팩트 저장 + 임의 프롬프트 `apply()`가 수 초 내 동작.
4. 실측 기반 8B 시간·VRAM 재추정 → B 단계 go/no-go 판단 자료.

## 미해결 질문 (Task 1에서 해소)

1. `jlens` 실제 API 시그니처 (`jlens.from_hf` / `jlens.fit` / `apply` / `merge` —
   웹 조사 기반 추정이므로 walkthrough.ipynb로 확정 필요).
2. `.cuda()` 하드코딩 여부 → MPS 치환 지점.
3. 코퍼스: repo `data/experiments/` 재현 프롬프트셋을 기본값으로 사용.
