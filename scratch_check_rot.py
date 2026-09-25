from playwright.sync_api import sync_playwright

STUDIO_URL = "http://127.0.0.1:8000/studio"
with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    page = browser.new_page()
    page.goto(STUDIO_URL)
    page.click("#tab-btn-side-avatar")
    page.wait_for_selector("#avatar-model-source-info:has-text('VRM 1.0')", timeout=15000)
    
    rot = page.evaluate("""() => {
        const ctrl = window.avatarController;
        const vrm = ctrl.player.model;
        const headPos = new THREE.Vector3();
        const eyePos = new THREE.Vector3();
        vrm.humanoid.getNormalizedBoneNode('head').getWorldPosition(headPos);
        vrm.humanoid.getNormalizedBoneNode('leftEye').getWorldPosition(eyePos);
        return {
            sceneRotY: vrm.scene.rotation.y,
            headZ: headPos.z,
            eyeZ: eyePos.z,
            eyeFrontOfHead: eyePos.z > headPos.z
        };
    }""")
    print("Orientation check:", rot)
    browser.close()
