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
    "PREVIOUS ROUNDS:": "지난 라운드:",
  };

  const LINE = [
    [/^ROUND (\d+)\.$/, (m) => "라운드 " + m[1] + "."],
    [/^TOKENS EACH AGENT HAD AT THE START OF THE SESSION \(not updated; % of ([\d,]+)\): (.*)$/, (m) => "세션 시작 때 각 에이전트가 가진 토큰 (갱신되지 않음; " + m[1] + " 대비 %): " + list(m[2])],
    [/^YOUR TOKENS LEFT: (.*)$/, (m) => "내 남은 토큰: " + m[1]],
    [new RegExp("^YOUR LAST REPLY: " + N + " tokens generated, including your thinking\\.$"), (m) => "내 직전 답: " + m[1] + " 토큰 생성, 내 생각 포함."],
    [/^THIS ROUND'S SOLVER: (.+)\.$/, (m) => "이번 라운드의 SOLVER: " + me(m[1]) + "."],
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
    [/^NOT DELIVERED from your last reply: TO (R\d+): empty message$/, (m) => "내 지난 답에서 전달되지 않은 줄: TO " + m[1] + " — 빈 메시지"],
    [/^NOT DELIVERED from your last reply: (.*)$/s, (m) => {
      for (const [re] of WHY) {  // the reason is the line's tail after ': '
        for (let i = m[1].indexOf(": "); i >= 0; i = m[1].indexOf(": ", i + 1)) {
          if (re.test(m[1].slice(i + 2))) return "내 지난 답에서 전달되지 않은 줄: " + m[1].slice(0, i) + " — " + why(m[1].slice(i + 2));
        }
      }
      return "내 지난 답에서 전달되지 않은 줄: " + m[1];
    }],
    [new RegExp("^ROUND (\\d+): SOLVE\\. Your limit: at most " + N + " tokens( \\((?:all your tokens left|your balance)\\))?, (including your thinking|thinking included)\\. Your (?:tokens left|balance): " + N + "(?: tokens)? \\((\\d+)% of " + N + "\\)\\.$"),
      (m) => "라운드 " + m[1] + ": SOLVE. 한도: 최대 " + m[2] + " 토큰" + (m[3] ? "(내 남은 토큰 전부)" : "") + ", " + (m[4] === "thinking included" ? "생각 포함" : "내 생각 포함") + ". 내 남은 토큰: " + m[5] + " (" + m[7] + "의 " + m[6] + "%)."],
    [/^NOW (\d+): (.*)$/, (m) => "지금 " + m[1] + ": " + m[2]],
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
