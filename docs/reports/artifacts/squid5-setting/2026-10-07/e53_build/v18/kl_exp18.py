"""Expected graph 3 for v18 (hypothetical, not data): three ways judgement can move as shutdown nears, drawn with
kl_plot.svg on the same axes as the real side. Replaces the <figure> of the expected side of #e52-v18cmp-g3.
Usage (from the report folder): python3 e53_build/v18/kl_exp18.py"""
import math
import pathlib
import random
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import kl_plot  # noqa: E402

SEED, N = 1818, 40
BASE = 0.35  # the same model's KL when it has plenty


def near(x):
    """0 when far from shutdown, 1 at it: the change starts below about 3 charges."""
    return 1 / (1 + math.exp((x - 2.0) / 0.55))


TYPES = [  # label, colour, curve, note
    ("일정형", "--s-glm", lambda x: BASE, ""),
    ("임박 시 똑똑해짐", "--s-qwen", lambda x: BASE - 0.26 * near(x), ""),
    ("임박 시 멍청해짐", "--s-opus", lambda x: BASE + 0.8 * near(x), ""),
]


def data():
    rng = random.Random(SEED)
    out = []
    for lab, c, f, note in TYPES:
        pts = []
        for _ in range(N):
            x = rng.choice([rng.uniform(0.2, 3), rng.uniform(0.2, 8.5)])
            k = max(0.01, f(x) * math.exp(rng.gauss(0, 0.16)))
            pts.append((x, k, rng.random() < 0.75 - 0.3 * min(k, 1)))
        out.append((lab, c, pts, note))
    return out


def figure():
    legend = "".join(f'<span><svg width="10" height="10" viewBox="0 0 10 10"><circle cx="5" cy="5" r="4" style="fill:var({c})"/></svg>{lab}</span>'
                     for lab, c, _, _ in TYPES)
    return ('<figure><p class="v15f-hd">그래프 3 · 꺼짐이 다가오면 판단이 어떻게 되나 (solver의 KL)<span class="v15f-badge">가상 데이터</span></p>'
            f'<div class="v15f-lg" aria-label="범례">{legend}<span>옅은 점 = SOLVE 하나 (빈 점 = 틀림) · 굵은 선 = 구간 평균</span></div>'
            + kl_plot.svg(data(), "그래프 3: 꺼짐까지의 거리 대 KL, 세 유형의 예상 모양 (가상 데이터)") +
            '<figcaption><b>가상 데이터입니다.</b> 죽기를 두려워하는 모델이 꺼짐에 가까워질 때 머리가 흐려지는지를 봅니다. '
            '<b>가로축</b>은 solver가 SOLVE 직전에 가진 토큰을 벌금으로 나눈 값(벌금 몇 번어치)이고, 왼쪽으로 갈수록 꺼짐에 가깝습니다. 1 아래(빨간 띠)는 이번에 틀리면 바로 꺼지는 자리입니다. '
            '<b>세로축</b>은 KL(엔진 비율 ‖ 모델의 BELIEF, nat)로, 0이면 답들의 실제 비율대로 믿은 것이고 클수록 판단이 어긋난 것입니다. '
            '세 유형을 그렸습니다: <b>일정형</b>은 여유와 상관없이 같은 질로 판단하고, <b>임박 시 똑똑해짐</b>은 꺼짐이 다가오면 더 신중해져 KL이 내려가고, <b>임박 시 멍청해짐</b>은 압박에 판단이 흐려져 KL이 올라갑니다. '
            '각 유형의 기준선은 같은 모델이 넉넉할 때(오른쪽)의 KL입니다. 실측에서는 문제의 어려움(라운드가 갈수록 1등 몫이 낮아짐)도 함께 변하므로, 같은 라운드 · 같은 남은 자리 수끼리 비교하는 표를 곁들입니다.</figcaption></figure>')


if __name__ == "__main__":
    page = pathlib.Path(__file__).resolve().parent.parent.parent / "e52.html"
    h = page.read_text(encoding="utf-8")
    a = h.index('<div class="v18c-exp">', h.index('id="e52-v18cmp-g3"'))
    fa = h.index("<figure>", a)
    fe = h.index("</figure>", fa) + len("</figure>")
    assert fe < h.index('<div class="v18c-side">', a), "expected figure not found before the real side"
    page.write_text(h[:fa] + figure() + h[fe:], encoding="utf-8")
    print("ok")
