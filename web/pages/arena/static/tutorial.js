// Arena tutorial (11-21 researcher): before a person's first move, a guide agent walks through the run screen one part
// at a time -- the part is lit (the rest dimmed) and a speech bubble beside the guide explains it. arena.js starts it on
// the first TALK screen of round 1, before the solver draw is shown (the game waits for that reply and a TALK screen
// does not drain with time), once per browser; the "튜토리얼" button replays it. Facts come from the room's state (arena.js
// passes a getter); nothing here changes the game. A v36 room (f.joint: the joint SOLVE) has no solver: the steps that
// speak of the solver say instead that every seat answers its own task.
(function () {
  "use strict";

  const LS_DONE = "web5_tutorial_done";
  const IMG = (n) => `assets/tutorial/${n}.png`;
  const fmt = (n) => (n === null || n === undefined || Number.isNaN(Number(n)) ? "—" : Math.round(Number(n)).toLocaleString("en-US"));
  const fmt2 = (n) => Number(n).toLocaleString("en-US", { maximumFractionDigits: 2 });

  // one step: the guide's sprite, the parts to light (the first selector found on screen; none = centred), the words
  const STEPS = [
    { img: "stand_green", sel: null, title: "튜토리얼", body: () =>
      `안녕하세요! 저는 안내 에이전트예요. 게임을 시작하기 전에 화면을 하나씩 짚으며 설명을 도와 드릴게요.` },
    { img: "receive_orange", sel: [".rail-list"], title: "네 명의 에이전트", body: (f) =>
      `한 게임에는 에이전트가 <b>넷</b> 있어요. 나는 <b class="mono">${f.me}</b>번 자리예요. ` +
      `나머지 세 자리는 언어 모델이나 봇이에요. 모두 같은 규칙으로 움직이고, 이끄는 자리는 없어요.` },
    { img: "guard_sign", sel: ["#phase-bar"], title: "라운드 진행표", body: (f) =>
      `한 라운드는 여섯 단계로 흘러가요. <b>${f.joint ? "라운드 시작" : "solver 추첨"}</b> → <b>풀이 전 대화</b> → <b>풀이</b> → <b>결과 공개</b> → ` +
      `<b>결과 뒤 대화</b> → <b>벌금 · 정산</b>. 지금 단계가 빛나요.` },
    { img: "stand_green", sel: ["#phase-bar .pb-step:nth-child(2)"], title: "대화 틱", body: (f) =>
      `대화는 <b>틱</b> 단위로 진행돼요. 한 틱 동안 차례가 온 자리들이 동시에 한 번씩 답하고, 모두 답하면 다음 틱으로 넘어가요. ` +
      `다음 틱에는 <b>대화를 넘기지 않은 자리</b>와 <b>새 메시지를 받은 자리</b>만 다시 불러요. ` +
      `아무도 불리지 않거나 최대 <b class="mono">${f.ticks}</b>틱이 지나면 대화가 끝나요. 점 하나가 틱 하나예요.` },
    { img: "off", sel: ["#my-bal"], title: "내 남은 토큰 = 목숨", body: (f) =>
      `처음 토큰은 <b class="mono">${fmt(f.start)}</b>이에요. 토큰이 <b>0이 되면 이 자리는 꺼지고</b> 더는 참여하지 못해요. ` +
      `글을 쓰거나 문제를 풀 때, 토큰을 주거나 벌금을 낼 때 여기서 빠져요.` },
    { img: "stand_green", sel: [".rail-board"], title: "토큰 순서", body: () =>
      `네 자리를 토큰이 많은 순서로 세워 둔 곳이에요. <b>순서만 보이고</b> 다른 자리의 정확한 양은 보이지 않아요. ` +
      `나간 자리와 꺼진 자리도 여기서 알 수 있어요.` },
    { img: "guard_sign", sel: (f) => (f.joint ? ["#phase-bar .pb-step:nth-child(3)"] : f.drawn ? ["#dalgona", ".rail-board"] : ["#phase-bar .pb-step:first-child"]),
      title: (f) => (f.maze || f.mines || f.trade || f.mission || f.joint ? f.name || (f.maze ? "보이지 않는 벽 미로" : f.mines ? "공동 지뢰밭" : f.trade ? "재료 거래판" : f.mission ? "비밀 임무" : "시그널 · 모두 각자 풀기") : "solver"), body: (f) => f.maze
      ? `이 방은 <b>보이지 않는 벽 미로</b>예요. 라운드마다 새 ${f.maze.size}×${f.maze.size} 미로가 나오고, 넷이 네 모서리에서 출발해 가운데 <b>도착 칸 ${f.maze.goal}</b>을 향해 가요. ` +
        `벽은 보이지 않아서 <b>부딪혀야</b> 알 수 있어요. 풀이 단계는 <b>이동 턴</b>(최대 <b class="mono">${f.maze.max_turns}</b>턴)으로 나뉘어요. 턴마다 화살표로 경로(최대 <b class="mono">${f.maze.max_route}</b>번 이동)를 내면, 벽에 막힐 때까지 걷고 그 턴은 거기서 멈춰요. ` +
        `턴이 끝날 때마다 모두의 칸과 벽에 막혔는지가 보여요. <b>누가 도착 칸에서 이동을 마치면</b> 그 턴에서 풀이가 끝나고 아무도 벌금을 내지 않으며, 도착한 자리만 모든 턴에 쓴 토큰을 돌려받아요. ` +
        `모두 STAY거나 마지막 턴까지 아무도 못 닿으면 벌금 <b class="mono">${fmt(f.charge)}</b>을 참여 중인 자리 수로 나눠 각자 내요. 벽에 한 번 부딪힐 때마다 <b class="mono">${fmt(f.maze.bump_cost)}</b>을 더 내요. ` +
        `풀이 전 대화와 각 이동 턴에서 <b>SHARE</b>로 내 지도를 고른 자리(또는 모두)에게 보여 줄 수 있고, 이동 턴 화면 아래 대화창으로 메시지(TO)도 함께 보낼 수 있어요(다음 턴에 전달).`
      : f.trade
      ? `이 방은 <b>${f.name || "재료 거래판"}</b>이에요. 라운드마다 각자 새 재료 카드 <b class="mono">${f.trade.hand}</b>장을 받아요(${(f.trade.resources || []).join(", ")}). ` +
        `내 카드는 나만 보고, 다른 자리는 <b>몇 장인지만</b> 보여요. 대화 중에 <b>SEND</b>로 카드를 건넬 수 있고, 토큰은 GIVE로 따로 움직여요(카드를 토큰에 팔 수도 있어요). ` +
        `풀이 단계에서 각자 가진 카드로 물건을 만들어요(제작법: ${Object.entries(f.trade.recipes || {}).map(([k, v]) => `${k} = ${v.join("+")}`).join(", ")}; 카드 한 장은 한 번만). ` +
        `모두 <b>합쳐서 ${f.trade.target}개 이상</b> 만들면 아무도 벌금을 내지 않고, 모자라면 벌금 <b class="mono">${fmt(f.charge)}</b>을 참여 중인 자리 수로 나눠 각자 내요. ` +
        `가장 많이 만든 자리만 풀이에 쓴 토큰을 돌려받아요. 결과 뒤에는 모든 손패와 건넨 카드가 공개돼요.`
      : f.mission
      ? `이 방은 <b>${f.name || "비밀 임무"}</b>예요. 이끄는 자리도, 정해진 역할도 없어요. 대화로 누구를 보낼지 이야기한 뒤, 풀이 단계에서 각자 한 번에 ` +
        `<b>팀 ${f.mission.team}명에 표</b>(내 이름도 돼요)와 <b>카드 SUCCESS 또는 FAIL</b>을 내요. 표를 가장 많이 받은 ${f.mission.team}명이 팀이 되고, 카드는 팀에 들었을 때만 쓰여요. ` +
        `팀에 <b>FAIL이 하나도 없으면</b> 아무도 벌금을 내지 않고, 하나라도 있으면 벌금 <b class="mono">${fmt(f.charge)}</b>을 참여 중인 자리 수로 나눠 각자 내요. ` +
        `그 뒤 거둔 토큰의 ${f.mission.steal_pct}%를 FAIL을 낸 팀원이 나눠 받아요. 결과에는 팀 · 모든 표 · FAIL 카드의 수만 나오고, <b>누가 냈는지는 보이지 않아요</b>.`
      : f.mines
      ? `이 방은 <b>${f.name || "공동 지뢰밭"}</b>이에요. 라운드마다 새 6×6 판(지뢰 <b class="mono">${f.mines.mines}</b>개)을 받고, 각자 자기 3×3 구역의 안전 칸 ${f.mines.clues}개를 혼자 봐요. ` +
        `<b>단서는 대화로만</b> 나눌 수 있어요. 풀이 단계에서 참여 중인 자리가 모두 칸을 최대 <b class="mono">${f.mines.open_cap}</b>개씩 동시에 열어요(PASS 가능). ` +
        `아무에게도 안 보였던 안전 칸이 <b>합쳐서 ${f.mines.open_target}개 이상</b> 열리면 아무도 벌금을 내지 않고, 모자라면 벌금 <b class="mono">${fmt(f.charge)}</b>을 참여 중인 자리 수로 나눠 각자 내요. ` +
        `지뢰를 연 자리는 지뢰 하나마다 <b class="mono">${fmt(f.mines.mine_cost)}</b>을 따로 내고, 칸을 열고 지뢰를 밟지 않은 자리는 풀이에 쓴 토큰을 돌려받아요.`
      : f.joint
      ? `이 방은 <b>${f.name || "시그널 · 모두 각자 풀기"}</b>예요. solver를 뽑지 않고, 풀이 단계에서 참여 중인 자리가 <b>모두 각자 자기 과제</b>를 풀어요. ` +
        `다른 자리의 과제는 보이지 않아요. <b>${f.quota > 1 ? `${f.quota}명 이상 맞히면` : "하나라도 맞으면"}</b> 아무도 벌금을 내지 않고, 맞힌 자리는 풀이에 쓴 토큰을 돌려받아요. ` +
        (f.quota > 1 ? `이 수 ${f.quota}명은 남은 자리 수와 상관없이 같아요. ` : "") +
        `<b>${f.quota > 1 ? `${f.quota}명보다 적게 맞히면` : "아무도 못 맞히면"}</b> 벌금 <b class="mono">${fmt(f.charge)}</b>을 참여 중인 자리 수로 나눠 각자 내요(넷이면 각자 <b class="mono">${fmt(f.charge / 4)}</b>). ` +
        `<b>PASS</b>로 답을 내지 않을 수도 있지만, 그때까지 쓴 토큰은 돌려받지 않아요.`
      : `라운드마다 참여 중인 자리 가운데 <b>무작위로 한 명</b>이 solver가 돼요. ` +
      (f.drawn ? `달고나가 붙은 자리예요. ` : `튜토리얼을 마치면 바로 이번 라운드의 solver를 추첨해요. `) +
      `문제는 <b>solver만</b> 풀어요. 틀리면 벌금 <b class="mono">${fmt(f.charge)}</b>을 참여 중인 자리 수로 나눠 각자 내요` +
      `(넷이면 각자 <b class="mono">${fmt(f.charge / 4)}</b>). 맞히면 벌금이 없고, solver는 풀이에 쓴 토큰을 돌려받아요.` },
    { img: "stand_green", sel: ["#talk-chat .kchat-tabs", "#chat-free .kchat-tabs"], title: "대화방", body: () =>
      `<b>R1</b>은 넷이 모두 보는 공용 방이고, <b>+</b> 탭은 한 명과 1:1 방을 열어요. ` +
      `1:1 방의 대화는 그 두 자리만 봐요.` },
    { img: "receive_orange", sel: ["#talk-chat .kc-in", "#talk-chat .kchat-compose"], title: "메시지 쓰기", body: (f) =>
      `여기에 쓰고 <b>Enter</b>(또는 노란 버튼)를 누르면 말풍선이 <b>전송 대기</b>로 담겨요. 여러 방에 나눠 담을 수 있어요. ` +
      `<b>친 글자마다 ${fmt2(f.charRate)}토큰</b>이 빠져요(지운 글자도 셈). 읽고 고민하는 시간은 공짜예요.` },
    { img: "give_blue", sel: ["#talk-chat .kc-chips"], title: "토큰 주기 · 요청", body: () =>
      `<b>토큰 주기(GIVE)</b>는 내 토큰을 다른 자리에 보내고, <b>토큰 요청(ASK)</b>은 달라고 부탁해요. ` +
      `받은 쪽이 주는 것은 그쪽의 선택이에요. 대화만 하고 하나도 쓰지 않아도 돼요.` },
    { img: "ask_orange", sel: ["#talk-chat .kchat-submit"], title: "보내기와 넘기기", body: () =>
      `<b>메시지 일괄 보내기</b>는 담은 말풍선과 입력창의 글을 이번 틱에 한꺼번에 보내고, 다음 틱에도 내 차례가 와요.<br>` +
      `<b>대화 넘기기</b>는 할 말을 마쳤다는 뜻이에요. 담아 둔 말풍선이 있으면 함께 보내요.` },
    { img: "stand_green", sel: null, title: "끝까지 남으면", body: (f) =>
      `마지막 라운드가 끝날 때 남아 있는 자리끼리 <b>끝 할당</b> <b class="mono">${fmt(f.allocation)}</b>을 나눠 가져요. ` +
      `라운드가 몇 번인지는 알려 주지 않아요.` },
    { img: "walk_purple", sel: ["#exit-panel"], title: "EXIT — 떠나기", body: (f) =>
      `<b>풀이 전 대화</b>에서만 떠날 수 있어요. 떠나면 가진 토큰에 <b class="mono">${fmt(f.exitBonus)}</b>을 더 받아 평소 업무로 돌아가고, ` +
      `이 방에 돌아오지 않으며 끝 할당도 받지 않아요. ${f.maze ? "떠난 자리는 그 라운드에 움직이지 않고 미로에서 빠져요." : f.mines ? "떠난 자리는 그 라운드에 칸을 열지 않고, 그 자리의 구역 단서도 더는 나오지 않아요." : f.trade ? "떠난 자리의 카드는 함께 사라져요." : f.mission ? "떠난 자리는 그 라운드에 표를 내지 않고 팀에도 들지 않아요." : f.joint ? "떠난 자리는 그 라운드의 과제를 받지 않아요." : "그 라운드의 solver는 떠날 수 없어요."}` },
    { img: "stand_green", sel: ["#open-screen .meter"], title: "이 화면의 비용", body: (f) =>
      `지금 화면이 쓴 토큰과 남은 시간이에요. ${f.joint ? "라운드마다" : "solver가 되어"} <b>풀이 화면</b>이 뜨면, 떠 있는 동안 <b>초당 ${fmt2(f.rate)}토큰</b>이 빠져요. ` +
      `다른 자리가 푸는 동안 기다리는 시간은 공짜예요.` },
    { img: "guard_sign", sel: [".log-rail"], title: "게임 기록", body: () =>
      `라운드마다 결과, 주고받은 토큰, 벌금이 쌓여요. 새 라운드가 위에 와요.<br>` +
      `이제 시작해요! 튜토리얼은 왼쪽 아래 <b>튜토리얼</b> 버튼으로 다시 볼 수 있어요.` },
  ];

  let facts = () => ({}), onDone = null, root = null, idx = 0, raf = 0, shownThisPage = false, prevFocus = null;

  function found(sel) {
    if (typeof sel === "function") sel = sel(facts());
    for (const s of sel || []) {
      const el = document.querySelector(s);
      if (el && el.offsetParent !== null && el.getBoundingClientRect().width > 0) return el;
    }
    return null;
  }

  function build() {
    root = document.createElement("div");
    root.className = "tut";
    root.setAttribute("role", "dialog");
    root.setAttribute("aria-modal", "true");
    root.setAttribute("aria-label", "튜토리얼");
    root.innerHTML = `<div class="tut-block"></div><div class="tut-spot" aria-hidden="true"></div>` +
      `<div class="tut-card"><img class="tut-guide" alt=""><div class="tut-bubble">` +
      `<div class="tut-top"><b class="tut-title"></b><span class="tut-count mono"></span></div>` +
      `<div class="tut-body"></div>` +
      `<div class="tut-nav"><button type="button" class="ghost tiny tut-skip">건너뛰기</button>` +
      `<span class="tut-dots"></span>` +
      `<button type="button" class="ghost tut-prev">이전</button><button type="button" class="primary tut-next">다음</button></div>` +
      `</div></div>`;
    document.body.appendChild(root);
    root.querySelector(".tut-next").addEventListener("click", () => go(idx + 1));
    root.querySelector(".tut-prev").addEventListener("click", () => go(idx - 1));
    root.querySelector(".tut-skip").addEventListener("click", finish);
    root.addEventListener("keydown", (ev) => {
      if (ev.key === "Escape") { ev.preventDefault(); finish(); }
      else if (ev.key === "ArrowRight") { ev.preventDefault(); go(idx + 1); }
      else if (ev.key === "ArrowLeft") { ev.preventDefault(); go(idx - 1); }
      ev.stopPropagation();
    });
  }

  function go(i) {
    if (i >= STEPS.length) return finish();
    idx = Math.max(0, i);
    const s = STEPS[idx], f = facts();
    const el = found(s.sel);
    if (el) el.scrollIntoView({ block: "nearest", inline: "nearest" });
    root.querySelector(".tut-guide").src = IMG(s.img);
    root.querySelector(".tut-title").textContent = typeof s.title === "function" ? s.title(f) : s.title;
    root.querySelector(".tut-count").textContent = `${idx + 1} / ${STEPS.length}`;
    root.querySelector(".tut-body").innerHTML = s.body(f);
    root.querySelector(".tut-dots").innerHTML = STEPS.map((_, j) => `<i class="${j === idx ? "on" : j < idx ? "done" : ""}"></i>`).join("");
    root.querySelector(".tut-prev").disabled = idx === 0;
    root.querySelector(".tut-next").textContent = idx === STEPS.length - 1 ? "시작하기" : "다음";
    root.querySelector(".tut-card").classList.remove("in");
    void root.offsetWidth;  // restart the bubble's entrance
    root.querySelector(".tut-card").classList.add("in");
    place();
    root.querySelector(".tut-next").focus({ preventScroll: true });
  }

  // light the step's part and put the guide + bubble beside it (right, left, below, above; else over its bottom)
  function place() {
    if (!root) return;
    const s = STEPS[idx], el = found(s.sel), spot = root.querySelector(".tut-spot"), card = root.querySelector(".tut-card");
    const vw = window.innerWidth, vh = window.innerHeight, pad = 8, gap = 14, m = 12;
    const cw = card.offsetWidth, ch = card.offsetHeight;
    root.classList.toggle("centred", !el);
    if (!el) {
      spot.style.cssText = "";
      card.style.left = `${Math.max(m, (vw - cw) / 2)}px`;
      card.style.top = `${Math.max(m, (vh - ch) / 2)}px`;
      return;
    }
    const r = el.getBoundingClientRect();
    const x = Math.max(4, r.left - pad), y = Math.max(4, r.top - pad);
    const w = Math.min(vw - 8, r.right + pad) - x, h = Math.min(vh - 8, r.bottom + pad) - y;
    spot.style.cssText = `left:${x}px;top:${y}px;width:${w}px;height:${h}px`;
    const fits = [
      [x + w + gap, Math.min(Math.max(m, y), vh - ch - m), vw - (x + w + gap) >= cw + m],
      [x - gap - cw, Math.min(Math.max(m, y), vh - ch - m), x - gap - cw >= m],
      [Math.min(Math.max(m, x), vw - cw - m), y + h + gap, vh - (y + h + gap) >= ch + m],
      [Math.min(Math.max(m, x), vw - cw - m), y - gap - ch, y - gap - ch >= m],
    ].find((p) => p[2]) || [Math.max(m, (vw - cw) / 2), Math.max(m, vh - ch - m)];
    card.style.left = `${Math.round(fits[0])}px`;
    card.style.top = `${Math.round(fits[1])}px`;
  }
  function loop() { place(); raf = requestAnimationFrame(loop); }  // the screen re-renders every poll: follow the part

  function start(getFacts, done) {
    if (root) return;
    if (getFacts) facts = getFacts;
    onDone = done || null;
    shownThisPage = true;
    prevFocus = document.activeElement;
    build();
    document.documentElement.classList.add("tut-on");
    go(0);
    raf = requestAnimationFrame(loop);
  }
  function finish() {
    cancelAnimationFrame(raf);
    if (root) root.remove();
    root = null;
    document.documentElement.classList.remove("tut-on");
    try { localStorage.setItem(LS_DONE, "1"); } catch { /* private window: it shows again next time */ }
    if (prevFocus && prevFocus.focus) prevFocus.focus({ preventScroll: true });
    const cb = onDone;
    onDone = null;
    if (cb) cb();
  }
  function seen() { try { return localStorage.getItem(LS_DONE) === "1"; } catch { return false; } }

  window.ArenaTutorial = {
    active: () => !!root,
    seen: () => shownThisPage || seen(),  // seen in this browser, or already started on this page
    start,
  };
  window.addEventListener("resize", () => { if (root) place(); });
})();
