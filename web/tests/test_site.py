"""The site as a whole, over whichever page folders exist (web/pages/*): the app boots, every page loads, and every
page's top bar links the game log and the leaderboard (a link whose page is gone hides itself: web/shared/site-lang.js)."""

from __future__ import annotations

from web.server.app import PAGES


def test_every_page_loads_and_links_the_others(client):
    assert client.get("/api/health").status_code == 200
    pages = [h for h in sorted(PAGES.glob("*/static/*.html")) if 'http-equiv="refresh"' not in h.read_text()]  # not redirects
    for page in (h.name for h in pages):
        r = client.get(f"/{page}")
        assert r.status_code == 200 and client.head(f"/{page}").status_code == 200, page
        assert 'data-api-href="monitor/"' in r.text and 'href="leaderboard.html"' in r.text, page
    assert client.head("/no-such-page.html").status_code == 404  # what makes a link to a deleted page hide
