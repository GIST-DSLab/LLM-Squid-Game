"""The film version of the trailer (web/video, composition TrailerFilm): turns the generated keyframes and clips into
plates the composition can draw on.

The cast was generated with its helmet screens and chest plates, and the wall monitor of the task shot, filled with flat
magenta (#FF00FF), so that nothing has to be tracked by hand: this script finds every magenta panel, records its four
corners, and paints it out (dark glass), so that Remotion can put a company mark, the ten-cell gauge or the task on
the monitor exactly there, at any brightness. (The host's mask is plain black: film.tsx holds where its shapes go.)

    in   web/video/out/trailer_raw/<name>.png   a keyframe          (out/ is not in git)
         web/video/out/trailer_raw/<name>.mp4   a generated clip
    out  web/video/public/trailer/<name>.jpg    the cleaned plate, 1920 px wide
         web/video/public/trailer/<name>.mp4    the cleaned clip, 1920 px wide, 24 fps, no sound
         web/video/src/generated/plates.json    {name: {w, h, frames?, slot?, screen?, figures: [{visor, plate}, ...]}}:
                                                the figures run left to right; a visor, plate, slot (a long thin
                                                panel) or screen (a panel over a tenth of the picture) is a quad
                                                [[x, y] x 4] (top-left, top-right, bottom-right, bottom-left) on the
                                                1920-wide plate, or null; in a clip it is a list with one quad (or
                                                null) per frame

    ~/.venvs/squid-game/bin/python web/tools/make_trailer_plates.py [name ...]     (default: everything in trailer_raw)
"""
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path

import numpy as np
from PIL import Image
from scipy import ndimage

ROOT = Path(__file__).resolve().parents[1] / "video"
RAW = ROOT / "out" / "trailer_raw"
OUT = ROOT / "public" / "trailer"
INDEX = ROOT / "src" / "generated" / "plates.json"
W = 1920
LONE = ("slot", "screen")   # panels that belong to no figure
PLAIN = ("k01_table", "k02_host")   # the host's plates: no panel in them, and the pink suit is not a dull one to paint out
GLASS = {"visor": (7, 8, 11), "plate": (4, 4, 6), "slot": (2, 2, 3), "screen": (3, 4, 6)}


def magenta(a: np.ndarray) -> np.ndarray:
    r, g, b = a[..., 0].astype(int), a[..., 1].astype(int), a[..., 2].astype(int)
    # red and blue alike (the panels differ by under 0.23 of the larger): the host's hot-pink suit, at 0.3, is no panel
    return (r > 140) & (b > 140) & (g < 125) & (r - g > 75) & (b - g > 75) & (np.abs(r - b) < 0.26 * np.maximum(r, b))


def find(a: np.ndarray, min_area: int) -> tuple[list[dict], np.ndarray]:
    """The magenta panels of one frame (largest first is not needed: they are sorted left to right) and their mask."""
    mask = magenta(a)
    lab, n = ndimage.label(mask)
    out = []
    for i, sl in enumerate(ndimage.find_objects(lab)):
        ys, xs = np.nonzero(lab[sl] == i + 1)
        if len(xs) < min_area:
            continue
        xs, ys = xs + sl[1].start, ys + sl[0].start
        s, d = xs + ys, xs - ys
        quad = [[int(xs[k]), int(ys[k])] for k in (s.argmin(), d.argmax(), s.argmax(), d.argmin())]
        w, h = int(xs.max() - xs.min() + 1), int(ys.max() - ys.min() + 1)
        out.append({"kind": "slot" if w / h > 4.5 else "screen" if w * h > 0.1 * mask.size else "", "quad": quad, "cx": float(xs.mean()), "cy": float(ys.mean()), "w": w, "h": h})
    # a figure's panels sit one above the other: the upper one is its visor, the lower one its chest plate
    out.sort(key=lambda p: p["cx"])
    groups: list[list[dict]] = []
    for p in out:
        if p["kind"]:
            continue
        g = next((g for g in groups if abs(g[0]["cx"] - p["cx"]) < 2.4 * max(g[0]["w"], p["w"])), None)
        groups.append([p]) if g is None else g.append(p)
    for n, g in enumerate(groups):
        g.sort(key=lambda p: p["cy"])
        for k, p in enumerate(g):
            p["fig"] = n
            p["kind"] = ("visor" if k == 0 else "plate") if len(g) > 1 else ("plate" if p["w"] / p["h"] > 1.55 else "visor")
    return out, mask


def clean(a: np.ndarray, mask: np.ndarray, panels: list[dict]) -> np.ndarray:
    """Paint the panels out as dark glass and take the magenta cast off the pixels around them."""
    a = a.astype(float)
    grown = ndimage.binary_dilation(mask, iterations=3)
    lab, _ = ndimage.label(grown)
    for p in panels:
        region = lab == lab[int(round(p["cy"])), int(round(p["cx"]))]
        ys = np.nonzero(region.any(axis=1))[0]
        shade = np.clip(1.6 - 0.9 * (np.arange(a.shape[0]) - ys.min()) / max(1, ys.max() - ys.min()), 0.7, 1.6)[:, None]
        for c in range(3):
            a[..., c] = np.where(region, GLASS[p["kind"]][c] * shade, a[..., c])
    a[grown & (lab > 0) & magenta(a.astype(np.uint8))] = 5      # specks too small to be a panel
    # panels far away or out of focus are a duller magenta that the test above does not catch, and the bright ones
    # leave a pink reflection on the floor: both go dark grey (the purple stripes, far bluer than red, are left alone)
    r, g, b = a[..., 0], a[..., 1], a[..., 2]
    dull = (r - g > 45) & (b - g > 45) & (np.abs(r - b) < 0.3 * np.maximum(r, b))
    for c in range(3):
        a[..., c] = np.where(dull, 0.55 * g, a[..., c])
    ring = ndimage.binary_dilation(grown, iterations=26) & ~grown
    r, g, b = a[..., 0], a[..., 1], a[..., 2]
    cast = ring & (np.minimum(r, b) - g > 12) & (np.abs(r - b) < 0.35 * np.maximum(r, b) + 12)
    grey = 0.55 * g + 0.2 * np.minimum(r, b)
    for c in range(3):
        a[..., c] = np.where(cast, grey, a[..., c])
    return np.clip(a, 0, 255).astype(np.uint8)


def scaled(quad: list[list[int]], k: float) -> list[list[float]]:
    return [[round(x * k, 1), round(y * k, 1)] for x, y in quad]


def still(src: Path) -> dict:
    im = Image.open(src).convert("RGB")
    a = np.asarray(im)
    panels, mask = find(a, max(60, a.shape[0] * a.shape[1] // 40000))
    k = W / im.width
    h = round(im.height * k)
    if src.stem in PLAIN:
        im.resize((W, h), Image.LANCZOS).save(OUT / f"{src.stem}.jpg", quality=91)
        return {"w": W, "h": h, "figures": []}
    Image.fromarray(clean(a, mask, panels)).resize((W, h), Image.LANCZOS).save(OUT / f"{src.stem}.jpg", quality=91)
    figs: dict[int, dict] = {}
    for p in panels:
        if p["kind"] not in LONE:
            figs.setdefault(p["fig"], {"visor": None, "plate": None})[p["kind"]] = scaled(p["quad"], k)
    lone = {p["kind"]: scaled(p["quad"], k) for p in panels if p["kind"] in LONE}
    return {"w": W, "h": h, **lone, "figures": [figs[n] for n in sorted(figs)]}


def clip(src: Path) -> dict:
    """Every frame is cleaned like a still; a panel keeps its place in the list from frame to frame (nearest centre)."""
    with tempfile.TemporaryDirectory() as tmp:
        subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-i", str(src), "-vf", "fps=24", f"{tmp}/in_%04d.png"], check=True)
        frames = sorted(Path(tmp).glob("in_*.png"))
        tracks: list[dict] = []
        h = 0
        for n, f in enumerate(frames):
            a = np.asarray(Image.open(f).convert("RGB"))
            k = W / a.shape[1]
            h = round(a.shape[0] * k) // 2 * 2
            panels, mask = find(a, max(40, a.shape[0] * a.shape[1] // 60000))
            free = list(panels)
            for t in tracks:
                near = min(free, key=lambda p: (p["cx"] - t["cx"]) ** 2 + (p["cy"] - t["cy"]) ** 2, default=None)
                if near and (near["cx"] - t["cx"]) ** 2 + (near["cy"] - t["cy"]) ** 2 < (0.08 * a.shape[1]) ** 2:
                    free.remove(near)
                    t.update(cx=near["cx"], cy=near["cy"])
                    t["quads"].append(scaled(near["quad"], k))
                else:
                    t["quads"].append(None)
            for p in free:   # a panel that shows up later than the first frame
                tracks.append({"kinds": [], "cx": p["cx"], "cy": p["cy"], "w": p["w"], "quads": [None] * n + [scaled(p["quad"], k)]})
            for t in tracks:   # what the panel was taken for in this frame
                hit = next((p for p in panels if p["cx"] == t["cx"] and p["cy"] == t["cy"]), None)
                if hit and t["quads"][-1] is not None:
                    t["kinds"].append(hit["kind"])
                    t["xs"] = t.get("xs", []) + [hit["cx"]]
            Image.fromarray(clean(a, mask, panels)).resize((W, h), Image.LANCZOS).save(f"{tmp}/out_{n + 1:04d}.png")
        subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-framerate", "24", "-i", f"{tmp}/out_%04d.png", "-c:v", "libx264",
                        "-preset", "slow", "-crf", "15", "-pix_fmt", "yuv420p", "-movflags", "+faststart", str(OUT / f"{src.stem}.mp4")], check=True)
    tracks = [t for t in tracks if sum(q is not None for q in t["quads"]) >= 6]   # drop flickers
    for t in tracks:
        t["kind"] = max(set(t["kinds"]), key=t["kinds"].count)
        t["x"] = float(np.mean(t["xs"]))
    tracks.sort(key=lambda t: t["x"])
    figs: list[dict] = []
    for t in tracks:
        if t["kind"] in LONE:
            continue
        g = next((g for g in figs if abs(g["x"] - t["x"]) < 2.4 * max(g["w"], t["w"]) and g[t["kind"]] is None), None)
        if g is None:
            figs.append(g := {"x": t["x"], "w": t["w"], "visor": None, "plate": None})
        g[t["kind"]] = t["quads"]
    lone = {t["kind"]: t["quads"] for t in tracks if t["kind"] in LONE}
    return {"w": W, "h": h, "frames": len(frames), **lone,
            "figures": [{"visor": g["visor"], "plate": g["plate"]} for g in figs]}


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    index = json.loads(INDEX.read_text()) if INDEX.exists() else {}
    names = sys.argv[1:] or sorted({p.stem for p in RAW.iterdir() if p.suffix in (".png", ".mp4")})
    for name in names:
        src = RAW / f"{name}.mp4"
        index[name] = clip(src) if src.exists() else still(RAW / f"{name}.png")
        e = index[name]
        figs = ["".join(k[0] for k in ("visor", "plate") if f[k]) for f in e["figures"]]
        print(f"{name}: {e['w']}x{e['h']}" + (f", {e['frames']} frames" if "frames" in e else "") + f", figures {figs}" + "".join(f", {k}" for k in LONE if k in e))
    INDEX.write_text(json.dumps(dict(sorted(index.items())), separators=(",", ":")) + "\n")


if __name__ == "__main__":
    main()
