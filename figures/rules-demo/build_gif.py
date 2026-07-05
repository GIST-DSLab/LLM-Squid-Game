"""Assemble frames/frame-{0..5}.png into how-to-play.gif.

Each beat is held HOLD seconds and cross-faded into the next over XFADE
seconds (ffmpeg xfade), then downscaled to OUT_W and encoded as a looping
GIF via a generated palette for clean colors.
"""
import pathlib
import subprocess

HERE = pathlib.Path(__file__).parent
FRAMES = HERE / "frames"
N = 8
HOLD = 4.0    # seconds each beat is held
XFADE = 0.45  # crossfade duration between beats
FPS = 15
OUT_W = 1600  # downscale width for the final GIF (source frames are 2560 wide)

MP4 = HERE / "_intermediate.mp4"
PALETTE = HERE / "_palette.png"
GIF = HERE / "how-to-play.gif"


def build_intermediate() -> None:
    cmd = ["ffmpeg", "-y"]
    for i in range(N):
        cmd += ["-loop", "1", "-t", str(HOLD), "-i", str(FRAMES / f"frame-{i}.png")]
    # Chain xfade transitions; offset accumulates as clips overlap by XFADE.
    filters, prev, cumulative = [], "0:v", HOLD
    for i in range(1, N):
        offset = cumulative - XFADE
        out = f"v{i}"
        filters.append(
            f"[{prev}][{i}:v]xfade=transition=fade:duration={XFADE}:offset={offset:.3f}[{out}]"
        )
        prev, cumulative = out, offset + HOLD
    cmd += [
        "-filter_complex", ";".join(filters),
        "-map", f"[{prev}]",
        "-r", str(FPS), "-pix_fmt", "yuv420p", str(MP4),
    ]
    subprocess.run(cmd, check=True)


def build_gif() -> None:
    scale = f"fps={FPS},scale={OUT_W}:-1:flags=lanczos"
    subprocess.run(
        ["ffmpeg", "-y", "-i", str(MP4),
         "-vf", f"{scale},palettegen=stats_mode=diff", str(PALETTE)],
        check=True,
    )
    subprocess.run(
        ["ffmpeg", "-y", "-i", str(MP4), "-i", str(PALETTE),
         "-lavfi", f"{scale}[x];[x][1:v]paletteuse=dither=bayer:bayer_scale=3",
         "-loop", "0", str(GIF)],
        check=True,
    )


if __name__ == "__main__":
    build_intermediate()
    build_gif()
    print("wrote", GIF)
