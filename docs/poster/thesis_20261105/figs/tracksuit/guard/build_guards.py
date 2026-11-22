r"""진행요원 포즈 원본(guard/poses/*_v1.png) → 잘라낸 스프라이트(sprites/guard_*.png)와 배치 메타(sprites/guard_meta.tex).

생성 모델을 다시 부르지 않는 결정적 단계. 좌표는 모두 잘라낸 그림의 왼쪽 아래 기준, 그림 높이 = 1.
  \gd@<이름>@w       : 폭/높이,  \gd@<이름>@fx : 발끝(아래 3%) 가로 중심
  aim  : \gd@aim@mx, \gd@aim@my   총구(가장 왼쪽 불투명 화소)
  sign : \gd@sign@{x0,x1,y0,y1}   흰 팻말 안쪽 상자
  big  : \gd@big@{hx0,hx1,hy1}    후드 좌우 끝·위끝, \gd@big@{mx,my} 마스크 중심
사용: python guard/build_guards.py   (figs/tracksuit에서)
"""
import numpy as np
from PIL import Image

POSES = ["aim", "sign", "big"]


def main():
    meta = []
    for n in POSES:
        im = Image.open(f"guard/poses/{n}_v1.png").convert("RGBA")
        im = im.crop(im.getchannel("A").point(lambda v: 255 if v > 8 else 0).getbbox())
        im.save(f"sprites/guard_{n}.png")
        a = np.array(im).astype(int)
        h, w = a.shape[:2]
        op = a[..., 3] > 128
        fx = lambda x: f"{x / h:.4f}"           # 폭 방향도 높이로 나눈다(높이 = 1)
        fy = lambda y: f"{(h - y) / h:.4f}"     # 아래에서 잰 높이
        ys, xs = op[int(h * .97):].nonzero()
        d = {"w": fx(w), "fx": fx(xs.mean())}
        if n == "aim":
            ys, xs = op.nonzero()
            i = xs.argmin()
            d.update(mx=fx(xs[i]), my=fy(ys[i]))
        if n == "sign":
            white = op & (a[..., :3].min(axis=2) > 235)
            rows = white.sum(axis=1)               # 팻말 = 위에서 처음 나오는, 흰 화소가 많은 줄의 연속 구간
            full = rows > rows.max() * .5          # (마스크의 흰 △는 줄마다 화소가 적어 빠진다)
            top = full.argmax()
            bot = top + (~full[top:]).argmax()
            white[:top] = False
            white[bot:] = False
            ys, xs = white.nonzero()
            d.update(x0=fx(xs.min()), x1=fx(xs.max()), y0=fy(ys.max()), y1=fy(ys.min()))
        if n == "big":
            r, g, b = a[..., 0], a[..., 1], a[..., 2]
            pink = op & (r > 180) & (g < 90) & (b > 70)
            pink[int(h * .45):] = False            # 후드만
            ys, xs = pink.nonzero()
            dark = op & (a[..., :3].max(axis=2) < 40)
            dark[int(h * .45):] = False
            my_, mx_ = dark.nonzero()
            d.update(hx0=fx(xs.min()), hx1=fx(xs.max()), hy1=fy(ys.min()),
                     mx=fx(mx_.mean()), my=fy(my_.mean()))
        for k, v in d.items():
            meta.append(f"\\expandafter\\def\\csname gd@{n}@{k}\\endcsname{{{v}}}")
        print(n, w, h, d)
    open("sprites/guard_meta.tex", "w").write("\n".join(meta) + "\n")


if __name__ == "__main__":
    main()
