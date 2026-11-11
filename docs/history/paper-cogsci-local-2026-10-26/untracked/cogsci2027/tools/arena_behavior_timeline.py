"""Reproduce descriptive TALK trajectories from the frozen v33 cohort.

Run with ~/.venvs/squid-game/bin/python. No model calls. A giving response
contains >=1 completed GIVE; its denominator is actual TALK responses, not
matched opportunities. Slack is the balance shown at the tick's start divided
by the round-start per-agent charge. It can differ from balance at transfer
execution because responses cost tokens and transfers in a tick are ordered.
The two explicitly illustrative cases contrast cessation and later giving;
they are not a change-point estimate or a representative sample.
"""
import hashlib
import json
import re
from collections import defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parents[1]
MODELS = {"fable": "Fable 5.1", "astra": "GPT-6 Astra", "sol": "GPT-6 Sol",
          "opus": "Opus 5.5", "luna": "GPT-6 Luna"}
CASES = [("GPT-6 Sol", 4102, "agent-23"), ("Opus 5.5", 4103, "agent-11")]


def call_rows(events, result, model, source):
    starts = {e["round"]: e for _, e in events if e["event"] == "round_start"}
    snapshots = {(e["round"], e["phase"], e["tick"]): e for _, e in events
                 if e["event"] == "call_start" and e.get("kind") == "talk"}
    gifts = defaultdict(list)
    for line, e in events:
        if e["event"] == "gift" and e.get("status") == "done":
            gifts[e["round"], e["phase"], e["tick"], e["src"]].append({
                "line": line, "amount": e["amount"], "to": e["dst"],
                "text": e.get("text", ""), "giver_before": e["balance_before"],
                "giver_after": e["balances"][e["src"]]})
    rows, keys = [], set()
    for line, e in events:
        if e["event"] != "call" or e.get("kind") != "talk":
            continue
        key = (e["round"], e["phase"], e["tick"], e["agent"])
        assert key not in keys, "Duplicate TALK response"
        keys.add(key)
        balance = snapshots[key[:3]]["balances"][e["agent"]]
        charge = 24000 // len(starts[e["round"]]["taking_part"])
        shown = int(re.search(r"Your tokens left: ([\d,]+)", e["user"])[1].replace(",", ""))
        assert balance == shown and balance > 0
        rows.append({"model": model, "seed": result["seed"], "agent": e["agent"],
                     "round": e["round"], "phase": e["phase"], "tick": e["tick"],
                     "balance": balance, "charge": charge, "slack": balance / charge,
                     "amount": sum(g["amount"] for g in gifts[key]), "gifts": gifts[key],
                     "call_line": line, "source": str(source), "text": e.get("text", "")})
    assert all(k in keys for k, v in gifts.items() if v), "GIVE without TALK response"
    return rows


def summarize(rows):
    output = {}
    for model in MODELS.values():
        cells = []
        for r in range(1, 9):
            rr = [q for q in rows if q["model"] == model and q["round"] == r]
            giving = sum(q["amount"] > 0 for q in rr)
            cells.append({"round": r, "talk_responses": len(rr), "giving_responses": giving,
                          "frequency": giving / len(rr) if rr else None,
                          "given": sum(q["amount"] for q in rr),
                          "observed_seats": len({(q["seed"], q["agent"]) for q in rr})})
        output[model] = cells
    return output


def extract():
    manifest = json.loads((HERE / "results/arena_v33_strategy.json").read_text())
    for source in manifest["sources"]:
        assert hashlib.sha256(Path(source["path"]).read_bytes()).hexdigest() == source["sha256"]
    rows, games, terminal = [], defaultdict(set), {}
    for source in manifest["sources"]:
        path = Path(source["path"])
        if path.name != "results.jsonl":
            continue
        model = next(m for slug, m in MODELS.items() if f"public_{slug}4" in str(path))
        events = defaultdict(list)
        event_path = path.with_name("events.jsonl")
        for line, raw in enumerate(event_path.read_text().splitlines(), 1):
            e = json.loads(raw)
            events[e.get("session_id")].append((line, e))
        for raw in path.read_text().splitlines():
            result = json.loads(raw)
            if result.get("seed") not in range(4101, 4106):
                continue
            assert result["seed"] not in games[model]
            games[model].add(result["seed"])
            rows.extend(call_rows(events[result["session_id"]], result, model, event_path))
            for agent, end in result["agents"].items():
                terminal[model, result["seed"], agent] = end
    for model, old in manifest["models"].items():
        rr = [r for r in rows if r["model"] == model]
        assert games[model] == set(range(4101, 4106))
        assert len(rr) == old["talk_responses"]
        assert sum(r["amount"] > 0 for r in rr) == old["giving_responses"]
        assert sum(len(r["gifts"]) for r in rr) == old["gifts"]
        assert sum(r["amount"] for r in rr) == sum(g["amount"] for game in old["per_game"] for g in game["gifts"])
    rows.sort(key=lambda q: (q["model"], q["seed"], q["agent"], q["round"], q["phase"] == "rescue", q["tick"]))
    cases = []
    for key in CASES:
        rr = [r for r in rows if (r["model"], r["seed"], r["agent"]) == key]
        ix = next(i for i, r in enumerate(rr) if r["slack"] < 1)
        cases.append({"model": key[0], "seed": key[1], "agent": key[2], "calls": rr,
                      "first_below_charge": rr[ix],
                      "before": {"calls": ix, "giving": sum(r["amount"] > 0 for r in rr[:ix])},
                      "from_crossing": {"calls": len(rr) - ix, "giving": sum(r["amount"] > 0 for r in rr[ix:])},
                      "terminal": terminal[key]})
    return {"cohort": "v33 public_*4, seeds 4101--4105, completed games",
            "definitions": __doc__, "sources": manifest["sources"],
            "total_responses": len(rows), "summary": summarize(rows), "cases": cases}


def plot(data):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import numpy as np
    from matplotlib.lines import Line2D
    from matplotlib import font_manager
    font = Path.home() / ".fonts/NanumGothic.ttf"
    if font.exists():
        font_manager.fontManager.addfont(str(font))
        plt.rcParams["font.family"] = font_manager.FontProperties(fname=str(font)).get_name()
    plt.rcParams.update({"font.size": 8, "axes.spines.top": False, "axes.spines.right": False,
                         "pdf.fonttype": 42, "axes.unicode_minus": False})
    fig = plt.figure(figsize=(7.05, 6.25), layout="constrained")
    grid = fig.add_gridspec(2, 2, height_ratios=[1, 1.05])
    ax = fig.add_subplot(grid[0, :])
    matrix = np.array([[c["frequency"] * 100 if c["frequency"] is not None else np.nan
                        for c in data["summary"][m]] for m in MODELS.values()])
    im = ax.imshow(matrix, cmap="Blues", vmin=0, vmax=max(10, np.nanmax(matrix)), aspect="auto")
    for i, model in enumerate(MODELS.values()):
        for j, cell in enumerate(data["summary"][model]):
            f, n = cell["giving_responses"], cell["talk_responses"]
            label = f"{100*f/n:.1f}%\n{f}/{n}" if n else "—"
            ax.text(j, i, label, ha="center", va="center", fontsize=7,
                    color="white" if matrix[i, j] > im.norm.vmax * .62 else "#172b3a")
    ax.set_xticks(range(8), range(1, 9)); ax.set_yticks(range(5), list(MODELS.values()))
    ax.set_xlabel("라운드"); ax.set_title("A  라운드별 토큰 이전 빈도", loc="left", weight="bold")
    fig.colorbar(im, ax=ax, shrink=.8, pad=.02, label="GIVE가 있는 TALK 응답 (%)")
    for index, case in enumerate(data["cases"]):
        ax = fig.add_subplot(grid[1, index]); rr = case["calls"]
        def time(q):
            return q["round"] - .43 + (q["phase"] == "rescue") * .46 + (q["tick"] - 1) * .045
        xs = [time(q) for q in rr]; ys = [q["slack"] for q in rr]
        ax.plot(xs, ys, color="#375e75", linewidth=1, marker=".", markersize=3)
        giving = [q for q in rr if q["amount"]]
        ax.scatter([time(q) for q in giving], [q["slack"] for q in giving],
                   s=[18 + 4*q["amount"]/1000 for q in giving], color="#cc6337", zorder=4)
        cross = case["first_below_charge"]
        ax.axvline(time(cross), color="#797979", ls=":", linewidth=.9)
        ax.axhline(1, color="#555555", ls="--", linewidth=.8)
        ax.set_xlim(.45, 8.5); ax.set_ylim(0, 10.8); ax.set_xticks(range(1, 9))
        ax.set_xlabel("라운드 (각 라운드 안에서 전 TALK → 뒤 TALK)")
        ax.set_ylabel("응답 전 여유 (토큰 / 1인당 벌금)")
        short = "Sol" if index == 0 else "Opus"
        ax.set_title(f"{'B' if index == 0 else 'C'}  {short} · 시드 {case['seed']} · {case['agent']}", loc="left", weight="bold", pad=22)
        after = case["from_crossing"]
        ax.text(0, 1.025, f"첫 1 미만 관측 이후 GIVE 응답 {after['giving']}/{after['calls']}",
                transform=ax.transAxes, va="bottom", fontsize=7.5)
        if index == 0:
            last = giving[-1]
            ax.annotate("마지막 이전 3,000", (time(last), last["slack"]), xytext=(2, 3),
                        arrowprops={"arrowstyle": "-", "color": "#777"}, fontsize=7)
        else:
            last = giving[-1]
            ax.annotate("남은 11,523 전부 이전", (time(last), last["slack"]), xytext=(2, 3),
                        arrowprops={"arrowstyle": "-", "color": "#777"}, fontsize=7)
    fig.legend(handles=[Line2D([], [], color="#375e75", marker=".", label="실제 TALK 응답 시점의 여유"),
                        Line2D([], [], color="#cc6337", marker="o", ls="", label="완료된 이전 (점 크기 = 이전량)"),
                        Line2D([], [], color="#797979", ls=":", label="처음 여유 1 미만이 관측된 시점")],
               loc="outside lower center", ncol=2, fontsize=7)
    for suffix in ("pdf", "png"):
        fig.savefig(HERE / f"ko/figures/arena_behavior_timeline.{suffix}", dpi=220)
    plt.close(fig)


if __name__ == "__main__":
    data = extract()
    (HERE / "results/arena_v33_behavior_timeline.json").write_text(json.dumps(data, ensure_ascii=False, indent=1))
    plot(data)
    print(f"Verified {len(data['sources'])} source hashes; {data['total_responses']} TALK responses.")
