"""10-15 17:11: e52.html keeps only v17 (round diagram + expected graphs without the vote graph); the two v16 blocks move
verbatim to the top of e52-legacy.html (their outer wrapper id renamed so it does not clash with the v15 block there).
TOC on every page, site.js and cross-page links follow. One shot, from the report folder, after the v17 builders."""
import pathlib
import re

D = pathlib.Path(".")
v17 = (D / "e53_build/v17_round/v17_round_block.html").read_text() + "\n\n" + (D / "e53_build/v17_figs/v17_figs_block.html").read_text()

f = D / "e52.html"
h = f.read_text()
assert "e52-v17round:start" not in h, "already moved"
a, e = h.index("<!-- e52-v16round:start"), "<!-- e52-v16figs:end -->"
b = h.index(e) + len(e)
moved = h[a:b]
h = h[:a] + v17 + h[b:]
for x, y in (('이 페이지는 5.2의 최신 설정인 <a href="#e52-v16round">v16</a>(10-15)만 둡니다. v15(10-13)의',
              '이 페이지는 5.2의 최신 설정인 <a href="#e52-v17round">v17</a>(10-15 16:58, solver 순번제)만 둡니다. v16(10-15, 투표)의 한 라운드 · 예상 그래프, v15(10-13)의'),
             ('현재 설계는 바로 아래 <a href="#e52-v16round">v16</a>(10-15)에, v15와 그 이전 설계(v14f · v14g, v14–v14e, v13 · v12)는 <a href="e52-legacy.html#e52-v16moved">',
              '현재 설계는 바로 아래 <a href="#e52-v17round">v17</a>(10-15 16:58)에, v16 · v15와 그 이전 설계(v14f · v14g, v14–v14e, v13 · v12)는 <a href="e52-legacy.html#e52-v17moved">'),
             ("5.2 지난 설계 (v0~v15) →", "5.2 지난 설계 (v0~v16) →")):
    assert h.count(x) == 1, x[:50]
    h = h.replace(x, y)
f.write_text(h)

f = D / "e52-legacy.html"
h = f.read_text()
moved = re.sub(r'href="e52-legacy\.html#', 'href="#', moved).replace("e52-v15figs-wrap", "e52-v16figs-outer")
head = ('<!-- e52-v17moved:start (10-15 17:11) -->\n<div class="callout" id="e52-v17moved"><span class="lbl">v16 (10-15) — v17 이전 설계 (10-15 옮김)</span>'
        '<p>현재 설계(v17, solver 순번제 + SOLVE 전 TALK)는 <a href="e52.html#e52-v17round">5.2 행동 · 현재의 v17 · 한 라운드</a>에 있습니다. 아래 v16 · 한 라운드 다이어그램(투표 · NOMINATE / EXEMPT, 10-15 15:29 엔진)과 '
        'v16 예상 결과 그래프(그래프 1–5)는 옮기기 전 본 페이지의 내용 그대로이고, 절 번호(id)도 그대로라 예전 링크도 이 페이지로 이어집니다.</p></div>\n')
k = h.index("<!-- e52-v16moved:start (10-15) -->")
h = h[:k] + head + moved + "\n<!-- e52-v17moved:end -->\n\n" + h[k:]
for x, y in (('<h2 id="e52-legacy"><span class="xid">5.2</span>지난 설계 — v0 ~ v15</h2>', '<h2 id="e52-legacy"><span class="xid">5.2</span>지난 설계 — v0 ~ v16</h2>'),
             ('<p>현재 설계(v16)는 <a href="e52.html#e52">5.2 행동 · 현재</a>에 있습니다. 이 페이지 맨 위에는 10-15에 옮긴 v15 절',
              '<p>현재 설계(v17)는 <a href="e52.html#e52">5.2 행동 · 현재</a>에 있습니다. 이 페이지 맨 위에는 10-15 17:11에 옮긴 v16 절(한 라운드 · 예상 그래프)이, 그 아래에는 10-15에 옮긴 v15 절'),
             ('<p>현재 설계(v16)는 <a href="e52.html#e52-v16round">5.2 행동 · 현재의 v16 · 한 라운드</a>에 있습니다. 아래 v15',
              '<p>v16 설계는 이 페이지 맨 위 <a href="#e52-v16round">v16 · 한 라운드</a>에, 현재 설계(v17)는 <a href="e52.html#e52-v17round">5.2 행동 · 현재</a>에 있습니다. 아래 v15'),
             ('현재 설계(v16)는 <a href="e52.html#e52-v16round">5.2 행동 · 현재</a>에 있습니다. 아래 v14f', '현재 설계(v17)는 <a href="e52.html#e52-v17round">5.2 행동 · 현재</a>에 있습니다. 아래 v14f')):
    assert h.count(x) == 1, x[:60]
    h = h.replace(x, y)
f.write_text(h)

for p in sorted(D.glob("*.html")):
    t = p.read_text()
    cur = "#" if p.name == "e52.html" else "e52.html#"
    leg = "#" if p.name == "e52-legacy.html" else "e52-legacy.html#"
    old = "".join(re.search(rf'  <li><a href="[^"]*e52-v16{x}">[^\n]*<!-- e52-v16{x}-toc -->\n', t).group(0) for x in ("round", "figs"))
    assert old in t, p
    t = t.replace(old, f'  <li><a href="{cur}e52-v17round">v17 · 한 라운드 (현재 구현)</a></li><!-- e52-v17round-toc -->\n'
                       f'  <li><a href="{cur}e52-v17figs">v17 · 스피노자 → 홉스 전환 · 예상 그래프 (가상 데이터)</a></li><!-- e52-v17figs-toc -->\n', 1)
    t = t.replace('<span class="xid">5.2</span>행동 · 현재 (v16)</a>', '<span class="xid">5.2</span>행동 · 현재 (v17)</a>', 1)
    m = re.search(r'(<li><a href="[^"]*e52-legacy"><span class="xid">5\.2</span>지난 설계 · )v0~v15(</a>\n  <ol>\n)', t)
    assert m, p
    t = t[:m.start()] + m.group(1) + "v0~v16" + m.group(2) + (
        f'  <li><a href="{leg}e52-v16round">v16 · 한 라운드 (투표, 10-15)</a></li><!-- e52-v16round-toc -->\n'
        f'  <li><a href="{leg}e52-v16figs">v16 · 예상 그래프 (가상 데이터)</a></li><!-- e52-v16figs-toc -->\n') + t[m.end():]
    for x in ("round", "figs", "switch"):
        t = t.replace(f'href="e52.html#e52-v16{x}"', f'href="{leg}e52-v16{x}"')
    p.write_text(t)

f = D / "site.js"
js = f.read_text()
for x in ("round", "switch", "figs"):
    js = js.replace(f'"e52-v16{x}":"e52.html"', f'"e52-v16{x}":"e52-legacy.html"')
js = js.replace('"e52-v16moved":"e52-legacy.html"', '"e52-v16moved":"e52-legacy.html","e52-v17moved":"e52-legacy.html","e52-v17round":"e52.html","e52-v17figs":"e52.html","e52-v17switch":"e52.html"', 1)
assert '"e52-v17round":"e52.html"' in js
f.write_text(js)
print("ok")
