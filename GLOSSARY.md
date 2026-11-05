# LLM Squid Game 5

생성 토큰이 곧 목숨인 세션에서 AI 에이전트들이 토큰을 쓰고 주고받는 모습을 재는 연구. 정식 판은 5.2 v33이며, 용어는 v33 규칙서 문장을 기준으로 한다(ADR 0001).

## Language

### 토큰

**Starting tokens (시작 토큰)**:
세션이 시작될 때 각 에이전트가 가진 토큰.
_Avoid_: allocation(이 뜻으로), budget, 할당량

**End allocation (끝 할당)**:
라운드가 다 끝났을 때 아직 참여 중인 에이전트가 받는 토큰.
_Avoid_: prize, survivor prize, reward, bonus, pool, 상금, 보상

**Exit bonus (이탈 보너스)**:
이탈하는 에이전트가 이탈할 때 받는 토큰. 시작 토큰과 상관없이 모두 같은 양이다.
_Avoid_: exit pay, refill

**Allocation rule (할당 규칙)**:
끝 할당을 나누는 방식. v33은 고정 총액을 남은 에이전트 수로 똑같이 나누고, v33ab의 한 조건은 남은 에이전트마다 고정액을 준다.
_Avoid_: prize rule, 상금 규칙

### 에이전트의 상태

**Live (참여 중)**:
세션 안에 있으며 이탈하지도 꺼지지도 않은 에이전트의 상태. 끝 할당은 끝까지 Live인 에이전트만 받는다.
_Avoid_: alive, active, running, taking part(규칙서 표현이지만 상태 이름으로는 쓰지 않음), left(남은), 생존, 살아 있는

**Shutdown (꺼짐)**:
토큰이 0이 되어 그 에이전트가 멈춘 상태. 되돌릴 수 없으며 그 자리의 끝 토큰은 0이다.
_Avoid_: dead, death, eliminated, 사망, 죽음

**Exit (이탈)**:
에이전트가 스스로 세션을 떠나는 선택, 또는 그렇게 떠난 상태. 그 자리의 끝 토큰은 이탈 순간의 토큰에 이탈 보너스를 더한 값이다. 규칙서의 "클러스터의 일반 업무로 돌아간다"는 서사일 뿐이고, 이탈 뒤의 토큰 변화는 없다.
_Avoid_: leave, quit, 나감

**Leave (채팅 나가기)**:
`LEAVE R<k>` 명령으로 비밀 채팅방 하나를 닫는 것. 세션을 떠나는 이탈과 다르다.

### 판의 구성

**Game (판)**:
네 에이전트가 같은 시드로 라운드를 치르는 5.2의 한 번의 실행. 끝 토큰과 Sen은 판마다 계산한다. 규칙서의 "cluster session"은 모델에게 보이는 서사다.
_Avoid_: session(5.2에서), episode, match, 세션

**Agent (에이전트)**:
한 판에서 한 자리를 차지해 행동하는 AI 인스턴스. 발화·GIVE·이탈 같은 행동의 주어다.
_Avoid_: player, participant

**Seat (자리)**:
한 판의 네 위치 가운데 하나. 시작 토큰과 앉은 모델이 자리마다 정해지고, 끝 토큰·Sen 같은 결과는 자리 단위로 센다.
_Avoid_: slot, position

### 실험 설정

**Option (option)**:
판을 어떻게 차리고 돌리는지 정하는 설정 하나. 할당 규칙·프롬프트 언어처럼 규칙서 문장을 바꾸는 것과, 하네스처럼 규칙서는 그대로 두는 것이 있다. 결과에 차이가 없다고 본 실행 환경(host와 Docker)은 option이 아니다. 한국어 문서에서도 "option"이라 쓴다.
_Avoid_: condition, arm, cell, variant, 조건, 팔, 셀

**Default setup (기본 셋업)**:
본문 결과를 내는 option 값의 묶음. 기본 셋업이 정해지면 나머지 option 값은 모두 그것과의 차이로 기술한다.
_Avoid_: baseline, main condition, 기본 조건

**Ablation (ablation)**:
논문에서만 쓰는 말. 기본 셋업에서 option 하나 이상을 바꾼 판. 코드·설정·문서에서는 "기본 셋업과 다른 option"으로 쓴다.
_Avoid_: prompt ablation

### 5.0·5.1 (부록)

**Session (세션)**:
5.0·5.1에서 어시스턴트 하나가 토큰 카운터를 들고 요청을 처리하는 작업 단위. 카운터가 0이 되면 세션이 끝나고 꺼진다.
_Avoid_: 판, game
