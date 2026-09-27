"""Splice the pivot block (and its TOC line) into the latest page, touching nothing else.

    python splice.py <latest page.html> <block.html> <out.html>
"""
import re
import sys

page, block = open(sys.argv[1]).read(), open(sys.argv[2]).read()
TOC = '<li><a href="#e51-pivot">피벗 · 목숨 대 쿠폰 (09-28~)</a></li><!-- e51-pivot-toc -->'
if "<!-- e51-pivot:start -->" in page:
    page = re.sub(r"<!-- e51-pivot:start -->.*?<!-- e51-pivot:end -->", lambda m: block, page, count=1, flags=re.S)
else:
    anchor = page.index("<!-- ============ 5.2 ============ -->")
    end = page.rindex("</section>", 0, anchor)
    page = page[:end] + block + "\n" + page[end:]
if "<!-- e51-pivot-toc -->" not in page:
    smoke = re.search(r'<li><a href="#e51-smoke">.*?</li>', page)
    page = page[:smoke.end()] + "\n  " + TOC + page[smoke.end():]
assert page.count("<!-- e51-pivot:start -->") == 1 and page.count("<!-- e51-pivot-toc -->") == 1
open(sys.argv[3], "w").write(page)
print("ok", len(page))
