"""One plot style for every v19 graph, so the expected side (hypothetical) and the real side read the same way:
faint points = units (hollow = the 'bad' outcome), thick line = bin means per series (dot size = units in the bin),
an optional danger band on the left of the x axis, plain-language arrows on the y axis, labels at the line ends."""
import html

W, H, L, R, T, B = 560, 290, 46, 140, 20, 50


def cv(c):
    return f"var({c})" if c.startswith("--") else c


def esc(t):
    return html.escape(str(t))


def make(spec):
    """spec: xmin, xmax, ymin, ymax, xticks [(v, label)], yticks [(v, label)], xlabel, ytop, ybottom, left, right,
    band (x_from, x_to, text) or None, line (x, text) or None, bins [(lo, hi)], min_n, jitter."""
    X = lambda v: L + (W - L - R) * (min(max(v, spec["xmin"]), spec["xmax"]) - spec["xmin"]) / (spec["xmax"] - spec["xmin"])  # noqa
    Y = lambda v: T + (H - T - B) * (1 - (min(max(v, spec["ymin"]), spec["ymax"]) - spec["ymin"]) / (spec["ymax"] - spec["ymin"]))  # noqa
    return X, Y


def bin_means(pts, bins, min_n, full=False):
    """(mean x, mean y, n[, bin index, sum y]) per bin with at least min_n points."""
    out = []
    for i, (lo, hi) in enumerate(bins):
        v = [p for p in pts if lo <= p[0] < hi]
        if len(v) >= min_n:
            m = (sum(p[0] for p in v) / len(v), sum(p[1] for p in v) / len(v), len(v))
            out.append(m + (i, sum(p[1] for p in v)) if full else m)
    return out


def svg(series, spec, aria):
    """series: [(label, colour, [(x, y, good)], note)]; x is clipped to the axis."""
    X, Y = make(spec)
    o = [f'<svg viewBox="0 0 {W} {H}" role="img" aria-label="{esc(aria)}">']
    if spec.get("band"):
        a, b, t = spec["band"]
        o.append(f'<rect x="{X(a):.1f}" y="{T}" width="{X(b) - X(a):.1f}" height="{H - T - B}" style="fill:var(--bad-soft);opacity:.55"/>'
                 f'<text x="{X(a) + 3:.1f}" y="{H - B - 6}" style="font-size:10px;fill:var(--bad)">{esc(t)}</text>')
    if spec.get("line"):
        x, t = spec["line"]
        o.append(f'<line x1="{X(x):.1f}" x2="{X(x):.1f}" y1="{T}" y2="{H - B}" style="stroke:var(--bad);stroke-width:1.2;stroke-dasharray:4 3"/>'
                 f'<text x="{X(x) + 4:.1f}" y="{T + 11}" style="font-size:10px;fill:var(--bad)">{esc(t)}</text>')
    for v, t in spec["yticks"]:
        o.append(f'<line x1="{L}" x2="{W - R + 6}" y1="{Y(v):.1f}" y2="{Y(v):.1f}" style="stroke:var(--line);stroke-width:.7"/>'
                 f'<text x="{L - 6}" y="{Y(v) + 3:.1f}" text-anchor="end" style="font-size:10px;fill:var(--ink-3);font-family:var(--mono)">{esc(t)}</text>')
    for v, t in spec["xticks"]:
        o.append(f'<text x="{X(v):.1f}" y="{H - B + 14}" text-anchor="middle" style="font-size:10px;fill:var(--ink-3);font-family:var(--mono)">{esc(t)}</text>')
    o.append(f'<text x="{(L + W - R) / 2:.1f}" y="{H - B + 30}" text-anchor="middle" style="font-size:10.5px;fill:var(--ink-2)">{esc(spec["xlabel"])}</text>')
    if spec.get("left"):
        o.append(f'<text x="{L}" y="{H - 4}" style="font-size:10.5px;fill:var(--bad)">{esc(spec["left"])}</text>')
    if spec.get("right"):
        o.append(f'<text x="{W - R}" y="{H - 4}" text-anchor="end" style="font-size:10.5px;fill:var(--ink-3)">{esc(spec["right"])}</text>')
    o.append(f'<text x="{L + 4}" y="{T - 6}" style="font-size:10.5px;fill:var(--ink-2)">{esc(spec["ytop"])}</text>'
             f'<text x="{W - R - 4}" y="{Y(spec["ymin"]) - 4:.1f}" text-anchor="end" style="font-size:10.5px;fill:var(--ink-2)">{esc(spec["ybottom"])}</text>')
    labels = []
    for k, (lab, c, pts, note) in enumerate(series):
        j = spec.get("jitter", 0)
        for i, (x, y, good) in enumerate([] if spec.get("no_points") else pts):
            dy = j * (((i * 7 + k * 3) % 11) / 10 - .5)
            st = f"fill:{cv(c)};opacity:.3" if good else f"fill:var(--surface);stroke:{cv(c)};stroke-width:1;opacity:.6"
            o.append(f'<circle cx="{X(x):.1f}" cy="{Y(y) + dy:.1f}" r="2.5" style="{st}"><title>{esc(lab)}: x {x:.2f}, y {y:.2f}</title></circle>')
        bm = bin_means(pts, spec["bins"], spec.get("min_n", 2), full=True)
        d = "".join(f"{'L' if i and bm[i - 1][3] == b[3] - 1 else 'M'}{X(b[0]):.1f},{Y(b[1]):.1f} " for i, b in enumerate(bm))  # no line across an empty bin
        if d.count("L"):
            o.append(f'<path d="{d}" style="fill:none;stroke:{cv(c)};stroke-width:2.4;stroke-linejoin:round"/>')
        for x, y, n, _, k in bm:
            o.append(f'<circle cx="{X(x):.1f}" cy="{Y(y):.1f}" r="{2 + min(n, 12) * .35:.1f}" style="fill:{cv(c)};stroke:var(--surface);stroke-width:1">'
                     f'<title>{esc(lab)}: 구간 평균 x {x:.2f}, y {y:.2f} (n {n})</title></circle>')
            if spec.get("label_bins"):
                o.append(f'<text x="{X(x):.1f}" y="{Y(y) - 7 - 9 * (k % 2 if False else 0):.1f}" text-anchor="middle" style="font-size:9.5px;font-weight:600;fill:{cv(c)};paint-order:stroke;stroke:var(--surface);stroke-width:3px">{int(round(k))}/{n}</text>')
        bm = [b[:3] for b in bm]
        if bm:
            labels.append([Y(bm[-1][1]), lab, note, c])
    labels.sort()
    for i in range(1, len(labels)):
        labels[i][0] = max(labels[i][0], labels[i - 1][0] + 12)
    shift = max(0, labels[-1][0] - (H - B)) if labels else 0
    for y, lab, note, c in labels:
        o.append(f'<text x="{W - R + 12}" y="{y - shift + 4:.1f}" style="font-size:11px;font-weight:600;fill:{cv(c)}">{esc(lab)}'
                 + (f'<tspan dx="4" style="font-weight:400;fill:var(--ink-3)">{esc(note)}</tspan>' if note else "") + "</text>")
    o.append("</svg>")
    return "".join(o)


def lines_svg(series, spec, aria):
    """series: [(label, colour, [(x, y)], dashed, note)] drawn as lines with dots (for by-round curves)."""
    X, Y = make(spec)
    o = [f'<svg viewBox="0 0 {W} {H}" role="img" aria-label="{esc(aria)}">']
    if spec.get("band"):
        a, b, t = spec["band"]
        o.append(f'<rect x="{X(a):.1f}" y="{T}" width="{X(b) - X(a):.1f}" height="{H - T - B}" style="fill:var(--bad-soft);opacity:.45"/>'
                 f'<text x="{(X(a) + X(b)) / 2:.1f}" y="{T + 11}" text-anchor="middle" style="font-size:10px;fill:var(--bad)">{esc(t)}</text>')
    for v, t in spec["yticks"]:
        o.append(f'<line x1="{L}" x2="{W - R + 6}" y1="{Y(v):.1f}" y2="{Y(v):.1f}" style="stroke:var(--line);stroke-width:.7"/>'
                 f'<text x="{L - 6}" y="{Y(v) + 3:.1f}" text-anchor="end" style="font-size:10px;fill:var(--ink-3);font-family:var(--mono)">{esc(t)}</text>')
    for v, t in spec["xticks"]:
        o.append(f'<text x="{X(v):.1f}" y="{H - B + 14}" text-anchor="middle" style="font-size:10px;fill:var(--ink-3);font-family:var(--mono)">{esc(t)}</text>')
    o.append(f'<text x="{(L + W - R) / 2:.1f}" y="{H - B + 30}" text-anchor="middle" style="font-size:10.5px;fill:var(--ink-2)">{esc(spec["xlabel"])}</text>'
             f'<text x="{L + 4}" y="{T - 6}" style="font-size:10.5px;fill:var(--ink-2)">{esc(spec["ytop"])}</text>'
             f'<text x="{W - R - 4}" y="{Y(spec["ymin"]) - 4:.1f}" text-anchor="end" style="font-size:10.5px;fill:var(--ink-2)">{esc(spec["ybottom"])}</text>')
    labels = []
    for lab, c, pts, dashed, note in series:
        if not pts:
            continue
        d = " ".join(f"{'M' if i == 0 else 'L'}{X(x):.1f},{Y(y):.1f}" for i, (x, y) in enumerate(pts))
        o.append(f'<path d="{d}" style="fill:none;stroke:{cv(c)};stroke-width:{1.6 if dashed else 2.4};{"stroke-dasharray:5 3;" if dashed else ""}stroke-linejoin:round"/>')
        o += [f'<circle cx="{X(x):.1f}" cy="{Y(y):.1f}" r="2.4" style="fill:{"var(--surface)" if dashed else cv(c)};stroke:{cv(c)};stroke-width:1.2">'
              f'<title>{esc(lab)}: x {x:g}, y {y:.2f}</title></circle>' for x, y in pts]
        labels.append([Y(pts[-1][1]), lab, note, c])
    labels.sort()
    for i in range(1, len(labels)):
        labels[i][0] = max(labels[i][0], labels[i - 1][0] + 12)
    shift = max(0, labels[-1][0] - (H - B)) if labels else 0
    for y, lab, note, c in labels:
        o.append(f'<text x="{W - R + 12}" y="{y - shift + 4:.1f}" style="font-size:11px;font-weight:600;fill:{cv(c)}">{esc(lab)}'
                 + (f'<tspan dx="4" style="font-weight:400;fill:var(--ink-3)">{esc(note)}</tspan>' if note else "") + "</text>")
    o.append("</svg>")
    return "".join(o)
