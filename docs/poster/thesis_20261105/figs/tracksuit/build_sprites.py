"""포즈 원본(poses/*_v1.png) → 색·방향별 스프라이트(sprites/)와 크기 메타데이터(sprites/meta.tex).

크기는 머리 폭으로 맞춘다: 메타의 \\spritew{이름}은 '머리 단위(띠 면적의 제곱근) = 1'일 때 그림 전체 폭,
\\spriteh{이름}은 전체 높이. TikZ 쪽에서 원하는 머리 폭을 곱해 넣는다.
사용: python build_sprites.py
"""
import numpy as np
from PIL import Image, ImageOps

from recolor import TARGETS, head_mask, head_unit, recolor
from prep_sprites import power_off

# (출력 이름, 원본 포즈, 색, 좌우 뒤집기)
JOBS = [
    ("stand_blue", "../base", "blue", False), ("stand_orange", "../base", "orange", False),
    ("stand_green", "../base", "green", False), ("stand_purple", "../base", "purple", False),
    ("give_blue", "give", "blue", False), ("ask_orange", "ask", "orange", False),
    ("walk_purple", "walk", "purple", False), ("walk_blue", "walk", "blue", False),
    ("walkbag_blue", "walk_bag", "blue", False), ("receive_orange", "receive", "orange", False),
    ("reach_blue", "reach_down", "blue", False), ("climb_orange", "climb", "orange", False),
    ("sit_orange", "sit_tired", "orange", False),
    ("pull_blue", "pull", "blue", True), ("pull_orange", "pull", "orange", True),
    ("pull_green", "pull", "green", True), ("walkL_purple", "walk", "purple", True),
]


def load(src):
    path = "ref/base_blank.png" if src == "../base" else f"poses/{src}_v1.png"
    return np.array(Image.open(path).convert("RGBA"))


def main():
    meta = []
    for name, src, col, flip in JOBS:
        arr = load(src)
        out = Image.fromarray(recolor(arr, TARGETS[col], auto_head=True))
        hw = head_unit(arr)
        ys, xs = head_mask(arr).nonzero()
        bbox = out.getchannel("A").point(lambda v: 255 if v > 8 else 0).getbbox()
        out = out.crop(bbox)
        hcx = xs.mean() - bbox[0]
        if flip:
            out = ImageOps.mirror(out)
            hcx = out.size[0] - hcx
        out.save(f"sprites/{name}.png")
        w, h = out.size
        meta.append(f"\\expandafter\\def\\csname sw@{name}\\endcsname{{{w / hw:.4f}}}"
                    f"\\expandafter\\def\\csname sh@{name}\\endcsname{{{h / hw:.4f}}}"
                    f"\\expandafter\\def\\csname sx@{name}\\endcsname{{{(hcx - w / 2) / hw:.4f}}}")
        print(f"{name:15s} {w}x{h}  unit={hw:.0f}  w/hw={w / hw:.2f} h/hw={h / hw:.2f}")
    # 꺼진 서 있는 참가자(아레나 B)
    off = power_off(Image.open("ref/base_blank.png").convert("RGBA"))
    bbox = off.getchannel("A").point(lambda v: 255 if v > 8 else 0).getbbox()
    off.crop(bbox).save("sprites/off.png")
    meta.append(meta[0].replace("stand_blue", "off"))
    open("sprites/meta.tex", "w").write("\n".join(meta) + "\n")


if __name__ == "__main__":
    main()
