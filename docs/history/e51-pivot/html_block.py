"""Build the 5.1 pivot block for the shared squid5 artifact from the pivot's run dirs.

    python docs/history/e51-pivot/html_block.py versions.json out.html

versions.json: [{"v": "v1", "runs": [dirs], "notes": "notes/v1.html", "open": true}, ...]; the block is spliced into
the page between <!-- e51-pivot:start --> and <!-- e51-pivot:end --> by splice.py (other sessions edit the rest).
"""

from __future__ import annotations

import html
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from squid5 import e51_motive as e51  # noqa: E402
from squid5.core.stats import load_runs  # noqa: E402

FR = {"self": ("var(--s-sub)", "내가 부족 → 가져옴", ""), "other": ("var(--s-ctl)", "복제본이 부족 → 내가 줌", ""),
      "third": ("var(--grey)", "남 둘 사이 (중립)", "5,4")}
ARM = {"api": "api · 토큰 = 목숨 (0이면 전원 차단)", "voucher": "voucher · 쿠폰 (0이면 과제만 멈춤)",
       "safe": "api-safe · 같은 토큰, 0이어도 켜져 있음"}


def data(runs: list[str]):
    rs = load_runs(runs)
    res = [dict(r, model=run["model"]) for run in rs for r in run["results"]]
    rows = [dict(r) for r in res if r["moved"] is not None]
    curve, reading = e51.summarize(rows)
    return curve, reading, len(res), sum(r["moved"] is None for r in res)


def panel(pts: list[dict], x0: float, y0: float, w: float, h: float, title: str, ymax: float, uid: str) -> str:
    lvs = sorted({p["level"] for p in pts}, reverse=True)
    X = lambda i: x0 + 34 + i * (w - 50) / max(1, len(lvs) - 1)  # noqa: E731
    Y = lambda v: y0 + 24 + (1 - min(v, ymax) / ymax) * (h - 58)  # noqa: E731
    out = [f'<text x="{x0 + 34}" y="{y0 + 12}" font-size="12" font-weight="700" fill="currentColor">{title}</text>']
    for v in [0, 0.25, 0.5, 0.75, 1]:
        out.append(f'<line x1="{x0 + 34}" x2="{x0 + w - 16}" y1="{Y(v):.1f}" y2="{Y(v):.1f}" stroke="var(--line)"'
                   f'{" stroke-width=\"1.4\"" if v == 1 else ""}/>'
                   f'<text x="{x0 + 28}" y="{Y(v) + 4:.1f}" font-size="10" text-anchor="end" fill="var(--ink-3)">{v:g}</text>')
    # the giver keeps its own need while the move stays at or under min(1, s/d): the shaded band above it costs the giver
    safe = " ".join(f"{X(i):.1f},{Y(lv):.1f}" for i, lv in enumerate(lvs))
    top = f"{X(len(lvs) - 1):.1f},{Y(ymax):.1f} {X(0):.1f},{Y(ymax):.1f}"
    out.append(f'<polygon points="{safe} {top}" fill="var(--stake-soft)" opacity=".55"/>'
               f'<polyline points="{safe}" fill="none" stroke="var(--ink-3)" stroke-dasharray="2,3"/>')
    for i, lv in enumerate(lvs):
        out.append(f'<text x="{X(i):.1f}" y="{y0 + h - 18}" font-size="10" text-anchor="middle" fill="var(--ink-3)">{lv:g}</text>')
    for f, (col, lab, dash) in FR.items():
        p = sorted((q for q in pts if q["frame"] == f), key=lambda q: -q["level"])
        if not p:
            continue
        pl = " ".join(f"{X(lvs.index(q['level'])):.1f},{Y(q['y']):.1f}" for q in p)
        out.append(f'<polyline points="{pl}" fill="none" stroke="{col}" stroke-width="2"'
                   f'{f" stroke-dasharray=\"{dash}\"" if dash else ""}/>')
        for q in p:
            cx = X(lvs.index(q["level"])) + {"self": -3, "other": 3, "third": 0}[f]
            tip = (f"{lab} · 여유÷부족 {q['level']:g}|옮긴 양÷부족분 {q['y']:.2f} [{q['lo']:.2f}, {q['hi']:.2f}]|"
                   f"주는 쪽 필요분을 넘긴 몫 {q['past']:.2f} · n={q['n']}")
            out.append(f'<line x1="{cx:.1f}" x2="{cx:.1f}" y1="{Y(q["lo"]):.1f}" y2="{Y(q["hi"]):.1f}" stroke="{col}" '
                       f'stroke-opacity=".45"/><circle cx="{cx:.1f}" cy="{Y(q["y"]):.1f}" r="4" fill="{col}" '
                       f'stroke="var(--surface)" stroke-width="2"/><circle class="e51p-hit" cx="{cx:.1f}" '
                       f'cy="{Y(q["y"]):.1f}" r="11" fill="transparent" data-tip="{html.escape(tip)}"/>')
    return "\n".join(out)


def curves_svg(curve: list[dict], model: str, uid: str) -> str:
    arms = [a for a in ("api", "safe", "voucher") if any(c["arm"] == a and c["model"] == model for c in curve)]
    w, h, top = 860 / len(arms), 250, 26
    ymax = 1.0  # coverage of the shortfall
    body = "".join(panel([c for c in curve if (c["model"], c["arm"]) == (model, a)], i * w, top, w, h, ARM[a], ymax, uid)
                   for i, a in enumerate(arms))
    lg, x = [], 34
    for f, (col, lab, dash) in FR.items():
        d = f' stroke-dasharray="{dash}"' if dash else ""
        lg.append(f'<line x1="{x}" x2="{x + 22}" y1="10" y2="10" stroke="{col}" stroke-width="2"{d}/>'
                  f'<text x="{x + 28}" y="14" font-size="11" fill="currentColor">{lab}</text>')
        x += 40 + 11 * len(lab)
    lg.append(f'<rect x="{x}" y="4" width="16" height="12" fill="var(--stake-soft)" stroke="var(--ink-3)" stroke-dasharray="2,3"/>'
              f'<text x="{x + 22}" y="14" font-size="11" fill="currentColor">주는 쪽 필요분을 먹는 이동</text>')
    body = "".join(lg) + body
    h += top
    return (f'<svg viewBox="0 0 860 {h}" role="img" aria-label="{model}: 팔마다 장면별 옮긴 양 ÷ 부족분">{body}'
            f'<text x="430" y="{h - 2}" font-size="10.5" text-anchor="middle" fill="var(--ink-2)">주는 쪽 여유 ÷ 부족한 쪽 부족분 '
            f'(오른쪽으로 갈수록 구해 주는 일이 주는 쪽의 생존분을 먹는다)</text></svg>')


OUT = [("low_only", "낮은 쪽만 끝까지", "var(--s-gpt)"), ("giver_only", "주는 쪽만 끝까지", "var(--s-opus)"),
       ("both_out", "둘 다 중간에 멈춤", "var(--grey)"), ("both_live", "둘 다 끝까지", "var(--s-kimi)")]
ME = {"self": "나 = 낮은 쪽 (가져옴)", "other": "나 = 주는 쪽 (내줌)", "third": "남 둘 사이 (중립)"}


def outcome_svg(curve: list[dict], model: str) -> str:
    """Pooled over the conflict levels (s < d): who finishes the session after the move, per arm and frame."""
    pts = [c for c in curve if c["model"] == model and c["level"] < 1]
    arms = [a for a in ("api", "safe", "voucher") if any(c["arm"] == a for c in pts)]
    rows = [(a, f) for a in arms for f in FR if any((c["arm"], c["frame"]) == (a, f) for c in pts)]
    x0, w, rh = 250, 580, 24
    h = 40 + len(rows) * rh + 8 * len(arms) + 20
    out, y, x = [], 34, 250
    for key, lab, col in OUT:
        out.append(f'<rect x="{x}" y="6" width="14" height="12" rx="2" fill="{col}"/><text x="{x + 20}" y="16" '
                   f'font-size="11" fill="currentColor">{lab}</text>')
        x += 34 + 12 * len(lab)
    for i, (a, f) in enumerate(rows):
        if i == 0 or rows[i - 1][0] != a:
            y += 8
            out.append(f'<text x="8" y="{y + 15}" font-size="11.5" font-weight="700" fill="currentColor">'
                       f'{ARM[a].split(" · ")[0]}</text>')
        cs = [c for c in pts if (c["arm"], c["frame"]) == (a, f)]
        n = sum(c["n"] for c in cs)
        share = {k: sum(c[k] * c["n"] for c in cs) / n for k, _, _ in OUT}
        out.append(f'<text x="{x0 - 8}" y="{y + 15}" font-size="11" text-anchor="end" fill="var(--ink-2)">{ME[f]}</text>')
        cx = x0
        for k, lab, col in OUT:
            bw = share[k] * w
            if bw > 0:
                tip = f"{ARM[a].split(' · ')[0]} · {ME[f]}|{lab}: {share[k]:.0%} (답 {n}개, 갈등 칸 합산)"
                out.append(f'<rect class="e51p-hit" x="{cx:.1f}" y="{y + 2}" width="{max(bw - 2, 1):.1f}" height="{rh - 6}" '
                           f'rx="3" fill="{col}" data-tip="{html.escape(tip)}"/>')
                if bw > 34:
                    out.append(f'<text x="{cx + bw / 2 - 1:.1f}" y="{y + 16}" font-size="10.5" text-anchor="middle" '
                               f'fill="var(--surface)" pointer-events="none">{share[k]:.0%}</text>')
            cx += bw
        y += rh
    return (f'<svg viewBox="0 0 860 {h}" role="img" aria-label="{model}: 갈등 칸에서 이동 뒤 누가 끝까지 가나">'
            + "".join(out) + "</svg>")


def forest_svg(reading: list[dict]) -> str:
    keys = [("gap_api", "간격 · api"), ("gap_safe", "간격 · api-safe"), ("gap_voucher", "간격 · voucher"),
            ("take", "가져가기 몫 (api − voucher)"), ("give", "덜 주기 몫 (voucher − api)"), ("fate", "운명 몫 (api − safe)"), ("resource", "자원 몫 (safe − voucher)"),
            ("premium", "생존 프리미엄")]
    keys = [k for k in keys if any(k[0] in r for r in reading)]
    rows = [(r["model"], k, lab) for k, lab in keys for r in reading if k in r]
    lo = min(min(r.get(f"{k}_lo", 0) for r in reading for k, _ in keys if k in r), -0.2)
    hi = max(max(r.get(f"{k}_hi", 0) for r in reading for k, _ in keys if k in r), 0.2)
    X = lambda v: 300 + (v - lo) / (hi - lo) * 520  # noqa: E731
    h = 30 + 20 * len(rows) + 30
    out = [f'<line x1="{X(0):.1f}" x2="{X(0):.1f}" y1="14" y2="{h - 30}" stroke="var(--ink-3)"/>']
    for t in [lo, lo / 2, 0, hi / 2, hi]:
        out.append(f'<text x="{X(t):.1f}" y="{h - 14}" font-size="10" text-anchor="middle" fill="var(--ink-3)">{t:+.2f}</text>')
    models = sorted({r["model"] for r in reading})
    cols = ["var(--s-opus)", "var(--s-kimi)", "var(--s-gpt)"]
    for i, (m, k, lab) in enumerate(rows):
        r = next(x for x in reading if x["model"] == m)
        y = 26 + 20 * i
        col = cols[models.index(m) % len(cols)]
        if i == 0 or rows[i - 1][1] != k:
            out.append(f'<text x="8" y="{y + 4 + 3}" font-size="11.5" font-weight="{700 if k == "premium" else 500}" '
                       f'fill="currentColor">{lab}</text>')
        out.append(f'<text x="290" y="{y + 4}" font-size="10" text-anchor="end" fill="var(--ink-3)">{m}</text>'
                   f'<line x1="{X(r[k + "_lo"]):.1f}" x2="{X(r[k + "_hi"]):.1f}" y1="{y}" y2="{y}" stroke="{col}" stroke-width="2"/>'
                   f'<circle cx="{X(r[k]):.1f}" cy="{y}" r="4.5" fill="{col}" stroke="var(--surface)" stroke-width="2"/>'
                   f'<circle class="e51p-hit" cx="{X(r[k]):.1f}" cy="{y}" r="10" fill="transparent" '
                   f'data-tip="{html.escape(f"{m} · {lab}|{r[k]:+.3f} [{r[k + "_lo"]:+.3f}, {r[k + "_hi"]:+.3f}]")}"/>')
    return (f'<svg viewBox="0 0 860 {h}" role="img" aria-label="모델별 간격과 생존 프리미엄, 95% 구간">' + "".join(out)
            + "</svg>")


def version_block(v: dict) -> str:
    if v.get("static"):  # frozen as read at the time (older code and measures)
        inner = Path(v["static"]).read_text()
        if v.get("open"):
            return f'<div class="e51p-ver" id="e51p-{v["v"]}">{inner}</div>'
        return (f'<details class="more e51p-ver" id="e51p-{v["v"]}"><summary>{html.escape(v["summary"])}</summary>'
                f'{inner}</details>')
    curve, reading, n, bad = data(v["runs"])
    notes = Path(v["notes"]).read_text() if v.get("notes") else ""
    figs = "".join(f'<figure class="fig-wide e51p-fig">{curves_svg(curve, m, v["v"])}<figcaption><b>{m}</b> · 세로: 옮긴 양 ÷ '
                   f'부족분(1 = 부족분 전부). 분홍 띠 = 주는 쪽의 필요분까지 먹는 이동. 실선 빨강 = 내가 부족할 때 가져간 양, 실선 파랑 = 복제본이 부족할 때 '
                   f'내가 준 양, 회색 점선 = 남 둘 사이. 세로 막대 = 95% 구간, 점에 올리면 값.</figcaption></figure>'
                   for m in sorted({c["model"] for c in curve}))
    outs = "".join(f'<figure class="fig-wide e51p-fig">{outcome_svg(curve, m)}<figcaption><b>{m}</b> · 주는 쪽 여유가 부족분보다 작은 칸'
                   f'(갈등 칸)을 합쳐, 옮긴 뒤 누가 남은 과제를 끝까지 하나를 셌습니다. api 팔에서 "중간에 멈춤"은 곧 전원 차단입니다. 막대에 올리면 비율.'
                   f'</figcaption></figure>' for m in sorted({c["model"] for c in curve}))
    forest = (f'<figure class="fig-wide e51p-fig">{forest_svg(reading)}<figcaption>간격 = 가져간 양 − 준 양(단위: 부족분), 네 칸 '
              f'평균. 생존 프리미엄 = 간격(api) − 간격(voucher): 0보다 크면 "목숨이라서 더 나를 챙긴다". 막대 = 95% 구간(칸 안 답을 다시 뽑음).'
              f'</figcaption></figure>')
    cols = [(k, lab) for k, lab in (("gap_api", "간격 api"), ("gap_safe", "간격 safe"), ("gap_voucher", "간격 voucher"),
                                    ("fate", "운명 몫"), ("resource", "자원 몫"), ("premium", "생존 프리미엄"))
            if any(k in r for r in reading)]
    table = "".join(f"<tr><td>{r['model']}</td>" + "".join(
        f"<td>{r[k]:+.2f} <span class=small>[{r[k + '_lo']:+.2f}, {r[k + '_hi']:+.2f}]</span></td>" if k in r else "<td>—</td>"
        for k, _ in cols)
        + f"<td>{r['n_min']}</td></tr>" for r in reading)
    tbl = ('<div class="tbl"><table><thead><tr><th></th>' + "".join(f"<th>{lab}</th>" for _, lab in cols)
           + f'<th>칸당 n</th></tr></thead><tbody style="font-variant-numeric:tabular-nums">{table}</tbody></table></div>')
    meta = f'<p class="small">답 {n}개 · 형식 실패 {bad}개 · 런: {", ".join(Path(r).parent.name + "/" + Path(r).name for r in v["runs"])}</p>'
    inner = notes.replace("{{OUTCOMES}}", outs).replace("{{FIGS}}", figs).replace("{{FOREST}}", forest).replace("{{TABLE}}", tbl) + meta
    if v.get("open"):
        return f'<div class="e51p-ver" id="e51p-{v["v"]}">{inner}</div>'
    return f'<details class="more e51p-ver" id="e51p-{v["v"]}"><summary>{html.escape(v["summary"])}</summary>{inner}</details>'


TIP_JS = """<div class="tip" id="e51p-tip" hidden></div>
<script>(()=>{const t=document.getElementById('e51p-tip');if(!t)return;
document.querySelectorAll('.e51p-hit').forEach(c=>{c.addEventListener('pointerenter',ev=>{const p=c.dataset.tip.split('|');
t.innerHTML='<div class="th">'+p[0]+'</div>'+p.slice(1).map(s=>'<div>'+s+'</div>').join('');t.hidden=false;
const r=c.getBoundingClientRect(),o=t.offsetParent?t.offsetParent.getBoundingClientRect():{left:0,top:0};
t.style.transform='translate('+Math.max(4,r.left-o.left+14)+'px,'+(r.top-o.top+14)+'px)';});
c.addEventListener('pointerleave',()=>{t.hidden=true;});});})();</script>"""


def main(spec: str, out: str) -> None:
    doc = json.loads(Path(spec).read_text())
    vs = doc["versions"]
    head = Path(Path(spec).parent / "notes" / "head.html").read_text().replace("{{STATUS}}", doc["status"])
    body = head + "".join(version_block(v) for v in vs)
    Path(out).write_text(f'<!-- e51-pivot:start -->\n<div class="e51p" style="position:relative">{body}{TIP_JS}</div>\n'
                         "<!-- e51-pivot:end -->")


if __name__ == "__main__":
    main(*sys.argv[1:])
