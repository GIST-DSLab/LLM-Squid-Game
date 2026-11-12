#!/usr/bin/env python3
"""Measure our CogSci manuscript (paper/cogsci2027/ko) the same way the award papers were measured.

Counts 어절 (whitespace tokens) per \\section / \\subsection in the body sections listed in
content.tex before \\printbibliography, excluding comments, floats (figure/table), captions,
labels and citation commands.  Page starts come from pdftotext of the latest no-appendix PDF.
Writes ours.json (or ours_<version>.json) next to this script.  Run:  python ours.py [version]
Earlier versions stay frozen in their JSON; only re-run the version whose manuscript you measure.
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
KO = REPO / "paper" / "cogsci2027" / "ko"
DIST = REPO / "paper" / "dist"

VERSIONS = {
    "2026-10-23": {
        "pdf": DIST / "ko_cogsci2027_2026-10-23_no_appendix.pdf", "out": "ours.json",
        "label": "CogSci 2027 한국어판 원고, 2026-10-23 no-appendix 빌드",
        "body": ["01_introduction", "02_related_work", "03_arena", "04_evaluation", "06_results", "07_discussion"],
        "abstract": "00_abstract",
        "roles": {"서론": "intro", "관련 연구": "intro", "LLM Squid Game: 공존 아레나": "method", "평가": "method",
                  "결과": "result", "종합 논의": "disc"},
        "related_work": True,
        "model_loc": "아레나 규칙은 독립 1수준 절 'LLM Squid Game: 공존 아레나'(2수준 넷), 지표는 '평가' 절(2수준 넷)",
        "first_page": "제목 · 초록 · 서론 · 관련 연구 첫 소절까지 1쪽",
    },
    "2026-10-26": {
        "pdf": DIST / "ko_cogsci2027_2026-10-26.pdf", "out": "ours_2026-10-26.json",
        "label": "CogSci 2027 한국어판 원고, 2026-10-26 빌드",
        "body": ["r1_introduction", "r2_arena", "r3_analysis", "r4_discussion"],
        "abstract": "r0_abstract",
        # '아레나' holds both prior work and design/metrics; counted as method like the old arena + evaluation pair
        "roles": {"서론": "intro", "아레나": "method", "분석": "result", "논의 및 결론": "disc"},
        "related_work": False,
        "model_loc": "독립 1수준 절 '아레나' 안 2수준 '선행 연구와 우리 의도' · '설계와 지표'",
        "first_page": "제목 · 초록 · 서론이 1쪽",
    },
    "2026-10-27": {
        "pdf": DIST / "ko_cogsci2027_2026-10-27_no_appendix.pdf", "out": "ours_2026-10-27.json",
        "label": "CogSci 2027 한국어판 원고, 2026-10-27 빌드",
        "body": ["01_introduction", "02_arena", "03_analysis", "04_discussion"],
        "abstract": "00_abstract",
        "roles": {"서론": "intro", "아레나": "method", "분석": "result", "논의 및 결론": "disc"},
        "related_work": False,
        "model_loc": "독립 1수준 절 '아레나' 안 2수준 '선행 연구와 우리 의도' · '설계와 지표'",
        "first_page": "제목 · 초록 · 서론이 1쪽",
    },
}


def strip_tex(src: str) -> tuple[str, int, int]:
    """Return (plain text, n_figures, n_tables) for one section file."""
    src = re.sub(r"(?<!\\)%.*", "", src)
    n_fig = len(re.findall(r"\\begin\{figure\*?\}", src))
    n_tab = len(re.findall(r"\\begin\{table\*?\}", src))
    src = re.sub(r"\\begin\{(figure|table)\*?\}.*?\\end\{\1\*?\}", " ", src, flags=re.S)
    src = re.sub(r"\\(label|ref|cite[tp]?|eqref|input|includegraphics|begin|end)\*?(\[[^\]]*\])?\{[^}]*\}", " ", src)
    src = re.sub(r"\\begin\{equation\*?\}.*?\\end\{equation\*?\}", " EQN ", src, flags=re.S)
    src = re.sub(r"\$[^$]*\$", " M ", src)              # inline math counts as one token
    src = re.sub(r"\\[a-zA-Z]+\*?(\[[^\]]*\])?", " ", src)  # remaining commands
    src = re.sub(r"[{}]", " ", src)
    return src, n_fig, n_tab


def count(text: str) -> int:
    return len(text.split())


def parse_file(name: str) -> dict:
    src = (KO / "sections" / f"{name}.tex").read_text(encoding="utf-8")
    src_nc = re.sub(r"(?<!\\)%.*", "", src)
    sec = re.search(r"\\section\*?\{([^}]*)\}", src_nc)
    title = sec.group(1)
    body = src_nc[sec.end():]
    parts = re.split(r"\\subsection\*?\{([^}]*)\}", body)
    lead, _, _ = strip_tex(parts[0])
    children = []
    figs = tabs = 0
    for i in range(1, len(parts), 2):
        txt, f, t = strip_tex(parts[i + 1])
        figs += f
        tabs += t
        children.append({"level": 2, "title": clean_title(parts[i]), "words": count(txt)})
    _, f0, t0 = strip_tex(parts[0])
    figs += f0
    tabs += t0
    total = count(lead) + sum(c["words"] for c in children)
    return {"level": 1, "title": clean_title(title), "words": total, "lead_words": count(lead),
            "children": children, "figures": figs, "tables": tabs}


def clean_title(t: str) -> str:
    t = re.sub(r"\\textcolor\{[^}]*\}", "", t)
    t = re.sub(r"\$\\rho\$", "ρ", t)
    t = re.sub(r"\\[a-zA-Z]+", "", t)
    return re.sub(r"\s+", " ", t.replace("{", "").replace("}", "")).strip()


def page_index(pdf: Path) -> list[str]:
    n = int(re.search(r"Pages:\s+(\d+)", subprocess.run(["pdfinfo", str(pdf)], capture_output=True, text=True).stdout).group(1))
    pages = []
    for i in range(1, n + 1):
        out = subprocess.run(["pdftotext", "-f", str(i), "-l", str(i), "-layout", str(pdf), "-"], capture_output=True, text=True).stdout
        pages.append(out)
    return pages


def find_page(pages: list[str], title: str, start: int = 1) -> int | None:
    """First page >= start where the heading stands alone on a line (or a column of one)."""
    key = re.sub(r"\s*ρ$", "", title.split("(")[0]).strip()
    key = re.sub(r"[?？]$", "", key).strip()
    pat = re.compile(r"(^|\s{2,})" + re.escape(key) + r"\S*(\s{2,}|\s*$)", re.M)
    for i, p in enumerate(pages, 1):
        if i >= start and pat.search(p):
            return i
    return None


def main() -> None:
    version = sys.argv[1] if len(sys.argv) > 1 else "2026-10-23"
    cfg = VERSIONS[version]
    PDF = cfg["pdf"]
    pages = page_index(PDF)
    sections = [parse_file(n) for n in cfg["body"]]
    total = sum(s["words"] for s in sections)
    ROLE = cfg["roles"]
    cur = 1
    for s in sections:
        s["share"] = round(s["words"] / total, 3)
        s["role"] = ROLE[s["title"]]
        s["page_start"] = find_page(pages, s["title"], cur) or cur
        cur = s["page_start"]
        for c in s["children"]:
            c["page_start"] = find_page(pages, c["title"], cur) or cur
            cur = c["page_start"]
    abs_txt, _, _ = strip_tex((KO / "sections" / f"{cfg['abstract']}.tex").read_text(encoding="utf-8"))
    refs_page = next((i for i, p in enumerate(pages, 1) if re.search(r"^\s*References(\s{2,}|\s*$)", p, re.M)), None)
    body_end = max((x["page_start"] or 0) for s in sections for x in [s, *s["children"]])
    # appendix pages after the references are not part of the paper length
    app = next((i for i, p in enumerate(pages, 1) if refs_page and i > refs_page and re.match(r"\s*A\s+부록", p)), None)
    n_pages = (app - 1) if app else len(pages)
    out = {
        "id": "OURS", "version": version, "year": 2027, "award": cfg["label"],
        "title": "생존이 걸린 토큰을 언어 모델은 어떻게 나누는가",
        "authors": [], "affiliations": "",
        "url_page": "paper/cogsci2027/ko/", "url_pdf": str(PDF.relative_to(REPO)), "pdf_source_note": "로컬 빌드",
        "abstract_ko": " ".join(abs_txt.split()),
        "pages_body": n_pages, "text_pages": body_end,
        "references_location": f"p.{refs_page}부터 (본문과 같은 쪽에서 시작)" if refs_page else "",
        "extras": "감사의 글 있음. 부록(보조 실험 · 사례)은 제출 때 보충 자료로 옮길 예정이라 제외." + (f" PDF는 부록 포함 {len(pages)}쪽." if app else ""),
        "words_body_total": total, "unit": "어절",
        "sections": [{k: v for k, v in s.items() if k not in ("figures", "tables")} for s in sections],
        "figures_count": sum(s["figures"] for s in sections), "tables_count": sum(s["tables"] for s in sections),
        "figures": [], "tables": [],
        "observations": {
            "intro_subheadings": False, "related_work_section": cfg["related_work"], "experiments_as_top_level": False,
            "final_section_name": sections[-1]["title"],
            "final_section_subheadings": [c["title"] for c in sections[-1]["children"]],
            "ends_with_conclusion_paragraph": True,
            "model_description_location": cfg["model_loc"],
            "first_page_use": cfg["first_page"],
            "links": "",
        },
        "structure_summary_ko": "",
    }
    (HERE / cfg["out"]).write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"total {total} 어절, pdf {len(pages)} pages, body ends p.{body_end}, refs p.{refs_page}")
    for s in sections:
        print(f"  {s['title']:<28} p.{s['page_start']}  {s['words']:>5}  {s['share']:.0%}  fig {s['figures']} tab {s['tables']}")
        for c in s["children"]:
            print(f"      {c['title']:<26} p.{c['page_start']}  {c['words']:>5}")


if __name__ == "__main__":
    main()
