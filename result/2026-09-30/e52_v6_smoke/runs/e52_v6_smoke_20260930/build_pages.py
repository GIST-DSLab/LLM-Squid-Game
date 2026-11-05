"""Splice the v6 calibration log (all entries in calib_entries/, oldest first) and the smoke results (smoke_frags/)
into e52.html after the v6 prompt block, and make sure the TOC lines exist on every page.
usage: build_pages.py <downloaded artifact dir> <out dir>"""
import pathlib, re, sys
R = pathlib.Path.home() / "squid5-runs/e52_v6_smoke_20260930"
src, out = pathlib.Path(sys.argv[1]), pathlib.Path(sys.argv[2]); out.mkdir(parents=True, exist_ok=True)
entries = "".join(p.read_text() for p in sorted((R / "calib_entries").glob("*.html")))
frags = sorted((R / "smoke_frags").glob("*.html"))
smoke = "".join(p.read_text() for p in frags) or "<p>진행 중입니다.</p>"
note = (R / "smoke_note.html").read_text() if (R / "smoke_note.html").exists() else ""
block = f"""<!-- e52-v6runs:start -->
<style>.e52cal-entry{{margin:14px 0 18px;padding-left:12px;border-left:2px solid var(--line)}} .e52v6r td{{vertical-align:top}}</style>
<div class="e52v6 e52v6r">
<h4 id="e52-v6-calib">⑦ 보정 기록 (누적 · 회차마다 아래에 쌓음)</h4>
<p class="small">보정 = 압박 없이(잔액 1천만, 선물 · 상금 · 유지비 없음) 넷 다 푸는 판 하나. 칸 안의 수는 SOLVE 생성 토큰의 중앙값, 아래 줄은 범위 · 정답/시도. c̄ = PLAN 중앙값 + 여섯 라운드 일정의 SOLVE 평균(에이전트 한 명의 라운드당 비용). 오른쪽 끝은 여기서 정한 스모크 숫자(P = 4c̄, U = P/2, 부담금 c̄, 시작 8c̄). 원본 JSON은 브랜치 <code>exp/e52-v6-smoke</code>의 <code>docs/history/e52-v6-calib/</code>에 날짜별로 보관합니다.</p>
{entries}
<h4 id="e52-v6-smoke">⑧ 스모크 결과 (모델마다 1판, 숨긴 6라운드)</h4>
{note}
{smoke}
</div>
<!-- e52-v6runs:end -->
"""
TOC = [("#e52-v6-calib", "v6 · 보정 기록 (누적)", "e52-v6-calib-toc"), ("#e52-v6-smoke", "v6 · 스모크 결과", "e52-v6-smoke-toc")]
for name in ["index.html", "e50.html", "e50-legacy.html", "e51.html", "e51-legacy.html", "e52.html"]:
    t = (src / name).read_text()
    own = name == "e52.html"; pre = "" if own else "e52.html"
    anchor = "<!-- e52-v6-rank-toc -->\n"
    for href, label, tag in reversed(TOC):
        if f"<!-- {tag} -->" not in t:
            t = t.replace(anchor, anchor + f'  <li><a href="{pre}{href}">{label}</a></li><!-- {tag} -->\n', 1)
    if own:
        if "<!-- e52-v6runs:start -->" in t:
            s, e = t.index("<!-- e52-v6runs:start -->"), t.index("<!-- e52-v6runs:end -->") + len("<!-- e52-v6runs:end -->\n")
            t = t[:s] + block + t[e:]
        else:
            t = t.replace("<!-- e52-v6prompt:end -->\n", "<!-- e52-v6prompt:end -->\n" + block, 1)
    (out / name).write_text(t)
print("ok", len(frags), "smoke frags")
