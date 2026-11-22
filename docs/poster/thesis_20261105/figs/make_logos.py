"""Lab/school marks for the dark poster header, as a transparent PNG.

The marks come from the footer of sample/JumyungPark_GIST_BS_Poster.pdf, where they sit
on a flat gray (204) band in dark gray. Each pixel is read as a blend of that gray and one
mark color; the gray becomes transparent and dark grays are recolored light so the marks
read on the poster background. Red and blue keep their brand colors.

Run: ~/.venvs/squid-game/bin/python poster/figs/make_logos.py  (needs pdftoppm)
"""
from pathlib import Path
import subprocess
import tempfile

import numpy as np
from PIL import Image

HERE = Path(__file__).resolve().parent
SAMPLE = HERE.parent / 'sample/JumyungPark_GIST_BS_Poster.pdf'
DPI = 600
X, Y, W, H = 1800, 4, 492, 78          # pt, same crop as the poster's old viewport (from bottom)
PAGE_H = 3456

BG = np.array([204, 204, 204], float)
# 원본 색 -> 어두운 배경용 색
KEYS = [
    ((51, 51, 51), (242, 239, 244)),     # 글자 -> 포스터 fg
    ((105, 104, 110), (190, 188, 196)),  # GIST·AI 마크 회색 -> 밝은 회색
    ((225, 48, 40), (225, 48, 40)),      # 빨강 유지
    ((67, 90, 167), (92, 120, 205)),     # 파랑: 어두운 배경에서 보이도록 약간 밝게
    ((207, 210, 211), (88, 90, 98)),     # 연구실 로고의 밝은 사각형 -> 어두운 회색 면
]

with tempfile.TemporaryDirectory() as tmp:
    s = DPI / 72
    subprocess.run(['pdftoppm', '-png', '-r', str(DPI), '-singlefile',
                    '-x', str(round(X * s)), '-y', str(round((PAGE_H - Y - H) * s)),
                    '-W', str(round(W * s)), '-H', str(round(H * s)),
                    str(SAMPLE), f'{tmp}/crop'], check=True)
    px = np.asarray(Image.open(f'{tmp}/crop.png').convert('RGB'), float)

best_res = np.full(px.shape[:2], np.inf)
out = np.zeros((*px.shape[:2], 4))
d = px - BG
for src, dst in KEYS:
    k = np.array(src, float) - BG
    a = np.clip((d @ k) / (k @ k), 0, 1)                  # 배경과 이 색의 혼합 비율
    res = np.linalg.norm(d - a[..., None] * k, axis=-1)
    better = res < best_res
    best_res[better] = res[better]
    out[better, :3] = dst
    out[better, 3] = a[better]
out[..., 3] = np.where(np.linalg.norm(d, axis=-1) < 2, 0, out[..., 3])
# 연구실 로고에서 두 사각형이 겹치는 칸은 원본에서 배경과 같은 회색이라 투명해진다.
# 밝은 사각형의 경계 상자 안쪽은 그 사각형 색으로 채운다.
sq = np.all(np.abs(px - KEYS[-1][0]) < 1.5, axis=-1)
ys, xs = np.nonzero(sq)
y0, y1, x0, x1 = ys.min(), ys.max() + 1, xs.min(), xs.max() + 1
box = out[y0:y1, x0:x1]
hole = box[..., 3] < 1
box[hole, :3] = KEYS[-1][1]
box[hole, 3] = 1
Image.fromarray(np.round(out * [1, 1, 1, 255]).astype(np.uint8), 'RGBA').save(HERE / 'logos_dark.png')
print('wrote', HERE / 'logos_dark.png')
