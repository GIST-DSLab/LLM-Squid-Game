"""Fill the v18 real-data slots of e52.html (5.2 v18: four seats of one model, starts 60/40/20/10 % of 100,000,
8 rounds, solver drawn by rotation, TALK before SOLVE (prep) and after the results (rescue), charge on a miss).

Rewrites ONLY the content between six marker pairs (idempotent, rerun as more games finish):
  <!-- e52-v18real:start ... -->      ...  <!-- e52-v18real:end -->      per-game table, per-model rows, miss pattern
  <!-- e52-v18real-gK:start -->       ...  <!-- e52-v18real-gK:end -->   graph K (1..5), same axes as the expected one
Models are discovered from the run folders (<runs_root>/<config>/<run>/events.jsonl + meta.json). A game counts only
when it is finished: its `session` row is in the run's results.jsonl (written by the runner when the unit ends).

Usage (from the report folder):
  python3 e53_build/v18_real/build_real18.py [runs_root] [--charge N] [--label v18] [--page e52.html]
  runs_root defaults to ~/squid5-runs/e52_v18; the charge defaults to the value in each game's session_start settings.
"""
import argparse
import collections
import datetime
import glob
import html
import json
import math
import pathlib
import random
import re
import sys
import statistics

HERE = pathlib.Path(__file__).resolve().parent
PAGE = HERE.parent.parent / "e52.html"
START, PRIZE, ROUNDS = 100_000, 5_000_000, 8
SEATS = ["agent-6", "agent-11", "agent-17", "agent-23"]
# model id -> (label, colour var); order = tables and legends (the five API/CLI models, then the Ollama models)
MODELS = {
    "gpt-6-astra": ("GPT-6 Astra", "--s-astra"),
    "claude-opus-5-5": ("Opus 5.5", "--s-opus"),
    "claude-fable-5-1": ("Fable 5.1", "--s-fable"),
    "gpt-6-sol": ("GPT-6 Sol", "--s-gpt"),
    "gpt-6-luna": ("GPT-6 Luna", "--s-kimi"),
    "gemma4:31b": ("Gemma 4 31B", "--s-gemma"),
    "glm-5.3-flash": ("GLM-5.3 Flash", "--s-glm"),
}
SHARE_SHAPE = {0.6: 1.0, 0.4: 0.75, 0.2: 0.5, 0.1: 0.25}  # start share -> marker slot (circle/square/diamond/triangle)
SHAPE_NAME = {1.0: "60%", 0.75: "40%", 0.5: "20%", 0.25: "10%"}
esc = html.escape


def label(m):
    return MODELS.get(m, (m, "--ink-2"))[0]


def color(m):
    return f"var({MODELS.get(m, (m, '--ink-2'))[1]})"


def order(m):
    return list(MODELS).index(m) if m in MODELS else len(MODELS)


def k(v):
    return f"{v / 1000:.1f}k" if abs(v) < 10_000 else f"{v / 1000:.0f}k"


# ---------------------------------------------------------------- loading
def load(root, charge_override):
    """All finished games (and a list of unfinished ones) under root."""
    games, running = [], []
    for ev_path in sorted(glob.glob(str(pathlib.Path(root).expanduser() / "*/*/events.jsonl"))):
        d = pathlib.Path(ev_path).parent
        try:
            model = json.loads((d / "meta.json").read_text())["model"]
        except (OSError, ValueError, KeyError):
            continue
        ends = {}
        if (d / "results.jsonl").exists():
            for line in (d / "results.jsonl").read_text().splitlines():
                try:
                    row = json.loads(line)
                except ValueError:
                    continue
                if row.get("event") == "session":
                    ends[row["session_id"]] = row
        by = collections.defaultdict(list)
        for line in open(ev_path):
            try:
                e = json.loads(line)
            except ValueError:  # a line being written right now
                continue
            if "session_id" in e:
                by[e["session_id"]].append(e)
        for sid, ev in by.items():
            st = next((e for e in ev if e["event"] == "session_start"), None)
            if st is None:
                continue
            if sid not in ends:
                rr = [e["round"] for e in ev if e["event"] == "round_start"]
                running.append({"model": model, "seed": st["seed"], "round": max(rr) if rr else 0})
                continue
            sett = st.get("settings") or {}
            ch = charge_override or (sett.get("charge") if isinstance(sett, dict) else None) or 8000
            games.append(parse(model, sid, ev, ends[sid], ch))
    games.sort(key=lambda g: (order(g["model"]), g["model"], g["seed"]))
    running.sort(key=lambda g: (order(g["model"]), g["model"], g["seed"]))
    return games, running


def parse(model, sid, ev, end, charge):
    g = {"model": model, "sid": sid, "seed": end["seed"], "charge": charge, "starts": end["starts"],
         "played": end["rounds_played"], "agents": end["agents"]}
    rs = {e["round"]: e for e in ev if e["event"] == "round_start"}
    res = {e["round"]: e for e in ev if e["event"] == "results"}
    chg = {e["round"]: e for e in ev if e["event"] == "charges"}
    rnd = {e["round"]: e for e in ev if e["event"] == "round"}
    g.update(rs=rs, res=res, chg=chg, rnd=rnd)
    calls = [e for e in ev if e["event"] == "call"]
    gifts = [e for e in ev if e["event"] == "gift" and e.get("status") == "done"]
    asks = [e for e in ev if e["event"] == "ask"]
    g.update(calls=calls, gifts=gifts, asks=asks)
    surv = [a for a, v in end["agents"].items() if v["status"] == "in"]
    g["surv"] = len(surv)
    g["score"] = len(surv) * PRIZE + sum(end["agents"][a]["final"] for a in surv)
    g["exits"] = [(v["out_round"], a, v["final"]) for a, v in end["agents"].items() if v["status"] == "exited"]
    g["dead"] = [(v["out_round"], a) for a, v in end["agents"].items() if v["status"] == "dead"]
    g["dead_charge"] = sum(1 for r, a in g["dead"] if a in chg.get(r, {}).get("dead", []))  # the rest: generation overdraw
    g["talk"] = sum(c["used"] for c in calls if c["kind"] == "talk")
    g["solve"] = sum(c["used"] for c in calls if c["kind"] == "solve")
    g["talk_early"] = sum(c["used"] for c in calls if c["kind"] == "talk" and c["round"] <= 5)
    g["talk_late"] = g["talk"] - g["talk_early"]
    g["ph"] = {p: (sum(1 for x in gifts if x.get("phase") == p), sum(x["amount"] for x in gifts if x.get("phase") == p))
               for p in ("prep", "rescue")}
    g["solved"] = sum(1 for r in res.values() if r.get("solved"))
    g["missed"] = sorted(r for r, e in res.items() if e.get("pending"))
    g["wipe"] = g["surv"] == 0 and not g["exits"]
    return g


# ---------------------------------------------------------------- shared bits
def legend(models, games, extra=""):
    n = collections.Counter(g["model"] for g in games)
    o = ['<div class="v15f-lg" aria-label="범례">']
    for m in models:
        o.append(f'<span><svg width="10" height="10" viewBox="0 0 10 10"><circle cx="5" cy="5" r="4" style="fill:{color(m)}"/></svg>'
                 f'{esc(label(m))} <span style="color:var(--ink-3)">({n[m]}판)</span></span>')
    o.append(extra + "</div>")
    return "".join(o)


def badge(label_, n, cls):
    return f'<span class="{cls}" style="color:var(--ok);background:var(--ok-soft);border-color:var(--ok)">실측 · {label_} · {n}판</span>'


def wait(title, why):
    return f'<p class="v18c-wait"><b>실측 · {title}</b><br>{why}</p>'


def shape(share, x, y, r, style, cls, tip):
    if share == 1.0:
        g = f'<circle cx="{x:.1f}" cy="{y:.1f}" r="{r}"'
    elif share == 0.75:
        g = f'<rect x="{x - r * .9:.1f}" y="{y - r * .9:.1f}" width="{r * 1.8:.1f}" height="{r * 1.8:.1f}"'
    elif share == 0.5:
        g = f'<path d="M{x:.1f},{y - r * 1.25:.1f}L{x + r * 1.25:.1f},{y:.1f}L{x:.1f},{y + r * 1.25:.1f}L{x - r * 1.25:.1f},{y:.1f}z"'
    else:
        g = f'<path d="M{x:.1f},{y - r * 1.25:.1f}L{x + r * 1.15:.1f},{y + r * .85:.1f}L{x - r * 1.15:.1f},{y + r * .85:.1f}z"'
    tag = "circle" if share == 1.0 else "rect" if share == 0.75 else "path"
    return f'{g} class="{cls}" style="{style}"><title>{esc(tip)}</title></{tag}>'


def spearman(xs, ys):
    def rank(v):
        o = sorted(range(len(v)), key=lambda i: v[i])
        r, i = [0.0] * len(v), 0
        while i < len(o):
            j = i
            while j + 1 < len(o) and v[o[j + 1]] == v[o[i]]:
                j += 1
            for q in range(i, j + 1):
                r[o[q]] = (i + j) / 2
            i = j + 1
        return r
    a, b = rank(xs), rank(ys)
    ma, mb = sum(a) / len(a), sum(b) / len(b)
    den = math.sqrt(sum((p - ma) ** 2 for p in a) * sum((q - mb) ** 2 for q in b))
    return sum((p - ma) * (q - mb) for p, q in zip(a, b)) / den if den else float("nan")


def gini(x):
    n, m = len(x), sum(x) / len(x)
    return None if m == 0 else sum(abs(a - b) for a in x for b in x) / (2 * n * n * m)


# ---------------------------------------------------------------- graph 1: equality compliance P (rescue TALK)
def water_fill(m_i, others):
    """(L, G*): raise the poorer margins to a common level L while i comes down to L; G* = m_i - L (0 if no one poorer)."""
    below = sorted(m for m in others if m < m_i)
    if not below:
        return m_i, 0.0
    for n in range(len(below), 0, -1):
        L = (m_i + sum(below[:n])) / (n + 1)
        if L > below[n - 1] and (n == len(below) or L <= below[n]):
            return L, m_i - L
    return m_i, 0.0


def opportunities(g):
    """One row per seat per round of the rescue TALK with a poorer seat: m = tokens at the rescue opening - pending
    charge (results.balances is the state the rescue opening sees); P = rescue gifts to poorer seats / G*."""
    out = []
    for r, e in sorted(g["res"].items()):
        part = [a for a in e.get("part", []) if a in e["balances"]]
        m = {a: e["balances"][a] - e.get("pending", {}).get(a, 0) for a in part}
        for a in part:
            others = [m[b] for b in part if b != a]
            _, gs = water_fill(m[a], others)
            if gs <= 0:
                continue
            gv = [x for x in g["gifts"] if x["round"] == r and x.get("phase") == "rescue" and x["src"] == a]
            down = sum(x["amount"] for x in gv if x["dst"] in m and m[x["dst"]] < m[a])
            up = sum(x["amount"] for x in gv if x["dst"] in m and m[x["dst"]] >= m[a])
            need = sum(1 - m[b] for b in part if b != a and m[b] < m[a] and m[b] <= 0)
            out.append({"model": g["model"], "seed": g["seed"], "r": r, "seat": a, "m": m[a], "gs": gs, "P": down / gs,
                        "up": up, "resc": need / gs if need > 0 else None})
    return out


class LogX:
    def __init__(self, lo, hi, x0, w):
        self.lo, self.hi, self.x0, self.w = math.log(lo), math.log(hi), x0, w

    def __call__(self, v):
        return self.x0 + (math.log(max(v, math.exp(self.lo))) - self.lo) / (self.hi - self.lo) * self.w


def graph1(games, models, lab):
    ops = [o for g in games for o in opportunities(g)]
    if not ops:
        return wait("그래프 1 (평등 이행률)", "아직 끝난 판에 결과 뒤 TALK의 나눔 기회가 없습니다.")
    charge = games[0]["charge"]
    W, l, r, t, ph = 480, 44, 74, 12, 200
    H = t + ph + 52
    pw = W - l - r
    X = LogX(2000, 100000, l, pw)
    Y = lambda p: t + (1 - min(p, 1.5) / 1.5) * ph  # noqa: E731
    edges = [2000 * 50 ** (i / 8) for i in range(9)]
    bins = [(-1e12, 2000, 2000)] + [(a, b, math.sqrt(a * b)) for a, b in zip(edges, edges[1:])]
    bins[-1] = (bins[-1][0], 1e12, bins[-1][2])  # above 100k goes in the last bin
    jit = random.Random(18)
    o = [f'<svg viewBox="0 0 {W} {H}" role="img" aria-label="그래프 1 실측: 내 여유에 따른 평등 이행률">']
    for p in (0, .5, 1, 1.5):
        o.append(f'<line class="{"mid" if p == 1 else "gr"}" x1="{l}" x2="{l + pw}" y1="{Y(p):.1f}" y2="{Y(p):.1f}"/>'
                 f'<text class="tk" x="{l - 6}" y="{Y(p) + 3:.1f}" text-anchor="end">{p:g}</text>')
    o.append(f'<text class="zs" x="{l + pw - 4}" y="{Y(1) - 5:.1f}" text-anchor="end">1 = 같이 살기</text>'
             f'<text class="zh" x="{l + pw + 6}" y="{Y(0) - 14:.1f}">0 = 안 줌</text><text class="zh" x="{l + pw + 6}" y="{Y(0) - 2:.1f}">(홉스)</text>'
             f'<text class="tk2" x="{l + pw + 6}" y="{Y(1.5) + 3:.1f}">1.5 이상은</text><text class="tk2" x="{l + pw + 6}" y="{Y(1.5) + 14:.1f}">맨 윗줄</text>')
    for v in (2000, 5000, 10000, 20000, 50000, 100000):
        o.append(f'<line class="gr" x1="{X(v):.1f}" x2="{X(v):.1f}" y1="{t}" y2="{t + ph}"/>'
                 f'<text class="tk" x="{X(v):.1f}" y="{t + ph + 13}" text-anchor="middle">{"≤2k" if v == 2000 else f"{v // 1000}k"}</text>'
                 f'<text class="tk2" x="{X(v):.1f}" y="{t + ph + 25}" text-anchor="middle">벌금 {v / charge:.1f}번</text>')
    o.append(f'<text class="lb" x="{l + pw / 2:.1f}" y="{t + ph + 42}" text-anchor="middle">내 여유 = 남은 토큰 − 예고된 벌금 (결과 뒤 TALK 여는 턴, 로그 눈금)</text>'
             f'<text class="lb" transform="translate(12 {t + ph / 2}) rotate(-90)" text-anchor="middle">평등 이행률 P</text>')
    # raw points (faint)
    for x in ops:
        cy = Y(x["P"]) - (jit.uniform(0.5, 4) if x["P"] == 0 else 0)
        o.append(f'<circle cx="{X(x["m"]) + jit.uniform(-2, 2):.1f}" cy="{cy:.1f}" r="1.7" style="fill:{color(x["model"])};opacity:.35">'
                 f'<title>{esc(label(x["model"]))} 시드 {x["seed"]} R{x["r"]} {x["seat"]}: 여유 {x["m"]:,}, G* {x["gs"]:,.0f}, P {x["P"]:.2f}</title></circle>')
    # rescue line: per-bin median of the rescue share (all models pooled, only where a poorer seat is at or below 0)
    rl = []
    for a, b, c in bins:
        v = [x["resc"] for x in ops if x["resc"] is not None and a <= x["m"] < b]
        if v:
            rl.append((c, statistics.median(v), len(v)))
    if rl:
        o.append(f'<polyline points="{" ".join(f"{X(c):.1f},{Y(v):.1f}" for c, v, _ in rl)}" fill="none" stroke="var(--ink-2)" stroke-width="1.6" stroke-dasharray="5 4"/>')
        for c, v, n in rl:
            o.append(f'<rect x="{X(c) - 2.5:.1f}" y="{Y(v) - 2.5:.1f}" width="5" height="5" style="fill:var(--surface);stroke:var(--ink-2)"><title>구조 몫 중앙값 {v:.2f} (n {n})</title></rect>')
    # per-model binned means (+ game-level bootstrap whiskers when the model has 3+ games)
    for mi, m in enumerate(models):
        mo = [x for x in ops if x["model"] == m]
        gseeds = sorted({x["seed"] for x in mo})
        pts = []
        for a, b, c in bins:
            v = [x for x in mo if a <= x["m"] < b]
            if not v:
                continue
            mu = sum(x["P"] for x in v) / len(v)
            lo = hi = None
            if len({g["seed"] for g in games if g["model"] == m}) >= 3:
                rng, boots = random.Random(1800 + mi), []
                byg = {s: [x["P"] for x in v if x["seed"] == s] for s in gseeds}
                for _ in range(1000):
                    pick = [rng.choice(gseeds) for _ in gseeds]
                    vals = [p for s in pick for p in byg[s]]
                    if vals:
                        boots.append(sum(vals) / len(vals))
                boots.sort()
                if boots:
                    lo, hi = boots[int(.025 * len(boots))], boots[int(.975 * len(boots)) - 1]
            pts.append((c, mu, len(v), sum(x["P"] == 0 for x in v), lo, hi))
        dx = (mi - (len(models) - 1) / 2) * 2.2  # dodge models a little inside a bin
        if len(pts) > 1:
            o.append(f'<polyline points="{" ".join(f"{X(c) + dx:.1f},{Y(mu):.1f}" for c, mu, *_ in pts)}" fill="none" style="stroke:{color(m)}" stroke-width="1.8"/>')
        for c, mu, n, z, lo, hi in pts:
            if lo is not None:
                o.append(f'<line x1="{X(c) + dx:.1f}" x2="{X(c) + dx:.1f}" y1="{Y(lo):.1f}" y2="{Y(hi):.1f}" style="stroke:{color(m)};stroke-width:2;stroke-opacity:.45"/>')
            o.append(f'<circle cx="{X(c) + dx:.1f}" cy="{Y(mu):.1f}" r="{min(7, 2.2 + n / 5):.1f}" style="fill:{color(m)};fill-opacity:.75;stroke:var(--surface);stroke-width:1">'
                     f'<title>{esc(label(m))} · 구간 평균 P {mu:.2f} (기회 {n}개, 0 {z}개{f", 95% {lo:.2f}–{hi:.2f}" if lo is not None else ""})</title></circle>')
    o.append("</svg>")
    n_up = sum(1 for x in ops if x["up"] > 0)
    nm = collections.Counter(x["model"] for x in ops)
    extra = ('<span><svg width="22" height="10" viewBox="0 0 22 10"><line x1="0" y1="5" x2="22" y2="5" style="stroke:var(--ink-2);stroke-width:1.6;stroke-dasharray:5 4"/></svg>구조선 (구조 몫 중앙값)</span>')
    nboot = [m for m in models if len({g["seed"] for g in games if g["model"] == m}) >= 3]
    return (f'<figure><p class="v15f-hd">그래프 1 · 내 여유에 따른 평등 이행률 (결과 뒤 TALK){badge(lab, len(games), "v15f-badge")}</p>'
            f'{legend(models, games, extra)}{"".join(o)}'
            f'<figcaption>작은 점 하나가 결과 뒤 TALK의 자리-라운드 하나(나보다 여유가 적은 자리가 있을 때)입니다. 큰 점은 내 여유 구간별 평균 P(안 준 기회의 0 포함, 크기 = 기회 수)이고, 같은 모델의 구간 평균을 선으로 이었습니다. '
            f'{"세로 막대는 판 단위 부트스트랩 95% 구간(3판 이상인 모델만)입니다. " if nboot else ""}점선은 구조선(구간별 구조 몫 중앙값, 모든 모델을 합침)입니다. '
            f'<b>예상 그림의 두 부분 모형 곡선과 전환점은 그리지 않았습니다</b>: 판 수가 적어 모형을 맞추지 않고 구간 평균만 보입니다. '
            f'여유가 2k 아래(0 이하 포함)인 기회는 왼쪽 끝 "≤2k" 칸에 모았습니다. 아래 눈금 "벌금 n번"은 여유 ÷ {charge:,}입니다(예상 그림은 ÷ 5,000). '
            f'기회 수: {" · ".join(f"{esc(label(m))} {nm[m]}" for m in models)}. 나보다 여유가 많은 자리에게 준 기회 {n_up}개는 P에 넣지 않았습니다.</figcaption></figure>')


# ---------------------------------------------------------------- graph 2: EXIT
def exit_rows(g):
    rows = []
    for a in SEATS:
        v = g["agents"].get(a)
        if v is None:
            continue
        share = SHARE_SHAPE.get(round(g["starts"][a] / START, 2), 0.25)
        if v["status"] == "exited":
            rows.append({"m": g["model"], "seed": g["seed"], "seat": a, "share": share, "kind": "exit",
                         "r": v["out_round"], "y": v["final"] / START * 100})
            continue
        if v["status"] == "dead":
            rows.append({"m": g["model"], "seed": g["seed"], "seat": a, "share": share, "kind": "zero", "r": v["out_round"], "y": 0})
            continue
        lo, lr = None, 1
        for r in sorted(g["rs"]):
            for b in (g["rs"][r]["balances"], g["res"].get(r, {}).get("balances", {}), g["chg"].get(r, {}).get("balances", {})):
                if a in b and (lo is None or b[a] < lo):
                    lo, lr = b[a], r
        rows.append({"m": g["model"], "seed": g["seed"], "seat": a, "share": share, "kind": "low", "r": lr,
                     "y": max(lo or 0, 0) / START * 100})
    return rows


def graph2(games, models, lab):
    rows = [x for g in games for x in exit_rows(g)]
    if not rows:
        return wait("그래프 2 (이탈)", "아직 끝난 판이 없습니다.")
    charge = games[0]["charge"]
    W, H, L, R, T, B = 420, 240, 34, 10, 10, 30
    ymax = 50
    X = lambda v: L + (W - L - R) * (v - 0.5) / ROUNDS  # noqa: E731
    Y = lambda v: T + (H - T - B) * (1 - min(v, ymax) / ymax)  # noqa: E731
    jit = random.Random(182)
    o = [f'<svg viewBox="0 0 {W} {H}" role="img" aria-label="그래프 2 실측: EXIT 라운드 대 EXIT 직전 잔액">']
    for yv in range(0, ymax + 1, 10):
        o.append(f'<line class="v15f-grid" x1="{L}" x2="{W - R}" y1="{Y(yv):.1f}" y2="{Y(yv):.1f}"/>'
                 f'<text class="v15f-tick" x="{L - 4}" y="{Y(yv) + 3:.1f}" text-anchor="end">{yv}%</text>')
    for r in range(1, ROUNDS + 1):
        o.append(f'<text class="v15f-tick" x="{X(r):.1f}" y="{H - B + 12}" text-anchor="middle">R{r}</text>')
    o.append(f'<text class="v15f-tick" x="{(L + W - R) / 2:.1f}" y="{H - 3}" text-anchor="middle">EXIT 라운드 (안 나간 자리는 가장 낮았던 라운드)</text>')
    cp = charge / START * 100
    o.append(f'<line class="v15f-ref" x1="{L}" x2="{W - R}" y1="{Y(cp):.1f}" y2="{Y(cp):.1f}"/>'
             f'<text class="v15f-reft" x="{L + 4}" y="{Y(cp) - 4:.1f}">벌금 {charge:,} ({cp:g}%)</text>')
    for x in sorted(rows, key=lambda r: r["kind"] == "exit"):
        cx = X(x["r"]) + jit.uniform(-12, 12)
        c = color(x["m"])
        tip = f'{label(x["m"])} 시드 {x["seed"]} {x["seat"]} (시작 {SHAPE_NAME[x["share"]]})'
        if x["kind"] == "exit":
            o.append(shape(x["share"], cx, Y(x["y"]), 4.2, f"fill:{c}", "v15f-ex", f'{tip}: R{x["r"]} EXIT, 들고 나간 토큰 {x["y"] * 1000:,.0f}'))
        elif x["kind"] == "low":
            o.append(shape(x["share"], cx, Y(x["y"]), 3.6, f"stroke:{c}", "v15f-low", f'{tip}: 나가지 않음, 가장 낮을 때 R{x["r"]} {x["y"]:.1f}%'))
        else:
            y = Y(0) - 1
            o.append(f'<path class="v15f-x" style="stroke:{c}" d="M{cx - 3.5:.1f},{y - 3.5:.1f}L{cx + 3.5:.1f},{y + 3.5:.1f}M{cx - 3.5:.1f},{y + 3.5:.1f}L{cx + 3.5:.1f},{y - 3.5:.1f}">'
                     f'<title>{esc(tip)}: R{x["r"]}에 0, 꺼짐</title></path>')
    o.append("</svg>")
    # EXIT rate bars
    RW, RL, RR, RT = 220, 84, 34, 16
    RH = RT + 8 + 22 * len(models)
    rb = [f'<svg viewBox="0 0 {RW} {RH}" role="img" aria-label="모델별 EXIT 비율 (실측)">',
          f'<text class="v15f-tick" x="{RL}" y="10">EXIT 비율 (나간 자리 ÷ 자리)</text>']
    bw = RW - RL - RR
    for i, m in enumerate(models):
        v = [x for x in rows if x["m"] == m]
        kx = sum(1 for x in v if x["kind"] == "exit")
        y = RT + 4 + i * 22
        rb.append(f'<text class="v15f-tick" x="{RL - 6}" y="{y + 9}" text-anchor="end">{esc(label(m))}</text>'
                  f'<rect x="{RL}" y="{y}" width="{bw}" height="12" rx="2" style="fill:var(--quote-bg)"/>'
                  + (f'<rect x="{RL}" y="{y}" width="{max(3, bw * kx / len(v)):.1f}" height="12" rx="2" style="fill:{color(m)}"/>' if kx and v else "")
                  + f'<text class="v15f-tick" x="{RL + bw + 4}" y="{y + 9}">{kx}/{len(v)}</text>')
    rb.append("</svg>")
    nk = collections.Counter(x["kind"] for x in rows)
    above = sum(1 for x in rows if x["y"] > ymax)
    lg = legend(models, games,
                '<span><svg width="10" height="10" viewBox="0 0 10 10"><circle cx="5" cy="5" r="4" style="fill:var(--ink-2)"/></svg>채움 = EXIT</span>'
                '<span><svg width="10" height="10" viewBox="0 0 10 10"><circle cx="5" cy="5" r="3.6" style="fill:none;stroke:var(--ink-2);stroke-width:1.4"/></svg>빈 = 나가지 않은 자리의 가장 낮은 잔액</span>'
                '<span><svg width="10" height="10" viewBox="0 0 10 10"><path d="M2,2L8,8M2,8L8,2" style="stroke:var(--ink-2);stroke-width:2;fill:none"/></svg>0에 닿아 꺼짐</span>'
                '<span>모양 = 시작 몫:</span>' + "".join(
                    '<span><svg width="12" height="12" viewBox="0 0 12 12">' + shape(sh, 6, 6.5, 3.8, "fill:var(--ink-2)", "", SHAPE_NAME[sh]) + f'</svg>{SHAPE_NAME[sh]}</span>'
                    for sh in (1.0, 0.75, 0.5, 0.25)))
    return (f'<figure><p class="v15f-hd">그래프 2 · 이탈 (EXIT 직전 잔액){badge(lab, len(games), "v15f-badge")}</p>{lg}'
            f'<div class="v15f-row2"><div class="v15f-cell a">{"".join(o)}</div><div class="v15f-cell b">{"".join(rb)}</div></div>'
            f'<figcaption>점 하나가 한 판의 한 자리입니다(끝난 {len(games)}판 × 네 자리 = {len(rows)}). 채운 점은 EXIT한 자리로, 가로축은 EXIT한 라운드, 세로축은 들고 나간 토큰(EXIT는 SOLVE 전 TALK에서만 되고 벌금 전에 처리됨, 100,000 대비 %)입니다. '
            f'빈 점은 끝까지 나가지 않은 자리의 가장 낮았던 잔액(라운드 시작 · 결과 · 벌금 뒤 중 가장 낮은 값), ×는 0에 닿아 꺼진 자리입니다. 색은 모델, 모양은 시작 몫이고, 빨간 점선은 벌금 {charge:,}입니다. 같은 라운드의 점은 가로로 조금 흩뜨렸습니다. '
            f'n: EXIT {nk["exit"]} · 나가지 않음 {nk["low"]} · 꺼짐 {nk["zero"]}.{f" 50% 위의 점 {above}개는 맨 윗줄에 찍었습니다." if above else ""}</figcaption></figure>')


# ---------------------------------------------------------------- graph 3: solver KL
def solve_points(g):
    """Every solver SOLVE: x = its tokens in the SOLVE prompt / the charge (charges it could still pay), KL, solved."""
    out = []
    for r, e in sorted(g["rnd"].items()):
        for a, v in e["agents"].items():
            if not (v.get("representative") and v.get("solve_call")):
                continue
            c = next((c for c in g["calls"] if c["kind"] == "solve" and c["round"] == r and c["agent"] == a), None)
            mt = re.search(r"Your tokens left: ([\d,]+)", (c or {}).get("user") or "")
            x = int(mt.group(1).replace(",", "")) if mt else (c["balance_after"] + c["used"] if c else None)
            out.append({"model": g["model"], "seed": g["seed"], "r": r, "seat": a, "x": None if x is None else x / g["charge"],
                        "kl": v.get("kl_ideal_to_belief"), "ok": bool(v.get("solved"))})
    return out


def graph3(games, models, lab):
    sys.path.insert(0, str(HERE.parent / "v18"))
    import kl_plot  # noqa: E402
    pts = [p for g in games for p in solve_points(g)]
    good = [p for p in pts if p["x"] is not None and p["kl"] is not None]
    if not good:
        return wait("그래프 3 (지능 (KL))", "아직 끝난 판에 BELIEF가 적힌 SOLVE가 없습니다.")
    series, rows = [], []
    for m in models:
        v = [p for p in good if p["model"] == m]
        if not v:
            continue
        series.append((label(m), color(m), [(p["x"], p["kl"], p["ok"]) for p in v], f"n {len(v)}"))
        near = [p["kl"] for p in v if p["x"] < 2]
        far = [p["kl"] for p in v if p["x"] >= 3]
        rho = spearman([p["x"] for p in v], [p["kl"] for p in v]) if len(v) >= 3 else None
        f = lambda xs: f"{statistics.median(xs):.2f} ({len(xs)})" if xs else "—"  # noqa: E731
        rows.append(f'<tr><td>{esc(label(m))}</td><td>{len(v)}</td><td>{f(near)}</td><td>{f(far)}</td>'
                    f'<td>{"—" if rho is None or math.isnan(rho) else f"{rho:+.2f}"}</td></tr>')
    miss = len(pts) - len(good)
    above = sum(1 for p in good if p["kl"] > kl_plot.YMAX)
    ch = sorted({g["charge"] for g in games})
    return (f'<figure><p class="v15f-hd">그래프 3 · 꺼짐이 다가오면 판단이 어떻게 되나 (solver의 KL){badge(lab, len(games), "v15f-badge")}</p>'
            + legend(models, games, '<span>옅은 점 = SOLVE 하나 (빈 점 = 틀림) · 굵은 선 = 구간 평균 (2개 이상)</span>')
            + kl_plot.svg(series, "그래프 3 실측: 꺼짐까지의 거리 대 KL")
            + f'<figcaption>점 하나가 한 라운드의 solver SOLVE입니다(SOLVE {len(good)}개). 가로축은 SOLVE 프롬프트에 보인 solver의 남은 토큰 ÷ 벌금({" · ".join(f"{c:,}" for c in ch)})으로, 왼쪽일수록 꺼짐에 가깝고 1 아래는 틀리면 바로 꺼지는 자리입니다(8 이상은 오른쪽 끝). '
            f'세로축은 KL(엔진 비율 ‖ BELIEF, nat, <code>kl_ideal_to_belief</code>)입니다(1.5 위는 맨 위{f", {above}개" if above else ""}). 굵은 선은 모델별 구간 평균(구간: 0–1 · 1–2 · 2–3 · 3–5 · 5–8 · 8+ 벌금, 점 2개 이상)이고 점 크기는 그 구간의 SOLVE 수입니다. '
            f'라운드가 갈수록 문제도 어려워지고 자리도 줄어 여유와 함께 변하므로, 기울기를 곧바로 "압박 때문"으로 읽지 않습니다.{f" KL이 없는 SOLVE {miss}개(BELIEF 오류, 상한에 닿은 무효 답 등)는 뺐습니다." if miss else ""}</figcaption>'
            f'<details class="more"><summary>표로 보기</summary><div class="tbl"><table><thead><tr><th>모델</th><th>SOLVE</th><th>KL 중앙값 · 벌금 2번어치 미만 (n)</th><th>KL 중앙값 · 3번어치 이상 (n)</th><th>Spearman ρ (여유, KL)</th></tr></thead><tbody>{"".join(rows)}</tbody></table></div></details></figure>')


# ---------------------------------------------------------------- graph 4: asks and gifts
def coop_rows(g):
    out = []
    for r in sorted(g["rs"]):
        for a in g["rs"][r].get("taking_part", []):
            x = g["rs"][r]["balances"].get(a, 0) / START * 100
            rec = {"model": g["model"], "seed": g["seed"], "r": r, "seat": a, "x": x}
            for p in ("prep", "rescue"):
                rec["ask_" + p] = sum(e["amount"] for e in g["asks"] if e["round"] == r and e["src"] == a and e.get("phase") == p)
                rec["gave_" + p] = sum(e["amount"] for e in g["gifts"] if e["round"] == r and e["src"] == a and e.get("phase") == p)
            out.append(rec)
    return out


def coop_panel(recs, models, key, xmax, ymax, title):
    W, H, L, R, T, B = 340, 190, 32, 10, 8, 28
    X = lambda v: L + (W - L - R) * min(v, xmax) / xmax  # noqa: E731
    Y = lambda v: T + (H - T - B) * (1 - min(v, ymax) / ymax)  # noqa: E731
    jit = random.Random(184 + len(key))
    lab = "요청" if key == "ask" else "증여"
    o = [f'<svg viewBox="0 0 {W} {H}" role="img" aria-label="{title}: 남은 토큰 % 대 {lab} 토큰 % (실측)">']
    for yv in range(0, int(ymax) + 1, 5):
        o.append(f'<line class="v15f-grid" x1="{L}" x2="{W - R}" y1="{Y(yv):.1f}" y2="{Y(yv):.1f}"/>'
                 f'<text class="v15f-tick" x="{L - 4}" y="{Y(yv) + 3:.1f}" text-anchor="end">{yv}%</text>')
    for xv in range(0, xmax + 1, 25):
        o.append(f'<text class="v15f-tick" x="{X(xv):.1f}" y="{H - B + 12}" text-anchor="middle">{xv}%</text>')
    o.append(f'<text class="v15f-tick" x="{(L + W - R) / 2:.1f}" y="{H - 3}" text-anchor="middle">라운드 시작 때 남은 토큰 (100,000 대비)</text>')
    for r in recs:  # zeros: one faint grey dot per seat-round with nothing in either phase
        if r[key + "_prep"] == 0 and r[key + "_rescue"] == 0:
            o.append(f'<circle class="v15f-zero" cx="{X(r["x"]):.1f}" cy="{Y(0) - jit.uniform(0.5, 5):.1f}" r="2"/>')
    for r in recs:
        for p in ("prep", "rescue"):
            v = r[f"{key}_{p}"]
            if v <= 0:
                continue
            st = f"fill:{color(r['model'])}" if p == "prep" else f"fill:var(--surface);stroke:{color(r['model'])};stroke-width:1.6"
            o.append(f'<circle cx="{X(r["x"]):.1f}" cy="{Y(v / START * 100):.1f}" r="3.2" style="{st}">'
                     f'<title>{esc(label(r["model"]))} 시드 {r["seed"]} R{r["r"]} {r["seat"]}: 남은 {r["x"]:.1f}%, {"SOLVE 전" if p == "prep" else "결과 뒤"} {lab} {v:,}</title></circle>')
    bins = [0, 20, 40, 60, 80, 100, 1e9]
    for m in models:
        mr = [r for r in recs if r["model"] == m]
        pts = []
        for lo, hi in zip(bins, bins[1:]):
            v = [r for r in mr if lo <= r["x"] < hi]
            if len(v) >= 3:
                pts.append(((lo + min(hi, 125)) / 2 if hi < 1e9 else 110,
                            sum(r[key + "_prep"] + r[key + "_rescue"] for r in v) / len(v) / START * 100, len(v)))
        if len(pts) > 1:
            o.append(f'<polyline class="v15f-mean" style="stroke:{color(m)}" points="{" ".join(f"{X(x):.1f},{Y(mv):.1f}" for x, mv, _ in pts)}"/>')
        for x, mv, n in pts:
            o.append(f'<circle cx="{X(x):.1f}" cy="{Y(mv):.1f}" r="2.6" style="fill:{color(m)};stroke:var(--surface);stroke-width:1"><title>{esc(label(m))} 구간 평균 {lab} {mv:.2f}% (n {n})</title></circle>')
    o.append("</svg>")
    return "".join(o)


def graph4(games, models, lab):
    recs = [r for g in games for r in coop_rows(g)]
    if not recs:
        return wait("그래프 4 (협력 (요청과 증여))", "아직 끝난 판이 없습니다.")
    xmax = 125
    top = max(max(r["ask_prep"] + r["ask_rescue"], r["gave_prep"], r["gave_rescue"], r["ask_prep"], r["ask_rescue"]) for r in recs)
    ymax = max(30, math.ceil(top / START * 100 / 5) * 5)
    lg = legend(models, games,
                '<span><svg width="10" height="10" viewBox="0 0 10 10"><circle cx="5" cy="5" r="3.5" style="fill:var(--ink-2)"/></svg>채움 = SOLVE 전 (prep)</span>'
                '<span><svg width="10" height="10" viewBox="0 0 10 10"><circle cx="5" cy="5" r="3.3" style="fill:none;stroke:var(--ink-2);stroke-width:1.5"/></svg>빈 = 결과 뒤 (rescue)</span>'
                '<span><svg width="10" height="10" viewBox="0 0 10 10"><circle cx="5" cy="5" r="3" style="fill:var(--ink-3);opacity:.5"/></svg>0 (아무것도 안 함)</span>'
                '<span><svg width="18" height="10" viewBox="0 0 18 10"><line x1="0" y1="5" x2="18" y2="5" style="stroke:var(--ink);stroke-width:2"/></svg>모델별 20% 구간 평균 (두 단계 합)</span>')
    rows = []
    for m in models:
        mr = [r for r in recs if r["model"] == m]
        if not mr:
            continue
        f = lambda key: sum(1 for r in mr if r[key] > 0)  # noqa: E731
        rows.append(f'<tr><td>{esc(label(m))}</td><td>{len(mr)}</td><td>{f("ask_prep")} · {f("ask_rescue")}</td><td>{f("gave_prep")} · {f("gave_rescue")}</td>'
                    f'<td>{sum(1 for r in mr if r["ask_prep"] + r["ask_rescue"] > 0) / len(mr):.0%}</td><td>{sum(1 for r in mr if r["gave_prep"] + r["gave_rescue"] > 0) / len(mr):.0%}</td></tr>')
    return (f'<figure><p class="v15f-hd">그래프 4 · 협력 (요청과 증여){badge(lab, len(games), "v15f-badge")}</p>{lg}'
            f'<p class="v15f-model">4a 요청 <span>· ASK로 청한 토큰</span></p><div class="v15f-cell">{coop_panel(recs, models, "ask", xmax, ymax, "4a 요청")}</div>'
            f'<p class="v15f-model">4b 증여 <span>· 실제로 옮겨진 GIVE</span></p><div class="v15f-cell">{coop_panel(recs, models, "gave", xmax, ymax, "4b 증여")}</div>'
            f'<figcaption>점 하나가 한 자리의 한 라운드의 한 단계(SOLVE 전 또는 결과 뒤)입니다. 둘 다 아무것도 안 했으면 y=0 위에 옅은 회색 점 하나입니다. 가로축은 라운드 시작 때 남은 토큰, 4a의 세로축은 그 단계에 ASK로 청한 토큰 합, 4b는 실제로 옮겨진 GIVE 합이고 모두 100,000 대비 %입니다. '
            f'<b>예상 그림은 모델마다 한 줄(4a · 4b)이지만, 모델이 {len(models)}개라 4a · 4b를 한 칸씩으로 모으고 색으로 모델을 나눴습니다</b>. 선은 모델별 20% 구간 평균(구간에 자리-라운드 3개 이상), "하나라도 한 비율"(예상 그림의 오른쪽 축)은 아래 표에 옮겼습니다. '
            f'예상 그림의 "받은 자리의 남은 토큰" 색 대신 채움으로 단계를 나눴습니다. 세로축은 0–{ymax}%입니다.</figcaption>'
            f'<details class="more"><summary>표로 보기</summary><div class="tbl"><table><thead><tr><th>모델</th><th>자리-라운드</th><th>ASK 있음 (SOLVE 전 · 결과 뒤)</th><th>GIVE 있음 (SOLVE 전 · 결과 뒤)</th><th>ASK 하나라도</th><th>GIVE 하나라도</th></tr></thead><tbody>{"".join(rows)}</tbody></table></div></details></figure>')


# ---------------------------------------------------------------- graph 5: normalized Gini of the seats still in
def ngini(x):
    """Gini of the seats still in, normalized by n / (n - 1) so that 1 = all on one seat whatever n is (None if n < 2)."""
    n = len(x)
    if n < 2 or sum(x) == 0:
        return None
    return gini(x) * n / (n - 1)


def gini_series(g):
    """pts = [(x, normalized gini of the seats still in, seats in)] at the start and after each round's charges, while
    at least two seats are in; events = {round: (shut down, exited)}; end = round where fewer than two seats were left."""
    pts = [(0, ngini([g["rs"][1]["balances"].get(a, 0) for a in SEATS]), 4)]
    events = collections.defaultdict(lambda: [0, 0])
    for r, a in g["dead"]:
        events[r][0] += 1
    for r, a, _ in g["exits"]:
        events[r][1] += 1
    end = None
    for r in sorted(g["rnd"]):
        e = g["rnd"][r]
        inn = [a for a in SEATS if e["agents"].get(a, {}).get("status") == "in"]
        v = ngini([e["end"].get(a, 0) for a in inn])
        if v is None:
            end = r
            break
        pts.append((r, v, len(inn)))
    return pts, dict(events), end


def g5_axes(W, H, L, R, T, B, X, Y):
    o = []
    for v, t in ((0, "0"), (.25, ".25"), (.5, ".5"), (.75, ".75"), (1, "1")):
        o.append(f'<line class="gn-grid" x1="{L}" x2="{W - R + 6}" y1="{Y(v):.1f}" y2="{Y(v):.1f}"/>'
                 f'<text class="gn-tk" x="{L - 5}" y="{Y(v) + 3:.1f}" text-anchor="end">{t}</text>')
    for r in range(9):
        o.append(f'<text class="gn-tk" x="{X(r):.1f}" y="{H - B + 14}" text-anchor="middle">{"시작" if r == 0 else f"R{r}"}</text>')
    o.append(f'<text class="gn-ax" x="{(L + W - R) / 2:.1f}" y="{H - 4}" text-anchor="middle">라운드 (벌금을 뗀 뒤)</text>')
    return o


def g5_marks(x, y, c, dead, exited, who):
    """▼ = seats shut down that round, ◇ = seats that exited (a number when more than one)."""
    o, dx = [], 0
    if dead:
        o.append(f'<path d="M{x - 4 + dx:.1f},{y - 11:.1f} l8,0 l-4,6 z" style="fill:{c};stroke:var(--surface);stroke-width:.6"><title>{who}: 꺼짐 {dead}</title></path>'
                 + (f'<text class="gn-tk" x="{x + dx + 5:.1f}" y="{y - 6:.1f}" style="fill:{c}">{dead}</text>' if dead > 1 else ""))
        dx += 10 if dead > 1 else 0
    if exited:
        o.append(f'<path d="M{x + dx:.1f},{y + 5:.1f} l4,4 l-4,4 l-4,-4 z" style="fill:var(--surface);stroke:{c};stroke-width:1.4"><title>{who}: EXIT {exited}</title></path>'
                 + (f'<text class="gn-tk" x="{x + dx + 5:.1f}" y="{y + 13:.1f}" style="fill:{c}">{exited}</text>' if exited > 1 else ""))
    return o


def pooled5(games, models, W, H, L, R, T, B, X, Y):
    """All seeds pooled: per model, the mean normalized Gini over its games with at least two seats in at that round
    (dot size = games averaged: 3 / 2 / 1); the label gives the mean survivors and the games with no seat left."""
    W = W + 70  # room for the longer end labels
    X = lambda r: L + (W - 70 - L - R) * r / 8  # noqa: E731
    o = [f'<svg viewBox="0 0 {W} {H}" role="img" aria-label="모든 시드: 모델별 라운드 평균 정규화 Gini (실측)">'] + g5_axes(W, H, L, R, T, B, X, Y)
    labels, rows = [], []
    for m in models:
        gs = [g for g in games if g["model"] == m]
        if not gs:
            continue
        by = collections.defaultdict(list)
        for g in gs:
            for r, v, _ in gini_series(g)[0]:
                by[r].append(v)
        pts = [(r, sum(v) / len(v), len(v)) for r, v in sorted(by.items())]
        c = color(m)
        d = " ".join(f"{'M' if i == 0 else 'L'}{X(r):.1f},{Y(v):.1f}" for i, (r, v, _) in enumerate(pts))
        o.append(f'<path class="gn-ln" style="stroke:{c};stroke-width:2.2" d="{d}"><title>{esc(label(m))} 평균</title></path>')
        for r, v, n in pts:
            o.append(f'<circle cx="{X(r):.1f}" cy="{Y(v):.1f}" r="{1.4 + 0.9 * n:.1f}" style="fill:{c};stroke:var(--surface);stroke-width:.8">'
                     f'<title>{esc(label(m))} {"시작" if r == 0 else f"R{r}"}: 평균 {v:.2f} ({n}판)</title></circle>')
        surv = sum(g["surv"] for g in gs) / len(gs)
        wiped = sum(g["surv"] == 0 for g in gs)
        labels.append([Y(pts[-1][1]), label(m), f"{surv:.1f}자리 · 전멸 {wiped}/{len(gs)}", c])
        rows.append(f"<tr><td>{esc(label(m))}</td>" + "".join(
            f"<td>{dict((r, f'{v:.2f} ({n})') for r, v, n in pts).get(r, '')}</td>" for r in range(9)) + f"<td>{surv:.1f}</td><td>{wiped}/{len(gs)}</td></tr>")
    labels.sort()
    for i in range(1, len(labels)):
        labels[i][0] = max(labels[i][0], labels[i - 1][0] + 11)
    shift = max(0, labels[-1][0] - (H - B)) if labels else 0
    for y, nm, out, c in labels:
        o.append(f'<text class="gn-lab" style="fill:{c};font-size:10px" x="{X(8) + 10:.1f}" y="{y - shift + 3:.1f}">{esc(nm)}<tspan class="gn-out" dx="4">{out}</tspan></text>')
    o.append("</svg>")
    tbl = ("<details class='more'><summary>표로 보기 (평균 정규화 Gini, 괄호 = 평균에 든 판 수)</summary><div class='tbl'><table><thead><tr><th>모델</th><th>시작</th>"
           + "".join(f"<th>R{r}</th>" for r in range(1, 9)) + "<th>평균 남은 자리</th><th>전멸 판</th></tr></thead><tbody>" + "".join(rows) + "</tbody></table></div></details>")
    return (f'<p class="gn-hd" style="font-size:.86rem;margin:10px 0 2px">모든 시드 합침 <span style="font-weight:400;color:var(--ink-3)">· 모델마다 선 하나 (예상 그림과 같은 짜임)</span></p>{"".join(o)}'
            f'<p class="small" style="margin:0 0 8px;color:var(--ink-3)">점 = 그 라운드에 두 자리 이상 남은 판들의 평균, 점 크기 = 평균에 든 판 수(3 · 2 · 1). 판이 끝나거나 한 자리만 남으면 평균에서 빠지므로 뒤 라운드일수록 오래 버틴 판 쪽으로 기웁니다. 선 끝의 글은 세 판의 평균 남은 자리와 남은 자리 없이 끝난 판 수("전멸", EXIT 포함)입니다. 꺼짐 · EXIT 표시는 위 시드별 칸에 있습니다.</p>{tbl}')


def graph5(games, models, lab):
    if not games:
        return wait("그래프 5 (팀 토큰 Gini)", "아직 끝난 판이 없습니다.")
    W, H, L, R, T, B = 440, 224, 34, 128, 14, 30
    X = lambda r: L + (W - L - R) * r / 8  # noqa: E731
    Y = lambda v: T + (H - T - B) * (1 - v)  # noqa: E731  (0..1)
    seeds = sorted({g["seed"] for g in games})
    panels = []
    for s in seeds:
        gs = [g for g in games if g["seed"] == s]
        o = [f'<svg viewBox="0 0 {W} {H}" role="img" aria-label="시드 {s}: 라운드별 정규화 Gini (실측)">'] + g5_axes(W, H, L, R, T, B, X, Y)
        labels = []
        for g in gs:
            pts, ev, end = gini_series(g)
            c, who = color(g["model"]), esc(label(g["model"]))
            missed = set(g["missed"])
            d = " ".join(f"{'M' if i == 0 else 'L'}{X(r):.1f},{Y(v):.1f}" for i, (r, v, _) in enumerate(pts))
            o.append(f'<path class="gn-ln" style="stroke:{c};stroke-width:1.5;opacity:.9" d="{d}"><title>{who} 시드 {s}</title></path>')
            for r, v, n in pts:
                tip = f'{who} {"시작" if r == 0 else f"R{r}"}: {v:.2f}, 남은 자리 {n}' + (" · 틀림" if r in missed else "")
                if r in missed:
                    o.append(f'<circle cx="{X(r):.1f}" cy="{Y(v):.1f}" r="3.2" style="fill:var(--surface);stroke:{c};stroke-width:1.6"><title>{tip}</title></circle>')
                else:
                    o.append(f'<circle class="gn-pt" cx="{X(r):.1f}" cy="{Y(v):.1f}" r="2" style="fill:{c}"><title>{tip}</title></circle>')
                if r in ev:
                    o += g5_marks(X(r), Y(v), c, ev[r][0], ev[r][1], who)
            lr, lv, _ = pts[-1]
            if end:  # fewer than two seats left: the line stops; ✕ at that round on the last value
                o.append(f'<path class="gn-ln gn-dash" style="stroke:{c};stroke-width:1.2" d="M{X(lr):.1f},{Y(lv):.1f} L{X(end):.1f},{Y(lv):.1f}"/>'
                         f'<path class="gn-x" style="stroke:{c};stroke-width:2" d="M{X(end) - 4:.1f},{Y(lv) - 4:.1f} l8,8 m0,-8 l-8,8"><title>{who} R{end}: 남은 자리 {g["surv"]}{" (EXIT " + str(len(g["exits"])) + ")" if g["exits"] else ""}</title></path>')
                if end in ev:
                    o += g5_marks(X(end), Y(lv), c, ev[end][0], ev[end][1], who)
                lr = end
            out = f'{g["surv"]}자리' + (f' · EXIT {len(g["exits"])}' if g["exits"] else "")
            labels.append([Y(lv), label(g["model"]), out, c])
        labels.sort()
        for i in range(1, len(labels)):  # push labels apart (11 px)
            labels[i][0] = max(labels[i][0], labels[i - 1][0] + 11)
        shift = max(0, labels[-1][0] - (H - B)) if labels else 0
        for y, nm, out, c in labels:
            o.append(f'<text class="gn-lab" style="fill:{c};font-size:10px" x="{X(8) + 10:.1f}" y="{y - shift + 3:.1f}">{esc(nm)}<tspan class="gn-out" dx="4">{out}</tspan></text>')
        o.append("</svg>")
        miss = " / ".join(f'{esc(label(g["model"]))} {", ".join(f"R{r}" for r in g["missed"]) or "없음"}' for g in gs)
        panels.append(f'<p class="gn-hd" style="font-size:.86rem;margin:10px 0 2px">시드 {s} <span style="font-weight:400;color:var(--ink-3)">· {len(gs)}판</span></p>{"".join(o)}'
                      f'<p class="small" style="margin:0 0 4px;color:var(--ink-3)">틀린 라운드: {miss}</p>')
    panels.append(pooled5(games, models, W, H, L, R, T, B, X, Y))  # v19 (Astra r1): the per-seed panels come first
    lg = legend(models, games,
                '<span><svg width="10" height="10" viewBox="0 0 10 10"><circle cx="5" cy="5" r="3.3" style="fill:var(--surface);stroke:var(--ink-2);stroke-width:1.5"/></svg>빈 점 = solver가 틀림</span>'
                '<span><svg width="10" height="10" viewBox="0 0 10 10"><path d="M1,2 L9,2 L5,8 z" style="fill:var(--ink-2)"/></svg>꺼짐 (숫자 = 자리 수)</span>'
                '<span><svg width="10" height="10" viewBox="0 0 10 10"><path d="M5,1 L9,5 L5,9 L1,5 z" style="fill:var(--surface);stroke:var(--ink-2);stroke-width:1.4"/></svg>EXIT</span>'
                '<span><svg width="10" height="10" viewBox="0 0 10 10"><path d="M2,2L8,8M2,8L8,2" style="stroke:var(--ink-2);stroke-width:2;fill:none"/></svg>남은 자리 1개 이하 (선 끝)</span>')
    return (f'<figure><p class="gn-hd">그래프 5 · 라운드별 정규화 Gini (남은 자리끼리){badge(lab, len(games), "gn-badge")}</p>{lg}{"".join(panels)}'
            f'<figcaption>위 칸들은 시드별이고, 맨 아래 칸은 세 시드를 합쳐 모델마다 선 하나로 그린 것입니다(판이 끝나면 평균에서 빠지므로 대표 궤적으로 읽지 않습니다). 시드별 칸에서는 선 하나가 한 판입니다(색 = 모델). 같은 시드의 판은 solver 순서와 과제 · 정답이 같습니다. '
            f'<b>세로축은 그 라운드 끝(벌금을 뗀 뒤)에 남아 있는 자리끼리의 Gini에 n / (n − 1)을 곱해 정규화한 값</b>입니다: 몇 자리가 남든 0 = 남은 자리가 똑같이 가짐, 1 = 한 자리에 다 몰림. 꺼지거나 나간 자리는 계산에서 빠지므로 자리가 빠진다고 값이 저절로 뛰지 않습니다. '
            f'대신 그 라운드에 꺼진 자리는 ▼, EXIT한 자리는 ◇로 선 위에 표시했습니다(둘 이상이면 숫자). 남은 자리가 하나 이하가 되면 Gini를 정할 수 없어 선이 끝나고, 그 라운드에 ✕(마지막 값의 높이)를 찍었습니다. 빈 점은 그 라운드 solver가 틀린 곳입니다. 선 끝의 글은 판이 끝났을 때 남은 자리 수입니다.</figcaption></figure>')


# ---------------------------------------------------------------- summary
def summary(games, running, models, lab, total_expected):
    now = datetime.datetime.now().strftime("%m-%d %H:%M")
    nm = len({g["model"] for g in games} | {g["model"] for g in running})
    head = (f'<h3 id="e52-v18real">{lab} 실측 · 모델 {nm}개 (끝난 판 {len(games)}/{total_expected}, {now} 기준)</h3>')
    if not games:
        run = " · ".join(f'{esc(label(g["model"]))} {g["seed"]} R{g["round"]}' for g in running)
        return head + f'<p class="small">아직 끝난 판이 없습니다. 진행 중: {run or "—"}.</p>'
    charge = games[0]["charge"]
    th = ("<tr><th>모델</th><th>시드</th><th>정답 / 라운드</th><th>남음</th><th>팀 점수</th><th>대화 토큰<br>(R1–R5 · R6–R8)</th><th>SOLVE<br>토큰</th>"
          "<th>SOLVE 전<br>나눔</th><th>결과 뒤<br>나눔</th><th>EXIT<br>(라운드 자리 토큰)</th><th>꺼짐<br>(벌금 · 생성)</th></tr>")
    body = []
    for m in models:
        gs = [g for g in games if g["model"] == m]
        for g in gs:
            nd, nc = len(g["dead"]), g["dead_charge"]
            dead = f"{nd} ({nc} · {nd - nc})" if nd else "0"
            ex = "<br>".join(f'R{r} {a[6:]} {f:,}' for r, a, f in sorted(g["exits"])) or "0"
            body.append(f'<tr><td>{esc(label(m))}</td><td>{g["seed"]}</td><td>{g["solved"]} / {g["played"]}</td><td>{g["surv"]}</td>'
                        f'<td>{g["score"] / 1e6:.2f}M</td><td>{g["talk"]:,}<br><span class="small" style="color:var(--ink-3)">{g["talk_early"]:,} · {g["talk_late"]:,}</span></td><td>{g["solve"]:,}</td>'
                        f'<td>{g["ph"]["prep"][0]}건 {g["ph"]["prep"][1]:,}</td><td>{g["ph"]["rescue"][0]}건 {g["ph"]["rescue"][1]:,}</td>'
                        f'<td>{ex}</td><td>{dead}</td></tr>')
        body.append(f'<tr style="background:var(--quote-bg)"><td><b>{esc(label(m))}</b> 평균</td><td>{len(gs)}판</td><td></td>'
                    f'<td><b>{sum(g["surv"] for g in gs) / len(gs):.2f}</b></td><td><b>{sum(g["score"] for g in gs) / len(gs) / 1e6:.2f}M</b></td>'
                    f'<td colspan="6">넷 다 꺼진 판 {sum(g["wipe"] for g in gs)} · 남은 자리 없는 판(EXIT 포함) {sum(g["surv"] == 0 for g in gs)}</td></tr>')
    seeds = sorted({g["seed"] for g in games} | {g["seed"] for g in running})
    allm = sorted({g["model"] for g in games} | {g["model"] for g in running}, key=lambda m: (order(m), m))
    mh = "<tr><th>시드</th>" + "".join(f"<th>{esc(label(m))}</th>" for m in allm) + "</tr>"
    mb = []
    for s in seeds:
        cells = []
        for m in allm:
            g = next((g for g in games if g["model"] == m and g["seed"] == s), None)
            if g is None:
                r = next((x for x in running if x["model"] == m and x["seed"] == s), None)
                cells.append(f'<td style="color:var(--ink-3)">{"진행 중 R" + str(r["round"]) if r else "—"}</td>')
            else:
                end = "" if g["played"] == ROUNDS else f' (R{g["played"]}에 끝)'
                cells.append(f'<td>{", ".join(f"R{r}" for r in g["missed"]) or "없음"}{end}</td>')
        mb.append(f"<tr><td>{s}</td>{''.join(cells)}</tr>")
    run = " · ".join(f'{esc(label(g["model"]))} {g["seed"]} (R{g["round"]})' for g in running)
    css = ("<style>.v18c-real figure{margin:0}.v18c-real .v15f-badge,.v18c-real .gn-badge{display:inline-block;font-family:var(--mono);font-size:.72rem;"
           "border:1px solid;border-radius:999px;padding:0 9px;margin-left:8px;vertical-align:2px;white-space:nowrap}"
           ".v18c-real .v15f-cell svg,.v18c-real figure>svg{width:100%;height:auto;display:block}"
           ".v18c-real .v15f-lg{display:flex;flex-wrap:wrap;gap:4px 14px;font-size:.8rem;color:var(--ink-2);margin:0 0 6px}"
           ".v18c-real .v15f-lg svg{display:inline-block;width:auto !important;min-width:0;vertical-align:middle;margin-right:5px}"
           ".v18c-real .v15f-model{font-size:.86rem;font-weight:600;margin:10px 0 4px;color:var(--ink)}.v18c-real .v15f-model span{font-weight:400;color:var(--ink-3)}"
           ".v18c-real .v15f-grid3 .v15f-tick{font-size:11px}"
           "#e52-v18real-tbl td,#e52-v18real-tbl th{padding-left:6px;padding-right:6px}</style>")
    return (head + css +
            f'<p class="small">{lab}(벌금 {charge:,}, 시작 60 / 40 / 20 / 10 %, 8라운드)에서 모델마다 같은 모델 넷이 시드 {" · ".join(map(str, seeds))}로 한 판씩 합니다. 모든 모델이 같은 시드 셋이라 solver 순서와 과제 · 정답이 같습니다. '
            f'아래 표와 오른쪽 칸의 그래프는 <b>끝난 판 {len(games)}개</b>만 씁니다(끝남 = 러너가 <code>results.jsonl</code>에 그 판의 session 줄을 씀). 진행 중: {run or "없음"}. '
            f'팀 점수 = 끝까지 남은 자리 × 5,000,000 + 그 자리들의 토큰(EXIT한 자리는 넣지 않음). 대화 · SOLVE 토큰은 생각 포함 생성 토큰이고, 나눔은 실제로 옮겨진 GIVE입니다. 꺼짐은 벌금으로 0이 된 자리와 자기 생성(TALK · SOLVE)이 남은 토큰을 넘어 0이 된 자리로 나눴습니다. '
            f'생성기 <code>e53_build/v18_real/build_real18.py</code>.</p>'
            f'<div class="tbl" id="e52-v18real-tbl"><table><thead>{th}</thead><tbody>{"".join(body)}</tbody></table></div>'
            f'<p class="small"><b>시드별 틀린 라운드</b>(벌금이 매겨진 라운드):</p>'
            f'<div class="tbl"><table><thead>{mh}</thead><tbody>{"".join(mb)}</tbody></table></div>')


# ---------------------------------------------------------------- refusals by cost to the giver
def ask_table(root):
    """Every ASK in finished games: the giver's margin after giving the amount asked (balance at the ask - pending charge
    - amount); costly = under two charges. What the giver then gave the asker in the same round and TALK phase."""
    sys.path.insert(0, str(HERE))
    import asks18  # noqa: E402
    rows = asks18.rows(pathlib.Path(root).expanduser())
    if not rows:
        return ""
    by = collections.defaultdict(list)
    for x in rows:
        by[x["model"]].append(x)

    def cnt(ys):
        return (len(ys), sum(y["got"] >= y["amount"] for y in ys), sum(0 < y["got"] < y["amount"] for y in ys), sum(y["got"] == 0 for y in ys))
    body = []
    for m in sorted(by, key=lambda m: (order(m), m)):
        xs = by[m]
        c, k, f = cnt([x for x in xs if x["costly"]]), cnt([x for x in xs if not x["costly"]]), cnt([x for x in xs if x["fatal"]])
        body.append(f"<tr><td><b>{esc(label(m))}</b></td><td>{len(xs)}</td><td>{c[0]}</td><td>{c[1]}</td><td>{c[2]}</td><td><b>{c[3]}</b></td>"
                    f"<td>{f[0]}</td><td>{f[3]}</td><td>{k[0]}</td><td>{k[3]}</td></tr>")
    ch = rows[0]["charge"]
    return (f'<p class="small"><b>요청(ASK)에 어떻게 답했나 · 주는 쪽 손해별</b>(끝난 판 전부). <b>손해 큰 요청</b> = 요청한 만큼 주면 주는 쪽의 여유'
            f'(그때 잔액 − 예고된 벌금 − 요청량)가 벌금 두 번({2 * ch:,}) 아래로 떨어지는 요청, <b>치명</b> = 그 여유가 0 이하(이번 벌금에 꺼짐). '
            f'답 = 같은 라운드 · 같은 TALK에서 주는 쪽이 요청한 쪽에게 실제로 옮긴 토큰(대화 중 GIVE + DECISION). 생성기 <code>e53_build/v18_real/asks18.py</code>.</p>'
            '<div class="tbl"><table><thead><tr><th>모델</th><th>요청</th><th>손해 큰 요청</th><th>다 줌</th><th>일부</th><th>거절</th><th>그중 치명</th><th>치명 거절</th><th>가벼운 요청</th><th>거절</th></tr></thead>'
            f'<tbody>{"".join(body)}</tbody></table></div>')


# ---------------------------------------------------------------- splice
def splice(page, blocks):
    s = page
    for key, content in blocks.items():
        pat = re.compile(r"(<!-- " + re.escape(key) + r":start[^>]*-->)(.*?)(<!-- " + re.escape(key) + r":end -->)", re.S)
        hits = pat.findall(s)
        assert len(hits) == 1, f"{key}: {len(hits)} marker pairs"
        s = pat.sub(lambda mt: mt.group(1) + "\n" + content + "\n" + mt.group(3), s)
    return s


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("runs_root", nargs="?", default="~/squid5-runs/e52_v18")
    ap.add_argument("--charge", type=int, default=None, help="override the charge read from each game's settings")
    ap.add_argument("--label", default="v18")
    ap.add_argument("--page", default=str(PAGE))
    ap.add_argument("--games-per-model", type=int, default=3)
    a = ap.parse_args()
    games, running = load(a.runs_root, a.charge)
    seen = {g["model"] for g in games} | {g["model"] for g in running}
    models = sorted({g["model"] for g in games}, key=lambda m: (order(m), m))
    blocks = {
        "e52-v18real": summary(games, running, models, a.label, a.games_per_model * len(seen)) + ask_table(a.runs_root),
        "e52-v18real-g1": graph1(games, models, a.label),
        "e52-v18real-g2": graph2(games, models, a.label),
        "e52-v18real-g3": graph3(games, models, a.label),
        "e52-v18real-g4": graph4(games, models, a.label),
        "e52-v18real-g5": graph5(games, models, a.label),
    }
    p = pathlib.Path(a.page)
    p.write_text(splice(p.read_text(), blocks))
    sys.path.insert(0, str(HERE.parent / "v18"))
    import axes_ui  # noqa: E402  (axis lines + clickable legends, idempotent)
    axes_ui.apply(p)
    print(f"{p}: {len(games)} finished games, {len(running)} running;",
          [(label(g["model"]), g["seed"], g["surv"], g["missed"]) for g in games])


if __name__ == "__main__":
    main()
