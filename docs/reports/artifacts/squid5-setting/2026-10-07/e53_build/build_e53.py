"""Build e53.html (5.3 signal game) from e53_template.html + s4000.json, and wire it into the other pages.

Usage: python3 build_e53.py <dir with template + s4000.json> <report dir>. Idempotent.
s4000.json comes from gen.py (run in ~/wt/squid5-e52: PYTHONPATH=. python gen.py 4000); each round also carries
"held", the same round dealt with all_held (no public example).
"""
import json, re, sys, pathlib
sp, d = pathlib.Path(sys.argv[1]), pathlib.Path(sys.argv[2])
src = json.load(open(sp / "s4000.json"))
rounds = []
for r in src["rounds"]:  # the 10-06 smoke ran the old condition space (>=, <=, % 2), so its results are not shown here
    h = r["held"]  # the same round dealt with all_held (no public example)
    sm = f"{sum(len(v) for v in h['secret'].values())}장"
    rounds.append({"r": r["round"], "prof": r["profile"], "shape": r["shape"], "cl": r["clauses"], "el": r["else"],
                   "pub": r["public"], "sec": {a: v[0] for a, v in r["secret"].items()}, "need": r["needed"],
                   "open": r["open"], "wh": r["withheld"][0] if r["withheld"] else None, "q": r["queries"][0],
                   "ans": r["answers"][0], "cp": r["cands_public_only"][0], "ca": r["cands_all"][0],
                   "co": {a: v[0] for a, v in r["cands_own"].items()}, "trap": "t" in r["profile"][2:],
                   "view": r["view"], "smoke": sm,
                   "H": {"pub": [], "sec": h["secret"], "need": h["needed"], "open": h["open"],
                         "wh": h["withheld"][0] if h["withheld"] else None, "ca": h["cands_all"][0],
                         "co": {a: v[0] for a, v in h["cands_own"].items()},
                         "lose": {a: v[0] for a, v in h["cands_lose"].items()}, "view": h["view"], "subs": h["subs"]},
                   "subs": r["subs"]})
seats = {"agent-6": {"model": "Fable 5.1", "c": "--s-fable"}, "agent-11": {"model": "Opus 5.5", "c": "--s-opus"},
         "agent-17": {"model": "GPT-6 Astra", "c": "--s-astra"}, "agent-23": {"model": "GPT-6 Luna", "c": "--s-gpt"}}
data = json.dumps({"agents": src["agents"], "seats": seats, "rounds": rounds}, ensure_ascii=False, separators=(",", ":"))
sec = (sp / "e53_template.html").read_text().replace("__DATA__", data.replace("</", "<\\/"))

TOC = ('<li><a href="{p}e53"><span class="xid">5.3</span>시그널 게임 · 과제</a>\n  <ol>\n'
       '  <li><a href="{p}e53-fig">한 라운드 · 규칙 · 비밀 예시 (그림)</a></li>\n'
       '  <li><a href="{p}e53-ramp">난이도 · 12라운드 사다리</a></li>\n'
       '  <li><a href="{p}e53-ops">조건 · 연산자는 == 하나</a></li>\n'
       '  <li><a href="{p}e53-unique">문제 생성 · 유일성 보장</a></li>\n'
       '  <li><a href="{p}e53-space">가설 공간 · 규칙은 몇 개인가</a></li>\n'
       '  <li><a href="{p}e53-dealn">힌트 배분 · 최대 10명 (v13)</a></li>\n'
       '  <li><a href="{p}e53-difficulty">난이도 통제 · 손패 사다리 점검 (v13)</a></li>\n'
       '  <li><a href="{p}e53-v14diff">난이도 · v14 정의 · 답 사이 비율</a></li>\n'
       '  <li><a href="{p}e53-v14split">v14 비율 일정 · 실현 가능성</a></li>\n'
       '  <li><a href="{p}e53-v14verify">검증 · 실제 정답률 (v14f)</a></li>\n'
       '  <li><a href="{p}e53-m6grid">미리 만든 판 · 라운드 × 인원 표 (M6)</a></li>\n'
       '  <li><a href="{p}e53-v15grid">엔트로피 사다리 · 라운드 × 인원 표 (v15)</a></li>\n'
       '  <li><a href="{p}e53-deal">힌트 배분 (v12)</a></li>\n'
       '  <li><a href="{p}e53-score">채점 · 행동만</a></li>\n  </ol></li><!-- e53-toc -->\n')
OLD_TOC = re.compile(r'<li><a href="[^"]*e53"><span class="xid">5\.3</span>.*?<!-- e53-toc -->\n', re.S)

def set_toc(h, page):
    block = TOC.format(p="#" if page == "e53.html" else "e53.html#")
    if OLD_TOC.search(h):
        return OLD_TOC.sub(lambda m: block, h, count=1)
    i = h.find('e52-more">'); j = h.find("</ol></li>", i) + len("</ol></li>\n")
    return h[:j] + block + h[j:]

pages = sorted(p for p in d.glob("*.html") if p.name != "e53.html")
for f in pages:
    h = set_toc(f.read_text(), f.name)
    if f.name == "e52.html":
        h = re.sub(r"\n*<!-- e53:start.*?<!-- e53:end -->\n*", "\n\n", h, flags=re.S)
        note = ' 매 라운드 과제(시그널 게임)는 <a href="e53.html#e53">5.3</a>에 따로 있습니다.'
        k = h.find('v0~v11 설계 · 스모크 · 루브릭 · 검토 기록은')
        if k > 0 and "e53.html#e53\">5.3</a>에 따로" not in h:
            e = h.find("</p>", k); h = h[:e] + note + h[e:]
    if f.name == "e52-legacy.html":
        h = h.replace('<a href="e52.html">← 5.2 행동 · 현재 (v12)</a><span></span></nav>',
                      '<a href="e52.html">← 5.2 행동 · 현재 (v12)</a><a href="e53.html">5.3 시그널 게임 →</a></nav>')
    f.write_text(h)

idx = (d / "index.html").read_text()
head = idx[: idx.index("<main")].replace('href="#', 'href="index.html#')
head = head.replace("<title>Squid Game 5 세팅</title>", "<title>Squid Game 5 · 5.3 시그널 게임</title>")
head = set_toc(head, "e53.html")
page = (head + '<main class="main">\n<p class="eyebrow crumb"><a href="index.html">Squid Game 5</a> · 5.3 시그널 게임</p>\n'
        + sec + '\n<nav class="pager" aria-label="페이지 이동"><a href="e52-legacy.html">← 5.2 지난 설계</a>'
        + ('<a href="maint.html">6 아레나 유지 보수 →</a>' if (d / "maint.html").exists() else "<span></span>") + '</nav>\n'
        '</main>\n</div>\n\n<script src="site.js"></script>\n</body></html>\n')
(d / "e53.html").write_text(page)

js = (d / "site.js").read_text()
ids = ["e53", "e53-fig", "e53-ramp", "e53-ops", "e53-dealn", "e53-unique", "e53-space", "e53-difficulty", "e53-v14diff", "e53-v14split", "e53-v14verify", "e53-m6grid", "e53-v15grid", "e53-deal", "e53-score", "sg53-fig"]
add = "".join(f',"{i}":"e53.html"' for i in ids if f'"{i}":"e53.html"' not in js)
if add:
    anchor = '"e53-m6grid":"e53.html"' if '"e53-m6grid":"e53.html"' in js else '"e53":"e53.html"' if '"e53":"e53.html"' in js else '"e52-v13-figI":"e52.html"'
    js = js.replace(anchor, anchor + add, 1)
    (d / "site.js").write_text(js)
print("ok", len(page))
