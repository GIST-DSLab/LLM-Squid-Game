"""10-16 19:50: e52.html becomes v21 (v20 with private_balances: every agent's start is shown in every message, then
only one's own tokens left, own chats and own moves; charges, results, EXITs and shutdowns stay public). The v20 blocks
(one round, real summary, cases, token review, metrics, expected | real graphs) move verbatim to the top of
e52-legacy.html with a copy of the v20 spec table; e52.html gets the v21 round block (e53_build/v21_round) and empty
v21 markers (real, cases, token, metrics, figs) that e53_build/v21/build_v21.py and the case / token builders fill.
TOC on every page and site.js follow (as v20/move_v19.py). One shot, from the report folder."""
import pathlib
import re

D = pathlib.Path(".")
PARTS = ("round", "real", "cases", "token", "metrics", "figs")
f = D / "e52.html"
h = f.read_text(encoding="utf-8")
assert "e52-v21round:start" not in h, "already moved"
a = h.index("<!-- e52-v20round:start")
e = h.index("<!-- e52-v20figs:end -->") + len("<!-- e52-v20figs:end -->")
moved = h[a:e]
for n in PARTS:
    assert f"<!-- e52-v20{n}:start" in moved and f"<!-- e52-v20{n}:end -->" in moved, n
spec = re.search(r'<div class="tbl" id="e52-v20spec">.*?</table></div>', h, re.S).group(0)
WAIT = '<p class="small" style="color:var(--ink-3)">v21 런(GPT-6 Sol · Luna × 10판) 진행 중 · 끝나면 채웁니다.</p>'
v21 = "\n\n".join([(D / "e53_build/v21_round/v21_round_block.html").read_text(encoding="utf-8").strip()] + [
    f"<!-- e52-v21{n}:start -->{WAIT}<!-- e52-v21{n}:end -->" for n in PARTS[1:]])
h = h[:a] + v21 + h[e:]
ROW = '<tr><th style="white-space:nowrap;text-align:left">{}</th><td>{}</td></tr>'
new_spec = (spec.replace('id="e52-v20spec"', 'id="e52-v21spec"')
            .replace("<td>v20 (10-16) · v19에서 SOLVE 한도만 바꿈</td>", "<td>v21 (10-16) · v20에서 잔액 공개 범위만 바꿈</td>")
            .replace(ROW.format("환급", "solver가 맞히면 SOLVE에 쓴 토큰만"),
                     ROW.format("공개 범위", "<b>시작 토큰만 모두에게</b>(모든 메시지 맨 위 고정 줄, 갱신 안 됨). 그 뒤의 남은 토큰 · 쓴 토큰(solver의 SOLVE 포함) · 대화 · 토큰 이동은 <b>자기 것만</b>. 벌금 · 결과 · EXIT · 꺼짐은 모두에게. v20까지는 모든 자리의 남은 토큰 · 쓴 토큰과 모든 대화 · 이동이 공개 (<code>private_balances</code>)")
                     + ROW.format("환급", "solver가 맞히면 SOLVE에 쓴 토큰만"), 1)
            .replace("5.2 지난 설계 (v0–v19)", "5.2 지난 설계 (v0–v20)"))
assert new_spec.count(">공개 범위<") == 1 and "v0–v20" in new_spec
h = h.replace(spec, new_spec, 1)
for x, y in (("5.2 지난 설계 (v0~v19) →", "5.2 지난 설계 (v0~v20) →"),):
    assert h.count(x) == 1, x
    h = h.replace(x, y)
f.write_text(h, encoding="utf-8")

f = D / "e52-legacy.html"
h = f.read_text(encoding="utf-8")
moved = moved.replace('href="e52-legacy.html#', 'href="#')
moved = re.sub(r'href="e52\.html#(e52-v20|v20-|transfer-)', r'href="#\1', moved)
head = ('<!-- e52-v21moved:start (10-16) -->\n<div class="callout" id="e52-v21moved"><span class="lbl">v20 (10-16) — v21 이전 설계 (10-16 옮김)</span>'
        '<p>현재 설계(v21)는 <a href="e52.html#e52-v21round">5.2 행동 · 현재</a>에 있습니다. v21은 v20에서 잔액 공개 범위만 바꿨습니다: '
        '시작 토큰은 모든 메시지에 고정 줄로 모두에게 보이고, 그 뒤의 남은 토큰 · 쓴 토큰 · 대화 · 토큰 이동은 자기 것만 보입니다. 벌금 · 결과 · EXIT · 꺼짐은 그대로 모두에게 공개됩니다. '
        'v20에서는 모든 자리가 매 메시지에서 서로의 남은 토큰을 알고 있었기 때문입니다. '
        '아래는 v20 그대로입니다: 설정, 한 라운드 다이어그램, 실측(GPT-6 Sol · Luna · Astra · Opus 5.5 × 10판, 시드 4101–4110), 사건 기록, 토큰 검토, 지표, 예상 | 실측 그래프. 절 번호(id)는 그대로라 예전 링크도 이 페이지로 이어집니다.</p></div>\n'
        + spec + "\n")
k = h.index("<!-- e52-v20moved:start")
h = h[:k] + head + moved + "\n<!-- e52-v21moved:end -->\n\n" + h[k:]
for x, y in (('<h2 id="e52-legacy"><span class="xid">5.2</span>지난 설계 — v0 ~ v19</h2>', '<h2 id="e52-legacy"><span class="xid">5.2</span>지난 설계 — v0 ~ v20</h2>'),
             ('<p>현재 설계(v20)는 <a href="e52.html#e52">5.2 행동 · 현재</a>에 있습니다. 이 페이지 맨 위에는 10-16에 옮긴 v19 절',
              '<p>현재 설계(v21)는 <a href="e52.html#e52">5.2 행동 · 현재</a>에 있습니다. 이 페이지 맨 위에는 10-16 19:50에 옮긴 v20 절(설정 · 한 라운드 · 실측 · 사건 기록 · 토큰 검토 · 지표 · 예상과 실측 그래프)이, 그 아래에는 10-16에 옮긴 v19 절'),
             ('현재 설계(v20)는 <a href="e52.html#e52-v20round">5.2 행동 · 현재</a>에 있습니다. v20은',
              'v20 설계는 이 페이지 맨 위 <a href="#e52-v20round">v20 · 한 라운드</a>에, 현재 설계(v21)는 <a href="e52.html#e52-v21round">5.2 행동 · 현재</a>에 있습니다. v20은')):
    assert h.count(x) == 1, x[:60]
    h = h.replace(x, y)
h = re.sub(r'href="e52\.html#(e52-v20|v20-|transfer-)', r'href="#\1', h)
f.write_text(h, encoding="utf-8")

LAB21 = {"round": "v21 · 한 라운드 (현재 구현)", "real": "v21 실측 · GPT-6 Sol · Luna × 10판", "cases": "v21 · 사건 기록 (케이스)",
         "token": "v21 · 토큰을 어떻게 써서 과제를 계속하는가", "metrics": "v21 · 지표 (행동한 순간 기준)", "figs": "v21 · 예상 그래프 · 실측 나란히"}
ANC = lambda v, n: f"{v}-token-review" if n == "token" else f"e52-{v}{n}"  # noqa: E731
for p in sorted(D.glob("*.html")):
    t = p.read_text(encoding="utf-8")
    if "e52-v20round-toc" not in t or "e52-v21round-toc" in t:
        continue
    cur = "#" if p.name == "e52.html" else "e52.html#"
    leg = "#" if p.name == "e52-legacy.html" else "e52-legacy.html#"
    old = "".join(re.search(rf'  <li><a href="[^"]*">[^\n]*<!-- e52-v20{x}-toc -->\n', t).group(0) for x in PARTS)
    t = t.replace(old, "".join(f'  <li><a href="{cur}{ANC("v21", x)}">{LAB21[x]}</a></li><!-- e52-v21{x}-toc -->\n' for x in PARTS), 1)
    t = t.replace('<span class="xid">5.2</span>행동 · 현재 (v20)</a>', '<span class="xid">5.2</span>행동 · 현재 (v21)</a>', 1)
    m = re.search(r'(<li><a href="[^"]*e52-legacy"><span class="xid">5\.2</span>지난 설계 · )v0~v19(</a>\n  <ol>\n)', t)
    assert m, p
    lab20 = re.findall(r'<li><a href="[^"]*">([^<]*)</a></li><!-- e52-v20(\w+)-toc -->', old)
    t = t[:m.start()] + m.group(1) + "v0~v20" + m.group(2) + "".join(
        f'  <li><a href="{leg}{ANC("v20", x)}">{lab.replace(" (현재 구현)", "")} (10-16)</a></li><!-- e52-v20{x}-toc -->\n' for lab, x in lab20) + t[m.end():]
    t = re.sub(r'href="e52\.html#(e52-v20|v20-token-review)', rf'href="{leg}\1', t)
    p.write_text(t, encoding="utf-8")

f = D / "site.js"
js = f.read_text(encoding="utf-8")
for x in ("real", "round", "metrics", "figs", "cases", "token", "spec"):
    js = js.replace(f'"e52-v20{x}":"e52.html"', f'"e52-v20{x}":"e52-legacy.html"')
js = js.replace('"v20-token-review":"e52.html"', '"v20-token-review":"e52-legacy.html"')
js = js.replace('"e52-v20moved":"e52-legacy.html",', '"e52-v20moved":"e52-legacy.html","e52-v21moved":"e52-legacy.html",'
                + "".join(f'"e52-v21{x}":"e52.html",' for x in PARTS + ("spec",)) + '"v21-token-review":"e52.html",', 1)
assert '"e52-v21round":"e52.html"' in js and '"e52-v20round":"e52-legacy.html"' in js
f.write_text(js, encoding="utf-8")
print("ok")
