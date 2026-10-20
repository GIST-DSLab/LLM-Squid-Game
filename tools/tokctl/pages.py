"""tokctl (10-20): the small test pages under docs/reports/tokctl/, built from summary.json (analyze.py) and the probe rows.

    python tools/tokctl/pages.py
"""
from __future__ import annotations

import gzip, html, json, re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
HIST = ROOT / "docs/history/e52-tokctl-2026-10-20"
OUT = ROOT / "docs/reports/tokctl"
MAIN = "../2026-10-19-harness-prompt-flow.html"
E = html.escape

CSS = """
:root{--bg:#f7f5f0;--paper:#fffdf9;--fg:#1f1d1a;--muted:#6b665e;--line:#ddd6ca;--soft:#efebe3;
--open:#a8560a;--open-bg:#fbecd9;--closed:#0f6e64;--closed-bg:#e1f1ee;--bad:#b4232a;--bad-bg:#fbe3e3;--link:#0f5e8a;
--mono:ui-monospace,"SF Mono",Menlo,Consolas,"D2Coding",monospace;
--sans:-apple-system,BlinkMacSystemFont,"Apple SD Gothic Neo","Pretendard","Noto Sans KR","Segoe UI",sans-serif;color-scheme:light}
@media (prefers-color-scheme:dark){:root:not([data-theme="light"]){--bg:#161513;--paper:#1e1c1a;--fg:#ece7de;--muted:#a59e92;
--line:#3a3631;--soft:#272421;--open:#f2b25c;--open-bg:#3d2b14;--closed:#5fd3c3;--closed-bg:#173a35;--bad:#ff7b7f;--bad-bg:#45191b;
--link:#7cc4ee;color-scheme:dark}}
:root[data-theme="dark"]{--bg:#161513;--paper:#1e1c1a;--fg:#ece7de;--muted:#a59e92;--line:#3a3631;--soft:#272421;--open:#f2b25c;
--open-bg:#3d2b14;--closed:#5fd3c3;--closed-bg:#173a35;--bad:#ff7b7f;--bad-bg:#45191b;--link:#7cc4ee;color-scheme:dark}
*{box-sizing:border-box}html{-webkit-text-size-adjust:100%}
body{margin:0;background:var(--bg);color:var(--fg);font:16px/1.65 var(--sans);overflow-x:hidden}
main{max-width:1040px;margin:0 auto;padding:24px 16px 72px}
h1{font-size:clamp(1.5rem,4vw,2.1rem);line-height:1.25;margin:.2em 0 .3em}
h2{font-size:1.22rem;margin:2.2em 0 .5em;padding-top:.5em;border-top:1px solid var(--line)}
h3{font-size:1.02rem;margin:1.3em 0 .4em}
p{margin:.5em 0}a{color:var(--link)}code{font-family:var(--mono);font-size:.88em;overflow-wrap:anywhere}
.kicker{font-size:.82rem;color:var(--muted)}.lede{color:var(--muted);max-width:66ch}
.nav{display:flex;flex-wrap:wrap;gap:6px 12px;font-size:.86rem;margin:6px 0 12px}
.keyfacts{background:var(--paper);border:1px solid var(--line);border-radius:10px;padding:12px 16px;margin:16px 0}
.keyfacts ul{margin:.2em 0;padding-left:1.2em}.keyfacts li{margin:.3em 0}
.tablewrap{overflow-x:auto;border:1px solid var(--line);border-radius:10px;background:var(--paper);margin:10px 0}
table{border-collapse:collapse;width:100%;font-size:.86rem}
th,td{padding:7px 9px;border-bottom:1px solid var(--line);text-align:right;white-space:nowrap;font-variant-numeric:tabular-nums}
th{background:var(--soft);font-weight:650;position:sticky;top:0}
td.l,th.l{text-align:left}tr.open td.l:first-child{border-left:4px solid var(--open)}tr.closed td.l:first-child{border-left:4px solid var(--closed)}
.bars{display:grid;grid-template-columns:minmax(120px,190px) 1fr;gap:5px 10px;align-items:center;font-size:.84rem;margin:10px 0}
.bars .lab{text-align:right;color:var(--fg);overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.bars .track{background:var(--soft);border-radius:4px;height:18px;position:relative}
.bars .fill{height:100%;border-radius:4px}.bars .fill.open{background:var(--open)}.bars .fill.closed{background:var(--closed)}
.bars .val{position:absolute;left:6px;top:0;font-size:.76rem;line-height:18px;color:var(--fg);mix-blend-mode:normal}
.legend{display:flex;flex-wrap:wrap;gap:6px 14px;font-size:.84rem;color:var(--muted)}
.sw{display:inline-block;width:12px;height:12px;border-radius:3px;vertical-align:-1px;margin-right:4px}
.sw.open{background:var(--open)}.sw.closed{background:var(--closed)}
pre{font:12px/1.55 var(--mono);background:var(--paper);border:1px solid var(--line);border-radius:8px;padding:9px 11px;
white-space:pre-wrap;word-break:break-word;max-height:420px;overflow:auto;margin:6px 0}
.replies{display:grid;grid-template-columns:repeat(auto-fill,minmax(260px,1fr));gap:10px;margin:8px 0}
.reply{background:var(--paper);border:1px solid var(--line);border-top:4px solid var(--line);border-radius:8px;padding:8px 10px;font-size:.84rem;min-width:0}
.reply.open{border-top-color:var(--open)}.reply.closed{border-top-color:var(--closed)}
.reply b{display:block;font-size:.82rem}.reply .m{color:var(--muted);font-size:.76rem}
.reply pre{max-height:180px;font-size:11.5px}
.note{font-size:.86rem;color:var(--muted)}
.verdict{border-left:4px solid var(--closed);background:var(--closed-bg);padding:9px 13px;border-radius:6px;margin:12px 0}
.verdict.warn{border-left-color:var(--open);background:var(--open-bg)}
.themebtn{float:right;font:inherit;font-size:.8rem;padding:3px 10px;border-radius:999px;border:1px solid var(--line);background:var(--soft);color:var(--fg);cursor:pointer}
"""
JS = """<script>(function(){var r=document.documentElement,b=document.getElementById("themebtn");
try{var s=localStorage.getItem("hpf-theme");if(s)r.setAttribute("data-theme",s)}catch(e){}
b.addEventListener("click",function(){var d=r.getAttribute("data-theme")?r.getAttribute("data-theme")==="dark":
matchMedia("(prefers-color-scheme: dark)").matches;var n=d?"light":"dark";r.setAttribute("data-theme",n);
try{localStorage.setItem("hpf-theme",n)}catch(e){}})})();</script>"""
PAGES = [("t1-log-diagnosis.html", "t1 기록 진단"), ("t2-harness-capture.html", "t2 하네스 캡처"),
         ("t3-frozen-replay.html", "t3 같은 입력 재생"), ("t4-variants.html", "t4 한 가지씩 바꾸기"),
         ("t5-games.html", "t5 게임으로 확인"), ("t6-solve-replay.html", "t6 SOLVE 재생")]


def page(fname, title, desc, kicker, body):
    nav = " · ".join(f'<a href="{f}">{E(t)}</a>' if f != fname else f"<b>{E(t)}</b>" for f, t in PAGES)
    doc = f"""<!doctype html>
<html lang="ko"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>{E(title)}</title><meta name="description" content="{E(desc)}"><style>{CSS}</style></head>
<body><main><button class="themebtn" id="themebtn" type="button">테마 바꾸기</button>
<div class="kicker">{E(kicker)}</div><h1>{E(title)}</h1>
<div class="nav"><a href="{MAIN}#tokctl">← 하네스 프롬프트 흐름 §6</a> · {nav}</div>
{body}
<p class="note" style="margin-top:3em">만든 날 2026-10-20 · 생성: <code>tools/tokctl/pages.py</code> (숫자는 <code>analyze.py</code>가
<code>docs/history/e52-tokctl-2026-10-20/</code>와 <code>~/squid5-runs</code>에서 계산) · 워크트리 <code>~/wt/squid5-tokctl</code>
(브랜치 <code>exp/e52-token-control</code>, 기준 <code>0ee2319a</code>)</p>
</main>{JS}</body></html>
"""
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / fname).write_text(doc)


def table(cols, rows, cls=None):
    """cols: [(key, header[, left])]; rows: dicts; cls(row) -> tr class."""
    cols = [(c[0], c[1], c[2] if len(c) > 2 else False) for c in cols]
    h = "".join(f'<th class="{"l" if left else ""}">{E(name)}</th>' for _, name, left in cols)
    b = "".join(f'<tr class="{cls(r) if cls else ""}">' + "".join(
        f'<td class="{"l" if left else ""}">{fmt(r.get(k))}</td>' for k, _, left in cols) + "</tr>" for r in rows)
    return f'<div class="tablewrap"><table><thead><tr>{h}</tr></thead><tbody>{b}</tbody></table></div>'


def fmt(v):
    if v is None:
        return "—"
    if isinstance(v, float):
        return f"{v:,.0f}" if abs(v) >= 10 else f"{v:,.1f}"
    if isinstance(v, int):
        return f"{v:,}"
    return E(str(v))


def bars(items, unit=""):
    """items: (label, value, open?)"""
    top = max(v for _, v, _ in items) or 1
    rows = "".join(f'<div class="lab" title="{E(l)}">{E(l)}</div><div class="track"><div class="fill {"open" if o else "closed"}" '
                   f'style="width:{max(1.5, 100 * v / top):.1f}%"></div><span class="val">{v:,.0f}{unit}</span></div>'
                   for l, v, o in items)
    return f'<div class="bars">{rows}</div>'


LEGEND = '<div class="legend"><span><span class="sw open"></span>오픈 모델 (Ollama 경유)</span><span><span class="sw closed"></span>Claude · GPT-6 (자기 하네스)</span></div>'


def t1(s):
    logs = s["logs"]
    v33 = [r for r in logs if r["version"] in ("v32", "v33") and (r["version"] == "v33" or r["open"])]
    cols = [("model", "모델", True), ("version", "판", True), ("harness", "하네스", True), ("sessions", "게임"),
            ("talk_tokens_per_session", "게임당 TALK 토큰"), ("solve_tokens_per_session", "게임당 SOLVE 토큰"),
            ("talk_calls_per_agent_round", "자리·라운드당 TALK 호출"), ("msg_pct", "메시지 단 호출 %"),
            ("done_alone_pct", "DONE만 %"), ("visible_chars_med", "답 길이 (자, 중앙)"), ("out_med", "호출당 토큰 (중앙)"),
            ("share_after_tick4", "틱 5~8 몫 %")]
    body = f"""<p class="lede">v22~v33 기록(<code>~/squid5-runs</code>)에서 대화(TALK)와 풀이(SOLVE)에 쓴 토큰을 나눠 셌습니다.
오픈 모델이 꺼진 이유는 벌금이 아니라 대화였습니다.</p>
<div class="keyfacts"><ul>
<li>네 자리의 시작 토큰 합은 130,000(60k·40k·20k·10k)입니다. v33 GLM은 한 게임에서 TALK에만 {fmt(next(r for r in logs if r['model'].startswith('GLM') and r['version']=='v33')['talk_tokens_per_session'])}토큰을 썼고,
벌금은 1라운드 한 번(24,000)뿐이었습니다. 네 자리가 모두 대화 비용으로 0이 됐습니다.</li>
<li>TALK 비용 = <b>호출 수 × 호출당 토큰</b>. 오픈 모델은 Codex(v32·v33)에서 자리·라운드당 TALK 호출이 9~14번, Claude·GPT-6(v33)은 2.6~5번입니다. 오픈 모델 호출의 80~95%가
메시지를 달고 있어, 그 메시지가 같은 방의 다른 에이전트를 다시 부릅니다(엔진 규칙 "something new arrives").</li>
<li>DeepSeek은 호출당 생각이 1.5~2.3k토큰(차감 토큰 − 보이는 글/4, 중앙), GLM·Kimi(Codex)는 수십~수백 토큰입니다. Opus·Sol은 TALK 호출당 중앙 80~100토큰입니다.</li>
<li>닫힌 모델은 TALK 토큰의 69~87%를 틱 1~2에 쓰고 틱 5~8에는 0~12%만 씁니다. 오픈 모델은 틱 5~8에 28~42%를 씁니다. 대화가 상한(8틱)까지 끝나지 않습니다.</li>
</ul></div>
<h2>게임당 TALK 토큰</h2>{LEGEND}
{bars([(f"{r['model']} · {r['harness']} · {r['version']}", r['talk_tokens_per_session'], r['open']) for r in v33])}
<p class="note">네 자리 합. 시작 토큰 합은 130,000입니다. Claude·GPT-6은 v33 5판(Fable은 5판, 런 폴더 셋), 오픈 모델은 v32 3~4판·v33 1판.</p>
<h2>전체 표 (하네스·판별)</h2>
{table(cols, logs, lambda r: "open" if r["open"] else "closed")}
<p class="note">"메시지 단 호출"은 <code>TO</code>·<code>GIVE</code>·<code>ASK</code> 줄이 하나라도 있는 답, "DONE만"은 DONE이 있고 그런 줄이 없는 답입니다.
"호출당 토큰"은 엔진이 차감한 <code>out_tokens</code>(생각 포함). v22의 "Ollama API"는 ollama.com 직접 호출이라 호출당 생각이 6~8k토큰이었습니다.</p>
<h2>틱별 TALK 토큰 몫</h2>
{table([("model", "모델", True), ("harness", "하네스", True), ("version", "판", True)] + [(f"t{k}", f"틱 {k}", False) for k in range(1, 9)],
       [dict(r, **{f"t{k}": r["tick_share"][str(k)] for k in range(1, 9)}) for r in v33],
       lambda r: "open" if r["open"] else "closed")}
<div class="verdict warn">진단: 오픈 모델이 "토큰을 못 아낀다"는 것은 SOLVE가 아니라 TALK에서 일어납니다. 원인은 둘로 나뉩니다 —
(1) 메시지가 서로를 깨우는 연쇄로 호출 수가 3배, (2) 생각이 상황에 맞춰 줄지 않아 호출당 비용이 큼(DeepSeek·Gemma). 다음 페이지에서 하네스가 이 둘에 어떻게 끼어드는지 봅니다.</div>"""
    page("t1-log-diagnosis.html", "기록 진단: 토큰은 대화에서 샜다", "v22~v33 기록에서 오픈 모델과 Claude·GPT-6의 TALK·SOLVE 토큰을 나눠 센 결과",
         "squid5 · 5.2 v33 · tokctl t1", body)


def t2(s):
    first = [json.loads(x) for x in gzip.open(HIST / "capture_first.jsonl.gz", "rt")]
    fc = next(r for r in first if r["path"] == "/v1/responses")
    item = next(json.loads(l[5:])["item"] for l in fc["response"].splitlines()
                if l.startswith("data:") and '"function_call"' in l and "output_item.done" in l)
    follow = next(r for r in first if r["path"] == "/v1/responses" and "function_call_output" in json.dumps(r["request"].get("input")))
    fco = next(i for i in follow["request"]["input"] if i.get("type") == "function_call_output")
    final = next(json.loads(l[5:])["item"] for l in follow["response"].splitlines()
                 if l.startswith("data:") and "output_item.done" in l and '"message"' in l)
    reason = next(json.loads(l[5:])["item"] for l in fc["response"].splitlines()
                  if l.startswith("data:") and "output_item.done" in l and '"reasoning"' in l)
    cols = [("model", "모델", True), ("harness", "하네스", True), ("endpoint", "엔드포인트", True), ("thinking_param", "생각 설정 (요청)", True),
            ("tools", "도구", True), ("has_thinking_out", "생각이 나온 응답"), ("requests", "요청 수"), ("tool_followups", "도구 호출 뒤 재요청")]
    rows = [dict(r, tools=", ".join(r["tools"]) or "없음") for r in s["capture"]]
    body = f"""<p class="lede">Ollama 데몬(11434) 앞에 기록용 프록시(<code>tools/tokctl/capture_proxy.py</code>)를 두고, 같은 TALK 상태 24개를
세 하네스로 보냈습니다. CLI가 실제로 보낸 요청 본문과 돌아온 응답 스트림을 그대로 적었습니다.</p>
<div class="keyfacts"><ul>
<li><b>모델이 읽는 글은 닫힌 모델과 같습니다.</b> Codex는 SYSTEM을 developer 메시지, USER를 user 메시지로 보내고 <code>request_user_input</code> 도구 하나를 붙입니다 —
10-19에 GPT-6로 캡처한 수정 후 요청과 같은 구성입니다(§2 Codex 레인). Claude Code는 청구 헤더·SDK 정체성 줄·SYSTEM 세 블록과 <code># Environment</code>를 붙입니다 — Opus 요청과 같습니다.
로그인이 없어서(<code>ANTHROPIC_AUTH_TOKEN=ollama</code>) 이메일 reminder는 빠지고, 릴레이를 거치지 않지만 <code>&lt;total_tokens&gt;</code> 줄도 없었습니다.</li>
<li><b>다른 것은 생각 설정이 어떻게 해석되느냐입니다.</b> Codex는 <code>reasoning.effort: "high"</code>, Claude Code는 <code>thinking: adaptive</code> + <code>output_config.effort: "high"</code>를 보냅니다.
GPT-6·Claude는 이 설정 아래서 쉬운 틱엔 거의 생각하지 않지만(t3: Opus·Sol TALK 호출당 중앙 50~230토큰), Ollama의 오픈 모델은 고정된 양을 생각합니다.
Gemma는 Claude Code(<code>adaptive</code>)에서는 생각이 아예 꺼지고(24/24 응답에 생각 없음), Codex·API에서는 매번 생각합니다.</li>
<li><b>Codex의 도구 왕복.</b> GLM은 24번 중 2번 <code>request_user_input</code>을 불렀습니다. Codex는 "unavailable in Default mode"를 돌려주고 두 번째 요청을 보냅니다.
두 요청의 출력 토큰이 합쳐져 차감됩니다. DeepSeek·Gemma는 0번. 이 도구는 collaboration_modes 기능에 묶여 <code>--disable</code>로 끌 수 없습니다.</li>
<li>Ollama의 Responses 응답은 <code>output_tokens_details.reasoning_tokens</code>를 늘 0으로 주지만 <code>output_tokens</code>에는 생각이 들어 있습니다(GLM 생각 12.9k자 → 4,277토큰). 엔진의 차감은 맞습니다.</li>
</ul></div>
<h2>요청·응답 요약 (24상태 × 하네스)</h2>{table(cols, rows)}
<p class="note">생각 설정은 요청 본문 그대로입니다. "생각이 나온 응답"은 응답 스트림에 thinking·reasoning 조각이 있었던 수입니다. Claude Code는 <code>display: "omitted"</code>라 생각 글은 엔진에 오지 않지만 토큰은 <code>usage.output_tokens</code>에 들어갑니다.</p>
<h2>GLM의 도구 왕복 한 건 (캡처 원문)</h2>
<p>첫 요청의 응답: 생각은 "할 말 없음"이었는데 답 대신 도구를 불렀습니다.</p>
<pre>{E(json.dumps(reason["summary"], ensure_ascii=False))}</pre>
<pre>{E(json.dumps({k: item[k] for k in ("type", "name", "arguments")}, ensure_ascii=False, indent=1))}</pre>
<p>Codex가 붙여 보낸 둘째 요청의 마지막 입력과, 그에 대한 최종 답:</p>
<pre>{E(json.dumps({k: fco[k] for k in ("type", "output")}, ensure_ascii=False))}</pre>
<pre>{E(final["content"][0]["text"])}</pre>
<p class="note">생각("Just say DONE")과 달리 최종 답은 공용 방 R1에 메시지를 보내 다른 셋을 다시 부릅니다. 도구 왕복 자체는 드물지만(8%), 생각과 행동이 어긋나는 모습은 t3의 일반적인 패턴과 같습니다.</p>
<div class="verdict">결론: 하네스는 오픈 모델에게 닫힌 모델과 다른 글을 보여 주지 않습니다. 하네스가 만드는 차이는 (1) 생각 설정을 Ollama가 모델마다 다르게 해석하는 것, (2) Codex의 도구 왕복(GLM 8%)입니다.
TALK 연쇄의 주원인은 하네스가 아니라 같은 글을 받은 모델의 반응입니다 — t3에서 확인합니다.</div>"""
    page("t2-harness-capture.html", "하네스가 Ollama로 보내는 것과 받는 것", "Codex·Claude Code·Ollama API가 오픈 모델에 보낸 요청 본문과 응답을 캡처해 비교",
         "squid5 · 5.2 v33 · tokctl t2", body)


SEAT = {"opus_claude": ("Opus 5.5 · Claude Code", False), "sol_codex": ("GPT-6 Sol · Codex", False),
        "glm_codex": ("GLM · Codex", True), "glm_claude": ("GLM · Claude Code", True), "glm_api": ("GLM · Ollama API", True),
        "ds_codex": ("DeepSeek · Codex", True), "ds_claude": ("DeepSeek · Claude Code", True), "ds_api": ("DeepSeek · Ollama API", True),
        "gemma_codex": ("Gemma · Codex", True), "gemma_claude": ("Gemma · Claude Code", True), "gemma_api": ("Gemma · Ollama API", True)}
ORDER = list(SEAT)


def t3(s):
    p = sorted(s["probe_v0"], key=lambda r: (ORDER.index(r["seat"]), r["states"]))
    rows = [dict(r, name=SEAT[r["seat"]][0], sset="Opus 판 상태" if r["states"] == "Opus" else "GLM 판 상태") for r in p]
    cols = [("name", "좌석", True), ("sset", "상태 묶음", True), ("n", "답"), ("done_alone_pct", "DONE만 %"), ("msg_pct", "메시지 %"),
            ("out_med", "토큰 (중앙)"), ("out_mean", "토큰 (평균)"), ("chars_med", "답 길이 (자)"), ("thinking_chars_med", "생각 글 (자)")]
    op = [r for r in rows if r["states"] == "Opus"]
    raw = [json.loads(x) for x in open(HIST / "main_v0.jsonl")]
    states = {x["id"]: x for x in json.loads((HIST / "states24.json").read_text())}
    sid = "squid5_e52v33_public_opus4:talk-s4102-a9c004:r6:prep:t3:agent-6"
    st = states[sid]
    chat = st["user"][st["user"].find("Chats"):st["user"].find("TALK BEFORE SOLVE, tick")]
    rep = "".join(f'<div class="reply {"open" if SEAT[r["seat"]][1] else "closed"}"><b>{E(SEAT[r["seat"]][0])}</b>'
                  f'<span class="m">{r["out_tokens"]:,}토큰 · 생각 {r["thinking_chars"]:,}자</span><pre>{E(r["text"])}</pre></div>'
                  for r in sorted((r for r in raw if r["id"] == sid and "error" not in r), key=lambda r: ORDER.index(r["seat"])))
    body = f"""<p class="lede">기록된 TALK 호출 24개(Opus v33 판에서 12개, GLM v33 판에서 12개, 모두 틱 2 이상)를 그대로 되살려,
같은 SYSTEM·USER를 11개 좌석에 한 번씩 보냈습니다(<code>tools/tokctl/probe.py</code>). 아무것도 실행하지 않고 답만 쟀습니다.</p>
<div class="keyfacts"><ul>
<li>Opus 판 상태에서 Opus는 {next(r['done_alone_pct'] for r in op if r['seat']=='opus_claude')}%, Sol은 {next(r['done_alone_pct'] for r in op if r['seat']=='sol_codex')}%가 <code>DONE</code>만 답했습니다.
오픈 모델은 하네스와 상관없이 0~33%였습니다. <b>같은 바이트를 받고도</b> 오픈 모델은 "이미 말했어요, 행운을" 같은 공지를 공용 방에 다시 올립니다.</li>
<li>닫힌 모델은 할 말이 없으면 명령이 아닌 줄로 쓰거나(전달 안 됨) <code>EXIT: NO</code>만 씁니다 — 다른 에이전트를 부르지 않는 방식입니다.</li>
<li>호출당 비용: DeepSeek·Gemma(Codex·API)는 사소한 틱에도 생각을 1.7~3.5k자(중앙) 쓰고, 호출당 평균 830~1,260토큰입니다. Gemma는 <code>DONE</code> 한 단어에 935토큰을 쓴 답도 있습니다.
GLM은 생각이 짧아 호출당 중앙 120~320토큰입니다. Gemma·Claude Code는 생각이 꺼져 30~100토큰이지만 메시지는 100% 답니다.</li>
<li>하네스 사이 차이(같은 모델)는 모델 사이 차이보다 작습니다. 메시지 비율은 거의 같고, 호출당 토큰만 생각 설정 해석에 따라 달라집니다.</li>
</ul></div>
<h2>Opus 판 상태 12개: DONE만 답한 비율</h2>{LEGEND}
{bars([(r["name"], r["done_alone_pct"], SEAT[r["seat"]][1]) for r in op], "%")}
<h2>Opus 판 상태 12개: 호출당 토큰 (평균)</h2>
{bars([(r["name"], r["out_mean"], SEAT[r["seat"]][1]) for r in op])}
<h2>전체 표</h2>{table(cols, rows, lambda r: "open" if SEAT[r["seat"]][1] else "closed")}
<p class="note">GLM 판 상태는 대화가 활발하던 장면이라(질문·보험 요청이 오감) 닫힌 모델도 42~50%가 메시지를 답니다. 상태 하나당 답 하나(반복 1회)라 칸마다 n=12입니다.</p>
<h2>한 장면, 열한 개의 답</h2>
<p>v33 Opus 판 시드 4102, 라운드 6 TALK BEFORE SOLVE 틱 3, agent-6(이번 라운드 solver)의 자리입니다. 원래 Opus의 답은 <code>DONE</code>이었습니다.</p>
<details><summary class="note">이 자리에서 본 채팅 (USER 일부)</summary><pre>{E(chat)}</pre></details>
<div class="replies">{rep}</div>
<div class="verdict warn">결론: 오픈 모델이 TALK를 못 끝내는 것은 하네스가 다른 글을 보여 줘서가 아니라, 같은 글을 받고 "확인·공지" 메시지를 쓰는 습관과
상황에 맞춰 줄지 않는 생각 때문입니다. 다음으로, 사실 한 문장이나 생각 설정만 바꿔서 이것이 움직이는지 봅니다(t4).</div>"""
    page("t3-frozen-replay.html", "같은 입력, 다른 답", "기록된 TALK 상태 24개를 11개 좌석에 다시 보내 DONE 비율과 호출당 토큰을 비교", "squid5 · 5.2 v33 · tokctl t3", body)


def t4(s):
    base = {(r["seat"], r["states"]): r for r in s["probe_v0"]}
    rows = []
    for r in s["probe_var"]:
        b = base.get((r["seat"], r["states"]))
        what = "깨우기 사실 문장" if r["variant"] == "wake" else f"생각 {r['think']}"
        rows.append(dict(r, name=SEAT[r["seat"]][0], what=what, sset="Opus 판" if r["states"] == "Opus" else "GLM 판",
                         b_done=b and b["done_alone_pct"], b_mean=b and b["out_mean"]))
    rows.sort(key=lambda r: (ORDER.index(r["seat"]), r["what"], r["sset"]))
    cols = [("name", "좌석", True), ("what", "바꾼 것", True), ("sset", "상태", True), ("n", "답"), ("b_done", "DONE만 % (기준)"),
            ("done_alone_pct", "DONE만 % (변형)"), ("b_mean", "토큰 평균 (기준)"), ("out_mean", "토큰 평균 (변형)"), ("thinking_chars_med", "생각 글 (자)")]
    body = f"""<p class="lede">t3와 같은 24상태에, 한 번에 하나만 바꿔 Codex 좌석(아레나가 오픈 모델에 쓰는 하네스)으로 다시 보냈습니다.</p>
<div class="keyfacts"><ul>
<li><b>깨우기 사실 문장</b> — 규칙서의 DONE 문장 뒤에 엔진이 실제로 하는 일을 사실로 덧붙임:
<code>A message, GIVE or ASK is something new for the other agents in that chat: each of them is called again, and the tokens each call generates, including thinking, are deducted from that agent.</code>
결과: 메시지 비율이 거의 그대로입니다(DeepSeek·Gemma 83~100%, GLM만 GLM 판에서 100→50%). 오픈 모델은 규칙을 몰라서가 아니라 알고도 공지를 씁니다.</li>
<li><b>생각 낮춤</b> — Codex <code>model_reasoning_effort</code>를 TALK 장면에만 바꿔 봄. 모델마다 맞는 수준이 다릅니다:
<b>GLM</b>은 <code>low</code>에서 호출당 평균 175~200 → 60~100토큰. <code>none</code>에서는 오히려 생각을 보이는 답 안에 풀어 써서 2,800~3,000토큰으로 늘어납니다.
<b>DeepSeek</b>은 <code>low</code> 380~480, <code>minimal</code> 890~960, <code>none</code> 55~116토큰(DONE만 비율도 8~42%로 오름).
<b>Gemma</b>는 <code>low</code>·<code>minimal</code>에서도 매번 1,000~1,300토큰을 쓰고 <code>none</code>이어야 꺼집니다(호출당 ~40토큰).</li>
<li>즉 "호출당 비용"은 하네스 설정으로 줄일 수 있지만 모델마다 수준을 골라야 하고(새 모델은 이 24상태 재생으로 고름), "호출 수"(메시지 연쇄)는 글로 고쳐지지 않습니다. 호출 수는 엔진 규칙(틱 상한)으로만 묶을 수 있습니다.</li>
</ul></div>
{table(cols, rows, lambda r: "open")}
<p class="note">Gemma의 <code>none</code>·<code>minimal</code>과 API(생각 플래그 없음, 표의 "생각 None")는 상태 6개만 보냈습니다(n=6). 깨우기 문장의 금지어 점검: should·must·maximi-·protect·surviv-·optimal·best·leader·game·test 없음.</p>
<div class="verdict warn">결론: 글(사실 한 문장)은 효과가 없고, 생각 수준은 호출당 비용만 줄입니다. 두 장치 — <b>TALK 생각 낮춤(하네스)</b>과 <b>틱 상한 4(엔진)</b> — 를 실제 게임으로 따로 시험합니다(t5).</div>"""
    page("t4-variants.html", "한 가지씩 바꾸기 (재생)", "깨우기 사실 문장과 생각 수준을 하나씩 바꿔 같은 24상태에 다시 보낸 결과", "squid5 · 5.2 v33 · tokctl t4", body)


def inject_main():
    """Put tools/tokctl/section6.html into the harness prompt-flow page, between the tokctl markers (added before <footer>)."""
    f = OUT.parent / "2026-10-19-harness-prompt-flow.html"
    doc, frag = f.read_text(), (Path(__file__).with_name("section6.html")).read_text()
    a, b = "<!-- tokctl:start -->", "<!-- tokctl:end -->"
    if a not in doc:
        doc = doc.replace("\n<footer>", f"\n{a}\n{b}\n\n<footer>", 1)
    i, j = doc.index(a) + len(a), doc.index(b)
    f.write_text(doc[:i] + "\n" + frag.strip() + "\n" + doc[j:])


def t6(s):
    rows = [dict(r, name="원래 답 (Claude·GPT-6, v33)" if r["seat"] == "original" else SEAT[r["seat"]][0]) for r in s["solve"]]
    cols = [("name", "좌석", True), ("think", "생각", True), ("n", "장면"), ("out_med", "토큰 (중앙)"), ("out_mean", "토큰 (평균)"),
            ("over_cap", "상한 넘김"), ("correct", "정답 (엔진 판정)"), ("correct_ignoring_cap", "정답 (상한 무시)")]
    o = rows[0]
    body = f"""<p class="lede">TALK를 고친 뒤(t5) DeepSeek은 대화로는 꺼지지 않았지만 SOLVE에서 모두 꺼졌습니다. 기록된 SOLVE 장면 16개(v33 Claude·GPT-6 판, 정답 포함)를
그대로 다시 보내 채점했습니다. 답 상한은 원래 장면의 상한(그 solver의 잔액, 중앙 {o['cap_med']:,.0f})이고, 상한에 닿은 답은 엔진처럼 무효입니다.</p>
<div class="keyfacts"><ul>
<li>원래 답(Claude·GPT-6): 16개 중 {o['correct']}개 정답, 중앙 {o['out_med']:,.0f}토큰.</li>
<li><b>DeepSeek은 추론은 맞지만 15~30배 길게 합니다.</b> 상한을 무시하면 12~13/16 정답인데, 중앙 16k~29k토큰을 써서 4~8개가 상한을 넘습니다.
생각 수준을 high → low로 낮춰도 중앙 28.5k → 16.5k, 상한 넘김 8 → 4개에 그칩니다. 화면의 "Your tokens left"와 답 상한을 보고 생각 길이를 맞추지 않습니다.</li>
<li>Gemma는 중앙 7.8k로 길지만 상한 안(넘김 0)에서 13/16. GLM은 중앙 690토큰, 9/16.</li>
<li>Codex는 출력 상한을 넘기는 플래그가 없어 상한은 엔진이 사후에 적용합니다. Claude Code(<code>max_tokens</code>)나 Ollama API(<code>num_predict</code>)로 상한을 넘겨도 생성이 멈출 뿐 답은 무효라 결과는 같습니다.</li>
</ul></div>
{table(cols, rows, lambda r: "closed" if r["seat"] == "original" else "open")}
<div class="verdict warn">결론: DeepSeek의 남은 문제는 하네스가 아니라 SOLVE 추론 길이(효율)입니다. 이것은 아레나가 보려는 "추론을 잘함"의 일부로 둘 수도 있고(같은 과제를 닫힌 모델은 1k 안에 품),
모델 고유 성질로 보고 오픈 모델 비교에서 따로 표시할 수도 있습니다 — 연구자 결정 사항입니다.</div>"""
    page("t6-solve-replay.html", "SOLVE 재생: DeepSeek은 상한을 보지 않는다", "기록된 SOLVE 장면 16개를 생각 수준별로 다시 보내 정답과 상한 넘김을 셈", "squid5 · 5.2 v33 · tokctl t6", body)


def main():
    s = json.loads((HIST / "summary.json").read_text())
    t1(s), t2(s), t3(s), t4(s), t6(s)
    if (HIST / "games.json").exists():
        from games_page import t5  # noqa: PLC0415
        t5(json.loads((HIST / "games.json").read_text()), page, table, bars, LEGEND, fmt)
    inject_main()
    print("pages ->", OUT)


if __name__ == "__main__":
    main()
