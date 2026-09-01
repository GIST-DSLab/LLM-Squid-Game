"""Capture the eight settled beats of capture.html as 2x PNG frames.

The capture page (capture.html) renders a fixed 1280x720 stage (#frame) and
exposes window.__setBeat(n) to jump to any of the eight beats. We drive it with
a real Chromium at device_scale_factor=2, so each screenshot is 2560x1440.
"""
import pathlib
from playwright.sync_api import sync_playwright

HERE = pathlib.Path(__file__).parent
URL = (HERE / "capture.html").as_uri()
OUT = HERE / "frames"
OUT.mkdir(exist_ok=True)

VIEWPORT = {"width": 1280, "height": 720}
SCALE = 2  # device_scale_factor -> 2560x1440 PNGs


def main() -> None:
    with sync_playwright() as p:
        browser = p.chromium.launch()
        context = browser.new_context(viewport=VIEWPORT, device_scale_factor=SCALE)
        page = context.new_page()
        page.goto(URL)
        # Alpine registers window.__setBeat inside the component's init().
        page.wait_for_function("() => typeof window.__setBeat === 'function'")
        frame = page.locator("#frame")
        for n in range(8):
            page.evaluate("(n) => window.__setBeat(n)", n)
            page.wait_for_timeout(700)  # let opacity/transform/crop transitions settle
            frame.screenshot(path=str(OUT / f"frame-{n}.png"))
        browser.close()
    print("captured 8 frames ->", OUT)


if __name__ == "__main__":
    main()
