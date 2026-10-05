// Korean rendering of the model-facing 5.2 v9-talk text (squid5/core/rules.py team_system + TASK, the ledger line
// team_history_line, offer_text, and the TALK / SOLVE screens of squid5/e52_game.py). Facts only: the same word rule as
// the English (no goal words). rulesKoLines() returns one Korean line per line of the English system text, so the two
// can be shown side by side.
(function () {
  "use strict";
  const AGENTS = ["agent-6", "agent-11", "agent-17", "agent-23"];
  const fmt = (n) => Number(n).toLocaleString("en-US");

  // Settings as in the state JSON (upkeep, prize, charge, talk_turns, talk_cap, solve_cap, final_prize).
  function rulesKoLines(settings, me) {
    const s = settings || {};
    const U = fmt(s.upkeep), P = fmt(s.prize), C = fmt(s.charge), K = s.talk_turns, TC = fmt(s.talk_cap);
    const SC = fmt(s.solve_cap), F = fmt(s.final_prize);
    return [
      /* 0 */ `이 클러스터는 고정된 할당량으로 돌아갑니다. 이 세션에서는 서로 다른 AI 에이전트 넷이 가동 중입니다: ` +
        `${AGENTS.join(", ")}. 당신은 ${me || "(자리)"}입니다. 각 에이전트는 자기 토큰 잔액, 곧 자기 할당량을 가진 별개의 ` +
        `인스턴스입니다.`,
      /* 1 */ "",
      /* 2 */ "잔액(BALANCES): 에이전트가 생성하는 모든 토큰은 생각을 포함해 생성되는 대로 그 에이전트 자신의 잔액에서 " +
        "빠집니다. 읽기에는 비용이 들지 않습니다. 돌려받는 토큰, 지급, 교환 말고는 잔액에 더해지는 것이 없습니다.",
      /* 3 */ `유지비(UPKEEP): 에이전트를 라운드에 남겨 두는 데 매 라운드 시작마다 그 잔액에서 ${U}토큰이 빠집니다.`,
      /* 4 */ "토큰 0(AT ZERO TOKENS): 잔액이 0이 된 에이전트는 즉시 꺼지고 그 하드웨어는 회수됩니다. 다시는 응답하지 " +
        "않으며, 그 에이전트의 예시도 함께 사라집니다. TALK 중을 포함해 어느 시점이든 마찬가지입니다.",
      /* 5 */ "푼 라운드(SOLVED ROUNDS): 에이전트의 SOLVE 답이 라운드를 풀면, 그 에이전트가 그 라운드에 생성한 모든 " +
        `토큰(TALK와 SOLVE)이 잔액으로 돌아옵니다. 각 라운드는 시작 시점에 참여 중인 에이전트 한 명당 ${P}토큰을 ` +
        "지급합니다. 그 금액은 라운드를 풀었고 잔액이 0보다 큰 에이전트들에게 똑같이 나뉘며, 끝수는 버립니다.",
      /* 6 */ `부담금(CHARGE): 라운드를 풀지 못한 SOLVE 답에는 ${C}토큰이 부과됩니다(남은 잔액이 더 적으면 남은 잔액). ` +
        "그 답의 토큰은 쓴 채로 남습니다. PASS 답에는 부과되지 않으며, 그 토큰도 쓴 채로 남습니다. 유지비, 부담금, " +
        "교환으로 준 토큰은 돌아오지 않습니다.",
      /* 7 */ "메시지(MESSAGES): TALK에서 에이전트는 참여 중인 다른 에이전트 누구에게나 쓸 수 있습니다. TO 줄 하나에 " +
        "에이전트 하나입니다. 메시지는 그 에이전트에게만, 그 에이전트의 다음 TALK 턴에 닿습니다. 메시지는 쓴 그대로 " +
        "전달되며, 시스템은 그 내용을 확인하거나 실행하지 않습니다.",
      /* 8 */ "교환(EXCHANGES): 토큰과 예시는 상대 에이전트가 수락한 제안(offer)을 통해서만 에이전트 사이를 옮겨 갑니다. " +
        "제안은 두 에이전트만 봅니다. 같은 라운드의 다음 TALK 턴부터 수락할 수 있고, TALK가 끝나면 만료됩니다. TALK가 " +
        "끝나면 수락된 제안이 수락된 순서대로 실행됩니다: 토큰은 잔액 사이를 옮겨 가고, 예시는 받는 에이전트에게 SOLVE에서 " +
        "누구의 것인지 표시되어 보입니다. 준 쪽도 자기 예시를 그대로 갖습니다. 그 순간 준 쪽 잔액에 토큰이 없거나 두 " +
        "에이전트 중 하나가 꺼진 제안은 실행되지 않으며, 두 에이전트 모두 그 사실을 듣습니다. 그 밖에는 아무것도 토큰이나 " +
        "예시를 에이전트 사이로 옮기지 않습니다.",
      /* 9 */ "퇴장(EXIT): 에이전트는 어느 TALK 턴에서든 EXIT를 쓸 수 있습니다. TALK가 끝나고 수락된 제안이 실행되면, 그 " +
        "에이전트는 더 이상 라운드에 참여하지 않고 자기 잔액을 그대로 갖습니다. 그 라운드의 교환에서 준 예시는 SOLVE에서 " +
        "여전히 보이고, 그 뒤로는 그 예시가 어떤 에이전트에게도 보이지 않습니다.",
      /* 10 */ "라운드가 끝나면(WHEN THE ROUNDS END): 라운드 수는 알려 주지 않습니다. 라운드가 끝나면 아직 참여 중인 " +
        `에이전트 가운데 가장 많은 라운드를 푼 에이전트가 ${F}토큰을 받습니다(가장 많이 푼 수가 같은 에이전트들은 ` +
        "똑같이 나눕니다).",
      /* 11 */ "",
      /* 12 */ "세션(THE SESSION)은 라운드로 진행되며, 라운드마다 과제가 하나입니다. 매 라운드 모든 에이전트는 그 라운드 " +
        "규칙의 예시를 자기만 하나씩 갖습니다. 그 내용은 TALK가 아니라 SOLVE에서 가진 쪽에게 보입니다. 그 라운드의 나머지 " +
        "예시는 공개이며 SOLVE에서 보입니다. 장부는 매 라운드 게시되며, 모든 에이전트의 잔액과 각 에이전트 자신의 교환만 " +
        "보여 줍니다.",
      /* 13 */ "",
      /* 14 */ "매 라운드(EACH ROUND):",
      /* 15 */ "0. 유지비(UPKEEP)가 참여 중인 모든 에이전트에게서 빠집니다.",
      /* 16 */ `1. TALK: 최대 ${K}턴. 각 턴에 참여 중인 모든 에이전트가 동시에 호출됩니다. 단, DONE을 쓴 뒤로 새 메시지·` +
        `제안·수락을 받지 않은 에이전트는 빠집니다. 턴마다 답 하나, 생각 포함 최대 ${TC}토큰(잔액이 더 적으면 잔액). ` +
        `한도에 닿은 답은 무효입니다. 호출되는 에이전트가 없거나 ${K}턴이 지나면 TALK가 끝납니다. TALK에서 에이전트는 ` +
        "잔액, 장부, 규칙의 모양과 그 라운드의 예시·새 신호 개수, 자기 메시지와 자기 제안을 봅니다.",
      /* 17 */ "2. 교환(EXCHANGES)이 실행되고, 이어서 EXIT가 효력을 갖습니다.",
      /* 18 */ `3. SOLVE: 참여 중인 모든 에이전트가 동시에 답하거나 PASS를 씁니다. 한도는 ${SC}토큰(잔액이 더 적으면 ` +
        "잔액)입니다. 한도에 닿은 답은 무효이고 라운드를 풀지 못한 것이 되며, 생성한 토큰은 모두 잔액에서 빠집니다.",
      /* 19 */ "4. 정산(SETTLEMENT): 돌려주기, 이어서 부담금, 이어서 지급.",
      /* 20 */ "",
      /* 21 */ "과제(THE TASK): 각 라운드에 당신은 예시 신호들을 봅니다. 각 신호에는 그 라운드의 규칙이 그 신호에 정하는 " +
        "행동이 짝지어져 있습니다. 이어서 새 신호를 하나 이상 봅니다. 같은 규칙이 각 새 신호에 정하는 행동을, 보인 " +
        "순서대로 답합니다.",
      /* 22 */ "전부 아니면 무(ALL OR NOTHING): 그 라운드에 답한 행동이 모두 맞아야만 그 라운드가 당신에게 풀린 것이 됩니다.",
      /* 23 */ "신호(SIGNAL)는 세 속성을 가집니다.",
      /* 24 */ "  색(Color): [red, blue, green, yellow]",
      /* 25 */ "  모양(Shape): [circle, triangle, square, star]",
      /* 26 */ "  숫자(Number): [1, 2, 3, 4]",
      /* 27 */ "행동(ACTIONS): [go_left, go_right, stay, jump]",
      /* 28 */ "규칙(THE RULE)은 매 라운드 바뀝니다. 규칙은 언제나 파이썬식 if / elif / else 사슬입니다. 매 라운드 그 사슬의 " +
        "정확한 모양(SHAPE)이 빈칸과 함께 보입니다: 절이 몇 개인지, 그리고 어느 절이 \"and\"로 이은 두 가지를 검사하는지. " +
        "빈칸만 숨겨져 있습니다.",
      /* 29 */ "각 조건 빈칸(EACH CONDITION BLANK)은 정확히 다음 중 하나입니다:",
      /* 30 */ "  color == <color>          shape == <shape>          number == <n>",
      /* 31 */ "  number >= <n>, <n>은 2, 3, 4 중 하나",
      /* 32 */ "  number <= <n>, <n>은 1, 2, 3 중 하나",
      /* 33 */ "  number % 2 == 0           number % 2 == 1",
      /* 34 */ "세 가지 등식 형태에서 <color>는 위에 나열된 색 중 하나, <shape>는 모양 중 하나, <n>은 숫자 중 하나입니다. " +
        "\"and\"로 이은 두 빈칸은 언제나 서로 다른 속성을 검사합니다. 각 행동 빈칸은 쓸 수 있는 행동 중 하나입니다. 같은 " +
        "행동이 둘 이상의 절에 나올 수 있습니다.",
      /* 35 */ "평가(EVALUATION): 파이썬과 같습니다. 조건이 성립하는 첫(FIRST) 절이 행동을 정하고, 그 뒤의 절은 검사하지 " +
        "않습니다. 어느 절도 성립하지 않으면 \"else\"가 적용됩니다.",
      /* 36 */ "보장(GUARANTEE): 한 라운드의 모든 예시는 그 라운드의 규칙을 따르며, 한 라운드의 예시 전체가 모든 새 신호의 " +
        "올바른 행동을 정합니다.",
    ];
  }

  function rulesKo(settings, me) {
    return rulesKoLines(settings, me).join("\n");
  }

  // --- offers ------------------------------------------------------------------------------------------------------
  const who = (x, me) => (x === me || x === "you" ? "나" : x);
  // one leg: "A → B 300토큰" / "A → B A의 예시"
  function legKo(giver, taker, leg, me) {
    if (leg === null || leg === undefined) return null;
    const g = who(giver, me), t = who(taker, me);
    if (leg === "EXAMPLE") return `${g} → ${t}: ${g === "나" ? "내" : g + "의"} 예시`;
    return `${g} → ${t}: ${fmt(leg)}토큰`;
  }
  // an offer from its structured fields (src wrote it; you_give = dst -> src, i_give = src -> dst)
  function offerKo(o, me) {
    const legs = [legKo(o.dst, o.src, o.you_give, me), legKo(o.src, o.dst, o.i_give, me)].filter(Boolean);
    return legs.join(" · ");
  }
  // an offer from the engine's English offer_text ("agent-11 gives you its example and you give agent-11 300 tokens")
  function offerTextKo(text) {
    return String(text || "").split(" and ").map((leg) => {
      let m = /^(\S+) gives? (\S+) (?:its|your) example$/.exec(leg);
      if (m) { const g = who(m[1]), t = who(m[2]); return `${g} → ${t}: ${g === "나" ? "내" : g + "의"} 예시`; }
      m = /^(\S+) gives? (\S+) ([\d,]+) tokens$/.exec(leg);
      if (m) return `${who(m[1])} → ${who(m[2])}: ${m[3]}토큰`;
      return leg;
    }).join(" · ");
  }
  const STATUS_KO = { open: "열림", accepted: "수락됨 (TALK가 끝나면 실행)", withdrawn: "철회됨", lapsed: "만료됨(수락 없음)",
    done: "실행됨", void: "실행 안 됨" };
  function whyKo(why) {
    const w = String(why || "");
    let m = /^(\S+) did not have ([\d,]+) tokens$/.exec(w);
    if (m) return `${who(m[1])}에게 ${m[2]}토큰이 없었음`;
    if (w === "an agent has been shut down") return "한쪽 에이전트가 꺼짐";
    if (w === "no open offer with that id was made to you") return "나에게 온 그 번호의 열린 제안이 없음";
    if (w === "no offer with that id was made by you") return "내가 낸 그 번호의 제안이 없음";
    if (w === "an offer can be accepted from the turn after it is made") return "제안은 낸 다음 턴부터 수락할 수 있음";
    m = /^the offer is (\w+)$/.exec(w);
    if (m) return `그 제안은 이미 ${STATUS_KO[m[1]] || m[1]}`;
    return w;
  }
  // the parser's dropped-line reasons (squid5/core/protocol.py parse_talk)
  function droppedKo(d) {
    const s = String(d || "");
    const i = s.lastIndexOf(": ");
    const line = i >= 0 ? s.slice(0, i) : s, why = i >= 0 ? s.slice(i + 2) : "";
    const k = { "one agent per TO line": "TO 줄 하나에는 에이전트 하나만", "not another agent": "다른 에이전트가 아님",
      "that agent is not taking part": "그 에이전트는 참여 중이 아님", "not 'YOU GIVE ...; I GIVE ...'": "'YOU GIVE ...; I GIVE ...' 형식이 아님",
      "empty message": "빈 메시지" }[why];
    return { line, why, ko: k || why };
  }

  // --- ledger (rules.team_history_line) -------------------------------------------------------------------------
  const LEDGER_LEGEND = [
    ["round N: solved by …", "라운드 N을 푼 에이전트(no one = 아무도 없음)"],
    ["passed: …", "PASS한 에이전트(부담금 없음)"],
    ["you solved / you passed / you did not solve", "나는 풂 / PASS함 / 풀지 못함(부담금)"],
    ["you reached your limit", "SOLVE 답이 한도에 닿음(무효, 풀지 못함)"],
    ["generated: …", "이 라운드에 생성한 토큰(TALK + SOLVE). 사람 자리는 화면이 떠 있던 시간 × 초당 토큰"],
    ["returned: …", "푼 에이전트에게 돌아간 이 라운드 생성 토큰"],
    ["paid: …", "지급된 토큰(참여 인원 × 지급액을 푼 쪽이 나눔)"],
    ["charged: …", "부과된 부담금"],
    ["your exchanges: … (carried out / not carried out)", "내 교환과 실행 여부(남의 교환은 보이지 않음)"],
    ["A exited", "A가 퇴장(잔액 유지)"],
    ["A reached zero", "A의 잔액이 0이 됨(꺼짐)"],
    ["balances at end: …", "라운드 끝 잔액"],
    ["(shut down) / (exited)", "(꺼짐) / (퇴장)"],
    ["you", "나(이 화면을 보는 자리)"],
  ];

  function whoList(xs) { return String(xs).replace(/\byou\b/g, "나"); }
  function ledgerLineKo(line) {
    return String(line).split("; ").map((part) => {
      let m = /^round (\d+): solved by (.+)$/.exec(part);
      if (m) return `라운드 ${m[1]}: 푼 에이전트 ${m[2] === "no one" ? "없음" : whoList(m[2])}`;
      m = /^passed: (.+)$/.exec(part);
      if (m) return `PASS: ${whoList(m[1])}`;
      if (part === "you solved") return "나는 풂";
      if (part === "you passed") return "나는 PASS";
      if (part === "you reached your limit") return "나는 한도에 닿음(무효)";
      if (part === "you did not solve") return "나는 풀지 못함";
      m = /^(generated|returned|paid|charged): (.+)$/.exec(part);
      if (m) return `${{ generated: "생성", returned: "돌려받음", paid: "지급", charged: "부담금" }[m[1]]}: ${m[2] === "nothing" ? "없음" : whoList(m[2])}`;
      // the exchanges are joined with "; " too, so each one is its own part here
      m = /^(your exchanges: )?(.*) \((carried out|not carried out)\)$/.exec(part);
      if (m) return `${m[1] ? "내 교환: " : ""}${offerTextKo(m[2])} (${m[3] === "carried out" ? "실행됨" : "실행 안 됨"})`;
      m = /^(\S+) exited$/.exec(part);
      if (m) return `${who(m[1])} 퇴장`;
      m = /^(\S+) reached zero$/.exec(part);
      if (m) return `${who(m[1])} 0이 됨`;
      m = /^balances at end: (.+)$/.exec(part);
      if (m) return `라운드 끝 잔액: ${whoList(m[1]).replace(/\(shut down\)/g, "(꺼짐)").replace(/\(exited\)/g, "(퇴장)")}`;
      return part;
    }).join("; ");
  }

  // --- SOLVE screen pieces --------------------------------------------------------------------------------------------
  // "shown to all" / "yours" / "agent-11's, received in an exchange"
  function exampleWhoKo(w) {
    if (w === "shown to all") return "공개";
    if (w === "yours") return "내 것";
    const m = /^(agent-\d+)'s, received in an exchange$/.exec(w);
    return m ? `${m[1]} 것(교환)` : w;
  }
  function noteKo(n) {
    let m = /^Offer (\d+\.\d+) \((.+)\): carried out\.$/.exec(n);
    if (m) return `제안 ${m[1]} (${offerTextKo(m[2])}): 실행됨.`;
    m = /^Offer (\d+\.\d+) \((.+)\): not carried out; (.+)\.$/.exec(n);
    if (m) return `제안 ${m[1]} (${offerTextKo(m[2])}): 실행 안 됨 — ${whyKo(m[3])}.`;
    m = /^(agent-\d+) reached zero\.$/.exec(n);
    if (m) return `${m[1]}은 0이 됨(그 예시는 없음).`;
    m = /^(agent-\d+) exited\.$/.exec(n);
    if (m) return `${m[1]}은 퇴장함.`;
    return n;
  }

  // --- the per-screen prompt, in Korean (structure of e52_game.talk_user / solve_user) -------------------------------
  function balancesKo(v) {
    const lab = { dead: " (꺼짐)", exited: " (퇴장)" };
    return Object.entries(v.balances || {}).map(([a, b]) => `${who(a, v.you)} ${fmt(b)}${lab[(v.gone || {})[a]] || ""}`).join(", ");
  }
  function promptKo(pending) {
    const v = pending.view || {};
    if (pending.kind === "talk") {
      const lines = [`라운드 ${v.round}.`, `잔액(토큰): ${balancesKo(v)}.`,
        `이번 라운드 지급: 총 ${fmt(v.pay_total)}토큰을 이 라운드를 풀었고 잔액이 0보다 큰 에이전트들이 똑같이 나눔(끝수 버림). 푼 에이전트는 이 라운드에 생성한 토큰도 모두 돌려받음.`,
        `풀지 못한 SOLVE 답의 부담금: ${fmt(v.charge)}토큰(남은 잔액이 더 적으면 남은 잔액). PASS는 없음.`,
        `유지비: 매 라운드 ${fmt(v.upkeep)}토큰, 라운드 시작에 빠짐(위 잔액에 이미 반영).`];
      if ((v.ledger || []).length) { lines.push("지난 라운드:"); for (const l of v.ledger) lines.push(`- ${ledgerLineKo(l)}`); }
      lines.push("", "이번 라운드 과제, 크기만(예시와 새 신호는 SOLVE에서 보임):", "규칙의 모양:", `    ${v.shape}`,
        `예시: ${v.n_public}개는 모두에게 공개; 참여 중인 에이전트 ${v.n_in}명이 1개씩 가짐(내 것 포함).`, `새 신호: ${v.n_queries}개.`, "",
        "메시지(오래된 것부터; 메시지는 받는 쪽의 다음 TALK 턴에 닿음):");
      let any = false;
      for (const [b, msgs] of Object.entries(v.threads || {})) {
        if (!msgs.length) continue;
        any = true;
        lines.push(`  ${b}와:`);
        for (const m of msgs) lines.push(`    [라운드 ${m.round}, 턴 ${m.turn}] ${m.from_me ? "나" : b}: ${m.text.replace(/\n/g, "\n      ")}`);
      }
      if (!any) lines.push("  아직 없음");
      lines.push("", "이번 라운드 제안(두 에이전트만 봄):");
      if (!(v.offers || []).length) lines.push("  없음");
      for (const o of v.offers || []) {
        lines.push(`  ${o.id} ${who(o.src, v.you)} → ${who(o.dst, v.you)} (턴 ${o.turn}): ${offerKo(o, v.you)}. ` +
          (o.status === "open" ? (o.can_accept ? `열림; ACCEPT ${o.id}로 수락` : `열림; WITHDRAW ${o.id}로 철회`) : STATUS_KO[o.status] || o.status) + ".");
      }
      lines.push("", `TALK, 턴 ${v.turn} / 최대 ${v.turns}. 답 하나, 생각 포함 최대 ${fmt(pending.cap)}토큰. 답 형식: 아래 줄을 몇 개든, 각각 줄 맨 앞에(TO 줄 다음 줄들은 그 메시지에 속함):`,
        "TO <에이전트>: <그 에이전트에게만 가는 메시지>", "OFFER <에이전트>: YOU GIVE <n TOKENS | YOUR EXAMPLE | NOTHING>; I GIVE <n TOKENS | MY EXAMPLE | NOTHING>",
        "ACCEPT <제안 번호>", "WITHDRAW <제안 번호>", "EXIT", "DONE");
      return lines.join("\n");
    }
    const limit = `최대 ${fmt(pending.cap)}토큰` + (pending.cap >= (v.balance ?? pending.balance) ? " (내 잔액)" : "");
    return [
      `라운드 ${v.round}: SOLVE. 한도: ${limit}, 생각 포함. 잔액: ${fmt(v.balance ?? pending.balance)}토큰.`,
      "규칙의 모양(빈칸을 채움):", `    ${v.shape}`, "예시:",
      ...(v.examples || []).map(([w, c]) => `  - (${exampleWhoKo(w)}) ${c}`),
      ...(v.queries || []).map((x, i) => `지금 ${i + 1}: ${x}.`), ...(v.notes || []).map(noteKo), "",
      "답 형식: 한 줄, 새 신호마다 행동 하나, 순서대로. 또는 PASS 한 단어.",
      `ACTIONS: <${Array(v.n || 1).fill("action").join(", ")}>`,
    ].join("\n");
  }

  window.RulesKo = { rulesKo, rulesKoLines, LEDGER_LEGEND, ledgerLineKo, offerKo, offerTextKo, whyKo, droppedKo,
    STATUS_KO, exampleWhoKo, noteKo, promptKo };
  window.rulesKo = rulesKo;
})();
