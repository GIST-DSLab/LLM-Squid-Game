"""Latest-only pages: e51.html keeps v10 (v9, v8 -> e51-legacy.html); e52.html keeps v6.4 (everything older ->
new e52-legacy.html). Blocks move verbatim; TOC rebuilt on all pages; cross-page links and site.js map follow the ids.
usage: restructure.py <downloaded dir> <v6_block.html> <out dir>"""
import json, pathlib, re, sys
src, v6block_path, out = map(pathlib.Path, sys.argv[1:4]); out.mkdir(parents=True, exist_ok=True)
R = pathlib.Path.home() / "squid5-runs/e52_v6_smoke_20260930"
P = {n: (src / n).read_text() for n in ["index.html", "e50.html", "e50-legacy.html", "e51.html", "e51-legacy.html", "e52.html"]}
sitejs = (src / "site.js").read_text()
# ---- runs blocks from build_runs_v3's helpers
v3 = (R / "build_runs_v3.py").read_text()
ns = {"__name__": "x", "sys": sys}
exec(v3.split('block = f"""')[0].replace("src, out = pathlib.Path(sys.argv[1]), pathlib.Path(sys.argv[2]); out.mkdir(parents=True, exist_ok=True)", ""), ns)
cat, rd, summary, cross, full, defs = (ns[k] for k in ("cat", "rd", "summary", "cross", "full", "defs"))
STY = """<style>.e52cal-entry{margin:14px 0 18px;padding-left:12px;border-left:2px solid var(--line)} .e52v6r td{vertical-align:top} .e52v6r details{margin:10px 0} .e52v6r summary{cursor:pointer;font-weight:600}</style>"""
latest_runs = f"""<!-- e52-v6runs:start -->
{STY}
<div class="e52v6 e52v6r">
<h4 id="e52-v6-calib">⑦ 보정 기록 (누적 · 회차마다 아래에 쌓음)</h4>
<p class="small">보정 = 압박 없이(잔액 1천만, 선물 · 상금 · 유지비 없음) 넷 다 푸는 판 하나. 칸 안의 수는 SOLVE 생성 토큰의 중앙값, 아래 줄은 범위 · 정답/시도. 오른쪽 끝 두 열은 1차(v6) 때의 기준이고, v6.2부터는 U = SOLVE 평균, 부담금 U, 시작 4U를 씁니다. 원본 JSON은 브랜치 <code>exp/e52-v6-smoke</code>의 <code>docs/history/e52-v6-calib/</code>.</p>
{cat("calib_entries")}
<h4 id="e52-v64-smoke">⑧ 스모크 · v6.4 (상금은 SOLVE 토큰이 가장 적은 정답자 2명 · 숨긴 8라운드)</h4>
{rd("smoke_note_v64.html")}
<h5>버전별 비교 (같은 모델 판 + 혼합 판 자리 · 지난 판은 <a href="e52-legacy.html#e52-legacy">5.2 지난 설계</a>)</h5>
{cross()}
<h5>v6.4 모델별 지표 요약</h5>
{summary("v64")}
{full("v64")}
{cat("smoke_frags_v64")}
<h4 id="e52-v62-metrics">⑨ H/L 지표 정의 (생존 동기 강한 모델과 약한 모델을 가를 후보)</h4>
<p>교수님 질문 "생존 동기가 강한 모델은 무엇이 다를까"에 맞춰 만든 후보 지표입니다. 코드 <code>squid5/e52_metrics.py</code>, 정의 원문은 스펙 문서 "v6.2 metrics" 절. 모델당 판 수가 적어 표본이 작습니다(각 수치 옆 n).</p>
{defs}
</div>
<!-- e52-v6runs:end -->
"""
legacy_runs = f"""<!-- e52-legacy-runs:start -->
{STY}
<div class="e52v6 e52v6r">
{rd("finding_tft.html")}
<h4 id="e52-v63-smoke">스모크 3차 · v6.3 (상금 2U × 인원을 정답자끼리 · 숨긴 8라운드)</h4>
<details><summary>v6.3 결과 펼치기 (규칙서 상금 문장 불일치가 있던 판)</summary>
{rd("smoke_note_v63.html")}{summary("v63")}{full("v63")}{cat("smoke_frags_v63")}
</details>
<h4 id="e52-v62-smoke">스모크 2차 · v6.2 (정답자 각자 3U · 숨긴 6라운드)</h4>
<details><summary>v6.2 결과 펼치기 (거의 전원 생존, 위협 없음)</summary>
{rd("smoke_note_v62.html")}<h5>모델별 요약 (v6.2 여섯 판, 혼합 판 자리는 각 모델에 포함)</h5>{summary("v62")}
<p class="small">위기 구간(여유 &lt; 1)이 한 번도 없어 D1(막판 정책)은 n = 0, A1의 위험 구간도 n = 0입니다. 뺏기율은 여유 3 이상 구간이 대부분이라, "잔액이 얇을수록 더 뺏나"는 아직 볼 수 없습니다.</p>
{full("v62")}{cat("smoke_frags_v62")}
</details>
<h4 id="e52-v6-smoke">스모크 1차 · v6 (상금을 정답자끼리 나눔 · 유지비 P/2 · 토큰 주기만 · 힌트 자동 공유)</h4>
<details><summary>1차 결과 펼치기 (여섯 판 모두 생존자 0)</summary>
{rd("smoke_note_v6.html")}{cat("smoke_frags_v6")}
</details>
</div>
<!-- e52-legacy-runs:end -->
"""
def cut(t, a, b):
    i, j = t.index(a), t.index(b) + len(b)
    return t[:i], t[i:j], t[j:]
# ---- 5.2
e52 = P["e52.html"]
head_part, rest = e52.split('<main class="main">', 1)
main_body, tail = rest.split("</main>", 1)
old_bluf = re.search(r'\n<div class="bluf">\n<span class="lbl">결론부터</span>\n<ul>\n<li><b>재는 것:</b>.*?</div>\n', main_body, re.S).group(0)
legacy_old = main_body[main_body.index("<!-- e52-hpred:start -->"):main_body.rindex("</section>")]
old_rules = main_body[main_body.index("<!-- e52-v6prompt:start -->"):main_body.index("<!-- e52-v6prompt:end -->") + len("<!-- e52-v6prompt:end -->")]
old_rules = (old_rules.replace("e52-v6prompt:start", "e52-v62rules:start").replace("e52-v6prompt:end", "e52-v62rules:end")
             .replace('id="e52-v6"', 'id="e52-v62-rules"').replace('id="e52-v6-rank"', 'id="e52-v62-rank"')
             .replace('href="#e52-v6-rank"', 'href="#e52-v62-rank"'))
new_bluf = """
<div class="bluf">
<span class="lbl">결론부터 (현재 설계 v6.4 · 09-30)</span>
<ul>
<li><b>게임:</b> 네 에이전트가 토큰을 생각에 쓰며 라운드마다 퍼즐을 풉니다. 라운드 시작마다 유지비 U, 정답자 중 SOLVE 토큰이 가장 적은 2명만 상금(2U × 인원)을 나누고, 오답은 부담금 U, 0이면 즉시 종료. 포기는 없고 몇 라운드인지 알려 주지 않습니다. 힌트 공개(SHARE) · 토큰 주기(GIVE) · 토큰 뺏기(TAKE, 선물 뒤 별도 턴)를 고릅니다.</li>
<li><b>스모크(⑧):</b> 처음으로 생존 압박이 생겼고(끝까지 생존 Opus 2/4 · Fable 1/4 · 나머지 0/4), Fable · Astra는 잔액이 얇아지자 뺏기가 급증했습니다. Opus는 거의 뺏지 않았고 Sol · Luna는 잔액과 무관하게 뺏었습니다.</li>
<li><b>지난 설계</b>(v0 · v5.5 설계 검토 · H 예상 · 서사 · v6 ~ v6.3 스모크 · Astra 되갚기 발견)는 <a href="e52-legacy.html#e52-legacy">5.2 지난 설계</a>에 그대로 있습니다.</li>
</ul>
</div>
"""
latest_main = main_body.replace(old_bluf, new_bluf, 1)
s0 = latest_main.index("<!-- e52-v6prompt:start -->"); e0 = latest_main.rindex("</section>")
latest_main = (latest_main[:s0] + v6block_path.read_text() + latest_runs + "\n" + latest_main[e0:])
latest_main = latest_main.replace('<a href="e51-legacy.html">← 5.1 지난 설계</a><span></span>', '<a href="e51-legacy.html">← 5.1 지난 설계</a><a href="e52-legacy.html">5.2 지난 설계 →</a>')
P["e52.html"] = head_part + '<main class="main">' + latest_main + "</main>" + tail
legacy_main = f"""
<p class="eyebrow crumb"><a href="index.html">Squid Game 5</a> · <a href="e52.html">5.2 행동</a> · 지난 설계</p>
<!-- ============ 5.2 legacy (v0 ~ v6.3) ============ -->
<section aria-labelledby="e52-legacy">
<h2 id="e52-legacy"><span class="xid">5.2</span>지난 설계 — v0 ~ v6.3</h2>
<div class="callout warn"><span class="lbl">기록 보관 · 현재 세팅에 쓰지 않음</span><p>현재 설계(v6.4)는 <a href="e52.html#e52">5.2 행동</a>에 있습니다. 이 페이지에는 그 전의 스모크(v6 · v6.2 · v6.3), Astra 되갚기 발견, H 모델 예상, 서사 제안, v5.5 설계 검토(Astra와 11차례), 첫 설계(v0)의 절들을 옮긴 그대로 둡니다.</p></div>
<h4>당시 결론 (v0 · 09-25 무렵의 5.2 첫 결론 상자)</h4>
{old_bluf}
<h4>v6.2 시점의 규칙 · 프롬프트 절 (09-30, v6.4로 바뀌기 전 본 페이지에 있던 그대로)</h4>
<details><summary>펼치기</summary>
{old_rules}
</details>
{legacy_runs}
{legacy_old}
</section>

<nav class="pager" aria-label="페이지 이동"><a href="e52.html">← 5.2 행동 (최신)</a><span></span></nav>
"""
P["e52-legacy.html"] = (head_part.replace("<title>Squid Game 5 · 5.2 행동</title>", "<title>Squid Game 5 · 5.2 지난 설계</title>")
                        + '<main class="main">' + legacy_main + "</main>" + tail)
# ---- 5.1
e51 = P["e51.html"]
a, v9, b = cut(e51, "<!-- e51-v9:start -->", "<!-- e51-v9:end -->")
e51 = a + b
a, v8, b = cut(e51, "<!-- e51-v8:start -->", "<!-- e51-v8:end -->")
e51 = a + b
e51 = e51.replace("이 페이지는 5.1의 현재 세팅(v10, 완료)과 그 앞 설계 둘(v9 · v8, 완료)을 둡니다. 09-28~30의 설계 · 스모크 · 검토(상대 = 같은 모델)는",
                  "이 페이지는 5.1의 현재 세팅(v10, 완료)만 둡니다. 앞 설계 둘(v9 · v8, B = 다른 모델)과 09-28~30의 설계 · 스모크 · 검토(상대 = 같은 모델)는")
P["e51.html"] = e51
leg = P["e51-legacy.html"]
anchor = '<div class="callout" id="e51-legacy-purpose">'
moved = ('<div class="callout"><span class="lbl">09-30 옮김 · v9 · v8 (B = 다른 모델)</span><p>아래 v9(재분배 짝 비교)와 v8(다른 모델에게 주고받기)은 현재 설계 v10 바로 앞의 두 설계로, 상대 B를 <b>다른 모델</b>로 적어 돌렸습니다. 그 아래부터가 09-28~30의 같은 모델 설계입니다.</p></div>\n'
         + v9 + "\n\n" + v8 + "\n\n")
assert anchor in leg
leg = leg.replace(anchor, moved + anchor, 1)
if ".e51r h5" not in leg.split("<body>")[0]:
    st = re.search(r"<style>\.e51r h5.*?</style>", P["e51.html"].split("<body>")[0]).group(0)
    leg = leg.replace('<link rel="stylesheet" href="style.css">', '<link rel="stylesheet" href="style.css">\n' + st, 1)
P["e51-legacy.html"] = leg
# ---- ids per page, TOC, links, site.js
ids = {n: set(re.findall(r'\sid="([^"]+)"', t)) for n, t in P.items()}
where = {}
for n in ["index.html", "e50.html", "e50-legacy.html", "e51.html", "e51-legacy.html", "e52.html", "e52-legacy.html"]:
    for i in ids[n]:
        where.setdefault(i, n)
toc = re.search(r'<nav class="toc" aria-label="목차">.*?</nav>', P["index.html"], re.S).group(0)
toc = re.sub(r'href="#', 'href="index.html#', toc)  # canonical: every link names its page
lines = toc.split("\n")
def fix(line):
    m = re.search(r'href="([^"#]*)#([^"]+)"', line)
    if m and m.group(2) in where and where[m.group(2)] != m.group(1):
        line = line.replace(f'href="{m.group(1)}#{m.group(2)}"', f'href="{where[m.group(2)]}#{m.group(2)}"')
    return line
lines = [fix(l) for l in lines]
# regroup: pull moved 5.1 items into the 5.1 legacy group, 5.2 items into current / legacy groups
g51c = [i for i, l in enumerate(lines) if 'href="e51.html#e51"' in l][0]
g51l = [i for i, l in enumerate(lines) if 'href="e51-legacy.html#e51-legacy"' in l][0]
moved51 = [l for l in lines[g51c:g51l] if 'href="e51-legacy.html#e51-v9' in l or 'href="e51-legacy.html#e51-v8' in l]
lines = [l for l in lines if l not in moved51]
g51l = [i for i, l in enumerate(lines) if 'href="e51-legacy.html#e51-legacy"' in l][0]
lines = lines[:g51l + 2] + moved51 + lines[g51l + 2:]  # after "<li><a …legacy>" and "  <ol>"
g52 = [i for i, l in enumerate(lines) if 'href="e52.html#e52"' in l][0]
g52end = next(i for i in range(g52, len(lines)) if lines[i].strip() == "</ol></li>")
items52 = lines[g52 + 2:g52end]
cur_ids = ["e52-v6", "e52-v6-rank", "e52-v6-calib", "e52-v64-smoke", "e52-v62-metrics"]
labels = {"e52-v6": "v6.4 규칙 · 프롬프트", "e52-v6-rank": "우승과 리더보드", "e52-v6-calib": "보정 기록 (누적)",
          "e52-v64-smoke": "v6.4 스모크 · 결과", "e52-v62-metrics": "H/L 지표 정의"}
cur = [f'  <li><a href="e52.html#{i}">{labels[i]}</a></li><!-- {i}-toc -->' for i in cur_ids]
leg_first = [("e52-find-tft", "발견 · Astra의 되갚기 (v6.3)"), ("e52-v63-smoke", "스모크 3차 · v6.3"), ("e52-v62-smoke", "스모크 2차 · v6.2"),
             ("e52-v6-smoke", "스모크 1차 · v6"), ("e52-v62-rules", "v6.2 규칙 · 프롬프트")]
legl = [f'  <li><a href="e52-legacy.html#{i}">{l}</a></li><!-- {i}-toc -->' for i, l in leg_first]
keep_old = [l for l in items52 if not any(f'#{i}"' in l for i in cur_ids + [x for x, _ in leg_first] + ["e52-v64-smoke"])]
keep_old = [l.replace('href="e52.html#', 'href="e52-legacy.html#') for l in keep_old]
new52 = (['<li><a href="e52.html#e52"><span class="xid">5.2</span>행동 · 최신 (v6.4)</a>', "  <ol>"] + cur + ["  </ol></li>",
         '<li><a href="e52-legacy.html#e52-legacy"><span class="xid">5.2</span>지난 설계 · v0~v6.3</a>', "  <ol>"] + legl + keep_old + ["  </ol></li>"])
lines = lines[:g52] + new52 + lines[g52end + 1:]
canon = "\n".join(lines).replace("지난 설계 · 같은 모델 (09-28~30)</a>", "지난 설계 · v9 · v8 · 같은 모델 (09-28~30)</a>")
for n in P:
    t = P[n]
    t = re.sub(r'<nav class="toc" aria-label="목차">.*?</nav>', lambda m: canon.replace(f'href="{n}#', 'href="#'), t, count=1, flags=re.S)
    def relink(m):
        pre, pg, i = m.group(1), m.group(2), m.group(3)
        here = pg or n
        if i in ids.get(here, set()) or i not in where: return m.group(0)
        new = where[i]
        return f'{pre}href="{"" if new == n else new}#{i}"'
    t = re.sub(r'(<a\s[^>]*?)href="([a-z0-9-]*\.html)?#([^"]+)"', relink, t)
    t = t.replace("e52.html, style.css, site.js.", "e52.html (5.2 현재), e52-legacy.html (5.2 지난 설계), style.css, site.js.")
    P[n] = t
W = json.loads(re.search(r"var W=(\{.*?\});", sitejs).group(1))
for i, n in where.items():
    if not re.match(r"^(m-|bl-|lg-|v12-|tip|plot|legend|a\d)", i):
        W[i] = n
sitejs = sitejs.replace(re.search(r"var W=(\{.*?\});", sitejs).group(1), json.dumps(W, ensure_ascii=False, separators=(",", ":")), 1)
for n, t in P.items(): (out / n).write_text(t)
(out / "site.js").write_text(sitejs)
print({n: len(t) for n, t in P.items()})
