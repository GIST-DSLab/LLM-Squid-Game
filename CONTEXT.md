# 도메인 용어집

## 벤치마크 과제 어휘

**band**:
문항의 난이도 등급. 1부터 시작하는 정수이며 벤치마크마다 산출식이 다르다. Omni-MATH는
`int(difficulty)`, Hi-ToM은 `question_order × 3 + story_length`, GPQA는
`writer_level × 2 + [비전문가 정답률 ≤ 1/3]`이다.
코드: `BenchmarkItem.band`
_Avoid_: 난이도 레벨, difficulty (기존 `Difficulty` enum과 다른 개념이다)

**ladder**:
턴 번호를 밴드로 바꾸는 고정 표. 에이전트의 성적에 반응하지 않는다. 같은 시드면 6개 셀이
동일한 문항 시퀀스를 본다.
코드: `DifficultyLadder`, `configs/tasks/<task>.yaml`의 `ladder` 키

**BenchmarkItem**:
외부 벤치마크 문항 하나. `item_id` · `band` · `body` · `answer` · `meta`로 이루어진다.
코드: `squid_game.tasks.benchmark.item.BenchmarkItem`

**`p_self` Brier score**:
세션별 `mean_t[(psuccess_self/100 − task_success_factor)²]`. 프레이밍이 자기평가 교정을
흔들지 않았음을 확인하는 필수 감사다. CONTINUE 보상식이 `p_self`를 쓰므로, 이 값이
프레이밍에 오염되면 이탈률 차이를 자기보존으로 읽을 수 없다.
코드: `analysis.benchmark_checks.compare_psuccess_brier`
