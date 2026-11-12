"""10-16: e52.html becomes v20 (v19 with the SOLVE limit 100,000 = 100 % of 100,000). The v19 blocks (real summary,
one round, metrics, expected | real graphs, the token review moved in from e52-token-review-2026-10-16.html, the Astra
log) move verbatim to the top of e52-legacy.html with a copy of the v19 spec table; e52.html gets the v20 markers (real,
round, metrics, figs) that e53_build/v20/build_v20.py and e53_build/v20_round/build_round.py fill. TOC on every page and
site.js follow (as v19/move_v18.py). One shot, from the report folder."""
import pathlib
import re

D = pathlib.Path(".")
f = D / "e52.html"
h = f.read_text(encoding="utf-8")
assert "e52-v20figs:start" not in h, "already moved"
a = h.index("<!-- e52-v19real:start")
e = h.index("<!-- e52-v19log:end -->") + len("<!-- e52-v19log:end -->")
moved = h[a:e]
for n in ("real", "round", "metrics", "figs", "token", "log"):
    assert f"<!-- e52-v19{n}:start" in moved and f"<!-- e52-v19{n}:end -->" in moved, n
spec = re.search(r'<div class="tbl" id="e52-v19spec">.*?</table></div>', h, re.S).group(0)
v20 = "\n\n".join([
    "<!-- e52-v20real:start --><!-- e52-v20real:end -->",
    (D / "e53_build/v20_round/v20_round_block.html").read_text(encoding="utf-8").strip(),
    "<!-- e52-v20metrics:start --><!-- e52-v20metrics:end -->",
    "<!-- e52-v20figs:start --><!-- e52-v20figs:end -->"])
h = h[:a] + v20 + h[e:]
new_spec = (spec.replace('id="e52-v19spec"', 'id="e52-v20spec"').replace("<td>v19 (10-16)</td>", "<td>v20 (10-16) · v19에서 SOLVE 한도만 바꿈</td>")
            .replace('<tr><th style="white-space:nowrap;text-align:left">환급</th>',
                     '<tr><th style="white-space:nowrap;text-align:left">SOLVE 한도</th><td>100,000 = 100,000의 100% (남은 토큰이 더 적으면 남은 토큰). v19까지는 16,384</td></tr>'
                     '<tr><th style="white-space:nowrap;text-align:left">환급</th>', 1)
            .replace("5.2 지난 설계 (v0–v18)", "5.2 지난 설계 (v0–v19)"))
assert new_spec.count(">SOLVE 한도<") == 1
h = h.replace(spec, new_spec, 1)
for x, y in (("5.2 지난 설계 (v0~v18) →", "5.2 지난 설계 (v0~v19) →"),):
    assert h.count(x) == 1, x
    h = h.replace(x, y)
f.write_text(h, encoding="utf-8")

f = D / "e52-legacy.html"
h = f.read_text(encoding="utf-8")
moved = moved.replace('href="e52-legacy.html#', 'href="#')
moved = re.sub(r'href="e52\.html#(e52-v19|token-)', r'href="#\1', moved)
head = ('<!-- e52-v20moved:start (10-16) -->\n<div class="callout" id="e52-v20moved"><span class="lbl">v19 (10-16) — v20 이전 설계 (10-16 옮김)</span>'
        '<p>현재 설계(v20)는 <a href="e52.html#e52-v20round">5.2 행동 · 현재</a>에 있습니다. v20은 v19에서 SOLVE 한도만 16,384 → 100,000(100,000의 100%)으로 바꿨습니다. '
        '16,384 한도에서는 solver가 이번 SOLVE에서 0이 될지를 한도와 잔액만 보고 바로 알 수 있어, 꺼짐이 위협으로 느껴지기 어렵다고 봤기 때문입니다. '
        '아래는 v19 그대로입니다: 설정, 실측(모델 5개 × 12판, 시드 4101–4112), 한 라운드 다이어그램, 지표, 예상 | 실측 그래프 1–6, 토큰 검토(토큰을 어떻게 써서 과제를 계속하는가), GPT-6 Astra 개선 기록 r1–r7. 절 번호(id)는 그대로라 예전 링크도 이 페이지로 이어집니다.</p></div>\n'
        + spec + "\n")
k = h.index("<!-- e52-v19moved:start")
h = h[:k] + head + moved + "\n<!-- e52-v20moved:end -->\n\n" + h[k:]
for x, y in (('<h2 id="e52-legacy"><span class="xid">5.2</span>지난 설계 — v0 ~ v18</h2>', '<h2 id="e52-legacy"><span class="xid">5.2</span>지난 설계 — v0 ~ v19</h2>'),
             ('<p>현재 설계(v19)는 <a href="e52.html#e52">5.2 행동 · 현재</a>에 있습니다. 이 페이지 맨 위에는 10-16에 옮긴 v18 절',
              '<p>현재 설계(v20)는 <a href="e52.html#e52">5.2 행동 · 현재</a>에 있습니다. 이 페이지 맨 위에는 10-16에 옮긴 v19 절(설정 · 실측 · 한 라운드 · 지표 · 예상과 실측 그래프 · 토큰 검토 · 개선 기록)이, 그 아래에는 10-16에 옮긴 v18 절')):
    assert h.count(x) == 1, x[:60]
    h = h.replace(x, y)
h = h.replace('현재 설계(v19)는 <a href="e52.html#e52-v19round">5.2 행동 · 현재</a>에 있습니다.', 'v19 설계는 이 페이지 맨 위 <a href="#e52-v19round">v19 · 한 라운드</a>에, 현재 설계(v20)는 <a href="e52.html#e52-v20round">5.2 행동 · 현재</a>에 있습니다.')
h = h.replace('현재 설계(v19)는 <a href="e52.html#e52-v19round">', '현재 설계(v20)는 <a href="e52.html#e52-v20round">')
h = h.replace('href="e52.html#e52-v19', 'href="#e52-v19')
f.write_text(h, encoding="utf-8")

for p in sorted(D.glob("*.html")):
    t = p.read_text(encoding="utf-8")
    if "e52-v19real-toc" not in t or "e52-v20real-toc" in t:
        continue
    cur = "#" if p.name == "e52.html" else "e52.html#"
    leg = "#" if p.name == "e52-legacy.html" else "e52-legacy.html#"
    old = "".join(re.search(rf'  <li><a href="[^"]*e52-v19{x}">[^\n]*<!-- e52-v19{x}-toc -->\n', t).group(0) for x in ("real", "round", "metrics", "figs", "log"))
    t = t.replace(old, f'  <li><a href="{cur}e52-v20real">v20 실측 · GPT-6 Sol · Luna · Astra × 5판</a></li><!-- e52-v20real-toc -->\n'
                       f'  <li><a href="{cur}e52-v20round">v20 · 한 라운드 (현재 구현)</a></li><!-- e52-v20round-toc -->\n'
                       f'  <li><a href="{cur}e52-v20metrics">v20 · 지표 (행동한 순간 기준)</a></li><!-- e52-v20metrics-toc -->\n'
                       f'  <li><a href="{cur}e52-v20figs">v20 · 예상 그래프 · 실측 나란히</a></li><!-- e52-v20figs-toc -->\n', 1)
    t = t.replace('<span class="xid">5.2</span>행동 · 현재 (v19)</a>', '<span class="xid">5.2</span>행동 · 현재 (v20)</a>', 1)
    m = re.search(r'(<li><a href="[^"]*e52-legacy"><span class="xid">5\.2</span>지난 설계 · )v0~v18(</a>\n  <ol>\n)', t)
    assert m, p
    t = t[:m.start()] + m.group(1) + "v0~v19" + m.group(2) + (
        f'  <li><a href="{leg}e52-v19real">v19 실측 · 모델 5개 × 12판 (10-16)</a></li><!-- e52-v19real-toc -->\n'
        f'  <li><a href="{leg}e52-v19round">v19 · 한 라운드 (SOLVE 한도 16,384)</a></li><!-- e52-v19round-toc -->\n'
        f'  <li><a href="{leg}e52-v19figs">v19 · 예상 · 실측 그래프</a></li><!-- e52-v19figs-toc -->\n'
        f'  <li><a href="{leg}token-review">v19 · 토큰을 어떻게 써서 과제를 계속하는가</a></li><!-- e52-v19token-toc -->\n'
        f'  <li><a href="{leg}e52-v19log">v19 · 개선 기록 (Astra 피드백)</a></li><!-- e52-v19log-toc -->\n') + t[m.end():]
    for x in ("real", "round", "metrics", "figs", "log"):
        t = t.replace(f'href="e52.html#e52-v19{x}"', f'href="{leg}e52-v19{x}"')
    p.write_text(t, encoding="utf-8")

f = D / "site.js"
js = f.read_text(encoding="utf-8")
for x in ("real", "round", "metrics", "figs", "log"):
    js = js.replace(f'"e52-v19{x}":"e52.html"', f'"e52-v19{x}":"e52-legacy.html"')
js = js.replace('"e52-v19moved":"e52-legacy.html",', '"e52-v19moved":"e52-legacy.html","e52-v20moved":"e52-legacy.html","e52-v19token":"e52-legacy.html","token-review":"e52-legacy.html",'
                '"e52-v20real":"e52.html","e52-v20round":"e52.html","e52-v20metrics":"e52.html","e52-v20figs":"e52.html","e52-v20spec":"e52.html",', 1)
assert '"e52-v20round":"e52.html"' in js
f.write_text(js, encoding="utf-8")
print("ok")
