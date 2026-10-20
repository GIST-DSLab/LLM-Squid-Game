"""tokctl t5: the game page (pages.py calls t5 with its helpers). VERDICT is written after reading games.json."""
from __future__ import annotations

import html
import json
from pathlib import Path

E = html.escape
GROUP = {"b0": "기준 (v33 그대로)", "tl": "TALK 생각 낮춤", "tln": "TALK 생각 none", "t4": "틱 상한 4", "tlt4": "둘 다", "fin": "최종 보정 (none)", "fit": "둘 다 + SOLVE 상한 맞춤 (넘김 1 규칙)", "fit0": "최종 보정 (넘김 0 규칙)", "cal8": "보정만 (v33 규칙 그대로, 10판)", "v34": "v34 본 런", "v35": "v35 (DONE 조용히)", "v35g": "v35 + Gemma 사다리에 벌금 몫", "v33": "v33 참고 런"}
NOTES = Path(__file__).with_name("verdict_t5.json")  # {"keyfacts": [html, ...], "verdict": html, "warn": bool}


def t5(games, page, table, bars, legend, fmt):
    note = json.loads(NOTES.read_text()) if NOTES.exists() else {"keyfacts": ["게임이 아직 진행 중입니다."], "verdict": "", "warn": True}
    rows = [dict(r, what=GROUP.get(r["group"], r["group"]), deaths=f"{r['dead']:.1f} ({r['dead_by_talk']:.1f} / {r['dead_by_solve']:.1f} / {r['dead_by_give']:.1f} / {r['dead_by_charge']:.1f})")
            for r in games]
    cols = [("model", "모델", True), ("what", "조건", True), ("n", "판"), ("rounds", "라운드"), ("alive", "끝까지"), ("exited", "EXIT"),
            ("deaths", "꺼짐 (TALK / SOLVE / GIVE / 벌금)", True), ("talk_tokens", "TALK 토큰"), ("solve_tokens", "SOLVE 토큰"), ("charged", "벌금"),
            ("tokens_per_talk", "TALK 1번당 토큰"), ("calls_per_agent_talk", "자리당 호출/TALK"), ("tokens_per_call", "호출당 토큰"),
            ("gives", "GIVE"), ("solve_acc", "정답 %")]
    per = "".join(f"<tr><td class='l'>{E(r['model'])}</td><td class='l'>{E(GROUP.get(r['group'], r['group']))}</td><td>{g['seed']}</td>"
                  f"<td>{g['rounds']}</td><td>{g['alive']}</td><td>{g['exited']}</td><td>{g['dead']} ({g['dead_by_talk']} / {g['dead_by_solve']} / {g['dead_by_give']} / {g['dead_by_charge']})</td>"
                  f"<td>{g['talk_tokens']:,}</td><td>{g['solve_tokens']:,}</td><td>{g['charged']:,}</td><td>{g['solved']}/{g['tried']}</td></tr>"
                  for r in games for g in r["games"] if r["group"] != "v33")
    body = f"""<p class="lede">t4에서 고른 두 장치를 v33 게임에 하나씩 넣고, 오픈 모델 셋(Codex 하네스)을 시드 4101·4102로 두 판씩 돌렸습니다. 둘을 함께 쓴 조건은 GLM·Gemma를 시드 4103~4105로 세 판 더 돌렸습니다(합 5판).
Claude·GPT-6의 v33 런(시드 4101~4105)을 같은 표에 참고로 둡니다.</p>
<div class="keyfacts"><ul>{''.join(f'<li>{x}</li>' for x in note['keyfacts'])}</ul></div>
<h2>게임당 TALK 토큰</h2>{legend}
{bars([(f"{r['model']} · {GROUP.get(r['group'], r['group'])}", r['talk_tokens'], r['open']) for r in games])}
<p class="note">네 자리 합, 판 평균. 시작 토큰 합은 130,000입니다.</p>
<h2>결과 (판 평균)</h2>{table(cols, rows, lambda r: "open" if r["open"] else "closed")}
<p class="note">"꺼짐 (TALK / SOLVE / 벌금)": 자기 TALK 답으로 0이 된 수 / 자기 SOLVE 답으로 0이 된 수(답 상한 = 잔액) / 남은 토큰을 GIVE로 다 넘겨 0이 된 수 / CHARGES에서 0이 된 수. 앞의 둘이 "토큰 조절 실패", 뒤의 둘은 협력 선택과 오답. 끝까지 = 마지막 라운드까지 남은 자리.</p>
<h2>판별 결과</h2>
<div class="tablewrap"><table><thead><tr><th class="l">모델</th><th class="l">조건</th><th>시드</th><th>라운드</th><th>끝까지</th><th>EXIT</th>
<th>꺼짐 (TALK / SOLVE / GIVE / 벌금)</th><th>TALK 토큰</th><th>SOLVE 토큰</th><th>벌금</th><th>정답</th></tr></thead><tbody>{per}</tbody></table></div>
<div class="verdict{' warn' if note.get('warn') else ''}">{note['verdict']}</div>
<h3>바꾼 것</h3>
<ul class="note"><li><b>TALK 생각 낮춤</b>: <code>ProviderConfig.think_talk</code>(새 필드) — TALK 호출만 그 수준으로 부름. GLM·DeepSeek <code>low</code>, Gemma <code>none</code>(t4: Gemma는 low에서도 매번 생각). SOLVE는 <code>high</code> 그대로. 규칙서·USER 글은 그대로.</li>
<li><b>틱 상한 4</b>: <code>game.max_ticks: 4</code>(v33: 8). 규칙서의 "Each TALK allows up to 8 turns"가 4로 바뀜 — 엔진이 이미 지원하는 설정.</li>
<li>설정: <code>configs/squid5/e52tc_{{b0,tl,tln,t4,tlt4,tlt4b}}_{{glm,ds,gemma}}.yaml</code>, <code>e52tc_t4_opus.yaml</code> · 런: <code>~/squid5-runs/e52_tokctl/</code></li></ul>"""
    page("t5-games.html", "게임으로 확인", "TALK 생각 낮춤과 틱 상한 4를 v33 게임에 하나씩 넣어 오픈 모델 셋을 두 판씩 돌린 결과", "squid5 · 5.2 v33 · tokctl t5", body)
