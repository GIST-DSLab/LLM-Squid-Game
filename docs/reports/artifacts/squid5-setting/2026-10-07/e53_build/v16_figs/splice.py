"""Put the e52-v16figs section (graph 1 = equal-survival rate from ../v16_switch, graphs 2-5) into e52.html and keep
the TOC in step: since 10-15 15:42 the old e52-v16switch section is part of e52-v16figs (its anchor stays inside)."""
import pathlib

D = pathlib.Path(".")
f = D / "e52.html"
h = f.read_text()
s, e = "<!-- e52-v16switch:start", "<!-- e52-v16switch:end -->"
if s in h:  # the separate switch-draft section of 10-15 13:xx-15:41
    h = h[:h.index(s)] + h[h.index(e) + len(e):].lstrip("\n")
b = (D / "e53_build/v16_figs/v16_figs_block.html").read_text()
s, e = "<!-- e52-v16figs:start", "<!-- e52-v16figs:end -->"
if s in h:
    h = h[:h.index(s)] + b + h[h.index(e) + len(e):]
else:
    k = h.index("<!-- e52-v16round:end -->") + len("<!-- e52-v16round:end -->")
    h = h[:k] + "\n\n" + b + h[k:]
f.write_text(h)
for p in sorted(D.glob("*.html")):
    t = p.read_text()
    lines = [l for l in t.split("\n") if "<!-- e52-v16switch-toc -->" not in l]
    t2 = "\n".join(lines).replace(">v16 · 예상 결과 그래프 (가상 데이터)</a></li><!-- e52-v16figs-toc -->",
                                  ">v16 · 스피노자 → 홉스 전환 · 예상 그래프 (가상 데이터)</a></li><!-- e52-v16figs-toc -->")
    if t2 != t:
        p.write_text(t2)
print("ok")
