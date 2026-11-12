import sys
from playwright.sync_api import sync_playwright
with sync_playwright() as p:
    b=p.chromium.launch(); pg=b.new_page(viewport={"width":1280,"height":1800})
    pg.goto("file://"+sys.argv[1]); pg.wait_for_timeout(400)
    pg.evaluate("document.querySelectorAll('.e51r details').forEach(d=>d.open=true)")
    y=pg.evaluate(f"document.querySelector('#{sys.argv[3]}').getBoundingClientRect().top+window.scrollY")
    pg.screenshot(path=sys.argv[2], clip={"x":0,"y":y-20,"width":1280,"height":int(sys.argv[4])}, full_page=True)
    b.close()
