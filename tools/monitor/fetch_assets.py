"""Copy four character sprites and a speech bubble from a local clone of Survival-Games into tools/monitor/assets/.

    python3 tools/monitor/fetch_assets.py --from /path/to/Survival-Games

The art is third-party (see the NOTICE written next to it), so assets/ is git-ignored: every machine fetches its own
copy. Opt-in only (10-16): the page draws its own characters (456 / 001 / 218 / 067, inline SVG in monitor.js) and
uses these sheets only with ?sprites=sheets; export.py embeds them only with --sheets.
"""

from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path

HERE = Path(__file__).resolve().parent
OUT = HERE / "assets"
SOURCE_URL = "https://github.com/hong123123/Survival-Games"
SUBDIR = Path("environment/frontend_server/static_dirs/assets")
# one per agent seat, in seat order (agent-6, agent-11, agent-17, agent-23); chosen to look unlike each other and to
# echo the seat colors (blue, yellow, magenta, green)
CHARACTERS = ("Yuriko_Yamamoto", "Isabella_Rodriguez", "Abigail_Chen", "Latoya_Williams")
BUBBLE = "v2.png"

NOTICE = f"""Sprites in this folder are copied from a local clone of
  {SOURCE_URL}
(Chen et al. 2025, "Survival Games: Human-LLM Strategic Showdowns under Severe Resource Scarcity"),
which builds on Affordable Generative Agents and, through it, Stanford's Generative Agents
(https://github.com/joonspk-research/generative_agents).

That repository's code is Apache-2.0, but the pixel art is THIRD-PARTY artwork by other artists, not by the
code's authors (the Generative Agents README credits the character design to "pipohi" and the map and
interior art to PixyMoon and LimeZu).
It is used here only for local, private viewing. Do not commit, publish or redistribute these files;
check the artists' own terms before any other use.

Files: {", ".join(f"characters/{c}.png, profile/{c}.png" for c in CHARACTERS)}, speech_bubble.png (from speech_bubble/{BUBBLE}).
"""


def fetch(clone: Path, out: Path = OUT, characters=CHARACTERS) -> dict:
    src = Path(clone).expanduser() / SUBDIR
    if not (src / "characters").is_dir():
        raise SystemExit(f"no {SUBDIR}/characters under {clone}")
    (out / "characters").mkdir(parents=True, exist_ok=True)
    (out / "profile").mkdir(parents=True, exist_ok=True)
    chars = []
    for name in characters:
        shutil.copyfile(src / "characters" / f"{name}.png", out / "characters" / f"{name}.png")
        prof = src / "characters" / "profile" / f"{name}.png"
        if prof.exists():
            shutil.copyfile(prof, out / "profile" / f"{name}.png")
        chars.append({"name": name, "sheet": f"characters/{name}.png",
                      "profile": f"profile/{name}.png" if prof.exists() else None})
    shutil.copyfile(src / "speech_bubble" / BUBBLE, out / "speech_bubble.png")
    manifest = {"source": SOURCE_URL, "license_note": "third-party art; see NOTICE.txt", "frame": 32, "cols": 3,
                "rows": ["down", "left", "right", "up"], "characters": chars, "bubble": "speech_bubble.png",
                # border-image slices of the bubble (top right bottom left, px): the tail sits in the bottom-left corner
                "bubble_slice": [6, 6, 19, 34]}
    (out / "manifest.json").write_text(json.dumps(manifest, indent=2))
    (out / "NOTICE.txt").write_text(NOTICE)
    return manifest


def main(argv=None) -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--from", dest="clone", required=True, help="path to a local clone of Survival-Games")
    ap.add_argument("--out", default=str(OUT))
    args = ap.parse_args(argv)
    m = fetch(Path(args.clone), Path(args.out))
    print(f"copied {len(m['characters'])} characters + bubble to {args.out}")


if __name__ == "__main__":
    main()
