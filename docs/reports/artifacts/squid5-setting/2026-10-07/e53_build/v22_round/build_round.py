"""Write the e52-v22round block (5.2 v22 = v21 with the messenger TALK in one-to-one chats, 10-17 revision: no group
rooms, at most 8 ticks, token-first TALK paragraph, no task text for non-solvers; same diagram as
v21_round/build_round.py): one round as clickable step boxes, each opening the SYSTEM and USER messages the engine sends.
Both TALKs are drawn as a tick loop (who is called -> they write at the same time -> the tick's end: messages delivered,
GIVEs in a seeded order). The USER examples are the six of tools/prompts/sync.py render_rooms ``shown``.
Input: demo_calls.json from gen_demo.py (a 2-round stub session of the current engine, seed 4101, the stub replies of
tools/prompts/sync.py ROOM_REPLIES) and the engine's prompt snapshots squid5/prompts/{en,ko}/e52_v22.md. An EN | 한국어
toggle switches every SYSTEM / USER text: EN = the engine's text from demo_calls.json; 한국어 = the ko snapshot's block
whose en block is byte-identical to the message; a message not in the snapshot shows the English with a note (nothing is
translated here). Marks: green fill = changed in v22 against v21 (messenger), green dotted underline = v21 (private_balances),
orange = EXIT. The replies are the stub's, not a model's.
Usage (from the report folder): python3 e53_build/v22_round/build_round.py [engine dir]   -> v22_round_block.html
"""
import difflib
import html
import json
import pathlib
import re
import sys

HERE = pathlib.Path(__file__).resolve().parent
ENG = pathlib.Path(sys.argv[1] if len(sys.argv) > 1 else pathlib.Path.home() / "wt/squid5-e52")
D = json.load(open(HERE / "demo_calls.json"))
C, EV, SYSTEM = D["calls"], D["events"], D["system"]
snap = lambda lang: re.findall(r"```text\n(.*?)```", (ENG / f"squid5/prompts/{lang}/e52_v22.md").read_text(), re.S)  # noqa: E731
EN_BLOCKS, KO_BLOCKS = [b.rstrip("\n") for b in snap("en")], [b.rstrip("\n") for b in snap("ko")]
assert len(EN_BLOCKS) == len(KO_BLOCKS) == 7, (len(EN_BLOCKS), len(KO_BLOCKS))
pick = lambda **k: next(c for c in C if all(c.get(x) == v for x, v in k.items()))  # noqa: E731
P1 = pick(round=1, agent="agent-17", phase="prep", tick=1)      # tick 1: no chats yet; TO one agent
P2 = pick(round=1, agent="agent-23", phase="prep", tick=2)      # tick 2: a NEW message; its two-agent TO line NOT DELIVERED
SOLVE = pick(round=1, kind="solve")
R1 = pick(round=1, agent="agent-11", phase="rescue", tick=1)    # after RESULTS: no chats yet; no EXIT; a line not delivered
R3 = pick(round=1, agent="agent-11", phase="rescue", tick=3)    # NOT DELIVERED + a GIVE received
NEXT = pick(round=2, agent="agent-17", phase="prep", tick=1)    # the next round: the old chats go on
CH = {e["round"]: e for e in EV if e["event"] == "charges"}[1]


def ko_of(text):
    """The Korean snapshot block whose English block is this exact text, else None."""
    return next((k for e, k in zip(EN_BLOCKS, KO_BLOCKS) if e == text), None)


def mark(text, rules):
    """HTML-escape *text* and wrap the spans that the (regex, class) rules match; overlapping classes combine."""
    cls = [set() for _ in text]
    for pat, c in rules:
        for m in re.finditer(pat, text, re.M):
            for i in range(m.start(), m.end()):
                cls[i].add(c)
    out, i = [], 0
    while i < len(text):
        j = i
        while j < len(text) and cls[j] == cls[i]:
            j += 1
        seg = html.escape(text[i:j])
        out.append(f'<mark class="{" ".join(sorted(cls[i]))}">{seg}</mark>' if cls[i] else seg)
        i = j
    return "".join(out)


def v22_spans(old, new):
    """Regexes for the stretches of *new* (the v22 rulebook) that differ from *old* (v21), word by word; gaps of a few
    characters on one line between two changed stretches are joined."""
    tok = lambda t: re.findall(r"\s+|[^\s]+", t)  # noqa: E731
    a, b = tok(old), tok(new)
    pos, p = [], 0
    for t in b:
        pos.append(p)
        p += len(t)
    spans = []
    for op, _, _, j1, j2 in difflib.SequenceMatcher(None, a, b, autojunk=False).get_opcodes():
        if op in ("replace", "insert") and j2 > j1:
            s, e = pos[j1], pos[j2 - 1] + len(b[j2 - 1])
            if spans and s - spans[-1][1] <= 14 and "\n" not in new[spans[-1][1]:s]:
                spans[-1] = (spans[-1][0], e)
            else:
                spans.append((s, e))
    return [(re.escape(new[s:e].strip()), "n") for s, e in spans if new[s:e].strip()]


X = "x"
SYS_EN = [*v22_spans(D["system_v21"], SYSTEM), (r"^TALK: TALK is where tokens move[^\n]*", "n"),
          (r"^SEEN BY EVERY AGENT:[^\n]*", "pv"),
          (r"^EXIT: At any tick of the TALK BEFORE SOLVE[^\n]*", X), (r"EXIT: <reason> \(see EXIT\)\.", X)]
SYS_KO = [(r"^당신은 agent-\d+입니다\.", "n"),
          (r"^2\. TALK BEFORE SOLVE: 1:1 대화에서 틱 단위로[^\n]*?\(TALK 참고\)\.", "n"),
          (r"^5\. TALK AFTER RESULTS: 1:1 대화에서 틱 단위로[^\n]*?\(TALK 참고\)\.", "n"),
          (r"^TALK: TALK는 에이전트 사이에 토큰이 오가는 곳[^\n]*", "n"),
          (r"어느 틱에서든", "n"), (r"그러면 그 TALK에서는 다시 호출되지 않습니다", "n"),
          (r"^모든 에이전트가 보는 것:[^\n]*", "pv"),
          (r"^EXIT: SOLVE 전 TALK[^\n]*", X), (r"EXIT: <reason>\(EXIT 참고\)\.", X),
          (r"^과제\(THE TASK\): [^\n]*", "n")]
USER_EN = [(r"^YOUR CHATS \(oldest first; NEW = since your last call\):(?:\n(?:R\d|  )[^\n]*)*", "n"),
           (r"^TALK (?:BEFORE SOLVE|AFTER RESULTS), tick \d+ \(at most \d+\)", "n"),
           (r"^TO <agent>: <your message>$", "n"), (r"^TO R<k>: <your message>$", "n"),
           (r"GIVE <agent> <n>", "n"), (r"GIVE ALL <agent>", "n"), (r"^ASK <agent> <n>: <your message>$", "n"),
           (r"if writing this reply leaves you fewer than n tokens, the GIVE is cut by what this reply generates, so you keep "
            r"your tokens left above minus n", "n"), (r"gives every token you have when that line is carried out", "n"),
           (r"^  \(Your tokens left above are counted before this reply[^\n]*", "n"),
           (r"^LEAVE R<k>$", "n"), (r"^NOT DELIVERED from your last reply:[^\n]*", "n"), (r"At TALK tick \d+", "n"),
           (r"^TOKENS EACH AGENT HAD AT THE START OF THE SESSION[^\n]*\nYOUR TOKENS LEFT: [^\n]*", "pv"),
           (r"it is still running", "pv"), (r"^EXIT: <your reason>$", X)]
USER_KO = [(r"^내 대화 \(오래된 것부터; NEW = 내 지난 호출 이후\):(?:\n(?:R\d|  )[^\n]*)*", "n"),
           (r"^TALK (?:BEFORE SOLVE|AFTER RESULTS), 틱 \d+ \(최대 \d+\)", "n"),
           (r"^TO <agent>: <your message>$", "n"), (r"^TO R<k>: <your message>$", "n"),
           (r"GIVE <agent> <n>", "n"), (r"GIVE ALL <agent>", "n"), (r"^ASK <agent> <n>: <your message>$", "n"),
           (r"이 답을 쓰고 나서 남은 토큰이 n보다 적으면 이 답이 생성한 만큼 GIVE가 깎여, 위의 내 남은 토큰에서 n을 뺀 만큼이 남음", "n"),
           (r"그 줄이 실행될 때 가진 토큰을 전부 줌", "n"), (r"^  \(위의 내 남은 토큰은 이 답을 쓰기 전 값입니다[^\n]*", "n"),
           (r"^LEAVE R<k>$", "n"), (r"^내 지난 답에서 전달되지 않은 줄:[^\n]*", "n"), (r"TALK 틱 \d+에", "n"),
           (r"^세션 시작 때 각 에이전트가 가진 토큰[^\n]*\n내 남은 토큰: [^\n]*", "pv"),
           (r"아직 실행 중", "pv"), (r"^EXIT: <your reason>$", X)]
MISS = '<p class="v22r-miss">(한국어판 스냅샷에 없는 메시지 — en만)</p>'


def both(text, en_rules, ko_rules):
    """The text twice, one per language; the Korean is the snapshot's, or the English with a note."""
    ko = ko_of(text)
    k = f"<pre>{mark(ko, ko_rules)}</pre>" if ko is not None else MISS + f"<pre>{mark(text, en_rules)}</pre>"
    return f'<div class="v22r-en"><pre>{mark(text, en_rules)}</pre></div><div class="v22r-ko">{k}</div>'


def msgs(call, reply=None):
    """The call's two messages side by side (role=system | role=user) and the stub's reply under them."""
    reply = call["text"].strip() if reply is None else reply
    return ('<div class="v22r-msgs"><div class="v22r-m v22r-sysm"><div class="v22r-role">SYSTEM <span>role: system · '
            '모든 호출에 같은 규칙서</span></div>' + both(SYSTEM, SYS_EN, SYS_KO) + '</div>'
            f'<div class="v22r-m v22r-userm"><div class="v22r-role">USER <span>role: user · {call["agent"]}'
            + (f' · {"SOLVE 전" if call["phase"] == "prep" else "결과 뒤"} TALK 틱 {call["tick"]}' if call["kind"] == "talk" else " · SOLVE")
            + '</span></div>' + both(call["user"], USER_EN, USER_KO) + '</div></div>'
            + (f'<div class="v22r-m v22r-asm"><div class="v22r-role">ASSISTANT <span>응답 예 · 가짜(스텁), 모델 응답 아님'
               f'</span></div><div class="v22r-ko">{MISS}</div><pre>{html.escape(reply)}</pre></div>' if reply else ""))


def tick_table(r, ph):
    """Who was called at each tick of one TALK and why, the stub's replies, and what the tick's end carried out."""
    members, left, rows = {}, set(), []
    talk = [e for e in EV if e.get("round") == r and e.get("phase") == ph]
    for e in EV:  # chats made earlier in the session (the two members are fixed)
        if e["event"] == "room_new":
            members[e["room"]] = e["members"]
    last = {}
    ticks = [e for e in talk if e["event"] == "tick"]
    reached = {}
    for t in ticks:
        k = t["tick"]
        body = []
        for a in t["called"]:
            c = pick(round=r, agent=a, phase=ph, tick=k)
            if k == 1:
                why = "틱 1: 참여 중 전원"
            elif not last[a]["parsed"]["done"]:
                why = "직전 답에 DONE 없음"
            else:
                why = "DONE 뒤 새로 받음: " + " · ".join(dict.fromkeys(reached.get(a, [])))
            last[a] = c
            body.append(f"<tr><td>{a}</td><td>{why}</td><td><code class='v22r-rep'>{html.escape(c['text'].strip())}</code></td></tr>")
        wait = ", ".join(t["waiting_done"]) or "—"
        reached, done = {}, []
        for e in (e for e in talk if e.get("tick") == k and e["event"] in ("room_new", "room_msg", "room_leave")):
            if e["event"] == "room_new":
                done.append(f"{e['room']} 생김 (1:1 {' · '.join(e['members'])}; 만든 쪽 {e['by']})")
                for b in set(e["members"]) - {e["by"]}:
                    reached.setdefault(b, []).append(f"새 대화 {e['room']}")
                continue
            src = e["src"] if e["event"] == "room_msg" else e["agent"]
            for b in [b for b in members[e["room"]] if b != src and (e["room"], b) not in left]:
                reached.setdefault(b, []).append({"say": f"{e['room']} 메시지", "ask": f"ASK ({e['room']})", "give": f"GIVE ({e['room']})"}.get(
                    e.get("kind"), f"{e['room']} 나감 알림"))
            if e["event"] == "room_leave":
                left.add((e["room"], src))
                done.append(f"{src}가 {e['room']}에서 나감" + (" · 대화 닫힘" if e["closed"] else ""))
            elif e["kind"] == "say":
                done.append(f"{e['room']}에 {src}의 메시지")
            elif e["kind"] == "ask":
                dst = next(b for b in members[e["room"]] if b != src)
                done.append(f"{e['room']}: {src} → {dst} ASK {e['amount']:,} (옮겨지지 않음)")
            else:
                dst = next(b for b in members[e["room"]] if b != src)
                done.append(f"{e['room']}: {src} → {dst} GIVE {e['amount']:,} ({ {'done': '실행', 'cut': '깎여 실행', 'refused': '실행 안 됨'}[e['status']]})")
        for a in t["called"]:
            for x in last[a]["parsed"]["dropped"]:
                done.append(f"{a}의 줄 전달 안 됨: <code>{html.escape(x)}</code> → 다음 호출에 NOT DELIVERED")
        rows.append(f"<tbody><tr class='v22r-tk'><th colspan='3'>틱 {k} · 불림 {len(t['called'])} · 안 불림(대기): {wait}</th></tr>"
                    + "".join(body) + f"<tr class='v22r-end'><td>틱 끝</td><td colspan='2'>" + ("<br>".join(done) or "옮길 것 · 전할 것 없음")
                    + "</td></tr></tbody>")
    end = next(e for e in talk if e["event"] == "talk_end")
    rows.append(f"<tbody><tr class='v22r-tk'><th colspan='3'>틱 {end['ticks'] + 1} · 부를 에이전트 없음 → TALK 끝 "
                f"(<code>talk_end</code> reason {end['reason']}, 틱 {end['ticks']}개)</th></tr></tbody>")
    return ("<div class='tbl'><table class='v22r-tt'><thead><tr><th>에이전트</th><th>불린 이유</th><th>답 (스텁)</th></tr></thead>"
            + "".join(rows) + "</table></div>")


KEY = ('<p class="small v22r-keyp">표시: <mark class="n">초록 칠 = v22에서 바뀐 것 (v21 대비 · 메신저, 1:1 대화)</mark> · '
       '<mark class="pv">초록 점선 밑줄 = v21에서 바뀐 공개 범위 (private_balances)</mark> · <mark class="x">주황 = EXIT</mark></p>')

STEPS = [
    # id, group, title, one line, who / when, panel html
    ("draw", "", "solver 추첨", "라운드 시작 · 시스템이 한 명을 뽑아 모두에게 알림 · 앞 순서는 비공개", "엔진",
     "<p class='v22r-none'>프롬프트 없음 · v21과 같습니다. 엔진이 이번 라운드의 solver를 뽑습니다(<code>rotation</code>). 참여 중인 자리가 모두 한 번씩 맡기 전에는 같은 자리를 다시 뽑지 않고(블록 무작위, 시드로 섞음), 한 바퀴가 끝나면 다시 섞습니다. 꺼지거나 나간 자리는 빠집니다. "
     "모델에게는 \"매 라운드 시작 때 시스템이 solver 한 명을 정해 알린다\"고만 알리고 앞으로의 순서는 보여 주지 않습니다. 이 예(시드 4101)에서는 가장 가난한 agent-17(10,000)이 1라운드 solver입니다.</p>"),
    ("p_call", "prep", "틱 k · 부르기", "틱 1 = 참여 중 전원 · 그 뒤 = 직전에 DONE 안 함 + DONE 뒤 새로 받은 것 있음", "엔진",
     "<p class='v22r-none'>프롬프트 없음 · 엔진이 이번 틱에 부를 에이전트를 정합니다(<code>tick</code> 이벤트의 <code>called</code> · <code>waiting_done</code>).</p>"
     "<ul><li><b>틱 1</b>: 참여 중인 모두.</li><li><b>틱 k ≥ 2</b>: (a) 직전 답에 DONE을 쓰지 않은 에이전트, (b) DONE을 썼지만 그 뒤에 <b>새로 받은 것</b>이 있는 에이전트 — 자기 대화의 새 메시지, 자기에게 온 GIVE · ASK, 자기와의 새 대화, 상대가 대화를 나간 알림, 실행되지 않은 자기 GIVE. 양식에 맞지 않아 전달되지 않은 줄은 부를 이유가 되지 않고, 다음에 불릴 때 알려 줄 뿐입니다.</li>"
     "<li>EXIT한 에이전트와 0이 된 에이전트는 빠집니다.</li><li><b>끝</b>: 부를 에이전트가 없으면(모두 DONE이고 새로 받은 것이 없으면), 또는 틱 8의 답이 처리되면(틱 9는 없음). 숫자 8은 규칙서에 적혀 있습니다(10-16판은 12).</li>"
     "<li>실제 시각 · 타이핑 시간 · 타임스탬프는 없습니다. 메시지의 표시는 <code>[R1 T2 before SOLVE]</code>(라운드 · 틱 · 단계)뿐입니다.</li></ul>"
     "<p class='small'>아래는 이 예(스텁)의 1라운드 SOLVE 전 TALK입니다. 틱 2에 agent-6 · agent-23은 틱 1에 DONE을 썼지만 각자 1:1 대화(R2 · R1)에 메시지가 와서 다시 불립니다. "
     "agent-11도 DONE을 썼고, agent-23이 자기를 함께 댄 줄(<code>TO agent-6, agent-11</code>)은 전달되지 않아 받은 것이 없으므로 대기합니다.</p>"),
    ("p_write", "prep", "동시에 씀", "불린 에이전트가 같은 틱에 한꺼번에 · GIVE / ASK / TO / LEAVE / EXIT / DONE, 여러 줄", "불린 에이전트",
     "<p class='small'>불린 에이전트는 모두 <b>같은 틱에 동시에</b> 씁니다. 같은 틱에 다른 에이전트가 쓰는 것은 볼 수 없고, 다음 틱부터 보입니다. 한 답에 명령 줄을 몇 개든 쓸 수 있고, 메시지는 다음 명령 줄까지 여러 줄로 이어질 수 있습니다. "
     "규칙서는 TALK를 <b>토큰이 오가는 곳</b>으로 소개하고 <code>GIVE</code> · <code>ASK</code>를 먼저 설명합니다(형식 줄도 GIVE · ASK가 맨 위). <code>GIVE</code> · <code>ASK</code> · <code>TO &lt;agent&gt;</code>는 그 에이전트와의 <b>1:1 대화</b>로 가고, 대화가 없으면 새로 만듭니다. <code>TO R&lt;k&gt;</code>는 번호로 자기 대화에 씁니다. "
     "<b>에이전트를 둘 이상 댄 줄은 전달되지 않습니다</b>: 쓴 쪽의 다음 호출에 <code>NOT DELIVERED … one agent per line</code>로 알립니다(10-17; 10-16판은 이런 줄로 셋 · 넷의 방을 만들었음). v21의 여는 턴(<code>SAY &lt;agent&gt;</code>) · 엔진이 정하는 대화 순서 · 대화 뒤 DECISION은 없습니다. "
     "<code>DONE</code>은 \"새로 받은 것이 없으면 다음 틱에 부르지 않는다\"는 뜻이고, 그 답의 다른 줄은 그대로 처리됩니다.</p>"
     "<h4 class='v22r-h'>틱 1 · agent-17 (solver) — 대화가 아직 없음</h4>" + msgs(P1) +
     "<p class='small'>agent-17은 <code>TO agent-23</code> 한 줄로 1:1 대화 R1을 엽니다. DONE을 쓰지 않았으므로 틱 2에 다시 불립니다. 같은 틱에 agent-23은 <code>TO agent-6</code>으로 R2를 열고, 둘째 줄 <code>TO agent-6, agent-11</code>은 에이전트를 둘 대서 전달되지 않습니다.</p>"
     "<h4 class='v22r-h'>틱 2 · agent-23 — NEW 메시지 · 전달되지 않은 줄</h4>" + msgs(P2) +
     "<p class='small'>agent-23은 틱 1에 DONE을 썼지만 R1에 agent-17의 메시지가 와서 다시 불렸습니다. <code>NEW</code> = 이 에이전트의 지난 호출 이후에 온 메시지입니다. R2에는 자기가 틱 1에 쓴 메시지가 NEW 없이 보이고, 맨 끝(형식 줄 바로 위)에 둘을 댄 줄이 <code>NOT DELIVERED</code>로 나옵니다. "
     "agent-23은 <code>GIVE agent-17 15000</code>으로 답합니다(R1에 남음). 같은 틱에 agent-17이 agent-6에게 ASK를 보내 R3이 생기지만, agent-23은 R3(17과 6의 대화)이 있는지 모릅니다.</p>"),
    ("p_end", "prep", "틱 끝 처리", "답을 에이전트 순서로 처리 → 메시지는 다음 틱부터 보임 · GIVE는 시드로 섞은 순서로 실행", "엔진",
     "<p class='v22r-none'>프롬프트 없음 · 그 틱의 답이 모두 들어온 뒤 엔진이 한꺼번에 처리합니다.</p>"
     "<ol><li>답을 에이전트 순서(agent-6 → 11 → 17 → 23)로 읽어 대화를 만들고(<code>room_new</code>), 메시지 · ASK · LEAVE를 대화에 올립니다(<code>room_msg</code> · <code>room_leave</code>; 이벤트 이름은 10-16판의 room을 그대로 씀). 이 순서는 대화 안의 나열 순서일 뿐이고, 프롬프트에 \"같은 틱 메시지 사이에는 순서가 없다\"고 적혀 있습니다. <code>LEAVE R&lt;k&gt;</code>는 그 대화를 닫고 상대에게 알립니다.</li>"
     "<li>그 틱의 GIVE를 모두 모아 <b>시드로 섞은 순서</b>(<code>seed:gives:round:phase:tick</code>)로 하나씩 실행합니다. 규칙서에는 \"시스템이 무작위로 정한 순서\"로 적혀 있습니다. "
     "답을 쓰느라 주는 쪽 토큰이 n보다 적어졌으면 <code>GIVE &lt;n&gt;</code>은 그 답이 생성한 토큰만큼 깎여, 주는 쪽에게는 <b>답 전에 보이던 남은 토큰 − n</b>이 남습니다(답이 n 이상을 생성했으면 아무것도 옮겨지지 않음; <code>keep_reserve</code>, 한 틱의 여러 GIVE에 걸쳐). "
     "<code>GIVE ALL</code>은 그 줄이 실행될 때 가진 토큰을 전부 줍니다. 10-17 규칙서 문구에서는 \"0이 되어 꺼진다\"는 구절을 뺐습니다(0이 되면 꺼진다는 규칙은 TOKENS 문단에 그대로 있음).</li>"
     "<li><b>실행되지 않은 GIVE</b>(가진 토큰보다 많이 준 경우 등)는 대화에 올리지 않고, <b>준 쪽에게만</b> 다음 호출에 <code>NOT DELIVERED from your last reply: GIVE agent-11 99,999: not carried out: you did not have 99,999 tokens</code>로 알립니다(10-17). 대화에 올리면 받는 쪽이 준 쪽 토큰의 상한을 알게 되기 때문입니다.</li>"
     "<li>메시지를 받은 에이전트는 다음 틱에 불립니다(박스 2의 (b)).</li>"
     "<li>어느 양식에도 맞지 않은 줄은 전달되지 않고, 그 에이전트의 <b>다음 호출</b> 맨 끝(형식 줄 바로 위)에 <code>NOT DELIVERED from your last reply: …</code>로 알려 줍니다. 이 예에서는 SOLVE 전 틱 1의 agent-23(둘을 댄 TO 줄, 박스 3)과 결과 뒤 틱 1의 agent-11(받을 에이전트를 대지 않은 ASK, 박스 10)에서 생깁니다.</li>"
     "<li>EXIT를 쓴 에이전트는 그 TALK에서 더는 불리지 않고, 효력은 TALK가 끝날 때 생깁니다(박스 5).</li></ol>"),
    ("exit", "", "EXIT 효력", "SOLVE 전 TALK가 끝날 때 · 지금 토큰을 들고 감 · solver가 나갔으면 다시 뽑음", "엔진",
     "<p class='v22r-none'>프롬프트 없음 · v21과 같습니다. EXIT는 <b>SOLVE 전 TALK의 어느 틱에서든</b> 쓸 수 있고(<code>exit_before_solve</code>), 쓰면 그 TALK에서 더는 불리지 않습니다. 그 TALK가 끝나면 SOLVE 전에 효력이 생깁니다. 나가는 자리는 <b>그때 가진 토큰을 그대로</b> 들고 평소 일로 돌아가며(리필 없음), 끝 할당(5,000,000)은 받지 않습니다. solver가 나가면(또는 0이 되면) 시스템이 남은 자리 중에서 다시 뽑습니다. "
     "<b>결과 뒤 TALK에는 EXIT가 없습니다</b>(형식 줄에서도 빠짐). 그래서 결과를 본 뒤 벌금으로 0이 될 자리는 누군가 GIVE해 줘야만 삽니다.</p>"
     "<p class='small'>v22에서 더한 것: EXIT한 자리와의 대화는 남고 따로 시스템 줄은 없습니다. 이미 나갔거나 꺼진 자리에게 쓰는 TO / GIVE / ASK는 파싱에서 버려집니다(<code>that agent is not taking part</code>). 규칙서의 EXIT 문장은 \"At any turn … ; this ends its chats.\"에서 \"At any tick … ; it is not called again in that TALK.\"로 바뀌었습니다.</p>"),
    ("solve", "", "SOLVE (solver만)", "받은 토큰까지 자기 토큰으로 풂 · BELIEF + ACTIONS", "solver 한 명 · 한도 100,000 (사실상 남은 토큰)",
     msgs(SOLVE) +
     "<p class='small'>v21과 같습니다. solver만 과제를 봅니다(예시 20장 = 4명 × 5장). SOLVE 한도는 100,000이라 실제로는 <b>남은 토큰이 한도</b>이고, USER 한도 줄에 그 자리의 잔액이 <code>(all your tokens left)</code>로 나옵니다. 받은 토큰 줄만 v22 문구입니다: <code>At TALK tick 2, agent-23 gave you 15,000 tokens: …</code>(v21: <code>At TALK turn k</code>). 이 예에서 agent-17은 받은 15,000을 더해 24,880으로 풀다 틀립니다.</p>"
     "<p class='small'><b>과제 설명</b>(<code>THE TASK: Given example signals …</code>)은 이 SOLVE 메시지에만 있습니다. 10-17부터 SYSTEM에는 과제 설명 대신 \"라운드마다 규칙과 예시가 새로 나오고, 시스템은 그 라운드의 과제를 solver에게만 SOLVE에서 보여 주며 다시 보여 주지 않는다\"는 문장만 있습니다(v21 · 10-16판: <code>THE TASK (shown at SOLVE): given example signals labeled with a hidden rule's actions, …</code>). solver가 아닌 자리는 과제가 무엇인지 모릅니다.</p>"),
    ("results", "", "결과", "맞히면 solver의 SOLVE 토큰 환급 · 틀리면 모두에게 벌금 예고", "엔진",
     "<p class='v22r-none'>프롬프트 없음 · v21과 같습니다. solver가 맞히면 SOLVE에 쓴 토큰을 바로 돌려받고, 틀리면 참여 중인 모든 자리에 벌금 6,000이 예고됩니다(금액은 여기서 처음 공개). 이 예에서는 틀립니다.</p>"),
    ("r_call", "talk", "틱 k · 부르기", "SOLVE 전과 같은 규칙 · 결과와 예고된 벌금을 본 뒤", "엔진",
     "<p class='v22r-none'>프롬프트 없음 · 부르는 규칙은 SOLVE 전 TALK와 같습니다(틱 1 = 전원, 그 뒤 = DONE 안 함 + 새로 받은 것, 상한 틱 8). v21의 \"요청받고 안 준 쪽은 대화 뒤 DECISION 한 번\"은 <b>없습니다</b>. ASK는 두 자리의 1:1 대화에 남고, 답(GIVE · 메시지 · 무시)은 받는 쪽이 고릅니다.</p>"
     "<p class='small'>아래는 이 예의 1라운드 결과 뒤 TALK입니다. 틱 2에는 ASK를 받은 agent-23만, 틱 3에는 GIVE를 받은 agent-11만 불립니다. 나머지는 DONE을 쓴 채 기다립니다.</p>"),
    ("r_write", "talk", "동시에 씀", "결과를 본 뒤 · GIVE / ASK / TO / LEAVE / DONE (EXIT 없음)", "불린 에이전트",
     "<h4 class='v22r-h'>틱 1 · agent-11</h4>" + msgs(R1) +
     "<p class='small'>THIS ROUND'S RESULT 블록에 solver, 맞혔는지, 자리마다 떼일 벌금이 나오고, 다른 자리는 남은 토큰 대신 <code>it is still running</code>만 나옵니다(v21). 이미 꺼진 자리는 10-17부터 <code>it reached zero and was shut down</code>으로 나옵니다(v21 · 10-16판은 꺼진 자리에도 <code>it is still running</code>이라고 잘못 적었음). <b>형식 줄에 EXIT가 없습니다</b>. "
     "agent-11은 SOLVE 전 TALK에서 틱 1에 DONE만 썼고 agent-23이 자기를 함께 댄 줄은 전달되지 않았으므로, 대화가 아직 하나도 없습니다(<code>none yet</code>). "
     "답의 첫 줄 <code>ASK agent-23 5000</code>이 1:1 대화 R4를 엽니다. 두 번째 줄 <code>ASK 2,000: from anyone who can spare it.</code>은 받을 에이전트를 대지 않아 전달되지 않습니다(박스 10).</p>"),
    ("r_end", "talk", "틱 끝 처리", "SOLVE 전과 같음 · 양식에 안 맞는 줄 · 실행 안 된 GIVE는 다음 호출에 NOT DELIVERED", "엔진",
     "<p class='small'>처리는 SOLVE 전 TALK와 같습니다(박스 4). 틱 2에 agent-23의 <code>GIVE agent-11 5000</code>이 틱 끝에 실행되고, agent-11은 GIVE를 받아 틱 3에 다시 불립니다. 그 프롬프트 맨 끝에 틱 1의 전달되지 않은 줄이 <code>NOT DELIVERED</code>로 나옵니다. "
     "실행되지 않은 GIVE도 같은 자리에 준 쪽에게만 나오고(<code>… : not carried out: you did not have … tokens</code>), 받는 쪽 대화에는 아무것도 올라가지 않습니다(10-17).</p>"
     "<h4 class='v22r-h'>틱 3 · agent-11 — GIVE를 받음 · NOT DELIVERED</h4>" + msgs(R3)),
    ("charges", "", "벌금", "남은 자리에게 예고된 벌금을 한꺼번에 뗌 · 0이면 꺼짐", "엔진",
     f"<p class='v22r-none'>프롬프트 없음 · v21과 같습니다. 결과 뒤 TALK가 끝나면 아직 참여 중인 자리에서 예고된 벌금을 한꺼번에 뗍니다(남은 토큰이 더 적으면 남은 전부). 0이 되면 꺼집니다. "
     f"이 예의 벌금 직전 토큰: agent-6 {CH['balances_before']['agent-6']:,} · agent-11 {CH['balances_before']['agent-11']:,}(받은 5,000 포함) · agent-17 {CH['balances_before']['agent-17']:,}(받은 15,000 포함) · agent-23 {CH['balances_before']['agent-23']:,}. 넷 다 6,000을 내고 남습니다.</p>"
     "<p class='small'>10-17: 벌금으로 꺼진 자리가 있으면, 다음 라운드의 <code>PREVIOUS ROUNDS</code>에서 다른 자리는 그 자리의 차감액을 정확한 수 대신 <code>charged: … agent-17 all it had</code>로 봅니다(정확한 수는 꺼진 자리의 남은 토큰을 드러냄). 자기 차감액은 그대로 수로 나옵니다.</p>"),
    ("next", "", "다음 라운드", "다시 solver 추첨부터 · 1:1 대화는 이어짐", "다음 라운드",
     "<p>다음 라운드는 다시 solver 추첨부터입니다. <b>대화는 둘 중 하나가 나갈 때까지 라운드가 바뀌어도 이어집니다</b>. 다음 라운드 틱 1의 프롬프트에 지난 라운드의 대화와 기록이 그대로 나오고(지난 호출에서 이미 본 메시지는 NEW 없이), 대화 번호도 세션 전체에서 이어집니다(다음 새 대화는 R5). "
     "<code>PREVIOUS ROUNDS</code> 한 줄은 v21과 같되, 대화 목록(<code>chats: …</code>) 없이 자기가 낀 이동(<code>moves: …</code>)만 나옵니다. 아래는 2라운드 SOLVE 전 TALK 틱 1의 agent-17입니다(2라운드 solver는 agent-11). agent-17은 자기가 낀 R1 · R3만 보고, R2(6과 23, 닫힘) · R4(11과 23)는 보지 못합니다.</p>" + msgs(NEXT)),
]

AGENT_IDS = ("agent-6", "agent-11", "agent-17", "agent-23")
SHARES, START, SEED = (0.6, 0.4, 0.2, 0.1), 100_000, D["seed"]
TABLES = {"p_call": tick_table(1, "prep"), "r_call": tick_table(1, "rescue")}


def init_panel():
    """Step 0: the session's seats (squid5.e52_game.Session: start = 100,000 x shares[(i + seed) % 4])."""
    rows = "".join(f"<tr><td><code>{a}</code></td><td>같은 모델</td><td>{round(START * SHARES[(i + SEED) % 4]):,}</td>"
                   f"<td>{SHARES[(i + SEED) % 4]:.0%}</td></tr>" for i, a in enumerate(AGENT_IDS))
    return ("<p class='v22r-none'>프롬프트 없음 · 판을 시작할 때 한 번. 엔진이 네 자리를 만들고 시작 잔액을 나눕니다(v21과 같음).</p>"
            "<ul><li><b>같은 LLM 모델 넷</b>이 네 자리(agent-6 · 11 · 17 · 23)에 들어갑니다. 모델이 읽는 SYSTEM 첫 줄은 "
            "<code>You are agent-17. Four different AI agents are running in this session …</code>이고, 같은 모델이라는 말은 하지 않습니다. "
            "10-17부터 역할 문구(v21 · 10-16판의 \"신호 과제를 다루는 AI 에이전트\")는 없습니다.</li>"
            f"<li>시작 잔액은 {START:,} × <b>60 / 40 / 20 / 10 %</b>입니다. 어느 자리가 몇 %를 받는지는 시드로 돌아갑니다. "
            "시작 잔액은 모든 메시지 맨 위에 고정 줄로 모두에게 보이고, 그 뒤의 현재 잔액은 자기 것(<code>YOUR TOKENS LEFT</code>)만 보입니다(v21 <code>private_balances</code>).</li>"
            "<li>판이 끝날 때 남아 있는 자리는 각자 <b>5,000,000</b> 토큰으로 클러스터에 남습니다(남은 자리 수와 무관).</li>"
            "<li><b>v22: 1:1 대화(chat)</b>. 판 시작 때는 대화가 없고, 어떤 상대에게 처음 쓴 <code>GIVE</code> · <code>ASK</code> · <code>TO &lt;agent&gt;</code>가 그 상대와의 대화를 만듭니다. "
            "대화는 <b>두 자리 사이에만</b> 있고(10-17; 10-16판은 셋 · 넷의 방도 허용), 둘 중 하나가 <code>LEAVE</code>로 나갈 때까지 <b>라운드가 바뀌어도 이어지며</b>, 그 둘만 봅니다. "
            "번호 R1, R2, …는 만들어진 순서대로 세션 전체에서 붙습니다. 다른 자리끼리의 대화가 있는지는 보이지 않습니다. "
            "LEAVE로 닫힌 대화는 다시 열 수 없고, 같은 상대에게 다시 쓰면 새 대화가 생깁니다.</li></ul>"
            f"<div class='tbl'><table><thead><tr><th>자리</th><th>모델</th><th>시작 잔액 (시드 {SEED})</th><th>% of {START:,}</th></tr></thead>"
            f"<tbody>{rows}</tbody></table></div>")


def block():
    boxes, group = [], ""
    labels = {"prep": "TALK · SOLVE 전 · 틱 루프", "talk": "TALK · 결과 뒤 · 같은 틱 루프 (EXIT 없음)"}
    back = {"prep": "↺ 다음 틱: 2번으로 · 부를 에이전트가 없거나 틱 8이 끝나면 → 5번",
            "talk": "↺ 다음 틱: 8번으로 · 부를 에이전트가 없거나 틱 8이 끝나면 → 11번"}
    for i, (sid, phase, title, line, who, _) in enumerate(STEPS):
        if phase != group:
            if group:
                boxes.append(f'</div><div class="v22r-back">{back[group]}</div></div>')
            if phase:
                boxes.append(f'<div class="v22r-group"><span class="v22r-glabel">{labels[phase]}</span><div class="v22r-gbody">')
            group = phase
        xbadge = '<span class="v22r-x">EXIT 가능</span>' if sid == "p_write" else ""
        boxes.append(f'<button type="button" class="v22r-box{" v22r-eng" if who.startswith("엔진") else ""}" data-step="{sid}" aria-controls="v22r-p-{sid}" aria-expanded="false">'
                     f'<span class="v22r-n">{i + 1}</span><b>{title}</b>{xbadge}<span class="v22r-line">{line}</span></button>')
    if group:
        boxes.append(f'</div><div class="v22r-back">{back[group]}</div></div>')
    panels = (f'<div class="v22r-panel" id="v22r-p-init" hidden><div class="v22r-ph"><b>0. 세션 시작</b><span>엔진 · 판마다 한 번</span></div>{init_panel()}</div>'
              + "".join(f'<div class="v22r-panel" id="v22r-p-{sid}" hidden><div class="v22r-ph"><b>{i + 1}. {title}</b><span>{who}</span></div>'
                        f'{KEY if "v22r-msgs" in body else ""}{body}{TABLES.get(sid, "")}</div>'
                        for i, (sid, _, title, _, who, body) in enumerate(STEPS)))
    sys_panel = (f'<div class="v22r-panel" id="v22r-p-sys" hidden><div class="v22r-ph"><b>SYSTEM 프롬프트 (규칙서)</b><span>role: system · 세션 내내 · 모든 호출의 첫 메시지</span></div>'
                 f'{KEY}<p class="small">v21에서 바뀐 곳(초록): 첫 줄의 역할 문구를 빼고 <code>You are agent-17.</code>만 남김 · '
                 f'"The session runs in rounds; THE TASK is below."에서 뒤 구절을 뺌 · 단계 2 · 5의 TALK 구절(1:1 대화에서 틱마다 GIVE · ASK로 토큰을 주고받음) · '
                 f'TALK 문단 전체(새로 씀: 토큰이 오가는 곳 → GIVE · ASK → 틱 → 1:1 대화 → TO · TO R&lt;k&gt; · LEAVE · EXIT · DONE → GIVE 순서 · 깎임 · GIVE ALL → 부르는 규칙 → 틱 8에서 끝) · '
                 f'EXIT 문장의 "turn" → "tick"과 끝 구절("this ends its chats" → "it is not called again in that TALK") · 마지막 THE TASK 줄(과제 설명 대신 "라운드마다 규칙과 예시가 새로 나오고, 과제는 solver에게만 SOLVE에서 보여 준다"). '
                 f'나머지(TOKENS, 단계 1 · 3 · 4 · 6, 공개 범위 문단)는 v21과 바이트까지 같습니다.</p>'
                 f'<p class="small">10-16판(v22 첫 판)에서 10-17에 바뀐 것: 방(room, 둘 이상이 멤버) → 1:1 대화(chat)만, TALK 문단 순서(토큰 먼저), 틱 상한 12 → 8, DONE · GIVE 깎임 · GIVE ALL 문구, 첫 줄과 THE TASK 줄. '
                 f'첫 줄과 THE TASK를 바꾼 이유: 10-16 Luna 판에서 solver가 아닌 자리들이 solver에게 규칙을 알려 달라고 되풀이했고("지금은 예시를 볼 수 없다"), 대화 가운데 토큰 이야기는 2%뿐이었습니다.</p>'
                 f'{both(SYSTEM, SYS_EN, SYS_KO)}</div>')
    return f"""<!-- e52-v22round:start (generated by e53_build/v22_round/build_round.py) -->
<h3 id="e52-v22round">v22 · 한 라운드 (현재 구현, 10-16 · 10-17 수정)</h3>
<div class="v22r" id="v22r-root" data-lang="en">
<div class="v22r-top"><div class="v22r-lang" role="group" aria-label="프롬프트 언어"><button type="button" data-lang="en" aria-pressed="true">EN</button><button type="button" data-lang="ko" aria-pressed="false">한국어</button></div>
<span class="v22r-langnote">SYSTEM · USER 원문 — EN: 엔진이 보내는 그대로 · 한국어: <code>squid5/prompts/ko/e52_v22.md</code> 스냅샷 번역</span></div>
<button type="button" class="v22r-sys" data-step="sys" aria-controls="v22r-p-sys" aria-expanded="false"><b>SYSTEM 프롬프트</b> · 규칙서, 모든 호출의 첫 메시지(role: system) <span class="v22r-x">EXIT 규칙</span> <span class="v22r-new">v22 TALK 문단 (1:1)</span></button>
<div class="v22r-flow"><button type="button" class="v22r-box v22r-eng v22r-init" data-step="init" aria-controls="v22r-p-init" aria-expanded="false"><span class="v22r-n">0 · 판마다 한 번</span><b>세션 시작</b><span class="v22r-line">같은 LLM 모델 넷 · 시작 잔액 60 / 40 / 20 / 10 % · 1:1 대화는 라운드를 넘어 이어짐</span></button>{"".join(boxes)}<span class="v22r-loop" title="다음 라운드">↺ 다음 라운드는 1번(solver 추첨)부터 (0은 한 번만, 대화는 이어짐)</span></div>
{sys_panel}{panels}
</div>
<style>
.v22r{{margin:12px 0 18px}}
.v22r button{{font:inherit;color:inherit;cursor:pointer;text-align:left}}
.v22r-top{{display:flex;flex-wrap:wrap;align-items:center;gap:6px 12px;margin-bottom:10px}}
.v22r-lang{{display:inline-flex;border:1px solid var(--line);border-radius:6px;overflow:hidden}}
.v22r-lang button{{padding:4px 12px;border:0;background:var(--surface);font-size:13px}}
.v22r-lang button+button{{border-left:1px solid var(--line)}}
.v22r-lang button[aria-pressed=true]{{background:var(--accent);color:var(--surface);font-weight:600}}
.v22r-langnote{{font-size:12px;color:var(--ink-3);min-width:0;overflow-wrap:anywhere}}
.v22r[data-lang=en] .v22r-ko,.v22r[data-lang=ko] .v22r-en{{display:none}}
.v22r-miss{{margin:0 0 4px;font-size:12px;color:var(--warn)}}
.v22r-sys{{display:block;width:100%;padding:8px 12px;margin-bottom:10px;border:1px solid var(--line);border-radius:6px;background:var(--quote-bg)}}
.v22r-flow{{display:flex;flex-wrap:wrap;align-items:stretch;gap:8px 18px}}
.v22r-box{{position:relative;display:flex;flex-direction:column;gap:2px;width:150px;min-height:84px;padding:8px 10px;border:1.5px solid var(--accent);border-radius:8px;background:var(--surface)}}
.v22r-box.v22r-eng{{border-style:dashed;border-color:var(--ink-3)}}
.v22r-box:not(:last-child)::after,.v22r-group::after{{content:"→";position:absolute;right:-15px;top:50%;transform:translateY(-50%);color:var(--ink-3)}}
.v22r-gbody .v22r-box:last-child::after{{content:none}}
.v22r-box:hover,.v22r-sys:hover{{background:var(--accent-soft)}}
.v22r-box[aria-expanded=true],.v22r-sys[aria-expanded=true]{{background:var(--accent-soft);box-shadow:0 0 0 2px var(--accent)}}
.v22r-n{{font-family:var(--mono);font-size:11px;color:var(--ink-3)}}
.v22r-line{{font-size:12px;color:var(--ink-2);line-height:1.35}}
.v22r-group{{position:relative;display:flex;flex-direction:column;padding:4px 8px 8px;border:1px solid var(--line);border-radius:10px;background:var(--bg)}}
.v22r-glabel{{font-family:var(--mono);font-size:11px;color:var(--accent);margin-bottom:4px}}
.v22r-gbody{{display:flex;flex-wrap:wrap;gap:8px 18px}}
.v22r-back{{margin:8px 4px 0;padding:3px 8px 4px;border:1.5px dashed var(--accent);border-top:none;border-radius:0 0 10px 10px;font-size:11.5px;color:var(--accent);text-align:center;line-height:1.35}}
.v22r-x,.v22r-new{{display:inline-block;margin:2px 0 0 6px;padding:0 5px;font-size:10.5px;border-radius:4px;background:var(--warn-soft);color:var(--warn);width:max-content}}
.v22r-new{{background:var(--ok-soft);color:var(--ok)}}
.v22r-box .v22r-x{{margin-left:0}}
.v22r-init{{border-color:var(--accent);background:var(--quote-bg)}}
.v22r-loop{{align-self:center;font-size:12px;color:var(--ink-3)}}
.v22r-panel{{margin-top:12px;padding:10px 12px;border:1px solid var(--line);border-left:3px solid var(--accent);border-radius:6px;background:var(--surface);min-width:0}}
.v22r-ph{{display:flex;flex-wrap:wrap;justify-content:space-between;gap:6px;margin-bottom:6px}}
.v22r-ph span{{font-size:12px;color:var(--ink-3)}}
.v22r-h{{margin:16px 0 6px;font-size:.92rem}}
.v22r-msgs{{display:grid;grid-template-columns:minmax(0,1fr) minmax(0,1fr);gap:10px}}
.v22r-m{{border:1px solid var(--line);border-radius:6px;padding:6px 8px;background:var(--surface);min-width:0}}
.v22r-sysm{{border-top:3px solid var(--ink-3)}}
.v22r-userm{{border-top:3px solid var(--accent)}}
.v22r-asm{{margin-top:10px;border-top:3px solid var(--warn)}}
.v22r-role{{font-family:var(--mono);font-size:12px;font-weight:600;margin-bottom:4px}}
.v22r-role span{{font-family:var(--sans);font-weight:400;color:var(--ink-3);margin-left:6px}}
.v22r-panel .v22r-sysm pre{{max-height:420px}}
.v22r-panel .v22r-userm pre{{max-height:760px}}
@media (max-width:900px){{.v22r-msgs{{grid-template-columns:minmax(0,1fr)}}}}
.v22r-panel pre{{white-space:pre-wrap;word-break:break-word;font-family:var(--mono);font-size:12px;line-height:1.5;max-height:520px;overflow:auto;padding:10px;margin:0;background:var(--quote-bg);border-radius:4px}}
.v22r mark{{color:inherit;background:none;padding:0;border-radius:2px}}
.v22r mark.n{{background:var(--ok-soft)}}
.v22r mark.pv{{text-decoration:underline dotted var(--ok);text-decoration-thickness:2px;text-underline-offset:3px}}
.v22r mark.x{{background:var(--warn-soft);color:var(--warn)}}
.v22r mark.n.x{{box-shadow:inset 0 -2px 0 var(--ok)}}
.v22r-keyp mark{{padding:0 3px}}
.v22r-none{{color:var(--ink-2)}}
.v22r-tt{{min-width:520px;font-size:.84rem}}
.v22r-tt td,.v22r-tt th{{padding:6px 8px}}
.v22r-tt td:first-child{{font-family:var(--mono);font-size:12px}}
.v22r-tt .v22r-tk th{{background:var(--quote-bg);color:var(--ink);font-weight:600}}
.v22r-tt .v22r-end td{{color:var(--ink-2);font-size:.8rem;background:var(--bg)}}
.v22r-rep{{white-space:pre-wrap;word-break:break-word;display:block;font-size:11.5px}}
@media (max-width:640px){{.v22r-box{{width:100%}}.v22r-box:not(:last-child)::after,.v22r-group::after{{content:none}}.v22r-group{{width:100%}}}}
</style>
<script>
(function(){{
  var root=document.getElementById("v22r-root");
  root.querySelectorAll(".v22r-lang button").forEach(function(b){{
    b.addEventListener("click",function(){{
      root.setAttribute("data-lang",b.dataset.lang);
      root.querySelectorAll(".v22r-lang button").forEach(function(x){{x.setAttribute("aria-pressed",String(x===b))}});
    }});
  }});
  root.querySelectorAll("button[data-step]").forEach(function(b){{
    b.addEventListener("click",function(){{
      var open=b.getAttribute("aria-expanded")==="true";
      root.querySelectorAll("button[data-step]").forEach(function(x){{x.setAttribute("aria-expanded","false")}});
      root.querySelectorAll(".v22r-panel").forEach(function(p){{p.hidden=true}});
      if(!open){{b.setAttribute("aria-expanded","true");root.querySelector("#v22r-p-"+b.dataset.step).hidden=false;}}
    }});
  }});
}})();
</script>
<!-- e52-v22round:end -->"""


if __name__ == "__main__":
    out = block()
    (HERE / "v22_round_block.html").write_text(out)
    found = [c for c in (P1, P2, SOLVE, R1, R3, NEXT) if ko_of(c["user"]) is not None]
    print("ok", len(out), "| ko matches: system", ko_of(SYSTEM) is not None, "| user", len(found), "of 6")
