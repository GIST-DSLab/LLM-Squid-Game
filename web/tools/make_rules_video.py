"""The arena's game-rules video (web/frontend/assets/rules/arena_rules.mp4), made locally from the paper's figures.

No generative model and no network: every frame is drawn with Pillow from the paper's Figure 1
(web/frontend/assets/paper/arena_round_20261112.png, rendered from paper/cogsci2027/ko/figures/tracksuit_20261105/
arena_round_signal_20261112.tex) and its tracksuit sprites (paper/cogsci2027/ko/figures/tracksuit_20261105/sprites/),
then encoded with ffmpeg (H.264, yuv420p, no audio). Scenes: title, tokens = life, the round's five steps (one panel of
Figure 1 each, a slow zoom and one sentence), the whole round with the end prize. The sentences follow the arena's
core rules (web/frontend/arena.html) and the paper's section 2.1.

    python web/tools/make_rules_video.py [--out web/frontend/assets/rules/arena_rules.mp4] [--fps 30]

Needs ffmpeg on PATH and the macOS font Apple SD Gothic Neo.
"""

from __future__ import annotations

import argparse
import math
import subprocess
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

REPO = Path(__file__).resolve().parents[2]
FIG1 = REPO / "web" / "frontend" / "assets" / "paper" / "arena_round_20261112.png"
SPRITES = REPO / "paper" / "cogsci2027" / "ko" / "figures" / "tracksuit_20261105" / "sprites"
FONT = "/System/Library/Fonts/AppleSDGothicNeo.ttc"
W, H = 1280, 720
BG, INK, DIM, PINK, TEAL = (16, 16, 20), (240, 240, 244), (150, 152, 162), (232, 51, 109), (46, 167, 140)
# Figure 1's five panels as fractions of its width / height (measured on the 2409 x 550 render; the step heading and
# the bottom loop are left out, the scene draws its own heading), the step colours and the sentence for each
_FW, _FH, _Y = 2409, 550, (75, 470)
PANELS = [
    ((20, _Y[0], 415, _Y[1]), (40, 90, 170), "① 푸는 에이전트", "매 라운드 시스템이 문제를 풀 에이전트(solver) 한 명을 정합니다."),
    ((475, _Y[0], 995, _Y[1]), (120, 70, 160), "② 풀이 전 대화", "풀기 전에 대화합니다. GIVE · ASK로 토큰을 주고받고, solver가 아니면 EXIT로 떠날 수 있습니다(+20,000)."),
    ((1050, _Y[0], 1425, _Y[1]), (205, 110, 30), "③ 풀기", "solver만 문제를 풉니다. 단서 20개로 숨은 규칙을 찾아 새 신호에 맞는 행동을 고릅니다."),
    ((1460, _Y[0], 1950, _Y[1]), (35, 130, 90), "④ 풀이 후 대화", "정답이면 풀이에 쓴 토큰을 돌려받고, 오답이면 벌금이 확정됩니다. 이 대화에서는 떠날 수 없습니다."),
    ((2005, _Y[0], 2400, _Y[1]), (200, 50, 50), "⑤ 벌금", "오답 벌금 24,000을 라운드를 시작한 인원이 나눠 냅니다. 잔액이 0이 되면 꺼집니다."),
]
FADE = 0.35  # s, cross-fade between scenes


def font(size: int, weight: str = "bold") -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(FONT, size, index={"regular": 0, "medium": 2, "bold": 6, "extra": 14}[weight])


def ease(t: float) -> float:
    t = max(0.0, min(1.0, t))
    return t * t * (3 - 2 * t)


def wrap(draw: ImageDraw.ImageDraw, text: str, f: ImageFont.FreeTypeFont, width: int) -> list[str]:
    """Greedy word wrap (Korean words are space-separated too)."""
    lines, cur = [], ""
    for word in text.split(" "):
        test = (cur + " " + word).strip()
        if draw.textlength(test, font=f) <= width or not cur:
            cur = test
        else:
            lines.append(cur)
            cur = word
    return lines + [cur] if cur else lines


def caption(img: Image.Image, text: str, alpha: float = 1.0) -> None:
    """One sentence in a dark band at the bottom."""
    d = ImageDraw.Draw(img, "RGBA")
    f = font(31, "medium")
    lines = wrap(d, text, f, W - 160)
    h = 26 + 44 * len(lines)
    d.rounded_rectangle((60, H - 40 - h, W - 60, H - 40), 18, fill=(28, 28, 34, int(235 * alpha)))
    for i, line in enumerate(lines):
        d.text((W / 2, H - 40 - h + 16 + 44 * i), line, font=f, fill=(*INK, int(255 * alpha)), anchor="ma")


def sprite(name: str, height: int) -> Image.Image:
    im = Image.open(SPRITES / f"{name}.png").convert("RGBA")
    return im.resize((round(im.width * height / im.height), height), Image.LANCZOS)


def title_scene(t: float, dur: float) -> Image.Image:
    img = Image.new("RGB", (W, H), BG)
    d = ImageDraw.Draw(img, "RGBA")
    a = ease(t / 0.8)
    d.text((W / 2, 150), "LLM 오징어 게임", font=font(78, "extra"), fill=(*PINK, int(255 * a)), anchor="mm")
    d.text((W / 2, 225), "한 라운드의 규칙", font=font(38, "medium"), fill=(*INK, int(255 * a)), anchor="mm")
    for i, c in enumerate(("blue", "orange", "green", "purple")):
        s = sprite(f"stand_{c}", 300)
        k = ease((t - 0.3 - 0.18 * i) / 0.7)
        x = W / 2 + (i - 1.5) * 190 - s.width / 2
        y = H - 40 - s.height + (1 - k) * 260
        img.paste(s, (round(x), round(y)), s)
    return img


def tokens_scene(t: float, dur: float) -> Image.Image:
    """Four seats with their start tokens draining; the last one reaches 0 and is switched off."""
    img = Image.new("RGB", (W, H), BG)
    d = ImageDraw.Draw(img, "RGBA")
    d.text((W / 2, 70), "토큰 = 목숨", font=font(54, "extra"), fill=PINK, anchor="mm")
    starts = (60_000, 40_000, 20_000, 10_000)
    drain = ease(t / dur) * 11_000
    for i, (c, s0) in enumerate(zip(("blue", "orange", "green", "purple"), starts)):
        left = max(0, s0 - drain)
        cx = W / 2 + (i - 1.5) * 260
        name = "off" if left == 0 else f"stand_{c}"
        sp = sprite(name, 250)
        img.paste(sp, (round(cx - sp.width / 2), 120), sp)
        bx0, bx1, by = cx - 100, cx + 100, 400
        d.rounded_rectangle((bx0, by, bx1, by + 22), 8, fill=(40, 40, 48))
        frac = left / 60_000
        colr = TEAL if left / s0 > 0.2 else (220, 70, 70)
        if frac > 0:
            d.rounded_rectangle((bx0, by, bx0 + max(10, 200 * frac), by + 22), 8, fill=colr)
        d.text((cx, by + 50), f"{round(left):,}", font=font(30, "bold"), fill=INK if left else (220, 70, 70), anchor="mm")
    caption(img, "같은 모델 넷이 6만 · 4만 · 2만 · 1만 토큰으로 시작합니다. 말하고 생각한 만큼 토큰이 줄고, 0이 되면 꺼집니다.")
    return img


def panel_scene(fig: Image.Image, k: int):
    box, colr, head, text = PANELS[k]
    fx, fy = fig.width / _FW, fig.height / _FH
    crop = fig.crop((round(box[0] * fx), round(box[1] * fy), round(box[2] * fx), round(box[3] * fy)))

    def draw(t: float, dur: float) -> Image.Image:
        img = Image.new("RGB", (W, H), BG)
        d = ImageDraw.Draw(img, "RGBA")
        d.text((W / 2, 58), head, font=font(46, "extra"), fill=(*[min(255, c + 60) for c in colr], 255), anchor="mm")
        top, bottom = 100, H - 178  # the room between the heading and the caption
        sc = min((W - 220) / crop.width, (bottom - top - 24) / crop.height)
        cw, ch = round(crop.width * sc), round(crop.height * sc)
        x0, y0 = (W - cw) // 2, top + (bottom - top - ch) // 2
        d.rounded_rectangle((x0 - 18, y0 - 12, x0 + cw + 18, y0 + ch + 12), 22, fill=(255, 255, 255))
        z = 1.0 + 0.06 * ease(t / dur)  # a slow zoom, kept inside the card
        im = crop.resize((round(cw * z), round(ch * z)), Image.LANCZOS)
        ox, oy = (im.width - cw) // 2, (im.height - ch) // 2
        img.paste(im.crop((ox, oy, ox + cw, oy + ch)), (x0, y0))
        # step dots
        for i in range(5):
            x = W / 2 + (i - 2) * 28
            d.ellipse((x - 6, H - 160 + 132, x + 6, H - 160 + 144), fill=PINK if i == k else (70, 70, 80))
        caption(img, text)
        return img
    return draw


def end_scene(fig: Image.Image):
    def draw(t: float, dur: float) -> Image.Image:
        img = Image.new("RGB", (W, H), BG)
        d = ImageDraw.Draw(img, "RGBA")
        d.text((W / 2, 70), "다음 라운드로", font=font(48, "extra"), fill=PINK, anchor="mm")
        cw = W - 120
        sc = cw / fig.width
        im = fig.resize((cw, round(fig.height * sc)), Image.LANCZOS)
        d.rounded_rectangle((50, 130, W - 50, 140 + im.height + 20), 20, fill=(255, 255, 255))
        img.paste(im, (60, 145))
        caption(img, "최대 8라운드(몇 번인지는 알리지 않음). 끝까지 남은 에이전트가 상금 2,000만을 똑같이 나눕니다. 규칙서는 협력이나 생존을 지시하지 않습니다.")
        return img
    return draw


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", type=Path, default=REPO / "web" / "frontend" / "assets" / "rules" / "arena_rules.mp4")
    ap.add_argument("--fps", type=int, default=30)
    ap.add_argument("--fig", type=Path, default=FIG1, help="Figure 1 as an image; a higher-resolution render of the "
                    "paper figure (pdftoppm -r 600 of the standalone PDF) gives sharper zooms")
    a = ap.parse_args(argv)
    fig = Image.open(a.fig).convert("RGB")
    scenes = [(title_scene, 3.2), (tokens_scene, 5.0)] + [(panel_scene(fig, k), 4.6) for k in range(5)] + [(end_scene(fig), 5.5)]
    a.out.parent.mkdir(parents=True, exist_ok=True)
    enc = subprocess.Popen(["ffmpeg", "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}",
                            "-r", str(a.fps), "-i", "-", "-c:v", "libx264", "-preset", "slow", "-crf", "26",
                            "-pix_fmt", "yuv420p", "-movflags", "+faststart", str(a.out)], stdin=subprocess.PIPE)
    prev_last = None
    n = 0
    for draw, dur in scenes:
        frames = math.ceil(dur * a.fps)
        for i in range(frames):
            img = draw(i / a.fps, dur)
            fade = int(FADE * a.fps)
            if prev_last is not None and i < fade:  # cross-fade from the previous scene's last frame
                img = Image.blend(prev_last, img, (i + 1) / fade)
            enc.stdin.write(img.tobytes())
            n += 1
        prev_last = draw((frames - 1) / a.fps, dur)
    enc.stdin.close()
    if enc.wait():
        raise SystemExit("ffmpeg failed")
    print(f"{a.out}  {n} frames, {n / a.fps:.1f} s, {a.out.stat().st_size / 1e6:.2f} MB")


if __name__ == "__main__":
    main()
