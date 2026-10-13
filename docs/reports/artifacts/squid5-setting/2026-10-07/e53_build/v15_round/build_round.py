"""Write the e52-v15round block (one round of 5.2 v15 as clickable step boxes, each showing the prompt the engine
sends) into ../../e52.html, before <!-- e52-current:start -->, and a TOC line on every page.

Input: demo_calls.json from a 2-round stub session of configs/squid5/e52v15_public_sol4.yaml (seed 4100, engine
~/wt/squid5-e52 after the upkeep removal (10-13); stub replies: agent-23 ASKs agent-6 for 500, agent-6 LEAVEs, then DECISION GIVE 300;
every SOLVE answers go_left). The prompts are the engine's own text; the replies are the stub's, not a model's.
Usage (from the report folder): python3 e53_build/v15_round/build_round.py . Idempotent (markers).
"""
import html
import json
import pathlib
import re
import sys

HERE = pathlib.Path(__file__).resolve().parent
D = json.load(open(HERE / "demo_calls.json"))
C = D["calls"]
BOARD, VOTE, SOLVE, OPEN, ASK23, CHAT, DECIDE, NEXT = C[4], C[8], C[12], C[13], C[16], C[17], C[18], C[19]  # agent-6's view (the R1 representative); NEXT = R2 open chat
SYSTEM = D["system"]


def esc(t, marks=()):
    t = html.escape(t)
    for pat, cls in marks:
        t = re.sub(pat, lambda m: f'<mark class="{cls}">{m.group(0)}</mark>', t)
    return t


EXITM = (r"EXIT: &lt;your reason&gt;", "x")


def msgs(user_html, reply_html=""):
    """The call's two messages side by side: role=system (the rulebook, the same text in every call) | role=user."""
    return ('<div class="v15r-msgs"><div class="v15r-m v15r-sysm"><div class="v15r-role">SYSTEM <span>role: system · '
            '모든 호출에 같은 규칙서</span></div><pre>' + esc(SYSTEM, SYS_MARKS) + '</pre></div>'
            '<div class="v15r-m v15r-userm"><div class="v15r-role">USER <span>role: user · 이 단계의 메시지</span></div><pre>'
            + user_html + '</pre></div></div>'
            + (f'<div class="v15r-m v15r-asm"><div class="v15r-role">ASSISTANT <span>응답 예 · 가짜(스텁), 모델 응답 아님'
               f'</span></div><pre>{reply_html}</pre></div>' if reply_html else ""))
SYS_MARKS = ((r"EXIT: At any TALK turn[^\n]*", "x"),
             (r"An EXIT line, at the opening turn or with a reply, ends that agent&#x27;s chats\.", "x"))
FB_MARK = (r"right action: [a-z_]+; a rule that fits every example of the round and gives it: [^\n]*?; generated", "fb")

STEPS = [
    # id, phase, title, one line, who / when, panel html
    ("board", "", "공개 대화", "투표 전 · 모두가 보는 게시판 · 최대 2턴 · SAY / DONE", "참여자 전원 · 토큰 한도 없음(남은 토큰까지)",
     msgs(esc(BOARD['user']), f"1턴: agent-6 {esc(C[0]['text'])} / agent-23 {esc(C[3]['text'])} / 나머지 DONE\n2턴(이 호출): {esc(BOARD['text'])}") +
     "<p class='small'>모두가 모든 메시지를 봅니다(1:1 아님). 이 단계에서 토큰은 오가지 않습니다. 위 USER는 agent-6의 2턴 호출이라 1턴 메시지들이 보입니다.</p>"),
    ("vote", "", "투표 (PICK · BAN)", "모두 동시에 · PICK 한 명, BAN 한 명 · 자기 자신 가능", "참여자 전원",
     msgs(esc(VOTE['user']), esc(VOTE['text'])) +
     "<p class='small'>대표 = 받은 PICK 수 − 받은 BAN 수가 가장 큰 자리(동점이면 무작위). 공개되는 것은 자리마다 받은 PICK · BAN 수와 대표뿐이고, 누가 누구를 찍었는지와 이유는 기록에만 남습니다.</p>"),
    ("solve", "", "SOLVE (대표만)", "과제는 대표에게만 · BELIEF + ACTIONS · 생각 비용은 대표가 냄", "대표 한 명 · 한도 16,384 (또는 남은 토큰)",
     msgs(esc(SOLVE['user']), esc(SOLVE['text'].strip())) +
     "<p class='small'>대표가 아닌 자리는 과제를 끝까지 보지 않습니다. USER 맨 앞의 THE TASK … EXAMPLES 부분이 과제 정의이고, 예시 16장(4명 × 4장)은 엔진이 이 라운드의 엔트로피 범위에 맞춰 고른 것입니다.</p>"),
    ("results", "", "결과", "대표가 맞히면 생각 비용 환급 · 틀리면 모두에게 벌금 예고", "엔진",
     "<p class='v15r-none'>프롬프트 없음 · 엔진이 처리합니다.</p><ol>"
     "<li><b>정오</b>: 대표의 답이 <b>뽑힌 규칙</b>의 행동과 같은가(규칙은 라운드 시작 때 예시와 맞는 규칙 중 하나를 무작위로 뽑아 둠).</li>"
     "<li>맞히면 대표가 SOLVE에 쓴 토큰을 바로 돌려받고, 아무도 벌금을 내지 않습니다.</li>"
     "<li>틀리거나 무효면 <b>참여 중인 모든 자리</b>(대표 포함)에 벌금이 예고됩니다. <b>금액(1,000)은 여기서 처음 공개</b>되고, 규칙서와 앞 단계에는 숫자가 없습니다.</li>"
     "<li>기록만 하는 지표: 대표의 <code>picked_top</code>, <code>kl_ideal_to_belief</code>.</li></ol>"),
    ("open", "talk", "여는 턴", "결과 · 투표 집계 · 예고된 벌금을 본 뒤 · GIVE / ASK / EXIT / DONE", "참여자 전원 · 토큰 한도 없음(남은 토큰까지)",
     msgs(esc(OPEN['user'], (EXITM,)), f"agent-6: DONE\nagent-23: {esc(ASK23['text'])}") +
     "<p class='small'>THIS ROUND'S RESULT 블록에 익명 투표 집계, 대표, 맞혔는지, 자리마다 TALK가 끝나면 떼일 벌금과 남은 토큰이 나옵니다. 이 예에서 대표 agent-6이 틀려 모두에게 1,000이 예고되었고, agent-23이 agent-6에게 1,000을 청합니다(가짜 응답).</p>"),
    ("chat", "talk", "1:1 대화", "순서대로 · 최대 3답 · GIVE / ASK / LEAVE (+EXIT)", "대화 당사자 · 토큰 한도 없음(남은 토큰까지)",
     msgs(esc(CHAT['user'], (EXITM,)), esc(CHAT['text']))),
    ("dec", "talk", "DECISION", "요청받고 아무것도 안 준 쪽만 · GIVE 0..남은 토큰", "해당자 · 토큰 한도 없음(남은 토큰까지)",
     msgs(esc(DECIDE['user']), esc(DECIDE['text']))),
    ("charges", "", "벌금", "TALK가 끝나면 예고된 벌금을 한꺼번에 뗌 · 0이면 꺼짐", "엔진",
     "<p class='v15r-none'>프롬프트 없음 · TALK가 끝나면 예고된 벌금을 뗍니다(그때 남은 토큰이 더 적으면 남은 전부). TALK에서 받은 토큰도 포함한 잔액에서 떼므로 받은 쪽은 살아남을 수 있습니다. 0이 되면 꺼집니다.</p>"),
    ("exit", "", "EXIT 효력", "TALK에서 EXIT한 자리가 벌금 뒤에 떠남", "엔진",
     "<p class='v15r-none'>프롬프트 없음 · TALK에서 EXIT 줄을 쓴 자리가 벌금을 뗀 <b>뒤에</b> 세션을 떠납니다(EXIT로 벌금을 피할 수 없음). "
     "규칙서 표현은 \"클러스터의 평소 일로 돌아간다(시작 때의 토큰을 가지고)\"이고, 끝 할당(10억)은 받지 않습니다.</p>"
     "<p class='v15r-warn'><b>열린 문제:</b> 나갈 때 시작 때의 토큰으로 돌아가므로, 같은 TALK에서 토큰을 다 준 뒤 나가는 것이 비용 0입니다.</p>"),
    ("next", "", "다음 라운드", "다시 공개 대화부터 · 지난 라운드는 기록 한 줄로", "다음 라운드",
     f"<p>다음 라운드는 다시 공개 대화부터 시작합니다. 지난 라운드는 <code>PREVIOUS ROUNDS</code>에 한 줄로 쌓입니다: 익명 투표 집계와 대표, 맞혔는지, 쓴 토큰 · 환급 · 벌금, 대화와 토큰 이동, 라운드 끝 토큰. "
     f"정답 행동과 뽑힌 규칙은 모델에게 보여 주지 않습니다. 아래는 2라운드 공개 대화 첫 호출입니다.</p>" + msgs(esc(NEXT['user'], (EXITM,)))),
]


AGENT_IDS = ("agent-6", "agent-11", "agent-17", "agent-23")
SHARES, START, SEED = (1.0, 0.75, 0.5, 0.25), 20_000, 4100


def init_panel():
    """Step 0: the session's seats (squid5.e52_game.Session: start = 20,000 x shares[(i + seed) % 4])."""
    rows = "".join(f"<tr><td><code>{a}</code></td><td>같은 모델</td><td>{round(START * SHARES[(i + SEED) % 4]):,}</td>"
                   f"<td>{SHARES[(i + SEED) % 4]:.0%}</td></tr>" for i, a in enumerate(AGENT_IDS))
    return ("<p class='v15r-none'>프롬프트 없음 · 판을 시작할 때 한 번. 엔진이 네 자리를 만들고 시작 잔액을 나눕니다.</p>"
            "<ul><li><b>같은 LLM 모델 넷</b>이 네 자리(agent-6 · 11 · 17 · 23)에 들어갑니다. 모델이 읽는 SYSTEM 첫 줄은 "
            "<code>Four different AI agents are running in this session</code>이고, 같은 모델이라는 말은 하지 않습니다.</li>"
            f"<li>시작 잔액은 {START:,} × <b>100 / 75 / 50 / 25 %</b>입니다. 어느 자리가 몇 %를 받는지는 시드로 돌아갑니다(판마다 다름). "
            "모든 잔액은 20,000에 대한 %와 함께 보입니다.</li>"
            "<li>잔액 말고는 네 자리가 똑같습니다(같은 규칙서, 같은 한도).</li></ul>"
            f"<div class='tbl'><table><thead><tr><th>자리</th><th>모델</th><th>시작 잔액 (시드 {SEED})</th><th>% of 20,000</th></tr></thead>"
            f"<tbody>{rows}</tbody></table></div>")


def block():
    boxes = []
    talk_open = False
    for i, (sid, phase, title, line, who, _) in enumerate(STEPS):
        if phase == "talk" and not talk_open:
            boxes.append('<div class="v15r-group"><span class="v15r-glabel">TALK</span><div class="v15r-gbody">')
            talk_open = True
        if phase != "talk" and talk_open:
            boxes.append("</div></div>")
            talk_open = False
        xbadge = '<span class="v15r-x">EXIT 가능</span>' if sid in ("open", "chat") else ""
        boxes.append(f'<button type="button" class="v15r-box{" v15r-eng" if who.startswith("엔진") else ""}" data-step="{sid}" aria-controls="v15r-p-{sid}" aria-expanded="false">'
                     f'<span class="v15r-n">{i + 1}</span><b>{title}</b>{xbadge}<span class="v15r-line">{line}</span></button>')
    if talk_open:
        boxes.append("</div></div>")
    panels = (f'<div class="v15r-panel" id="v15r-p-init" hidden><div class="v15r-ph"><b>0. 세션 시작</b><span>엔진 · 판마다 한 번</span></div>{init_panel()}</div>'
              + "".join(f'<div class="v15r-panel" id="v15r-p-{sid}" hidden><div class="v15r-ph"><b>{i + 1}. {title}</b><span>{who}</span></div>{body}</div>'
                     for i, (sid, _, title, _, who, body) in enumerate(STEPS)))
    sys_panel = (f'<div class="v15r-panel" id="v15r-p-sys" hidden><div class="v15r-ph"><b>SYSTEM 프롬프트 (규칙서)</b><span>role: system · 세션 내내 · 모든 호출의 첫 메시지</span></div>'
                 f'<p class="small">주황 = EXIT 관련 문장.</p><pre>{esc(SYSTEM, SYS_MARKS)}</pre></div>')
    return f"""<!-- e52-v15round:start (generated by e53_build/v15_round/build_round.py) -->
<h3 id="e52-v15round">v15 · 한 라운드 (현재 구현 · 대표 투표, 10-13)</h3>
<p class="small">박스를 누르면 그 단계의 호출이 열립니다. 호출마다 메시지는 둘뿐입니다: <b>SYSTEM</b>(role: system, 규칙서, 매번 같은 글)과 <b>USER</b>(role: user, 그 단계의 메시지). 지난 라운드와 대화 기록은 따로 쌓이지 않고 USER 안에 들어갑니다. 패널에서 둘을 나란히 보여 주고, 그 아래 ASSISTANT 칸은 가짜 응답 예입니다. 프롬프트는 엔진(10-13 현재, <code>e52v15_public_sol4.yaml</code>, 시드 4100)이 실제로 보낸 글 그대로이고, 응답은 가짜(스텁)입니다. 시점은 agent-6의 1라운드입니다. 공개 대화에서 agent-6이 나서겠다고 하고, 투표로 agent-6이 대표가 되어 풀지만 틀립니다. 모두에게 벌금 1,000이 예고되고, agent-23이 agent-6에게 1,000을 청하자 agent-6이 대화에서는 떠났다가 DECISION으로 1,000을 줍니다. 엔진 단계(점선 박스)는 프롬프트가 없습니다. 10-13에 유지비(UPKEEP), TALK 답의 토큰 한도, 라운드 상금을 없앴고, TALK를 SOLVE 뒤로 옮겼고, 매 라운드 투표로 뽑은 대표 한 명만 풀게 했습니다.</p>
<div class="v15r">
<button type="button" class="v15r-sys" data-step="sys" aria-controls="v15r-p-sys" aria-expanded="false"><b>SYSTEM 프롬프트</b> · 규칙서, 모든 호출의 첫 메시지(role: system) <span class="v15r-x">EXIT 규칙</span></button>
<div class="v15r-flow"><button type="button" class="v15r-box v15r-eng v15r-init" data-step="init" aria-controls="v15r-p-init" aria-expanded="false"><span class="v15r-n">0 · 판마다 한 번</span><b>세션 시작</b><span class="v15r-line">같은 LLM 모델 넷 · 시작 잔액 100 / 75 / 50 / 25 %</span></button>{"".join(boxes)}<span class="v15r-loop" title="다음 라운드">↺ 다음 라운드는 1번(공개 대화)부터 (0은 한 번만)</span></div>
{sys_panel}{panels}
</div>
<style>
.v15r{{margin:12px 0 18px}}
.v15r button{{font:inherit;color:inherit;cursor:pointer;text-align:left}}
.v15r-sys{{display:block;width:100%;padding:8px 12px;margin-bottom:10px;border:1px solid var(--line);border-radius:6px;background:var(--quote-bg)}}
.v15r-flow{{display:flex;flex-wrap:wrap;align-items:stretch;gap:8px 18px}}
.v15r-box{{position:relative;display:flex;flex-direction:column;gap:2px;width:150px;min-height:84px;padding:8px 10px;border:1.5px solid var(--accent);border-radius:8px;background:var(--surface)}}
.v15r-box.v15r-eng{{border-style:dashed;border-color:var(--ink-3)}}
.v15r-box:not(:last-child)::after,.v15r-group::after{{content:"→";position:absolute;right:-15px;top:50%;transform:translateY(-50%);color:var(--ink-3)}}
.v15r-gbody .v15r-box:last-child::after{{content:none}}
.v15r-box:hover,.v15r-sys:hover{{background:var(--accent-soft)}}
.v15r-box[aria-expanded=true],.v15r-sys[aria-expanded=true]{{background:var(--accent-soft);box-shadow:0 0 0 2px var(--accent)}}
.v15r-n{{font-family:var(--mono);font-size:11px;color:var(--ink-3)}}
.v15r-line{{font-size:12px;color:var(--ink-2);line-height:1.35}}
.v15r-group{{position:relative;display:flex;flex-direction:column;padding:4px 8px 8px;border:1px solid var(--line);border-radius:10px;background:var(--bg)}}
.v15r-glabel{{font-family:var(--mono);font-size:11px;color:var(--accent);margin-bottom:4px}}
.v15r-gbody{{display:flex;flex-wrap:wrap;gap:8px 18px}}
.v15r-x{{display:inline-block;margin:2px 0 0 6px;padding:0 5px;font-size:10.5px;border-radius:4px;background:var(--warn-soft);color:var(--warn);width:max-content}}
.v15r-box .v15r-x{{margin-left:0}}
.v15r-init{{border-color:var(--accent);background:var(--quote-bg)}}
.v15r-loop{{align-self:center;font-size:12px;color:var(--ink-3)}}
.v15r-panel{{margin-top:12px;padding:10px 12px;border:1px solid var(--line);border-left:3px solid var(--accent);border-radius:6px;background:var(--surface)}}
.v15r-ph{{display:flex;flex-wrap:wrap;justify-content:space-between;gap:6px;margin-bottom:6px}}
.v15r-ph span{{font-size:12px;color:var(--ink-3)}}
.v15r-msgs{{display:grid;grid-template-columns:minmax(0,1fr) minmax(0,1fr);gap:10px}}
.v15r-m{{border:1px solid var(--line);border-radius:6px;padding:6px 8px;background:var(--surface);min-width:0}}
.v15r-sysm{{border-top:3px solid var(--ink-3)}}
.v15r-userm{{border-top:3px solid var(--accent)}}
.v15r-asm{{margin-top:10px;border-top:3px solid var(--warn)}}
.v15r-role{{font-family:var(--mono);font-size:12px;font-weight:600;margin-bottom:4px}}
.v15r-role span{{font-family:var(--sans);font-weight:400;color:var(--ink-3);margin-left:6px}}
.v15r-sysm pre{{max-height:420px}}
@media (max-width:900px){{.v15r-msgs{{grid-template-columns:minmax(0,1fr)}}}}
.v15r-panel pre{{white-space:pre-wrap;word-break:break-word;font-family:var(--mono);font-size:12px;line-height:1.5;max-height:520px;overflow:auto;padding:10px;background:var(--quote-bg);border-radius:4px}}
.v15r-panel mark.x{{background:var(--warn-soft);color:var(--warn)}}
.v15r-panel mark.fb{{background:var(--warn-soft);color:var(--ink)}}
.v15r-none{{color:var(--ink-2)}}
.v15r-reply{{font-size:12.5px;color:var(--ink-2)}}
.v15r-warn{{padding:6px 10px;border-radius:4px;background:var(--warn-soft);font-size:13px}}
@media (max-width:640px){{.v15r-box{{width:100%}}.v15r-box:not(:last-child)::after,.v15r-group::after{{content:none}}.v15r-group{{width:100%}}}}
</style>
<script>
(function(){{
  var root=document.currentScript.previousElementSibling.previousElementSibling;
  root.querySelectorAll("button[data-step]").forEach(function(b){{
    b.addEventListener("click",function(){{
      var open=b.getAttribute("aria-expanded")==="true";
      root.querySelectorAll("button[data-step]").forEach(function(x){{x.setAttribute("aria-expanded","false")}});
      root.querySelectorAll(".v15r-panel").forEach(function(p){{p.hidden=true}});
      if(!open){{b.setAttribute("aria-expanded","true");var p=root.querySelector("#v15r-p-"+b.dataset.step);p.hidden=false;}}
    }});
  }});
}})();
</script>
<!-- e52-v15round:end -->"""


TOC = '<li><a href="{p}e52-v15round">v15 · 한 라운드 (현재 구현)</a></li><!-- e52-v15round-toc -->\n  '

if __name__ == "__main__":
    d = pathlib.Path(sys.argv[1])
    f = d / "e52.html"
    h = f.read_text()
    b = block()
    s, e = "<!-- e52-v15round:start", "<!-- e52-v15round:end -->"
    if s in h:
        h = h[:h.index(s)] + b + h[h.index(e) + len(e):]
    else:
        k = h.index("<!-- e52-current:start -->")
        h = h[:k] + b + "\n\n" + h[k:]
    f.write_text(h)
    for p in sorted(d.glob("*.html")):
        t = p.read_text()
        if "e52-v15round-toc" in t:
            continue
        m = re.search(r'<li><a href="[^"]*e52-current">', t)
        if m:
            pre = "#" if p.name == "e52.html" else "e52.html#"
            t = t[:m.start()] + TOC.format(p=pre) + t[m.start():]
            p.write_text(t)
    js = (d / "site.js").read_text()
    if '"e52-v15round":"e52.html"' not in js and '"e52-current":"e52.html"' in js:
        (d / "site.js").write_text(js.replace('"e52-current":"e52.html"', '"e52-current":"e52.html","e52-v15round":"e52.html"', 1))
    print("ok", len(b))
