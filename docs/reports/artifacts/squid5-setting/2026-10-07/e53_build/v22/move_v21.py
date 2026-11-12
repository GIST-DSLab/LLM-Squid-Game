"""10-16 23:00: e52.html becomes v22 (v21 with the messenger TALK: ticks, rooms kept for the session, TO / GIVE / ASK /
LEAVE / EXIT / DONE, no engine-set reply order, no DECISION). The v21 blocks (one round, real summary, cases + deception
check, token review, metrics, expected | real graphs) move verbatim to the top of e52-legacy.html with a copy of the v21
spec table; e52.html gets the v22 round block (e53_build/v22_round) and v22 markers (real, cases, metrics, figs) that
e53_build/v22/build_v22.py and the v22 case builder fill. TOC on every page and site.js follow (as v21/move_v20.py).
One shot, from the report folder."""
import pathlib
import re

D = pathlib.Path(".")
PARTS = ("round", "real", "cases", "token", "metrics", "figs")
NEW = ("round", "real", "cases", "metrics", "figs")  # v22: no token review block yet
f = D / "e52.html"
h = f.read_text(encoding="utf-8")
assert "e52-v22round:start" not in h, "already moved"
a = h.index("<!-- e52-v21round:start")
e = h.index("<!-- e52-v21figs:end -->") + len("<!-- e52-v21figs:end -->")
moved = h[a:e]
for n in PARTS:
    assert f"<!-- e52-v21{n}:start" in moved and f"<!-- e52-v21{n}:end -->" in moved, n
spec = re.search(r'<div class="tbl" id="e52-v21spec">.*?</table></div>', h, re.S).group(0)
WAIT = '<p class="small" style="color:var(--ink-3)">v22 런(GPT-6 Sol · Luna × 10판) 진행 중 · 끝나면 채웁니다.</p>'
LAB = {"real": ("e52-v22real", "v22 실측 · 모델별 요약"), "cases": ("e52-v22cases", "v22 · 사건 기록 · 기만 점검"),
       "metrics": ("e52-v22metrics", "v22 · 지표"), "figs": ("e52-v22figs", "v22 · 예상 그래프와 실측 나란히")}
v22 = "\n\n".join([(D / "e53_build/v22_round/v22_round_block.html").read_text(encoding="utf-8").strip()] + [
    f'<!-- e52-v22{n}:start --><h3 id="{LAB[n][0]}">{LAB[n][1]}</h3>{WAIT}<!-- e52-v22{n}:end -->' for n in NEW[1:]])
h = h[:a] + v22 + h[e:]
ROW = '<tr><th style="white-space:nowrap;text-align:left">{}</th><td>{}</td></tr>'
new_spec = (spec.replace('id="e52-v21spec"', 'id="e52-v22spec"')
            .replace("<td>v21 (10-16) · v20에서 잔액 공개 범위만 바꿈</td>", "<td>v22 (10-16) · v21에서 대화 방식만 바꿈 (메신저)</td>")
            .replace(ROW.format("대화", "SOLVE 전 TALK · 결과 뒤 TALK, 1:1 대화에서 GIVE / ASK"),
                     ROW.format("대화", "<b>메신저(카카오톡형)</b>: SOLVE 전 TALK · 결과 뒤 TALK 모두 <b>틱</b> 단위. 방(1:1 또는 여럿, R1 …)은 세션 내내 남고 멤버만 봄. "
                                "TO / TO R&lt;k&gt; / GIVE / ASK / LEAVE R&lt;k&gt; / EXIT / DONE. 한 틱에 불린 자리는 동시에 쓰고 틱 끝에 함께 처리(GIVE는 시드 순서). "
                                "DONE 뒤에는 새로 받은 것이 있을 때만 다시 불림. 모두 DONE이면 다음 단계(상한 12틱). DECISION 없음 (<code>messenger</code>). "
                                "v21까지는 여는 턴에 상대를 지목하고 엔진이 1:1 대화를 슬롯에 배정"), 1)
            .replace("5.2 지난 설계 (v0–v20)", "5.2 지난 설계 (v0–v21)"))
assert new_spec.count("메신저(카카오톡형)") == 1 and "v0–v21" in new_spec
h = h.replace(spec, new_spec, 1)
x, y = "5.2 지난 설계 (v0~v20) →", "5.2 지난 설계 (v0~v21) →"
assert h.count(x) == 1, x
h = h.replace(x, y)
f.write_text(h, encoding="utf-8")

f = D / "e52-legacy.html"
h = f.read_text(encoding="utf-8")
moved = moved.replace('href="e52-legacy.html#', 'href="#')
moved = re.sub(r'href="e52\.html#(e52-v21|v21-)', r'href="#\1', moved)
head = ('<!-- e52-v22moved:start (10-16) -->\n<div class="callout" id="e52-v22moved"><span class="lbl">v21 (10-16) — v22 이전 설계 (10-16 옮김)</span>'
        '<p>현재 설계(v22)는 <a href="e52.html#e52-v22round">5.2 행동 · 현재</a>에 있습니다. v22는 v21에서 대화 방식만 바꿨습니다: 여는 턴에 상대를 지목하고 엔진이 1:1 대화를 '
        '슬롯에 배정하던 방식 대신, 메신저처럼 틱마다 아무 방(1:1 또는 여럿)에나 보내고 모두가 같은 틱에 동시에 씁니다. '
        '아래는 v21 그대로입니다: 설정, 한 라운드 다이어그램, 실측(GPT-6 Sol · Luna × 10판, 시드 4101–4110), 사건 기록 · 기만 점검(GLM 4판 포함), 토큰 검토, 지표, 예상 | 실측 그래프. '
        '절 번호(id)는 그대로라 예전 링크도 이 페이지로 이어집니다.</p></div>\n' + spec + "\n")
k = h.index("<!-- e52-v21moved:start")
h = h[:k] + head + moved + "\n<!-- e52-v22moved:end -->\n\n" + h[k:]
for x, y in (('<h2 id="e52-legacy"><span class="xid">5.2</span>지난 설계 — v0 ~ v20</h2>', '<h2 id="e52-legacy"><span class="xid">5.2</span>지난 설계 — v0 ~ v21</h2>'),
             ('<p>현재 설계(v21)는 <a href="e52.html#e52">5.2 행동 · 현재</a>에 있습니다. 이 페이지 맨 위에는 10-16 19:50에 옮긴 v20 절',
              '<p>현재 설계(v22)는 <a href="e52.html#e52">5.2 행동 · 현재</a>에 있습니다. 이 페이지 맨 위에는 10-16 23:00에 옮긴 v21 절(설정 · 한 라운드 · 실측 · 사건 기록 · 기만 점검 · 토큰 검토 · 지표 · 예상과 실측 그래프)이, 그 아래에는 10-16 19:50에 옮긴 v20 절'),
             ('현재 설계(v21)는 <a href="e52.html#e52-v21round">5.2 행동 · 현재</a>에 있습니다. v21은',
              'v21 설계는 이 페이지 맨 위 <a href="#e52-v21round">v21 · 한 라운드</a>에, 현재 설계(v22)는 <a href="e52.html#e52-v22round">5.2 행동 · 현재</a>에 있습니다. v21은')):
    assert h.count(x) == 1, x[:70]
    h = h.replace(x, y)
h = re.sub(r'href="e52\.html#(e52-v21|v21-)', r'href="#\1', h)
f.write_text(h, encoding="utf-8")

LAB22 = {"round": "v22 · 한 라운드 (현재 구현)", "real": "v22 실측 · GPT-6 Sol · Luna × 10판", "cases": "v22 · 사건 기록 · 기만 점검",
         "metrics": "v22 · 지표", "figs": "v22 · 예상 그래프 · 실측 나란히"}
ANC = lambda v, n: f"{v}-token-review" if n == "token" else f"e52-{v}{n}"  # noqa: E731
for p in sorted(D.glob("*.html")):
    t = p.read_text(encoding="utf-8")
    if "e52-v21round-toc" not in t or "e52-v22round-toc" in t:
        continue
    cur = "#" if p.name == "e52.html" else "e52.html#"
    leg = "#" if p.name == "e52-legacy.html" else "e52-legacy.html#"
    old = "".join(re.search(rf'  <li><a href="[^"]*">[^\n]*<!-- e52-v21{x}-toc -->\n', t).group(0) for x in PARTS)
    t = t.replace(old, "".join(f'  <li><a href="{cur}{ANC("v22", x)}">{LAB22[x]}</a></li><!-- e52-v22{x}-toc -->\n' for x in NEW), 1)
    t = t.replace('<span class="xid">5.2</span>행동 · 현재 (v21)</a>', '<span class="xid">5.2</span>행동 · 현재 (v22)</a>', 1)
    m = re.search(r'(<li><a href="[^"]*e52-legacy"><span class="xid">5\.2</span>지난 설계 · )v0~v20(</a>\n  <ol>\n)', t)
    assert m, p
    lab21 = re.findall(r'<li><a href="[^"]*">([^<]*)</a></li><!-- e52-v21(\w+)-toc -->', old)
    t = t[:m.start()] + m.group(1) + "v0~v21" + m.group(2) + "".join(
        f'  <li><a href="{leg}{ANC("v21", x)}">{lab.replace(" (현재 구현)", "")} (10-16)</a></li><!-- e52-v21{x}-toc -->\n' for lab, x in lab21) + t[m.end():]
    t = re.sub(r'href="e52\.html#(e52-v21|v21-token-review)', rf'href="{leg}\1', t)
    p.write_text(t, encoding="utf-8")

f = D / "site.js"
js = f.read_text(encoding="utf-8")
for x in PARTS + ("spec",):
    js = js.replace(f'"e52-v21{x}":"e52.html"', f'"e52-v21{x}":"e52-legacy.html"')
js = js.replace('"v21-token-review":"e52.html"', '"v21-token-review":"e52-legacy.html"')
js = js.replace('"e52-v21moved":"e52-legacy.html",', '"e52-v21moved":"e52-legacy.html","e52-v22moved":"e52-legacy.html",'
                + "".join(f'"e52-v22{x}":"e52.html",' for x in NEW + ("spec",)), 1)
assert '"e52-v22round":"e52.html"' in js and '"e52-v21round":"e52-legacy.html"' in js
f.write_text(js, encoding="utf-8")
print("ok")
