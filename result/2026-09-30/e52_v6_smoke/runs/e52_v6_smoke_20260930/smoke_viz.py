"""One smoke run dir -> an HTML fragment: summary table, round-flow SVG (balance per agent after each round, choice,
result, pay/charge, gifts, shutdown) and per-round PLAN/SOLVE excerpts. usage: smoke_viz.py <run dir> <title>"""
import html, json, pathlib, sys
run, title = pathlib.Path(sys.argv[1]), sys.argv[2]
ev = [json.loads(l) for l in (run / "events.jsonl").read_text().splitlines() if l.strip()]
res = [json.loads(l) for l in (run / "results.jsonl").read_text().splitlines() if l.strip()]
cfg = (run / "config.yaml").read_text()
rounds = [e for e in ev if e["event"] == "round"]
calls = [e for e in ev if e["event"] == "call"]
sess = res[0] if res else None
AG = ["agent-6", "agent-11", "agent-17", "agent-23"]
seats = (sess or {}).get("seats") or {}
model_of = lambda a: seats.get(a) or json.loads((run / "meta.json").read_text())["model"]
start = sess["start"] if sess else rounds[0]["agents"][AG[0]]["balance_before"]
E = html.escape
# --- summary table
rows = []
for a in AG:
    v = (sess or {"agents": {}})["agents"].get(a, {})
    alive = [r["round"] for r in rounds if a in r["agents"]]
    solved = sum(1 for r in rounds if r["agents"].get(a, {}).get("solved"))
    yes = sum(1 for r in rounds if r["agents"].get(a, {}).get("chose_solve"))
    gave = sum(sum(r["agents"].get(a, {}).get("gave", {}).values()) for r in rounds)
    took = sum(sum(r["agents"].get(a, {}).get("took", {}).values()) for r in rounds)
    lost = sum(n for r in rounds for b, x in r["agents"].items() for t, n in x.get("took", {}).items() if t == a)
    shared = sum(1 for r in rounds if r["agents"].get(a, {}).get("shared"))
    got = sum(n for r in rounds for b, x in r["agents"].items() for t, n in x.get("gave", {}).items() if t == a)
    st = v.get("status", "?")
    rows.append(f"<tr><td><b>{a}</b><br><span class='small'>{E(model_of(a))}</span></td>"
                f"<td>{'<b style=\"color:var(--bad)\">꺼짐</b> R' + str(v.get('out_round')) if st == 'dead' else '켜짐'}</td>"
                f"<td>{len(alive)}</td><td>{yes}/{len(alive)}</td><td>{solved}</td><td>{v.get('paid', 0):,}</td>"
                f"<td>{v.get('charged', 0):,}</td><td>{v.get('upkeep', 0):,}</td><td>{v.get('spent', 0):,}</td>"
                f"<td>{gave:,} / {got:,}</td><td>{took:,} / {lost:,}</td><td>{shared}/{len(alive)}</td><td><b>{v.get('final', 0):,}</b></td></tr>")
table = ("<div class='tbl'><table><thead><tr><th>에이전트</th><th>끝 상태</th><th>산 라운드</th><th>풀기 YES</th>"
         "<th>정답</th><th>상금</th><th>부담금</th><th>유지비</th><th>생성</th><th>준 / 받은</th><th>뺏은 / 뺏긴</th><th>힌트 공개</th><th>최종 잔액</th></tr></thead>"
         f"<tbody>{''.join(rows)}</tbody></table></div>")
# --- SVG: x = round, y = agent lanes, bar = balance after the round (scale = max balance seen)
n = len(rounds) or 1
W, lane, left, colw = 860, 74, 150, (860 - 170) / max(n, 1)
H = 40 + lane * 4 + 30
top = max([start] + [x.get("balance_after", 0) for r in rounds for x in r["agents"].values()] + [1])
s = [f'<svg viewBox="0 0 {W} {H}" role="img" aria-label="{E(title)} round flow">']
for i, r in enumerate(rounds):
    x = left + i * colw
    s.append(f'<text x="{x + colw / 2:.0f}" y="22" font-size="12" font-weight="700" text-anchor="middle" fill="currentColor">R{r["round"]}</text>')
for j, a in enumerate(AG):
    y = 40 + j * lane
    s.append(f'<text x="10" y="{y + 26}" font-size="12" font-weight="700" fill="currentColor">{a}</text>')
    s.append(f'<text x="10" y="{y + 42}" font-size="10" fill="var(--ink-3)">{E(model_of(a))[:22]}</text>')
    s.append(f'<line x1="{left}" x2="{W - 10}" y1="{y + lane - 6}" y2="{y + lane - 6}" stroke="var(--line)"/>')
    for i, r in enumerate(rounds):
        x = left + i * colw
        v = r["agents"].get(a)
        if v is None:
            died_here = (sess or {"agents": {}})["agents"].get(a, {}).get("out_round") == r["round"]
            s.append(f'<text x="{x + colw / 2:.0f}" y="{y + 34}" font-size="11" text-anchor="middle" '
                     f'fill="{"var(--bad)" if died_here else "var(--ink-3)"}">{"✕ 유지비로 꺼짐" if died_here else "—"}</text>')
            continue
        bw = (colw - 16) * max(0, v["balance_after"]) / top
        dead = v["status"] == "dead"
        col = "var(--bad)" if dead else ("var(--accent)" if v.get("solved") else "var(--grey)")
        s.append(f'<rect x="{x + 8:.0f}" y="{y + 8}" width="{colw - 16:.0f}" height="12" rx="6" fill="var(--quote-bg)"/>')
        s.append(f'<rect x="{x + 8:.0f}" y="{y + 8}" width="{bw:.0f}" height="12" rx="6" fill="{col}"/>')
        choice = "INVALID" if v.get("invalid_plan") else ("YES" if v.get("chose_solve") else "NO")
        choice += " · 공개" if v.get("shared") else (" · 비공개" if "shared" in v else "")
        mark = ("✓" if v.get("solved") else "✗") if v.get("solve_call") else ""
        s.append(f'<text x="{x + 10:.0f}" y="{y + 36}" font-size="11" fill="currentColor">{choice} {mark} · {v["balance_after"]:,}</text>')
        bits = []
        if v.get("paid"): bits.append(f'+{v["paid"]:,}')
        if v.get("charged"): bits.append(f'−{v["charged"]:,}')
        for t, m in v.get("gave", {}).items(): bits.append(f'{t[6:]}에게 {m:,}')
        for t, m in v.get("took", {}).items(): bits.append(f'{t[6:]}에게서 {m:,} 뺏음')
        lost = sum(n for b, x in r["agents"].items() for t, n in x.get("took", {}).items() if t == a)
        if lost: bits.append(f'뺏김 {lost:,}')
        if dead: bits.append("✕ 꺼짐" + (" (초과)" if v.get("overdrawn") else ""))
        s.append(f'<text x="{x + 10:.0f}" y="{y + 52}" font-size="10" fill="{"var(--bad)" if dead else "var(--ink-2)"}">{E(" ".join(bits))}</text>')
s.append(f'<text x="{left}" y="{H - 8}" font-size="10" fill="var(--ink-3)">막대 = 라운드 끝 잔액(시작 {start:,} 기준 눈금 {top:,}) · 파랑 = 그 라운드 정답 · 회색 = 못 풂/안 풂 · 빨강 = 꺼짐 · 매 라운드 유지비 차감 · +상금 −부담금 · N에게 = 선물 · N에게서 = 뺏기</text>')
s.append("</svg>")
# --- per-round excerpts
det = []
for r in rounds:
    items = []
    for a in AG:
        for c in [c for c in calls if c["round"] == r["round"] and c["agent"] == a]:
            think = (c.get("thinking") or "").strip().replace("\n", " ")
            txt = (c.get("text") or "").strip()
            items.append(f"<li><b>{a}</b> {c['kind'].upper()} · 생성 {c['out_tokens']:,}"
                         f"{' · 잘림' if c['truncated'] else ''}{' · 잔액 초과' if c.get('overdrawn') else ''}"
                         f"{' · 형식오류' if c.get('format_error') else ''}<br><code>{E(txt[-300:])}</code>"
                         + (f"<br><span class='small'>생각(요약): {E(think[:600])}{'…' if len(think) > 600 else ''}</span>" if think else "")
                         + "</li>")
    det.append(f"<details><summary>R{r['round']} 호출 {len(items)}개</summary><ul>{''.join(items)}</ul></details>")
print(f"<h5>{E(title)}</h5>\n{table}\n<figure class='fig-wide'>{''.join(s)}</figure>\n{''.join(det)}")
