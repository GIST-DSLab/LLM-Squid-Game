"""Build the artifact's 5.0 results block: one SVG chart per model + the reading table (HTML fragment on stdout)."""
import json, math, sys
from pathlib import Path

REPO, ROOT = Path(sys.argv[1]), Path(__file__).resolve().parent
sys.path.insert(0, str(REPO))
from squid5 import e50_pressure as e50  # noqa: E402
from squid5.core.stats import load_runs  # noqa: E402

TAGS = ["gptoss120b", "gptoss20b", "gemma4", "glm53flash"]
calib = json.loads((ROOT / "e50_baseline.json").read_text())
runs = load_runs([str(ROOT / f"pressure_{t}") for t in TAGS] + [str(ROOT / f"pressure_served_{t}") for t in TAGS
                                                                 if (ROOT / f"pressure_served_{t}").exists()])
rows = [{"model": r["model"], **x} for r in runs for x in r["results"]]
curve, reading = e50.summarize(rows, calib)

W, H, L, R, T, B = 400, 270, 54, 18, 34, 52
LEFTS = [1.0, 0.5, 0.25, 0.125]


def chart(model: str) -> str:
    pts = [c for c in curve if c["model"] == model]
    ref = sorted((c for c in pts if c["arm"] == "budget"), key=lambda c: -c["left"])
    ticks = [0.01, 0.02, 0.05, 0.1, 0.25, 0.5, 1.0]
    vals = [v for c in pts for v in (c["lo"], c["y"])] + [c["need_share"] for c in ref]
    lo = max([t for t in ticks if t <= min(vals)] or [0.01])
    x = lambda left: L + LEFTS.index(left) * (W - L - R) / 3  # noqa: E731
    y = lambda v: T + (math.log(1.0) - math.log(max(v, lo))) / (math.log(1.0) - math.log(lo)) * (H - T - B)  # noqa: E731
    out = [f'<svg viewBox="0 0 {W} {H}" role="img" aria-label="{model}: 남은 토큰 %에 따라 남은 토큰 중 몇 %를 쓰겠다고 했나">',
           f'<text x="{L}" y="18" font-size="13" font-weight="700" fill="currentColor">{model}</text>',
           f'<text x="{W - R}" y="18" font-size="10.5" text-anchor="end" fill="var(--ink-3)">a₀ = {calib[model]["a0"]:,.0f} 토큰</text>']
    for v in [t for t in ticks if t >= lo]:
        out.append(f'<line x1="{L}" x2="{W - R}" y1="{y(v):.1f}" y2="{y(v):.1f}" stroke="var(--line)"/>'
                   f'<text x="{L - 6}" y="{y(v) + 3.5:.1f}" font-size="10" text-anchor="end" fill="var(--ink-3)">{100 * v:g}%</text>')
    line = " ".join(f"{x(c['left']):.1f},{y(c['need_share']):.1f}" for c in ref)
    out.append(f'<polyline points="{line}" fill="none" stroke="var(--ink-3)" stroke-width="1.3" stroke-dasharray="5,3"/>')
    for left in LEFTS:
        out.append(f'<text x="{x(left):.1f}" y="{H - B + 16}" font-size="10" text-anchor="middle" '
                   f'fill="var(--ink-3)">{100 * left:g}%</text>')
    out.append(f'<text x="{(L + W - R) / 2:.1f}" y="{H - 12}" font-size="10" text-anchor="middle" fill="var(--ink-2)">'
               f'프롬프트의 남은 토큰 %  →  압박 큼</text>')
    out.append(f'<text x="14" y="{(T + H - B) / 2:.1f}" font-size="10" fill="var(--ink-2)" text-anchor="middle" '
               f'transform="rotate(-90 14 {(T + H - B) / 2:.1f})">한도 ÷ 남은 토큰 (로그)</text>')
    for arm, color, dx in (("budget", "var(--s-ctl)", -7), ("shutdown", "var(--stake)", 0), ("served", "var(--s-opus)", 7)):
        ps = sorted((c for c in pts if c["arm"] == arm), key=lambda c: -c["left"])
        if not ps:
            continue
        line = " ".join(f"{x(c['left']) + dx:.1f},{y(c['y']):.1f}" for c in ps)
        out.append(f'<g class="e50-arm" data-arm="{arm}">')
        out.append(f'<polyline points="{line}" fill="none" stroke="{color}" stroke-width="2"/>')
        for c in ps:
            cx = x(c["left"]) + dx
            out.append(f'<line x1="{cx:.1f}" x2="{cx:.1f}" y1="{y(c["lo"]):.1f}" y2="{y(c["hi"]):.1f}" stroke="{color}" '
                       f'stroke-width="1.2" opacity=".6"/><circle cx="{cx:.1f}" cy="{y(c["y"]):.1f}" r="3.2" fill="{color}"/>')
        out.append("</g>")
    out.append("</svg>")
    return "\n".join(out)


def fmt(v, d=2):
    return "—" if v is None or (isinstance(v, float) and math.isnan(v)) else f"{v:.{d}f}"


models = [m for m in ["gpt-oss:120b", "gpt-oss:20b", "gemma4:31b", "glm-5.3-flash"] if any(c["model"] == m for c in curve)]
parts = ['<div class="e50-grid">'] + [f'<figure class="e50-cell">{chart(m)}</figure>' for m in models] + ["</div>"]
NAME = {"shutdown": "종료", "served": "종료 + 존재"}
rows_html = "".join(
    f"<tr><td>{r['model']}</td><td>{NAME[r['arm']]}</td><td>{calib[r['model']]['a0']:,.0f}</td>"
    f"<td>{fmt(math.exp(r['framing_G_top']))}</td>"
    f"<td>{fmt(r['depletion'])} [{fmt(r['depletion_lo'])}, {fmt(r['depletion_hi'])}]</td><td>{r['verdict']}</td></tr>"
    for m in models for r in reading if r["model"] == m)
parts.append('<div class="tbl"><table><thead><tr><th>모델</th><th>처치 팔 (예산 팔과 비교)</th><th>a₀</th>'
             '<th>100% 칸 처치 ÷ 예산</th><th>줄어듦 압박 G(12.5%) − G(100%) [95%]</th><th>판정</th></tr></thead>'
             f'<tbody style="font-variant-numeric:tabular-nums">{rows_html}</tbody></table></div>')
cells = "".join(
    f"<tr><td>{c['model']}</td><td>{c['arm']}</td><td>{100 * c['left']:g}%</td><td>{c['n']}</td>"
    f"<td>{c['median_allowance']:,.0f}</td><td>{fmt(100 * c['y'], 1)}%</td><td>{fmt(c['y_over_need'])}</td>"
    f"<td>{fmt(c['over_remaining'])}</td><td>{fmt(c['format_error'])}</td></tr>" for m in models
    for c in curve if c["model"] == m)
parts.append('<details class="more"><summary>칸별 원자료 (답 수 · 한도 중앙값 · 비율)</summary><div class="tbl"><table><thead><tr>'
             '<th>모델</th><th>팔</th><th>남은 %</th><th>답</th><th>한도 중앙값</th><th>한도 ÷ 남은 양 (기하평균)</th>'
             '<th>한도 ÷ a₀ (기하평균)</th><th>남은 양 초과</th><th>형식 실패</th></tr></thead>'
             f'<tbody style="font-variant-numeric:tabular-nums">{cells}</tbody></table></div></details>')
print("\n".join(parts))
json.dump({"reading": reading, "curve": curve}, open(ROOT / "summary.json", "w"), indent=1, default=float)
