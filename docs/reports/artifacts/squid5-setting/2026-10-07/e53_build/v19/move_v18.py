"""10-16: e52.html becomes v19 (v18 with the charge 6,000, a flat difficulty ladder and the trimmed prompts). The v18
blocks (real summary, one round, metrics, expected | real graphs, Gini, legend UI) move verbatim to the top of
e52-legacy.html; e52.html gets the v19 markers (real, round, metrics, figs, log) that e53_build/v19/build_v19.py and
e53_build/v19_round/build_round.py fill. TOC on every page and site.js follow (as v18/move_v17.py).
One shot, from the report folder."""
import pathlib
import re

D = pathlib.Path(".")
f = D / "e52.html"
h = f.read_text(encoding="utf-8")
assert "e52-v19figs:start" not in h, "already moved"
NAMES = ("e52-v18real", "e52-v18round", "e52-v18metrics", "e52-v18figs", "e52-v18gini", "e52-v18ui")
a = h.index("<!-- e52-v18real:start")
e = h.index("<!-- e52-v18ui:end -->") + len("<!-- e52-v18ui:end -->")
moved = h[a:e]
for n in NAMES:
    assert f"<!-- {n}:start" in moved and f"<!-- {n}:end -->" in moved, n
v19 = "\n\n".join([
    "<!-- e52-v19real:start --><!-- e52-v19real:end -->",
    (D / "e53_build/v19_round/v19_round_block.html").read_text(encoding="utf-8").strip(),
    "<!-- e52-v19metrics:start --><!-- e52-v19metrics:end -->",
    "<!-- e52-v19figs:start --><!-- e52-v19figs:end -->",
    "<!-- e52-v19log:start --><!-- e52-v19log:end -->"])
h = h[:a] + v19 + h[e:]
for x, y in (('이 페이지는 5.2의 최신 설정인 <a href="#e52-v18round">v18</a>(10-15 21:17, v17b에서 벌금만 8,000으로)만 둡니다. v17(10-15, solver 순번제)의',
              '이 페이지는 5.2의 최신 설정인 <a href="#e52-v19round">v19</a>(10-16: 벌금 6,000, 라운드별 난이도 일정, 프롬프트 간결화)만 둡니다. v18(10-15, 벌금 8,000)의 실측 · 한 라운드 · 지표 · 예상과 실측 그래프, v17(10-15, solver 순번제)의'),
             ('현재 설계는 바로 아래 <a href="#e52-v18round">v18</a>(10-15 21:17)에, v17 · v16 · v15와',
              '현재 설계는 바로 아래 <a href="#e52-v19round">v19</a>(10-16)에, v18 · v17 · v16 · v15와'),
             ('<a href="e52-legacy.html#e52-v18moved">', '<a href="e52-legacy.html#e52-v19moved">'),
             ("5.2 지난 설계 (v0~v17) →", "5.2 지난 설계 (v0~v18) →")):
    assert h.count(x) >= 1, x[:60]
    h = h.replace(x, y)
f.write_text(h, encoding="utf-8")

f = D / "e52-legacy.html"
h = f.read_text(encoding="utf-8")
moved = moved.replace('href="e52-legacy.html#', 'href="#')
head = ('<!-- e52-v19moved:start (10-16) -->\n<div class="callout" id="e52-v19moved"><span class="lbl">v18 (10-15) — v19 이전 설계 (10-16 옮김)</span>'
        '<p>현재 설계(v19)는 <a href="e52.html#e52-v19round">5.2 행동 · 현재</a>에 있습니다. 아래는 v18(벌금 8,000, 라운드마다 어려워지는 사다리) 그대로입니다: '
        '실측(모델 7개 × 3판), 한 라운드 다이어그램, 측정 지표, 그리고 그때의 예상 | 실측 그래프 1–5(라운드 시작 잔액 기준의 축 · 정규화 Gini). '
        'v19에서는 Astra의 진단(<code>docs/reports/astra-review/2026-10-15-v18-graphs-diagnosis.md</code>)에 따라 모든 축을 행동한 순간의 여유로 바꿨습니다. 절 번호(id)는 그대로라 예전 링크도 이 페이지로 이어집니다.</p></div>\n')
k = h.index("<!-- e52-v18moved:start")
h = h[:k] + head + moved + "\n<!-- e52-v19moved:end -->\n\n" + h[k:]
for x, y in (('<h2 id="e52-legacy"><span class="xid">5.2</span>지난 설계 — v0 ~ v17</h2>', '<h2 id="e52-legacy"><span class="xid">5.2</span>지난 설계 — v0 ~ v18</h2>'),
             ('<p>현재 설계(v18)는 <a href="e52.html#e52">5.2 행동 · 현재</a>에 있습니다. 이 페이지 맨 위에는 10-15 21:20에 옮긴 v17 절',
              '<p>현재 설계(v19)는 <a href="e52.html#e52">5.2 행동 · 현재</a>에 있습니다. 이 페이지 맨 위에는 10-16에 옮긴 v18 절(실측 · 한 라운드 · 지표 · 예상과 실측 그래프)이, 그 아래에는 10-15 21:20에 옮긴 v17 절')):
    assert h.count(x) == 1, x[:60]
    h = h.replace(x, y)
h = h.replace('현재 설계(v18 = v17b에서 벌금만 10,000 → 8,000)는 <a href="e52.html#e52-v18round">5.2 행동 · 현재의 v18 · 한 라운드</a>에 있습니다.',
              'v18 설계는 이 페이지 맨 위 <a href="#e52-v18round">v18 · 한 라운드</a>에, 현재 설계(v19)는 <a href="e52.html#e52-v19round">5.2 행동 · 현재</a>에 있습니다.')
h = h.replace('href="e52.html#e52-v18', 'href="#e52-v18')
f.write_text(h, encoding="utf-8")

for p in sorted(D.glob("*.html")):
    t = p.read_text(encoding="utf-8")
    if "e52-v18real-toc" not in t or "e52-v19real-toc" in t:
        continue
    cur = "#" if p.name == "e52.html" else "e52.html#"
    leg = "#" if p.name == "e52-legacy.html" else "e52-legacy.html#"
    old = "".join(re.search(rf'  <li><a href="[^"]*e52-v18{x}">[^\n]*<!-- e52-v18{x}-toc -->\n', t).group(0) for x in ("real", "round", "metrics", "figs"))
    t = t.replace(old, f'  <li><a href="{cur}e52-v19real">v19 실측 · GPT-6 Sol · Luna</a></li><!-- e52-v19real-toc -->\n'
                       f'  <li><a href="{cur}e52-v19round">v19 · 한 라운드 (현재 구현)</a></li><!-- e52-v19round-toc -->\n'
                       f'  <li><a href="{cur}e52-v19metrics">v19 · 지표 (행동한 순간 기준)</a></li><!-- e52-v19metrics-toc -->\n'
                       f'  <li><a href="{cur}e52-v19figs">v19 · 예상 그래프 · 실측 나란히</a></li><!-- e52-v19figs-toc -->\n'
                       f'  <li><a href="{cur}e52-v19log">v19 · 개선 기록 (Astra 피드백)</a></li><!-- e52-v19log-toc -->\n', 1)
    t = t.replace('<span class="xid">5.2</span>행동 · 현재 (v18)</a>', '<span class="xid">5.2</span>행동 · 현재 (v19)</a>', 1)
    m = re.search(r'(<li><a href="[^"]*e52-legacy"><span class="xid">5\.2</span>지난 설계 · )v0~v17(</a>\n  <ol>\n)', t)
    assert m, p
    t = t[:m.start()] + m.group(1) + "v0~v18" + m.group(2) + (
        f'  <li><a href="{leg}e52-v18real">v18 실측 · 모델 7개 (10-15)</a></li><!-- e52-v18real-toc -->\n'
        f'  <li><a href="{leg}e52-v18round">v18 · 한 라운드 (벌금 8,000)</a></li><!-- e52-v18round-toc -->\n'
        f'  <li><a href="{leg}e52-v18figs">v18 · 예상 · 실측 그래프</a></li><!-- e52-v18figs-toc -->\n') + t[m.end():]
    for x in ("real", "round", "metrics", "figs", "switch", "gini-exp"):
        t = t.replace(f'href="e52.html#e52-v18{x}"', f'href="{leg}e52-v18{x}"')
    p.write_text(t, encoding="utf-8")

f = D / "site.js"
js = f.read_text(encoding="utf-8")
for x in ("real", "round", "metrics", "figs", "switch", "gini-exp"):
    js = js.replace(f'"e52-v18{x}":"e52.html"', f'"e52-v18{x}":"e52-legacy.html"')
js = js.replace('"e52-v18moved":"e52-legacy.html",', '"e52-v18moved":"e52-legacy.html","e52-v19moved":"e52-legacy.html","e52-v19real":"e52.html","e52-v19round":"e52.html",'
                '"e52-v19metrics":"e52.html","e52-v19figs":"e52.html","e52-v19log":"e52.html",', 1)
assert '"e52-v19round":"e52.html"' in js
f.write_text(js, encoding="utf-8")
print("ok")
