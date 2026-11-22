"""기준 스프라이트(파란 머리 A)의 파란 계열 화소만 다른 에이전트 색으로 옮긴다.

트레이닝복(청록, hue≈165°)과 흰색·검정은 건드리지 않는다. 모양이 같은 네 캐릭터를
생성 모델을 다시 부르지 않고 결정적으로 만든다.
사용: python recolor.py 입력.png 출력접두어   → 출력접두어_{blue,orange,green,purple,off}.png
"""
import colorsys
import sys

import numpy as np
from PIL import Image

SRC = "2369A8"  # 아레나 sgblue
TARGETS = {"blue": "2369A8", "orange": "C66B18", "green": "23856C", "purple": "8658A5"}
HUE_BAND = (185 / 360, 240 / 360)  # 파란 계열로 볼 범위
MIN_SAT = 0.08
# 목 아래(트레이닝복)의 남색 외곽선(명도≈0.44)은 그대로 두고, 밝은 파랑(장갑·목, 명도≈0.70)만 옮긴다.
HEAD_BOTTOM = 0.495  # 그림 높이 대비 머리 아래끝
BODY_MIN_V = 0.6


def hsv_of(hexcode):
    r, g, b = (int(hexcode[i:i + 2], 16) / 255 for i in (0, 2, 4))
    return colorsys.rgb_to_hsv(r, g, b)


def tint_mask(rgba):
    """머리의 연한 하늘색 띠 화소."""
    a = rgba.astype(np.float64) / 255
    r, g, b = a[..., 0], a[..., 1], a[..., 2]
    return (b > 0.9) & (g > 0.8) & (r > 0.6) & (r < 0.85) & (a[..., 3] > 0.5)


def head_mask(rgba):
    """띠 안쪽(화면·눈·입)까지 채운 머리 영역. 포즈마다 머리 위치·기울기가 달라 자동으로 찾는다."""
    from scipy import ndimage
    return ndimage.binary_dilation(ndimage.binary_fill_holes(tint_mask(rgba)), iterations=4)


def head_unit(rgba):
    """크기 기준 = 띠 면적의 제곱근(머리 회전·3/4 각도에 덜 민감)."""
    return float(tint_mask(rgba).sum()) ** 0.5


def recolor(rgba, target_hex=None, auto_head=False):
    a = rgba.astype(np.float64) / 255
    rgb, alpha = a[..., :3], a[..., 3]
    mx, mn = rgb.max(-1), rgb.min(-1)
    v = mx
    s = np.where(mx > 0, (mx - mn) / np.maximum(mx, 1e-9), 0)
    h = np.vectorize(lambda r, g, b: colorsys.rgb_to_hsv(r, g, b)[0])(rgb[..., 0], rgb[..., 1], rgb[..., 2])
    if auto_head:
        in_head = head_mask(rgba)
    else:
        rows = np.arange(rgba.shape[0])[:, None] / rgba.shape[0]
        in_head = np.broadcast_to(rows < HEAD_BOTTOM, v.shape)
    mask = (h >= HUE_BAND[0]) & (h <= HUE_BAND[1]) & (s > MIN_SAT) & (alpha > 0) & (in_head | (v > BODY_MIN_V))
    _, ss, sv = hsv_of(SRC)
    out = rgb.copy()
    if target_hex is None:  # 꺼진 로봇: 같은 명도의 회색
        grey = 0.35 + 0.55 * v
        for c in range(3):
            out[..., c] = np.where(mask, grey, rgb[..., c])
    else:
        th, ts, tv = hsv_of(target_hex)
        ns = np.clip(s * ts / ss, 0, 1)
        nv = np.clip(v * tv / sv, 0, 1)
        conv = np.vectorize(lambda s_, v_: colorsys.hsv_to_rgb(th, s_, v_), otypes=[float, float, float])
        r, g, b = conv(ns, nv)
        for c, ch in enumerate((r, g, b)):
            out[..., c] = np.where(mask, ch, rgb[..., c])
    res = np.dstack([out, alpha])
    return (res * 255).round().astype(np.uint8)


def main(src, prefix):
    im = np.array(Image.open(src).convert("RGBA"))
    for name, hx in TARGETS.items():
        Image.fromarray(recolor(im, hx)).save(f"{prefix}_{name}.png")
    Image.fromarray(recolor(im, None)).save(f"{prefix}_off.png")


if __name__ == "__main__":
    main(*sys.argv[1:3])
