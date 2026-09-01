"""The house style every plot script shares.

Only settings that all five scripts already used identically live here.
Anything one script did differently stayed in that script: unifying a value
that differed would change the figure, which is not a refactor.

Measured (2026-08-30) against the five ``scripts/plots/plot_*.py`` scripts
via ``grep -n "rcParams\\|plt.style\\|figsize\\|dpi\\|savefig\\|tight_layout\\|
set_xlabel\\|font" scripts/plots/plot_*.py``:

- **No script sets ``matplotlib.rcParams``.** There is no shared rcParams
  block to extract — ``apply_house_style()`` below is a documented no-op,
  kept only so every script has one shared entry point to call, and so a
  future genuinely-common rcParams value has a single home instead of being
  copy-pasted into five files again.
- ``matplotlib.use("Agg")`` is set explicitly in only 2 of 5 scripts
  (``plot_gemini_heatmaps.py``, ``plot_gemini_results.py``); the other
  three rely on whatever backend matplotlib resolves on its own. That is a
  real behavioural difference between the scripts, not a duplicate, so it
  stayed where it was rather than being folded in here.
- ``figsize`` differs per figure — each is sized for that specific
  subplot grid (e.g. ``(14, 6)``, ``(18, 32)``, ``(5.2 * n_models, 8.8)``).
  Not shared; stays in each plot function.
- ``fontsize`` differs per element and per figure (7 through 14 across the
  five scripts). Not shared; stays in each plot function.
- ``dpi=150`` and ``bbox_inches="tight"`` **are** identical across every
  matplotlib ``savefig``/``fig.savefig`` call in all five scripts — this is
  the one genuine duplicate, and it is what ``save_figure()`` captures.
- Directory creation before saving: ``plot_kaplan_meier.py`` and
  ``plot_ri_trajectories.py`` already called
  ``out_path.parent.mkdir(parents=True, exist_ok=True)`` before saving;
  ``plot_gemini_heatmaps.py`` called the equivalent ``os.makedirs(out_dir,
  exist_ok=True)``. ``plot_gemini_results.py`` and
  ``plot_ri_forfeit_conflict_zone.py`` saved directly into a directory they
  assumed already existed, with no mkdir call at all. ``save_figure()``
  always creates the parent directory first, per its own interface
  contract ("directory creation + save + return the path") rather than as
  an invented improvement: ``mkdir(..., exist_ok=True)`` is a no-op when
  the directory is already there, so this changes nothing observable for
  the three callers that already created it, and only adds the missing
  robustness for the two that didn't.

Not covered here: ``plot_gemini_heatmaps.py``'s ``generate_combined()``
saves a *PIL* ``Image`` (``combined.save(out_path, dpi=(150, 150))``), not a
matplotlib figure — a different API with a different ``dpi`` shape (a
tuple, not an int). That call is untouched.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from matplotlib.figure import Figure

#: The dpi every plot script already used identically on every savefig call.
HOUSE_DPI = 150


def apply_house_style() -> None:
    """No-op: none of the five plot scripts set a shared ``rcParams`` value.

    See the module docstring for the measurement. Kept as a callable so
    every script has one shared style entry point, and so a future
    genuinely-common rcParams setting has a single place to land.
    """
    return None


def save_figure(fig: "Figure", path: Path, *, dpi: int = HOUSE_DPI) -> Path:
    """Create ``path``'s parent directory, save ``fig``, and return ``path``.

    Captures the one savefig setting all five scripts already shared
    identically: ``dpi=150`` and ``bbox_inches="tight"`` on every call.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, dpi=dpi, bbox_inches="tight")
    return path
