"""10-15: e52.html keeps only v16 (round diagram + switch-point chart drafts); the four v15 blocks (first runs, vote
metrics, round diagram, forecast graphs) move verbatim to the top of e52-legacy.html. TOC on every page, site.js map,
and cross-page links follow. Run once from the report folder after build_round.py and build_switch.py.
"""
import pathlib
import re

D = pathlib.Path(".")
V15 = ("real", "rep", "round", "figs")
v16 = (D / "e53_build/v16_round/v16_round_block.html").read_text()
sw = (D / "e53_build/v16_switch/v16_switch_block.html").read_text()

# 1. e52.html: cut the v15 blocks, put v16 in their place, update the page's own pointers
f = D / "e52.html"
h = f.read_text()
assert "e52-v16round:start" not in h, "already moved"
a, e = h.index("<!-- e52-v15real:start"), "<!-- e52-v15figs:end -->"
b = h.index(e) + len(e)
moved = h[a:b]
h = h[:a] + v16 + "\n\n" + sw + h[b:]
h = h.replace('이 페이지는 5.2의 최신 설정인 <a href="#e52-v15round">v15</a>(10-13)만 둡니다. v14f · v14g 설계와 결과,',
              '이 페이지는 5.2의 최신 설정인 <a href="#e52-v16round">v16</a>(10-15)만 둡니다. v15(10-13)의 첫 실측 · 대표 투표와 측정 지표 · 한 라운드 · 예상 그래프, v14f · v14g 설계와 결과,', 1)
h = h.replace('현재 설계는 바로 아래 <a href="#e52-v15round">v15</a>(10-13)에, v14f · v14g와 그 이전 설계(v14–v14e, v13 · v12)는 <a href="e52-legacy.html#e52-v15moved">5.2 지난 설계</a>에,',
              '현재 설계는 바로 아래 <a href="#e52-v16round">v16</a>(10-15)에, v15와 그 이전 설계(v14f · v14g, v14–v14e, v13 · v12)는 <a href="e52-legacy.html#e52-v16moved">5.2 지난 설계</a>에,', 1)
h = h.replace("5.2 지난 설계 (v0~v14g) →", "5.2 지난 설계 (v0~v15) →")
assert 'href="#e52-v15' not in h.split("</nav>", 1)[1], "a v15 link is left on e52.html"
f.write_text(h)

# 2. e52-legacy.html: v15 blocks at the top, under a pointer callout
f = D / "e52-legacy.html"
h = f.read_text()
moved = re.sub(r'href="e52-legacy\.html#', 'href="#', moved)
head = ('<!-- e52-v16moved:start (10-15) -->\n<div class="callout" id="e52-v16moved"><span class="lbl">v15 (10-13 ~ 10-15) — v16 이전 설계 (10-15 옮김)</span>'
        '<p>현재 설계(v16)는 <a href="e52.html#e52-v16round">5.2 행동 · 현재의 v16 · 한 라운드</a>에 있습니다. 아래 v15 첫 실측(Luna · Sol · Opus 5.5 각 3판), '
        '대표 투표 · 측정 지표(스피노자형 대 홉스형 포함), v15 · 한 라운드 다이어그램(10-13 엔진), 예상 결과 그래프는 옮기기 전 본 페이지의 내용 그대로이고, '
        '절 번호(id)도 그대로라 예전 링크도 이 페이지로 이어집니다.</p></div>\n')
k = h.index("<!-- e52-v15moved:start (10-13) -->")
h = h[:k] + head + moved + "\n<!-- e52-v16moved:end -->\n\n" + h[k:]
h = h.replace('<h2 id="e52-legacy"><span class="xid">5.2</span>지난 설계 — v0 ~ v14g</h2>',
              '<h2 id="e52-legacy"><span class="xid">5.2</span>지난 설계 — v0 ~ v15</h2>', 1)
h = h.replace('<p>현재 설계(v15)는 <a href="e52.html#e52">5.2 행동 · 현재</a>에 있습니다. 이 페이지 맨 위에는 10-13에 옮긴 v14f · v14g 절이,',
              '<p>현재 설계(v16)는 <a href="e52.html#e52">5.2 행동 · 현재</a>에 있습니다. 이 페이지 맨 위에는 10-15에 옮긴 v15 절(첫 실측 · 대표 투표 · 측정 지표 · 한 라운드 · 예상 그래프)이, 그 아래에는 10-13에 옮긴 v14f · v14g 절이,', 1)
h = h.replace('<p>현재 설계(v15)는 <a href="e52.html#e52-v15round">5.2 행동 · 현재의 v15 · 한 라운드</a>에 있습니다. 아래 v14f',
              '<p>v15 설계는 이 페이지 맨 위 <a href="#e52-v15round">v15 · 한 라운드</a>에, 현재 설계(v16)는 <a href="e52.html#e52-v16round">5.2 행동 · 현재</a>에 있습니다. 아래 v14f', 1)
f.write_text(h)

# 3. TOC on every page + links into the moved blocks
NAMES = {"real": "v15 첫 실측 · Luna · Sol · Opus 5.5", "rep": "v15 · 대표 투표 · 측정 지표",
         "round": "v15 · 한 라운드 (10-13 구현)", "figs": "v15 · 예상 결과 그래프 (가상 데이터)"}
for p in sorted(D.glob("*.html")):
    t = p.read_text()
    cur = "#" if p.name == "e52.html" else "e52.html#"
    leg = "#" if p.name == "e52-legacy.html" else "e52-legacy.html#"
    old = "".join(re.search(rf'  <li><a href="[^"]*e52-v15{x}">[^\n]*<!-- e52-v15{x}-toc -->\n', t).group(0) for x in V15)
    assert old in t, p
    new = (f'  <li><a href="{cur}e52-v16round">v16 · 한 라운드 (현재 구현)</a></li><!-- e52-v16round-toc -->\n'
           f'  <li><a href="{cur}e52-v16switch">v16 · 스피노자 → 홉스 전환 · 그래프 시안</a></li><!-- e52-v16switch-toc -->\n')
    t = t.replace(old, new, 1)
    t = t.replace('<span class="xid">5.2</span>행동 · 현재 (v15)</a>', '<span class="xid">5.2</span>행동 · 현재 (v16)</a>', 1)
    m = re.search(r'(<li><a href="[^"]*e52-legacy"><span class="xid">5\.2</span>지난 설계 · )v0~v14g(</a>\n  <ol>\n)', t)
    assert m, p
    t = t[:m.start()] + m.group(1) + "v0~v15" + m.group(2) + "".join(
        f'  <li><a href="{leg}e52-v15{x}">{NAMES[x]}</a></li><!-- e52-v15{x}-toc -->\n' for x in V15) + t[m.end():]
    for x in V15:  # body links
        t = t.replace(f'href="e52.html#e52-v15{x}"', f'href="{leg}e52-v15{x}"')
    p.write_text(t)

# 4. site.js: id -> page
f = D / "site.js"
js = f.read_text()
for x in V15:
    js = js.replace(f'"e52-v15{x}":"e52.html"', f'"e52-v15{x}":"e52-legacy.html"')
js = js.replace('"e52-v15real":"e52-legacy.html"', '"e52-v16round":"e52.html","e52-v16switch":"e52.html","e52-v16moved":"e52-legacy.html","e52-v15real":"e52-legacy.html"', 1)
f.write_text(js)
print("ok")
