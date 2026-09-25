import json
from playwright.sync_api import sync_playwright

STUDIO_URL = "http://127.0.0.1:8000/studio"

with sync_playwright() as p:
    browser = p.chromium.launch(
        headless=True,
        args=["--use-gl=angle", "--use-angle=swiftshader", "--enable-webgl", "--ignore-gpu-blocklist"]
    )
    page = browser.new_page(viewport={"width": 1440, "height": 900})
    page.goto(STUDIO_URL, wait_until="domcontentloaded")
    page.click("#tab-btn-side-avatar")
    page.wait_for_selector("#avatar-model-source-info:has-text('VRM 1.0')", timeout=15000)

    res = page.evaluate("""() => {
        const ctrl = window.avatarController;
        const vrm = ctrl.player.model;
        const p = vrm.humanoid.getNormalizedBoneNode('rightIndexProximal');
        const d = vrm.humanoid.getNormalizedBoneNode('rightIndexDistal');
        
        // Reset rotations
        p.rotation.set(0, 0, 0);
        d.rotation.set(0, 0, 0);
        vrm.scene.updateMatrixWorld(true);

        const p0 = p.position.clone();
        const d0 = new THREE.Vector3();
        d.getWorldPosition(d0);
        const p0_world = new THREE.Vector3();
        p.getWorldPosition(p0_world);

        // Try z = 0.5
        p.rotation.set(0, 0, 0.5);
        vrm.scene.updateMatrixWorld(true);
        const d_zpos = new THREE.Vector3();
        d.getWorldPosition(d_zpos);

        // Try z = -0.5
        p.rotation.set(0, 0, -0.5);
        vrm.scene.updateMatrixWorld(true);
        const d_zneg = new THREE.Vector3();
        d.getWorldPosition(d_zneg);

        // Try x = 0.5
        p.rotation.set(0.5, 0, 0);
        vrm.scene.updateMatrixWorld(true);
        const d_xpos = new THREE.Vector3();
        d.getWorldPosition(d_xpos);

        // Try y = 0.5
        p.rotation.set(0, 0.5, 0);
        vrm.scene.updateMatrixWorld(true);
        const d_ypos = new THREE.Vector3();
        d.getWorldPosition(d_ypos);

        p.rotation.set(0, 0, 0);
        vrm.scene.updateMatrixWorld(true);

        return {
            distal_rest: [d0.x - p0_world.x, d0.y - p0_world.y, d0.z - p0_world.z],
            delta_zpos: [d_zpos.x - d0.x, d_zpos.y - d0.y, d_zpos.z - d0.z],
            delta_zneg: [d_zneg.x - d0.x, d_zneg.y - d0.y, d_zneg.z - d0.z],
            delta_xpos: [d_xpos.x - d0.x, d_xpos.y - d0.y, d_xpos.z - d0.z],
            delta_ypos: [d_ypos.x - d0.x, d_ypos.y - d0.y, d_ypos.z - d0.z],
        };
    }""")

    print(json.dumps(res, indent=2))
    browser.close()
