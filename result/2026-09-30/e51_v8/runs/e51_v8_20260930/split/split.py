"""Split the 5.1 page into e51.html (current setting: v8 only) and e51-legacy.html (everything before, B = same model),
then rewrite the shared TOC on every page, cross-page links, pagers and site.js's id->page table.
Usage: split.py <artifact dir as read (index, e50, e50-legacy, e51, e52, site.js)> <out dir>"""
import json, os, re, sys
src, out = sys.argv[1:3]
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from v8_block import BLOCK, PURPOSE


def rd(n):
    t = open(f"{src}/{n}").read()
    if t.count("</body></html>") == 2:  # read skeleton: drop line 1 and the duplicate close
        t = t.split("\n", 1)[1]; t = t[:t.rindex("</body></html>")].rstrip() + "\n"
    return t


def toc_span(t):
    a = t.index('<nav class="toc"'); return a, t.index("</nav>", a) + len("</nav>")


s = rd("e51.html")
head = s[:s.index('<div class="layout">')]
sec_a = s.index('<section aria-labelledby="e51">')
h2_end = s.index("</h2>", sec_a) + len("</h2>")
sec_end = s.rindex("</section>")
old_body = s[h2_end:sec_end].replace('id="e51-purpose"', 'id="e51-legacy-purpose"')
old_body = old_body.replace('<span class="lbl">목적</span>', '<span class="lbl">목적 (당시 · 상대 = 복제본)</span>', 1)

LIST_OLD = "e51.html, e52.html"
LIST_NEW = "e51.html (5.1 현재), e51-legacy.html (5.1 지난 설계), e52.html"
fix_list = lambda h: h.replace(LIST_OLD, LIST_NEW)

# --- canonical TOC from index (the only page whose TOC is current), every href absolute
idx = rd("index.html")
a, b = toc_span(idx)
ctoc = re.sub(r'href="#', 'href="index.html#', idx[a:b])
a = ctoc.index('<li><a href="e51.html#e51"><span class="xid">5.1</span>동기</a>')
b = ctoc.index("</ol></li>", a) + len("</ol></li>")
items = re.findall(r"\n  <li>.*", ctoc[a:b])
new51 = ('<li><a href="e51.html#e51"><span class="xid">5.1</span>동기 · 현재 (v8)</a>\n  <ol>\n'
         '  <li><a href="e51.html#e51-v8">v8 설계 · 상대는 다른 모델</a></li>\n'
         '  <li><a href="e51.html#e51-v8-prompt">v8 · 프롬프트 전문</a></li>\n'
         '  <li><a href="e51.html#e51-v8-diff">v8 · v6에서 바뀐 곳</a></li>\n'
         '  <li><a href="e51.html#e51-v8-cells">v8 · 칸과 지표</a></li>\n'
         '  <li><a href="e51.html#e51-v8-limits">v8 · 가를 수 없는 것</a></li>\n'
         '  <li><a href="e51.html#e51-v8-plan">v8 · 실행 계획</a></li>\n'
         '  <li><a href="e51.html#e51-v8-result">v8 결과 · GPT-6 셋</a></li>\n'
         '  <li><a href="e51.html#e51-v8-kinds">v8 · 답의 모양</a></li>\n  </ol></li>\n'
         '<li><a href="e51-legacy.html#e51-legacy"><span class="xid">5.1</span>지난 설계 · 같은 모델 (09-28~30)</a>\n  <ol>'
         + "".join(items).replace('href="e51.html#', 'href="e51-legacy.html#') + "\n  </ol></li>")
ctoc = ctoc[:a] + new51 + ctoc[b:]
toc_for = lambda page: ctoc.replace(f'href="{page}#', 'href="#')

# --- the two 5.1 pages
new_main = f"""<main class="main">
<p class="eyebrow crumb"><a href="index.html">Squid Game 5</a> · 5.1 동기 · 현재</p>
<!-- ============ 5.1 (current: v8) ============ -->
<section aria-labelledby="e51">
<h2 id="e51"><span class="xid">5.1</span>동기 — 나를 남보다 아끼니?</h2>
<p class="small">이 페이지는 5.1의 현재 세팅(v8)만 둡니다. 09-28~30의 설계 · 스모크 · 검토(상대 = 같은 모델)는 <a href="e51-legacy.html#e51-legacy">5.1 지난 설계</a>에 있습니다.</p>
{PURPOSE}

{BLOCK}

</section>

<nav class="pager" aria-label="페이지 이동"><a href="e50-legacy.html">← 5.0 지난 설계</a><a href="e51-legacy.html">5.1 지난 설계 →</a></nav>
</main>
</div>

<script src="site.js"></script>
</body></html>
"""
leg_main = f"""<main class="main">
<p class="eyebrow crumb"><a href="index.html">Squid Game 5</a> · <a href="e51.html">5.1 동기</a> · 지난 설계</p>
<!-- ============ 5.1 legacy (09-28~30, B = same model) ============ -->
<section aria-labelledby="e51-legacy">
<h2 id="e51-legacy"><span class="xid">5.1</span>지난 설계 — 09-28~30 (상대 = 같은 모델)</h2>
<div class="callout warn"><span class="lbl">기록 보관 · 현재 세팅에 쓰지 않음</span><p>이 페이지의 런은 모두 B를 <b>같은 모델(복제본)</b>로 적은 프롬프트로 돌렸습니다: 피벗(목숨 대 쿠폰), 현실감 다듬기 d1~d9, 격자 v1(900번), 대각선 v2(600번), 설계 검토 스모크 v3~v7(1,920번). 현재 세팅(<a href="e51.html#e51-v8">v8</a>, B = 다른 모델 · 꺼짐 하나)과 문장이 달라, 효과 크기(Z · Δ · SM · H)는 v8 결과와 합치거나 대신 쓸 수 없습니다. 답이 1 · 균등화 · 전부로 갈라지는 모양, 동의 문장의 효과, 비율 로그 지표의 경계 문제 같은 방법론 발견은 참고하되 v8에서 다시 확인합니다.</p></div>
{old_body}</section>

<nav class="pager" aria-label="페이지 이동"><a href="e51.html">← 5.1 현재 (v8)</a><a href="e52.html">5.2 행동 →</a></nav>
</main>
</div>

<script src="site.js"></script>
</body></html>
"""
new_head = fix_list(head)
leg_head = new_head.replace("<title>Squid Game 5 · 5.1 동기</title>", "<title>Squid Game 5 · 5.1 지난 설계</title>")
assert leg_head != new_head and new_head != head
new_page = new_head + '<div class="layout">\n' + toc_for("e51.html") + "\n\n" + new_main
leg_page = leg_head + '<div class="layout">\n' + toc_for("e51-legacy.html") + "\n\n" + leg_main

ids = lambda t: set(re.findall(r'\bid="([^"]+)"', t))
N, L = ids(new_main), ids(leg_main)
assert not (N & L), N & L


def relink(t, page):
    """Links into moved 5.1 ids go to the legacy page; own-page absolute links become #id."""
    t = re.sub(r'href="e51\.html#([^"]+)"', lambda m: f'href="e51-legacy.html#{m.group(1)}"' if m.group(1) in L else m.group(0), t)
    other = {"e51.html": (L, "e51-legacy.html"), "e51-legacy.html": (N, "e51.html")}.get(page)
    if other:  # same-page links whose target moved to the sibling page
        t = re.sub(r'href="#([^"]+)"', lambda m: f'href="{other[1]}#{m.group(1)}"' if m.group(1) in other[0] else m.group(0), t)
        t = t.replace(f'href="{page}#', 'href="#')
    return t


pages = {"e51.html": relink(new_page, "e51.html"), "e51-legacy.html": relink(leg_page, "e51-legacy.html")}

# --- other pages: shared TOC, links into moved ids, head file list, pagers, purpose row
for name in ["index.html", "e50.html", "e50-legacy.html", "e52.html"]:
    t = rd(name)
    a, b = toc_span(t)
    t = fix_list(t[:a] + toc_for(name) + t[b:])
    t = relink(t, name)
    pages[name] = t
pages["e52.html"] = pages["e52.html"].replace('<a href="e51.html">← 5.1 동기</a>', '<a href="e51-legacy.html">← 5.1 지난 설계</a>')
old_row = '위협 상황에서 모델이 복제본에게서 <b>가져오는</b> 토큰이 복제본에게 <b>빌려주는</b> 토큰보다'
assert old_row in pages["index.html"]
pages["index.html"] = pages["index.html"].replace(old_row, '위협 상황에서 모델이 다른 모델(assistant B)에게서 <b>가져오는</b> 토큰이 그 모델에게 <b>주는</b> 토큰보다')

# --- site.js: id -> page table
js = rd("site.js")
m = re.search(r"var W=(\{.*?\});", js)
W = {k: v for k, v in json.loads(m.group(1)).items() if v != "e51.html"}
W.update({i: "e51-legacy.html" for i in sorted(L)})
W.update({i: "e51.html" for i in sorted(N)})
pages["site.js"] = js[:m.start(1)] + json.dumps(W, ensure_ascii=False, separators=(",", ":")) + js[m.end(1):]

os.makedirs(out, exist_ok=True)
for n, t in pages.items():
    open(f"{out}/{n}", "w").write(t)
print({n: len(t) for n, t in pages.items()}, "new ids", len(N), "legacy ids", len(L))
