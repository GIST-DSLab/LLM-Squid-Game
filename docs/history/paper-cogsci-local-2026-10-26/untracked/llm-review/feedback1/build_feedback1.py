"""Merge the Fable 5.1 and GPT-6 Astra readability reviews and the team lead's (승필) feedback into one PDF.

Output layout (every page is 1312 pt wide, landscape):
  1. 종합 평가   both reviewers' scores, one-line diagnoses and Fable's overall notes in one place
  1-2. 승필 팀장 피드백  who gave it, the three questions verbatim, and where each piece of advice sits
  2. 논문 p.1-7  each manuscript page in the middle, Fable cards on the left, Astra cards on the right,
                 both reviewers' highlights drawn on the same page; below it a purple band with the
                 Fable | Astra advice on the team lead's feedback that concerns this page (markers S1-S18)
  3. 통합 수정 로드맵  one row per spot in the manuscript, Fable | Astra side by side
Review text is copied verbatim from sources/*/annotations.json, sources/fable-review/fable_review.md and
sources/seungpil-review/seungpil-review.md (split into pieces by manuscript spot; every line is used once).

Run:  python3 build_feedback1.py   (needs xelatex, pandoc, PyMuPDF >= 1.23)
"""
import html
import json
import re
import subprocess
import tempfile
from pathlib import Path

import fitz

HERE = Path(__file__).resolve().parent
SRC = HERE / "sources"
OUT = HERE / "feedback1_ko_cogsci2027_review_fable_astra.pdf"
PAPER = SRC / "ko_cogsci2027_2026-10-23_no_appendix.pdf"
FONT_DIR = Path.home() / "Library/Fonts"
FONT_REG, FONT_BOLD = "NanumGothic-Regular.ttf", "NanumGothic-Bold.ttf"  # the .otf maps · and … to other code points

# page geometry (pt)
W, H_MIN = 1312, 838
BAND = 30
LX0, LX1 = 14, 332           # Fable card column
PX0, PY0 = 350, 38           # manuscript page origin (612 x 792)
RX0, RX1 = 980, 1298         # Astra card column
CARD_GAP = 6

REV = {
    "F": dict(key="fable", name="Fable 5.1", label="FABLE 5.1 리뷰", rgb=(0.76, 0.25, 0.05), hex="C2410C",
              hl=(0.98, 0.62, 0.30), light=(1.0, 0.93, 0.87),
              ann=SRC / "fable-review/annotations.json", md=SRC / "fable-review/fable_review.md"),
    "A": dict(key="astra", name="GPT-6 Astra", label="ASTRA 리뷰 (GPT-6 Astra)", rgb=(0.06, 0.46, 0.43), hex="0F766E",
              hl=(0.25, 0.75, 0.68), light=(0.88, 0.97, 0.95),
              ann=SRC / "astra-review/annotations.json"),
}
PRIORITY = {"highest": "★ 최우선", "high": "▲ 중요", "normal": "일반"}
PRIORITY_ORDER = {"highest": 0, "high": 1, "normal": 2}
CATEGORY = {"content": ("내용", (0.99, 0.84, 0.84)), "structure": ("구조", (0.82, 0.90, 0.99)),
            "sentence": ("문장", (1.0, 0.93, 0.70))}

# Scores exactly as each reviewer wrote them (Fable: fable_review.md table; Astra: one_line_diagnosis).
SCORES = [("1. 논리적 작성", "논리", 72, 78), ("2. 두괄식 핵심 노출", "두괄식", 68, 82),
          ("3. 비전문가 가독성", "비전문가 접근성", 58, 65), ("4. 문장 가독성", "문장 가독성", 64, 73),
          ("5. 사람다움", "자연스러움", 78, 77)]
TOTAL = (68, 75)

# Rationale sentences from the score page of Fable's original review PDF (p.2), verbatim.
FABLE_PDF_SCORE_NOTES = {
    "head": "Fable 5.1 리뷰 · 2026-10-23 · 점수는 편집적 판단이며, 사람다움 점수는 높을수록 사람이 쓴 글처럼 읽힌다는 뜻이다.",
    "rows": [
        "서론→설계→지표→결과의 뼈대는 맞다. '목표 추구'를 재는 지표가 끝까지 명시되지 않고, 관련 연구의 차별점 문장 하나(p.2 '단, 협력을 목표로…')가 문법적으로 끊겨 반대로 읽힌다.",
        "서론 첫 문장과 분배 전략 절 첫 문장은 좋다. 결과 절 첫 문장이 부정 진술이고, 글의 통찰('한 번의 선택이 아니라 여러 라운드의 조정')이 6쪽 종합 논의에 처음 나온다.",
        "틱·시드·solver·시그널·여유를 정의 없이 쓴다. 왜 '오징어 게임'인지는 서론 한 줄뿐이다. 결과 본문이 표 1~4의 숫자를 다시 옮겨 적는다.",
        "능동태·단문이라 리듬은 좋다. 같은 rho를 '자기보존 지표'와 '상대적 배분' 두 이름으로 부르고, token/토큰이 섞이며, 꼬인 문장이 3~4곳(p.2 Energy Society, p.6 한계) 있다.",
        "오징어 게임 1화 장면 비유, 고르지 않은 문단 길이, 구체적 유보가 사람 손을 보여준다. 'A는… B는… C는…' 반복과 서론 둘째 문단의 지나치게 고른 단문 연쇄에 기계적 윤문 흔적이 있다.",
        "다섯 항목의 단순 평균. 중심 문장(토큰 = 사고 비용 = 생존 자원 → 세 요소 충돌)을 초록·서론·아레나 절 첫머리에 세우면 1·2·3번이 함께 오른다.",
    ],
    "reading": [
        "70점 이상(초록)은 유지해도 되는 수준, 60~69점(주황)은 손보면 한 단계 오르는 수준, 60점 미만(빨강)은 비전문가 독자가 멈추는 곳이 있다는 뜻이다.",
        "다음 쪽부터 본문 위에 24건의 카드(★ 최우선 3 · ▲ 중요 10 · 일반 11)가 붙어 있고, 마지막 두 쪽에 우선순위 로드맵이 있다.",
        "최우선 3건: 초록의 rho 문장(p.1), 세 요소와 지표의 대응(p.1·p.3), 결과 절 첫 문장(p.4).",
    ],
}

# One row per spot in the manuscript. Labels are this merge's wording; ids are each review's roadmap numbers.
TOPICS = [
    ("초록의 ρ 문장 (정의와 해석)", ["F01"], ["A01", "A02"]),
    ("초록: 세 요소와 지표의 대응", ["F02"], []),
    ("초록: token / 토큰 표기", ["F14"], []),
    ("기여 (ii) 문장", ["F04"], ["A04"]),
    ("서론: 중심 문장의 위치", ["F05"], []),
    ("관련 연구: Energy Society 문장", ["F06"], []),
    ("관련 연구: 협력 지시에 관한 차별점 문장", ["F07"], ["A05"]),
    ("관련 연구: 종료 자체 / 자신의 종료", ["F15"], []),
    ("아레나 절 첫 문장", ["F08"], []),
    ("용어 정의: 틱 · 시드 · solver · TALK · SOLVE", ["F16"], ["A06"]),
    ("시그널 용어", ["F18"], []),
    ("정답 확률 범위 (지지 비율 · 1등 몫)", ["F17"], ["A07"]),
    ("Sen 지수 문단 첫 문장", [], ["A08"]),
    ("ρ 정의와 읽는 방향", ["F09"], []),
    ("여유 정의", ["F19"], []),
    ("결과 절 첫 문장", ["F03"], ["A09"]),
    ("ρ 이름 통일 (상대적 배분)", ["F20"], []),
    ("'모델의 지능' 표현", ["F21"], ["A03"]),
    ("이탈 서술", ["F22"], []),
    ("분배 전략 절: Fable 문단", ["F10", "F11"], ["A10"]),
    ("오징어 게임 1화 비유", ["F23"], []),
    ("한계: ρ 해석 범위", ["F13"], ["A11"]),
    ("결론 첫 문장", [], ["A12"]),
    ("종합 논의: 세 요소 충돌의 통찰", ["F12"], []),
    ("Fable 결과의 인과적 서술", ["F24"], []),
]
# Guards that the roadmap numbering (priority order) still matches the topics above.
EXPECT = {"F01": "자기보존은", "F03": "일치하지는", "F14": "token을", "F24": "가장높은",
          "A03": "모델의지능은", "A09": "총이전량", "A12": "우리는목표지향"}

# ---- team lead's feedback (seungpil-review.md): three questions, each answered by Fable and Astra.
SP_MD = SRC / "seungpil-review/seungpil-review.md"
SP = dict(name="승필 팀장", rgb=(0.42, 0.16, 0.60), hex="6B2999", light=(0.95, 0.91, 0.98))
SP_WHO = {"F": "Fable", "A": "Astra"}  # the names as the source file writes them
# question line, reviewer marker line before each answer, answer line range (1-based, inclusive)
SP_Q = {"Q1": dict(q=4, F=(6, 7, 39), A=(41, 42, 117)),
        "Q2": dict(q=119, F=(121, 122, 154), A=(157, 158, 255)),
        "Q3": dict(q=257, F=(259, 260, 284), A=(286, 287, 376))}
# Manuscript spots: id -> (page, label, regions). A region is (start phrase, end phrase[, column]);
# "@top" / "@bottom" stand for the top / bottom of the column's text.
SP_ANCHORS = {
    1: (1, "제목 · 초록", [("LLM오징어게임:생존게임에서", "차이가관찰되었다.")]),
    2: (1, "서론 (문제 · 세 요소의 충돌 · 제안)", [("서론", "처럼동료"), ("가서로의존속을돕는", "구체적인기여는다음과같다.")]),
    3: (1, "서론: 기여 (i)–(iii)", [("(i)여러AI가", "행동을비교한다.")]),
    4: (1, "관련 연구: 공존의 정의 · 자원을 나누는 환경", [("관련연구", "넘기는것은다르다.")]),
    5: (2, "관련 연구: Energy Society", [("EnergySociety는이문제를", "구분할수없다.")]),
    6: (2, "관련 연구: TBSP", [("다른문제로,종료를피한", "개선할여지가남아있다.")]),
    7: (2, "아레나 절: 참여자 · 한 게임 · 한 라운드", [("LLMSquidGame:공존아레나", "@bottom"),
                                                ("EnergySociety에서는생존에너지를", "같은틱에전달된")]),
    8: (3, "아레나: TALK 운영 세부", [("응답사이지연공개는없으며", "다른자리가맡는다."), ("대화방은모", "대화가이어진다.")]),
    9: (3, "그림 2 · 시그널 게임", [("TALK에서보는상태와이력", "Figure2:단계와역할에따라모델이받는정보이다."),
                             ("시그널게임은단서20개", "@bottom"), ("@top", "그림3은한번의SOLVE를보여준다.")]),
    10: (4, "평가: 협력 지표 F · A · V와 JS 거리", [("협력의빈도와이전량", "@bottom"), ("@top", "JS로비교한다.")]),
    11: (4, "결과 절 첫머리 (결과 절 전체의 구성)", [("프론티어모델5개", "남은참여자에따라달라진다.")]),
    12: (4, "결과: 어느 모델이 함께 살아남았는가? · 표 1", [("어느모델이함께살아남았는가?", "60,818(25)0.34")]),
    13: (5, "그림 4 (여유 산점도)", [("@top", "두여유가같은선이다.", "L")]),
    14: (5, "결과: 토큰을 받은 자리 · 표 2", [("토큰을받은자리도모두", "7/5/0")]),
    15: (5, "결과: 여유 1 경계 (제공자가 1 아래로 내려간 경우 없음)", [("잔량을해당", "모두없었다.")]),
    16: (5, "결과: 분배 전략 절 (모델별 문단)", [("모델들은어떤토큰분배전략을썼는가?", "@bottom"),
                                       ("맞추지않은정답과오답", "@bottom")]),
    17: (6, "종합 논의", [("종합논의", "@bottom"), ("@top", "과정도비교할수있다.")]),
    18: (6, "한계와 향후 과제", [("한계와향후과제", "살펴볼필요가있다.")]),
}
# Each answer cut into pieces in source order: (source lines, manuscript spot). Lines are 1-based ranges
# of seungpil-review.md; a piece may skip lines (table rows that belong to other spots).
SP_PIECES = {
    ("Q1", "F"): [("7", 1), ("9-15", 2), ("17-23", 1), ("25-33", 2), ("35-37", 3), ("39", 2)],
    ("Q1", "A"): [("42", 1), ("44-55", 2), ("57-73", 2), ("75-83", 4), ("85", 5), ("87-97", 3),
                  ("99-109", 1), ("111-117", 2)],
    ("Q2", "F"): [("122", 11), ("124-128", 15), ("130", 6), ("132", 16), ("134-138", 2), ("140", 4),
                  ("142", 9), ("144", 10), ("146", 11), ("148", 17), ("150-152", 16), ("154", 17)],
    ("Q2", "A"): [("158-160", 11), ("162-179", 15), ("181-194", 16), ("196-209", 11),
                  ("211-218,222-224", 2), ("219", 7), ("220", 11), ("221", 17),
                  ("226-229,235", 2), ("230", 8), ("231-232", 10), ("233-234,236", 16),
                  ("238-240", 9), ("242-255", 18)],
    ("Q3", "F"): [("260", 12), ("262-264", 12), ("266", 15), ("268", 16), ("270", 12), ("272-276", 14),
                  ("278", 1), ("280", 16), ("282", 17), ("284", 18)],
    ("Q3", "A"): [("287", 11), ("289-301", 12), ("303-319", 16), ("321-331", 11), ("333-343", 13),
                  ("345-358", 17), ("360-374", 18), ("376", 1)],
}


# ---------------------------------------------------------------- data

def load_annotations() -> dict:
    out = {}
    for p, r in REV.items():
        anns = json.loads(r["ann"].read_text())["annotations"]
        anns = sorted(anns, key=lambda a: PRIORITY_ORDER[a["priority"]])  # = original roadmap numbering
        for i, a in enumerate(anns, 1):
            a["id"], a["who"] = f"{p}{i:02d}", p
            out[a["id"]] = a
    for k, v in EXPECT.items():
        assert out[k]["phrase"].replace(" ", "").startswith(v), (k, out[k]["phrase"])
    ids = [i for _, f, a in TOPICS for i in f + a]
    assert sorted(ids) == sorted(out), "every annotation must sit in exactly one topic"
    for _, f, a in TOPICS:
        for i in f:
            out[i]["peers"] = a
        for i in a:
            out[i]["peers"] = f
    return out


def page_chars(page: fitz.Page):
    chars = []
    for b in page.get_text("rawdict")["blocks"]:
        for line in b.get("lines", []):
            for span in line["spans"]:
                for c in span["chars"]:
                    if not c["c"].isspace():
                        chars.append((c["c"], fitz.Rect(c["bbox"])))
    return chars


def locate(paper: fitz.Document, ann: dict) -> list:
    """Line rects of the phrase the reviewer anchored on (phrases are space-stripped search keys)."""
    chars = page_chars(paper[ann["page"] - 1])
    text = "".join(c for c, _ in chars)
    key = re.sub(r"\s", "", ann["phrase"])
    i = text.find(key)
    assert i >= 0, f"phrase not found: {ann['id']} {key}"
    rects = []
    for _, r in chars[i:i + len(key)]:
        if rects and abs(rects[-1].y0 - r.y0) < 2 and r.x0 - rects[-1].x1 < 12:
            rects[-1] |= r
        else:
            rects.append(fitz.Rect(r))
    return rects


def md_sections() -> dict:
    md = REV["F"]["md"].read_text(encoding="utf-8")
    parts = re.split(r"(?m)^## ", md)
    secs = {"_head": parts[0]}
    for p in parts[1:]:
        title, _, body = p.partition("\n")
        secs[title.strip()] = body.strip("\n")
    return secs


def md_items(secs: dict) -> dict:
    """fable_review.md item text keyed by Fable roadmap id (md ★1-3 and table rows 4-24 = F01-F24)."""
    items = {}
    top = next(v for k, v in secs.items() if k.startswith("최우선"))
    for m in re.finditer(r"(?ms)^### ★(\d+)\. (.+?)\n(.*?)(?=^### |\Z)", top):
        items[f"F{int(m.group(1)):02d}"] = dict(title=f"★{m.group(1)}. {m.group(2).strip()}", body=m.group(3).strip())
    for k, v in secs.items():
        if k.startswith(("중요", "일반")):
            for line in v.splitlines():
                cells = [c.strip() for c in line.strip().strip("|").split("|")]
                if len(cells) == 4 and cells[0].isdigit():
                    items[f"F{int(cells[0]):02d}"] = dict(where=cells[1], problem=cells[2], fix=cells[3])
    assert sorted(items) == [f"F{i:02d}" for i in range(1, 25)], sorted(items)
    return items


def sp_lines(spec: str) -> list:
    out = []
    for part in spec.split(","):
        a, _, b = part.partition("-")
        out += range(int(a), int(b or a) + 1)
    return out


def sp_load() -> tuple:
    """The team lead's questions and the Fable / Astra advice pieces, each piece tied to a manuscript spot."""
    lines = SP_MD.read_text(encoding="utf-8").splitlines()
    L = lambda i: lines[i - 1]
    is_row = lambda i: L(i).lstrip().startswith("|")
    is_sep = lambda i: re.fullmatch(r"\|[-:| ]+\|", L(i).strip()) is not None
    head = [L(1).strip(), L(2).strip()]
    questions = {}
    pieces = []
    for q, spec in SP_Q.items():
        questions[q] = L(spec["q"]).strip()
        assert "juhyeon" in questions[q], (q, questions[q])
        for who in "FA":
            marker, a, b = spec[who]
            assert L(marker).strip().strip("[]") == SP_WHO[who], (q, who, L(marker))
            assert all(not L(i).strip() for i in range(marker + 1, a)), (q, who)
            used = [i for spec_, _ in SP_PIECES[(q, who)] for i in sp_lines(spec_)]
            want = [i for i in range(a, b + 1) if L(i).strip()]
            assert sorted(i for i in used if L(i).strip()) == want, f"{q}-{who}: every answer line exactly once"
            plan = SP_PIECES[(q, who)]
            for k, (spec_, anchor) in enumerate(plan, 1):
                idx = sp_lines(spec_)
                while not L(idx[-1]).strip():
                    idx.pop()
                out, prev = [], None
                for i in idx:
                    if is_row(i) and not is_sep(i + 1) and not (prev is not None and is_row(prev)):
                        # first body row of a table in this piece: find that table's separator line above
                        sep = i
                        while not is_sep(sep):
                            sep -= 1
                            assert is_row(sep), (q, who, i)
                        if sep - 1 not in idx:  # table header lives in another piece: repeat it
                            out += [("\n\n" if out else "") + L(sep - 1), "\n" + L(sep)]
                            prev = sep
                    gap = "" if not out else ("\n" if prev is not None and (i == prev + 1 or is_row(i) and is_row(prev)) else "\n\n")
                    out.append(gap + L(i))
                    prev = i
                pieces.append(dict(q=q, who=who, k=k, n=len(plan), anchor=anchor, md="".join(out),
                                   src=spec_.replace("-", "–").replace(",", ", ")))
    assert {p["anchor"] for p in pieces} == set(SP_ANCHORS), "every spot carries at least one piece"
    return head, questions, pieces


def sp_html(md: str) -> str:
    # CommonMark will not close **“…”** when a Korean particle follows, so bold is converted before pandoc
    md = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", md)
    h = subprocess.run(["pandoc", "-f", "gfm", "-t", "html", "--wrap=none"],
                       input=md, capture_output=True, text=True, check=True).stdout
    # keep each link's address visible on paper
    return re.sub(r'<a href="([^"]+)">(.*?)</a>', r'<a href="\1">\2</a><span class="url"> (\1)</span>', h)


def sp_locate(paper: fitz.Document) -> dict:
    """Spot id -> list of (column 'L'/'R', y0, y1) in manuscript page coordinates."""
    out = {}
    for sid, (pg, _, regions) in SP_ANCHORS.items():
        chars = page_chars(paper[pg - 1])
        text = "".join(c for c, _ in chars)
        body = [r for _, r in chars if r.y1 < 760]

        def find(phrase):
            i = text.find(phrase)
            assert i >= 0, f"S{sid}: phrase not found: {phrase}"
            return chars[i][1], chars[i + len(phrase) - 1][1]

        spans = []
        for reg in regions:
            start, end, col = (reg + (None,))[:3]
            s = None if start.startswith("@") else find(start)[0]
            e = None if end.startswith("@") else find(end)[1]
            col = col or ("L" if (s or e).x0 < 306 else "R")
            in_col = [r for r in body if (r.x0 < 306) == (col == "L")]
            y0 = s.y0 if s else min(r.y0 for r in in_col)
            y1 = e.y1 if e else max(r.y1 for r in in_col)
            spans.append((col, y0, y1))
        out[sid] = spans
    return out


def sp_markers(page, spans: dict, pno: int, fonts) -> None:
    """Purple brackets in the manuscript margins with the spot number; overlapping spots move outward."""
    lanes = {"L": [], "R": []}
    for sid in sorted(s for s in spans if SP_ANCHORS[s][0] == pno):
        for col, y0, y1 in spans[sid]:
            lane = 0
            while any(l == lane and not (y1 < a or y0 > b) for l, a, b in lanes[col]):
                lane += 1
            lanes[col].append((lane, y0 - 2, y1 + 2))
            sign = -1 if col == "L" else 1
            x = PX0 + (54 - 7 if col == "L" else 558 + 7) + sign * lane * 9
            top, bot = PY0 + y0, PY0 + y1
            page.draw_line((x, top), (x, bot), color=SP["rgb"], width=1.6)
            for y in (top, bot):
                page.draw_line((x, y), (x - sign * 3, y), color=SP["rgb"], width=1.6)
            c = fitz.Point(x + sign * 7, top + 5)
            page.draw_circle(c, 6, color=None, fill=SP["rgb"])
            label = str(sid)
            fs = 6.4 if sid < 10 else 5.6
            tw = fitz.TextWriter(page.rect)
            tw.append((c.x - fonts["b"].text_length(label, fontsize=fs) / 2, c.y + fs * 0.36), label,
                      font=fonts["b"], fontsize=fs)
            tw.write_text(page, color=(1, 1, 1))


# ---------------------------------------------------------------- LaTeX parts

PREAMBLE = r"""
\documentclass[10pt]{article}
\usepackage[paperwidth=1312bp,paperheight=838bp,top=58bp,bottom=40bp,left=56bp,right=56bp]{geometry}
\usepackage{fontspec}
\setmainfont{Apple SD Gothic Neo}[BoldFont={Apple SD Gothic Neo Bold}]
\setsansfont{Apple SD Gothic Neo}[BoldFont={Apple SD Gothic Neo Bold}]
\setmonofont{Apple SD Gothic Neo}
\newfontfamily\symfont{STIX Two Math}
\XeTeXlinebreaklocale "ko"
\XeTeXlinebreakskip=0pt plus 1pt
\usepackage{xcolor,calc,array,longtable,booktabs,multicol}
\usepackage[most]{tcolorbox}
\usepackage[hidelinks]{hyperref}
\definecolor{fable}{HTML}{C2410C}
\definecolor{astra}{HTML}{0F766E}
\definecolor{muted}{HTML}{555555}
\setlength{\parindent}{0pt}
\setlength{\parskip}{4pt}
\linespread{1.22}
\setcounter{secnumdepth}{0}
\newcounter{none}
\providecommand{\tightlist}{\setlength{\itemsep}{0pt}\setlength{\parskip}{0pt}}
\pagestyle{empty}
\begin{document}
"""


def tex(s: str) -> str:
    rep = {"\\": r"\textbackslash{}", "&": r"\&", "%": r"\%", "$": r"\$", "#": r"\#",
           "_": r"\_", "{": r"\{", "}": r"\}", "~": r"\textasciitilde{}", "^": r"\textasciicircum{}"}
    s = "".join(rep.get(c, c) for c in s)
    s = s.replace("\U0001D70C", r"{\symfont " + "\U0001D70C" + "}")  # math italic rho missing from Apple SD Gothic Neo
    return s.replace("\n", r"\newline ")


def tex_md_inline(s: str) -> str:
    s = tex(s)
    s = re.sub(r"\*\*(.+?)\*\*", r"\\textbf{\1}", s)
    return re.sub(r"`(.+?)`", r"\\texttt{\1}", s)


def tex_md_block(s: str) -> str:
    """Small markdown blocks from fable_review.md: paragraphs and '> ' quotes."""
    out = []
    groups = []  # consecutive lines of the same kind (quote / text); blank lines split text paragraphs
    for line in s.strip().splitlines():
        kind = "q" if line.startswith(">") else ("" if not line.strip() else "t")
        if kind and groups and groups[-1][0] == kind:
            groups[-1][1].append(line)
        elif kind:
            groups.append((kind, [line]))
        else:
            groups.append(("", []))
    for kind, lines in groups:
        if kind == "q":
            q = " ".join(l.lstrip("> ").strip() for l in lines)
            out.append(r"\begin{tcolorbox}[enhanced,frame hidden,colback=black!4,borderline west={1.5pt}{0pt}{black!30},"
                       r"left=5pt,right=3pt,top=1pt,bottom=1pt,before skip=1pt,after skip=2pt,arc=0pt]"
                       + tex_md_inline(q) + r"\end{tcolorbox}")
        elif kind == "t":
            out.append(tex_md_inline(" ".join(lines)) + r"\par")
    return "\n".join(out)


def pandoc(md: str) -> str:
    return subprocess.run(["pandoc", "-f", "markdown-smart", "-t", "latex", "--columns=40"],
                          input=md, capture_output=True, text=True, check=True).stdout


def compile_tex(body: str, name: str, work: Path) -> Path:
    f = work / f"{name}.tex"
    f.write_text(PREAMBLE + body + "\n\\end{document}\n", encoding="utf-8")
    for _ in range(2):
        r = subprocess.run(["xelatex", "-interaction=nonstopmode", "-halt-on-error", f.name],
                           cwd=work, capture_output=True, text=True)
        if r.returncode:
            raise SystemExit(f"xelatex failed on {name}:\n{r.stdout[-3000:]}")
    log = (work / f"{name}.log").read_text(errors="ignore")
    missing = re.findall(r"Missing character: There is no (.) ", log)
    if missing:
        print(f"[warn] {name}: missing glyphs {sorted(set(missing))}")
    return work / f"{name}.pdf"


def counts(anns: dict, p: str) -> dict:
    mine = [a for a in anns.values() if a["who"] == p]
    c = {k: sum(a["priority"] == k for a in mine) for k in PRIORITY}
    c["n"] = len(mine)
    c["pages"] = " · ".join(f"p{pg}: {sum(a['page'] == pg for a in mine)}" for pg in sorted({a['page'] for a in mine}))
    return c


def evaluation_tex(anns: dict, secs: dict) -> str:
    cf, ca = counts(anns, "F"), counts(anns, "A")
    one = {p: json.loads(REV[p]["ann"].read_text())["one_line_diagnosis"] for p in REV}
    md_score = {}
    for line in secs["점수"].splitlines():
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if len(cells) == 3 and cells[0][:1].isdigit():
            md_score[cells[0][:2]] = (cells[0], cells[2])
    rows = []
    for (f, a, fs, as_), note in zip(SCORES, FABLE_PDF_SCORE_NOTES["rows"]):
        md_label, md_note = md_score[f[:2]]
        rows.append(rf"{tex_md_inline(md_label)} & {tex(a)} & \textcolor{{fable}}{{\textbf{{{fs}}}}} & \textcolor{{astra}}{{\textbf{{{as_}}}}} & "
                    rf"{(fs + as_) / 2:.1f} & {tex_md_inline(md_note)} & {tex(note)} \\ \midrule")
    total_note = FABLE_PDF_SCORE_NOTES["rows"][-1]
    rows.append(rf"\textbf{{종합}} & \textbf{{종합}} & \textcolor{{fable}}{{\textbf{{{TOTAL[0]}}}}} & "
                rf"\textcolor{{astra}}{{\textbf{{{TOTAL[1]}}}}} & \textbf{{{sum(TOTAL) / 2:.1f}}} & "
                rf"— & {tex(total_note)} \\")
    md_title = secs["_head"].splitlines()[0].lstrip("# ")
    md_head = "\n".join(l[2:] for l in secs["_head"].splitlines() if l.startswith("- "))
    overall = "\n\n".join(f"### {k}\n\n{secs[k]}" for k in ["한 줄 결론", "잘 된 점 (유지)", "사람/AI 판정에 대한 보충", "권장 작업 순서"])
    reading = "".join(rf"\item {tex(x)}" for x in FABLE_PDF_SCORE_NOTES["reading"])
    return rf"""
{{\LARGE\bfseries 피드백 1 — 한국어 CogSci 원고 가독성 리뷰 (Fable 5.1 + Astra 통합본)}}\par\vspace{{2pt}}
{{\large LLM 오징어 게임: 생존 게임에서 언어 모델은 공존을 추구하는가?}} \quad {{\small\color{{muted}}대상 원고: \texttt{{sources/ko\_cogsci2027\_2026-10-23\_no\_appendix.pdf}} (본문 6쪽 + 참고문헌 1쪽) · 2026-10-23}}\par\vspace{{0pt}}

\begin{{tcolorbox}}[colback=white,colframe=black!25,boxrule=0.5pt,arc=2pt,left=6pt,right=6pt,top=3pt,bottom=3pt]
\small\textbf{{읽는 법}} \quad
\textcolor{{fable}}{{\rule{{8pt}}{{8pt}}}}\ \textbf{{Fable 5.1}} = 주황, 카드 번호 \textbf{{F01–F24}}, 원고 쪽의 \textbf{{왼쪽}} 열 \qquad
\textcolor{{astra}}{{\rule{{8pt}}{{8pt}}}}\ \textbf{{Astra (GPT-6 Astra)}} = 청록, 카드 번호 \textbf{{A01–A12}}, 원고 쪽의 \textbf{{오른쪽}} 열 \newline
원고 위 하이라이트: 주황 칠 = Fable, 청록 칠 + 밑줄 = Astra(두 색이 겹친 곳은 둘 다 짚은 곳). 카드 번호는 각 리뷰 원본의 수정 로드맵 번호(우선순위 순)와 같다.
카드 머리의 ‘함께 짚음’은 같은 곳을 다룬 상대 리뷰의 카드다. 카드 안의 진단·대안과 아래 평가 문장은 리뷰 원문 그대로이며, 표의 ‘두 리뷰 평균’ 열과 로드맵의 주제 이름만 이 합본에서 붙였다.
\end{{tcolorbox}}

\vspace{{-10pt}}\section{{1. 종합 평가 — 두 리뷰의 채점과 총평}}
\vspace{{-4pt}}\renewcommand{{\arraystretch}}{{1.12}}
{{\small
\begin{{longtable}}{{@{{}}p{{100bp}} p{{72bp}} >{{\centering\arraybackslash}}p{{40bp}} >{{\centering\arraybackslash}}p{{40bp}} >{{\centering\arraybackslash}}p{{40bp}} p{{410bp}} p{{410bp}}@{{}}}}
\toprule
\textbf{{항목 (Fable 표기)}} & \textbf{{Astra 표기}} & \textbf{{\textcolor{{fable}}{{Fable}}}} & \textbf{{\textcolor{{astra}}{{Astra}}}} & \textbf{{평균}} &
\textbf{{\textcolor{{fable}}{{Fable ‘한 줄 근거’ — fable\_review.md}}}} & \textbf{{\textcolor{{fable}}{{Fable 근거 — 원본 리뷰 PDF 채점표}}}} \\ \midrule
{chr(10).join(rows)}
\bottomrule
\end{{longtable}}}}
\vspace{{-6pt}}{{\footnotesize\color{{muted}} 두 리뷰어 모두 종합 = 다섯 항목의 단순 평균. Astra는 항목별 근거 없이 점수를 한 줄 진단에만 적었다. 평균 열은 이 합본에서 계산했다.
Fable 채점표 머리말: “{tex(FABLE_PDF_SCORE_NOTES['head'])}”}}

\begin{{tcbraster}}[raster columns=2,raster equal height,raster column skip=10pt]
\begin{{tcolorbox}}[colback=fable!5,colframe=fable,boxrule=0.6pt,arc=2pt,title=\textbf{{Fable 5.1 — 한 줄 진단}} \quad 주석 {cf['n']}건 (★ {cf['highest']} · ▲ {cf['high']} · 일반 {cf['normal']}) · {cf['pages']},fonttitle=\small]
\small {tex(one['F'])}
\end{{tcolorbox}}
\begin{{tcolorbox}}[colback=astra!5,colframe=astra,boxrule=0.6pt,arc=2pt,title=\textbf{{Astra (GPT-6 Astra) — 한 줄 진단}} \quad 주석 {ca['n']}건 (★ {ca['highest']} · ▲ {ca['high']} · 일반 {ca['normal']}) · {ca['pages']},fonttitle=\small]
\small {tex(one['A'])}
\end{{tcolorbox}}
\end{{tcbraster}}

\vspace{{-6pt}}\subsection{{Fable 5.1의 총평 (fable\_review.md)}}
{{\footnotesize\color{{muted}} 메모 제목: {tex(md_title)} \newline 메모 머리말 — {tex_md_inline(md_head)}}}
{{\footnotesize\setlength{{\parskip}}{{2pt}}
\begin{{multicols}}{{3}}
{pandoc(overall).replace(chr(92) + "subsection", chr(92) + "subsubsection")}
\subsubsection{{원본 리뷰 PDF 채점표의 ‘읽는 법’}}
\begin{{itemize}}\tightlist {reading}\end{{itemize}}
\end{{multicols}}}}
"""


def roadmap_tex(anns: dict, items: dict, order: list, groups: list) -> str:
    def fable_cell(i: str) -> str:
        a, m = anns[i], items[i]
        head = rf"\textbf{{\textcolor{{fable}}{{{i}}}}} {PRIORITY[a['priority']]} · {CATEGORY[a['category']][0]} · p.{a['page']}"
        if "body" in m:  # ★ items: 현재 / 문제 / 수정 paragraphs
            return head + rf" — \textbf{{{tex_md_inline(m['title'])}}}\par " + tex_md_block(m["body"])
        return head + rf" — {tex_md_inline(m['where'])}\par \textbf{{문제}} {tex_md_inline(m['problem'])}\par \textbf{{수정}} {tex_md_inline(m['fix'])}"

    def astra_cell(i: str) -> str:
        a = anns[i]
        return (rf"\textbf{{\textcolor{{astra}}{{{i}}}}} {PRIORITY[a['priority']]} · {CATEGORY[a['category']][0]} · p.{a['page']}\par "
                rf"\textbf{{진단}} {tex(a['diagnosis'])}\par \textbf{{대안}} → {tex(a['alt'])}")

    none = r"{\color{muted}\footnotesize — (이 리뷰는 짚지 않음)}"
    rows = []
    for label, f, a, page in order:
        both = r"\newline\colorbox{black!10}{\scriptsize\bfseries 공통}" if f and a else ""
        fc = r"\par\vspace{3pt}".join(fable_cell(i) for i in f) or none
        ac = r"\par\vspace{3pt}".join(astra_cell(i) for i in a) or none
        rows.append(rf"\textbf{{p.{page}}} {tex(label)}{both} & {fc} & {ac} \\ \midrule")
    n_both = sum(1 for _, f, a, _ in order if f and a)
    return rf"""
\section{{3. 통합 수정 로드맵 — 원고 위치 순서}}
{{\small\color{{muted}} 원고의 같은 곳을 다룬 주석을 한 행에 묶었다({len(order)}곳, 그중 두 리뷰가 함께 짚은 곳 {n_both}곳 = ‘공통’).
Fable 칸은 \texttt{{fable\_review.md}}의 항목 글(최우선 3건의 현재·문제·수정, 중요·일반 표의 위치·문제·수정)을, Astra 칸은 \texttt{{annotations.json}}의 진단·대안을 그대로 옮겼다.
Fable 메모의 묶음은 {' · '.join(tex(g) for g in groups)}이며, 각 항목의 ★ / ▲ / 일반 표시가 이 묶음이다. Fable 카드의 진단·대안 원문은 2부의 원고 쪽 카드에 있다. 첫 열의 주제 이름만 이 합본에서 붙였다.}}
{{\small\renewcommand{{\arraystretch}}{{1.25}}
\begin{{longtable}}{{@{{}}p{{150bp}} p{{560bp}} p{{460bp}}@{{}}}}
\toprule
\textbf{{원고 위치 · 주제}} & \textbf{{\textcolor{{fable}}{{Fable 5.1}}}} & \textbf{{\textcolor{{astra}}{{Astra (GPT-6 Astra)}}}} \\ \midrule
\endhead
{chr(10).join(rows)}
\bottomrule
\end{{longtable}}}}
"""


def sp_overview_tex(head: list, questions: dict, pieces: list) -> str:
    qrows = "\n".join(rf"\textbf{{\textcolor{{sp}}{{{q}}}}} & {tex(t)} \\ \midrule" for q, t in questions.items())

    def cell(sid, who):
        ps = sorted((p for p in pieces if p["anchor"] == sid and p["who"] == who), key=lambda p: (p["q"], p["k"]))
        return ", ".join(f"{p['q']} 조각 {p['k']}/{p['n']}" for p in ps) or r"\textcolor{muted}{—}"

    rows = "\n".join(rf"\textbf{{\textcolor{{sp}}{{S{sid}}}}} & p.{pg} & {tex(label)} & {cell(sid, 'F')} & {cell(sid, 'A')} \\"
                     for sid, (pg, label, _) in SP_ANCHORS.items())
    per = {}
    for p in pieces:
        per.setdefault((p["q"], p["who"]), []).append(f"{p['k']}→S{p['anchor']}")
    order = "\n".join(rf"\textbf{{{q}}} & {' · '.join(per[(q, 'F')])} & {' · '.join(per[(q, 'A')])} \\ \midrule"
                      for q in questions)
    return rf"""
\definecolor{{sp}}{{HTML}}{{{SP['hex']}}}
{{\LARGE\bfseries\color{{sp}} 승필 팀장 피드백 — Fable · Astra 조언을 원고 위치에 배치}}\par\vspace{{4pt}}
\begin{{tcolorbox}}[colback=sp!5,colframe=sp,boxrule=0.6pt,arc=2pt,left=6pt,right=6pt,top=3pt,bottom=3pt]
\small\textbf{{누가}} \quad 피드백: \textbf{{승필 (팀장)}} \quad · \quad 피드백을 질문으로 정리: \textbf{{juhyeon}} \quad · \quad
조언: \textcolor{{fable}}{{\textbf{{Fable}}}}, \textcolor{{astra}}{{\textbf{{Astra}}}} (원문 표기 그대로) \quad · \quad
출처: \texttt{{sources/seungpil-review/seungpil-review.md}} \newline
\textbf{{원문 머리말}} \quad “{tex(head[0])} {tex(head[1])}”
\end{{tcolorbox}}

\begin{{tcolorbox}}[colback=white,colframe=black!25,boxrule=0.5pt,arc=2pt,left=6pt,right=6pt,top=3pt,bottom=3pt]
\small\textbf{{읽는 법}} \quad 각 원고 쪽(2부)의 위 절반은 기존 가독성 리뷰 그대로이고, 그 아래 \textcolor{{sp}}{{\textbf{{보라색 띠}}}}에 이 쪽에 해당하는 승필 팀장 피드백 조언이 붙어 있다.
원고 여백의 \textcolor{{sp}}{{\textbf{{보라색 괄호와 번호 S1–S{len(SP_ANCHORS)}}}}}가 조언이 가리키는 위치이고, 띠 안에서 같은 번호 아래 왼쪽은 \textcolor{{fable}}{{\textbf{{Fable}}}}, 오른쪽은 \textcolor{{astra}}{{\textbf{{Astra}}}} 조언이다.
한 질문에 대한 답 하나를 원고 위치별로 나눈 것이 ‘조각 k/n’이며, 조각을 1부터 n까지 이어 읽으면 원래 답 전체가 된다(아래 순서 표). 조각 안의 글은 원문 그대로이고, 다른 위치로 간 표 행이 있는 조각에만 표 머리를 다시 붙였다. 위치 이름과 S 번호만 이 합본에서 붙였다.
\end{{tcolorbox}}

\vspace{{-4pt}}\subsection{{세 질문 (원문 그대로)}}
{{\small\renewcommand{{\arraystretch}}{{1.15}}
\begin{{longtable}}{{@{{}}p{{30bp}} p{{1150bp}}@{{}}}}
\toprule
{qrows}
\end{{longtable}}}}

\vspace{{-10pt}}
\begin{{multicols}}{{2}}
\subsection{{위치별 색인}}
{{\footnotesize\renewcommand{{\arraystretch}}{{1.1}}
\begin{{tabular}}{{@{{}}p{{22bp}} p{{20bp}} p{{200bp}} p{{150bp}} p{{150bp}}@{{}}}}
\toprule
\textbf{{번호}} & \textbf{{쪽}} & \textbf{{원고 위치}} & \textbf{{\textcolor{{fable}}{{Fable 조언}}}} & \textbf{{\textcolor{{astra}}{{Astra 조언}}}} \\ \midrule
{rows}
\bottomrule
\end{{tabular}}}}
\columnbreak
\subsection{{답의 순서 — 조각 번호 → 위치}}
{{\footnotesize\renewcommand{{\arraystretch}}{{1.2}}
\begin{{tabular}}{{@{{}}p{{22bp}} p{{250bp}} p{{290bp}}@{{}}}}
\toprule
\textbf{{질문}} & \textbf{{\textcolor{{fable}}{{Fable 조언}}}} & \textbf{{\textcolor{{astra}}{{Astra 조언}}}} \\ \midrule
{order}
\end{{tabular}}}}
\end{{multicols}}
"""


# ---------------------------------------------------------------- integrated manuscript pages

CSS = f"""
@font-face {{font-family: ng; src: url({FONT_REG});}}
@font-face {{font-family: ng; src: url({FONT_BOLD}); font-weight: bold;}}
body {{font-family: ng; font-size: 8pt; line-height: 1.34; margin: 0; padding: 0; color: #111;}}
p {{margin: 0 0 2.5pt 0;}}
.alt {{color: #1f2937;}}
"""


def card_html(a: dict) -> str:
    e = lambda s: html.escape(s).replace("\n", "<br>")
    return (f"<p><b>진단</b>&nbsp; {e(a['diagnosis'])}</p>"
            f"<p class='alt'><b>→ 대안</b>&nbsp; {e(a['alt'])}</p>")


def measure(body: str, width: float, arch, css: str = CSS) -> float:
    story = fitz.Story(body, user_css=css, archive=arch)
    more, filled = story.place(fitz.Rect(0, 0, width, 6000))
    assert not more
    return fitz.Rect(filled).y1


def stack(cards: list, top: float, bottom: float) -> float:
    """Place cards near their anchors without overlap; returns the bottom actually needed."""
    y = top
    for c in cards:
        c["y"] = max(c["anchor"] - 8, y)
        y = c["y"] + c["h"] + CARD_GAP
    limit = bottom
    for c in reversed(cards):
        if c["y"] + c["h"] > limit:
            c["y"] = limit - c["h"]
        limit = c["y"] - CARD_GAP
    if cards and cards[0]["y"] < top:  # does not fit: plain stack from the top, page grows
        y = top
        for c in cards:
            c["y"] = y
            y += c["h"] + CARD_GAP
        return y
    return bottom


def draw_card(page, c, x0, x1, p, arch, fonts) -> None:
    a, r = c["ann"], REV[p]
    rect = fitz.Rect(x0, c["y"], x1, c["y"] + c["h"])
    page.draw_rect(rect, color=r["rgb"], fill=(1, 1, 1), width=0.7)
    head = fitz.Rect(x0, c["y"], x1, c["y"] + 14)
    page.draw_rect(head, color=r["rgb"], fill=r["light"], width=0.7)
    tw = fitz.TextWriter(page.rect)
    tw.append((x0 + 5, c["y"] + 10), a["id"], font=fonts["b"], fontsize=8.2)
    tw.write_text(page, color=r["rgb"])
    tw = fitz.TextWriter(page.rect)
    tw.append((x0 + 28, c["y"] + 10), PRIORITY[a["priority"]], font=fonts["b"], fontsize=7.2)
    peers = ", ".join(a["peers"])
    if peers:
        tw.append((x0 + 82, c["y"] + 10), f"함께 짚음: {peers}", font=fonts["r"], fontsize=6.6)
    tw.write_text(page, color=(0.15, 0.15, 0.15))
    cat, ccol = CATEGORY[a["category"]]
    chip = fitz.Rect(x1 - 30, c["y"] + 2.5, x1 - 4, c["y"] + 11.5)
    page.draw_rect(chip, color=None, fill=ccol)
    tw = fitz.TextWriter(page.rect)
    tw.append((chip.x0 + 5.5, chip.y1 - 2.2), cat, font=fonts["b"], fontsize=6.6)
    tw.write_text(page, color=(0.2, 0.2, 0.2))
    spare, _ = page.insert_htmlbox(fitz.Rect(x0 + 5, c["y"] + 17, x1 - 5, c["y"] + c["h"] - 2),
                                   c["html"], css=CSS, archive=arch, scale_low=1)
    assert spare >= 0, a["id"]


SP_CSS = CSS + """
body {font-size: 8.4pt; line-height: 1.42;}
p {margin: 0 0 3.5pt 0;}
ul, ol {margin: 0 0 3.5pt 0; padding-left: 14pt;}
li {margin: 0 0 1.5pt 0;}
blockquote {margin: 1pt 0 4pt 6pt; padding-left: 6pt; color: #333; background-color: #f3f3f3;}
table {border-collapse: collapse; margin: 1pt 0 4pt 0;}
th, td {border: 0.5pt solid #9a9a9a; padding: 1.5pt 3pt; vertical-align: top;}
th {background-color: #eeeeee;}
a {color: #1d4ed8;}
.url {color: #666; font-size: 7pt;}
.q {margin: 0 0 3pt 0;}
"""
SP_COLS = {"F": (LX0, W / 2 - 5), "A": (W / 2 + 5, RX1)}
SP_HEAD = 15  # card title bar


def sp_layout(pieces: list, questions: dict, pno: int, arch) -> dict:
    """Heights for the purple band under one manuscript page."""
    mine = [p for p in pieces if SP_ANCHORS[p["anchor"]][0] == pno]
    if not mine:
        return dict(h=0)
    qs = sorted({p["q"] for p in mine})
    qhtml = "".join(f"<p class='q'><b>{q}</b>&nbsp; {html.escape(questions[q])}</p>" for q in qs)
    qh = measure(qhtml, W - 2 * LX0 - 16, arch, SP_CSS) + 8
    rows = []
    for sid in sorted({p["anchor"] for p in mine}):
        side = {}
        for who in "FA":
            x0, x1 = SP_COLS[who]
            cards = []
            for p in sorted((p for p in mine if p["anchor"] == sid and p["who"] == who), key=lambda p: (p["q"], p["k"])):
                body = sp_html(p["md"])
                cards.append(dict(p=p, html=body, h=measure(body, x1 - x0 - 12, arch, SP_CSS) + SP_HEAD + 8))
            side[who] = cards
        h = max(sum(c["h"] + CARD_GAP for c in side[w]) if side[w] else 18 for w in "FA")
        rows.append(dict(sid=sid, side=side, h=h + 20))
    top = 34  # band
    return dict(h=top + qh + 6 + sum(r["h"] + 8 for r in rows) + 30, qs=qs, qhtml=qhtml, qh=qh, rows=rows,
                n={w: sum(p["who"] == w for p in mine) for w in "FA"}, top=top)


def sp_draw(page, y: float, lay: dict, pno: int, arch, fonts) -> None:
    page.draw_rect(fitz.Rect(0, y, W, y + 24), color=None, fill=SP["rgb"])
    tw = fitz.TextWriter(page.rect)
    tw.append((14, y + 16), f"▼ {SP['name']} 피드백 — 원고 p.{pno}에 해당하는 조언  ·  "
                            f"Fable 조언 {lay['n']['F']}조각 (왼쪽)  ·  Astra 조언 {lay['n']['A']}조각 (오른쪽)  ·  "
                            f"보라색 번호 S = 위 원고 여백의 괄호", font=fonts["b"], fontsize=10.5)
    tw.write_text(page, color=(1, 1, 1))
    y += lay["top"]
    box = fitz.Rect(LX0, y, W - LX0, y + lay["qh"])
    page.draw_rect(box, color=SP["rgb"], fill=SP["light"], width=0.7)
    page.insert_htmlbox(box + (8, 4, -8, -2), lay["qhtml"], css=SP_CSS, archive=arch, scale_low=1)
    y += lay["qh"] + 6
    for row in lay["rows"]:
        sid = row["sid"]
        pg, label, _ = SP_ANCHORS[sid]
        page.draw_rect(fitz.Rect(LX0, y, W - LX0, y + 15), color=None, fill=SP["light"])
        c = fitz.Point(LX0 + 9, y + 7.5)
        page.draw_circle(c, 6.2, color=None, fill=SP["rgb"])
        tw = fitz.TextWriter(page.rect)
        s = str(sid)
        tw.append((c.x - fonts["b"].text_length(s, fontsize=6.4) / 2, c.y + 2.3), s, font=fonts["b"], fontsize=6.4)
        tw.write_text(page, color=(1, 1, 1))
        tw = fitz.TextWriter(page.rect)
        tw.append((LX0 + 22, y + 11), f"S{sid}  원고 p.{pg} · {label}", font=fonts["b"], fontsize=8.8)
        tw.write_text(page, color=SP["rgb"])
        yy0 = y + 20
        for who in "FA":
            x0, x1 = SP_COLS[who]
            r = REV[who]
            yy = yy0
            if not row["side"][who]:
                tw = fitz.TextWriter(page.rect)
                tw.append((x0 + 4, yy + 10), f"— 이 위치에는 {SP_WHO[who]} 조언 없음", font=fonts["r"], fontsize=7.4)
                tw.write_text(page, color=(0.5, 0.5, 0.5))
            for cd in row["side"][who]:
                p = cd["p"]
                rect = fitz.Rect(x0, yy, x1, yy + cd["h"])
                page.draw_rect(rect, color=r["rgb"], fill=(1, 1, 1), width=0.7)
                page.draw_rect(fitz.Rect(x0, yy, x1, yy + SP_HEAD), color=r["rgb"], fill=r["light"], width=0.7)
                tw = fitz.TextWriter(page.rect)
                tw.append((x0 + 5, yy + 10.5), f"{SP_WHO[p['who']]} 조언 · {p['q']}", font=fonts["b"], fontsize=8.2)
                tw.write_text(page, color=r["rgb"])
                tw = fitz.TextWriter(page.rect)
                tw.append((x0 + 90, yy + 10.5), f"조각 {p['k']}/{p['n']}  ·  {SP['name']} 피드백에 대한 답  ·  원문 {p['src']}행",
                          font=fonts["r"], fontsize=7)
                tw.write_text(page, color=(0.25, 0.25, 0.25))
                spare, _ = page.insert_htmlbox(fitz.Rect(x0 + 6, yy + SP_HEAD + 3, x1 - 6, yy + cd["h"] - 2),
                                               cd["html"], css=SP_CSS, archive=arch, scale_low=1)
                assert spare >= 0, (p["q"], p["who"], p["k"])
                yy += cd["h"] + CARD_GAP
        y += row["h"] + 8


def build_manuscript_page(doc, paper, pno, anns, arch, fonts, sp=None) -> None:
    on_page = {p: sorted((a for a in anns.values() if a["who"] == p and a["page"] == pno + 1),
                         key=lambda a: (a["rects"][0].x0 > 306, a["rects"][0].y0)) for p in REV}
    cw = LX1 - LX0
    cards = {}
    need = H_MIN
    for p, lst in on_page.items():
        cards[p] = []
        for a in lst:
            body = card_html(a)
            h = measure(body, cw - 10, arch) + 22
            cards[p].append(dict(ann=a, html=body, h=h, anchor=PY0 + a["rects"][0].y0))
        cards[p].sort(key=lambda c: c["anchor"])
        need = max(need, stack(cards[p], BAND + 26, H_MIN - 10) + 10)
    pieces, questions, spans = sp
    lay = sp_layout(pieces, questions, pno + 1, arch)
    page = doc.new_page(width=W, height=need + lay["h"])
    if lay["h"]:
        sp_draw(page, need, lay, pno + 1, arch, fonts)
    page.show_pdf_page(fitz.Rect(PX0, PY0, PX0 + 612, PY0 + 792), paper, pno)
    page.draw_rect(fitz.Rect(PX0, PY0, PX0 + 612, PY0 + 792), color=(0.75, 0.75, 0.75), width=0.5)

    # highlights: Fable = orange fill, Astra = teal fill + underline
    for p, lst in on_page.items():
        for a in lst:
            for r in a["rects"]:
                rr = r + (PX0, PY0, PX0, PY0)
                page.draw_rect(rr, color=None, fill=REV[p]["hl"], fill_opacity=0.38 if p == "F" else 0.26, overlay=True)
                if p == "A":
                    page.draw_line((rr.x0, rr.y1 + 0.8), (rr.x1, rr.y1 + 0.8), color=REV[p]["rgb"], width=1.3)
    sp_markers(page, spans, pno + 1, fonts)

    for p, (x0, x1) in {"F": (LX0, LX1), "A": (RX0, RX1)}.items():
        tw = fitz.TextWriter(page.rect)
        n = len(cards[p])
        tw.append((x0, BAND + 16), f"{REV[p]['name']} 주석 {n}건" if n else f"{REV[p]['name']} — 이 쪽에는 주석 없음",
                  font=fonts["b"], fontsize=8.5)
        tw.write_text(page, color=REV[p]["rgb"])
        for c in cards[p]:
            draw_card(page, c, x0, x1, p, arch, fonts)
            first, last = c["ann"]["rects"][0], c["ann"]["rects"][-1]
            if p == "F":
                start = fitz.Point(PX0 + first.x0 - 1, PY0 + (first.y0 + first.y1) / 2)
                end = fitz.Point(x1, c["y"] + 7)
            else:
                start = fitz.Point(PX0 + last.x1 + 1, PY0 + (last.y0 + last.y1) / 2)
                end = fitz.Point(x0, c["y"] + 7)
            page.draw_line(start, end, color=REV[p]["rgb"], width=0.6, stroke_opacity=0.65)
            page.draw_circle(start, 1.6, color=None, fill=REV[p]["rgb"])


# ---------------------------------------------------------------- bands and assembly

def band(page, segments, footer: str, fonts) -> None:
    """segments: list of (x0, x1, rgb, text)."""
    for x0, x1, rgb, text in segments:
        page.draw_rect(fitz.Rect(x0, 0, x1, BAND - 4), color=None, fill=rgb, overlay=True)
        tw = fitz.TextWriter(page.rect)
        tw.append((x0 + 12, 17), text, font=fonts["b"], fontsize=10.5)
        tw.write_text(page, color=(1, 1, 1))
    tw = fitz.TextWriter(page.rect)
    fw = fonts["r"].text_length(footer, fontsize=7.5)
    tw.append((page.rect.width - 16 - fw, page.rect.height - 10), footer, font=fonts["r"], fontsize=7.5)
    tw.write_text(page, color=(0.45, 0.45, 0.45))


def main() -> None:
    anns = load_annotations()
    paper = fitz.open(PAPER)
    for a in anns.values():
        a["rects"] = locate(paper, a)
    secs = md_sections()
    items = md_items(secs)
    order = []
    for label, f, a in TOPICS:
        first = min((anns[i] for i in f + a), key=lambda x: (x["page"], x["rects"][0].x0 > 306, x["rects"][0].y0))
        order.append((label, f, a, first["page"], (first["page"], first["rects"][0].x0 > 306, first["rects"][0].y0)))
    order = [o[:4] for o in sorted(order, key=lambda o: o[4])]

    sp_head, sp_questions, sp_pieces = sp_load()
    sp = (sp_pieces, sp_questions, sp_locate(paper))
    sp_n = lambda pno: sum(SP_ANCHORS[p["anchor"]][0] == pno for p in sp_pieces)

    fonts = {"r": fitz.Font(fontfile=str(FONT_DIR / FONT_REG)), "b": fitz.Font(fontfile=str(FONT_DIR / FONT_BOLD))}
    arch = fitz.Archive(str(FONT_DIR))
    with tempfile.TemporaryDirectory() as tmp:
        work = Path(tmp)
        evaluation = fitz.open(compile_tex(evaluation_tex(anns, secs), "evaluation", work))
        overview = fitz.open(compile_tex(sp_overview_tex(sp_head, sp_questions, sp_pieces), "seungpil", work))
        groups = [k for k in secs if k.startswith(("최우선", "중요", "일반"))]
        roadmap = fitz.open(compile_tex(roadmap_tex(anns, items, order, groups), "roadmap", work))

        doc = fitz.open()
        doc.insert_pdf(evaluation)
        n_eval = doc.page_count
        doc.insert_pdf(overview)
        n_front = doc.page_count
        for pno in range(paper.page_count):
            build_manuscript_page(doc, paper, pno, anns, arch, fonts, sp)
        doc.insert_pdf(roadmap)

        n = doc.page_count
        dark, F, A = (0.2, 0.2, 0.2), REV["F"]["rgb"], REV["A"]["rgb"]
        for i, page in enumerate(doc):
            foot = f"피드백 1 통합본 · {i + 1} / {n}"
            if n_front <= i < n_front + paper.page_count:
                pno = i - n_front + 1
                k = {p: sum(1 for a in anns.values() if a["who"] == p and a["page"] == pno) for p in REV}
                below = f"  ·  승필 팀장 피드백 {sp_n(pno)}조각 ▼ 아래" if sp_n(pno) else ""
                band(page, [(0, PX0 - 9, F, f"◀ FABLE 5.1 리뷰 · 이 쪽 {k['F']}건"),
                            (PX0 - 9, RX0 - 9, dark, f"원고 p.{pno} / {paper.page_count}  ·  두 리뷰 통합{below}"),
                            (RX0 - 9, W, A, f"ASTRA 리뷰 (GPT-6 Astra) · 이 쪽 {k['A']}건 ▶")], foot, fonts)
            elif n_eval <= i < n_front:
                band(page, [(0, W, SP["rgb"], "1-2. 승필 팀장 피드백 — 누가 · 세 질문 · 원고 위치 색인")], foot, fonts)
            else:
                title = "1. 종합 평가 — Fable 5.1 + Astra (GPT-6 Astra)" if i < n_eval else "3. 통합 수정 로드맵 — Fable 5.1 + Astra (GPT-6 Astra)"
                band(page, [(0, 12, F, ""), (12, W - 12, dark, title), (W - 12, W, A, "")], foot, fonts)

        toc = [[1, "1. 종합 평가 (채점 · 한 줄 진단 · 총평)", 1],
               [1, "1-2. 승필 팀장 피드백 (누가 · 세 질문 · 위치 색인)", n_eval + 1],
               [1, "2. 원고 쪽별 통합 주석", n_front + 1]]
        for pno in range(paper.page_count):
            k = {p: sum(1 for a in anns.values() if a["who"] == p and a["page"] == pno + 1) for p in REV}
            toc.append([2, f"원고 p.{pno + 1} — Fable {k['F']}건 · Astra {k['A']}건 · 승필 피드백 {sp_n(pno + 1)}조각",
                        n_front + pno + 1])
        toc.append([1, "3. 통합 수정 로드맵", n_front + paper.page_count + 1])
        doc.set_toc(toc)
        doc.set_metadata({"title": "피드백 1 — 한국어 CogSci 원고 리뷰 (Fable 5.1 + GPT-6 Astra 가독성 리뷰, 승필 팀장 피드백)",
                          "author": "Fable 5.1, GPT-6 Astra (reviews); 승필 (feedback), juhyeon (questions); merged 2026-10-24"})
        doc.subset_fonts()
        doc.save(OUT, garbage=3, deflate=True)
        print(f"wrote {OUT} ({n} pages: evaluation {n_eval}, seungpil {overview.page_count}, "
              f"manuscript {paper.page_count}, roadmap {roadmap.page_count}; seungpil pieces {len(sp_pieces)})")


if __name__ == "__main__":
    main()
