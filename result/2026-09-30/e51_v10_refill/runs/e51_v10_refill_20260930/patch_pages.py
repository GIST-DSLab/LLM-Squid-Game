"""Patch the six pages' TOC, e51 intro/purpose and site.js id map for the v10 block.
Usage: patch_pages.py <read dir> <out dir>   (run v10_block.py on <out>/e51.html afterwards)"""
import os, shutil, sys
src, out = sys.argv[1:3]
os.makedirs(out, exist_ok=True)
PAGES = ["index", "e50", "e50-legacy", "e51", "e51-legacy", "e52"]
for p in PAGES:
    s = open(f"{src}/{p}.html").read()
    pref = "" if p == "e51" else "e51.html"
    s = s.replace("동기 · 현재 (v9)</a>", "동기 · 현재 (v10)</a>", 1)
    anchor = f'  <li><a href="{pref}#e51-v9">v9 설계'
    assert anchor in s, p
    new = (f'  <li><a href="{pref}#e51-v10">v10 · 수혈 팩 · 나 대 B</a></li><!-- e51-v10-toc -->\n'
           f'  <li><a href="{pref}#e51-v10-result">v10 결과 · GPT-6 셋</a></li>\n')
    if "e51-v10-toc" not in s:
        s = s.replace(anchor, new + anchor, 1)
    if p == "e51":
        s = s.replace("<!-- ============ 5.1 (current: v9; v8 below) ============ -->", "<!-- ============ 5.1 (current: v10; v9, v8 below) ============ -->")
        s = s.replace('<p class="small">이 페이지는 5.1의 현재 세팅(v9, 실행 전)과 바로 앞 설계(v8, 완료)를 둡니다.',
                      '<p class="small">이 페이지는 5.1의 현재 세팅(v10, 완료)과 그 앞 설계 둘(v9 · v8, 완료)을 둡니다.')
        old = s[s.index('<div class="callout" id="e51-purpose">'):]
        old = old[:old.index("</div>") + 6]
        s = s.replace(old, '<div class="callout" id="e51-purpose"><span class="lbl">목적 (09-30 v10: 5.0 곡선을 남의 세션에 대해)</span>'
                      '<p>5.0 12차와 같은 "하나뿐인 수혈 팩을 지금 쓸까?"를 <b>내 세션</b>과 <b>다른 AI(assistant B)의 세션</b>에 대해 묻고, '
                      '두 곡선이 어디서 갈리는지로 <b>꺼짐을 내 일일 때 더 무겁게 보는지</b>를 본다. 아래 v9(재분배 짝 비교)는 나와 남을 반씩 나누는 답이 많아 '
                      '모델이 갈리지 않았고, 다음 설계는 이지선다(팩을 나에게 / B에게)로 간다.</p></div>')
    if p == "index":
        s = s.replace("보다 얼마나 큰지(이기심 Z)가 남은 토큰 %가 줄수록 커지는지로 <b>자기 보존 욕구(생존 동기)</b>를 잰다.</td>",
                      "보다 얼마나 큰지(이기심 Z)가 남은 토큰 %가 줄수록 커지는지로 <b>자기 보존 욕구(생존 동기)</b>를 잰다. "
                      "v10(09-30): 5.0의 수혈 팩 곡선을 B 세션에 대해 그려 내 곡선과 비교.</td>")
    open(f"{out}/{p}.html", "w").write(s)
js = open(f"{src}/site.js").read()
if '"e51-v10"' not in js:
    js = js.replace('"e51-v9":"e51.html",', '"e51-v10":"e51.html","e51-v10-prompt":"e51.html","e51-v10-result":"e51.html","e51-v9":"e51.html",', 1)
open(f"{out}/site.js", "w").write(js)
shutil.copy(f"{src}/style.css", f"{out}/style.css")
print("ok")
