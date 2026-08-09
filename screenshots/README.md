# screenshots/

Scratch space for ad-hoc UI captures and one-off review pages (Playwright
screenshots of the Web Arena, design-review HTML dumps, before/after shots
used while iterating on `web/`).

Everything in here except this README is git-ignored (`.gitignore`:
`/screenshots/*`). Nothing in the build, the paper, or the deployed site reads
from this directory — delete its contents freely.

Figures that a document or a script actually depends on do **not** belong here;
they live in `figures/` (paper figures, sprite sources) or `web/assets/`
(assets served by the deployed frontend).
