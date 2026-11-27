"""The landing page's hero picture, a short loop (web/shared/assets/hero-coexist.gif) and its last frame as a still
(hero-coexist.png, shown when the visitor asks for reduced motion): the same moment of a survival session twice, one
panel above the other. In both, an agent hangs over a drop at the right end of the stage.

Above, the other three pull it up together (one kneels and takes its hand, two hold on behind in a chain); the four end
up standing side by side and the panel reads WIN. Below, an agent walks to the EXIT door and out through it instead; the
hand at the edge slips, the agent falls, the door shuts, and the panel reads LOSE.

The masked guard is a picture of its own (hero-guard.png), placed by the page.

Built from the poster's tracksuit sprites (docs/poster/thesis_20261105/figs/tracksuit: poses + recolor.py), so no
image model is called and the pictures are the same on every run.
Usage: python web/tools/make_hero_banner.py
"""
import math
import shutil
import subprocess
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageEnhance, ImageFilter, ImageFont

ROOT = Path(__file__).resolve().parents[2]
KIT = ROOT / "docs/poster/thesis_20261105/figs/tracksuit"
FONT = ROOT / "docs/poster/thesis_20261105/fonts/ChakraPetch-Bold.ttf"
ASSETS = ROOT / "web/shared/assets"
sys.path.insert(0, str(KIT))
from recolor import TARGETS, recolor  # noqa: E402

PW, PH = 1300, 580        # one panel, in scene units; both panels are this size
FLOOR, EDGE = 390, 840    # the stage's top; where the stage ends and the drop begins
GAP = 36                  # between the two panels
S = 2                     # the still parts are drawn at S x and scaled down (smooth edges)
Z = 880 / PW              # scene units -> pixels of the pictures
PAGE, SLAB, SLAB_TOP, LEG, LINE = "#0e0d11", "#262430", "#413e4b", "#1a1920", "#34313d"
PINK, TEAL, MINT, CREAM = "#ed1b76", "#1f8a5f", "#a8f0dc", "#f7ebc3"
HOLD, STEP, END = 900, 80, 2600  # ms: the first frame, every frame after it, the last
# The loop's clock, in frames after the first. Both panels run on it, so WIN and LOSE come up together.
PULL = 30             # 1 .. PULL: three heaves (above); the walk to the door and through it, the hand slipping (below)
SETTLE = PULL + 11    # .. SETTLE: the fourth comes up onto the stage and all four stand; the door shuts and the agent falls
WORD = SETTLE - 2     # from here the result fades in, over FADE frames
FADE = 6
LAST = SETTLE + 12    # .. LAST: the four hop, twice
_sprites: dict = {}


def open_face(im):
    """Redraw the kneeling pose's face in place: round eyes and a small open mouth, in the pose's own ink and screen white
    (its own half-closed eyes read as a sneer here). Done before the recolouring, which carries the ink to each colour."""
    d = ImageDraw.Draw(im)
    ink, white = im.getpixel((634, 548)), im.getpixel((736, 480))
    for box in ((582, 500, 690, 580), (786, 508, 892, 590), (690, 584, 786, 626)):
        d.rectangle(box, fill=white)
    for x, y in ((638, 544), (836, 552)):
        d.ellipse((x - 27, y - 27, x + 27, y + 27), fill=ink)
    d.ellipse((714, 590, 760, 626), fill=ink)


def sprite(pose=None, colour=None, height=300, flip=False, name=None, dim=1.0):
    """A sprite ``height`` scene units tall, in picture pixels: a finished one by ``name``, or the pose ``pose``
    recoloured to ``colour``. Kept, since the recolouring is slow."""
    key = (pose, colour, height, flip, name, dim)
    if key not in _sprites:
        if name:
            im = Image.open(KIT / "sprites" / f"{name}.png").convert("RGBA")
        else:
            src = Image.open(KIT / "poses" / f"{pose}_v1.png").convert("RGBA")
            if pose == "reach_down":
                open_face(src)
            im = Image.fromarray(recolor(np.array(src), TARGETS[colour], auto_head=True))
            im = im.crop(im.getchannel("A").point(lambda v: 255 if v > 8 else 0).getbbox())
        if flip:
            im = im.transpose(Image.FLIP_LEFT_RIGHT)
        if dim != 1.0:
            r, g, b, a = im.split()
            im = Image.merge("RGBA", (*ImageEnhance.Brightness(Image.merge("RGB", (r, g, b))).enhance(dim).split(), a))
        h = round(height * Z)
        _sprites[key] = im.resize((round(im.width * h / im.height), h), Image.LANCZOS)
    return _sprites[key]


def stand(cv, im, x, y=FLOOR, alpha=1.0, turn=0.0):
    """Paste ``im`` with its feet centred at (x, y) in scene units; ``alpha`` fades it, ``turn`` rotates it (degrees)."""
    if turn:
        im = im.rotate(turn, expand=True, resample=Image.BICUBIC)
    if alpha < 1.0:
        im = im.copy()
        im.putalpha(im.getchannel("A").point(lambda v: round(v * alpha)))
    left, top = round(x * Z - im.width / 2), round(y * Z - im.height)
    if left < 0 or top < 0:  # alpha_composite takes no negative destination: cut off what is outside
        im = im.crop((max(0, -left), max(0, -top), im.width, im.height))
        left, top = max(0, left), max(0, top)
    if left < cv.width and top < cv.height and im.width and im.height:
        cv.alpha_composite(im, (left, top))


def glow(cv, box, rgba, blur):
    layer = Image.new("RGBA", cv.size, (0, 0, 0, 0))
    ImageDraw.Draw(layer).ellipse([v * S for v in box], fill=rgba)
    cv.alpha_composite(layer.filter(ImageFilter.GaussianBlur(blur * S)))


def backdrop(base, door, light):
    """A panel without its agents, in picture pixels: the stage that ends at EDGE, the drop with spikes at its foot, and
    (``door``) the open EXIT door on the left. ``light``: (box, rgba) of the glow on the agents."""
    cv = Image.new("RGBA", (PW * S, PH * S), base)
    glow(cv, *light, 110)
    glow(cv, (EDGE - 20, FLOOR - 260, PW + 260, PH + 200), (0, 0, 0, 170), 70)      # the dark of the drop
    glow(cv, (EDGE - 60, PH - 150, PW + 200, PH + 240), (237, 27, 118, 120), 80)    # a red light from its foot
    d = ImageDraw.Draw(cv)
    for x in (300, EDGE - 210):
        d.rectangle((x * S, (FLOOR + 32) * S, (x + 60) * S, PH * S), fill=LEG)
    d.rectangle((0, FLOOR * S, EDGE * S, (FLOOR + 36) * S), fill=SLAB)
    d.rectangle((0, FLOOR * S, EDGE * S, (FLOOR + 7) * S), fill=SLAB_TOP)
    for i in range(5):  # warning stripes at the edge
        x = EDGE - 28 - i * 44
        d.polygon([(x * S, (FLOOR + 7) * S), ((x + 22) * S, (FLOOR + 7) * S), ((x + 6) * S, (FLOOR + 36) * S),
                   ((x - 16) * S, (FLOOR + 36) * S)], fill=PINK)
    for x in range(EDGE + 30, PW + 40, 58):  # spikes
        d.polygon([(x * S, PH * S), ((x + 29) * S, (PH - 62) * S), ((x + 58) * S, PH * S)], fill="#6b1233")
        d.polygon([((x + 29) * S, (PH - 62) * S), ((x + 58) * S, PH * S), ((x + 40) * S, PH * S)], fill="#8a1a44")
    if door:
        d.rectangle((72 * S, (FLOOR - 282) * S, 244 * S, FLOOR * S), fill="#3b3844")   # the frame
        d.rectangle((84 * S, (FLOOR - 270) * S, 232 * S, FLOOR * S), fill=CREAM)      # the light inside
        d.polygon([(232 * S, (FLOOR - 270) * S), (276 * S, (FLOOR - 252) * S), (276 * S, (FLOOR - 4) * S), (232 * S, FLOOR * S)], fill="#55515f")
        f = ImageFont.truetype(str(FONT), 34 * S)
        w = d.textlength("EXIT", font=f)
        d.rounded_rectangle((158 * S - w / 2 - 28, (FLOOR - 340) * S, 158 * S + w / 2 + 28, (FLOOR - 292) * S), radius=10 * S, fill=TEAL)
        d.text((158 * S, (FLOOR - 316) * S), "EXIT", font=f, fill="#ffffff", anchor="mm")
    return cv.resize((round(PW * Z), round(PH * Z)), Image.LANCZOS)


def tinted(back, colour, amount):
    """The backdrop under a result: a wash of the result's colour, ``amount`` 0 .. 1 (the agents keep their own colours)."""
    wash = Image.new("RGBA", back.size, colour)
    wash.putalpha(round(46 * amount))
    out = back.copy()
    out.alpha_composite(wash)
    return out


def verdict(cv, word, colour, amount):
    """The panel's result, large, above the heads, ``amount`` 0 .. 1 of the way in (it rises a little as it comes)."""
    f = ImageFont.truetype(str(FONT), round(92 * Z))
    layer = Image.new("RGBA", cv.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    x, y = (EDGE / 2 + 110) * Z, (60 + 14 * (1 - amount)) * Z
    d.text((x + 3, y + 4), word, font=f, fill="#0e0d11", anchor="mm")
    d.text((x, y), word, font=f, fill=colour, anchor="mm")
    layer.putalpha(layer.getchannel("A").point(lambda v: round(v * amount)))
    cv.alpha_composite(layer)


def ease(p):
    return 0.5 - 0.5 * math.cos(math.pi * max(0.0, min(1.0, p)))


def shown(t):
    """How far in the result is at frame ``t``: 0 .. 1."""
    return max(0.0, min(1.0, (t - WORD) / FADE))


def together(backs, t):
    """The upper panel at frame ``t``. ``backs``: its backdrop with no wash, half of it, all of it."""
    cv = backs[round(shown(t) * 2)].copy()
    # the pull: three heaves, each an effort (the chain leans back and gains ground) and a breath
    beat, into = divmod(min(t, PULL) - 1, 10) if t else (0, 0)
    effort = ease((into + 1) / 6) if t else 0.0
    p = (min(beat, 3) + effort) / 3 if t else 0.0
    lean = 5 * math.sin(math.pi * min(1.0, (into + 1) / 7)) if 0 < t <= PULL else 0.0
    dx = -52 * p
    ends = {"orange": 418 + dx, "blue": 586 + dx, "green": 756 + dx, "purple": 928 + dx}
    spots = {c: 326 + i * 162 for i, c in enumerate(("orange", "blue", "green", "purple"))}  # where the four end up
    if t <= PULL:
        stand(cv, sprite("climb", "purple", 300), ends["purple"], FLOOR + 174 - 150 * p, turn=-lean * 0.6)
        stand(cv, sprite("pull", "orange", 262, flip=True), ends["orange"], FLOOR + 6, turn=lean)
        stand(cv, sprite("pull", "blue", 262, flip=True), ends["blue"], FLOOR + 6, turn=lean)
        stand(cv, sprite("reach_down", "green", 270), ends["green"], FLOOR + 4)
    elif t <= PULL + 7:
        # over the edge: the three give ground, still holding on, and the fourth comes up onto the stage
        k = ease((t - PULL) / 7)
        at = {c: ends[c] + (spots[c] - ends[c]) * k for c in ends}
        stand(cv, sprite("climb", "purple", 300), at["purple"], FLOOR + 24 * (1 - k))
        stand(cv, sprite("pull", "orange", 262, flip=True), at["orange"], FLOOR + 6)
        stand(cv, sprite("pull", "blue", 262, flip=True), at["blue"], FLOOR + 6)
        stand(cv, sprite("reach_down", "green", 270), at["green"], FLOOR + 4)
    else:
        # all four stand, where they are; after a beat they hop, one after the other, twice
        hop = t - SETTLE
        for i, c in enumerate(("orange", "blue", "green", "purple")):
            up = -15 * abs(math.sin(math.pi * (hop - i * 0.9) / 6)) if i * 0.9 < hop <= i * 0.9 + 12 else 0.0
            stand(cv, sprite(name=f"stand_{c}", height=268), spots[c], FLOOR + up)
    if shown(t):
        verdict(cv, "WIN", MINT, shown(t))
    return cv


def alone(backs, t):
    """The lower panel at frame ``t``: one walks to the door and out, the hand at the edge slips, the door shuts, the
    agent falls."""
    cv = backs[round(shown(t) * 2)].copy()
    d = ImageDraw.Draw(cv)
    walk = min(t, PULL - 4) / (PULL - 4)                        # an even walk, 26 frames to the doorway
    walker_x = 560 - 410 * walk
    fade = max(0.0, min(1.0, (walker_x - 150) / 130))           # it fades as it passes into the light
    if fade > 0:
        stride = math.sin(math.pi * t / 3.5)
        stand(cv, sprite("walk", "blue", 280, flip=True), walker_x, FLOOR - 5 * abs(stride) if t else FLOOR, alpha=fade, turn=1.6 * stride if t else 0)
    shut = max(0.0, min(1.0, (t - (PULL - 3)) / 6))             # then the door swings shut, from the right
    if shut:
        d.rectangle(((232 - 148 * shut) * Z, (FLOOR - 270) * Z, 232 * Z, FLOOR * Z), fill="#2b2833")
    stand(cv, sprite(name="off", height=250, dim=0.85), 1152, PH - 26, turn=-104)   # one that fell before
    slip = ease(min(t, PULL) / PULL)
    tremble = 1.5 * math.sin(t * 2.4) if PULL * 0.55 < t <= PULL else 0.0
    if t <= PULL:
        stand(cv, sprite("climb", "purple", 300, dim=0.92), 932 + tremble, FLOOR + 150 + 34 * slip)
    else:
        k = t - PULL                                              # it falls, faster and faster, turning
        if k <= 9:
            stand(cv, sprite("climb", "purple", 300, dim=0.92), 932 + 4 * k, FLOOR + 184 + 7.5 * k * k, turn=-5 * k)
    if shown(t):
        verdict(cv, "LOSE", PINK, shown(t))
    return cv


def rounded(panel, radius=34):
    """The panel on the page's colour, with round corners and a thin outline."""
    mask = Image.new("L", (panel.width * 2, panel.height * 2), 0)
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, mask.width - 1, mask.height - 1), radius=radius * 2, fill=255)
    out = Image.new("RGBA", panel.size, PAGE)
    out.paste(panel, (0, 0), mask.resize(panel.size, Image.LANCZOS))
    line = Image.new("RGBA", (panel.width * 2, panel.height * 2), (0, 0, 0, 0))
    ImageDraw.Draw(line).rounded_rectangle((2, 2, line.width - 3, line.height - 3), radius=radius * 2, outline=LINE, width=4)
    out.alpha_composite(line.resize(panel.size, Image.LANCZOS))
    return out


def loop(tops, bottoms, frames):
    """The frames ``frames``, both panels on the page's colour."""
    w, h, gap = tops[0].width, tops[0].height, round(GAP * Z)
    out = []
    for t in frames:
        page = Image.new("RGBA", (w, h * 2 + gap), PAGE)
        page.alpha_composite(rounded(together(tops, t)), (0, 0))
        page.alpha_composite(rounded(alone(bottoms, t)), (0, h + gap))
        out.append(page.convert("RGB"))
    return out


def main():
    top = backdrop("#101716", door=False, light=((150, FLOOR - 470, 1030, FLOOR + 250), (127, 194, 177, 78)))
    bottom = backdrop("#150e13", door=True, light=((230, FLOOR - 400, 700, FLOOR + 120), (247, 235, 195, 26)))
    tops = [tinted(top, "#7fc2b1", i / 2) for i in range(3)]   # the wash comes in two steps (each repaints a whole panel)
    bottoms = [tinted(bottom, PINK, i / 2) for i in range(3)]
    ASSETS.mkdir(parents=True, exist_ok=True)
    loop(tops, bottoms, [LAST])[0].save(ASSETS / "hero-coexist.png", optimize=True)   # the still: the last frame, in full colour

    # The GIF: one palette for every frame, taken from three of them. The backdrops' soft lights are dithered once, to that
    # palette, and the agents are then set on top without dithering: the grain never moves, so each frame stores only
    # what changed.
    keys = loop(tops, bottoms, [0, PULL, LAST])
    sheet = Image.new("RGB", (keys[0].width, keys[0].height * 4), PAGE)
    for i, k in enumerate(keys):
        sheet.paste(k, (0, i * k.height))
    x = y = 0  # and every agent once more, large, so that their few colours weigh as much as the wide backdrops
    for im in _sprites.values():
        big = im.resize((im.width * 3 // 2, im.height * 3 // 2))
        if x + big.width > sheet.width:
            x, y = 0, y + 300
        sheet.paste(big, (x, keys[0].height * 3 + y), big)
        x += big.width
    pal = sheet.quantize(colors=255, method=Image.Quantize.MEDIANCUT, dither=Image.Dither.NONE)
    grain = lambda b: b.convert("RGB").quantize(palette=pal, dither=Image.Dither.FLOYDSTEINBERG).convert("RGBA")  # noqa: E731
    frames = [f.quantize(palette=pal, dither=Image.Dither.NONE) for f in loop([grain(b) for b in tops], [grain(b) for b in bottoms], range(LAST + 1))]
    times = [HOLD] + [STEP] * (LAST - 1) + [END]
    gif = ASSETS / "hero-coexist.gif"
    frames[0].save(gif, save_all=True, append_images=frames[1:], duration=times, loop=0, optimize=False, disposal=1)
    if shutil.which("gifsicle"):  # optional: stores only what changes between frames; a light lossy pass on top
        subprocess.run(["gifsicle", "-O3", "--lossy=20", "--batch", str(gif)], check=True)

    guard = Image.open(KIT / "sprites" / "guard_big.png").convert("RGBA")
    guard.thumbnail((440, 560), Image.LANCZOS)
    guard.save(ASSETS / "hero-guard.png", optimize=True)
    for name in ("hero-coexist.gif", "hero-coexist.png", "hero-guard.png"):
        print(name, (ASSETS / name).stat().st_size, Image.open(ASSETS / name).size)


if __name__ == "__main__":
    main()
