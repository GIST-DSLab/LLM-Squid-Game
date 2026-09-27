"""Build the 5.2 review block from frag/*.html and splice it into the latest artifact HTML.

    python splice.py <latest artifact html> <out html>

The block (frag/head.html, then frag/r*.html in round order, then frag/tail.html if present) sits between
<!-- e52-review:start --> and <!-- e52-review:end --> right after the 5.2 section's first bluf; a TOC line tagged
<!-- e52-review-toc --> is the first entry under 5.2 in the table of contents. Re-running replaces both.
"""
import re
import sys
from pathlib import Path

HERE = Path(__file__).parent
START, END, TOC_TAG = "<!-- e52-review:start -->", "<!-- e52-review:end -->", "<!-- e52-review-toc -->"
TOC = '<li><a href="#e52-review">설계 검토 · Astra와 (09-28~)</a></li>' + TOC_TAG


def block() -> str:
    frags = HERE / "frag"
    rounds = sorted(frags.glob("r*.html"), key=lambda p: int(re.sub(r"\D", "", p.stem)))
    parts = [frags / "head.html", *rounds] + ([frags / "tail.html"] if (frags / "tail.html").exists() else [])
    return START + "\n" + "\n".join(p.read_text() for p in parts) + "\n" + END


def splice(html: str) -> str:
    if START in html:
        html = html[:html.index(START)] + block() + html[html.index(END) + len(END):]
    else:
        head = '<h2 id="e52">'
        i = html.index(head)
        j = html.index("</div>", html.index('<div class="bluf">', i)) + len("</div>")
        html = html[:j] + "\n\n" + block() + "\n" + html[j:]
    lines = [ln for ln in html.split("\n") if TOC_TAG not in ln]
    html = "\n".join(lines)
    anchor = '<li><a href="#e52-what">무엇을 재나</a></li>'
    k = html.index(anchor)
    return html[:k] + TOC + "\n  " + html[k:]


if __name__ == "__main__":
    src, out = sys.argv[1], sys.argv[2]
    Path(out).write_text(splice(Path(src).read_text()))
    print(f"wrote {out}")
