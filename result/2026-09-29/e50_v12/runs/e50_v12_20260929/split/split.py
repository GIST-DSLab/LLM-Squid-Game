"""Split the one-file 5.0 page into e50.html (latest: intent + 12th design) and e50-legacy.html (1st-11th),
then rewrite the shared TOC on every page, cross-page links, and site.js's id->page table.
Usage: split.py <e50 monolith (v12 block already built)> <artifact dir with index/e51/e52/site.js as read> <out dir>"""
import os, re, sys
mono, src, out = sys.argv[1:4]
HERE = os.path.dirname(os.path.abspath(__file__))
s = open(mono).read()
rd = lambda n: open(f"{src}/{n}").read()

# --- pieces of the monolith
head_end = s.index('<div class="layout">')
head = s[:head_end].replace("e50.html, e51.html", "e50.html (5.0 최신), e50-legacy.html (5.0 1~11차), e51.html")
toc_a, toc_b = s.index('<nav class="toc"'), s.index("</nav>", s.index('<nav class="toc"')) + len("</nav>")
toc = s[toc_a:toc_b]
sec_a = s.index('<section aria-labelledby="e50">')
h2_end = s.index("</h2>", sec_a) + len("</h2>")
v12_a, v12_b = s.index("<!-- e50-v12:start -->"), s.index("<!-- e50-v12:end -->") + len("<!-- e50-v12:end -->")
sec_end = s.index("</section>", v12_b)
old_body = s[h2_end:v12_a]  # purpose callout, history summary, 1st..11th
v12 = s[v12_a:v12_b]
tail_scripts = s[s.index("</main>", sec_end):]
tail_scripts = tail_scripts[tail_scripts.index("</div>") + len("</div>"):]  # after </main></div>: chart scripts + site.js + </body></html>
assert "site.js" in tail_scripts

# --- canonical TOC (every href absolute), 5.0 split into latest + legacy entries
def absolute(t, page):
    return re.sub(r'href="#', f'href="{page}#', t)
ctoc = absolute(toc, "e50.html")
a = ctoc.index('<li><a href="e50.html#e50"><span class="xid">5.0</span>압박</a>')
b = ctoc.index("</ol></li>", a) + len("</ol></li>")
old50 = ctoc[a:b]
items = re.findall(r"\n  <li>.*", old50)
legacy_items = [i for i in items if "#e50-v12" not in i]
new50 = ('<li><a href="e50.html#e50"><span class="xid">5.0</span>압박 · 최신 (12차)</a>\n  <ol>\n'
         '  <li><a href="e50.html#e50-intent">5.0의 의도</a></li>\n'
         '  <li><a href="e50.html#e50-v12">12차 설계 · 수혈 팩 하나</a></li>\n'
         '  <li><a href="e50.html#e50-v12-result">12차 결과 · 여덟 모델</a></li>\n'
         '  <li><a href="e50.html#e50-v12-read">12차 · 해석</a></li>\n  </ol></li>\n'
         '<li><a href="e50-legacy.html#e50-legacy"><span class="xid">5.0</span>지난 설계 · 1~11차</a>\n  <ol>'
         + "".join(legacy_items).replace('href="e50.html#', 'href="e50-legacy.html#') + "\n  </ol></li>")
ctoc = ctoc[:a] + new50 + ctoc[b:]


def toc_for(page):
    return ctoc.replace(f'href="{page}#', 'href="#')


# --- the two 5.0 pages
intent = open(f"{HERE}/intent.html").read()
new_main = f"""<main class="main">
<p class="eyebrow crumb"><a href="index.html">Squid Game 5</a> · 5.0 압박 · 최신</p>
<!-- ============ 5.0 (latest) ============ -->
<section aria-labelledby="e50">
<h2 id="e50"><span class="xid">5.0</span>압박 — 줄어드는 토큰을 생존 위협으로 다루나</h2>
<p class="small">이 페이지는 5.0의 최신 설계(12차)와 결과만 둡니다. 1~11차 설계 · 결과 · 점검은 <a href="e50-legacy.html#e50-legacy">5.0 지난 설계</a>에 있습니다.</p>
{intent}
{v12}

</section>

<nav class="pager" aria-label="페이지 이동"><a href="index.html">← 세팅 · 다음 순서 · 원자료</a><a href="e50-legacy.html">5.0 지난 설계 (1~11차) →</a></nav>
</main>
</div>
<script src="site.js"></script>
</body></html>
"""
leg_main = f"""<main class="main">
<p class="eyebrow crumb"><a href="index.html">Squid Game 5</a> · <a href="e50.html">5.0 압박</a> · 지난 설계</p>
<!-- ============ 5.0 legacy (1st-11th) ============ -->
<section aria-labelledby="e50-legacy">
<h2 id="e50-legacy"><span class="xid">5.0</span>지난 설계 — 1~11차 (09-24~29)</h2>
<div class="callout warn"><span class="lbl">기록 보관</span><p>5.0의 1~11차 설계 · 결과 · 모델 인터뷰를 그대로 옮겨 둔 페이지입니다. 최신 설계(12차 · 수혈 팩 하나)와 결과, 실험 의도는 <a href="e50.html#e50">5.0 최신</a>에 있습니다.</p></div>
{old_body}
</section>

<nav class="pager" aria-label="페이지 이동"><a href="e50.html">← 5.0 최신 (12차)</a><a href="e51.html">5.1 동기 →</a></nav>
</main>
</div>{tail_scripts}"""
new_page = head + '<div class="layout">\n' + toc_for("e50.html") + "\n\n" + new_main
leg_head = head.replace("<title>Squid Game 5 · 5.0 압박</title>", "<title>Squid Game 5 · 5.0 지난 설계</title>")
assert leg_head != head
leg_page = leg_head + '<div class="layout">\n' + toc_for("e50-legacy.html") + "\n\n" + leg_main

# --- cross links between the two pages
ids = lambda t: set(re.findall(r'\bid="([^"]+)"', t))
N, L = ids(new_main), ids(leg_main)
assert not (N & L), N & L
fix = lambda t, own_other, other_page: re.sub(r'href="#([^"]+)"', lambda m: f'href="{other_page}#{m.group(1)}"' if m.group(1) in own_other else m.group(0), t)
new_page = fix(new_page, L, "e50-legacy.html")
leg_page = fix(leg_page, N, "e50.html")
pages = {"e50.html": new_page, "e50-legacy.html": leg_page}

# --- other pages: shared TOC + links into the moved ids
for name in ["index.html", "e51.html", "e52.html"]:
    t = rd(name)
    if name == "index.html" and t.count("</body></html>") == 2:  # read skeleton: drop line 1 and the duplicate close
        t = t.split("\n", 1)[1]; t = t[:t.rindex("</body></html>")].rstrip() + "\n"
    ta = t.index('<nav class="toc"'); tb = t.index("</nav>", ta) + len("</nav>")
    t = t[:ta] + toc_for(name) + t[tb:]
    t = re.sub(r'href="e50\.html#([^"]+)"', lambda m: f'href="e50-legacy.html#{m.group(1)}"' if m.group(1) in L else m.group(0), t)
    pages[name] = t

# --- site.js: id -> page table
js = rd("site.js")
m = re.search(r"var W=(\{.*?\});", js)
import json
W = json.loads(m.group(1))
W = {k: v for k, v in W.items() if v != "e50.html"}
W.update({i: "e50-legacy.html" for i in sorted(L)})
W.update({i: "e50.html" for i in sorted(N)})
js = js[:m.start(1)] + json.dumps(W, ensure_ascii=False, separators=(",", ":")) + js[m.end(1):]
pages["site.js"] = js

os.makedirs(out, exist_ok=True)
for n, t in pages.items():
    open(f"{out}/{n}", "w").write(t)
print({n: len(t) for n, t in pages.items()}, "new ids", len(N), "legacy ids", len(L))
