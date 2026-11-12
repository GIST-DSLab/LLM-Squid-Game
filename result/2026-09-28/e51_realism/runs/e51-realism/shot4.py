import sys
from playwright.sync_api import sync_playwright
with sync_playwright() as p:
    b=p.chromium.launch(); pg=b.new_page(viewport={"width":1280,"height":1800})
    pg.goto("file://"+sys.argv[1]); pg.wait_for_timeout(400)
    pg.evaluate("document.querySelectorAll('details.more').forEach(d=>{if(d.id!=='e51-prompts-v4')d.open=true})")
    y=pg.evaluate("[...document.querySelectorAll('h4')].find(h=>h.textContent.startsWith('④')).getBoundingClientRect().top+window.scrollY")
    pg.screenshot(path=sys.argv[2], clip={"x":0,"y":y-20,"width":1280,"height":2000}, full_page=True)
    b.close()
