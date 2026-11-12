#!/usr/bin/env python3
"""Render docs/reports/2026-10-24-cogsci-award-paper-structures.html from papers/P*.json.

Each JSON was produced by a reading agent from the eScholarship PDF of one
award-winning CogSci paper (heading outline, per-section word counts, figures,
abstract + Korean translation).  summary.json holds the hand-written synthesis
shown at the top of the page.  Run:  python build.py
"""
from __future__ import annotations

import html
import json
import re
from pathlib import Path

HERE = Path(__file__).resolve().parent
OUT = HERE.parent / "2026-10-24-cogsci-award-paper-structures.html"

ROLES = [
    ("intro", "서론·배경", ("introduction", "background", "related", "prior", "motivat", "overview")),
    ("method", "방법·모델", ("method", "model", "material", "participant", "procedure", "task", "approach",
                          "framework", "formal", "theor", "simulation", "design", "stimul", "data set",
                          "dataset", "paradigm", "algorithm", "setup", "corpus", "measure")),
    ("result", "실험·결과", ("experiment", "study", "result", "analysis", "evaluation", "finding",
                          "comparison", "predict", "fit", "validation", "performance")),
    ("disc", "논의·결론", ("discussion", "conclusion", "limitation", "future", "implication", "summary",
                        "outlook")),
]
ROLE_INDEX = {k: i for i, (k, _, _) in enumerate(ROLES)}

# Section titles that name a topic rather than a role; classified by reading the paper.
ROLE_OVERRIDES = {
    ("P08", "Inverse inverse planning"): "result",    # method + both behavioural experiments + demos
    ("P10", "Persistent Disagreement"): "intro",      # background theory before the experiments
    ("P06", "Preliminaries"): "method",               # formal setup and the three candidate models
    ("P11", "Related Work"): "intro",
}


def esc(s: object) -> str:
    return html.escape(str(s if s is not None else ""), quote=True)


def role_of(title: str, pid: str = "") -> str:
    if (pid, title) in ROLE_OVERRIDES:
        return ROLE_OVERRIDES[(pid, title)]
    t = title.lower()
    for key, _label, needles in ROLES:
        if any(n in t for n in needles):
            return key
    return "other"


def load_papers(prefix: str = "P") -> list[dict]:
    """P*.json = the ten award papers; T*.json = the Tenenbaum co-authored set (kept out of the award means)."""
    papers = []
    for p in sorted((HERE / "papers").glob(f"{prefix}*.json")):
        with p.open(encoding="utf-8") as f:
            papers.append(json.load(f))
    # newest year first, Marr Prize before the modeling prizes
    papers.sort(key=lambda d: (-int(d["year"]), 0 if "Marr" in d["award"] else 1, d["id"]))
    return papers


def load_ours() -> dict | None:
    f = HERE / "ours.json"
    if not f.exists():
        return None
    with f.open(encoding="utf-8") as fh:
        return json.load(fh)


# later manuscript versions (ours_<version>.json): shown as extra bars only; ours.json stays the compared base
OURS_LATER: list[dict] = []


def load_ours_later() -> list[dict]:
    out = []
    for f in sorted(HERE.glob("ours_*.json")):
        with f.open(encoding="utf-8") as fh:
            out.append(json.load(fh))
    return out


def ours_label(p: dict) -> str:
    v = p.get("version") or "2026-10-23"
    return f"우리 원고 {v[5:]}"


def ours_rows(ours: dict, bar_fn, href: str = "") -> str:
    """Base manuscript row plus one row per later version, in the cmprow layout."""
    def lab(p: dict, h: str) -> str:
        return f'<a href="#{h}">{esc(ours_label(p))}</a>' if h else esc(ours_label(p))
    rows = [f'<div class="cmprow"><span class="lab">{lab(ours, href)}</span>{bar_fn(ours)}</div>']
    rows += [f'<div class="cmprow"><span class="lab">{lab(o, "")}</span>{bar_fn(o)}</div>' for o in OURS_LATER]
    return "".join(rows)


def load_summary() -> dict:
    with (HERE / "summary.json").open(encoding="utf-8") as f:
        return json.load(f)


def fmt_share(x: float | None) -> str:
    return "" if x is None else f"{round(100 * x)}%"


BACK_MATTER = ("acknowledg", "reference", "appendix", "supplement")


def is_body(section: dict) -> bool:
    t = section["title"].lower()
    return not any(b in t for b in BACK_MATTER)


def body_sections(paper: dict) -> list[dict]:
    return [s for s in paper["sections"] if is_body(s)]


def text_pages(paper: dict) -> object:
    return paper.get("pages_text_before_references") or paper.get("text_pages") or paper.get("pages_body")


def _row(node: dict, depth: int) -> str:
    lv = min(int(node.get("level", depth)), 4)
    pg = node.get("page_start")
    pg_txt = f"p.{pg}" if pg not in (None, "") else ""
    share = fmt_share(node.get("share")) if lv == 1 else ""
    return (f'<tr class="lv{lv}"><td class="t">{esc(node.get("title"))}</td>'
            f'<td class="n">{pg_txt}</td><td class="n">{esc(node.get("words", ""))}</td>'
            f'<td class="n">{share}</td></tr>')


def section_rows(sections: list[dict]) -> str:
    rows: list[str] = []

    def walk(node: dict, depth: int) -> None:
        rows.append(_row(node, depth))
        for c in node.get("children") or []:
            walk(c, depth + 1)

    for s in sections:
        walk(s, 1)
    return "\n".join(rows)


def share_bar(paper: dict) -> str:
    """Stacked bar of level-1 section shares, coloured by role."""
    segs = []
    for s in body_sections(paper):
        sh = s.get("share") or 0
        if sh <= 0:
            continue
        r = s.get("role") or role_of(s["title"], paper["id"])
        segs.append(
            f'<span class="seg {r}" style="flex:{sh:.4f}" title="{esc(s["title"])} · {fmt_share(sh)}">'
            f'<i>{esc(s["title"])}</i></span>'
        )
    return f'<div class="bar">{"".join(segs)}</div>'


def role_totals(paper: dict) -> dict[str, float]:
    tot: dict[str, float] = {k: 0.0 for k, _, _ in ROLES}
    tot["other"] = 0.0
    for s in body_sections(paper):
        tot[s.get("role") or role_of(s["title"], paper["id"])] += s.get("share") or 0
    return tot


def count_subheads(paper: dict) -> tuple[int, int]:
    """(level-1 body sections, all lower-level headings under them)."""
    def deep(node: dict) -> int:
        kids = node.get("children") or []
        return len(kids) + sum(deep(k) for k in kids)
    secs = body_sections(paper)
    return len(secs), sum(deep(s) for s in secs)


def paper_card(p: dict, k: int, tag: str = "") -> str:
    ours = p.get("id") == "OURS"
    unit = p.get("unit", "단어")
    l1, l2 = count_subheads(p)
    obs = p.get("observations", {})
    fin_subs = obs.get("final_section_subheadings") or []
    fin_subs_txt = " · ".join(fin_subs) if fin_subs else "없음"
    figs = p.get("figures") or []
    tabs = p.get("tables") or []
    n_figs = len(figs) or p.get("figures_count", 0)
    n_tabs = len(tabs) or p.get("tables_count", 0)
    fig_list = "".join(
        f'<li>Fig. {esc(f.get("n"))} · p.{esc(f.get("page"))} · {esc(f.get("size"))} · {esc(f.get("section"))}</li>'
        for f in figs
    )
    tab_list = "".join(
        f'<li>Table {esc(t.get("n"))} · p.{esc(t.get("page"))} · {esc(t.get("size"))} · {esc(t.get("section"))}</li>'
        for t in tabs
    )
    authors = ", ".join(p.get("authors") or [])
    return f"""
<article class="paper{' ours' if ours else ''}" id="{esc(p["id"]).lower()}">
  <header>
    <div class="eyebrow"><span class="k">{'우리' if ours else f'{tag}{k:02d}'}</span> {'우리 원고 · ' + esc(p["award"]) if ours else 'CogSci ' + esc(p["year"]) + ' · ' + esc(p["award"])}</div>
    <h3>{esc(p["title"])}</h3>
    {'' if ours else f'<p class="meta">{esc(authors)}<br><span class="aff">{esc(p.get("affiliations", ""))}</span></p>'}
    <p class="src">{'원고: ' + esc(p["url_page"]) + ' · PDF ' + esc(p["url_pdf"]) if ours else
      '출처: <a href="' + esc(p["url_page"]) + '" target="_blank" rel="noopener">' + esc(p["url_page"]) + '</a> · <a href="' + esc(p["url_pdf"]) + '" target="_blank" rel="noopener">PDF</a>'
      + (' · <span class="note">' + esc(p["pdf_source_note"]) + '</span>' if p.get("pdf_source_note") and p["pdf_source_note"] != "eScholarship" else "")}</p>
  </header>

  <section class="abs">
    <h4>{'초록' if ours else '초록 (한국어 번역)'}</h4>
    <p>{esc(p["abstract_ko"])}</p>
    {'' if ours else '<details><summary>영어 원문</summary><p class="en">' + esc(p["abstract_en"]) + '</p></details>'}
  </section>

  <section class="layout">
    <h4>분량</h4>
    <dl class="facts">
      <div><dt>본문 글</dt><dd>{esc(text_pages(p))}쪽 · 약 {esc(p.get("words_body_total"))}{unit} (PDF {esc(p.get("pages_body"))}쪽{'' if ours else ', 표지 제외'})</dd></div>
      <div><dt>참고문헌</dt><dd>{esc(p.get("references_location"))}</dd></div>
      <div><dt>그 밖에</dt><dd>{esc(p.get("extras") or "—")}</dd></div>
      <div><dt>절 수</dt><dd>1수준 {l1} · 2수준 이하 {l2}</dd></div>
      <div><dt>그림·표</dt><dd>그림 {n_figs} · 표 {n_tabs}</dd></div>
    </dl>
    {share_bar(p)}
  </section>

  <section class="toc">
    <h4>목차 (제목 · 시작 쪽 · {unit} 수 · 본문 비율)</h4>
    <div class="scroll"><table class="outline">
      <thead><tr><th>제목</th><th>쪽</th><th>{unit}</th><th>비율</th></tr></thead>
      <tbody>{section_rows(p["sections"])}</tbody>
    </table></div>
  </section>

  <section class="obs">
    <h4>제목 짜임새</h4>
    <ul class="kv">
      <li><b>서론 소제목</b> {"있음" if obs.get("intro_subheadings") else "없음"}</li>
      <li><b>관련 연구 절</b> {"따로 있음" if obs.get("related_work_section") else "없음(서론에 녹임)"}</li>
      <li><b>실험을 1수준 절로</b> {"나눔" if obs.get("experiments_as_top_level") else "나누지 않음"}</li>
      <li><b>마지막 절 이름</b> {esc(obs.get("final_section_name"))}</li>
      <li><b>마지막 절 소제목</b> {esc(fin_subs_txt)}</li>
      <li><b>결론 문단으로 끝남</b> {"예" if obs.get("ends_with_conclusion_paragraph") else "아니오"}</li>
      <li><b>모델·형식 설명 위치</b> {esc(obs.get("model_description_location"))}</li>
      <li><b>첫 쪽 사용</b> {esc(obs.get("first_page_use"))}</li>
      <li><b>링크</b> {esc(obs.get("links") or "—")}</li>
    </ul>
    {'' if ours else '<h4>그림·표 위치</h4><ul class="figs">' + fig_list + tab_list + '</ul><h4>구조 읽기</h4><p class="summary">' + esc(p.get("structure_summary_ko")) + '</p>'}
  </section>
</article>"""


def overview_table(papers: list[dict], ours: dict | None = None, tag: str = "") -> str:
    rows = []
    items = ([(0, ours)] if ours else []) + list(enumerate(papers, 1))
    for k, p in items:
        l1, l2 = count_subheads(p)
        obs = p.get("observations", {})
        secs = body_sections(p)
        fin = secs[-1]["title"] if secs else ""
        fin_subs = obs.get("final_section_subheadings") or []
        rows.append(
            f'<tr{" class=\"ours\"" if k == 0 else ""}><td class="n">{"우리" if k == 0 else f"{tag}{k:02d}"}</td>'
            f'<td><a href="#{esc(p["id"]).lower()}">{esc(p["title"])}</a>'
            f'<div class="sub">{esc(p["year"])} · {esc(p["award"])}</div></td>'
            f'<td class="n">{esc(text_pages(p))} / {esc(p.get("pages_body"))}</td>'
            f'<td class="n">{l1} / {l2}</td>'
            f'<td class="n">{len(p.get("figures") or []) or p.get("figures_count", 0)} / {len(p.get("tables") or []) or p.get("tables_count", 0)}</td>'
            f'<td>{"예" if obs.get("intro_subheadings") else "—"}</td>'
            f'<td>{"예" if obs.get("experiments_as_top_level") else "—"}</td>'
            f'<td>{esc(fin)}{(" <span class=\"sub\">(" + esc(" · ".join(fin_subs)) + ")</span>") if fin_subs else ""}</td>'
            f'<td class="barcell">{share_bar(p)}</td></tr>'
        )
    return "\n".join(rows)


def role_means(papers: list[dict]) -> list[tuple[str, float]]:
    acc = {k: 0.0 for k, _, _ in ROLES}
    acc["other"] = 0.0
    for p in papers:
        for k, v in role_totals(p).items():
            acc[k] += v
    n = len(papers) or 1
    labels = {k: lab for k, lab, _ in ROLES}
    labels["other"] = "기타"
    return [(labels[k], acc[k] / n) for k in list(acc)]


def _median(xs: list[float]) -> float:
    xs = sorted(xs)
    n = len(xs)
    return xs[n // 2] if n % 2 else (xs[n // 2 - 1] + xs[n // 2]) / 2


def compare_block(papers: list[dict], ours: dict) -> str:
    """Side-by-side numbers: the ten award papers vs our manuscript."""
    labels = {k: lab for k, lab, _ in ROLES}
    n = len(papers)
    role_mean = {k: sum(role_totals(p)[k] for p in papers) / n for k in labels}
    role_ours = role_totals(ours)
    l1s = [count_subheads(p)[0] for p in papers]
    l2s = [count_subheads(p)[1] for p in papers]
    o_l1, o_l2 = count_subheads(ours)
    intro = [next(s["share"] for s in body_sections(p) if "intro" in s["title"].lower()) for p in papers]
    last = [body_sections(p)[-1]["share"] for p in papers]
    o_secs = body_sections(ours)
    o_intro = o_secs[0]["share"]
    o_last = o_secs[-1]["share"]
    figs = [len(p["figures"]) for p in papers]
    tabs = [len(p["tables"]) for p in papers]
    words = [p["words_body_total"] for p in papers]
    rng = lambda xs: f"{min(xs)}–{max(xs)}"
    pct = lambda x: f"{round(100 * x)}%"
    n_intro_sub = sum(bool(p["observations"].get("intro_subheadings")) for p in papers)
    n_rel = sum(bool(p["observations"].get("related_work_section")) for p in papers)
    n_fin_sub = sum(bool(p["observations"].get("final_section_subheadings")) for p in papers)
    n_concl = sum(1 for p in papers if "conclusion" in body_sections(p)[-1]["title"].lower())
    o_fin_subs = ours["observations"].get("final_section_subheadings") or []
    rows = [
        ("본문 글이 끝나는 쪽", f"6쪽 ({n}/{n}편, 모두 6쪽을 꽉 채움)", f"{ours['text_pages']}쪽 (왼쪽 단까지; 참고문헌이 p.6 오른쪽 단에서 시작)"),
        ("본문 길이", f"{min(words):,}–{max(words):,}단어 (중앙값 {int(_median(words)):,})", f"{ours['words_body_total']:,}어절 (단위가 달라 길이는 직접 비교 불가)"),
        ("1수준 절 수", f"{rng(l1s)} (중앙값 {int(_median(l1s))})", f"{o_l1}"),
        ("2수준 이하 소제목 수", f"{rng(l2s)} (중앙값 {int(_median(l2s))})", f"{o_l2} (모두 2수준)"),
        ("서론·배경 비율 (서론 + 관련 연구·배경 절)", pct(role_mean["intro"]), pct(role_ours["intro"])),
        ("  그중 Introduction 절만", f"{pct(min(intro))}–{pct(max(intro))} (중앙값 {pct(_median(intro))})", pct(o_intro)),
        ("방법·모델 비율", pct(role_mean["method"]), pct(role_ours["method"]) + " (아레나 규칙 + 평가 지표)"),
        ("실험·결과 비율", pct(role_mean["result"]), pct(role_ours["result"])),
        ("논의·결론 비율", pct(role_mean["disc"]), pct(role_ours["disc"])),
        ("  그중 마지막 절만", f"{pct(min(last))}–{pct(max(last))} (중앙값 {pct(_median(last))})", pct(o_last)),
        ("서론 소제목", f"{n_intro_sub}/{n}편", "없음"),
        ("별도 관련 연구 절", f"{n_rel}/{n}편", f"있음 (2수준 {len(o_secs[1]['children'])}개)"),
        ("마지막 절 소제목", f"{n_fin_sub}/{n}편", f"{len(o_fin_subs)}개: " + " · ".join(o_fin_subs)),
        ("Conclusion을 1수준 절로", f"{n_concl}/{n}편 (모두 1문단)", "아니오 (종합 논의 안의 2수준 '결론')"),
        ("그림 / 표", f"{rng(figs)} / {rng(tabs)} (중앙값 {int(_median(figs))} / {int(_median(tabs))})", f"{ours['figures_count']} / {ours['tables_count']}"),
    ]
    trs = "".join(f'<tr><td class="t">{esc(a)}</td><td>{esc(b)}</td><td class="o">{esc(c)}</td></tr>' for a, b, c in rows)
    return f"""
<h4>우리 원고와 비교</h4>
<div class="cmpbars">
  <div class="cmprow"><span class="lab">수상작 10편 평균</span>{share_bar_mean(papers)}</div>
  {ours_rows(ours, share_bar)}
</div>
<p class="lede">비교 대상은 {esc(ours["award"])}. 절별 어절 수를 tex에서 세고(그림·표·캡션 제외) 비율로 바꿨다. 위 막대는 1수준 절 단위이며 아래 표는 그 비율과 짜임새를 수상작과 나란히 둔 것.{" 10-23 줄 바로 아래 " + ", ".join(esc(ours_label(o)) for o in OURS_LATER) + " 막대는 같은 방식으로 센 새 판이며 표는 바꾸지 않았다." if OURS_LATER else ""}</p>
<div class="scroll"><table class="cmp">
<thead><tr><th>항목</th><th>수상작 10편</th><th>우리 원고</th></tr></thead>
<tbody>{trs}</tbody>
</table></div>
"""


def share_bar_mean(papers: list[dict]) -> str:
    means = role_means(papers)
    keys = [k for k, _, _ in ROLES] + ["other"]
    segs = "".join(
        f'<span class="seg {k}" style="flex:{v:.4f}"><i>{esc(lab)} {round(100*v)}%</i></span>'
        for (lab, v), k in zip(means, keys) if v > 0
    )
    return f'<div class="bar mean">{segs}</div>'


def _first_author(p: dict) -> str:
    a = (p.get("authors") or ["?"])[0].replace("*", "").replace("†", "").strip()
    return a.split()[-1]


def volume_block(award: list[dict], tenen: list[dict], ours: dict | None) -> str:
    """Every paper's level-1 share bar stacked in one place, so the spending can be compared at a glance."""
    def row(lab: str, bar: str, href: str = "", cls: str = "") -> str:
        lab_html = f'<a href="#{href}">{esc(lab)}</a>' if href else esc(lab)
        return f'<div class="cmprow{cls}"><span class="lab">{lab_html}</span>{bar}</div>'

    def bar(p: dict) -> str:
        segs = []
        for s in body_sections(p):
            sh = s.get("share") or 0
            if sh <= 0:
                continue
            r = s.get("role") or role_of(s["title"], p["id"])
            segs.append(f'<span class="seg {r}" style="flex:{sh:.4f}" title="{esc(s["title"])} · {fmt_share(sh)}">'
                        f'<i>{esc(s["title"])} {fmt_share(sh)}</i></span>')
        return f'<div class="bar">{"".join(segs)}</div>'

    def group(title: str, papers: list[dict], tag: str) -> str:
        rows = [row(f"{len(papers)}편 평균", share_bar_mean(papers), cls=" mean")]
        rows += [row(f"{tag}{k:02d} {_first_author(p)} {p['year']}", bar(p), p["id"].lower())
                 for k, p in enumerate(papers, 1)]
        return f'<h4>{esc(title)}</h4><div class="cmpbars vol">{"".join(rows)}</div>'

    parts = []
    if ours:
        parts.append(f'<h4>우리 원고</h4><div class="cmpbars vol">{ours_rows(ours, bar, "ours")}</div>')
    parts.append(group(f"수상작 {len(award)}편", award, ""))
    if tenen:
        parts.append(group(f"Tenenbaum 참여 {len(tenen)}편", tenen, "T"))
    return f"""
<h2 id="volume">분량 비교</h2>
<p class="lede">논문마다 1수준 절이 본문 단어 수의 몇 %를 쓰는지 한 줄 막대로 모았다. 색은 절의 역할, 칸 안 글자는 절 제목과 비율(칸이 좁으면 마우스를 올리면 보임). 이름을 누르면 그 논문 정리로 간다.</p>
<div class="legend"><span class="intro">서론·배경</span><span class="method">방법·모델</span><span class="result">실험·결과</span><span class="disc">논의·결론</span><span class="other">기타</span></div>
{"".join(parts)}
"""


def tenenbaum_block(award: list[dict], tenen: list[dict], tsum: dict, ours: dict | None) -> str:
    """Separate section for the Tenenbaum co-authored papers; award-paper means stay untouched."""
    pts = "".join(f"<li>{esc(x)}</li>" for x in tsum.get("common", []))
    ours_row = ours_rows(ours, share_bar) if ours else ""
    cards = "\n".join(paper_card(p, k, "T") for k, p in enumerate(tenen, 1))
    return f"""
<h2 id="tenenbaum">Tenenbaum 참여 논문 {len(tenen)}편</h2>
<p class="lede">{esc(tsum.get("lede", ""))}</p>
<h4>공통으로 보이는 특징</h4>
<ul class="points">{pts}</ul>
<h4>구조 비교 (1수준 절 역할별 평균)</h4>
<div class="cmpbars">
  <div class="cmprow"><span class="lab">수상작 {len(award)}편 평균</span>{share_bar_mean(award)}</div>
  <div class="cmprow"><span class="lab">Tenenbaum {len(tenen)}편 평균</span>{share_bar_mean(tenen)}</div>
  {ours_row}
</div>
<div class="scroll"><table class="overview">
<thead><tr><th class="n">#</th><th>논문</th><th class="n">글/PDF 쪽</th><th class="n">절 1/2수준</th><th class="n">그림/표</th><th>서론 소제목</th><th>실험을 절로</th><th>마지막 절 (소제목)</th><th>분량 비율</th></tr></thead>
<tbody>{overview_table(tenen, tag="T")}</tbody>
</table></div>
{cards}
"""


def render(papers: list[dict], summary: dict, ours: dict | None = None, tenen: list[dict] | None = None) -> str:
    tenen = tenen or []
    means = role_means(papers)
    mean_bar = "".join(
        f'<span class="seg {k}" style="flex:{v:.4f}"><i>{esc(lab)} {round(100*v)}%</i></span>'
        for (lab, v), k in zip(means, [k for k, _, _ in ROLES] + ["other"]) if v > 0
    )
    pts = "".join(f"<li>{esc(x)}</li>" for x in summary["common"])
    shape = "".join(f"<li><b>{esc(x[0])}</b> {esc(x[1])}</li>" for x in summary["shape"])
    cards = "\n".join(paper_card(p, k) for k, p in enumerate(papers, 1))
    cmp_html = compare_block(papers, ours) if ours else ""
    ours_card = paper_card(ours, 0) if ours else ""
    srcs = "".join(
        f'<li>{esc(", ".join(p["authors"]))} ({esc(p["year"])}). {esc(p["title"])}. '
        f'<i>Proceedings of the Annual Meeting of the Cognitive Science Society</i>. {esc(p["award"])}. '
        f'<a href="{esc(p["url_page"])}" target="_blank" rel="noopener">{esc(p["url_page"])}</a></li>'
        for p in papers + tenen
    )
    tenen_html = tenenbaum_block(papers, tenen, summary.get("tenenbaum", {}), ours) if tenen else ""
    n_head = f"CogSci 수상작 {len(papers)}편 · Tenenbaum {len(tenen)}편 구조" if tenen else f"CogSci 수상작 구조 {len(papers)}편"
    award_srcs = "".join(
        f'<li><a href="{esc(u)}" target="_blank" rel="noopener">{esc(u)}</a> — {esc(d)}</li>'
        for u, d in summary["award_sources"]
    )
    return f"""<!doctype html>
<html lang="ko">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<title>{esc(n_head)}</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Noto+Sans+KR:wght@400;500;700&family=Noto+Serif+KR:wght@600;700&family=IBM+Plex+Mono:wght@400;500&display=swap">
<style>
/* layout: one reading column; summary first, then a scannable table, then one card per paper */
:root {{
  --bg: #f7f7f4; --surface: #ffffff; --fg: #1d2129; --muted: #5d6470; --line: #d9dbd3;
  --accent: #2f5d8a; --accent-ink: #ffffff;
  --intro: #c9d7e8; --method: #d6e4c8; --result: #f1dcb3; --disc: #e5cfd9; --other: #e2e2dc;
  --display: "Noto Serif KR", "Apple SD Gothic Neo", serif;
  --body: "Noto Sans KR", "Apple SD Gothic Neo", system-ui, sans-serif;
  --mono: "IBM Plex Mono", ui-monospace, Menlo, monospace;
}}
@media (prefers-color-scheme: dark) {{ :root:not([data-theme="light"]) {{
  --bg: #15181d; --surface: #1d2127; --fg: #e8e9e4; --muted: #a2a8b3; --line: #343941;
  --accent: #8fb6dd; --accent-ink: #10131a;
  --intro: #2e4664; --method: #3a5230; --result: #6a5422; --disc: #5a3a4c; --other: #3a3d42; color-scheme: dark }} }}
:root[data-theme="dark"] {{
  --bg: #15181d; --surface: #1d2127; --fg: #e8e9e4; --muted: #a2a8b3; --line: #343941;
  --accent: #8fb6dd; --accent-ink: #10131a;
  --intro: #2e4664; --method: #3a5230; --result: #6a5422; --disc: #5a3a4c; --other: #3a3d42; color-scheme: dark }}
* {{ box-sizing: border-box }}
html, body {{ margin: 0 }}
body {{ background: var(--bg); color: var(--fg); font-family: var(--body); font-size: 15px; line-height: 1.65;
  padding-block: 32px 64px; padding-left: max(16px, env(safe-area-inset-left, 0px)); padding-right: max(16px, env(safe-area-inset-right, 0px)) }}
main {{ max-width: 980px; margin: 0 auto }}
h1, h2, h3 {{ font-family: var(--display); text-wrap: balance; line-height: 1.3 }}
h1 {{ font-size: 2rem; margin: 0 0 .25rem }}
h2 {{ font-size: 1.35rem; margin: 2.5rem 0 .75rem; padding-top: 1rem; border-top: 1px solid var(--line) }}
h3 {{ font-size: 1.15rem; margin: .25rem 0 .4rem }}
h4 {{ font-size: .8rem; letter-spacing: .06em; text-transform: uppercase; color: var(--muted); margin: 1.1rem 0 .35rem; font-weight: 700 }}
p {{ margin: .3rem 0 .6rem }}
a {{ color: var(--accent) }}
.lede {{ color: var(--muted); max-width: 70ch }}
.num {{ font-family: var(--mono); font-variant-numeric: tabular-nums }}
ul.points {{ padding-left: 1.2em; max-width: 78ch }}
ul.points li {{ margin: .35rem 0 }}
ul.shape {{ list-style: none; padding: 0; display: grid; gap: .5rem; grid-template-columns: repeat(auto-fit, minmax(260px, 1fr)) }}
ul.shape li {{ background: var(--surface); border: 1px solid var(--line); padding: .7rem .9rem; border-radius: 4px; min-width: 0 }}
ul.shape b {{ display: block; color: var(--accent) }}
.legend {{ display: flex; flex-wrap: wrap; gap: .5rem 1rem; font-size: .82rem; color: var(--muted); margin: .4rem 0 }}
.legend span::before {{ content: ""; display: inline-block; width: .9em; height: .9em; margin-right: .35em; vertical-align: -.1em; border: 1px solid var(--line) }}
.legend .intro::before {{ background: var(--intro) }} .legend .method::before {{ background: var(--method) }}
.legend .result::before {{ background: var(--result) }} .legend .disc::before {{ background: var(--disc) }} .legend .other::before {{ background: var(--other) }}
.bar {{ display: flex; width: 100%; height: 22px; border: 1px solid var(--line); overflow: hidden; margin-top: .5rem; min-width: 0 }}
.bar .seg {{ display: block; min-width: 0; overflow: hidden; white-space: nowrap; font-size: .68rem; line-height: 20px; padding: 0 .3em; color: var(--fg) }}
.bar .seg i {{ font-style: normal }}
.seg.intro {{ background: var(--intro) }} .seg.method {{ background: var(--method) }} .seg.result {{ background: var(--result) }}
.seg.disc {{ background: var(--disc) }} .seg.other {{ background: var(--other) }}
.bar.mean {{ height: 28px }} .bar.mean .seg {{ line-height: 26px; font-size: .8rem }}
.scroll {{ overflow-x: auto }}
table {{ border-collapse: collapse; width: 100%; font-size: .88rem }}
th, td {{ text-align: left; vertical-align: top; padding: .4rem .5rem; border-bottom: 1px solid var(--line) }}
th {{ font-size: .75rem; letter-spacing: .05em; text-transform: uppercase; color: var(--muted) }}
td.n, th.n {{ font-family: var(--mono); font-variant-numeric: tabular-nums; white-space: nowrap }}
.overview td .sub {{ font-size: .78rem; color: var(--muted) }}
.overview td.barcell {{ min-width: 180px }}
.overview tr.ours td {{ background: color-mix(in srgb, var(--accent) 10%, var(--surface)); font-weight: 500 }}
.cmpbars {{ display: grid; gap: .4rem; margin: .4rem 0 }}
.cmprow {{ display: grid; grid-template-columns: 9em 1fr; align-items: center; gap: .6rem; min-width: 0 }}
.cmprow .lab {{ font-size: .82rem; color: var(--muted) }}
.cmprow .bar {{ margin-top: 0; height: 26px }} .cmprow .bar .seg {{ line-height: 24px; font-size: .74rem }}
table.cmp td.t {{ white-space: pre-wrap; font-weight: 500 }} table.cmp td.o {{ background: color-mix(in srgb, var(--accent) 8%, var(--surface)) }}
article.paper.ours {{ border-color: var(--accent); box-shadow: inset 4px 0 0 var(--accent) }}
.cmpbars.vol {{ gap: .3rem }} .cmpbars.vol .cmprow {{ grid-template-columns: 11em 1fr }}
.cmpbars.vol .lab a {{ color: var(--fg); text-decoration: none; font-family: var(--mono); font-size: .78rem }}
.cmpbars.vol .lab a:hover {{ color: var(--accent); text-decoration: underline }}
.cmpbars.vol .cmprow.mean .lab {{ font-weight: 700; color: var(--fg) }}
.cmpbars.vol .cmprow.mean {{ margin-bottom: .2rem }}
@media (max-width: 640px) {{ .cmprow, .cmpbars.vol .cmprow {{ grid-template-columns: 1fr; gap: .15rem }} }}
.overview td.barcell .bar {{ margin-top: 0; height: 16px }} .overview .bar .seg i {{ display: none }}
article.paper {{ background: var(--surface); border: 1px solid var(--line); border-radius: 6px; padding: 1.2rem 1.4rem; margin: 1.4rem 0 }}
article.paper header .eyebrow {{ font-size: .78rem; letter-spacing: .05em; text-transform: uppercase; color: var(--muted) }}
article.paper header .k {{ font-family: var(--mono); color: var(--accent); margin-right: .4em }}
.meta {{ color: var(--muted); font-size: .9rem; margin: 0 }} .aff {{ font-size: .82rem }}
.src {{ font-size: .82rem; color: var(--muted); word-break: break-all }} .src .note {{ color: var(--accent) }}
.abs p {{ max-width: 74ch }} .abs .en {{ color: var(--muted); font-size: .88rem }}
details summary {{ cursor: pointer; color: var(--accent); font-size: .85rem }}
dl.facts {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: .3rem 1rem; margin: 0; font-size: .88rem }}
dl.facts dt {{ color: var(--muted); font-size: .75rem; text-transform: uppercase; letter-spacing: .05em }} dl.facts dd {{ margin: 0 }}
table.outline tr.lv1 td.t {{ font-weight: 700 }}
table.outline tr.lv2 td.t {{ padding-left: 1.6rem }}
table.outline tr.lv3 td.t {{ padding-left: 3rem; color: var(--muted) }}
table.outline tr.lv4 td.t {{ padding-left: 4.2rem; color: var(--muted); font-style: italic }}
ul.kv, ul.figs {{ list-style: none; padding: 0; margin: 0; font-size: .88rem }}
ul.kv {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(280px, 1fr)); gap: .15rem 1rem }}
ul.kv b {{ color: var(--muted); font-weight: 500; margin-right: .4em }}
ul.figs li {{ color: var(--muted) }}
.summary {{ max-width: 74ch }}
ol.sources {{ font-size: .86rem; padding-left: 1.4em }} ol.sources li {{ margin: .3rem 0; word-break: break-word }}
ul.sources {{ font-size: .86rem; padding-left: 1.2em }}
@media (max-width: 640px) {{ body {{ font-size: 14px }} h1 {{ font-size: 1.6rem }} article.paper {{ padding: 1rem }} }}
@media (prefers-reduced-motion: no-preference) {{ a {{ transition: color .15s }} }}
a:focus-visible, summary:focus-visible {{ outline: 2px solid var(--accent); outline-offset: 2px }}
</style>
</head>
<body>
<main>
<h1>{esc(n_head)}</h1>
<p class="lede">{esc(summary["lede"])}</p>
{f'<p class="lede">수상작과 따로, Joshua B. Tenenbaum이 공저자인 CogSci 논문 {len(tenen)}편을 같은 형식으로 <a href="#tenenbaum">아래 절</a>에 정리했다. 아래 평균은 수상작 {len(papers)}편만으로 낸 값이다.</p>' if tenen else ''}

<h2>핵심</h2>
<h4>공통으로 보이는 특징</h4>
<ul class="points">{pts}</ul>
<h4>좋은 논문의 구조 (10편 평균)</h4>
<div class="legend"><span class="intro">서론·배경</span><span class="method">방법·모델</span><span class="result">실험·결과</span><span class="disc">논의·결론</span><span class="other">기타</span></div>
<div class="bar mean">{mean_bar}</div>
<p class="lede">1수준 절 제목을 역할별로 묶어 본문 단어 수 비율을 평균한 값. 실험 절(Experiment 1, Study 2 …)은 그 안의 방법·결과를 모두 "실험·결과"로 셈.</p>
<ul class="shape">{shape}</ul>
{cmp_html}
{volume_block(papers, tenen, ours)}

<h2>한눈에 보기</h2>
<div class="scroll"><table class="overview">
<thead><tr><th class="n">#</th><th>논문</th><th class="n">글/PDF 쪽</th><th class="n">절 1/2수준</th><th class="n">그림/표</th><th>서론 소제목</th><th>실험을 절로</th><th>마지막 절 (소제목)</th><th>분량 비율</th></tr></thead>
<tbody>{overview_table(papers, ours)}</tbody>
</table></div>

<h2>논문별 정리</h2>
{ours_card}
{cards}
{tenen_html}

<h2>출처</h2>
<h4>논문</h4>
<ol class="sources">{srcs}</ol>
<h4>수상 목록</h4>
<ul class="sources">{award_srcs}</ul>
<p class="lede">{esc(summary["method_note"])}</p>
{f'<p class="lede">{esc(summary["tenenbaum"]["selection_note"])}</p>' if tenen and summary.get("tenenbaum", {}).get("selection_note") else ''}
</main>
</body>
</html>
"""


def main() -> None:
    papers = load_papers()
    summary = load_summary()
    ours = load_ours()
    tenen = load_papers("T")
    OURS_LATER[:] = load_ours_later()
    OUT.write_text(render(papers, summary, ours, tenen), encoding="utf-8")
    print(f"wrote {OUT} ({OUT.stat().st_size:,} bytes, {len(papers)} + {len(tenen)} papers)")


if __name__ == "__main__":
    main()
