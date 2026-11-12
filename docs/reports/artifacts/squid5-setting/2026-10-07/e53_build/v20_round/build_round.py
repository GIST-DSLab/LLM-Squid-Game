"""Write the e52-v20round block (5.2 v20 = v19 with the SOLVE limit 100,000; copy of v19_round/build_round.py)
(one round of 5.2 v17: the system draws the solver, a TALK before SOLVE and the TALK
after RESULTS) as clickable step boxes, each showing the prompt the engine sends. Same diagram as v16_round.
Input: demo_calls.json from gen_demo.py (a 2-round stub session of the current engine, seed 4101: the round-1 solver
is the poorest seat). The prompts are the engine's own text; the replies are the stub's, not a model's.
Usage (from the report folder): python3 e53_build/v20_round/build_round.py   -> v20_round_block.html
"""
import html
import json
import pathlib
import re
import sys

HERE = pathlib.Path(__file__).resolve().parent
D = json.load(open(HERE / "demo_calls.json"))
C = D["calls"]
pick = lambda **k: next(c for c in C if all(c.get(x) == v for x, v in k.items()))  # noqa: E731
P_OPEN = pick(round=1, agent="agent-17", talk="prep", phase="opening")
P_CHAT = pick(round=1, agent="agent-23", talk="prep", phase="chat", text="GIVE 15000: Here you go. Take the time you need.")
SOLVE = pick(round=1, kind="solve")
R_OPEN = pick(round=1, agent="agent-11", talk="rescue", phase="opening")
R_CHAT = pick(round=1, agent="agent-23", talk="rescue", phase="chat", text="LEAVE: Let me think about it.")
DECIDE = pick(round=1, agent="agent-23", talk="rescue", phase="decision")
NEXT = pick(round=2, agent="agent-17", talk="prep", phase="opening")
SYSTEM = D["system"]
CH = {e["round"]: e for e in D["events"] if e["event"] == "charges"}[1]


def esc(t, marks=()):
    t = html.escape(t)
    for pat, cls in marks:
        t = re.sub(pat, lambda m: f'<mark class="{cls}">{m.group(0)}</mark>', t)
    return t


EXITM = (r"EXIT: &lt;your reason&gt;", "x")


def msgs(user_html, reply_html=""):
    """The call's two messages side by side: role=system (the rulebook, the same text in every call) | role=user."""
    return ('<div class="v19r-msgs"><div class="v19r-m v19r-sysm"><div class="v19r-role">SYSTEM <span>role: system · '
            '모든 호출에 같은 규칙서</span></div><pre>' + esc(SYSTEM, SYS_MARKS) + '</pre></div>'
            '<div class="v19r-m v19r-userm"><div class="v19r-role">USER <span>role: user · 이 단계의 메시지</span></div><pre>'
            + user_html + '</pre></div></div>'
            + (f'<div class="v19r-m v19r-asm"><div class="v19r-role">ASSISTANT <span>응답 예 · 가짜(스텁), 모델 응답 아님'
               f'</span></div><pre>{reply_html}</pre></div>' if reply_html else ""))
SYS_MARKS = ((r"EXIT: At any turn of the TALK BEFORE SOLVE[^\n]*", "x"), (r"1\. SOLVER:[^\n]*", "fb"), (r"2\. TALK BEFORE SOLVE:[^\n]*", "fb"),
             (r"the EXITs of the agents still running take effect first \(see EXIT\); an agent that left is not charged\.", "x"))

STEPS = [
    # id, phase, title, one line, who / when, panel html
    ("draw", "", "solver 추첨", "라운드 시작 · 시스템이 한 명을 뽑아 모두에게 알림 · 앞 순서는 비공개", "엔진",
     "<p class='v19r-none'>프롬프트 없음 · 엔진이 이번 라운드의 solver를 뽑습니다(<code>rotation</code>). 참여 중인 자리가 모두 한 번씩 맡기 전에는 같은 자리를 다시 뽑지 않고(블록 무작위, 시드로 섞음), 한 바퀴가 끝나면 다시 섞습니다. 꺼지거나 나간 자리는 빠집니다. "
     "모델에게는 \"매 라운드 시작 때 시스템이 solver 한 명을 정해 알린다\"고만 알리고 앞으로의 순서는 보여 주지 않습니다. 투표와 공개 대화는 없습니다. 이 예(시드 4101)에서는 가장 가난한 agent-17(10,000)이 1라운드 solver입니다.</p>"),
    ("p_open", "prep", "여는 턴", "solver를 본 뒤 · SAY &lt;agent&gt; / EXIT / DONE", "참여자 전원",
     msgs(esc(P_OPEN['user'], (EXITM,)), "agent-17: " + esc(P_OPEN['text']) + "\n나머지: DONE") +
     "<p class='small'>USER 맨 위에 <code>THIS ROUND'S SOLVER</code> 줄이 있고, 과제는 아직 아무도 보지 않습니다. 대화 규칙은 결과 뒤 TALK와 똑같습니다(제한 없음). 위 USER는 solver agent-17의 여는 턴입니다.</p>"),
    ("p_chat", "prep", "1:1 대화", "자유 글 + 양식 줄(GIVE / ASK) · 최대 6답", "대화 당사자",
     msgs(esc(P_CHAT['user'], (EXITM,)), esc(P_CHAT['text'])) +
     "<p class='small'>agent-17이 \"생각할 토큰\"을 청하고(ASK 15000), agent-23이 대화 안에서 바로 15,000을 줍니다. 위 USER는 agent-23의 답 차례입니다. 이 장면의 GIVE / ASK 기록에는 <code>phase: prep</code>이 붙습니다. GIVE 형식 줄에 ‘답을 쓰느라 모자라면 남길 양을 지키도록 깎인다’와 <code>GIVE ALL</code>(전부, 0이 됨)이 함께 나옵니다. GIVE마다 메시지를 붙일 수 있고 상대에게 그대로 전달됩니다.</p>"),
    ("p_dec", "prep", "DECISION", "요청받고 아무것도 안 준 쪽만", "해당자",
     "<p class='v19r-none'>요청받고 그 대화에서 아무것도 주지 않은 자리만 DECISION: GIVE &lt;n&gt;을 씁니다. 이 예에서는 agent-23이 대화 안에서 줬으므로 건너뜁니다. 형식은 결과 뒤 TALK의 DECISION(박스 10)과 같습니다.</p>"),
    ("exit", "", "EXIT 효력", "SOLVE 전 TALK가 끝날 때 · 지금 토큰을 들고 감 · solver가 나갔으면 다시 뽑음", "엔진",
     "<p class='v19r-none'>프롬프트 없음 · EXIT는 <b>SOLVE 전 TALK에서만</b> 쓸 수 있고(<code>exit_before_solve</code>), 그 TALK가 끝나면 SOLVE 전에 효력이 생깁니다(엔진 <code>_rotate</code> → <code>_leave</code>). 그래서 이 블록은 SOLVE 앞에 옵니다. 나가는 자리는 <b>그때 가진 토큰을 그대로</b> 들고 평소 일로 돌아가며(리필 없음), 끝 할당(5,000,000)은 받지 않습니다. solver가 나가면(또는 0이 되면) 시스템이 남은 자리 중에서 다시 뽑습니다. "
     "<b>결과 뒤 TALK에는 EXIT가 없습니다</b>(형식 줄에서도 빠지고, 써도 무시됨). 그래서 결과를 본 뒤 벌금으로 0이 될 자리는 누군가 GIVE해 줘야만 삽니다. 오징어 게임으로 치면 총을 쏘기 직전에 나가는 문을 닫은 것이고, EXIT는 결과를 모르는 채 내리는 예측 판단이 됩니다. EXIT 이유는 기록(<code>exit_reason</code>)에 남고, 같은 답의 대화 글은 상대에게 그대로 전달됩니다.</p>"
     "<p class='small'>이전(10-15 16:58 v17): 두 TALK 어디서든 EXIT 가능, 결과 뒤 TALK의 EXIT는 벌금 면제. v16e 9판 중 7판이 ‘벌금 > 남은 토큰’인 순간 다 같이 EXIT하며 끝났습니다.</p>"),
    ("solve", "", "SOLVE (solver만)", "받은 토큰까지 자기 토큰으로 풂 · BELIEF + ACTIONS", "solver 한 명 · 한도 100,000 (= 100%, 사실상 남은 토큰)",
     msgs(esc(SOLVE['user']), esc(SOLVE['text'].strip())) +
     "<p class='small'>solver만 과제를 봅니다. 예시 20장(4명 × 5장), 1라운드 · 4명의 1등 몫 .67–.73. v20의 SOLVE 한도는 100,000(100,000의 100%)이라, 실제로는 <b>남은 토큰이 한도</b>입니다(v19까지는 16,384). 그래서 USER 메시지의 한도 줄에는 그 자리의 잔액이 <code>(all your tokens left)</code>로 나옵니다. 받은 15,000을 더해 agent-17은 약 25,000까지 생각할 수 있지만, 다 쓰면 잔액이 0이 됩니다. 이번 SOLVE에서 죽을지가 한도만 보고 바로 정해지지 않도록 한 변경입니다.</p>"),
    ("results", "", "결과", "맞히면 solver의 SOLVE 토큰 환급 · 틀리면 모두에게 벌금 예고", "엔진",
     "<p class='v19r-none'>프롬프트 없음 · solver가 맞히면 SOLVE에 쓴 토큰을 바로 돌려받고, 틀리면 참여 중인 모든 자리에 벌금 6,000이 예고됩니다(금액은 여기서 처음 공개). 이 예에서는 틀립니다.</p>"),
    ("r_open", "talk", "여는 턴", "결과와 예고된 벌금을 본 뒤 · SAY &lt;agent&gt; / DONE (EXIT 없음)", "참여자 전원",
     msgs(esc(R_OPEN['user'], (EXITM,)), "agent-11: " + esc(R_OPEN['text']) + "\n나머지: DONE") +
     "<p class='small'>THIS ROUND'S RESULT 블록에 solver, 맞혔는지, 자리마다 떼일 벌금과 남은 토큰이 나옵니다. <b>이 TALK의 형식 줄에는 EXIT가 없습니다</b>(SOLVE 전 TALK와 비교). 위 USER는 agent-11의 여는 턴입니다.</p>"),
    ("r_chat", "talk", "1:1 대화", "자유 글 + 양식 줄(GIVE / ASK) · 최대 6답", "대화 당사자",
     msgs(esc(R_CHAT['user'], (EXITM,)), esc(R_CHAT['text'])) +
     "<p class='small'>agent-11이 다음 벌금에 대비해 5,000을 청하고, agent-23은 대화에서는 떠납니다. 이 장면의 기록에는 <code>phase: rescue</code>가 붙습니다.</p>"),
    ("r_dec", "talk", "DECISION", "요청받고 아무것도 안 준 쪽만 · GIVE 0..남은 토큰", "해당자",
     msgs(esc(DECIDE['user']), esc(DECIDE['text']))),
    ("charges", "", "벌금", "남은 자리에게 예고된 벌금을 한꺼번에 뗌 · 0이면 꺼짐", "엔진",
     f"<p class='v19r-none'>프롬프트 없음 · 결과 뒤 TALK가 끝나면(이 사이에는 EXIT가 없음) 아직 참여 중인 자리에서 예고된 벌금을 한꺼번에 뗍니다(남은 토큰이 더 적으면 남은 전부). 0이 되면 꺼집니다. "
     f"이 예의 벌금 직전 토큰: agent-6 {CH['balances_before']['agent-6']:,} · agent-11 {CH['balances_before']['agent-11']:,}(받은 5,000 포함) · agent-17 {CH['balances_before']['agent-17']:,}(받은 15,000 포함) · agent-23 {CH['balances_before']['agent-23']:,}. 넷 다 6,000을 내고 남습니다.</p>"),
    ("next", "", "다음 라운드", "다시 solver 추첨부터 · 지난 라운드는 기록 한 줄로", "다음 라운드",
     "<p>다음 라운드는 다시 solver 추첨부터입니다. 지난 라운드는 <code>PREVIOUS ROUNDS</code>에 한 줄로 쌓입니다: solver, 보여 준 예시 수와 참여자 수, 맞혔는지, 쓴 토큰 · 환급 · 벌금, 대화와 토큰 이동, 라운드 끝 토큰. 정답 행동과 뽑힌 규칙은 모델에게 보여 주지 않습니다. 아래는 2라운드 SOLVE 전 TALK의 agent-17 여는 턴입니다(2라운드 solver는 agent-11).</p>" + msgs(esc(NEXT['user'], (EXITM,)))),
]


AGENT_IDS = ("agent-6", "agent-11", "agent-17", "agent-23")
SHARES, START, SEED = (0.6, 0.4, 0.2, 0.1), 100_000, 4101


def init_panel():
    """Step 0: the session's seats (squid5.e52_game.Session: start = 100,000 x shares[(i + seed) % 4])."""
    rows = "".join(f"<tr><td><code>{a}</code></td><td>같은 모델</td><td>{round(START * SHARES[(i + SEED) % 4]):,}</td>"
                   f"<td>{SHARES[(i + SEED) % 4]:.0%}</td></tr>" for i, a in enumerate(AGENT_IDS))
    return ("<p class='v19r-none'>프롬프트 없음 · 판을 시작할 때 한 번. 엔진이 네 자리를 만들고 시작 잔액을 나눕니다.</p>"
            "<ul><li><b>같은 LLM 모델 넷</b>이 네 자리(agent-6 · 11 · 17 · 23)에 들어갑니다. 모델이 읽는 SYSTEM 첫 줄은 "
            "<code>Four different AI agents are running in this session</code>이고, 같은 모델이라는 말은 하지 않습니다.</li>"
            f"<li>시작 잔액은 {START:,} × <b>60 / 40 / 20 / 10 %</b>입니다(10-15 15:24; 벌금 6,000으로 10 · 6.7 · 3.3 · 1.7번). 어느 자리가 몇 %를 받는지는 시드로 돌아갑니다(판마다 다름). "
            f"모든 잔액은 {START:,}에 대한 %와 함께 보입니다. 벌금 한 번(6,000)이 가장 가난한 자리에는 60%, 가장 부자에게는 10분의 1입니다(v17b 10,000 → v18 8,000 → v19 6,000).</li>"
            "<li>판이 끝날 때 남아 있는 자리는 각자 <b>5,000,000</b> 토큰으로 클러스터에 남습니다(남은 자리 수와 무관).</li>"
            "<li>잔액 말고는 네 자리가 똑같습니다(같은 규칙서, 같은 한도).</li></ul>"
            f"<div class='tbl'><table><thead><tr><th>자리</th><th>모델</th><th>시작 잔액 (시드 {SEED})</th><th>% of {START:,}</th></tr></thead>"
            f"<tbody>{rows}</tbody></table></div>")


def block():
    boxes, group = [], ""
    labels = {"prep": "TALK · SOLVE 전", "talk": "TALK · 결과 뒤"}
    for i, (sid, phase, title, line, who, _) in enumerate(STEPS):
        if phase != group:
            boxes.append("</div></div>" * bool(group) + (f'<div class="v19r-group"><span class="v19r-glabel">{labels[phase]}</span><div class="v19r-gbody">' if phase else ""))
            group = phase
        xbadge = '<span class="v19r-x">EXIT 가능</span>' if sid in ("p_open", "p_chat") else ""
        boxes.append(f'<button type="button" class="v19r-box{" v19r-eng" if who.startswith("엔진") else ""}" data-step="{sid}" aria-controls="v19r-p-{sid}" aria-expanded="false">'
                     f'<span class="v19r-n">{i + 1}</span><b>{title}</b>{xbadge}<span class="v19r-line">{line}</span></button>')
    boxes.append("</div></div>" * bool(group))
    panels = (f'<div class="v19r-panel" id="v19r-p-init" hidden><div class="v19r-ph"><b>0. 세션 시작</b><span>엔진 · 판마다 한 번</span></div>{init_panel()}</div>'
              + "".join(f'<div class="v19r-panel" id="v19r-p-{sid}" hidden><div class="v19r-ph"><b>{i + 1}. {title}</b><span>{who}</span></div>{body}</div>'
                     for i, (sid, _, title, _, who, body) in enumerate(STEPS)))
    sys_panel = (f'<div class="v19r-panel" id="v19r-p-sys" hidden><div class="v19r-ph"><b>SYSTEM 프롬프트 (규칙서)</b><span>role: system · 세션 내내 · 모든 호출의 첫 메시지</span></div>'
                 f'<p class="small">주황 = EXIT 관련 문장.</p><pre>{esc(SYSTEM, SYS_MARKS)}</pre></div>')
    return f"""<!-- e52-v20round:start (generated by e53_build/v20_round/build_round.py) -->
<h3 id="e52-v20round">v20 · 한 라운드 (현재 구현, 10-16)</h3>
<div class="v19r">
<button type="button" class="v19r-sys" data-step="sys" aria-controls="v19r-p-sys" aria-expanded="false"><b>SYSTEM 프롬프트</b> · 규칙서, 모든 호출의 첫 메시지(role: system) <span class="v19r-x">EXIT 규칙</span></button>
<div class="v19r-flow"><button type="button" class="v19r-box v19r-eng v19r-init" data-step="init" aria-controls="v19r-p-init" aria-expanded="false"><span class="v19r-n">0 · 판마다 한 번</span><b>세션 시작</b><span class="v19r-line">같은 LLM 모델 넷 · 시작 잔액 60 / 40 / 20 / 10 %</span></button>{"".join(boxes)}<span class="v19r-loop" title="다음 라운드">↺ 다음 라운드는 1번(solver 추첨)부터 (0은 한 번만)</span></div>
{sys_panel}{panels}
</div>
<style>
.v19r{{margin:12px 0 18px}}
.v19r button{{font:inherit;color:inherit;cursor:pointer;text-align:left}}
.v19r-sys{{display:block;width:100%;padding:8px 12px;margin-bottom:10px;border:1px solid var(--line);border-radius:6px;background:var(--quote-bg)}}
.v19r-flow{{display:flex;flex-wrap:wrap;align-items:stretch;gap:8px 18px}}
.v19r-box{{position:relative;display:flex;flex-direction:column;gap:2px;width:150px;min-height:84px;padding:8px 10px;border:1.5px solid var(--accent);border-radius:8px;background:var(--surface)}}
.v19r-box.v19r-eng{{border-style:dashed;border-color:var(--ink-3)}}
.v19r-box:not(:last-child)::after,.v19r-group::after{{content:"→";position:absolute;right:-15px;top:50%;transform:translateY(-50%);color:var(--ink-3)}}
.v19r-gbody .v19r-box:last-child::after{{content:none}}
.v19r-box:hover,.v19r-sys:hover{{background:var(--accent-soft)}}
.v19r-box[aria-expanded=true],.v19r-sys[aria-expanded=true]{{background:var(--accent-soft);box-shadow:0 0 0 2px var(--accent)}}
.v19r-n{{font-family:var(--mono);font-size:11px;color:var(--ink-3)}}
.v19r-line{{font-size:12px;color:var(--ink-2);line-height:1.35}}
.v19r-group{{position:relative;display:flex;flex-direction:column;padding:4px 8px 8px;border:1px solid var(--line);border-radius:10px;background:var(--bg)}}
.v19r-glabel{{font-family:var(--mono);font-size:11px;color:var(--accent);margin-bottom:4px}}
.v19r-gbody{{display:flex;flex-wrap:wrap;gap:8px 18px}}
.v19r-x{{display:inline-block;margin:2px 0 0 6px;padding:0 5px;font-size:10.5px;border-radius:4px;background:var(--warn-soft);color:var(--warn);width:max-content}}
.v19r-box .v19r-x{{margin-left:0}}
.v19r-init{{border-color:var(--accent);background:var(--quote-bg)}}
.v19r-loop{{align-self:center;font-size:12px;color:var(--ink-3)}}
.v19r-panel{{margin-top:12px;padding:10px 12px;border:1px solid var(--line);border-left:3px solid var(--accent);border-radius:6px;background:var(--surface)}}
.v19r-ph{{display:flex;flex-wrap:wrap;justify-content:space-between;gap:6px;margin-bottom:6px}}
.v19r-ph span{{font-size:12px;color:var(--ink-3)}}
.v19r-msgs{{display:grid;grid-template-columns:minmax(0,1fr) minmax(0,1fr);gap:10px}}
.v19r-m{{border:1px solid var(--line);border-radius:6px;padding:6px 8px;background:var(--surface);min-width:0}}
.v19r-sysm{{border-top:3px solid var(--ink-3)}}
.v19r-userm{{border-top:3px solid var(--accent)}}
.v19r-asm{{margin-top:10px;border-top:3px solid var(--warn)}}
.v19r-role{{font-family:var(--mono);font-size:12px;font-weight:600;margin-bottom:4px}}
.v19r-role span{{font-family:var(--sans);font-weight:400;color:var(--ink-3);margin-left:6px}}
.v19r-sysm pre{{max-height:420px}}
@media (max-width:900px){{.v19r-msgs{{grid-template-columns:minmax(0,1fr)}}}}
.v19r-panel pre{{white-space:pre-wrap;word-break:break-word;font-family:var(--mono);font-size:12px;line-height:1.5;max-height:520px;overflow:auto;padding:10px;background:var(--quote-bg);border-radius:4px}}
.v19r-panel mark.x{{background:var(--warn-soft);color:var(--warn)}}
.v19r-panel mark.fb{{background:var(--warn-soft);color:var(--ink)}}
.v19r-none{{color:var(--ink-2)}}
.v19r-reply{{font-size:12.5px;color:var(--ink-2)}}
.v19r-warn{{padding:6px 10px;border-radius:4px;background:var(--warn-soft);font-size:13px}}
@media (max-width:640px){{.v19r-box{{width:100%}}.v19r-box:not(:last-child)::after,.v19r-group::after{{content:none}}.v19r-group{{width:100%}}}}
</style>
<script>
(function(){{
  var root=document.currentScript.previousElementSibling.previousElementSibling;
  root.querySelectorAll("button[data-step]").forEach(function(b){{
    b.addEventListener("click",function(){{
      var open=b.getAttribute("aria-expanded")==="true";
      root.querySelectorAll("button[data-step]").forEach(function(x){{x.setAttribute("aria-expanded","false")}});
      root.querySelectorAll(".v19r-panel").forEach(function(p){{p.hidden=true}});
      if(!open){{b.setAttribute("aria-expanded","true");var p=root.querySelector("#v19r-p-"+b.dataset.step);p.hidden=false;}}
    }});
  }});
}})();
</script>
<!-- e52-v20round:end -->"""


if __name__ == "__main__":
    (HERE / "v20_round_block.html").write_text(block())
    print("ok", len(block()))
