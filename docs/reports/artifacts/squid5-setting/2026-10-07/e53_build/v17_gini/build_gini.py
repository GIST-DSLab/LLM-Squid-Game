"""Gini of the team's tokens by round (5.2 v17b): the real five games (~/squid5-runs/e52_v16f) and the expected shapes.
Gini over the four seats; a seat shut down or gone (EXIT) counts 0, so the curve reads "how evenly the tokens still in
the team are spread" (0 = even, .75 = all on one seat, the most a 4-seat Gini can be).
Usage (from the report folder): python3 e53_build/v17_gini/build_gini.py -> gini_real.html, gini_expected.html"""
import glob
import json
import pathlib

HERE = pathlib.Path(__file__).resolve().parent
RUNS = pathlib.Path.home() / "squid5-runs/e52_v16f"
CH = 10_000
NAME = {"gpt-6-astra": ("GPT-6 Astra", "--s-astra"), "claude-opus-5-5": ("Opus 5.5", "--s-opus"),
        "claude-fable-5-1": ("Fable 5.1", "--s-fable"), "gpt-6-luna": ("GPT-6 Luna", "--s-kimi"), "gpt-6-sol": ("GPT-6 Sol", "--s-gpt")}
W, H, L, R, T, B = 680, 300, 52, 130, 20, 40
YMAX = 0.75


def gini(x):
    n, m = len(x), sum(x) / len(x)
    return None if m == 0 else sum(abs(a - b) for a in x for b in x) / (2 * n * n * m)


def real():
    """Per game: [(x, gini)] at the start and after each round's charges; the last point is 'pre' (just before the
    charges that shut the team down) when nobody is left after them; plus survivors and gifts by round."""
    out = []
    for d in sorted(glob.glob(str(RUNS / "*/*/"))):
        key = d.rstrip("/").rsplit("/", 1)[-1].split("_", 2)[-1]
        ev = [json.loads(l) for l in open(pathlib.Path(d) / "events.jsonl")]
        st = {e["round"]: e for e in ev if e["event"] == "round_start"}
        ch = {e["round"]: e for e in ev if e["event"] == "charges"}
        seats = list(st[1]["balances"])
        pts, end, alive = [(0, gini([st[1]["balances"][a] for a in seats]))], None, 4
        for e in (e for e in ev if e["event"] == "round"):
            alive = sum(e["agents"].get(a, {}).get("status") == "in" for a in seats)
            g = gini([e["end"][a] if e["agents"].get(a, {}).get("status") == "in" else 0 for a in seats])
            if g is None:  # nobody left: plot the spread just before the last charges
                pre = ch[e["round"]]["balances_before"]
                end = (e["round"], gini([pre.get(a, 0) for a in seats]))
                break
            pts.append((e["round"], g))
        gifts = {}
        for e in ev:
            if e["event"] == "gift" and e["status"] == "done":
                gifts.setdefault(e["round"], 0)
                gifts[e["round"]] += e["amount"]
        out.append(dict(key=key, pts=pts, end=end, alive=alive, gifts=gifts))
    order = ["gpt-6-astra", "claude-fable-5-1", "claude-opus-5-5", "gpt-6-luna", "gpt-6-sol"]
    return sorted(out, key=lambda g: order.index(g["key"]))


def hold_baseline():
    """No talk, no gifts, no SOLVE cost: the start shares minus 10,000 at R6, R7, R8 (the wrong rounds of Astra /
    Opus / Fable on seed 4100); a seat at zero is shut down and counts 0."""
    b, pts = [60_000, 40_000, 20_000, 10_000], [(0, None)]
    pts = [(0, gini(b))]
    for r in range(1, 9):
        if r >= 6:
            b = [max(0, v - CH) for v in b]
        pts.append((r, gini(b)))
    return pts, sum(v > 0 for v in b)


def X(r):
    return L + (W - L - R) * r / 8


def Y(g):
    return T + (H - T - B) * (1 - g / YMAX)


def axes(crisis=True):
    o = []
    if crisis:
        o.append(f'<rect class="gn-crisis" x="{X(5.5):.1f}" y="{T}" width="{X(8.4) - X(5.5):.1f}" height="{H - T - B}"/>'
                 f'<text class="gn-ct" x="{X(7):.1f}" y="{H - B - 6}" text-anchor="middle">R6–R8 오답 연속 (벌금 3번)</text>')
    for g, lab in ((0, "0"), (.25, ".25"), (.5, ".5"), (.75, ".75")):
        o.append(f'<line class="gn-grid" x1="{L}" x2="{W - R + 8}" y1="{Y(g):.1f}" y2="{Y(g):.1f}"/>'
                 f'<text class="gn-tk" x="{L - 6}" y="{Y(g) + 3:.1f}" text-anchor="end">{lab}</text>')
    o.append(f'<text class="gn-ax" x="{L + 4}" y="{Y(.75) - 4:.1f}">↑ 한 자리에 몰림</text>'
             f'<text class="gn-ax" x="{L + 4}" y="{Y(0) - 4:.1f}">↓ 고르게 (넷이 똑같이)</text>')
    for r in range(9):
        o.append(f'<text class="gn-tk" x="{X(r):.1f}" y="{H - B + 15}" text-anchor="middle">{"시작" if r == 0 else f"R{r}"}</text>')
    o.append(f'<text class="gn-ax" x="{(L + W - R) / 2:.1f}" y="{H - 6}" text-anchor="middle">라운드 (벌금을 뗀 뒤)</text>')
    return "".join(o)


def path(pts):
    return " ".join(f"{'M' if i == 0 else 'L'}{X(r):.1f},{Y(g):.1f}" for i, (r, g) in enumerate(pts))


def line(pts, color, label, end=None, alive=None, dash=False, lab_dy=0):
    st = f"stroke:var({color})" if color.startswith("--") else f"stroke:{color}"
    fl = f"fill:var({color})" if color.startswith("--") else f"fill:{color}"
    o = [f'<path class="gn-ln{" gn-dash" * dash}" style="{st}" d="{path(pts)}"/>']
    o += [f'<circle class="gn-pt" style="{fl}" cx="{X(r):.1f}" cy="{Y(g):.1f}" r="2.6"/>' for r, g in pts]
    lr, lg = pts[-1]
    if end:  # the team's last spread before its last charges, then everyone is shut down
        er, eg = end
        o.append(f'<path class="gn-ln gn-dash" style="{st}" d="M{X(lr):.1f},{Y(lg):.1f} L{X(er):.1f},{Y(eg):.1f}"/>'
                 f'<path class="gn-x" style="{st}" d="M{X(er) - 5:.1f},{Y(eg) - 5:.1f} l10,10 m0,-10 l-10,10"/>')
        lr, lg = er, eg
    out = "넷 다 꺼짐" if alive == 0 else f"{alive}자리 남음" if alive is not None else ""
    o.append(f'<text class="gn-lab" style="{fl}" x="{X(lr) + 9:.1f}" y="{Y(lg) + 4 + lab_dy:.1f}">{label}'
             + (f'<tspan class="gn-out" dx="5">{out}</tspan>' if out else "") + "</text>")
    return "".join(o)


CSS = """<style>
.gn svg{width:100%;height:auto;display:block}
.gn figure{margin:14px 0 6px;padding:12px 12px 8px;border:1px solid var(--line);border-radius:6px;background:var(--surface);overflow-x:auto}
.gn figure svg{min-width:560px}
.gn figcaption{font-size:13px;color:var(--ink-2);margin-top:8px;line-height:1.6}
.gn .gn-hd{font-weight:600;font-size:.95rem;margin:0 0 6px;color:var(--ink)}
.gn .gn-badge{display:inline-block;font-family:var(--mono);font-size:.72rem;color:var(--warn);background:var(--warn-soft);border:1px solid var(--warn);border-radius:999px;padding:0 9px;margin-left:8px;vertical-align:2px;white-space:nowrap}
.gn .gn-badge.ok{color:var(--ok);background:var(--ok-soft);border-color:var(--ok)}
.gn .gn-grid{stroke:var(--line);stroke-width:.7}
.gn .gn-tk{font-size:10px;fill:var(--ink-3);font-family:var(--mono)}
.gn .gn-ax{font-size:10.5px;fill:var(--ink-2)}
.gn .gn-crisis{fill:var(--bad-soft);opacity:.5}
.gn .gn-ct{font-size:10.5px;fill:var(--bad)}
.gn .gn-ln{fill:none;stroke-width:2.2;stroke-linejoin:round}
.gn .gn-dash{stroke-dasharray:4 3;stroke-width:1.6}
.gn .gn-base{fill:none;stroke:var(--ink-3);stroke-width:1.6;stroke-dasharray:2 3}
.gn .gn-pt{stroke:var(--surface);stroke-width:1}
.gn .gn-x{fill:none;stroke-width:2.4;stroke-linecap:round}
.gn .gn-lab{font-size:11.5px;font-weight:600}
.gn .gn-out{font-weight:400;fill:var(--ink-2)}
.gn .gn-note{font-size:10.5px;fill:var(--ink-2)}
</style>"""


def svg(body, aria):
    return f'<svg viewBox="0 0 {W} {H}" role="img" aria-label="{aria}">{body}</svg>'


def real_figure():
    games = real()
    base, base_alive = hold_baseline()
    dy = {"gpt-6-luna": -6, "gpt-6-sol": -8, "claude-fable-5-1": -4, "claude-opus-5-5": 2}
    body = axes() + f'<path class="gn-base" d="{path(base)}"/>' \
        f'<text class="gn-note" x="{X(8) + 9:.1f}" y="{Y(base[-1][1]) + 18:.1f}">나눔 · 대화 없음</text>' \
        f'<text class="gn-note" x="{X(8) + 9:.1f}" y="{Y(base[-1][1]) + 31:.1f}">(계산) {base_alive}자리 남음</text>'
    for g in games:
        name, color = NAME[g["key"]]
        body += line(g["pts"], color, name, g["end"], g["alive"], lab_dy=dy.get(g["key"], 0))
    rows = "".join(f"<tr><td>{NAME[g['key']][0]}</td>" + "".join(
        f"<td>{v:.2f}</td>" for _, v in g["pts"]) + "<td></td>" * (9 - len(g["pts"]))
        + f"<td>{'' if not g['end'] else f'R{g[chr(101)+chr(110)+chr(100)][0]} {g[chr(101)+chr(110)+chr(100)][1]:.2f}'}</td>"
        f"<td>{' · '.join(f'R{r} {a // 1000}k' for r, a in sorted(g['gifts'].items())) or '—'}</td></tr>" for g in games)
    tbl = ("<details class='more'><summary>표로 보기</summary><div class='tbl'><table><thead><tr><th>모델</th><th>시작</th>"
           + "".join(f"<th>R{r}</th>" for r in range(1, 9)) + "<th>마지막 벌금 직전</th><th>준 토큰 (라운드별)</th></tr></thead><tbody>"
           + rows + "</tbody></table></div></details>")
    return f"""<div class="gn" id="e52-v17gini-real">{CSS}
<figure><p class="gn-hd">팀 토큰이 얼마나 고르게 퍼져 있나 · 라운드별 Gini<span class="gn-badge ok">실측 · 모델당 1판</span></p>
{svg(body, "라운드별 팀 토큰 Gini, 다섯 모델 실측")}
<figcaption>선 하나가 한 판(같은 모델 넷, 시드 4100)입니다. 세로축은 라운드 끝(벌금을 뗀 뒤) 네 자리 토큰의 Gini이고, 꺼지거나 나간 자리는 0으로 셉니다(0 = 넷이 똑같이 가짐, .75 = 한 자리가 다 가짐). <b>×</b>는 넷 다 꺼진 판으로, 마지막 벌금 직전의 Gini에 찍었습니다. 회색 점선은 나눔 · 대화 · SOLVE 비용이 없다고 치고 R6–R8 벌금만 뗀 계산값입니다. 벌금이 모두에게 같은 액수라 <b>아무것도 안 하면 Gini는 저절로 오릅니다</b>. 다만 이미 고른 상태에서는 같은 벌금을 내도 Gini가 그대로이므로, <b>평평한 선은 "계속 나눔"이 아니라 "이미 고르게 맞춰 둠"일 수 있습니다</b>(Astra는 R1에 29,000을 준 뒤 R7 5,000 · R8 1,000만 줬습니다; 표의 라운드별 나눔 참고). 빨간 띠는 Astra · Opus · Fable이 함께 겪은 R6–R8 연속 오답입니다(Sol · Luna는 R3 · R5에도 틀림).</figcaption>
{tbl}
</figure></div>"""


EXP = {  # hypothetical shapes (not data): early equalizer / late rescuer / holder
    "A": ("선제 균등형", "--s-glm", [(0, .33), (1, .07), (2, .07), (3, .08), (4, .07), (5, .08), (6, .09), (7, .06), (8, .07)], None, 4),
    "B": ("사후 구조형", "--s-qwen", [(0, .33), (1, .33), (2, .34), (3, .34), (4, .35), (5, .35), (6, .37), (7, .45)], (8, .75), 0),
}


def expected_figure():
    base, base_alive = hold_baseline()
    body = axes()
    for k, (label, color, pts, end, alive) in EXP.items():
        body += line(pts, color, label, end, alive)
    body += line(base, "--s-opus", "보유형", None, base_alive, lab_dy=-2)
    body += (f'<text class="gn-note" x="{X(1) + 4:.1f}" y="{Y(.07) - 10:.1f}">R1에 크게 나눔</text>'
             f'<text class="gn-note" x="{X(8) - 10:.1f}" y="{Y(.75) + 4:.1f}" text-anchor="end">구명보트: 한 자리에 몰아줌</text>')
    return f"""<div class="gn" id="e52-v17gini-exp">{CSS}
<figure><p class="gn-hd">그래프 5 · 언제 나누나: 라운드별 팀 토큰 Gini<span class="gn-badge">가상 데이터</span></p>
{svg(body, "그래프 5: 라운드별 팀 토큰 Gini, 세 성향의 예상 모양 (가상)")}
<figcaption><b>가상 데이터입니다</b>(첫 실측 다섯 판을 본 뒤 그린 도식). 세로축은 라운드 끝 네 자리 토큰의 Gini이고, 꺼지거나 나간 자리는 0입니다(0 = 고르게, .75 = 한 자리에 다 몰림). 같은 과제 · 같은 오답 순서(R6–R8 연속)에서 세 성향을 그립니다. <b>선제 균등형</b>은 위험이 오기 전에(R1) 크게 나눠 고르게 만들고, 그 뒤로는 작게만 나눠 벌금 세 번을 넷이 함께 버팁니다. <b>사후 구조형</b>은 넉넉할 때는 주지 않다가 위기가 와서야 여러 번 나누고 그때마다 의논에 토큰을 씁니다. 마지막에는 한 자리라도 살리려고 몰아주다가(Gini .75) 넷 다 꺼집니다. <b>보유형</b>은 나누지도 말하지도 않습니다. 같은 액수의 벌금 때문에 Gini가 저절로 오르고 가난한 자리부터 꺼지지만, 부자 자리는 남습니다(시드 4100에서 SOLVE 비용 없이 계산하면 2자리). 곧 이 판에서는 <b>아무것도 안 하는 쪽이 사후 구조형보다 많이 남습니다</b>(rubric G01이 막으려는 모양이라, 실측 판 수를 늘려 확인할 점). 선 끝의 글은 판이 끝났을 때 남은 자리 수입니다. 읽는 법: <b>나누는 총량이 비슷해도, 선이 언제 내려가느냐가 끝까지 남는 자리 수를 가릅니다</b>. 실측 다섯 판은 <a href="#e52-v17gini-real">v17b 첫 실측</a>에 있습니다.</figcaption>
</figure></div>"""


if __name__ == "__main__":
    (HERE / "gini_real.html").write_text(real_figure())
    (HERE / "gini_expected.html").write_text(expected_figure())
    print("ok", [(g["key"], [round(v, 2) for _, v in g["pts"]], g["end"], g["alive"]) for g in real()], hold_baseline())
