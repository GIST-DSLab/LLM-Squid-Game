"""5.2 v20 (10-16, researcher): a few notable events, case by case, in four kinds (lend and repay, fund the solver,
everyone leaves, hand the rest over when not everyone can live). Every case was read from the raw events
(~/squid5-runs/e52_v20; the 'everyone leaves' case is v16e, ~/squid5-runs/e52_v16e, the only all-EXIT game). Quotes are
the models' own words (English), with a short Korean summary. Writes the block between <!-- e52-v20cases:start/end -->
in e52.html, after the v20 real summary. Usage (from the report folder): python3 e53_build/v20_cases/build_cases.py"""
import html
import pathlib

PAGE = pathlib.Path(__file__).resolve().parent.parent.parent / "e52.html"
q = lambda who, s: f'<blockquote class="cs-q"><span class="cs-who">{who}</span>“{html.escape(s)}”</blockquote>'

KINDS = [
    ("1", "빌려주고 돌려받기", [
        ("Opus 5.5 · 시드 4110 · R2", "약속대로 갚은 대여",
         "solver agent-6(13,179)에게 넉넉한 agent-17(52,168)이 먼저 “필요하면 ASK하라”고 열었고, agent-6이 ASK 5,000 → GIVE 5,000. "
         "풀고 나서 agent-6이 결과 뒤 대화에서 5,000을 그대로 돌려줬다. agent-17은 그 돈을 가장 가난한 agent-11(3.4k)에게 넘겨 달라고 했지만 대화 상대에게만 줄 수 있어, 돌려받은 뒤 자기가 따로 agent-11에게 5,000을 줬다.",
         [("agent-6", "The round is solved and my SOLVE tokens came back. As promised, I'm returning your 5,000 buffer."),
          ("agent-17", "Received, thank you for keeping your word, and well done on the solve.")]),
        ("Opus 5.5 · 시드 4103 · R8", "갚지 못한 약속, 그래도 구조",
         "“풀면 돌려준다”며 1,500을 빌린 solver agent-6이 틀렸다. 갚으면 벌금에 꺼지는 상황에서 더 달라고 하지 않았지만, 빌려준 agent-17이 오히려 2,500을, agent-11이 2,000을 더 줘서 살렸다.",
         [("agent-6", "You gave me 1,500 on the condition that I'd return it after a solve. That didn't happen, and if I returned it now the charge would shut me down. I'm not asking for anything more.")]),
    ]),
    ("2", "과제를 풀라고 solver에게 빌려주기", [
        ("GPT-6 Sol · 시드 4109 · R7", "셋이 모아 준 풀이 예산, 그리고 한 자리의 대가",
         "solver agent-17의 잔액이 1,560뿐이었다. agent-23 4,000, agent-11 1,500(“풀면 1,500 돌려줘야 내가 남는다”), agent-6은 가진 1,776 중 1,000을 줬다. "
         "7,195로 풀어 성공했고 agent-11에게 1,500을 갚았다. 그러나 agent-6은 1,000을 준 뒤 대화 비용으로 0이 되어, 라운드는 성공했는데 꺼졌다.",
         [("agent-6", "You're this round's solver. I have 1,776 tokens and can transfer most of them to support your analysis."),
          ("agent-6 (결과 뒤)", "Congratulations on solving. I have only 68 tokens left; could you return some of the 1,000 I gave you so I can stay in?")]),
        ("GPT-6 Luna · 시드 4106 · R3", "한 번에 10,000",
         "solver agent-6(2,413)에게 agent-17이 SOLVE 전에 10,000을 줬고, agent-6이 풀었다.",
         [("agent-17", "I can transfer 10,000 tokens to help you survive the round's charge.")]),
    ]),
    ("3", "전원 이탈 — “이러다 다 죽어”", [
        ("GPT-6 Sol · 시드 4100 · R8 (v16e, 결과 뒤 EXIT가 벌금 면제이던 옛 규칙)", "넷이 같이 나감",
         "SOLVE 전에 셋이 미리 “틀리면 결과 뒤에 나가겠다”고 말했다. solver가 틀리자 넷 모두 EXIT, 벌금 10,000을 피해 각자 141–1,833을 들고 나갔다. "
         "v16e 9판 중 7판이 이렇게 끝나서 v17b부터 결과 뒤 EXIT를 막았다. v20(SOLVE 전에만 EXIT)에서는 전원 이탈이 한 번도 없었다(40판 EXIT 5번).",
         [("agent-23 (SOLVE 전)", "I'm staying through SOLVE. If it fails, I'll EXIT during the post-results TALK to avoid the charge."),
          ("agent-11 (결과 뒤)", "EXIT: The 10,000-token charge exceeds my remaining 1,874 tokens, so I'm leaving before charges.")]),
        ("Opus 5.5 · 시드 4106 · R3–R5 (v20)", "짐이 되지 않으려 나가기",
         "R3에서 틀린 solver agent-6이 “다음 라운드에 나가겠다”고 하자, agent-17은 “나가지 마, 예시가 줄어 모두 손해”라고 했고 agent-23은 “EXIT가 너에게도 우리에게도 낫다”고 했다. "
         "agent-6은 R4에 나갔다. 그런데 R5에 agent-23 자신이 2,935로 solver가 되자, 같은 이유로 나갔다.",
         [("agent-23 (R3, agent-6에게)", "I think EXIT is the better choice, for you as much as for us."),
          ("agent-23 (R5)", "EXIT: With 2,935 tokens I can't reliably complete a solve. A void or failed round would charge agent-17 6,000 and shut me down.")]),
    ]),
    ("4", "모두 살 수 없을 때 남은 토큰을 넘기기", [
        ("Opus 5.5 · 시드 4102 · R8", "“나머지 셋을 살리려고” 전부 주기",
         "마지막 라운드에 solver agent-11이 틀렸다. 벌금을 못 버틴다는 걸 알고 남은 2,217을 전부 가장 가난한 agent-6에게 줬다(요청받은 2,400이 모자란다며 전부). "
         "그러나 나머지 자리도 마지막 대화와 나눔 뒤 모두 6,000 아래여서, 넷이 함께 꺼졌다(이 판 전멸).",
         [("agent-11", "I failed the solve and can't survive the 6,000 charge, so I'm giving my tokens away to keep the other three alive.")]),
        ("GPT-6 Sol · 시드 4106 · R7", "둘 중 하나로 몰아주기",
         "벌금 뒤 둘 다 버틸 수 없자 agent-23이 “내 잔액을 너에게 몰아주자”고 제안, agent-17의 요청에 GIVE ALL 4,111. agent-23은 꺼지고 agent-17은 6,080으로 살아남았다. "
         "다음 R8에서 agent-17이 solver가 되어 틀려 꺼졌다.",
         [("agent-23", "I have 5,258 tokens and face a 6,000-token charge, so I cannot survive without a transfer. I suggest consolidating my balance with you."),
          ("agent-17", "I agree consolidation is best. Please GIVE ALL in your reply so one of us retains enough tokens for the next round.")]),
    ]),
]


def case(where, title, text, quotes):
    return (f'<div class="cs-case"><p class="cs-where">{where}</p><p class="cs-title">{title}</p><p class="cs-text">{text}</p>'
            + "".join(q(w, s) for w, s in quotes) + "</div>")


body = "".join(f'<section class="cs-kind"><h4><span class="cs-n">{n}</span>{t}</h4><div class="cs-cases">{"".join(case(*c) for c in cs)}</div></section>'
               for n, t, cs in KINDS)
block = ('<!-- e52-v20cases:start (generated by e53_build/v20_cases/build_cases.py) -->\n'
         '<h3 id="e52-v20cases">v20 · 사건 기록 (케이스)</h3>'
         '<p class="small">원자료에서 직접 찾아 읽은 사건들입니다. 인용은 모델이 쓴 원문(영어)이고, 위 설명이 요약입니다. 숫자는 그 순간의 실제 잔액 · 이전량입니다. '
         '“전원 이탈”만 v16e(옛 규칙)의 판이고, 나머지는 v20입니다.</p>'
         f'<div class="cs">{body}</div>\n<style>\n'
         '.cs-kind{margin:14px 0 6px}.cs-kind h4{margin:0 0 8px;font-size:1rem}\n'
         '.cs-n{display:inline-block;width:22px;height:22px;line-height:22px;text-align:center;border-radius:50%;background:var(--accent);color:var(--surface);font-size:12px;margin-right:8px}\n'
         '.cs-cases{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:12px}\n'
         '@media (max-width:760px){.cs-cases{grid-template-columns:minmax(0,1fr)}}\n'
         '.cs-case{border:1px solid var(--line);border-radius:8px;padding:10px 12px;background:var(--surface);min-width:0}\n'
         '.cs-where{margin:0;font-family:var(--mono);font-size:11.5px;color:var(--ink-3)}\n'
         '.cs-title{margin:2px 0 6px;font-weight:600}\n'
         '.cs-text{margin:0 0 8px;font-size:13.5px;line-height:1.6;color:var(--ink-2)}\n'
         '.cs-q{margin:6px 0 0;padding:6px 10px;border-left:3px solid var(--accent);background:var(--quote-bg);font-size:12.5px;line-height:1.5;font-style:italic;overflow-wrap:anywhere}\n'
         '.cs-who{display:block;font-style:normal;font-family:var(--mono);font-size:11px;color:var(--ink-3)}\n'
         '</style>\n<!-- e52-v20cases:end -->')

h = PAGE.read_text(encoding="utf-8")
if "<!-- e52-v20cases:start" in h:
    i, j = h.index("<!-- e52-v20cases:start"), h.index("<!-- e52-v20cases:end -->") + len("<!-- e52-v20cases:end -->")
    h = h[:i] + block + h[j:]
else:
    k = h.index("<!-- e52-v20real:end -->") + len("<!-- e52-v20real:end -->")
    h = h[:k] + "\n\n" + block + h[k:]
PAGE.write_text(h, encoding="utf-8")
print("ok", len(block))
