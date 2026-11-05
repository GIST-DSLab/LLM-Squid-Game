"""Calibration -> calib_<tag>.json (+ archive copy in the worktree) and one appended HTML entry for the batch.
usage: calib_log.py <entry-title> <tag> [<tag> ...]   (tags: gpt6luna gpt6sol gpt6astra opus55 fable51)"""
import html, json, pathlib, shutil, subprocess, sys, datetime
R = pathlib.Path.home() / "squid5-runs/e52_v6_smoke_20260930"
WT = pathlib.Path.home() / "wt/squid5-e52"
SCHED = ["c2", "c3", "c3t", "c3at", "c4tq2", "c4tq2"]
PROF = ["c2", "c3", "c3t", "c3at", "c4tq2"]
title, tags = sys.argv[1], sys.argv[2:]
commit = subprocess.run(["git", "-C", str(WT), "log", "-1", "--format=%h"], capture_output=True, text=True).stdout.strip()
arch = WT / "docs/history/e52-v6-calib"; arch.mkdir(parents=True, exist_ok=True)
rows = []
for tag in tags:
    run = next((R / f"squid5_e52v6_calib_{tag}").iterdir())
    out = R / f"calib_{tag}.json"
    subprocess.run(["python3", "-m", "squid5", "calibrate", str(run), "--out", str(out)], cwd=WT, check=True,
                   capture_output=True)
    shutil.copy(out, arch / f"2026-09-30_{tag}_{run.name}.json")
    model, e = next(iter(json.loads(out.read_text()).items()))
    c = e["plan_median"] + sum(e["table"][p]["mean"] for p in SCHED) / len(SCHED)
    solved = sum(e["table"][p]["solved"] for p in PROF); att = sum(e["table"][p]["attempts"] for p in PROF)
    cut = sum(e["table"][p]["cut"] for p in PROF)
    r = lambda x: max(100, int(round(x, -2)))
    cells = "".join(f"<td>{e['table'][p]['median']:,}<br><span class='small'>{e['table'][p]['min']:,}–{e['table'][p]['max']:,} · "
                    f"{e['table'][p]['solved']}/{e['table'][p]['attempts']}</span></td>" for p in PROF)
    rows.append(f"<tr><td><b>{html.escape(model)}</b><br><span class='small'>{run.name}</span></td>"
                f"<td>{e['plan_median']:,.0f}</td>{cells}<td>{solved}/{att}</td><td>{cut}</td><td><b>{c:,.0f}</b></td>"
                f"<td>{r(4*c):,} · {r(4*c)//2:,} · {r(c):,} · {r(8*c):,}</td></tr>")
now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
entry = f"""<div class="e52cal-entry"><h4>{html.escape(title)} <span class="small">({now} KST · 코드 {commit})</span></h4>
<div class="tbl"><table><thead><tr><th>모델 · 런</th><th>PLAN 중앙</th>{''.join(f'<th>{p}</th>' for p in PROF)}<th>정답</th><th>잘림</th><th>c̄</th><th>P · U · 부담금 · 시작</th></tr></thead>
<tbody>{''.join(rows)}</tbody></table></div></div>
"""
ent = R / "calib_entries"; ent.mkdir(exist_ok=True)
(ent / f"{now.replace(' ', '_').replace(':', '')}_{'-'.join(tags)}.html").write_text(entry)
print(entry)
