from playwright.sync_api import sync_playwright

STUDIO_URL = "http://127.0.0.1:8000/studio"
with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    page = browser.new_page()
    page.goto(STUDIO_URL)
    page.click("#tab-btn-side-avatar")
    page.wait_for_selector("#avatar-model-source-info:has-text('VRM 1.0')", timeout=15000)
    
    info = page.evaluate("""() => {
        const ctrl = window.avatarController;
        const cam = ctrl.engine.camera;
        const vrm = ctrl.player.model;
        const head = vrm.humanoid.getNormalizedBoneNode('head');
        const hips = vrm.humanoid.getNormalizedBoneNode('hips');
        const headPos = new THREE.Vector3();
        const hipsPos = new THREE.Vector3();
        head.getWorldPosition(headPos);
        hips.getWorldPosition(hipsPos);
        return {
            camPos: [cam.position.x, cam.position.y, cam.position.z],
            camFov: cam.fov,
            headWorld: [headPos.x, headPos.y, headPos.z],
            hipsWorld: [hipsPos.x, hipsPos.y, hipsPos.z]
        };
    }""")
    print("Camera and bone positions:", info)
    browser.close()
