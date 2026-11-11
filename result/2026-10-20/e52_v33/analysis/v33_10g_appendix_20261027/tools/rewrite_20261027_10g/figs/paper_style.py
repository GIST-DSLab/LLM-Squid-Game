"""One style for every data figure in the paper.

Canvas size = printed size (no tight bbox), 8 pt body, one Korean sans for all text,
and one meaning per colour across the paper.
"""
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import os
from matplotlib import font_manager as fm

for f in ("/usr/share/fonts/truetype/nanum/NanumBarunGothic.ttf", "/usr/share/fonts/truetype/nanum/NanumBarunGothicBold.ttf"):
    if os.path.exists(f): fm.fontManager.addfont(f)  # Linux build box; on a Mac the family list below falls back

C = {
    "finish": "#9CC0E0",   # stayed to the end
    "exit": "#D9772B",     # left with the sure payout
    "dead": "#3C3C3C",     # shut down
    "help": "#2F6DB0",     # tokens given / received
    "ink": "#222222",
    "grid": "#E6E6E6",
    "muted": "#B5B5B5",
}
COL1, COL2 = 3.35, 7.0   # CogSci single / double column width (in)


def use():
    plt.rcParams.update({
        "font.family": ["NanumBarunGothic", "Apple SD Gothic Neo", "AppleGothic"], "axes.unicode_minus": False,
        "font.size": 8, "axes.labelsize": 8, "xtick.labelsize": 7.5, "ytick.labelsize": 7.5, "legend.fontsize": 7.5,
        "axes.titlesize": 8.5, "axes.titleweight": "bold", "axes.titlelocation": "left", "axes.titlepad": 6,
        "axes.spines.top": False, "axes.spines.right": False, "axes.linewidth": 0.7, "axes.edgecolor": C["ink"],
        "xtick.major.width": 0.7, "ytick.major.width": 0.7, "xtick.major.size": 2.5, "ytick.major.size": 2.5,
        "axes.grid": False, "grid.color": C["grid"], "grid.linewidth": 0.6,
        "legend.frameon": False, "savefig.dpi": 300, "figure.facecolor": "white",
    })


def save(fig, path):
    for ext in ("pdf", "png"):
        fig.savefig(f"{path}.{ext}")
