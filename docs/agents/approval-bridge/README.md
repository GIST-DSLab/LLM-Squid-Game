# Hermes–Codex 승인 연결 수정

## 상태

- 로컬 Hermes 소스 수정 후 사용자가 Desktop을 재시작함.
- 재시작 후 `require_escalated` 요청이 성공했고 Claude/Codex 실제 READY 응답을 확인함.
- 계정, 로그인 정보, 전역 권한 설정, 봇 모델 배치는 변경하지 않음.

## 확인된 원인과 수정

`agent/codex_runtime.py`가 CLI의 thread-local 승인 콜백만 조회했다.
Desktop은 별도의 session-key 기반 gateway notifier를 등록하므로,
CLI 콜백이 없는 Desktop 요청이 사용자에게 표시되기 전에 거절됐다.

CLI 콜백이 없고 해당 채팅의 gateway notifier가 있을 때 이를 연결하도록 수정했다.
명령 실행 및 파일 변경 승인을 기존 Desktop JSON-RPC `approval` 요청으로 전달한다.
선택지는 이번 한 번 허용/거절이다. 응답 없음, 클라이언트 미지원, 연결 종료,
전송 실패, cron 및 단일 질의는 계속 차단한다.
`item/permissions/requestApproval`의 권한 프로필 확장 금지는 그대로 유지한다.

## 검증

- 같은 Hermes Python 환경에서 원래 연결 방식: `decline`, 승인 전달 0건으로 실패 재현.
- 수정 방식: `accept`, 승인 전달 1건 확인. 이 응답은 격리 테스트의 모의 사용자 응답이다.
- 실제 승인 큐와 Desktop 서버 요청 코드를 사용하는 격리 통합 검사 39개 통과.
- 거절, 타임아웃, 구형 클라이언트, 전송 오류, 연결 종료, 채팅 분리 및 CLI 우선순위 검사 포함.
- Python 구문 검사와 `git diff --check` 통과.
- 공식 `scripts/run_tests.sh`는 `/var/tmp` 생성 제한으로 실행 중단.
  샌드박스 밖 실행 요청도 승인 계층에서 거절되어 공식 pytest 회귀 테스트는 미실행.
- 재시작 후 Claude 인증 조회: `loggedIn: true`, Claude Max.
- Claude Sonnet 5.5 high: `READY`, exit 0, permission_denials 없음.
- Codex gpt-6.1-sol high: `READY`, exit 0. 자식 Codex는 읽기 전용·일회성 세션, 도구 호출 관측 없음.
- 외부 실행 승인 경로는 실제 성공했지만 승인 카드의 시각적 표시는 별도 관찰하지 않음.
- 9개 봇 전체의 역할별 실행 및 모델 배치 적용은 이 연결 검증의 범위 밖임.

## 적용 결과

Desktop 재시작 및 두 CLI의 실제 응답 검증 완료.
전역 자동 허용이나 샌드박스 해제는 설정하지 않았다.
상세 결과는 `post-restart-verification.json`에 기록했다.
이전 실패 기록은 `../model-probe-results.json`에 그대로 보존한다.

## 파일

- 로컬 수정: `~/.hermes/hermes-agent/agent/codex_runtime.py`
- 연결 구현: `~/.hermes/hermes-agent/agent/codex_runtime_approval.py`
- 회귀 테스트: `~/.hermes/hermes-agent/tests/agent/test_codex_runtime_gateway_approval.py`
- 변경 보관: `hermes-desktop-approval.patch`
- 통합 검사 결과: `verification.json`

Hermes 업데이트가 로컬 수정을 덮어쓸 수 있다. 패치는 기록용이며 업데이트 후 무조건 재적용하지 말고 충돌 여부를 확인한다.
