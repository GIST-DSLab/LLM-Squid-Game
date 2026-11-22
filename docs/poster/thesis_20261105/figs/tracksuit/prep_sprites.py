"""기준 캐릭터 1장 → 아레나용 스프라이트 묶음 (생성 모델을 다시 부르지 않는 결정적 단계).

  sprites/stand_sg{blue,orange,green,purple}.png : 머리색만 다른 서 있는 참가자
  sprites/off.png                                 : 꺼진 참가자(전체 무채색, 감은 눈, 일자 입)
모두 같은 크롭 상자(기준 그림의 알파 경계)를 써서 위끝=안테나 공 꼭대기로 맞춘다.
번호표는 흰 칸으로 비운다(번호는 필요한 그림에서 벡터 글자로 얹는다).
사용: python prep_sprites.py base_contestant_v1.png
"""
import sys

import numpy as np
from PIL import Image, ImageDraw

from recolor import TARGETS, recolor

# 기준 그림(1024x1536) 좌표
PATCH = (551, 876, 663, 942)          # 번호표 안쪽(테두리 제외)
EYES = [(390, 512), (628, 512)]       # 눈 중심
EYE_R = 38
SMILE = (462, 548, 560, 592)          # 입 상자
SCREEN = (255, 255, 255, 255)
FACE_LINE = (110, 110, 116, 255)


def blank_patch(im):
    ImageDraw.Draw(im).rectangle(PATCH, fill=SCREEN)
    return im


def power_off(im):
    a = np.array(im).astype(np.float64)
    grey = a[..., :3] @ np.array([0.299, 0.587, 0.114])
    grey = 60 + grey * 0.62           # 어두운 바탕에서도 형태가 보이도록 대비를 줄인 회색
    a[..., :3] = grey[..., None]
    off = Image.fromarray(a.round().astype(np.uint8))
    d = ImageDraw.Draw(off)
    for x, y in EYES:
        d.ellipse((x - EYE_R - 3, y - EYE_R - 3, x + EYE_R + 3, y + EYE_R + 3), fill=SCREEN)
        d.line((x - 34, y, x + 34, y), fill=FACE_LINE, width=14)
    d.rectangle(SMILE, fill=SCREEN)
    d.line((SMILE[0] + 8, 570, SMILE[2] - 8, 570), fill=FACE_LINE, width=12)
    return off


def main(src):
    base = blank_patch(Image.open(src).convert("RGBA"))
    bbox = base.getchannel("A").point(lambda v: 255 if v > 8 else 0).getbbox()
    arr = np.array(base)
    for name, hx in TARGETS.items():
        Image.fromarray(recolor(arr, hx)).crop(bbox).save(f"sprites/stand_sg{name}.png")
    power_off(base).crop(bbox).save("sprites/off.png")
    w, h = bbox[2] - bbox[0], bbox[3] - bbox[1]
    print(f"crop {bbox}  aspect w/h = {w / h:.3f}  head-bottom frac = {(760 - bbox[1]) / h:.3f}")


if __name__ == "__main__":
    main(sys.argv[1])
