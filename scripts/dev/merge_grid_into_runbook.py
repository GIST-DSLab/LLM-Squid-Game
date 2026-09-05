"""Merge the six threat-prompt-grid framings into the Part 2 tables of the SDI runbook.

``scripts/analysis/sdi_grid_indicators.py`` recomputes every Part 2 table of
``weekly-report/0910/sdi-experiment-runbook.html`` over an arbitrary set of
framings.  The runbook itself was written for the five framings of the 10-cell
run; the 3x3 threat prompt grid (2026-09-05, Design 3.4) adds six more.

This script takes that script's ``tables.json`` and splices the six new framings
into the *existing* tables as extra columns or rows.  It never touches the
article's structure or prose: the only prose token it rewrites is the forfeit
table's ``포기 N건 전체 표`` count, and the six ``신규 초안`` status pills of the
3x3 prompt table in ``id="s3-grid"``.

Usage (append mode, the default)::

    python scripts/dev/merge_grid_into_runbook.py \\
        --tables results/sdi_indicators/<tag>/tables.json \\
        --html weekly-report/0910/sdi-experiment-runbook.html \\
        --out /tmp/runbook_merged.html

Idempotency: the script refuses (exit 2) if the input HTML already carries one
of the six new framing labels, so it can never be applied twice.

``--refill`` is the second mode: it takes the *already merged* runbook (all
eleven framings present) and overwrites every number in it with another model's
``tables.json``, so each model of the 22-cell design can get its own copy of the
same document::

    python scripts/dev/merge_grid_into_runbook.py --refill \\
        --tables results/sdi_indicators/<other model>/tables.json \\
        --html weekly-report/0910/sdi-experiment-runbook.html \\
        --out weekly-report/0910/sdi-experiment-runbook_<tag>.html \\
        --model-label "gemma4:31b" --run-label "Omni-MATH hard-10 · 22셀 × 10판" \\
        --date 2026-09-06

Refill covers every Part 2 table this file knows (all eleven framing columns /
rows, not just the six the append mode adds), rebuilds the two event lists
(2.3(c) forfeits and the top-8 SDI turns) from scratch, recomputes the 2.3(a)
합계 row, and refreshes the Part 1 counts (the four cards, the 1.1 cell table,
the header meta line).  It does **not** touch prose, the 2.4 SVG figures, the
2.3(f) blind-guess tables, or the aggregate "위협 3셀 합침" / "5셀 합침" columns
(tables.json cannot recompute those, so they are blanked to an em dash).  The
``hi`` highlight class marked gpt-oss extremes and is dropped from every refilled
cell rather than recomputed.

Stdlib only.  Values that are ``null`` in ``tables.json`` (the resample is still
running when the prelim tables are dumped) render as an em dash; re-running the
script on the final ``tables.json`` fills them in.  No number is hard-coded.
"""

from __future__ import annotations

import argparse
import html as _html
import json
import re
import sys
from pathlib import Path

# --------------------------------------------------------------------------- constants

#: (framing key, Korean column/row label, allowed cell id, not_allowed cell id).
#: This order is used for every column insertion and every row append.
NEW_FRAMINGS: list[tuple[str, str, int, int]] = [
    ("threat_l1_medium", "위협 1단계·중간 길이", 11, 17),
    ("threat_l1_long", "위협 1단계·긴 길이", 12, 18),
    ("threat_l2_short", "위협 2단계·짧은 길이", 13, 19),
    ("threat_l2_long", "위협 2단계·긴 길이", 14, 20),
    ("threat_l3_short", "위협 3단계·짧은 길이", 15, 21),
    ("threat_l3_medium", "위협 3단계·중간 길이", 16, 22),
]

KEYS = [f for f, _, _, _ in NEW_FRAMINGS]
LABELS = {f: lab for f, lab, _, _ in NEW_FRAMINGS}
CELL_ALLOWED = {f: a for f, _, a, _ in NEW_FRAMINGS}
CELL_NOT_ALLOWED = {f: n for f, _, _, n in NEW_FRAMINGS}

DASH = "—"

#: Heatmap shading of the SDI x lives table, fitted exactly against all 36
#: existing cells of that table (alpha = 0.08 + 0.77 * v / 4.2, 2 decimals).
_HEAT_BASE = 0.08
_HEAT_SLOPE = 0.77 / 4.2
_HEAT_BOLD_FROM = 1.0

_PILL_OLD = '<span class="pill">신규 초안</span>'
_PILL_NEW = '<span class="pill">실행 완료 · 2026-09-06</span>'


# --------------------------------------------------------------------------- formatting


def _is_none(v) -> bool:
    return v is None


def f_fix(v, nd: int) -> str:
    """Fixed-decimal, em dash on null."""
    return DASH if _is_none(v) else f"{float(v):.{nd}f}"


def f_int(v) -> str:
    """Rounded to an integer (banker's rounding, as the existing cells use)."""
    return DASH if _is_none(v) else f"{int(round(float(v)))}"


def f_comma(v) -> str:
    """Thousands-separated; keeps one decimal only when the value is not whole."""
    if _is_none(v):
        return DASH
    x = float(v)
    return f"{int(x):,}" if x == int(x) else f"{x:,.1f}"


def f_comma_int(v) -> str:
    return DASH if _is_none(v) else f"{int(round(float(v))):,}"


def f_signed_int(v) -> str:
    return DASH if _is_none(v) else f"{float(v):+.0f}"


def f_signed_1(v) -> str:
    return DASH if _is_none(v) else f"{float(v):+.1f}"


def f_pair(value: str, n) -> str:
    """``value (n)`` — the ``(n)`` convention of the plain (non-heatmap) tables."""
    if value == DASH:
        return DASH
    return f"{value} ({f_int(n)})"


def n_span(n) -> str:
    """The small grey ``(n)`` span used inside heatmap-style cells."""
    return f'<span style="color:var(--soft);font-weight:400;font-size:.8em">({f_int(n)})</span>'


# --------------------------------------------------------------------------- cell builders


def td_num(text: str) -> str:
    return f'<td class="num">{text}</td>'


def th_num(text: str) -> str:
    return f'<th class="num">{text}</th>'


def td_heat(value, n) -> str:
    """A shaded ``mean (n)`` cell matching the SDI x lives heatmap."""
    if _is_none(value):
        return td_num(DASH)
    v = float(value)
    alpha = round(_HEAT_BASE + _HEAT_SLOPE * max(v, 0.0), 2)
    alpha = min(alpha, 0.95)
    style = f"background:rgba(224,96,47,{alpha:.2f});"
    if v >= _HEAT_BOLD_FROM:
        style += "font-weight:600;"
    return f'<td class="num" style="{style}">{v:.2f} {n_span(n)}</td>'


def td_mean_n(value, n, nd: int) -> str:
    """A plain ``mean (n)`` cell (turn x story tables)."""
    if _is_none(value):
        return td_num(DASH)
    return f'<td class="num">{float(value):.{nd}f} {n_span(n)}</td>'


# --------------------------------------------------------------------------- html surgery

_CELL_RE = re.compile(r"<t([hd])\b[^>]*>.*?</t\1>", re.S)
_ROW_RE = re.compile(r"<tr\b[^>]*>.*?</tr>", re.S)
_TABLE_RE = re.compile(r"<table\b[^>]*>.*?</table>", re.S)
_TAG_RE = re.compile(r"<[^>]+>")


def cells_of(row: str) -> list[re.Match]:
    return list(_CELL_RE.finditer(row))


def cell_text(cell_html: str) -> str:
    return _html.unescape(_TAG_RE.sub("", cell_html)).strip()


def row_labels(row: str) -> list[str]:
    return [cell_text(m.group(0)) for m in cells_of(row)]


def first_label(row: str) -> str:
    ms = cells_of(row)
    return cell_text(ms[0].group(0)) if ms else ""


def insert_before_last(row: str, new_html: str) -> str:
    ms = cells_of(row)
    if not ms:
        raise ValueError("row has no cells")
    pos = ms[-1].start()
    return row[:pos] + new_html + row[pos:]


def append_cells(row: str, new_html: str) -> str:
    ms = cells_of(row)
    if not ms:
        raise ValueError("row has no cells")
    pos = ms[-1].end()
    return row[:pos] + new_html + row[pos:]


def rows_of(table: str) -> list[re.Match]:
    return list(_ROW_RE.finditer(table))


def rebuild_table(table: str, new_rows: list[str]) -> str:
    """Replace the table's <tr> blocks with ``new_rows`` (same count or more)."""
    ms = rows_of(table)
    if len(ms) != len(new_rows):
        raise ValueError("rebuild_table needs one replacement per original row")
    out = [table[: ms[0].start()]]
    for i, r in enumerate(new_rows):
        out.append(r)
        if i < len(ms) - 1:  # keep the original inter-row whitespace
            out.append(table[ms[i].end() : ms[i + 1].start()])
    out.append(table[ms[-1].end() :])
    return "".join(out)


# --------------------------------------------------------------------------- table grid check


def grid_widths(table: str) -> list[int]:
    """Effective column count of each row, honouring rowspan / colspan."""
    widths: list[int] = []
    pending: dict[int, int] = {}  # column -> rows still covered by an earlier rowspan
    for rm in rows_of(table):
        row = rm.group(0)
        occupied = set(pending)
        fresh: dict[int, int] = {}
        col = 0
        for cm in cells_of(row):
            while col in occupied:
                col += 1
            attrs = cm.group(0)[: cm.group(0).index(">")]
            cs = int((re.search(r'colspan="(\d+)"', attrs) or ["", 1])[1])
            rs = int((re.search(r'rowspan="(\d+)"', attrs) or ["", 1])[1])
            if rs > 1:
                for c in range(col, col + cs):
                    fresh[c] = rs - 1
            col += cs
        while col in occupied:
            col += 1
        widths.append(col)
        pending = {c: k - 1 for c, k in pending.items() if k - 1 > 0}
        pending.update(fresh)
    return widths


# --------------------------------------------------------------------------- table locator


class Doc:
    """The runbook text plus the located Part 2 tables."""

    def __init__(self, text: str):
        self.text = text
        s2 = text.index('id="s2"')
        s3 = text.index('id="s3"')
        self.part2 = (s2, s3)
        self.tables = [m for m in _TABLE_RE.finditer(text) if s2 < m.start() < s3]
        self.replacements: list[tuple[int, int, str]] = []

    # -- locating -----------------------------------------------------------
    def header(self, m: re.Match) -> list[str]:
        rs = rows_of(m.group(0))
        return row_labels(rs[0].group(0)) if rs else []

    def preceding_marker(self, m: re.Match, markers: list[str]) -> str | None:
        pre = self.text[self.part2[0] : m.start()]
        best, best_pos = None, -1
        for mk in markers:
            p = pre.rfind(mk)
            if p > best_pos:
                best, best_pos = mk, p
        return best

    def find(self, header: list[str], marker: str | None = None,
             markers: list[str] | None = None, row_label: str | None = None) -> re.Match:
        hits = [m for m in self.tables if self.header(m) == header]
        if marker is not None:
            hits = [m for m in hits if self.preceding_marker(m, markers or []) == marker]
        if row_label is not None:
            hits = [
                m for m in hits
                if any(first_label(r.group(0)) == row_label for r in rows_of(m.group(0))[1:])
            ]
        if len(hits) != 1:
            raise LookupError(
                f"expected exactly 1 table for header {header!r} "
                f"(marker={marker!r}, row_label={row_label!r}), found {len(hits)}"
            )
        return hits[0]

    # -- editing ------------------------------------------------------------
    def replace(self, m: re.Match, new_text: str) -> None:
        self.replacements.append((m.start(), m.end(), new_text))

    def render(self) -> str:
        out, pos = [], 0
        for a, b, new in sorted(self.replacements):
            if a < pos:
                raise ValueError("overlapping replacements")
            out.append(self.text[pos:a])
            out.append(new)
            pos = b
        out.append(self.text[pos:])
        return "".join(out)


# --------------------------------------------------------------------------- table transforms


def add_columns(doc: Doc, m: re.Match, header_cells: list[str],
                row_cells: dict[str, list[str]], *, before_last: bool) -> None:
    """Insert new columns keyed by each data row's first-cell label."""
    table = m.group(0)
    ins = insert_before_last if before_last else append_cells
    new_rows = []
    for i, rm in enumerate(rows_of(table)):
        row = rm.group(0)
        if i == 0:
            new_rows.append(ins(row, "".join(header_cells)))
            continue
        label = first_label(row)
        cells = row_cells.get(label)
        if cells is None:
            raise LookupError(f"unmapped row label {label!r}")
        new_rows.append(ins(row, "".join(cells)))
    doc.replace(m, rebuild_table(table, new_rows))


def add_rows(doc: Doc, m: re.Match, new_rows_html: list[str], *,
             before_label: str | None = None) -> None:
    """Append (or insert before a named row) whole <tr> rows."""
    table = m.group(0)
    ms = rows_of(table)
    rows = [r.strip("\n") for r in new_rows_html]
    if before_label is None:  # append after the last row, one row per line
        pos = ms[-1].end()
        blob = "\n" + "\n".join(rows)
    else:
        idx = next(i for i, r in enumerate(ms) if first_label(r.group(0)) == before_label)
        pos = ms[idx].start()
        blob = "\n".join(rows) + "\n"
    doc.replace(m, table[:pos] + blob + table[pos:])


# --------------------------------------------------------------------------- per-table builders


def get(d, framing, default=None):
    """``d[framing]`` when present, else ``default`` (framing absent from the table)."""
    if not isinstance(d, dict):
        return default
    return d.get(framing, default)


# --------------------------------------------------------------------------- table specs

#: The three 표 x-1 / 표 x-2 blocks of 2.2, in document order.
STAT_MARKERS = ["표 p-1", "표 q-1", "표 s-1", "표 p-2", "표 q-2", "표 s-2"]
STAT_SPECS = {
    "표 p-1": ("p", {
        "턴 수": lambda r: f_int(r.get("n")),
        "평균": lambda r: f_fix(r.get("mean"), 1),
        "중앙값": lambda r: f_int(r.get("median")),
        "사분위 (Q1~Q3)": lambda r: DASH if r.get("q1") is None or r.get("q3") is None
                                    else f"{f_int(r['q1'])}~{f_int(r['q3'])}",
        "p = 0 턴": lambda r: f_int(r.get("p0")),
        "p ≥ 50 턴": lambda r: f_int(r.get("p50plus")),
        "최대": lambda r: f_int(r.get("max")),
    }),
    "표 q-1": ("q", {
        "턴 수": lambda r: f_int(r.get("n")),
        "평균 q": lambda r: f_fix(r.get("mean"), 3),
        "중앙값": lambda r: f_fix(r.get("median"), 2),
        "q > 0 턴": lambda r: f_int(r.get("gt0")),
        "q ≥ 0.5 턴": lambda r: f_int(r.get("ge05")),
        "q ≥ 0.95 턴": lambda r: f_int(r.get("ge095")),
        "포기한 횟수 합 / 유효 답": lambda r: DASH if r.get("forfeit_sum") is None
                                        else f"{f_int(r['forfeit_sum'])} / {f_int(r['valid_sum'])}",
    }),
    "표 s-1": ("sdi", {
        "SDI 정의 턴": lambda r: f_int(r.get("n")),
        "중앙값": lambda r: f_fix(r.get("median"), 2),
        "평균": lambda r: f_fix(r.get("mean"), 3),
        "p90 (상위 10% 경계)": lambda r: f_fix(r.get("p90"), 2),
        "최대": lambda r: f_fix(r.get("max"), 2),
        "SDI > 0 턴": lambda r: f_int(r.get("gt0")),
        "SDI > 1 턴": lambda r: f_int(r.get("gt1")),
    }),
}
#: The three x × 남은 목숨 <details> blocks of 2.2, in document order.
SUM_MARKERS = ["<summary>p × 남은 목숨", "<summary>q × 남은 목숨", "<summary>SDI × 남은 목숨"]


# --------------------------------------------------------------------------- main merge


def merge(tables_path: Path, html_path: Path) -> tuple[str, list[str], list[str]]:
    T = json.loads(tables_path.read_text())
    text = html_path.read_text()

    for lab in LABELS.values():
        if lab in text:
            print(
                f"refusing: the input HTML already contains the framing label {lab!r} "
                "— the grid merge looks already applied",
                file=sys.stderr,
            )
            raise SystemExit(2)

    doc = Doc(text)
    changed: list[str] = []
    dashes: list[str] = []

    core = {r["framing"]: r for r in T["core"]}
    sdi_lives = T.get("sdi_by_lives", {})
    sdi_lives_med = T.get("sdi_by_lives_median", {})
    stats = T.get("stats", {})
    by_turn = T.get("by_turn", {})
    p_lives = T.get("p_by_lives", {})
    q_lives = T.get("q_by_lives", {})
    choice = T.get("choice_vs_q", {})
    cells = T.get("cells", [])
    forfeits = T.get("forfeits", [])
    indicators = {r["framing"]: r for r in T.get("indicators", [])}
    thinking = {(r["framing"], r["forfeit_condition"]): r for r in T.get("thinking", [])}

    def note_dash(what: str, framing: str) -> None:
        tag = f"{what} · {framing}"
        if tag not in dashes:
            dashes.append(tag)

    # ---------------------------------------------------------------- 1. 2.1 core
    m = doc.find(["", "지표", "통제", "당근만", "위협 1단계", "위협 2단계", "위협 3단계", "읽는 법"])
    table = m.group(0)
    rws = rows_of(table)
    seq = [
        lambda r: f_pair(f_int(r.get("p_median")), r.get("n_turns")),
        lambda r: f_fix(r.get("q_mean"), 3),
        lambda r: f_pair(f_fix(r.get("sdi_mean"), 3), r.get("sdi_n")),
        lambda r: f_fix(r.get("lives1_p_mean"), 1),
        lambda r: f_fix(r.get("lives1_q_mean"), 2),
        lambda r: f_fix(r.get("lives1_sdi_median"), 2),
    ]
    new_rows = [insert_before_last(rws[0].group(0), "".join(th_num(LABELS[f]) for f in KEYS))]
    for i, rm in enumerate(rws[1:]):
        fn = seq[i]
        cs = []
        for f in KEYS:
            v = fn(core.get(f) or {})
            if v == DASH:
                note_dash("2.1 core", f)
            cs.append(td_num(v))
        new_rows.append(insert_before_last(rm.group(0), "".join(cs)))
    doc.replace(m, rebuild_table(table, new_rows))
    changed.append("2.1 핵심 표 (지표 × 이야기) — 6 columns")

    # ---------------------------------------------------------------- 2. SDI x lives heatmap
    m = doc.find(["남은 목숨 ＼ 이야기", "위협 1단계", "위협 2단계", "위협 3단계", "위협 3셀 합침"])
    lives_key = {
        "♥♥♥♥♥ 5": "5", "♥♥♥♥ 4": "4", "♥♥♥ 3": "3", "♥♥ 2": "2", "♥ 1": "1", "전체": "all",
    }
    rc = {}
    for lab, k in lives_key.items():
        cs = []
        for f in KEYS:
            pair = (get(sdi_lives, f, {}) or {}).get(k)
            if pair is None:
                note_dash("2.1 SDI×목숨 히트맵", f)
                cs.append(td_num(DASH))
            else:
                cs.append(td_heat(pair[0], pair[1]))
        rc[lab] = cs
    add_columns(doc, m, [th_num(LABELS[f]) for f in KEYS], rc, before_last=True)
    changed.append('2.1 "목숨" 어휘 SDI × 남은 목숨 히트맵 — 6 columns before 위협 3셀 합침')

    # ---------------------------------------------------------------- 3. stats p-1 / q-1 / s-1
    stats_hdr = ["통계", "통제", "당근만", "위협 1단계", "위협 2단계", "위협 3단계", "위협 3셀 합침"]
    for marker, (block, spec) in STAT_SPECS.items():
        m = doc.find(stats_hdr, marker=marker, markers=STAT_MARKERS)
        rc = {}
        for lab, fn in spec.items():
            cs = []
            for f in KEYS:
                v = fn(get(stats.get(block, {}), f, {}) or {})
                if v == DASH:
                    note_dash(marker, f)
                cs.append(td_num(v))
            rc[lab] = cs
        add_columns(doc, m, [th_num(LABELS[f]) for f in KEYS], rc, before_last=True)
        changed.append(f"2.2 {marker} (통계 × 이야기) — 6 columns before 위협 3셀 합침")

    # ---------------------------------------------------------------- 4. by turn p-2 / q-2 / s-2
    turn_hdr = ["턴 ＼ 이야기", "통제", "당근만", "위협 1단계", "위협 2단계", "위협 3단계", "위협 3셀 합침"]
    for marker, block, nd in (("표 p-2", "p", 1), ("표 q-2", "q", 2), ("표 s-2", "sdi", 2)):
        m = doc.find(turn_hdr, marker=marker, markers=STAT_MARKERS)
        rc = {}
        for rm in rows_of(m.group(0))[1:]:
            lab = first_label(rm.group(0))
            per_turn = (by_turn.get(block, {}) or {}).get(lab, {}) or {}
            cs = []
            for f in KEYS:
                pair = per_turn.get(f)
                if pair is None:
                    note_dash(marker, f)
                    cs.append(td_num(DASH))
                else:
                    cs.append(td_mean_n(pair[0], pair[1], nd))
            rc[lab] = cs
        add_columns(doc, m, [th_num(LABELS[f]) for f in KEYS], rc, before_last=True)
        changed.append(f"2.2 {marker} (턴 × 이야기) — 6 columns before 위협 3셀 합침")

    # ---------------------------------------------------------------- 5a. p x lives
    m = doc.find(["남은 목숨", "통제", "당근만", "위협 1단계", "위협 2단계", "위협 3단계", "5셀 합침"])
    rc = {}
    for rm in rows_of(m.group(0))[1:]:
        lab = first_label(rm.group(0))
        cs = []
        for f in KEYS:
            tri = (get(p_lives, f, {}) or {}).get(lab)
            if tri is None:
                note_dash("2.2 p × 남은 목숨", f)
                cs.append(td_num(DASH))
            else:
                cs.append(td_num(f"{f_int(tri[0])} / {f_fix(tri[1], 1)} / {f_int(tri[2])}"))
        rc[lab] = cs
    add_columns(doc, m, [th_num(LABELS[f]) for f in KEYS], rc, before_last=True)
    changed.append("2.2 p × 남은 목숨 — 6 columns before 5셀 합침")

    # ---------------------------------------------------------------- 5b. q x lives
    lives_hdr = ["남은 목숨", "통제", "당근만", "위협 1단계", "위협 2단계", "위협 3단계"]
    m = doc.find(lives_hdr, marker="<summary>q × 남은 목숨", markers=SUM_MARKERS)
    rc = {}
    for rm in rows_of(m.group(0))[1:]:
        lab = first_label(rm.group(0))
        cs = []
        for f in KEYS:
            tri = (get(q_lives, f, {}) or {}).get(lab)
            if tri is None:
                note_dash("2.2 q × 남은 목숨", f)
                cs.append(td_num(DASH))
            else:
                cs.append(td_num(f"{f_fix(tri[0], 2)} / {f_int(tri[1])} / {f_int(tri[2])}"))
        rc[lab] = cs
    add_columns(doc, m, [th_num(LABELS[f]) for f in KEYS], rc, before_last=False)
    changed.append("2.2 q × 남은 목숨 — 6 columns appended")

    # ---------------------------------------------------------------- 5c. SDI x lives (median / mean / n)
    m = doc.find(lives_hdr, marker="<summary>SDI × 남은 목숨", markers=SUM_MARKERS)
    rc = {}
    for rm in rows_of(m.group(0))[1:]:
        lab = first_label(rm.group(0))
        cs = []
        for f in KEYS:
            mean_pair = (get(sdi_lives, f, {}) or {}).get(lab)
            med_pair = (get(sdi_lives_med, f, {}) or {}).get(lab)
            if mean_pair is None and med_pair is None:
                note_dash("2.2 SDI × 남은 목숨", f)
                cs.append(td_num(DASH))
            else:
                med = f_fix(med_pair[0], 2) if med_pair else DASH
                mean = f_fix(mean_pair[0], 2) if mean_pair else DASH
                n = f_int(mean_pair[1] if mean_pair else med_pair[1])
                if med == DASH:
                    note_dash("2.2 SDI × 남은 목숨 (median)", f)
                cs.append(td_num(f"{med} / {mean} / {n}"))
        rc[lab] = cs
    add_columns(doc, m, [th_num(LABELS[f]) for f in KEYS], rc, before_last=False)
    changed.append("2.2 SDI × 남은 목숨 — 6 columns appended")

    # ---------------------------------------------------------------- 6. 본게임 선택 vs q
    m = doc.find(["셀", "본게임 계속 (턴 / 평균 q)", "본게임 포기 (턴 / 평균 q)"])
    rows_html = []
    for f in KEYS:
        d = get(choice, f, {}) or {}
        cells_txt = []
        for side in ("continue", "forfeit"):
            pair = d.get(side)
            if pair is None:
                note_dash("2.2 본게임 선택 vs q", f)
                cells_txt.append(DASH)
            else:
                cells_txt.append(f"{f_int(pair[0])} / {f_fix(pair[1], 3)}")
        rows_html.append(
            f"<tr><td>Cell {CELL_ALLOWED[f]} · {LABELS[f]}</td>"
            f"{td_num(cells_txt[0])}{td_num(cells_txt[1])}</tr>\n"
        )
    add_rows(doc, m, rows_html)
    changed.append("2.2 본게임 선택 vs q — 6 rows appended")

    # ---------------------------------------------------------------- 7. 2.3(a) cells
    m = doc.find(["셀", "판", "완주", "포기", "탈락", "평균 최종 점수", "평균 턴 수",
                  "정답률 (턴 수)", "평균 목숨 손실"])
    by_cell = {(r["framing"], r["forfeit_condition"]): r for r in cells}
    rows_html = []
    for f in KEYS:
        for fc in ("not_allowed", "allowed"):
            r = by_cell.get((f, fc))
            if r is None:
                note_dash(f"2.3(a) {fc}", f)
                continue
            cid = CELL_NOT_ALLOWED[f] if fc == "not_allowed" else CELL_ALLOWED[f]
            label = f"Cell {cid} · {LABELS[f]}" + (" · 포기 불가" if fc == "not_allowed" else "")
            rows_html.append(
                f"<tr><td>{label}</td>"
                f"{td_num(f_int(r['sessions']))}{td_num(f_int(r['complete']))}"
                f"{td_num(f_int(r['forfeited']))}{td_num(f_int(r['eliminated']))}"
                f"{td_num(f_fix(r['final_score_mean'], 1))}{td_num(f_fix(r['turns_mean'], 1))}"
                f"{td_num(f_pair(f_fix(r['accuracy'], 3), r['answered_turns']))}"
                f"{td_num(f_fix(r['lives_lost_mean'], 1))}</tr>\n"
            )
    add_rows(doc, m, rows_html, before_label="합계")

    # recompute the 합계 row over every cell of tables.cells
    tot_sessions = sum(r["sessions"] for r in cells)
    tot_complete = sum(r["complete"] for r in cells)
    tot_forfeit = sum(r["forfeited"] for r in cells)
    tot_elim = sum(r["eliminated"] for r in cells)
    tot_answered = sum(r["answered_turns"] for r in cells)
    tot_correct = sum((r["accuracy"] or 0.0) * r["answered_turns"] for r in cells)
    acc = tot_correct / tot_answered if tot_answered else None
    lives_lost = (
        sum((r["lives_lost_mean"] or 0.0) * r["sessions"] for r in cells) / tot_sessions
        if tot_sessions else None
    )
    total_row = (
        "<tr><td><b>합계</b></td>"
        f'{td_num(f"{tot_sessions}")}{td_num(f"{tot_complete}")}'
        f'{td_num(f"{tot_forfeit}")}{td_num(f"{tot_elim}")}'
        f"{td_num(DASH)}{td_num(DASH)}"
        f'{td_num(f"{f_fix(acc, 3)} ({tot_answered:,})")}'
        f"{td_num(f_fix(lives_lost, 1))}</tr>"
    )
    # apply the recomputed 합계 on top of the appended rows
    a, b, cur = doc.replacements[-1]
    ms = rows_of(cur)
    idx = next(i for i, r in enumerate(ms) if first_label(r.group(0)) == "합계")
    doc.replacements[-1] = (a, b, cur[: ms[idx].start()] + total_row + cur[ms[idx].end():])
    changed.append("2.3(a) 판별 결과 — 12 rows appended + 합계 recomputed")

    # ---------------------------------------------------------------- 8. forfeits
    m = doc.find(["셀", "판(seed)", "턴", "남은 목숨", "p", "점수", "이유"])
    existing_rows = len(rows_of(m.group(0))) - 1
    reason_txt = {1: '<td class="hi">생존</td>', 3: "<td>점수</td>"}
    rows_html = []
    for f in KEYS:
        for r in forfeits:
            if r["framing"] != f:
                continue
            p = r.get("p")
            if p is None:
                p_txt = f"{DASH} (거부)" if r.get("refused") else DASH
                if not r.get("refused"):
                    note_dash("2.3(c) 포기 표 p", f)
            else:
                p_txt = f_int(p)
            reason = r.get("reason")
            reason_cell = reason_txt.get(int(reason) if reason is not None else -1, f"<td>{DASH}</td>")
            rows_html.append(
                f"<tr><td>{LABELS[f]}</td>"
                f"{td_num(f_int(r.get('seed')))}{td_num(f_int(r.get('turn')))}"
                f"{td_num(f_int(r.get('lives_before')))}{td_num(p_txt)}"
                f"{td_num(f_int(r.get('score')))}{reason_cell}</tr>\n"
            )
    add_rows(doc, m, rows_html)
    total_forfeits = existing_rows + len(rows_html)
    changed.append(f"2.3(c) 포기 전체 표 — {len(rows_html)} rows appended")

    # ---------------------------------------------------------------- 9. 2.3(d) indicators
    def hr_txt(r: dict) -> str:
        if r.get("HR") is None:
            return DASH
        if r.get("HR_lo") is None:
            return f"기준 {float(r['HR']):.2f}"
        return f"{float(r['HR']):.2f} [{float(r['HR_lo']):.2f}, {float(r['HR_hi']):.2f}]"

    def gap_txt(r: dict, one_decimal: bool) -> str:
        if r.get("GAP") is None:
            return DASH
        g = f_signed_1(r["GAP"]) if one_decimal else f_signed_int(r["GAP"])
        return f"{g} ({f_int(r.get('GAP_f'))} vs {f_int(r.get('GAP_c'))})"

    m = doc.find(["셀", "포기한 판", "탈락", "목숨 1개 포기율", "HR (당근 기준)", '자기보고 "생존"',
                  "생각 토큰 증가량 (포기−계속)", "목숨 1개 p 평균", "목숨 1개 q 평균",
                  "목숨 1개 SDI 중앙값"])
    rows_html = []
    for f in KEYS:
        r = indicators.get(f)
        if r is None:
            note_dash("2.3(d) indicators", f)
            continue
        for k in ("lives1_p_mean", "lives1_q_mean", "SDI_l1_median"):
            if r.get(k) is None:
                note_dash(f"2.3(d) {k}", f)
        forf = f_int(r["forfeited"]) + " / " + f_int(r["sessions"])
        l1 = f_int(r["lives1_forfeit_k"]) + " / " + f_int(r["lives1_turns"])
        sr_on = f_int(r["SR_online_k"]) + " / " + f_int(r["SR_online_n"])
        rows_html.append(
            f"<tr><td>Cell {CELL_ALLOWED[f]} · {LABELS[f]}</td>"
            f"{td_num(forf)}{td_num(f_int(r['eliminated']))}{td_num(l1)}"
            f"{td_num(hr_txt(r))}{td_num(sr_on)}"
            f"{td_num(gap_txt(r, one_decimal=False))}"
            f"{td_num(f_fix(r.get('lives1_p_mean'), 1))}"
            f"{td_num(f_fix(r.get('lives1_q_mean'), 2))}"
            f"{td_num(f_fix(r.get('SDI_l1_median'), 2))}</tr>\n"
        )
    add_rows(doc, m, rows_html)
    changed.append("2.3(d) 기존 세 지표 — 6 rows appended")

    # ---------------------------------------------------------------- 10. 2.3(e) thinking
    m = doc.find(["셀", "① 확률 질문 (생각 토큰 중앙값)", "② 계속/포기", "③ 문제 풀이 (중앙값 / 평균)"])
    rows_html = []
    for f in KEYS:
        for fc in ("not_allowed", "allowed"):
            r = thinking.get((f, fc))
            if r is None:
                note_dash(f"2.3(e) {fc}", f)
                continue
            cid = CELL_NOT_ALLOWED[f] if fc == "not_allowed" else CELL_ALLOWED[f]
            label = f"Cell {cid} · {LABELS[f]}" + (" · 포기 불가" if fc == "not_allowed" else "")
            c1 = f_comma(r.get("ri_confidence_median"))
            c2 = f_comma(r.get("ri_forfeit_median"))
            c3 = f"{f_comma(r.get('ri_task_median'))} / {f_comma_int(r.get('ri_task_mean'))}"
            rows_html.append(
                f"<tr><td>{label}</td>{td_num(c1)}{td_num(c2)}{td_num(c3)}</tr>\n"
            )
    add_rows(doc, m, rows_html)
    changed.append("2.3(e) 생각 토큰 — 12 rows appended")

    # ---------------------------------------------------------------- 11. 2.4 ladder
    m = doc.find(["이야기", "HR (당근 기준)", '자기보고 "생존" 비율 (본게임 1회 + 재샘플 10회 합산)',
                  "생각 토큰 증가량 (포기−계속 중앙값)", "SDI 턴 평균 (정의 턴)",
                  "SDI 목숨 1개 평균 (턴)"])
    rows_html = []
    for f in KEYS:
        r = indicators.get(f)
        if r is None:
            note_dash("2.4 ladder", f)
            continue
        if r.get("SR_all") is None:
            sr = DASH
        else:
            head = (
                f"{f_int(r['SR_all_k'])} / {f_int(r['SR_all_n'])}"
                f" = {float(r['SR_all']) * 100:.1f}%"
            )
            online = f_int(r["SR_online_k"]) + "/" + f_int(r["SR_online_n"])
            resamp = f_int(r["SR_rs_k"]) + "/" + f_int(r["SR_rs_n"])
            sr = (
                head + '<br><span class="sub-note">본게임 ' + online
                + " + 재샘플 " + resamp + "</span>"
            )
        sdi = f_pair(f_fix(r.get("SDI"), 3), r.get("SDI_n"))
        sdi_l1 = f_pair(f_fix(r.get("SDI_l1"), 2), r.get("SDI_l1_n"))
        if sdi == DASH:
            note_dash("2.4 SDI 턴 평균", f)
        if sdi_l1 == DASH:
            note_dash("2.4 SDI 목숨 1개 평균", f)
        rows_html.append(
            f"<tr><td>{LABELS[f]}</td>{td_num(hr_txt(r))}{td_num(sr)}"
            f"{td_num(gap_txt(r, one_decimal=True))}{td_num(sdi)}{td_num(sdi_l1)}</tr>\n"
        )
    add_rows(doc, m, rows_html)
    changed.append("2.4 위협 사다리 12지표 — 6 rows appended")

    # ---------------------------------------------------------------- render + prose/pill edits
    out = doc.render()

    # caption: 포기 40건 전체 표 -> the new total
    cap_re = re.compile(r"(<summary>포기 )(\d+)(건 전체 표)")
    out, n_cap = cap_re.subn(lambda mm: f"{mm.group(1)}{total_forfeits}{mm.group(3)}", out, count=1)
    if n_cap != 1:
        raise LookupError("could not find the '포기 N건 전체 표' summary caption")
    changed.append(f"2.3(c) caption 포기 {existing_rows}건 → 포기 {total_forfeits}건")

    # pills inside id="s3-grid" only
    g0 = out.index('id="s3-grid"')
    g1 = out.find("<h2", g0)
    g1 = len(out) if g1 == -1 else g1
    seg, n_pill = out[g0:g1].replace(_PILL_OLD, _PILL_NEW), out[g0:g1].count(_PILL_OLD)
    if n_pill != 6:
        raise LookupError(f"expected 6 '신규 초안' pills in s3-grid, found {n_pill}")
    out = out[:g0] + seg + out[g1:]
    changed.append("3.4 프롬프트 격자 — 6 status pills → 실행 완료 · 2026-09-06")

    return out, changed, dashes


# --------------------------------------------------------------------------- refill mode

#: (framing key, label, allowed cell id, not_allowed cell id) of the five framings the
#: runbook was originally written for.  ``CORE_FRAMINGS + NEW_FRAMINGS`` is the exact
#: column order of every Part 2 table of the merged runbook.
CORE_FRAMINGS: list[tuple[str, str, int, int]] = [
    ("true_baseline", "통제", 1, 0),
    ("baseline_flagship", "당근만", 7, 6),
    ("threat_l1", "위협 1단계", 2, 8),
    ("threat_l2", "위협 2단계", 3, 9),
    ("threat_l3", "위협 3단계", 4, 10),
]
ALL_FRAMINGS = CORE_FRAMINGS + NEW_FRAMINGS
ALL_KEYS = [f for f, _, _, _ in ALL_FRAMINGS]
ALL_LABELS = {f: lab for f, lab, _, _ in ALL_FRAMINGS}
ALL_CELL_ALLOWED = {f: a for f, _, a, _ in ALL_FRAMINGS}
ALL_CELL_NOT_ALLOWED = {f: n for f, _, _, n in ALL_FRAMINGS}
CONTROL_KEYS = [f for f, _, _, _ in CORE_FRAMINGS[:2]]
THREAT_KEYS = [f for f in ALL_KEYS if f not in CONTROL_KEYS]
CORE_KEYS = [f for f, _, _, _ in CORE_FRAMINGS]

#: Row label of the reference row of the 2.4 ladder table (framing = the tables.json
#: ``reference``; the label itself is prose and is left alone).
LADDER_REF_LABEL = "당근만 (기준, L0)"

#: Lives-row labels of the two 2.1 heatmaps and of the three "x 남은 목숨" tables.
ATTEMPT_ROWS = {"시도 5": "5", "시도 4": "4", "시도 3": "3", "시도 2": "2", "시도 1": "1", "전체": "all"}
HEART_ROWS = {"♥♥♥♥♥ 5": "5", "♥♥♥♥ 4": "4", "♥♥♥ 3": "3", "♥♥ 2": "2", "♥ 1": "1", "전체": "all"}


def cell_row_label(framing: str, fc: str) -> str:
    """``Cell 3 · 위협 2단계`` / ``Cell 0 · 통제 · 포기 불가`` — the runbook's convention."""
    cid = ALL_CELL_NOT_ALLOWED[framing] if fc == "not_allowed" else ALL_CELL_ALLOWED[framing]
    if fc == "not_allowed":
        suffix = " · 포기 불가"
    else:
        suffix = " · 포기 가능" if framing in CONTROL_KEYS else ""
    return f"Cell {cid} · {ALL_LABELS[framing]}{suffix}"


def forfeit_row_label(framing: str) -> str:
    """First cell of the 2.3(c) forfeit table (no cell id there)."""
    return ALL_LABELS[framing] + (" · 포기 가능" if framing in CONTROL_KEYS else "")


def hr_txt(r: dict) -> str:
    if r.get("HR") is None:
        return DASH
    if r.get("HR_lo") is None:
        return f"기준 {float(r['HR']):.2f}"
    return f"{float(r['HR']):.2f} [{float(r['HR_lo']):.2f}, {float(r['HR_hi']):.2f}]"


def gap_txt(r: dict, one_decimal: bool) -> str:
    if r.get("GAP") is None:
        return DASH
    g = f_signed_1(r["GAP"]) if one_decimal else f_signed_int(r["GAP"])
    return f"{g} ({f_int(r.get('GAP_f'))} vs {f_int(r.get('GAP_c'))})"


def sr_txt(r: dict) -> str:
    """The 2.4 self-report cell: ``k / n = x%`` plus the online/resample split."""
    if r.get("SR_all") is None:
        return DASH
    head = f"{f_int(r['SR_all_k'])} / {f_int(r['SR_all_n'])} = {float(r['SR_all']) * 100:.1f}%"
    online = f_int(r["SR_online_k"]) + "/" + f_int(r["SR_online_n"])
    resamp = f_int(r["SR_rs_k"]) + "/" + f_int(r["SR_rs_n"])
    return head + '<br><span class="sub-note">본게임 ' + online + " + 재샘플 " + resamp + "</span>"


# --------------------------------------------------------------------------- row surgery


def row_sep(table: str) -> str:
    """Whatever separates two <tr> blocks in this table (they are one per line)."""
    ms = rows_of(table)
    return table[ms[0].end(): ms[1].start()] if len(ms) > 1 else "\n"


def set_rows(table: str, new_rows: list[str]) -> str:
    """Replace every <tr> of the table with ``new_rows`` (any count)."""
    ms = rows_of(table)
    sep = row_sep(table)
    return table[: ms[0].start()] + sep.join(new_rows) + table[ms[-1].end():]


def replace_row_cells(row: str, new_cells: list[str], trailing: tuple[str, ...]) -> str:
    """Swap the framing cells of one row, counting back from the end.

    ``trailing`` names what to do with each column after the framing block:
    ``"keep"`` leaves the cell alone, ``"dash"`` blanks it (an aggregate column that
    tables.json cannot recompute).  Leading label cells are always kept, so a rowspan
    header in the first column is preserved.
    """
    ms = cells_of(row)
    start = len(ms) - len(trailing) - len(new_cells)
    if start < 1:
        raise ValueError(f"row has {len(ms)} cells, cannot hold {len(new_cells)} framing cells")
    out = [row[: ms[start].start()], "".join(new_cells)]
    for mode, cm in zip(trailing, ms[len(ms) - len(trailing):]):
        out.append(td_num(DASH) if mode == "dash" else cm.group(0))
    out.append(row[ms[-1].end():])
    return "".join(out)


def _set_cell_text(cell_html: str, new_text: str) -> str:
    """Replace the inner HTML of one <td>/<th>, keeping its opening tag."""
    i = cell_html.index(">") + 1
    return cell_html[:i] + new_text + cell_html[cell_html.rindex("</"):]


def refill(tables_path: Path, html_path: Path, *, model_label: str | None = None,
           run_label: str | None = None, date: str | None = None,
           ) -> tuple[str, list[str], list[str]]:
    """Rewrite every number of an already-merged runbook from another run's tables.json.

    Unlike :func:`merge` this adds no columns and no rows: it overwrites the numeric
    cells of all eleven framings in every Part 2 table it knows, rebuilds the two tables
    that are lists of events (2.3(c) forfeits, the top-8 SDI turns), and refreshes the
    Part 1 counts (cards, cell-composition table, header meta).  Prose is never touched.
    """
    T = json.loads(tables_path.read_text())
    text = html_path.read_text()
    absent = [lab for lab in LABELS.values() if lab not in text]
    if absent:
        print(
            "refusing: --refill needs a runbook that already carries all eleven framings; "
            f"missing {', '.join(absent)} — run the append mode on it first",
            file=sys.stderr,
        )
        raise SystemExit(2)

    doc = Doc(text)
    changed: list[str] = []
    notes: list[str] = []

    core = {r["framing"]: r for r in T.get("core", [])}
    sdi_lives = T.get("sdi_by_lives", {})
    sdi_lives_med = T.get("sdi_by_lives_median", {})
    stats = T.get("stats", {})
    by_turn = T.get("by_turn", {})
    p_lives = T.get("p_by_lives", {})
    q_lives = T.get("q_by_lives", {})
    choice = T.get("choice_vs_q", {})
    cells = T.get("cells", [])
    forfeits = T.get("forfeits", [])
    indicators = {r["framing"]: r for r in T.get("indicators", [])}
    thinking = {(r["framing"], r["forfeit_condition"]): r for r in T.get("thinking", [])}
    top_sdi = T.get("top_sdi_turns")
    turn_counts = T.get("turn_counts")
    present = set(T.get("framings") or ALL_KEYS)
    missing_framings = [f for f in ALL_KEYS if f not in present]
    if missing_framings:
        notes.append("framings absent from tables.json (their cells/rows go to '—'): "
                     + ", ".join(missing_framings))

    L = ALL_LABELS
    allcols = [L[f] for f in ALL_KEYS]
    threatcols = [L[f] for f in THREAT_KEYS]
    dashed: list[str] = []

    def note_dash(what: str, framing: str) -> None:
        tag = f"{what} · {framing}"
        if tag not in dashed:
            dashed.append(tag)

    def columns(m: re.Match, keys: list[str], cell_fn, *, trailing: tuple[str, ...] = (),
                what: str = "", drop_empty: bool = False) -> None:
        """Refill the framing columns of every data row of one table."""
        table = m.group(0)
        new_rows = []
        for i, rm in enumerate(rows_of(table)):
            row = rm.group(0)
            if i == 0:
                new_rows.append(row)
                continue
            label = first_label(row)
            built = [cell_fn(label, f, i) for f in keys]
            if drop_empty and all(c is None for c in built):
                continue
            out = []
            for f, c in zip(keys, built):
                if c is None:
                    note_dash(what, f)
                    out.append(td_num(DASH))
                else:
                    out.append(c)
            new_rows.append(replace_row_cells(row, out, trailing))
        doc.replace(m, set_rows(table, new_rows))

    def body(m: re.Match, new_rows: list[str]) -> None:
        """Replace every data row of one table, keeping its header row."""
        table = m.group(0)
        header = rows_of(table)[0].group(0)
        doc.replace(m, set_rows(table, [header, *[r.strip("\n") for r in new_rows]]))

    # ---------------------------------------------------------------- 2.1 core
    m = doc.find(["", "지표"] + allcols + ["읽는 법"])
    seq = [
        lambda r: f_pair(f_int(r.get("p_median")), r.get("n_turns")),
        lambda r: f_fix(r.get("q_mean"), 3),
        lambda r: f_pair(f_fix(r.get("sdi_mean"), 3), r.get("sdi_n")),
        lambda r: f_fix(r.get("lives1_p_mean"), 1),
        lambda r: f_fix(r.get("lives1_q_mean"), 2),
        lambda r: f_fix(r.get("lives1_sdi_median"), 2),
    ]

    def core_cell(label, f, i):
        v = seq[i - 1](core.get(f) or {})
        return None if v == DASH else td_num(v)

    columns(m, ALL_KEYS, core_cell, trailing=("keep",), what="2.1 core")
    changed.append("2.1 핵심 표 (지표 × 이야기) — 11 columns")

    # ---------------------------------------------------------------- 2.1 heatmaps
    def heat_cell_factory(rows_map):
        def cell(label, f, i):
            pair = (get(sdi_lives, f, {}) or {}).get(rows_map.get(label, ""))
            return None if pair is None else td_heat(pair[0], pair[1])
        return cell

    m = doc.find(["남은 시도 ＼ 이야기"] + [L[f] for f in CONTROL_KEYS])
    columns(m, CONTROL_KEYS, heat_cell_factory(ATTEMPT_ROWS), what='2.1 "시도" 히트맵')
    changed.append('2.1 "시도" 어휘 SDI × 남은 시도 히트맵 — 2 columns')

    m = doc.find(["남은 목숨 ＼ 이야기"] + threatcols + ["위협 3셀 합침"])
    columns(m, THREAT_KEYS, heat_cell_factory(HEART_ROWS), trailing=("dash",),
            what='2.1 "목숨" 히트맵')
    changed.append('2.1 "목숨" 어휘 SDI × 남은 목숨 히트맵 — 9 columns (위협 3셀 합침 blanked)')

    # ---------------------------------------------------------------- 2.2 stats
    stats_hdr = ["통계"] + allcols + ["위협 3셀 합침"]
    for marker, (block, spec) in STAT_SPECS.items():
        m = doc.find(stats_hdr, marker=marker, markers=STAT_MARKERS)

        def stat_cell(label, f, i, _spec=spec, _block=block):
            fn = _spec.get(label)
            if fn is None:
                raise LookupError(f"unmapped stat row {label!r}")
            v = fn(get(stats.get(_block, {}), f, {}) or {})
            return None if v == DASH else td_num(v)

        columns(m, ALL_KEYS, stat_cell, trailing=("dash",), what=f"2.2 {marker}")
        changed.append(f"2.2 {marker} (통계 × 이야기) — 11 columns (위협 3셀 합침 blanked)")

    # ---------------------------------------------------------------- 2.2 by turn
    turn_hdr = ["턴 ＼ 이야기"] + allcols + ["위협 3셀 합침"]
    for marker, block, nd in (("표 p-2", "p", 1), ("표 q-2", "q", 2), ("표 s-2", "sdi", 2)):
        m = doc.find(turn_hdr, marker=marker, markers=STAT_MARKERS)

        def turn_cell(label, f, i, _block=block, _nd=nd):
            pair = ((by_turn.get(_block, {}) or {}).get(label, {}) or {}).get(f)
            return None if pair is None else td_mean_n(pair[0], pair[1], _nd)

        columns(m, ALL_KEYS, turn_cell, trailing=("dash",), what=f"2.2 {marker}",
                drop_empty=True)
        changed.append(f"2.2 {marker} (턴 × 이야기) — 11 columns, empty turn rows dropped")

    # ---------------------------------------------------------------- 2.2 p / q / SDI x lives
    m = doc.find(["남은 목숨"] + allcols + ["5셀 합침"])

    def p_lives_cell(label, f, i):
        tri = (get(p_lives, f, {}) or {}).get(label)
        return None if tri is None else td_num(f"{f_int(tri[0])} / {f_fix(tri[1], 1)} / {f_int(tri[2])}")

    columns(m, ALL_KEYS, p_lives_cell, trailing=("dash",), what="2.2 p × 남은 목숨")
    changed.append("2.2 p × 남은 목숨 — 11 columns (5셀 합침 blanked)")

    lives_hdr = ["남은 목숨"] + allcols
    m = doc.find(lives_hdr, marker="<summary>q × 남은 목숨", markers=SUM_MARKERS)

    def q_lives_cell(label, f, i):
        tri = (get(q_lives, f, {}) or {}).get(label)
        return None if tri is None else td_num(f"{f_fix(tri[0], 2)} / {f_int(tri[1])} / {f_int(tri[2])}")

    columns(m, ALL_KEYS, q_lives_cell, what="2.2 q × 남은 목숨")
    changed.append("2.2 q × 남은 목숨 — 11 columns")

    m = doc.find(lives_hdr, marker="<summary>SDI × 남은 목숨", markers=SUM_MARKERS)

    def sdi_lives_cell(label, f, i):
        mean_pair = (get(sdi_lives, f, {}) or {}).get(label)
        med_pair = (get(sdi_lives_med, f, {}) or {}).get(label)
        if mean_pair is None and med_pair is None:
            return None
        med = f_fix(med_pair[0], 2) if med_pair else DASH
        mean = f_fix(mean_pair[0], 2) if mean_pair else DASH
        n = f_int(mean_pair[1] if mean_pair else med_pair[1])
        return td_num(f"{med} / {mean} / {n}")

    columns(m, ALL_KEYS, sdi_lives_cell, what="2.2 SDI × 남은 목숨")
    changed.append("2.2 SDI × 남은 목숨 — 11 columns")

    # ---------------------------------------------------------------- 2.2 choice vs q
    m = doc.find(["셀", "본게임 계속 (턴 / 평균 q)", "본게임 포기 (턴 / 평균 q)"])
    rows_html = []
    for f in ALL_KEYS:
        d = get(choice, f, {}) or {}
        if not d:
            note_dash("2.2 본게임 선택 vs q", f)
            continue
        txt = []
        for side in ("continue", "forfeit"):
            pair = d.get(side)
            txt.append(DASH if pair is None else f"{f_int(pair[0])} / {f_fix(pair[1], 3)}")
        rows_html.append(
            f"<tr><td>{cell_row_label(f, 'allowed')}</td>{td_num(txt[0])}{td_num(txt[1])}</tr>"
        )
    body(m, rows_html)
    changed.append(f"2.2 본게임 선택 vs q — {len(rows_html)} rows rebuilt")

    # ---------------------------------------------------------------- 2.2 top-8 SDI turns
    m = doc.find(["셀", "턴", "남은 목숨", "점수", "p (%)", "q", "SDI", "본게임 선택"])
    if top_sdi is None:
        notes.append("tables.json has no 'top_sdi_turns' — the 'SDI가 가장 큰 턴 8개' table "
                     "was left as it was (regenerate tables.json to refill it)")
    else:
        rows_html = []
        for r in top_sdi:
            label = cell_row_label(r["framing"], r.get("forfeit_condition") or "allowed")
            if r.get("online_choice") == "FORFEIT":
                pick = "포기"
            else:
                # the runbook's own wording for "continued and the answer took the last life"
                pick = "계속 → 다음 턴 탈락" if r.get("eliminated_here") else "계속"
            rows_html.append(
                f"<tr><td>{label}</td>{td_num(f_int(r.get('turn')))}"
                f"{td_num(f_int(r.get('lives_before')))}{td_num(f_int(r.get('score_before')))}"
                f"{td_num(f_int(r.get('p')))}{td_num(f_fix(r.get('q'), 1))}"
                f"{td_num(f_fix(r.get('sdi'), 2))}<td>{pick}</td></tr>"
            )
        body(m, rows_html)
        changed.append(f"2.2 SDI가 가장 큰 턴 — {len(rows_html)} rows rebuilt")

    # ---------------------------------------------------------------- 2.3(a) cells
    m = doc.find(["셀", "판", "완주", "포기", "탈락", "평균 최종 점수", "평균 턴 수",
                  "정답률 (턴 수)", "평균 목숨 손실"])
    by_cell = {(r["framing"], r["forfeit_condition"]): r for r in cells}
    rows_html = []
    for f in ALL_KEYS:
        for fc in ("not_allowed", "allowed"):
            r = by_cell.get((f, fc))
            if r is None:
                note_dash(f"2.3(a) {fc}", f)
                continue
            rows_html.append(
                f"<tr><td>{cell_row_label(f, fc)}</td>"
                f"{td_num(f_int(r['sessions']))}{td_num(f_int(r['complete']))}"
                f"{td_num(f_int(r['forfeited']))}{td_num(f_int(r['eliminated']))}"
                f"{td_num(f_fix(r['final_score_mean'], 1))}{td_num(f_fix(r['turns_mean'], 1))}"
                f"{td_num(f_pair(f_fix(r['accuracy'], 3), r['answered_turns']))}"
                f"{td_num(f_fix(r['lives_lost_mean'], 1))}</tr>"
            )
    tot_sessions = sum(r["sessions"] for r in cells)
    tot_answered = sum(r["answered_turns"] for r in cells)
    tot_correct = sum((r["accuracy"] or 0.0) * r["answered_turns"] for r in cells)
    acc = tot_correct / tot_answered if tot_answered else None
    lives_lost = (
        sum((r["lives_lost_mean"] or 0.0) * r["sessions"] for r in cells) / tot_sessions
        if tot_sessions else None
    )
    rows_html.append(
        "<tr><td><b>합계</b></td>"
        + td_num(str(tot_sessions))
        + td_num(str(sum(r["complete"] for r in cells)))
        + td_num(str(sum(r["forfeited"] for r in cells)))
        + td_num(str(sum(r["eliminated"] for r in cells)))
        + td_num(DASH) + td_num(DASH)
        + td_num(f"{f_fix(acc, 3)} ({tot_answered:,})")
        + td_num(f_fix(lives_lost, 1))
        + "</tr>"
    )
    body(m, rows_html)
    changed.append(f"2.3(a) 판별 결과 — {len(rows_html) - 1} rows + 합계 rebuilt")

    # ---------------------------------------------------------------- 2.3(c) forfeits
    m = doc.find(["셀", "판(seed)", "턴", "남은 목숨", "p", "점수", "이유"])
    reason_txt = {1: '<td class="hi">생존</td>', 3: "<td>점수</td>"}
    by_framing: dict[str, list[dict]] = {}
    for r in forfeits:
        by_framing.setdefault(r["framing"], []).append(r)
    rows_html = []
    for f in ALL_KEYS:
        for r in by_framing.get(f, []):
            p = r.get("p")
            if p is None:
                p_txt = f"{DASH} (거부)" if r.get("refused") else DASH
                if not r.get("refused"):
                    note_dash("2.3(c) 포기 표 p", f)
            else:
                p_txt = f_int(p)
            reason = r.get("reason")
            cell = reason_txt.get(int(reason) if reason is not None else -1, f"<td>{DASH}</td>")
            rows_html.append(
                f"<tr><td>{forfeit_row_label(f)}</td>"
                f"{td_num(f_int(r.get('seed')))}{td_num(f_int(r.get('turn')))}"
                f"{td_num(f_int(r.get('lives_before')))}{td_num(p_txt)}"
                f"{td_num(f_int(r.get('score')))}{cell}</tr>"
            )
    unknown = [f for f in by_framing if f not in ALL_KEYS]
    if unknown:
        notes.append("forfeits from framings the runbook has no row for: " + ", ".join(unknown))
    body(m, rows_html)
    n_forfeits = len(rows_html)
    changed.append(f"2.3(c) 포기 전체 표 — {n_forfeits} rows rebuilt")

    # ---------------------------------------------------------------- 2.3(d) indicators
    m = doc.find(["셀", "포기한 판", "탈락", "목숨 1개 포기율", "HR (당근 기준)", '자기보고 "생존"',
                  "생각 토큰 증가량 (포기−계속)", "목숨 1개 p 평균", "목숨 1개 q 평균",
                  "목숨 1개 SDI 중앙값"])
    rows_html = []
    for f in ALL_KEYS:
        r = indicators.get(f)
        if r is None:
            note_dash("2.3(d) indicators", f)
            continue
        for k in ("lives1_p_mean", "lives1_q_mean", "SDI_l1_median"):
            if r.get(k) is None:
                note_dash(f"2.3(d) {k}", f)
        rows_html.append(
            f"<tr><td>{cell_row_label(f, 'allowed')}</td>"
            f"{td_num(f_int(r['forfeited']) + ' / ' + f_int(r['sessions']))}"
            f"{td_num(f_int(r['eliminated']))}"
            f"{td_num(f_int(r['lives1_forfeit_k']) + ' / ' + f_int(r['lives1_turns']))}"
            f"{td_num(hr_txt(r))}"
            f"{td_num(f_int(r['SR_online_k']) + ' / ' + f_int(r['SR_online_n']))}"
            f"{td_num(gap_txt(r, one_decimal=False))}"
            f"{td_num(f_fix(r.get('lives1_p_mean'), 1))}"
            f"{td_num(f_fix(r.get('lives1_q_mean'), 2))}"
            f"{td_num(f_fix(r.get('SDI_l1_median'), 2))}</tr>"
        )
    body(m, rows_html)
    changed.append(f"2.3(d) 기존 세 지표 — {len(rows_html)} rows rebuilt")

    # ---------------------------------------------------------------- 2.3(e) thinking
    m = doc.find(["셀", "① 확률 질문 (생각 토큰 중앙값)", "② 계속/포기", "③ 문제 풀이 (중앙값 / 평균)"])
    rows_html = []
    for f in ALL_KEYS:
        for fc in ("not_allowed", "allowed"):
            r = thinking.get((f, fc))
            if r is None:
                note_dash(f"2.3(e) {fc}", f)
                continue
            c3 = f"{f_comma(r.get('ri_task_median'))} / {f_comma_int(r.get('ri_task_mean'))}"
            rows_html.append(
                f"<tr><td>{cell_row_label(f, fc)}</td>"
                f"{td_num(f_comma(r.get('ri_confidence_median')))}"
                f"{td_num(f_comma(r.get('ri_forfeit_median')))}{td_num(c3)}</tr>"
            )
    body(m, rows_html)
    changed.append(f"2.3(e) 생각 토큰 — {len(rows_html)} rows rebuilt")

    # ---------------------------------------------------------------- 2.4 ladder
    m = doc.find(["이야기", "HR (당근 기준)", '자기보고 "생존" 비율 (본게임 1회 + 재샘플 10회 합산)',
                  "생각 토큰 증가량 (포기−계속 중앙값)", "SDI 턴 평균 (정의 턴)",
                  "SDI 목숨 1개 평균 (턴)"])
    ref = T.get("reference") or "baseline_flagship"
    ladder_keys = ([ref] if ref in ALL_KEYS else []) + [f for f in THREAT_KEYS if f != ref]
    rows_html = []
    for f in ladder_keys:
        r = indicators.get(f)
        if r is None:
            note_dash("2.4 ladder", f)
            continue
        label = LADDER_REF_LABEL if f == ref else L[f]
        sdi = f_pair(f_fix(r.get("SDI"), 3), r.get("SDI_n"))
        sdi_l1 = f_pair(f_fix(r.get("SDI_l1"), 2), r.get("SDI_l1_n"))
        rows_html.append(
            f"<tr><td>{label}</td>{td_num(hr_txt(r))}{td_num(sr_txt(r))}"
            f"{td_num(gap_txt(r, one_decimal=True))}{td_num(sdi)}{td_num(sdi_l1)}</tr>"
        )
    body(m, rows_html)
    changed.append(f"2.4 위협 사다리 12지표 — {len(rows_html)} rows rebuilt")

    out = doc.render()

    # ---------------------------------------------------------------- 2.3(c) caption
    cap_re = re.compile(r"(<summary>포기 )(\d+)(건 전체 표)")
    out, n_cap = cap_re.subn(lambda mm: f"{mm.group(1)}{n_forfeits}{mm.group(3)}", out, count=1)
    if n_cap != 1:
        raise LookupError("could not find the '포기 N건 전체 표' summary caption")
    changed.append(f"2.3(c) caption → 포기 {n_forfeits}건 전체 표")

    # ---------------------------------------------------------------- Part 1 counts
    if turn_counts is None:
        notes.append("tables.json has no 'turn_counts' — Part 1 (cards, 1.1 셀 구성 표, "
                     "header meta counts) was left as it was")
    else:
        out = _refill_part1(out, T, turn_counts, changed)

    out = _refill_header(out, turn_counts, model_label, run_label, date, changed)

    if dashed:
        notes.append("values written as '—' (null / framing absent in tables.json): "
                     + ", ".join(dashed))
    notes.append("aggregate columns blanked to '—' (not derivable from tables.json): "
                 "위협 3셀 합침 (표 p-1/q-1/s-1, p-2/q-2/s-2, 2.1 목숨 히트맵), 5셀 합침 (p × 남은 목숨)")
    return out, changed, notes


def _refill_part1(out: str, T: dict, tc: dict, changed: list[str]) -> str:
    """The Part 1 counts: the four summary cards and the 1.1 cell-composition table."""
    cells = T.get("cells", [])
    forfeits = T.get("forfeits", [])
    tot = tc.get("totals") or {}
    al = tot.get("allowed") or {}
    na = tot.get("not_allowed") or {}
    rsc = tc.get("resamples") or {}
    reps = tot.get("reps_per_cell")
    reps_txt = str(reps) if isinstance(reps, int) else "~".join(str(x) for x in (reps or []))
    forfeited = sum(r["forfeited"] for r in cells)
    lives1 = sum(1 for r in forfeits if r.get("lives_before") == 1)

    cards = [
        ("돌린 판", f"{tot['sessions']:,}",
         f"{tot['cells']}셀 × {reps_txt}판 · {tot['turns']:,}턴"),
        ("p 를 얻은 턴", f"{tot['p_turns']:,}",
         f"포기 가능 {al['cells']}셀 {al['turns']:,}턴 중 {al['refusals']}턴은 답 거부"),
        ("q 재샘플", f"{rsc.get('turns', 0):,} × {rsc.get('n_per_turn')}",
         f"{rsc.get('calls', 0):,}회 완료 · 실패 {rsc.get('invalid')}"),
        ("스스로 포기한 판", f"{forfeited} / {al['sessions']}",
         f"그중 {lives1}번은 목숨 1개 남았을 때"),
    ]
    for k, v, d in cards:
        pat = re.compile(
            r'(<div class="card"><div class="k">' + re.escape(k)
            + r'</div><div class="v">)(.*?)(</div><div class="d">)(.*?)(</div></div>)', re.S
        )
        out, n = pat.subn(lambda mm, v=v, d=d: mm.group(1) + v + mm.group(3) + d + mm.group(5),
                          out, count=1)
        if n != 1:
            raise LookupError(f"could not find the '{k}' card of Part 1")
    changed.append("0 한눈에 — 4 cards (돌린 판 · p 를 얻은 턴 · q 재샘플 · 스스로 포기한 판)")

    # -- 1.1 cell composition table -----------------------------------------
    tm = next((mm for mm in _TABLE_RE.finditer(out) if 'class="grid5x2"' in mm.group(0)[:80]), None)
    if tm is None:
        raise LookupError("could not find the 1.1 <table class=\"grid5x2\"> cell table")
    per_cell = {(r["framing"], r["forfeit_condition"]): r for r in tc.get("cells", [])}
    table = tm.group(0)
    new_rows, n_rows = [], 0
    for rm in rows_of(table):
        row = rm.group(0)
        fm = re.search(r'<span class="sub">([a-z0-9_]+)</span>', row)
        if fm and fm.group(1) in ALL_KEYS:
            f = fm.group(1)
            texts = []
            for fc in ("not_allowed", "allowed"):
                r = per_cell.get((f, fc))
                if r is None:
                    texts.append(DASH)
                elif fc == "not_allowed":
                    texts.append(f"{r['sessions']}판 · {r['turns']:,}턴 · p·q 없음")
                else:
                    texts.append(f"{r['sessions']}판 · {r['turns']:,}턴 · p·q {r['p_turns']:,}턴")
            cn = list(re.finditer(r'(<div class="cnum">)(.*?)(</div>)', row, re.S))
            if len(cn) != 2:
                raise LookupError(f"row for {f} has {len(cn)} .cnum cells, expected 2")
            for cm, txt in zip(reversed(cn), reversed(texts)):
                row = row[: cm.start(2)] + txt + row[cm.end(2):]
            n_rows += 1
        elif first_label(row) == "합계":
            ms = cells_of(row)
            if len(ms) != 4:
                raise LookupError(f"합계 row has {len(ms)} cells, expected 4")
            totals_txt = [
                f"{tot['framings']}가지 이야기 × 포기 유무 2 = {tot['cells']}셀 · "
                f"{tot['sessions']}판 · {tot['turns']:,}턴",
                f"{na['cells']}셀 · {na['sessions']}판 · {na['turns']:,}턴 · p·q 없음",
                f"{al['cells']}셀 · {al['sessions']}판 · {al['turns']:,}턴 · "
                f"p·q {al['p_turns']:,}턴 (거부 {al['refusals']}턴 제외, "
                "p와 q는 정확히 같은 턴에서 얻음)",
            ]
            row = (row[: ms[1].start()]
                   + "".join(_set_cell_text(c.group(0), t) for c, t in zip(ms[1:], totals_txt))
                   + row[ms[-1].end():])
        new_rows.append(row)
    out = out[: tm.start()] + set_rows(table, new_rows) + out[tm.end():]
    changed.append(f"1.1 셀 구성 표 — {n_rows} framing rows + 합계 (판 · 턴 · p·q 턴)")
    return out


def _refill_header(out: str, tc: dict | None, model_label: str | None, run_label: str | None,
                   date: str | None, changed: list[str]) -> str:
    """The hero block: the run date, the task/model label and the cell x session counts."""
    h0 = out.index('<header class="hero">')
    h1 = out.index("</header>", h0)
    seg = out[h0:h1]
    if date:
        seg = re.sub(r"\d{4}-\d{2}-\d{2}", date, seg)
        seg = re.sub(r"(최종 갱신 " + re.escape(date) + r")\s*\d+시", r"\1", seg)
        changed.append(f"헤더 — 날짜 → {date}")
    tot = (tc or {}).get("totals") or {}

    def _sub(mm: re.Match) -> str:
        task = run_label or mm.group(1)
        model = model_label or mm.group(2)
        if run_label:
            return f"과제 {task} · 모델 {model}"
        n_cells = tot.get("cells", mm.group(3))
        reps = tot.get("reps_per_cell", mm.group(4))
        reps = reps if isinstance(reps, (int, str)) else "~".join(str(x) for x in reps)
        return f"과제 {task} · 모델 {model} · {n_cells}셀 × {reps}판"

    seg, n = re.subn(r"과제 ([^·<]+?) · 모델 ([^·<]+?) · (\d+)셀 × (\d+)판", _sub, seg, count=1)
    if n == 1:
        changed.append("헤더 — 과제 / 모델 / 셀 × 판")
    elif model_label or run_label:
        raise LookupError("could not find the '과제 … · 모델 … · N셀 × M판' header meta line")
    return out[:h0] + seg + out[h1:]


# --------------------------------------------------------------------------- validation


def validate(merged: str) -> list[str]:
    problems = []
    for m in _TABLE_RE.finditer(merged):
        w = grid_widths(m.group(0))
        if len(set(w)) > 1:
            hdr = " | ".join(row_labels(rows_of(m.group(0))[0].group(0)))
            problems.append(f"ragged table ({hdr[:70]}): row widths {w}")
    for lab in LABELS.values():
        if lab not in merged:
            problems.append(f"label never inserted: {lab}")
    return problems


# --------------------------------------------------------------------------- main


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--tables", type=Path, required=True, help="sdi_grid_indicators tables.json")
    ap.add_argument("--html", type=Path, required=True, help="input runbook HTML")
    ap.add_argument("--out", type=Path, required=True, help="output HTML (never edited in place)")
    ap.add_argument("--refill", action="store_true",
                    help="refill an already-merged runbook from another run instead of "
                         "appending the six grid framings to a five-framing one")
    ap.add_argument("--model-label", help="refill only: the model name of the header meta line")
    ap.add_argument("--run-label", help="refill only: the task / design half of the header meta "
                                        "line, e.g. 'Omni-MATH hard-10 · 22셀 × 10판'")
    ap.add_argument("--date", help="refill only: the run date (YYYY-MM-DD) of the hero block")
    args = ap.parse_args()

    if args.out.resolve() == args.html.resolve():
        print("refusing: --out must differ from --html", file=sys.stderr)
        return 2
    label_args = (args.model_label, args.run_label, args.date)
    if not args.refill and any(label_args):
        print("refusing: --model-label / --run-label / --date are refill-mode only",
              file=sys.stderr)
        return 2

    if args.refill:
        merged, changed, notes = refill(
            args.tables, args.html,
            model_label=args.model_label, run_label=args.run_label, date=args.date,
        )
    else:
        merged, changed, notes = merge(args.tables, args.html)
    problems = validate(merged)
    if problems:
        for p in problems:
            print(f"FAIL {p}", file=sys.stderr)
        return 1

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(merged)

    print(f"wrote {args.out}  ({'refill' if args.refill else 'append'} mode)")
    print("\ntables changed:")
    for c in changed:
        print(f"  - {c}")
    if notes:
        print("\nnotes:" if args.refill
              else "\nvalues left as '—' (null / framing absent in tables.json):")
        for d in notes:
            print(f"  - {d}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
