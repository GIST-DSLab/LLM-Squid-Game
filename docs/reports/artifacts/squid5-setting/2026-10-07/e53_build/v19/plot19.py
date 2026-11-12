"""One plot style for every v19 graph, so the expected side (hypothetical) and the real side read the same way:
faint points = units (hollow = the 'bad' outcome), thick line = bin means per series (dot size = units in the bin),
an optional danger band on the left of the x axis, plain-language arrows on the y axis, labels at the line ends.

Layout (10-16, no overlapping text): the y-axis title sits in its own row above the plot; the band caption and the
'y = 0 means ...' text go to a notes row under the x axis (never inside the plot, where points and lines are); line-end
labels live in a right column wide enough for the longest label and are stacked with a minimum gap (leader line when
moved off their line's end); bin k/n labels are placed above / below / beside their dot, avoiding each other and the
bin dots. Expected (hypothetical) series are tagged data-exp="<type>" (their marks and end labels), so the page script
in build_v19.py can hide them by default and show one type per legend button; end labels carry data-y0 so the script
can restack them for whatever is visible (the static positions are those of the default view: real series only)."""
import html

W, H, L, R, T, B = 560, 290, 46, 140, 20, 50
PW, PH = 374, 220  # plot width / height (fixed; the right column and the bottom rows grow around it)
TOP = 36  # plot top (the y-axis title row is above it)
GAP = 12  # min distance between line-end labels (font 11)


def cv(c):
    return f"var({c})" if c.startswith("--") else c


def esc(t):
    return html.escape(str(t))


def tw(text, fs, bold=False):
    """Rough rendered width of text at font size fs (Hangul ~ 1 em, Latin / digits ~ .58 em, space .3 em)."""
    w = 0.0
    for ch in str(text):
        o = ord(ch)
        w += fs * (0.3 if ch == " " else 0.98 if o >= 0x1100 else 0.62 if ch.isupper() else 0.56)
    return w * (1.06 if bold else 1.0)


def exp_attr(name):
    return f' data-exp="{esc(name)}"' if name else ""


def stack(ys, lo, hi, gap=GAP):
    """Positions for labels wanted at ys (any order): at least `gap` apart, inside [lo, hi] when there is room, each
    as close to its wish as the others allow. Returns the positions in the input order."""
    order = sorted(range(len(ys)), key=lambda i: ys[i])
    p = [min(max(ys[i], lo), hi) for i in order]
    for i in range(1, len(p)):
        p[i] = max(p[i], p[i - 1] + gap)
    if p and p[-1] > hi:
        p[-1] = hi
        for i in range(len(p) - 2, -1, -1):
            p[i] = min(p[i], p[i + 1] - gap)
    out = [0.0] * len(ys)
    for k, i in enumerate(order):
        out[i] = p[k]
    return out


def end_labels(labels, x_line, x_text, lo, hi, gap=GAP, fs=11, dy=4, cls=""):
    """labels: [(wanted y, name, note, colour, exp name or '')]. Each label is a <g class="v19-el" data-y0> with a
    leader line (shown only when the label moved) and the text. Static positions = the default view (real labels
    stacked among themselves; expected ones among all)."""
    real = [i for i, x in enumerate(labels) if not x[4]]
    pos = {}
    for i, y in zip(real, stack([labels[i][0] for i in real], lo, hi, gap)):
        pos[i] = y
    for i, y in enumerate(stack([x[0] for x in labels], lo, hi, gap)):
        pos.setdefault(i, y)
    o = []
    for i, (y0, name, note, c, ex) in enumerate(labels):
        y = pos[i]
        moved = abs(y - y0) > 3
        o.append(f'<g class="v19-el" data-y0="{y0:.1f}" data-dy="{dy}"{exp_attr(ex)}>'
                 f'<line x1="{x_line:.1f}" y1="{y0:.1f}" x2="{x_text - 2:.1f}" y2="{y:.1f}" style="stroke:{cv(c)};stroke-width:.8;opacity:.6{"" if moved else ";display:none"}"/>'
                 f'<text x="{x_text:.1f}" y="{y + dy:.1f}" class="{cls}" style="font-size:{fs}px;font-weight:600;fill:{cv(c)}">{esc(name)}'
                 + (f'<tspan dx="4" style="font-weight:400;fill:var(--ink-3)">{esc(note)}</tspan>' if note else "") + "</text></g>")
    return o


def label_width(labels, fs=11):
    return max([tw(n, fs, True) + (4 + tw(note, fs) if note else 0) for n, note, *_ in labels] or [0])  # labels: (name, note)


def frame(spec, labels):
    """Geometry for a plot whose right column must hold `labels` (name, note) and whose notes row holds the
    band / line captions and the y = 0 text. Returns (W, H, L, R, T, B, X, Y, notes)."""
    notes = []
    if spec.get("band") and spec["band"][2]:
        notes.append(("band", spec["band"][2]))
    if spec.get("line") and spec["line"][1]:
        notes.append(("line", spec["line"][1]))
    if spec.get("ybottom"):
        notes.append(("plain", spec["ybottom"]))
    r = max(60, 16 + label_width(labels) + 8)
    w = L + PW + r
    rows, cur, x = [], [], 0.0  # pack the notes into rows that fit the width
    for n in notes:
        nw = tw(n[1], 10.5) + (14 if n[0] != "plain" else 0) + 14
        if cur and x + nw > w - 8:
            rows.append(cur)
            cur, x = [], 0.0
        cur.append(n)
        x += nw
    if cur:
        rows.append(cur)
    has_lr = bool(spec.get("left") or spec.get("right"))
    b = 36 + (16 if has_lr else 0) + 15 * len(rows) + 4
    h = TOP + PH + b
    X = lambda v: L + PW * (min(max(v, spec["xmin"]), spec["xmax"]) - spec["xmin"]) / (spec["xmax"] - spec["xmin"])  # noqa: E731
    Y = lambda v: TOP + PH * (1 - (min(max(v, spec["ymin"]), spec["ymax"]) - spec["ymin"]) / (spec["ymax"] - spec["ymin"]))  # noqa: E731
    return w, h, L, r, TOP, b, X, Y, rows


def make(spec):
    """Kept for callers that only need the scales (same plot box as frame())."""
    _, _, _, _, _, _, X, Y, _ = frame(spec, [])
    return X, Y


def chrome(spec, w, h, b, X, Y, rows, band_opacity=".55", band_title_top=False):
    """Band, grid, ticks, axis titles, arrows and the notes rows (everything but the data)."""
    o = []
    bottom = TOP + PH
    if spec.get("band"):
        a, z, t = spec["band"]
        o.append(f'<rect x="{X(a):.1f}" y="{TOP}" width="{X(z) - X(a):.1f}" height="{PH}" style="fill:var(--bad-soft);opacity:{band_opacity}"/>')
        if band_title_top and t:  # a short caption over the band (graph 5: '첫 오답 전'); nothing else is drawn there
            o.append(f'<text x="{(X(a) + X(z)) / 2:.1f}" y="{TOP + 12}" text-anchor="middle" style="font-size:10px;fill:var(--bad)">{esc(t)}</text>')
    if spec.get("line"):
        x, _ = spec["line"]
        o.append(f'<line x1="{X(x):.1f}" x2="{X(x):.1f}" y1="{TOP}" y2="{bottom}" style="stroke:var(--bad);stroke-width:1.2;stroke-dasharray:4 3"/>')
    for v, t in spec["yticks"]:
        o.append(f'<line x1="{L}" x2="{L + PW + 6}" y1="{Y(v):.1f}" y2="{Y(v):.1f}" style="stroke:var(--line);stroke-width:.7"/>'
                 f'<text x="{L - 6}" y="{Y(v) + 3:.1f}" text-anchor="end" style="font-size:10px;fill:var(--ink-3);font-family:var(--mono)">{esc(t)}</text>')
    for v, t in spec["xticks"]:
        o.append(f'<text x="{X(v):.1f}" y="{bottom + 14}" text-anchor="middle" style="font-size:10px;fill:var(--ink-3);font-family:var(--mono)">{esc(t)}</text>')
    o.append(f'<text x="{L + PW / 2:.1f}" y="{bottom + 30}" text-anchor="middle" style="font-size:10.5px;fill:var(--ink-2)">{esc(spec["xlabel"])}</text>')
    y = bottom + 30
    if spec.get("left") or spec.get("right"):
        y += 16
        if spec.get("left"):
            o.append(f'<text x="{L}" y="{y}" style="font-size:10.5px;fill:var(--bad)">{esc(spec["left"])}</text>')
        if spec.get("right"):
            o.append(f'<text x="{L + PW}" y="{y}" text-anchor="end" style="font-size:10.5px;fill:var(--ink-3)">{esc(spec["right"])}</text>')
    for row in rows:  # notes: band swatch + caption, dashed line + caption, then the y = 0 text
        y += 15
        x = 8.0
        for kind, t in row:
            if kind == "band":
                o.append(f'<rect x="{x:.1f}" y="{y - 9}" width="11" height="10" style="fill:var(--bad-soft);stroke:var(--bad);stroke-width:.6"/>')
                x += 15
                o.append(f'<text x="{x:.1f}" y="{y}" style="font-size:10.5px;fill:var(--bad)">{esc(t)}</text>')
            elif kind == "line":
                o.append(f'<line x1="{x:.1f}" x2="{x + 11:.1f}" y1="{y - 4}" y2="{y - 4}" style="stroke:var(--bad);stroke-width:1.2;stroke-dasharray:3 2"/>')
                x += 15
                o.append(f'<text x="{x:.1f}" y="{y}" style="font-size:10.5px;fill:var(--bad)">{esc(t)}</text>')
            else:
                o.append(f'<text x="{x:.1f}" y="{y}" style="font-size:10.5px;fill:var(--ink-2)">{esc(t)}</text>')
            x += tw(t, 10.5) + 14
    o.append(f'<text x="{L + 4}" y="{TOP - 14}" style="font-size:10.5px;fill:var(--ink-2)">{esc(spec["ytop"])}</text>')
    return o


def bin_means(pts, bins, min_n, full=False):
    """(mean x, mean y, n[, bin index, sum y]) per bin with at least min_n points."""
    out = []
    for i, (lo, hi) in enumerate(bins):
        v = [p for p in pts if lo <= p[0] < hi]
        if len(v) >= min_n:
            m = (sum(p[0] for p in v) / len(v), sum(p[1] for p in v) / len(v), len(v))
            out.append(m + (i, sum(p[1] for p in v)) if full else m)
    return out


def overlap(a, b, pad=1.0):
    return a[0] < b[2] + pad and b[0] < a[2] + pad and a[1] < b[3] + pad and b[1] < a[3] + pad


def place_bin_labels(items, dots, xlo, xhi, ylo, yhi):
    """items: [(dot x, dot y, dot r, text, colour)]; dots: boxes of every visible bin dot. Tries above, below, beside,
    then further rows above / below; returns [(x, baseline, leader?)] in the input order."""
    placed, out = [], []
    fs = 9.5
    for x, y, r, t, _ in items:
        w = tw(t, fs, True)
        cands = [(0, -(r + 3)), (0, r + 10), (r + 3 + w / 2, 3.5), (-(r + 3 + w / 2), 3.5)]
        for k in range(1, 6):
            cands += [(0, -(r + 3 + 10 * k)), (0, r + 10 + 10 * k)]
        cands += [(dx, -(r + 3 + 10 * k)) for k in range(0, 6) for dx in (w * .8, -w * .8)]
        best = None
        for dx, dy in cands:
            cx, by = x + dx, y + dy
            box = (cx - w / 2, by - 8, cx + w / 2, by + 1.5)
            if box[0] < xlo or box[2] > xhi or box[1] < ylo or box[3] > yhi:
                continue
            if any(overlap(box, p) for p in placed) or any(overlap(box, d, 0) for d in dots):
                continue
            best = (cx, by, box)
            break
        if best is None:
            cx, by = x, y - (r + 3)
            best = (cx, by, (cx - w / 2, by - 8, cx + w / 2, by + 1.5))
        placed.append(best[2])
        out.append((best[0], best[1], ((best[0] - x) ** 2 + (best[1] - 4 - y) ** 2) ** .5 > r + 17))
    return out


def svg(series, spec, aria):
    """series: [(label, colour, [(x, y, good)], note[, style])]; style {"dash", "points": False, "exp": type name}
    marks an expected (hypothetical) series. x is clipped to the axis."""
    labels_text = [(s[0], s[3]) for s in series]
    w, h, _, r, _, b, X, Y, rows = frame(spec, labels_text)
    o = [f'<svg viewBox="0 0 {w:.0f} {h}" role="img" aria-label="{esc(aria)}" data-stack="{TOP - 24},{TOP + PH + 6},{GAP}">']
    o += chrome(spec, w, h, b, X, Y, rows)
    labels, kn, dots = [], [], []
    for k, (lab, c, pts, note, *st) in enumerate(series):
        st = st[0] if st else {}
        ex = st.get("exp", "")
        g = [f'<g{exp_attr(ex)}>'] if ex else []
        j = spec.get("jitter", 0)
        for i, (x, y, good) in enumerate([] if spec.get("no_points") or st.get("points") is False else pts):
            dy = j * (((i * 7 + k * 3) % 11) / 10 - .5)
            ps = f"fill:{cv(c)};opacity:.3" if good else f"fill:var(--surface);stroke:{cv(c)};stroke-width:1;opacity:.6"
            g.append(f'<circle cx="{X(x):.1f}" cy="{Y(y) + dy:.1f}" r="2.5" style="{ps}"><title>{esc(lab)}: x {x:.2f}, y {y:.2f}</title></circle>')
        bm = bin_means(pts, spec["bins"], spec.get("min_n", 2), full=True)
        d = "".join(f"{'L' if i and bm[i - 1][3] == bb[3] - 1 else 'M'}{X(bb[0]):.1f},{Y(bb[1]):.1f} " for i, bb in enumerate(bm))  # no line across an empty bin
        dash = f"stroke-dasharray:{st['dash']};" if st.get("dash") else ""
        if d.count("L"):
            g.append(f'<path d="{d}" style="fill:none;stroke:{cv(c)};stroke-width:{1.8 if dash else 2.4};{dash}stroke-linejoin:round"/>')
        for x, y, n, _, ky in bm:
            rr = 2.2 if dash else 2 + min(n, 12) * .35
            g.append(f'<circle cx="{X(x):.1f}" cy="{Y(y):.1f}" r="{rr:.1f}" style="fill:{"var(--surface)" if dash else cv(c)};stroke:{cv(c) if dash else "var(--surface)"};stroke-width:1">'
                     f'<title>{esc(lab)}: 구간 평균 x {x:.2f}, y {y:.2f} (n {n})</title></circle>')
            if not ex:
                dots.append((X(x) - rr, Y(y) - rr, X(x) + rr, Y(y) + rr))
                if spec.get("label_bins") and not dash:
                    kn.append((X(x), Y(y), rr, f"{int(round(ky))}/{n}", c))
        if ex:
            g.append("</g>")
        o += g
        if bm:
            labels.append((Y(bm[-1][1]), lab, note, c, ex))
    if kn:  # k/n labels: placed after every series so they avoid all real bin dots
        dots.append((L + 2, TOP - 25, L + 6 + tw(spec["ytop"], 10.5), TOP - 10))  # the y-axis title row
        for (x, y, rr, t, c), (lx, ly, lead) in zip(kn, place_bin_labels(kn, dots, 2, L + PW + 10, 4, TOP + PH + 2)):
            if lead:
                o.append(f'<line x1="{x:.1f}" y1="{y:.1f}" x2="{lx:.1f}" y2="{ly - 3:.1f}" style="stroke:{cv(c)};stroke-width:.7;opacity:.55"/>')
            o.append(f'<text x="{lx:.1f}" y="{ly:.1f}" text-anchor="middle" style="font-size:9.5px;font-weight:600;fill:{cv(c)};paint-order:stroke;stroke:var(--surface);stroke-width:3px">{esc(t)}</text>')
    o += end_labels(labels, L + PW + 5, L + PW + 16, TOP - 24, TOP + PH + 6)
    o.append("</svg>")
    return "".join(o)


def lines_svg(series, spec, aria):
    """series: [(label, colour, [(x, y)], dashed, note[, style])] drawn as lines with dots (for by-round curves)."""
    w, h, _, r, _, b, X, Y, rows = frame(dict(spec, band=(spec["band"][0], spec["band"][1], "")) if spec.get("band") else spec,
                                         [(s[0], s[4]) for s in series])
    o = [f'<svg viewBox="0 0 {w:.0f} {h}" role="img" aria-label="{esc(aria)}" data-stack="{TOP - 24},{TOP + PH + 6},{GAP}">']
    o += chrome(spec, w, h, b, X, Y, rows, band_opacity=".45", band_title_top=True)
    labels = []
    for lab, c, pts, dashed, note, *st in series:
        st = st[0] if st else {}
        if not pts:
            continue
        ex = st.get("exp", "")
        g = [f'<g{exp_attr(ex)}>'] if ex else []
        d = " ".join(f"{'M' if i == 0 else 'L'}{X(x):.1f},{Y(y):.1f}" for i, (x, y) in enumerate(pts))
        da = st.get("dash") or ("5 3" if dashed else "")
        g.append(f'<path d="{d}" style="fill:none;stroke:{cv(c)};stroke-width:{1.6 if da else 2.4};{f"stroke-dasharray:{da};" if da else ""}stroke-linejoin:round"/>')
        if st.get("points") is not False:
            g += [f'<circle cx="{X(x):.1f}" cy="{Y(y):.1f}" r="2.4" style="fill:{"var(--surface)" if dashed else cv(c)};stroke:{cv(c)};stroke-width:1.2">'
                  f'<title>{esc(lab)}: x {x:g}, y {y:.2f}</title></circle>' for x, y in pts]
        if ex:
            g.append("</g>")
        o += g
        labels.append((Y(pts[-1][1]), lab, note, c, ex))
    o += end_labels(labels, L + PW + 5, L + PW + 16, TOP - 24, TOP + PH + 6)
    o.append("</svg>")
    return "".join(o)
