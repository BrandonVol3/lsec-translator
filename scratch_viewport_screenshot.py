import os
from playwright.sync_api import sync_playwright

STUDIO_URL = "http://127.0.0.1:8000/studio"
OUT_IMG = r"C:\Users\brana\.gemini\antigravity-ide\brain\b7375b40-da4b-491e-a7d2-c71cf2439bdb\vrm_canvas_viewport_verified.png"

with sync_playwright() as p:
    browser = p.chromium.launch(
        headless=True,
        args=["--use-gl=angle", "--use-angle=swiftshader", "--enable-webgl", "--ignore-gpu-blocklist"]
    )
    page = browser.new_page(viewport={"width": 1440, "height": 900})
    page.goto(STUDIO_URL, wait_until="domcontentloaded")
    page.click("#tab-btn-side-avatar")
    page.wait_for_selector("#avatar-model-source-info:has-text('VRM 1.0')", timeout=15000)

    page.select_option("#select-avatar-clip", "SALUDAR_DEMO")
    page.click("#btn-avatar-play")
    page.wait_for_timeout(800)

    # Screenshot the viewport container directly
    page.locator("#avatar-viewport-wrap").screenshot(path=OUT_IMG)
    print("Viewport screenshot saved.")
    browser.close()
