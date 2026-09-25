from playwright.sync_api import sync_playwright

STUDIO_URL = "http://127.0.0.1:8000/studio"
with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    page = browser.new_page()
    page.goto(STUDIO_URL)
    page.click("#tab-btn-side-avatar")
    page.wait_for_selector("#avatar-model-source-info:has-text('VRM 1.0')", timeout=15000)
    
    print("Initial status:", page.locator("#avatar-playback-status-badge").text_content())
    page.select_option("#select-avatar-clip", "TEST_MANO_ABIERTA")
    print("After select selectedClipId:", page.evaluate("() => window.avatarController.selectedClipId"))
    page.click("#btn-avatar-play")
    print("After play status:", page.locator("#avatar-playback-status-badge").text_content())
    page.wait_for_timeout(300)
    print("After 300ms status:", page.locator("#avatar-playback-status-badge").text_content())
    print("Player playbackState:", page.evaluate("() => window.avatarController.player.playbackState"))
    print("Player currentTime:", page.evaluate("() => window.avatarController.player.currentTime"))
    browser.close()
