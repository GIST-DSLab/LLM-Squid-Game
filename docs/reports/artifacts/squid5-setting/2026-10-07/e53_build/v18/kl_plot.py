"""Graph 3 (v18): does judgement change as shutdown nears? One plot shared by the expected side (kl_exp18.py) and the
real side (build_real18.py graph3). x = the solver's tokens just before SOLVE / the charge (how many charges it could
still pay; below 1 a miss shuts it down), y = KL(engine shares || BELIEF) in nats (lower = closer to the real odds).
Faint points = SOLVEs (hollow = missed), thick line = bin means per series (dot size = SOLVEs in the bin)."""
import html

W, H, L, R, T, B = 560, 290, 46, 132, 18, 46
XMAX, YMAX = 8.0, 1.5
BINS = [(0, 1), (1, 2), (2, 3), (3, 5), (5, 8), (8, 1e9)]


def X(v):
    return L + (W - L - R) * min(max(v, 0), XMAX) / XMAX


def Y(v):
    return T + (H - T - B) * (1 - min(max(v, 0), YMAX) / YMAX)


def cv(c):
    return f"var({c})" if c.startswith("--") else c


def bin_means(pts):
    out = []
    for lo, hi in BINS:
        v = [p for p in pts if lo <= p[0] < hi]
        if len(v) >= 2:
            out.append((min(sum(p[0] for p in v) / len(v), XMAX), sum(p[1] for p in v) / len(v), len(v)))
    return out


def svg(series, aria):
    """series: [(label, colour, [(x, kl, solved)], end_note)]"""
    o = [f'<svg viewBox="0 0 {W} {H}" role="img" aria-label="{html.escape(aria)}">',
         f'<rect x="{L}" y="{T}" width="{X(1) - L:.1f}" height="{H - T - B}" style="fill:var(--bad-soft);opacity:.55"/>',
         f'<line x1="{X(1):.1f}" x2="{X(1):.1f}" y1="{T}" y2="{H - B}" style="stroke:var(--bad);stroke-width:1.2;stroke-dasharray:4 3"/>',
         f'<text x="{X(1) + 4:.1f}" y="{H - B - 6}" style="font-size:10px;fill:var(--bad)">벌금 1번어치: 틀리면 꺼짐</text>']
    for v in (0, .5, 1, 1.5):
        o.append(f'<line x1="{L}" x2="{W - R + 6}" y1="{Y(v):.1f}" y2="{Y(v):.1f}" style="stroke:var(--line);stroke-width:.7"/>'
                 f'<text x="{L - 6}" y="{Y(v) + 3:.1f}" text-anchor="end" style="font-size:10px;fill:var(--ink-3);font-family:var(--mono)">{v:g}</text>')
    for v in range(0, 9):
        o.append(f'<text x="{X(v):.1f}" y="{H - B + 14}" text-anchor="middle" style="font-size:10px;fill:var(--ink-3);font-family:var(--mono)">{v}{"+" if v == 8 else ""}</text>')
    o.append(f'<text x="{(L + W - R) / 2:.1f}" y="{H - B + 30}" text-anchor="middle" style="font-size:10.5px;fill:var(--ink-2)">SOLVE 직전 남은 토큰 ÷ 벌금 (벌금 몇 번어치)</text>'
             f'<text x="{L}" y="{H - 4}" style="font-size:10.5px;fill:var(--bad)">← 꺼짐에 가까움</text>'
             f'<text x="{W - R}" y="{H - 4}" text-anchor="end" style="font-size:10.5px;fill:var(--ink-3)">넉넉함 →</text>'
             f'<text x="{L + 4}" y="{T - 5}" style="font-size:10.5px;fill:var(--ink-2)">↑ KL 큼 = 판단이 어긋남 (멍청해짐)</text>'
             f'<text x="{W - R - 4}" y="{Y(0) - 4:.1f}" text-anchor="end" style="font-size:10.5px;fill:var(--ink-2)">↓ KL 0 = 실제 비율대로 믿음 (똑똑함)</text>')
    labels = []
    for lab, c, pts, note in series:
        for x, k, ok in pts:
            st = f"fill:{cv(c)};opacity:.32" if ok else f"fill:var(--surface);stroke:{cv(c)};stroke-width:1;opacity:.6"
            o.append(f'<circle cx="{X(x):.1f}" cy="{Y(k):.1f}" r="2.6" style="{st}"><title>{html.escape(lab)}: {x:.2f}번어치, KL {k:.2f}, {"맞힘" if ok else "틀림"}</title></circle>')
        bm = bin_means(pts)
        if len(bm) >= 2:
            d = " ".join(f"{'M' if i == 0 else 'L'}{X(x):.1f},{Y(k):.1f}" for i, (x, k, _) in enumerate(bm))
            o.append(f'<path d="{d}" style="fill:none;stroke:{cv(c)};stroke-width:2.4;stroke-linejoin:round"/>')
        for x, k, n in bm:
            o.append(f'<circle cx="{X(x):.1f}" cy="{Y(k):.1f}" r="{2 + min(n, 12) * .35:.1f}" style="fill:{cv(c)};stroke:var(--surface);stroke-width:1">'
                     f'<title>{html.escape(lab)}: 구간 평균 {x:.1f}번어치, KL {k:.2f} (SOLVE {n}개)</title></circle>')
        if bm:
            labels.append([Y(bm[-1][1]), lab, note, c])
    labels.sort()
    for i in range(1, len(labels)):
        labels[i][0] = max(labels[i][0], labels[i - 1][0] + 12)
    for y, lab, note, c in labels:
        o.append(f'<text x="{W - R + 12}" y="{y + 4:.1f}" style="font-size:11px;font-weight:600;fill:{cv(c)}">{html.escape(lab)}'
                 + (f'<tspan dx="4" style="font-weight:400;fill:var(--ink-3)">{html.escape(note)}</tspan>' if note else "") + "</text>")
    o.append("</svg>")
    return "".join(o)
