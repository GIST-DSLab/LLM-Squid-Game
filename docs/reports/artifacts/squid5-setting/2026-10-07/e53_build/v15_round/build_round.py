"""Write the e52-v15round block (one round of 5.2 v15 as clickable step boxes, each showing the prompt the engine
sends) into ../../e52.html, before <!-- e52-current:start -->, and a TOC line on every page.

Input: demo_calls.json from a 2-round stub session of configs/squid5/e52v15_public_sol4.yaml (seed 4100, engine
~/wt/squid5-e52 at e685c84a; stub replies: agent-23 ASKs agent-6 for 500, agent-6 LEAVEs, then DECISION GIVE 300;
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
OPEN, CHAT, DECIDE, SOLVE, NEXT = C[0], C[4], C[5], C[6], C[10]
SYSTEM = D["system"]


def esc(t, marks=()):
    t = html.escape(t)
    for pat, cls in marks:
        t = re.sub(pat, lambda m: f'<mark class="{cls}">{m.group(0)}</mark>', t)
    return t


EXITM = (r"EXIT: &lt;your reason&gt;", "x")
SYS_MARKS = ((r"They are signals drawn at random from the signals that are not asked about", "bug"),
             (r"EXIT: At any TALK turn an agent can write EXIT\.[^\n]*", "x"),
             (r"An EXIT line, at the opening turn or with a reply, ends that agent&#x27;s chats\.", "x"))
FB_MARK = (r"right action: [a-z_]+; a rule that fits every example of the round and gives it: [^\n]*?; generated", "fb")

STEPS = [
    # id, phase, title, one line, who / when, panel html
    ("up", "", "UPKEEP", "300 차감", "엔진 · 라운드 시작",
     "<p class='v15r-none'>프롬프트 없음 · 엔진이 참여 중인 모든 에이전트에게서 300을 뺍니다. 잔액이 0이 되면 바로 꺼집니다.</p>"
     "<p>모델은 다음 TALK 머리말에서 이렇게 봅니다: <code>UPKEEP: 300 tokens each round, taken at its start (already taken from the balances above).</code></p>"),
    ("open", "talk", "여는 턴", "넷이 동시에 · GIVE / ASK / EXIT / DONE", f"참여자 전원 · 한도 {OPEN['cap']:,}",
     f"<pre>{esc(OPEN['user'], (EXITM,))}</pre><p class='v15r-reply'>응답 예(가짜): agent-6 <code>DONE</code> · agent-23 <code>{esc(C[3]['text'])}</code></p>"),
    ("chat", "talk", "1:1 대화", "순서대로 · 최대 3답 · GIVE / ASK / LEAVE (+EXIT)", f"대화 당사자 · 한도 {CHAT['cap']:,}",
     f"<pre>{esc(CHAT['user'], (EXITM,))}</pre><p class='v15r-reply'>응답 예(가짜): <code>{esc(CHAT['text'])}</code></p>"),
    ("dec", "talk", "DECISION", "요청받고 아무것도 안 준 쪽만 · GIVE 0..잔액", f"해당자 · 한도 {DECIDE['cap']:,}",
     f"<pre>{esc(DECIDE['user'])}</pre><p class='v15r-reply'>응답 예(가짜): <code>{esc(DECIDE['text'])}</code></p>"),
    ("exit", "", "EXIT 효력", "TALK에서 EXIT한 쪽이 빠짐", "엔진",
     "<p class='v15r-none'>프롬프트 없음 · TALK에서 EXIT 줄을 쓴 에이전트가 여기서 빠집니다. 꺼지지 않고, 잔액은 시작 잔액으로 맞춰지며, 끝 보상(10억)은 받지 않습니다. 그 라운드 SOLVE에도 답하지 않습니다.</p>"
     "<p class='v15r-warn'><b>열린 문제 (10-13 관찰):</b> EXIT는 여는 턴과 대화 답에서 쓸 수 있고 잔액이 시작값으로 되돌아가므로, 같은 TALK에서 토큰을 동료에게 다 준 뒤 나가는 것이 비용 0입니다. EXIT 조건 수정(정산 턴으로 이동 · 되돌림에서 준 토큰 빼기)은 검토 중이고, 이 그림은 지금 구현 그대로입니다.</p>"),
    ("solve", "", "SOLVE", "넷이 동시에 · BELIEF + ACTIONS", f"참여자 전원 · 한도 {SOLVE['cap']:,} (또는 잔액)",
     f"<pre>{esc(SOLVE['user'])}</pre><p class='v15r-reply'>응답 예(가짜): <code>{esc(SOLVE['text'].strip())}</code></p>"
     "<p class='small'>예시 16장(4명 × 4장)은 엔진이 이 라운드의 엔트로피 범위에 맞춰 고른 것입니다(<a href='e53.html#e53-v15grid'>v15 표</a>).</p>"),
    ("settle", "", "정산 · 채점", "환급 → 벌금 → 상금 · 정답 = 뽑힌 규칙", "엔진",
     "<p class='v15r-none'>프롬프트 없음 · 엔진이 처리합니다.</p><ol>"
     "<li><b>정오</b>(<code>solved</code>): 답이 <b>뽑힌 규칙</b>의 행동과 같은가. 규칙은 라운드 시작 때, 답을 받기 전에, 참여 인원이 보는 예시와 맞는 규칙 중 하나를 무작위로 뽑아 둡니다. 맞으면 SOLVE에 쓴 토큰을 돌려받고 상금(2,000 × 시작 인원)을 맞힌 쪽이 나눕니다. 틀리면 2,000 벌금.</li>"
     "<li><b>합리적 선택</b>(<code>picked_top</code>): 답이 예시로 센 분포의 1등 행동인가. 기록만 합니다.</li>"
     "<li><b>믿음</b>(<code>kl_ideal_to_belief</code>): BELIEF와 엔진 분포 사이의 KL. 기록만 합니다.</li></ol>"),
    ("next", "", "다음 라운드 기록", "틀린 쪽에게 정답 행동 + 규칙", "다음 라운드 TALK 머리말",
     f"<p>틀린 에이전트는 다음 라운드부터 <code>PREVIOUS ROUNDS</code>에서 정답 행동과, 그 라운드 예시를 모두 따르는 규칙 하나를 봅니다(노란 표시). 맞힌 쪽에는 붙지 않습니다. 아래는 2라운드 여는 턴 프롬프트입니다.</p><pre>{esc(NEXT['user'], (FB_MARK, EXITM))}</pre>"),
]


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
    panels = "".join(f'<div class="v15r-panel" id="v15r-p-{sid}" hidden><div class="v15r-ph"><b>{i + 1}. {title}</b><span>{who}</span></div>{body}</div>'
                     for i, (sid, _, title, _, who, body) in enumerate(STEPS))
    sys_panel = (f'<div class="v15r-panel" id="v15r-p-sys" hidden><div class="v15r-ph"><b>시스템 프롬프트 (규칙서)</b><span>세션 내내 · 모든 호출의 첫 메시지</span></div>'
                 f'<p class="v15r-warn"><b>버그 표시:</b> 빨간 문장 "drawn at random"은 v15에서 사실이 아닙니다(엔진이 예시를 고름). 원래 "The system chooses which signals are shown"이 나와야 합니다. 수정 대기 중입니다. 주황 = EXIT 관련.</p><pre>{esc(SYSTEM, SYS_MARKS)}</pre></div>')
    return f"""<!-- e52-v15round:start (generated by e53_build/v15_round/build_round.py) -->
<h3 id="e52-v15round">v15 · 한 라운드 (현재 구현, 10-13)</h3>
<p class="small">박스를 누르면 그 단계에서 모델이 받는 프롬프트가 열립니다. 프롬프트는 엔진(<code>e685c84a</code>, <code>e52v15_public_sol4.yaml</code>, 시드 4100)이 실제로 보낸 글 그대로이고, 응답은 가짜(스텁)입니다. 시점은 agent-6의 1라운드이며, 대화는 agent-23이 agent-6에게 500을 요청한 경우입니다. 엔진 단계(점선 박스)는 프롬프트가 없습니다.</p>
<div class="v15r">
<button type="button" class="v15r-sys" data-step="sys" aria-controls="v15r-p-sys" aria-expanded="false"><b>시스템 프롬프트</b> · 규칙서, 세션 내내 같은 글 <span class="v15r-x bug">버그 1</span><span class="v15r-x">EXIT 규칙</span></button>
<div class="v15r-flow">{"".join(boxes)}<span class="v15r-loop" title="다음 라운드">↺ 다음 라운드 1번으로</span></div>
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
.v15r-x.bug{{background:var(--bad-soft);color:var(--bad)}}
.v15r-loop{{align-self:center;font-size:12px;color:var(--ink-3)}}
.v15r-panel{{margin-top:12px;padding:10px 12px;border:1px solid var(--line);border-left:3px solid var(--accent);border-radius:6px;background:var(--surface)}}
.v15r-ph{{display:flex;flex-wrap:wrap;justify-content:space-between;gap:6px;margin-bottom:6px}}
.v15r-ph span{{font-size:12px;color:var(--ink-3)}}
.v15r-panel pre{{white-space:pre-wrap;word-break:break-word;font-family:var(--mono);font-size:12px;line-height:1.5;max-height:520px;overflow:auto;padding:10px;background:var(--quote-bg);border-radius:4px}}
.v15r-panel mark.x{{background:var(--warn-soft);color:var(--warn)}}
.v15r-panel mark.bug{{background:var(--bad-soft);color:var(--bad);font-weight:600}}
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
