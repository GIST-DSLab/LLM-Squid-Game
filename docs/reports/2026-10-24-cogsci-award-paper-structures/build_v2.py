#!/usr/bin/env python3
"""Slim 2026-10-27 page: award definition + selection criteria, stacked share bars, per-paper ToC.

Reads papers/P*.json (award set), papers/T*.json (Tenenbaum set), citations.json, ours*.json and
summary_v2.json (definition / criteria lines).  Writes ../2026-10-24-cogsci-award-paper-structures.html (replaces the build.py page).
Role colouring reuses build.role_of so both pages classify sections the same way.
"""
from __future__ import annotations

import html
import json
from pathlib import Path

import build  # same folder: ROLES, role_of, body_sections, fmt_share

HERE = Path(__file__).resolve().parent
OUT = HERE.parent / "2026-10-24-cogsci-award-paper-structures.html"
esc = build.esc


def load(prefix: str) -> list[dict]:
    ps = [json.loads(p.read_text(encoding="utf-8")) for p in sorted((HERE / "papers").glob(f"{prefix}*.json"))]
    award_rank = lambda a: 0 if "marr" in str(a).lower() else 1
    ps.sort(key=lambda p: (-int(str(p["year"])[:4]), award_rank(p.get("award")), str(p.get("award"))))
    return ps


def cites() -> dict:
    f = HERE / "citations.json"
    return json.loads(f.read_text(encoding="utf-8")) if f.exists() else {"papers": {}}


def short(p: dict) -> str:
    a = p["authors"][0] if p.get("authors") else "?"
    last = a.replace("*", "").split()[-1]
    return f"{last} {str(p['year'])[:4]}"


def award_short(a: str) -> str:
    a = str(a)
    if "marr" in a.lower():
        return "Marr Prize"
    for k, v in (("applied", "CMP 응용 인지"), ("higher", "CMP 고차 인지"), ("language", "CMP 언어"),
                 ("perception", "CMP 지각·행동")):
        if k in a.lower():
            return v
    return a


def roles(p: dict) -> list[tuple[str, str, float]]:
    out = []
    for s in build.body_sections(p):
        sh = float(s.get("share") or 0)
        if sh > 0:
            out.append((s.get("role") or build.role_of(s["title"], p["id"]), s["title"], sh))
    return out


def bar(segs: list[tuple[str, str, float]], with_pct: bool = True) -> str:
    h = []
    for r, t, sh in segs:
        lab = f"{t} {round(sh * 100)}%" if with_pct else t
        h.append(f'<span class="seg {r}" style="flex:{sh:.4f}" title="{esc(t)} · {round(sh * 100)}%"><i>{esc(lab)}</i></span>')
    return f'<div class="sbar">{"".join(h)}</div>'


def mean_segs(ps: list[dict]) -> list[tuple[str, str, float]]:
    labels = {k: lab for k, lab, _ in build.ROLES}
    acc = {k: 0.0 for k in labels}
    for p in ps:
        tot = sum(sh for _, _, sh in roles(p)) or 1
        for r, _, sh in roles(p):
            if r in acc:
                acc[r] += sh / tot
    return [(k, labels[k], acc[k] / len(ps)) for k in labels]


def cite_txt(pid: str, C: dict) -> str:
    c = C.get("papers", {}).get(pid) or {}
    o, s = c.get("openalex"), c.get("s2")
    if o is None and s is None:
        return "—"
    return f"{o if o is not None else '—'} / {s if s is not None else '—'}"


def row(label: str, segs, cls: str = "", title: str = "", cite: str = "", href: str = "") -> str:
    lab = f'<a href="#{href}">{esc(label)}</a>' if href else esc(label)
    return (f'<div class="srow {cls}"><span class="lab" title="{esc(title)}">{lab}</span>'
            f'<span class="cit">{esc(cite)}</span>{bar(segs)}</div>')


def toc(p: dict) -> str:
    items = []

    def walk(n: dict, depth: int) -> None:
        lv = int(n.get("level", depth))
        if lv > 2:
            return
        sh = n.get("share")
        pct = f'<span class="pc">{round(float(sh) * 100)}%</span>' if (lv == 1 and sh not in (None, "")) else ""
        pg = n.get("page_start")
        pgs = f'<span class="pp">p.{esc(pg)}</span>' if pg not in (None, "") else ""
        r = build.role_of(n["title"], p["id"]) if lv == 1 else ""
        items.append(f'<li class="lv{lv} {r}">{esc(n["title"])}{pct}{pgs}</li>')
        for c in n.get("children") or []:
            walk(c, depth + 1)

    for s in p["sections"]:
        if build.is_body(s):
            walk(s, 1)
    return f'<ul class="toc">{"".join(items)}</ul>'


def card(p: dict, C: dict, tag: str) -> str:
    return (f'<article id="{esc(p["id"])}"><header><span class="k">{esc(short(p))}</span>'
            f'<span class="aw">{esc(tag)}</span><span class="ct">피인용 {esc(cite_txt(p["id"], C))}</span></header>'
            f'<h4><a href="{esc(p.get("url_page", ""))}">{esc(p["title"])}</a></h4>{toc(p)}</article>')


def main() -> None:
    S = json.loads((HERE / "summary_v2.json").read_text(encoding="utf-8"))
    A, T, C = load("P"), load("T"), cites()
    ours = []
    for f, lab in (("ours.json", "우리 원고 10-23"), ("ours_2026-10-27.json", "우리 원고 10-27")):
        fp = HERE / f
        if fp.exists():
            o = json.loads(fp.read_text(encoding="utf-8"))
            ours.append((lab, [(s["role"], s["title"], float(s["share"])) for s in o["sections"]]))
    bars = ['<h3>CogSci 수상작 ' + str(len(A)) + '편</h3><div class="sbars">',
            row(f"수상작 {len(A)}편 평균", mean_segs(A), "mean")]
    bars += [row(short(p), roles(p), "", f'{p["title"]} · {p.get("award", "")}', cite_txt(p["id"], C), p["id"]) for p in A]
    bars += ['</div><h3>Tenenbaum 공저 ' + str(len(T)) + '편</h3><div class="sbars">',
             row(f"Tenenbaum {len(T)}편 평균", mean_segs(T), "mean")]
    bars += [row(short(p), roles(p), "", p["title"], cite_txt(p["id"], C), p["id"]) for p in T]
    bars += ['</div><h3>우리 원고</h3><div class="sbars">'] + [row(l, s, "ours") for l, s in ours] + ['</div>']
    cards_a = "".join(card(p, C, f"{p['year']} · {award_short(p.get('award', ''))}") for p in A)
    cards_t = "".join(card(p, C, f"{p['year']} · Tenenbaum 공저") for p in T)
    legend = "".join(f'<span class="{k}">{lab}</span>' for k, lab, _ in build.ROLES)
    crit = "".join(f"<li>{x}</li>" for x in S["criteria"])
    page = TEMPLATE.format(define=S["define"], crit=crit, legend=legend, bars="\n".join(bars),
                           cards_a=cards_a, cards_t=cards_t, retrieved=esc(C.get("retrieved", "")),
                           n=len(A))
    OUT.write_text(page, encoding="utf-8")
    print("wrote", OUT, len(A), "award +", len(T), "tenenbaum")


TEMPLATE = """<title>CogSci 수상작 구조</title>
<meta name="claude:viewport-fit-sides" content="cover">
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Noto+Serif+KR:wght@600;700&family=Noto+Sans+KR:wght@400;500;600&display=swap">
<style>
/* Layout: one column; criteria → stacked bars (label · citations · bar) → per-paper ToC cards in a two-column grid. */
:root{{--bg:#f7f7f4;--surface:#fff;--fg:#1d2129;--mute:#5d6470;--line:#d9dbd3;--accent:#2f5d8a;
  --intro:#c9d7e8;--method:#d6e4c8;--result:#f1dcb3;--disc:#e5cfd9;--other:#e2e2dc;
  --display:"Noto Serif KR","Apple SD Gothic Neo",serif;--body:"Noto Sans KR","Apple SD Gothic Neo",system-ui,sans-serif}}
@media (prefers-color-scheme: dark){{:root:not([data-theme="light"]){{--bg:#15181d;--surface:#1d2127;--fg:#e8e9e4;--mute:#a2a8b3;--line:#343941;--accent:#8fb6dd;
  --intro:#2e4664;--method:#3a5230;--result:#6a5422;--disc:#5a3a4c;--other:#3a3d42;color-scheme:dark}}}}
:root[data-theme="dark"]{{--bg:#15181d;--surface:#1d2127;--fg:#e8e9e4;--mute:#a2a8b3;--line:#343941;--accent:#8fb6dd;
  --intro:#2e4664;--method:#3a5230;--result:#6a5422;--disc:#5a3a4c;--other:#3a3d42;color-scheme:dark}}
body{{background:var(--bg);color:var(--fg);font-family:var(--body);font-size:15px;line-height:1.6;
  padding-left:max(16px,env(safe-area-inset-left,0px));padding-right:max(16px,env(safe-area-inset-right,0px));padding-block:32px 72px}}
main{{max-width:1040px;margin:0 auto}}
h1,h2{{font-family:var(--display);text-wrap:balance;line-height:1.3}}
h1{{font-size:clamp(26px,3.6vw,36px);margin:0 0 12px}}
h2{{font-size:1.3rem;margin:2.4rem 0 .7rem;padding-top:1rem;border-top:1px solid var(--line)}}
h3{{font-size:.82rem;letter-spacing:.06em;color:var(--mute);margin:1.4rem 0 .4rem;font-weight:700}}
a{{color:var(--accent)}}
.define{{background:var(--surface);border-left:3px solid var(--accent);padding:10px 14px;margin:0 0 10px;max-width:80ch}}
ul.crit{{margin:0;padding-left:1.1em;max-width:80ch;display:grid;gap:3px;font-size:14px}}
.legend{{display:flex;flex-wrap:wrap;gap:6px 16px;font-size:13px;color:var(--mute);margin:12px 0 4px}}
.legend span::before{{content:"";display:inline-block;width:.9em;height:.9em;margin-right:.35em;vertical-align:-.1em;border:1px solid var(--line)}}
.legend .intro::before,.seg.intro{{background:var(--intro)}} .legend .method::before,.seg.method{{background:var(--method)}}
.legend .result::before,.seg.result{{background:var(--result)}} .legend .disc::before,.seg.disc{{background:var(--disc)}}
.seg.other{{background:var(--other)}}
.sbars{{display:grid;gap:6px}}
.srow{{display:grid;grid-template-columns:8.5em 5.5em 1fr;align-items:center;gap:8px;min-width:0}}
.srow .lab{{font-size:13px}} .srow .lab a{{color:var(--fg);text-decoration:none}} .srow .lab a:hover{{color:var(--accent)}}
.srow .cit{{font-size:12px;color:var(--mute);font-variant-numeric:tabular-nums;text-align:right}}
.srow.mean .lab,.srow.ours .lab{{font-weight:600}} .srow.mean{{margin-bottom:6px}}
.srow.ours .sbar{{outline:2px solid var(--accent);outline-offset:1px}}
.sbar{{display:flex;height:26px;border:1px solid var(--line);overflow:hidden;min-width:0}}
.sbar .seg{{display:block;min-width:0;overflow:hidden;white-space:nowrap;font-size:11.5px;line-height:24px;padding:0 .3em;color:var(--fg)}}
.sbar .seg i{{font-style:normal}}
.note{{font-size:12.5px;color:var(--mute);margin:.5rem 0 0}}
.cards{{display:grid;grid-template-columns:repeat(auto-fill,minmax(300px,1fr));gap:12px}}
article{{background:var(--surface);border:1px solid var(--line);padding:12px 14px;min-width:0}}
article header{{display:flex;flex-wrap:wrap;gap:4px 10px;align-items:baseline;font-size:12.5px;color:var(--mute)}}
article .k{{font-weight:700;color:var(--fg);font-size:13.5px}} article .ct{{margin-left:auto;font-variant-numeric:tabular-nums}}
article h4{{font-size:14px;margin:4px 0 8px;line-height:1.4;font-weight:600}} article h4 a{{color:var(--fg);text-decoration:none}}
ul.toc{{list-style:none;margin:0;padding:0;font-size:13px}}
ul.toc li{{display:flex;gap:6px;align-items:baseline;padding:1px 0}}
ul.toc li.lv1{{font-weight:600;border-top:1px solid var(--line);padding-top:3px;margin-top:2px}}
ul.toc li.lv1::before{{content:"";flex:none;width:.7em;height:.7em;border:1px solid var(--line);align-self:center}}
ul.toc li.lv1.intro::before{{background:var(--intro)}} ul.toc li.lv1.method::before{{background:var(--method)}}
ul.toc li.lv1.result::before{{background:var(--result)}} ul.toc li.lv1.disc::before{{background:var(--disc)}} ul.toc li.lv1.other::before{{background:var(--other)}}
ul.toc li.lv2{{padding-left:1.3em;color:var(--mute);font-weight:400}}
ul.toc .pc{{margin-left:auto;font-variant-numeric:tabular-nums}} ul.toc .pp{{color:var(--mute);font-weight:400;font-size:12px;min-width:2.6em;text-align:right}}
ul.toc li.lv2 .pp{{margin-left:auto}}
@media (max-width:640px){{.srow{{grid-template-columns:1fr auto;gap:2px 8px}} .srow .sbar{{grid-column:1/-1}}}}
</style>
<main>
<h1>CogSci 수상작 구조</h1>
<p class="define">{define}</p>
<ul class="crit">{crit}</ul>
<h2>섹션 비율</h2>
<div class="legend">{legend}</div>
<p class="note">숫자 칸은 피인용수(OpenAlex / Semantic Scholar, {retrieved} 기준). 막대는 1수준 절별 본문 단어 비율(그림·표·캡션·참고문헌 제외). 이름을 누르면 아래 목차로 간다.</p>
{bars}
<h2>논문별 목차 · 수상작 {n}편</h2>
<div class="cards">{cards_a}</div>
<h2>논문별 목차 · Tenenbaum 공저</h2>
<div class="cards">{cards_t}</div>
</main>
"""

if __name__ == "__main__":
    main()
