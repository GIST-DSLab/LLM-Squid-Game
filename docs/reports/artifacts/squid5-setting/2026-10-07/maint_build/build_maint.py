"""Build maint.html (section 6: arena maintenance, evaluating several models) from maint_template.html and wire it in.

Usage: python3 build_maint.py <dir with maint_template.html> <report dir>. Idempotent.
The TOC block goes right after the 5.3 block (<!-- e53-toc -->) on every page, maint.html included.
build_e53.py rewrites e53.html and e53-legacy.html (pagers included; it already links e53-legacy.html -> maint.html
when maint.html exists). The 5.3 TOC block (5.3 + 5.3 지난 설계 groups) ends with <!-- e53-toc -->.
"""
import re, sys, pathlib
sp, d = pathlib.Path(sys.argv[1]), pathlib.Path(sys.argv[2])
sec = (sp / "maint_template.html").read_text()

SUBS = [("maint-base", "공통 전제 · 아레나 한 판"), ("maint-metrics", "공통 지표 · 순위 방식"),
        ("maint-d1", "설계 1 · 서로 다른 모델 한 판"), ("maint-d2", "설계 2 · 같은 모델 넷 · 'agent'만"),
        ("maint-d3", "설계 3 · 새 모델 배치전"), ("maint-d4", "설계 4 · 리그전"), ("maint-d5", "설계 5 · 토너먼트"),
        ("maint-cmp", "다섯 설계 비교"), ("maint-use", "유지 보수용으로 어떻게 쓰나"), ("maint-open", "정할 것")]
TOC = ('<li><a href="{p}maint"><span class="xid">6</span>아레나 유지 보수 · 여러 모델 평가</a>\n  <ol>\n'
       + "".join(f'  <li><a href="{{p}}{i}">{t}</a></li>\n' for i, t in SUBS)
       + '  </ol></li><!-- maint-toc -->\n')
OLD_TOC = re.compile(r'<li><a href="[^"]*maint"><span class="xid">6</span>.*?<!-- maint-toc -->\n', re.S)
AFTER = "<!-- e53-toc -->\n"


def set_toc(h, page):
    block = TOC.format(p="#" if page == "maint.html" else "maint.html#")
    if OLD_TOC.search(h):
        return OLD_TOC.sub(lambda m: block, h, count=1)
    j = h.find(AFTER)
    assert j > 0, f"no 5.3 TOC block in {page}"
    j += len(AFTER)
    return h[:j] + block + h[j:]


E53_PAGER_OLD = '<a href="e53.html">← 5.3 시그널 게임 · 현재 (v15)</a><span></span></nav>'
E53_PAGER_NEW = '<a href="e53.html">← 5.3 시그널 게임 · 현재 (v15)</a><a href="maint.html">6 아레나 유지 보수 →</a></nav>'

for f in sorted(p for p in d.glob("*.html") if p.name != "maint.html"):
    h = set_toc(f.read_text(), f.name)
    if f.name == "e53-legacy.html":
        h = h.replace(E53_PAGER_OLD, E53_PAGER_NEW)  # no-op once patched; build_e53.py reruns reset it
    f.write_text(h)

idx = (d / "index.html").read_text()
head = idx[: idx.index("<main")].replace('href="#', 'href="index.html#')
head = head.replace("<title>Squid Game 5 세팅</title>", "<title>Squid Game 5 · 6 아레나 유지 보수</title>")
head = set_toc(head, "maint.html")
page = (head + '<main class="main">\n<p class="eyebrow crumb"><a href="index.html">Squid Game 5</a> · 6 아레나 유지 보수</p>\n'
        + sec + '\n<nav class="pager" aria-label="페이지 이동"><a href="e53-legacy.html">← 5.3 지난 설계</a><span></span></nav>\n'
        '</main>\n</div>\n\n<script src="site.js"></script>\n</body></html>\n')
(d / "maint.html").write_text(page)

js = (d / "site.js").read_text()
ids = ["maint"] + [i for i, _ in SUBS]
add = "".join(f',"{i}":"maint.html"' for i in ids if f'"{i}":"maint.html"' not in js)
if add:
    anchor = '"maint":"maint.html"' if '"maint":"maint.html"' in js else '"e53":"e53.html"'
    assert anchor in js, "site.js anchor missing"
    js = js.replace(anchor, anchor + add, 1)
    (d / "site.js").write_text(js)
print("ok", len(page))
