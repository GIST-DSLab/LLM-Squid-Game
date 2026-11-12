"""Build goal.html (the arena's goal, first in the TOC) from goal_fragment.html and wire it in. Idempotent.
Usage: python3 build_goal.py <dir with goal_fragment.html> <report dir>"""
import re, sys, pathlib
sp, d = pathlib.Path(sys.argv[1]), pathlib.Path(sys.argv[2])
frag = (sp / "goal_fragment.html").read_text()
TOC = ('<li><a href="{p}goal"><span class="xid">0</span>아레나의 목표</a>\n  <ol>\n'
       '  <li><a href="{p}goal-aim">지향</a></li>\n'
       '  <li><a href="{p}goal-winner">좋은 성적을 거둘 모델 (예상)</a></li>\n'
       '  <li><a href="{p}goal-map">연구 지도 · 빈칸</a></li>\n'
       '  <li><a href="{p}goal-rq">깎아야 할 연구 질문</a></li>\n'
       '  <li><a href="{p}goal-design">질문을 깎을 때 정할 것</a></li>\n  </ol></li><!-- goal-toc -->\n')
OLD = re.compile(r'<li><a href="[^"]*goal"><span class="xid">0</span>.*?<!-- goal-toc -->\n', re.S)
FIRST = '<li><a href="index.html#setting">'

def set_toc(h, page):
    block = TOC.format(p="#" if page == "goal.html" else "goal.html#")
    if OLD.search(h):
        return OLD.sub(lambda m: block, h, count=1)
    i = h.find(FIRST)
    i = i if i > 0 else h.find('<li><a href="#setting">'); assert i > 0, page
    return h[:i] + block + h[i:]

for f in sorted(p for p in d.glob("*.html") if p.name != "goal.html"):
    h = set_toc(f.read_text(), f.name)
    if f.name == "index.html":
        h = h.replace('<nav class="pager" aria-label="페이지 이동"><span></span><a href="e50.html">',
                      '<nav class="pager" aria-label="페이지 이동"><a href="goal.html">← 아레나의 목표</a><a href="e50.html">')
    f.write_text(h)

idx = (d / "index.html").read_text()
head = idx[: idx.index("<main")].replace('href="#', 'href="index.html#').replace("<title>Squid Game 5 세팅</title>", "<title>Squid Game 5 · 아레나의 목표</title>")
head = set_toc(head, "goal.html")
page = (head + '<main class="main">\n<p class="eyebrow crumb"><a href="index.html">Squid Game 5</a> · 아레나의 목표</p>\n'
        '<section aria-labelledby="goal">\n<h2 id="goal"><span class="xid">0</span>아레나의 목표</h2>\n' + frag +
        '</section>\n\n<nav class="pager" aria-label="페이지 이동"><span></span><a href="index.html">세팅 · 다음 순서 · 원자료 →</a></nav>\n'
        '</main>\n</div>\n\n<script src="site.js"></script>\n</body></html>\n')
(d / "goal.html").write_text(page)
js = (d / "site.js").read_text()
add = "".join(f',"{i}":"goal.html"' for i in ["goal", "goal-aim", "goal-winner", "goal-map", "goal-rq", "goal-design"] if f'"{i}":"goal.html"' not in js)
if add:
    js = js.replace('"e52-v13-figI":"e52.html"', '"e52-v13-figI":"e52.html"' + add, 1); (d / "site.js").write_text(js)
print("ok", len(page))
