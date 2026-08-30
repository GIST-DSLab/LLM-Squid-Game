# scripts/render/

Rendering a stored Excalidraw diagram to an image — run by hand, not part
of the experiment or analysis pipelines. Not a package (no `__init__.py`):
nothing imports these modules from elsewhere in the tree.

- `render_excalidraw.py` — renders Excalidraw JSON to PNG via Playwright +
  headless Chromium, using `render_template.html` as the HTML shell it
  screenshots.
- `render_template.html` — the HTML template `render_excalidraw.py` fills
  in and loads in the headless browser; not a script itself.
