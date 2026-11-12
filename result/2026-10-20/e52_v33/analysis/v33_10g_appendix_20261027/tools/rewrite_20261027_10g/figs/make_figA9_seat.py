"""Appendix: Fig. 3 with reasoning scored as picked_top against a same-seat baseline at any margin (an3/pt_seat.json). The first two
plots of (a) and both splits of (b) change: early tokens are divided by the same model's median (an3/pt_seat.py);
the third plot of (a) and (c), (d) are drawn as in Fig. 3."""
import json, os
import make_figA4_rho as f3
PS = json.load(open(os.path.join(f3.S, "an3", "pt_seat.json")))
f3.draw(PS["profile"], PS["joint"], "최다 행동 선택과\n같은 자리 기준(%)",
        "검은 가로줄: 같은 시드·같은 시작 토큰 자리의 다른 모델이 최다 행동을 고른 비율(모든 여유). 점선: 같은 모델 중앙값(1)",
        "두 능력: 같은 자리 기준 이상으로 최다 행동 고르기, 초반 응답당 토큰이 같은 모델 중앙값 이하", "figA9_seat_10g", "rw_figA9_seat_10g.pdf", acc_ymax=115,
        tok_key="etok_rel_med", tok_title="초반 응답당 토큰\n(같은 모델 중앙값 대비)", tok_ymax=1.6, tok_ticks=(0, 0.5, 1, 1.5), tok_fmt="{:.2f}", tok_ref=1)
