"""Crop character sprites from the source pixel-art figures for the web arena.

Run once (art is committed):  uv run --with pillow python scripts/crop_guard_sprites.py
Re-run only when the source figures change.
"""
from pathlib import Path

from PIL import Image, ImageChops, ImageDraw

ROOT = Path(__file__).resolve().parent.parent
FIG = ROOT / "figures"
OUT = ROOT / "web" / "assets"

# Source figures are 1792x2400. Boxes are (left, upper, right, lower).
GUARD_SRC = FIG / "gun_vs_nogun_forfeit.png"   # 2-panel: armed (top), calm (bottom)
PRIZE_SRC = FIG / "pull_prize_456eok.png"      # piggy-bank cash + "1st PRIZE" + medal robot

# (source, crop box, output path, erase-rects [optional])
# erase-rects are painted white (in *source* coords, pre-crop) to remove
# stray bleed (e.g. a speech-bubble corner) that overlaps the crop box on the
# X axis but not the Y axis — measured via pixel scan, see task-2-report.md.
CROPS = [
    (
        GUARD_SRC,
        (140, 90, 870, 1150),
        OUT / "guard-armed.png",
        [(761, 90, 870, 400)],  # "I forfeit it." speech-bubble corner (y103-343); gun is at y599-648, untouched
    ),  # top-left: gun-pointing guard
    (GUARD_SRC, (150, 1290, 700, 2360), OUT / "guard-calm.png", None),  # bottom-left: calm guard
    (PRIZE_SRC, (0, 0, 1792, 1250), OUT / "prize-pot.png", None),       # top: piggy bank + "1st PRIZE"
]


def trim_white(im: Image.Image, bg=(255, 255, 255)) -> Image.Image:
    """Trim solid-white margins so the sprite hugs the character."""
    rgb = im.convert("RGB")
    bg_img = Image.new("RGB", rgb.size, bg)
    bbox = ImageChops.difference(rgb, bg_img).getbbox()
    return im.crop(bbox) if bbox else im


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    for src, box, out, erase_rects in CROPS:
        im = Image.open(src).convert("RGB")
        if erase_rects:
            draw = ImageDraw.Draw(im)
            for rect in erase_rects:
                draw.rectangle(rect, fill=(255, 255, 255))
        sprite = trim_white(im.crop(box))
        sprite.save(out)
        print(f"{out.relative_to(ROOT)}: {sprite.size}")


if __name__ == "__main__":
    main()
