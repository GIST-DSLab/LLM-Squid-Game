import sys
from playwright.sync_api import sync_playwright
with sync_playwright() as p:
    b=p.chromium.launch(); pg=b.new_page(viewport={"width":1280,"height":1800})
    pg.goto("file://"+sys.argv[1]); pg.wait_for_timeout(500)
    el=pg.locator("#e51-real"); el.scroll_into_view_if_needed()
    y=pg.evaluate("document.querySelector('#e51-real').getBoundingClientRect().top+window.scrollY")
    pg.screenshot(path=sys.argv[2], clip={"x":0,"y":y-20,"width":1280,"height":int(sys.argv[3]) if len(sys.argv)>3 else 1800}, full_page=True)
    b.close()
