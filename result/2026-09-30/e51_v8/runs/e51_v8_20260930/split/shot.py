import os, sys
from playwright.sync_api import sync_playwright
with sync_playwright() as pw:
    b = pw.chromium.launch(); pg = b.new_page(viewport={"width": 1280, "height": 900})
    pg.goto("file://" + os.path.abspath(sys.argv[1])); pg.wait_for_timeout(600)
    pg.screenshot(path=sys.argv[2], full_page=True); b.close()
