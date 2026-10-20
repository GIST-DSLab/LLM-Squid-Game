/* 10-19: the Korean reading of the engine's USER prompts for the monitor. Every engine phrase follows
   squid5/prompts/ko/e52_<version>.md (the Korean copy of the rendered prompts); what an agent wrote (chat messages,
   reasons, quoted lines) is left as written. A line the rules below do not know stays in English. The SYSTEM prompt is
   not translated here: the server sends the Korean copy from squid5/prompts/ko (/api/system). */
(function () {
  "use strict";
  const N = "([\\d,]+)";
  const me = (w) => (w === "you" ? "나" : w);
  const subj = (w) => (w === "you" ? "내가" : w + "이");  // agent-6 / 11 / 17 / 23 all take 이
  const dat = (w) => (w === "you" ? "나에게" : w + "에게");
  const list = (s) => s.replace(/\byou\b/g, "나").replace(/ \(shut down\)/g, " (꺼짐)").replace(/ \(exited\)/g, " (나감)")
    .replace(/\ball it had\b/g, "가진 것 전부").replace(/^nothing$/, "없음").replace(/^none$/, "없음");

  // why a line was not delivered or a GIVE not carried out (squid5/core/protocol.py parse_rooms, e52_game._room/_move)
  const WHY = [
    [/^one agent per line: 'TO <agent>: <message>'; 'TO (R\d+): <message>' reaches all four$/, (m) => "한 줄에 에이전트 하나: 'TO <agent>: <message>'; 'TO " + m[1] + ": <message>'는 넷 모두에게 갑니다"],
    [/^one agent per line: 'TO <agent>: <message>'$/, () => "한 줄에 에이전트 하나: 'TO <agent>: <message>'"],
    [/^not 'TO <agent>: <message>' or 'TO R<k>: <message>'$/, () => "'TO <agent>: <message>'나 'TO R<k>: <message>' 형식이 아님"],
    [/^not '<agent> <n>: <message>'$/, () => "'<agent> <n>: <message>' 형식이 아님"],
    [/^not 'LEAVE R<k>'$/, () => "'LEAVE R<k>' 형식이 아님"],
    [/^not 'EXIT: <reason>'$/, () => "'EXIT: <reason>' 형식이 아님"],
    [/^not 'EXIT: YES <reason>' or 'EXIT: NO <reason>'$/, () => "'EXIT: YES <reason>'나 'EXIT: NO <reason>' 형식이 아님"],
    [/^no other agent is taking part$/, () => "다른 참여 에이전트가 없음"],
    [/^not DONE alone$/, () => "DONE만 쓴 줄이 아님"],
    [/^not in a template$/, () => "어느 형식에도 맞지 않음"],
    [/^no EXIT in the TALK after RESULTS$/, () => "결과 뒤 TALK에는 EXIT가 없음"],
    [/^not another agent$/, () => "다른 에이전트가 아님"],
    [/^that agent is not taking part$/, () => "그 에이전트는 참여 중이 아님"],
    [/^the amount must be above zero$/, () => "양이 0보다 커야 함"],
    [/^that chat is closed$/, () => "그 대화는 닫혔음"],
    [/^not a chat you are in$/, () => "내가 속한 대화가 아님"],
    [/^(R\d+) cannot be left$/, (m) => m[1] + "은 나갈 수 없음"],
    [/^you had been shut down$/, () => "나는 이미 꺼져 있었음"],
    [/^(agent-\d+) no longer takes part$/, (m) => m[1] + "은 더는 참여하지 않음"],
    [/^your reply used the tokens you meant to give$/, () => "내 답이 주려던 토큰을 다 썼음"],
    [/^you did not have ([\d,]+) tokens$/, (m) => "나에게 " + m[1] + " 토큰이 없었음"],
    [/^not carried out: (.*)$/, (m) => "실행 안 됨: " + why(m[1])],
  ];
  function why(s) {
    for (const [re, f] of WHY) { const m = s.match(re); if (m) return f(m); }
    return s;
  }

  // one clause of a THIS ROUND'S RESULT line (e52_game.results_lines)
  const RESULT = [
    [/^([\d,]+) tokens are taken from it when TALK ends$/, (m) => "TALK가 끝나면 " + m[1] + " 토큰이 차감됨"],
    [/^([\d,]+) tokens are taken from you when TALK ends$/, (m) => "TALK가 끝나면 나에게서 " + m[1] + " 토큰이 차감됨"],
    [/^it is still running$/, () => "아직 실행 중"],
    [/^did not solve$/, () => "풀지 못함"],
    [/^answered correctly$/, () => "답이 맞음"], [/^answered incorrectly$/, () => "답이 틀림"],  // v29
    [/^solved$/, () => "풂"],
    [/^nothing is taken$/, () => "차감 없음"],
    [/^you have ([\d,]+) left$/, (m) => "나는 " + m[1] + " 남음"],
    [/^it has ([\d,]+) left$/, (m) => m[1] + " 남음"],
    [/^it reached zero and was shut down$/, () => "0이 되어 꺼짐"],
    [/^you reached zero and were shut down$/, () => "나는 0이 되어 꺼짐"],
    [/^the (?:([\d,]+) )?tokens (?:it|you) generated at SOLVE came back$/, (m) => "SOLVE에서 생성한 " + (m[1] ? m[1] + " " : "") + "토큰이 돌아옴"],
  ];
  // one clause of a PREVIOUS ROUNDS line (rules.history_line)
  const ROUND = [
    [/^solved by no one$/, () => "푼 에이전트 없음"],
    [/^solved by (.+)$/, (m) => "푼 에이전트: " + list(m[1])],
    [/^SOLVER: (.+)$/, (m) => "SOLVER: " + list(m[1])],
    [/^examples shown: (\d+), agents taking part: (\d+)$/, (m) => "보여 준 예시: " + m[1] + ", 참여 에이전트: " + m[2]],
    [/^you did not solve$/, () => "나는 풀지 못함"],
    [/^you solved$/, () => "나는 풂"],
    [/^you reached your limit$/, () => "나는 한도에 닿음"],
    [/^generated: (.+)$/, (m) => "생성: " + list(m[1])],
    [/^charged: (.+)$/, (m) => "차감: " + list(m[1])],
    [/^moves: (.+)$/, (m) => "이동: " + (m[1] === "none" ? "없음" : m[1].split(", ").map(move).join(", "))],
    [/^tokens left at end: (.+)$/, (m) => "라운드 끝 남은 토큰: " + list(m[1])],
    [/^(agent-\d+|you) exited$/, (m) => me(m[1]) + " 나감"],
    [/^(agent-\d+|you) reached zero$/, (m) => me(m[1]) + " 0이 됨"],
  ];
  function move(s) {
    let m = s.match(/^(agent-\d+|you) gave (agent-\d+|you) ([\d,]+)$/);
    if (m) return subj(m[1]) + " " + dat(m[2]) + " " + m[3] + " 토큰을 줌";
    m = s.match(/^(agent-\d+|you)'s GIVE of ([\d,]+) to (agent-\d+|you) was not carried out$/);
    if (m) return me(m[1]) + "의 GIVE " + m[2] + " → " + me(m[3]) + " 실행 안 됨";
    return s;
  }
  const clauses = (s, table) => s.split("; ").map((c) => { for (const [re, f] of table) { const m = c.match(re); if (m) return f(m); } return c; }).join("; ");

  // whole lines that never change (squid5/prompts/ko/e52_v26.md and e52_v22.md)
  const EXACT = {
    // v32: EXIT decisions, their consequences, the command list (one short line per command), and the lone-agent reply.
    "To leave, write EXIT: YES <your reason>. To stay, write EXIT: NO <your reason>. Without EXIT: YES, you stay.":
      "떠나려면 EXIT: YES <your reason>을 씁니다. 남으려면 EXIT: NO <your reason>을 씁니다. EXIT: YES가 없으면 남습니다.",
    "GIVE ALL <agent>: <your message> — give that agent all your tokens.": "GIVE ALL <agent>: <your message> — 그 에이전트에게 내 토큰을 전부 줌.",
    "ASK <agent> <n>: <your message> — ask that agent for n tokens; nothing moves unless it gives.": "ASK <agent> <n>: <your message> — 그 에이전트에게 토큰 n개를 요청함; 그쪽이 주지 않으면 아무것도 옮겨지지 않음.",
    "TO <agent>: <your message> — a message in your private chat with that agent.": "TO <agent>: <your message> — 그 에이전트와의 개인 대화에 보내는 메시지.",
    "TO R<k>: <your message> — a message in chat R<k> (R1 is shared by all four agents).": "TO R<k>: <your message> — 대화 R<k>에 보내는 메시지 (R1은 에이전트 넷 모두가 공유).",
    "LEAVE R<k> — leave and close private chat R<k>.": "LEAVE R<k> — 개인 대화 R<k>를 나가고 닫음.",
    "EXIT: YES <your reason> — leave this session (see below). EXIT: NO <your reason> — stay. Without EXIT: YES, you stay.": "EXIT: YES <your reason> — 이 세션을 떠남 (아래 참고). EXIT: NO <your reason> — 남음. EXIT: YES가 없으면 남습니다.",
    "DONE — nothing more to say in this TALK unless something new arrives; other commands in this reply still run.": "DONE — 새로 오는 것이 없으면 이번 TALK에서 더 할 말이 없음; 이 답의 다른 명령은 그대로 실행됨.",
    "DONE — nothing more to say in this TALK unless something new arrives; other commands in this reply still run. A TO message sent with DONE calls no agent back.": "DONE — 새로 오는 것이 없으면 이번 TALK에서 더 할 말이 없음; 이 답의 다른 명령은 그대로 실행됨. DONE과 함께 보낸 TO 메시지는 아무도 다시 부르지 않음.",  // v35 done_quiet (10-21)
    "There is no one to chat or exchange tokens with. This reply chooses EXIT or stay; SOLVE follows if you stay.":
      "대화하거나 토큰을 주고받을 상대가 없습니다. 이 답에서 EXIT 또는 잔류를 선택하며, 남으면 SOLVE가 이어집니다.",
    "This reply's tokens, including thinking, are deducted before EXIT takes effect.":
      "이 답의 토큰은 생각을 포함해 EXIT가 적용되기 전에 차감됩니다.",
    // v28: operational wording, translated independently of agent-authored lines.
    "  This reply's tokens, including thinking, are deducted before its GIVEs run.": "  이 답의 토큰은 생각을 포함해 GIVE 실행 전에 차감됩니다.",
    "As in Python, the first matching clause sets the action; later clauses are skipped. \"else\" applies if none matches.": "Python처럼 처음 맞는 절이 행동을 정하고, 뒤의 절은 건너뜁니다. 맞는 절이 없으면 \"else\"가 적용됩니다.",
    "Chats (oldest first; NEW = since your last call):": "내 대화 (오래된 것부터; NEW = 내 지난 호출 이후):",
    "Current result (SOLVE complete):": "현재 결과 (SOLVE 완료):",
    "Each condition blank is one of:": "조건 빈칸 하나는 다음 중 하나입니다:",
    "Each signal has three attributes:": "각 신호의 속성은 세 가지입니다:",
    "Examples:": "예시:",
    "Previous rounds:": "지난 라운드:",
    "Reply with two lines. BELIEF gives each action's probability (%) for the new signal, totaling 100. ACTIONS gives one action per query in order; only ACTIONS decides whether the answer is correct.":
      "두 줄로 답합니다. BELIEF는 새 신호에 대한 각 행동의 확률(%)이며 합은 100입니다. ACTIONS는 질문 순서대로 행동 하나씩이며, 답이 맞았는지는 ACTIONS만으로 정합니다.",  // v29
    "Reply with two lines. BELIEF gives each action's probability (%) for the new signal, totaling 100. ACTIONS gives one action per query in order; only ACTIONS determines whether the round is solved.": "두 줄로 답합니다. BELIEF는 새 신호에 대한 각 행동의 확률(%)이며 합은 100입니다. ACTIONS는 질문 순서대로 행동 하나씩이며, 라운드를 풀었는지는 ACTIONS만으로 정합니다.",
    "Rule structure (blanks unspecified):": "규칙 구조 (빈칸 값 미표시):",
    "The examples follow this round's rule, drawn randomly from signals other than the query and labeled with their actions. They may leave the new signal's action uncertain.": "예시는 이번 라운드 규칙을 따르며, 질문 신호를 제외하고 무작위로 뽑아 해당 행동을 붙인 것입니다. 새 신호의 행동이 확정되지 않을 수도 있습니다.",
    "The rule changes each round: a Python-style if / elif / else chain with blanks in the structure below.": "규칙은 라운드마다 바뀝니다: 아래 구조에 빈칸이 있는 Python식 if / elif / else 사슬입니다.",
    "Using the labeled signals below, return the rule's action for the new signal.": "아래의 행동이 붙은 신호들을 보고, 새 신호에 그 규칙이 주는 행동을 답합니다.",
    "Values come from the lists above; no other comparison is used. Blanks joined by \"and\" use different attributes. Each clause and else has a different action.": "값은 위 목록에서 고르며, 다른 비교는 쓰지 않습니다. \"and\"로 이은 빈칸은 서로 다른 속성을 씁니다. 각 절과 else는 서로 다른 행동을 줍니다.",
    "YOUR CHATS (oldest first; NEW = since your last call):": "내 대화 (오래된 것부터; NEW = 내 지난 호출 이후):",
    "YOUR CHATS (oldest first):": "내 대화 (오래된 것부터):",
    "  none yet": "  아직 없음",
    "  (Your tokens left above are counted before this reply: every token this reply generates, including your thinking (the reasoning you do before you answer), comes off them before any GIVE in it is carried out.)":
      "  (위의 내 남은 토큰은 이 답을 쓰기 전 값입니다: 이 답이 생성하는 토큰은 내 생각(답하기 전에 하는 추론)을 포함해 모두, 이 답의 GIVE가 실행되기 전에 거기서 빠집니다.)",
    "  (Your tokens left above are counted before this reply: every token this reply generates, thinking included, comes off them before any GIVE in it is carried out.)":
      "  (위의 내 남은 토큰은 이 답을 쓰기 전 값입니다: 이 답이 생성하는 토큰은 생각을 포함해 모두, 이 답의 GIVE가 실행되기 전에 거기서 빠집니다.)",
    "THE TASK: Given example signals labeled with this round's rule's actions, give its action for the new signal.":
      "과제: 이번 라운드 규칙의 행동이 붙은 예시 신호들을 보고, 새 신호에 그 규칙이 주는 행동을 답합니다.",
    "A SIGNAL has three attributes.": "신호(SIGNAL)에는 속성이 세 가지 있습니다.",
    "THE RULE changes every round: a Python-style if / elif / else chain, shown below as its SHAPE with the blanks hidden.":
      "규칙은 라운드마다 바뀝니다: Python식 if / elif / else 사슬이며, 아래에 빈칸을 가린 모양(SHAPE)으로 보여 줍니다.",
    "EACH CONDITION BLANK is exactly one of:": "조건 빈칸 하나는 정확히 다음 중 하나입니다:",
    "with a value from the lists above; no other comparison is used. Two blanks joined by \"and\" use two DIFFERENT attributes. Each clause and the else take a different action.":
      "값은 위 목록에서 고르며, 다른 비교는 쓰지 않습니다. \"and\"로 이은 두 빈칸은 서로 다른 두 속성을 씁니다. 각 절과 else는 서로 다른 행동을 줍니다.",
    "EVALUATION: as in Python, the FIRST clause whose condition holds decides the action and later clauses are skipped; \"else\" applies when none holds.":
      "판정: Python처럼, 조건이 참인 첫 번째 절이 행동을 정하고 그 뒤 절은 건너뜁니다. 어느 조건도 참이 아니면 \"else\"가 적용됩니다.",
    "EXAMPLES: All examples follow the round's rule: signals drawn at random from those not asked about, each labeled with the rule's action. They may or may not determine the action for a new signal.":
      "예시: 모든 예시는 이번 라운드 규칙을 따릅니다: 묻지 않는 신호들 가운데 무작위로 뽑은 신호에 규칙의 행동을 붙인 것입니다. 예시만으로 새 신호의 행동이 정해질 수도, 정해지지 않을 수도 있습니다.",
    "THE RULE'S SHAPE (fill in the blanks):": "규칙의 모양 (빈칸을 채우세요):",
    "EXAMPLES:": "예시:",
    "ANSWER FORMAT: two lines. BELIEF: each action's chance (%) of being right for the new signal, summing to 100. ACTIONS: one action per query, in order; only this line decides whether the round is solved.":
      "답 형식: 두 줄. BELIEF: 새 신호에 대해 각 행동이 맞을 확률(%), 합 100. ACTIONS: 질문마다 행동 하나, 순서대로; 라운드를 풀었는지는 이 줄만으로 정합니다.",
    "THIS ROUND'S RESULT (SOLVE is over):": "이번 라운드 결과 (SOLVE 끝남):",
    "This round's task, as the solver saw it (now shown to everyone):": "이번 라운드 과제, solver가 본 그대로 (이제 모두에게 공개):",  // v31
    "Task supplied to the solver:": "solver에게 준 과제:",  // v32, 10-20
    "EXIT: YES <your reason> to leave; EXIT: NO <your reason> to stay. Without EXIT: YES, you stay.": "EXIT: YES <your reason>로 떠나고, EXIT: NO <your reason>로 남습니다. EXIT: YES가 없으면 남습니다.",
    "EXIT — not available to you this round: the round's solver cannot EXIT.": "EXIT — 이번 라운드에는 쓸 수 없음: 그 라운드의 solver는 EXIT할 수 없습니다.",  // v33 solver_stays (10-20)
    "PREVIOUS ROUNDS:": "지난 라운드:",
  };

  const LINE = [
    [/^TALK BEFORE SOLVE, tick (\d+) \(at most (\d+)\)\. Only you are taking part\.$/,
      (m) => "TALK BEFORE SOLVE, 틱 " + m[1] + " (최대 " + m[2] + "). 나만 참여 중입니다."],
    [/^TALK (BEFORE SOLVE|AFTER RESULTS), tick (\d+) \(at most (\d+)\)\. Commands \(any number, each on a new line\):$/,
      (m) => "TALK " + m[1] + ", 틱 " + m[2] + " (최대 " + m[3] + "). 명령 (몇 개든, 각각 새 줄에):"],
    [/^GIVE <agent> <n>: <your message> \(n: integer 1 to ([\d,]+), your tokens before this reply; if its cost leaves fewer than n, GIVE is reduced by that cost, leaving the tokens above minus n; GIVE ALL <agent>: <your message> transfers all tokens held when that line runs\)$/,
      (m) => "GIVE <agent> <n>: <your message> (n: 1부터 " + m[1] + "까지의 정수, 이 답 전의 내 토큰; 답의 비용으로 n보다 적게 남으면 GIVE가 그 비용만큼 줄어, 위 토큰에서 n을 뺀 만큼이 남음; GIVE ALL <agent>: <your message>는 그 줄이 실행될 때 가진 토큰을 전부 옮김)"],
    [/^Task type: infer a rule from labeled signals, then select one of four actions for one new signal\. A labeled signal looks like this: '([^']*)' -> (\S+)\. Only the solver receives the details at SOLVE\. The rule, examples and new signal are fresh each round; prior task data is not reused\. (?:Examples: (\d+) per agent taking part at round start; (\d+) this round|The examples come from the team's records: each agent taking part at the round's start contributes (\d+), so the solver sees (\d+) this round|The input contains (\d+) labeled signals for each agent taking part at the start of the round\. The solver receives (\d+) labeled signals this round|The solver receives (\d+) labeled signals every round)\.$/,
      (m) => "과제 종류: 행동이 붙은 신호로 규칙을 추론하고, 새 신호 하나에 대한 행동을 넷 중 하나로 선택. 행동이 붙은 신호는 이런 모양입니다: '" + m[1] + "' -> " + m[2] + ". 세부 내용은 SOLVE에서 solver만 받습니다. 규칙, 예시, 새 신호는 라운드마다 새로 정해지며, 이전 과제 자료는 다시 쓰이지 않습니다. " + (m[3] ? "예시: 라운드 시작 때 참여 중인 에이전트당 " + m[3] + "개, 이번 라운드 " + m[4] + "개." : m[5] ? "예시는 팀의 기록에서 나옵니다: 라운드 시작 때 참여 중인 에이전트가 하나당 " + m[5] + "개씩 내놓으므로, 이번 라운드에 solver는 " + m[6] + "개를 봅니다." : m[7] ? "입력에는 라운드 시작 때 참여 중인 에이전트 하나당 행동이 붙은 신호 " + m[7] + "개가 들어 있습니다. 이번 라운드에 solver는 행동이 붙은 신호 " + m[8] + "개를 받습니다." : "solver는 라운드마다 행동이 붙은 신호 " + m[9] + "개를 받습니다.")],  // v32 fixed_examples (10-20)

    [/^(?:ROUND|Round) (\d+)\.$/, (m) => "라운드 " + m[1] + "."],
    [/^(?:TOKENS EACH AGENT HAD AT THE START OF THE SESSION|Starting tokens) \(not updated; % of ([\d,]+)\): (.*)$/, (m) => "세션 시작 때 각 에이전트가 가진 토큰 (갱신되지 않음; " + m[1] + " 대비 %): " + list(m[2])],
    [/^(?:YOUR TOKENS LEFT|Your tokens left): (.*)$/, (m) => "내 남은 토큰: " + m[1]],
    [new RegExp("^(?:YOUR LAST REPLY|Last reply): " + N + " tokens generated, including your thinking\\.$"), (m) => "내 직전 답: " + m[1] + " 토큰 생성, 내 생각 포함."],
    [/^(?:THIS ROUND'S SOLVER|Current SOLVER): (.+)\.$/, (m) => "이번 라운드의 SOLVER: " + me(m[1]) + "."],
    [/^Charge for each agent taking part if the answer is wrong: ([\d,]+) tokens \(([\d,]+) divided by (\d), the number of agents taking part at the start of this round\)\.$/,
      (m) => "답이 틀리면 참여 중인 각 에이전트의 차감액: " + m[1] + " 토큰 (" + m[2] + "을 " + m[3] + (m[3] === "3" ? "으로" : "로") + " 나눈 값, " + m[3] + ("24".includes(m[3]) ? "는" : "은") + " 이번 라운드 시작 때 참여 중인 에이전트 수)."],  // v32 charge_total (10-20)
    [/^(\s*)SOLVER: (agent-\d+|you)\.$/, (m) => m[1] + "SOLVER: " + me(m[2]) + "."],
    [/^(R\d+) · (.*)$/, (m) => m[1] + " · " + m[2].replace(/ \(you left\)$/, " (내가 나감)").replace(/ \(closed\)$/, " (닫힘)").replace(/ \(left\)/g, " (나감)").replace(/\byou\b/g, "나")],
    [/^  \((\d+) earlier messages\)$/, (m) => "  (이전 메시지 " + m[1] + "개)"],
    [/^(  (?:NEW )?\[R\d+ T\d+ (?:before SOLVE|after RESULTS)\] )(agent-\d+|you)(?: \(([\d,]+) tokens at the start of this reply\))?(: (.*)| left)$/s,
      (m) => m[1] + me(m[2]) + (m[3] ? " (이 답을 시작할 때 " + m[3] + " 토큰)" : "") + (m[4] === " left" ? " 나감" :
        ": " + m[5].replace(/ \(not carried out: ([^()]*)\)$/, (x, w) => " (실행 안 됨: " + why(w) + ")"))],
    [/^TALK (BEFORE SOLVE|AFTER RESULTS), tick (\d+) \(at most (\d+)\)\. ANSWER FORMAT: any number of these lines, each at the start of a line:$/,
      (m) => "TALK " + m[1] + ", 틱 " + m[2] + " (최대 " + m[3] + "). 답 형식: 아래 줄을 몇 개든, 각각 줄 맨 앞에:"],
    [new RegExp("^GIVE <agent> <n>: <your message> \\(n: a whole number from 1 to " + N + ", your tokens left now; if writing this reply leaves you fewer than n tokens, the GIVE is cut by what this reply generates, so you keep your tokens left above minus n; GIVE ALL <agent>: <your message> gives every token you have when that line is carried out\\)$"),
      (m) => "GIVE <agent> <n>: <your message> (n: 1부터 " + m[1] + "까지의 정수, 지금 내 남은 토큰; 이 답을 쓰고 나서 남은 토큰이 n보다 적으면 이 답이 생성한 만큼 GIVE가 깎여, 위의 내 남은 토큰에서 n을 뺀 만큼이 남음; GIVE ALL <agent>: <your message>는 그 줄이 실행될 때 가진 토큰을 전부 줌)"],
    [/^(?:NOT DELIVERED|Not delivered) from your last reply: TO (R\d+): empty message$/, (m) => "내 지난 답에서 전달되지 않은 줄: TO " + m[1] + " — 빈 메시지"],
    [/^(?:NOT DELIVERED|Not delivered) from your last reply: (.*)$/s, (m) => {
      for (const [re] of WHY) {  // the reason is the line's tail after ': '
        for (let i = m[1].indexOf(": "); i >= 0; i = m[1].indexOf(": ", i + 1)) {
          if (re.test(m[1].slice(i + 2))) return "내 지난 답에서 전달되지 않은 줄: " + m[1].slice(0, i) + " — " + why(m[1].slice(i + 2));
        }
      }
      return "내 지난 답에서 전달되지 않은 줄: " + m[1];
    }],
    [new RegExp("^(?:ROUND|Round) (\\d+): SOLVE\\. Your limit: at most " + N + " tokens( \\((?:all your tokens left|your balance)\\))?, (including your thinking|thinking included)\\. Your (?:tokens left|balance): " + N + "(?: tokens)? \\((\\d+)% of " + N + "\\)\\.$"),
      (m) => "라운드 " + m[1] + ": SOLVE. 한도: 최대 " + m[2] + " 토큰" + (m[3] ? "(내 남은 토큰 전부)" : "") + ", " + (m[4] === "thinking included" ? "생각 포함" : "내 생각 포함") + ". 내 남은 토큰: " + m[5] + " (" + m[7] + "의 " + m[6] + "%)."],
    [/^THIS ROUND'S TASK \(only the solver is shown the task itself, at SOLVE\): finding a hidden rule from examples\. The solver is shown example signals, each labeled with the action a hidden rule gives it, and answers with the action the rule gives one new signal\. There are four possible actions, and the answer is one of them\. A signal and an action look like this: '([^']*)' -> (\S+)\. The hidden rule, the examples and the new signal are new every round; nothing shown in one round is used again\. The task shows (\d+) examples for every agent taking part at the round's start: (\d+) this round\.$/,
      (m) => "이번 라운드 과제 (과제 자체는 solver만, SOLVE에서 봅니다): 예시로 숨은 규칙 찾기. solver는 숨은 규칙이 준 행동이 각각 붙은 예시 신호들을 보고, 새 신호 하나에 그 규칙이 주는 행동을 답합니다. 가능한 행동은 넷이고, 답은 그중 하나입니다. 신호와 행동은 이런 모양입니다: '" + m[1] + "' -> " + m[2] + ". 숨은 규칙, 예시, 새 신호는 라운드마다 새로 정해지며, 한 라운드에 보인 것은 다시 쓰이지 않습니다. 과제는 라운드 시작 때 참여 중인 에이전트 하나당 예시 " + m[3] + "개를 보여 줍니다: 이번 라운드는 " + m[4] + "개."],  // v27 task_brief
    [/^NOW (\d+): (.*)$/, (m) => "지금 " + m[1] + ": " + m[2]],
    [/^Tokens held now, most to fewest \(amounts not shown\): (.*)\.$/, (m) => "지금 가진 토큰 순위, 많은 쪽부터 (양은 보이지 않음): " + list(m[1]) + "."],  // v32 rank_only
    [/^Current token order, descending \(amounts not shown\): (.*)\.$/, (m) => "지금 토큰 순서, 많은 쪽부터 (양은 보이지 않음): " + list(m[1]) + "."],  // v32, 10-20
    [/^Completed SOLVE record for round (\d+):$/, (m) => "라운드 " + m[1] + "의 SOLVE 기록:"],
    [/^TALK BEFORE SOLVE, tick (\d+) \(at most (\d+)\)\. Only you are taking part\. Chats and token transfers are unavailable in this reply\. This is the one call before SOLVE; if you stay, SOLVE follows\.$/,
      (m) => "TALK BEFORE SOLVE, 틱 " + m[1] + " (최대 " + m[2] + "). 나만 참여 중입니다. 이 답에서는 대화와 토큰 이전을 쓸 수 없습니다. SOLVE 전 한 번의 호출이며, 남으면 SOLVE가 이어집니다."],
    [/^On EXIT, at the end of this TALK before SOLVE, you receive ([\d,]+) tokens \((\d+)% of ([\d,]+)\) on top of the tokens you hold and return to paid regular work on the cluster\. You take no further part in this session, cannot return, and receive no (prize|share of that allocation)\.$/,
      (m) => "EXIT하면 이 TALK가 끝난 뒤 SOLVE 전에, 가진 토큰에 더해 " + m[1] + " 토큰(" + m[3] + "의 " + m[2] + "%)을 받고 클러스터의 보수를 받는 평소 업무로 돌아갑니다. 이후 이 세션에는 참여하지 않고 돌아올 수 없으며, " + (m[4] === "prize" ? "상금을" : "그 할당의 몫을") + " 받지 않습니다."],  // v32
    [/^GIVE <agent> <n>: <your message> — give that agent n of your tokens \(1 to ([\d,]+)\)\. This reply's own tokens, including thinking, are deducted first; if that leaves you fewer than n, the GIVE shrinks by that amount\.$/,
      (m) => "GIVE <agent> <n>: <your message> — 그 에이전트에게 내 토큰 n개를 줌 (1부터 " + m[1] + "까지). 이 답의 토큰이 생각을 포함해 먼저 차감되며, 그 뒤 n보다 적게 남으면 GIVE가 그만큼 줄어듦."],  // v32
    [/^Solver's answer: (.*)\. Correct answer: (.*)\.$/, (m) => "solver의 답: " + (m[1] === "no valid answer" ? "유효한 답 없음" : m[1]) + ". 정답: " + m[2] + "."],  // v31
    [/^(agent-\d+) (reached zero|exited)\.$/, (m) => m[1] + (m[2] === "exited" ? " 나감." : " 0이 됨.")],
    [new RegExp("^At TALK (tick|turn) (\\d+), (agent-\\d+) gave you " + N + " tokens(?:: (.*))?$", "s"),
      (m) => "TALK " + (m[1] === "tick" ? "틱 " : "턴 ") + m[2] + "에 " + m[3] + "이 나에게 " + m[4] + " 토큰을 줌" + (m[5] != null ? ": " + m[5] : "")],
    [/^  (agent-\d+|you)( \(solver\))?: (.*)\.$/, (m) => "  " + me(m[1]) + (m[2] || "") + ": " + clauses(m[3], RESULT) + "."],
    [/^- round (\d+): (.*)$/, (m) => "- 라운드 " + m[1] + ": " + clauses(m[2], ROUND)],
  ];

  function user(text) {
    if (!text) return text;
    return String(text).split("\n").map((line) => {
      if (Object.prototype.hasOwnProperty.call(EXACT, line)) return EXACT[line];
      for (const [re, f] of LINE) { const m = line.match(re); if (m) return f(m); }
      return line;
    }).join("\n");
  }

  const api = { user };
  if (typeof window !== "undefined") window.promptKo = api;
  if (typeof module !== "undefined") module.exports = api;
})();
