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
        const m = vrm.humanoid.getNormalizedBoneNode('rightThumbMetacarpal');
        const p = vrm.humanoid.getNormalizedBoneNode('rightThumbProximal');
        const d = vrm.humanoid.getNormalizedBoneNode('rightThumbDistal');
        
        m.rotation.set(0, 0, 0);
        p.rotation.set(0, 0, 0);
        d.rotation.set(0, 0, 0);
        vrm.scene.updateMatrixWorld(true);

        const d0 = new THREE.Vector3();
        d.getWorldPosition(d0);

        // Test thumb flexion around Y
        p.rotation.set(0, 0.5, 0);
        vrm.scene.updateMatrixWorld(true);
        const d_ypos = new THREE.Vector3();
        d.getWorldPosition(d_ypos);

        // Test thumb flexion around Z
        p.rotation.set(0, 0, 0.5);
        vrm.scene.updateMatrixWorld(true);
        const d_zpos = new THREE.Vector3();
        d.getWorldPosition(d_zpos);

        // Test thumb flexion around X
        p.rotation.set(0.5, 0, 0);
        vrm.scene.updateMatrixWorld(true);
        const d_xpos = new THREE.Vector3();
        d.getWorldPosition(d_xpos);

        // Check left hand mirror
        const lp = vrm.humanoid.getNormalizedBoneNode('leftIndexProximal');
        const ld = vrm.humanoid.getNormalizedBoneNode('leftIndexDistal');
        lp.rotation.set(0, 0, 0);
        vrm.scene.updateMatrixWorld(true);
        const ld0 = new THREE.Vector3();
        ld.getWorldPosition(ld0);

        // Test left index Z = -0.5 vs Z = +0.5
        lp.rotation.set(0, 0, -0.5);
        vrm.scene.updateMatrixWorld(true);
        const ld_zneg = new THREE.Vector3();
        ld.getWorldPosition(ld_zneg);

        return {
            thumb_rest: [d0.x, d0.y, d0.z],
            thumb_ypos: [d_ypos.x - d0.x, d_ypos.y - d0.y, d_ypos.z - d0.z],
            thumb_zpos: [d_zpos.x - d0.x, d_zpos.y - d0.y, d_zpos.z - d0.z],
            thumb_xpos: [d_xpos.x - d0.x, d_xpos.y - d0.y, d_xpos.z - d0.z],
            left_index_zneg: [ld_zneg.x - ld0.x, ld_zneg.y - ld0.y, ld_zneg.z - ld0.z]
        };
    }""")

    print(json.dumps(res, indent=2))
    browser.close()
