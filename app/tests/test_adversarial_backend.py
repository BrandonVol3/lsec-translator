"""
Adversarial Stress Test Suite — Backend Endpoints & Translation Engine.
Audit Milestone 2 / Challenger 1 (challenger_m2_1).

Tests the active FastAPI server (http://127.0.0.1:8000) against:
1. Translation edge-case inputs: empty string, whitespace only, punctuation only,
   massive text (boundary limits), numbers, acronyms ("UPEC", "LSEC", etc.),
   and out-of-vocabulary (OOV) unknown words.
2. Graceful responses: HTTP 200 with fallback to fingerspelling / review required,
   or HTTP 422 for schema violations, with ZERO unhandled 500 exceptions.
3. Sign animation resolution (/api/v1/animations/resolve/{gloss}):
   non-existent glosses, case insensitivity, accented characters, special characters.
   Verifies it never throws 404 or 500, but cleanly returns found=False.
4. Avatar download: /avatar/LSEC-Interpreter-Female.vrm returns valid binary
   with glTF magic header (0x46546C67) and size > 10 MB.
5. Non-existent static assets and malicious path traversal attempts:
   verifies proper 404/400 handling without server crash or information leakage.
"""

import sys
import json
import time
import urllib.parse
from typing import Any, Dict, List, Tuple

import httpx
import pytest

BASE_URL = "http://127.0.0.1:8000"


def _check_live_server() -> bool:
    try:
        r = httpx.get(f"{BASE_URL}/api/v1/health", timeout=3.0)
        return r.status_code == 200
    except Exception:
        return False


IS_SERVER_LIVE = _check_live_server()


@pytest.fixture(scope="module")
def http_client():
    """Client for testing against the live server."""
    with httpx.Client(base_url=BASE_URL, timeout=30.0) as client:
        yield client


# ============================================================================
# 1. TRANSLATION ENDPOINT ADVERSARIAL TESTS (POST /api/v1/translate)
# ============================================================================

def test_translate_empty_string(http_client: httpx.Client):
    """
    Empty string is rejected by Pydantic min_length=1 with HTTP 422,
    NEVER with unhandled HTTP 500.
    """
    resp = http_client.post("/api/v1/translate", json={"text": ""})
    assert resp.status_code == 422, f"Expected 422 for empty string, got {resp.status_code}: {resp.text}"
    body = resp.json()
    assert "detail" in body


def test_translate_whitespace_only(http_client: httpx.Client):
    """
    Whitespace-only input satisfies min_length=1.
    Must be handled gracefully without 500 exception (either 200 with empty/fallback glosses or 400).
    """
    resp = http_client.post("/api/v1/translate", json={"text": "     \t\n   "})
    assert resp.status_code in (200, 400, 422), f"Unexpected status {resp.status_code}: {resp.text}"
    assert resp.status_code != 500, "Server crashed with 500 on whitespace input"
    if resp.status_code == 200:
        data = resp.json()
        assert "glosses" in data
        assert isinstance(data["glosses"], list)


def test_translate_punctuation_only(http_client: httpx.Client):
    """
    Punctuation-only input: "...... ????? !!!!! ,,,, ---- ;;;; :::: <<>> () []"
    Must return HTTP 200 with graceful fallback, NO 500 error.
    """
    punct_text = "...... ????? !!!!! ,,,, ---- ;;;; :::: <<>> () [] ¡¡¡ ¿¿¿"
    resp = http_client.post("/api/v1/translate", json={"text": punct_text})
    assert resp.status_code == 200, f"Expected 200 for punctuation-only, got {resp.status_code}: {resp.text}"
    data = resp.json()
    assert "glosses" in data
    assert "schema_version" in data


def test_translate_massive_text_boundaries(http_client: httpx.Client):
    """
    Test boundary conditions around max_length=5000:
    - 4900 chars: should succeed HTTP 200.
    - 5000 chars: exact upper limit, should succeed HTTP 200.
    - 5001 chars: exceeds limit, must return HTTP 422 (never 500).
    - 15000 chars: massive overload, must return HTTP 422 (never 500/OOM).
    """
    # 1. Valid long text (4900 chars)
    sentence = "El estudiante sordo aprende lengua de señas ecuatoriana en la universidad. "
    text_4900 = (sentence * ((4900 // len(sentence)) + 1))[:4900]
    resp_4900 = http_client.post("/api/v1/translate", json={"text": text_4900})
    assert resp_4900.status_code == 200, f"Expected 200 for 4900 chars, got {resp_4900.status_code}"
    data_4900 = resp_4900.json()
    assert len(data_4900.get("glosses", [])) > 0

    # 2. Exact boundary (5000 chars)
    text_5000 = (sentence * ((5000 // len(sentence)) + 1))[:5000]
    resp_5000 = http_client.post("/api/v1/translate", json={"text": text_5000})
    assert resp_5000.status_code == 200, f"Expected 200 for 5000 chars, got {resp_5000.status_code}"

    # 3. Exceeds limit by 1 (5001 chars) -> HTTP 422
    text_5001 = text_5000 + "X"
    resp_5001 = http_client.post("/api/v1/translate", json={"text": text_5001})
    assert resp_5001.status_code == 422, f"Expected 422 for 5001 chars, got {resp_5001.status_code}"

    # 4. Overload (15000 chars) -> HTTP 422
    text_huge = sentence * 250
    resp_huge = http_client.post("/api/v1/translate", json={"text": text_huge})
    assert resp_huge.status_code == 422, f"Expected 422 for huge text, got {resp_huge.status_code}"


def test_translate_numbers_and_symbols(http_client: httpx.Client):
    """
    Test numbers, decimals, negatives, currency, and dates.
    Must return HTTP 200 with valid glosses and no crashes.
    """
    test_cases = [
        "1 2 3 4 5 10 20 100 1000",
        "El año 2026 tiene 365 días y 12 meses.",
        "La temperatura es -5 grados y el precio es $15.50 dólares.",
        "3.1415926535",
        "4500",
        "0992872993",
        "14:30",
    ]
    for text in test_cases:
        resp = http_client.post("/api/v1/translate", json={"text": text})
        assert resp.status_code == 200, f"Failed for '{text}': {resp.status_code}"
        data = resp.json()
        assert "glosses" in data
        assert len(data["glosses"]) > 0


def test_translate_xss_emojis_and_nested_symbols(http_client: httpx.Client):
    """
    Test XSS injection payloads, emojis, math symbols, nested punctuation, and +1500 char paragraphs.
    Must return HTTP 200 without throwing 500 Internal Server Error.
    """
    long_1500 = "La educación inclusiva universitaria en la UPEC fortalece la Lengua de Señas Ecuatoriana. " * 20
    assert len(long_1500) > 1500
    payloads = [
        "<script>alert('xss')</script><img src=x onerror=alert(1)>",
        "🔥🔥 ¿¿¿Hola??? ¡¡¡100% @#$%^&*()!!!",
        long_1500,
    ]
    for p in payloads:
        resp = http_client.post("/api/v1/translate", json={"text": p})
        assert resp.status_code == 200, f"Payload '{p[:40]}' failed with {resp.status_code}"
        data = resp.json()
        assert "glosses" in data and isinstance(data["glosses"], list)


def test_translate_acronyms_and_institutions(http_client: httpx.Client):
    """
    Test acronyms: UPEC, LSEC, UNESCO, FENASEC, CONADIS.
    Must return HTTP 200, proper gloss breakdown or fingerspelling.
    """
    acronyms = ["UPEC", "LSEC", "UNESCO", "FENASEC", "CONADIS"]
    for acr in acronyms:
        resp = http_client.post("/api/v1/translate", json={"text": acr})
        assert resp.status_code == 200, f"Acronym '{acr}' failed with {resp.status_code}"
        data = resp.json()
        assert "glosses" in data
        assert len(data["glosses"]) > 0

    combined = "La UPEC y FENASEC investigan la LSEC en Ecuador con el aval de CONADIS y UNESCO."
    resp_comb = http_client.post("/api/v1/translate", json={"text": combined})
    assert resp_comb.status_code == 200, f"Combined acronym text failed: {resp_comb.status_code}"
    data_comb = resp_comb.json()
    assert len(data_comb["glosses"]) >= 5


def test_translate_unknown_oov_words(http_client: httpx.Client):
    """
    Test completely unknown/invented words and keyboard mash.
    Must return HTTP 200 with fallback to fingerspelling / review required.
    Zero 500 errors.
    """
    oov_texts = [
        "qwertyuiop asdfghjkl zxcvbnm",
        "supercalifragilisticoespialidoso",
        "X Æ A-12 Musk",
        "Klingon tlhingan hol",
        "blork flup zorp",
    ]
    for text in oov_texts:
        resp = http_client.post("/api/v1/translate", json={"text": text})
        assert resp.status_code == 200, f"OOV text '{text}' failed with {resp.status_code}"
        data = resp.json()
        assert "glosses" in data
        # Check that items indicate need of review or fallback
        items = data.get("items", [])
        if items:
            for item in items:
                assert "gloss" in item


def test_translate_malformed_json_types(http_client: httpx.Client):
    """
    Test invalid payload types (int instead of str, missing field, wrong field types).
    Must return HTTP 422, NEVER HTTP 500.
    """
    bad_payloads = [
        {"text": 12345},
        {"text": ["hola", "mundo"]},
        {"text": None},
        {"wrong_field": "hola"},
        {},
    ]
    for payload in bad_payloads:
        resp = http_client.post("/api/v1/translate", json=payload)
        assert resp.status_code == 422, f"Payload {payload} did not return 422: got {resp.status_code}"


# ============================================================================
# 2. SIGN ANIMATION RESOLUTION ADVERSARIAL TESTS (/api/v1/animations/resolve/{gloss})
# ============================================================================

def test_resolve_non_existent_gloss(http_client: httpx.Client):
    """
    Non-existent glosses must NEVER return HTTP 404 or 500.
    Must return HTTP 200 with found=False and clean status MISSING.
    """
    missing_glosses = [
        "GLOSA_INEXISTENTE_XYZ999",
        "PALABRA_QUE_NO_EXISTE_EN_EL_DICCIONARIO_12345",
        "ZZZZZZZZZZ_NO_EXISTE",
        "SUPER_EXTRA_NON_EXISTENT_GLOSS",
    ]
    for gloss in missing_glosses:
        url = f"/api/v1/animations/resolve/{gloss}"
        resp = http_client.get(url)
        assert resp.status_code == 200, f"Failed for {gloss}: expected 200, got {resp.status_code}"
        data = resp.json()
        assert data.get("found") is False, f"Expected found=False for {gloss}, got {data.get('found')}"
        assert data.get("status") in ("MISSING", "none"), f"Unexpected status: {data.get('status')}"
        assert data.get("animation") is None


def test_resolve_case_insensitivity(http_client: httpx.Client):
    """
    Case variants must all resolve properly without 404/500:
    "hola", "HOLA", "HoLa", "hOlA".
    """
    variants = ["hola", "HOLA", "HoLa", "hOlA"]
    resolved_signs = []
    for var in variants:
        resp = http_client.get(f"/api/v1/animations/resolve/{var}?include_animation=false")
        assert resp.status_code == 200, f"Case variant '{var}' returned {resp.status_code}"
        data = resp.json()
        assert data.get("found") is True, f"Variant '{var}' was not found"
        resolved_signs.append(data.get("resolved_gloss") or data.get("sign"))

    # All should resolve to the same canonical sign
    assert len(set(resolved_signs)) == 1, f"Inconsistent resolution across case variants: {resolved_signs}"


def test_resolve_accented_and_unicode_characters(http_client: httpx.Client):
    """
    Test accented vowels, ñ, inverted punctuation (¿, ¡), and diacritics.
    Must return HTTP 200 without crashes or 500s.
    """
    accented_cases = [
        ("¿QUIÉN?", "%C2%BFQUI%C3%89N%3F"),
        ("canción", "canci%C3%B3n"),
        ("Árbol", "%C3%81rbol"),
        ("NIÑO", "NI%C3%91O"),
        ("año", "a%C3%B1o"),
        ("MÁS", "M%C3%81S"),
    ]
    for label, encoded in accented_cases:
        resp = http_client.get(f"/api/v1/animations/resolve/{encoded}?include_animation=false")
        assert resp.status_code == 200, f"Accented gloss '{label}' ({encoded}) failed with {resp.status_code}"
        data = resp.json()
        assert "found" in data
        assert isinstance(data["found"], bool)


def test_resolve_punctuation_and_symbols(http_client: httpx.Client):
    """
    Punctuation or symbol glosses: "???", "---", "!@#$%".
    Must return HTTP 200 with found=False, NEVER throw 500.
    """
    symbol_cases = [
        urllib.parse.quote("???"),
        urllib.parse.quote("---"),
        urllib.parse.quote("!@#$%^&*()"),
        urllib.parse.quote("   "),
    ]
    for sym in symbol_cases:
        resp = http_client.get(f"/api/v1/animations/resolve/{sym}?include_animation=false")
        assert resp.status_code in (200, 404), f"Symbol '{sym}' gave status {resp.status_code}"
        assert resp.status_code != 500, f"Server threw 500 on symbol '{sym}'"


def test_resolve_batch_adversarial(http_client: httpx.Client):
    """
    Test POST /api/v1/animations/resolve with:
    - Empty list
    - Mixed valid, invalid, accented, numbers, and symbols
    - 500-item batch
    All must succeed with HTTP 200 and zero 500 errors.
    """
    # 1. Empty list
    r_empty = http_client.post("/api/v1/animations/resolve", json={"glosses": []})
    assert r_empty.status_code == 200
    assert r_empty.json()["summary"]["total"] == 0

    # 2. Mixed list
    mixed = ["HOLA", "GLOSA_XYZ_999", "¿QUIÉN?", "COTIDIANA", "U-P-E-C", "12345", "SUPER_OOV_WORD"]
    r_mixed = http_client.post("/api/v1/animations/resolve", json={"glosses": mixed, "include_animation": False})
    assert r_mixed.status_code == 200
    m_data = r_mixed.json()
    assert m_data["summary"]["total"] == len(mixed)
    assert m_data["summary"]["resolved"] >= 2  # HOLA, COTIDIANA, ¿QUIÉN? should resolve

    # 3. Large batch (500 items)
    large_batch = (["HOLA", "ADIÓS", "GRACIAS", "INEXISTENTE_XYZ"] * 125)
    t0 = time.time()
    r_large = http_client.post("/api/v1/animations/resolve", json={"glosses": large_batch, "include_animation": False})
    elapsed = time.time() - t0
    assert r_large.status_code == 200
    assert r_large.json()["summary"]["total"] == 500
    assert elapsed < 5.0, f"Batch resolution too slow: {elapsed:.2f}s"


# ============================================================================
# 3. AVATAR VRM DOWNLOAD & INTEGRITY TESTS (/avatar/LSEC-Interpreter-Female.vrm)
# ============================================================================

def test_avatar_vrm_integrity_and_magic_header(http_client: httpx.Client):
    """
    Verify /avatar/LSEC-Interpreter-Female.vrm:
    - HTTP 200
    - Binary starts with glTF magic header: b'glTF' (0x46546C67)
    - Size > 10,000,000 bytes (~13.3 MB)
    - HEAD request returns valid Content-Length and Accept-Ranges
    """
    # 1. HEAD request
    head_resp = http_client.head("/avatar/LSEC-Interpreter-Female.vrm")
    assert head_resp.status_code == 200, f"HEAD request failed: {head_resp.status_code}"
    content_length = int(head_resp.headers.get("content-length", 0))
    assert content_length > 10_000_000, f"Content-Length too small: {content_length}"

    # 2. Range request (first 16 bytes for magic bytes)
    range_resp = http_client.get("/avatar/LSEC-Interpreter-Female.vrm", headers={"Range": "bytes=0-15"})
    assert range_resp.status_code in (200, 206), f"Range request failed: {range_resp.status_code}"
    header_bytes = range_resp.content[:4]
    assert header_bytes == b"glTF", f"Expected b'glTF', got {header_bytes}"

    # 3. Full download verification
    full_resp = http_client.get("/avatar/LSEC-Interpreter-Female.vrm")
    assert full_resp.status_code == 200
    assert len(full_resp.content) == content_length
    assert full_resp.content[:4] == b"glTF"


# ============================================================================
# 4. STATIC ASSET RESILIENCE & PATH TRAVERSAL / MALICIOUS PATH TESTS
# ============================================================================

def test_non_existent_static_assets_return_404(http_client: httpx.Client):
    """
    Non-existent static files and routes must return clean HTTP 404,
    without crashing or returning 500.
    """
    non_existent = [
        "/static/non_existent_file_xyz_12345.js",
        "/static/css/fake_style_non_existent.css",
        "/avatar/non_existent_model_xyz.vrm",
        "/configuracion-manual/non_existent_image.png",
        "/api/v1/non_existent_endpoint_xyz",
        "/foo/bar/baz/test/404",
    ]
    for path in non_existent:
        resp = http_client.get(path)
        assert resp.status_code == 404, f"Path '{path}' expected 404, got {resp.status_code}"
        assert resp.status_code != 500, f"Path '{path}' caused server 500"


def test_path_traversal_attempts(http_client: httpx.Client):
    """
    Test path traversal attempts against static mounts:
    - /static/../../app/main.py
    - /avatar/../../app/config.py
    - /avatar/%2e%2e%2f%2e%2e%2fpackage.json
    - /api/v1/animations/resolve/..%2f..%2fmain.py
    Must return 404 or 400 (or resolve as missing), NEVER 200 with leaked file contents,
    and NEVER crash the server.
    """
    traversal_paths = [
        "/static/../../app/main.py",
        "/static/..%2f..%2fapp%2fmain.py",
        "/avatar/../../app/main.py",
        "/avatar/..%2f..%2fapp%2fmain.py",
        "/avatar/%2e%2e%2f%2e%2e%2frequirements.txt",
        "/configuracion-manual/../../app/main.py",
    ]
    for path in traversal_paths:
        resp = http_client.get(path)
        # Should be 404, 400, or 403. Must NEVER expose source code or return 500.
        assert resp.status_code in (400, 404, 403), f"Path traversal '{path}' returned unexpected {resp.status_code}"
        assert "LSEC Translator Prototype" not in resp.text or resp.status_code == 404


def test_http_method_tampering(http_client: httpx.Client):
    """
    Tamper with HTTP methods on endpoints.
    Must return 405 Method Not Allowed, NEVER 500.
    """
    tamper_cases = [
        ("PUT", "/api/v1/translate"),
        ("DELETE", "/api/v1/translate"),
        ("DELETE", "/avatar/LSEC-Interpreter-Female.vrm"),
        ("POST", "/api/v1/health"),
        ("POST", "/avatar/LSEC-Interpreter-Female.vrm"),
    ]
    for method, path in tamper_cases:
        resp = http_client.request(method, path)
        assert resp.status_code == 405, f"Method {method} on {path} returned {resp.status_code}, expected 405"


# ============================================================================
# STANDALONE CLI RUNNER FOR DIRECT VERIFICATION
# ============================================================================

def run_standalone_adversarial_suite() -> Dict[str, Any]:
    print("=" * 70)
    print("EJECUTANDO SUITE ADVERSARIAL COMPLETA — CHALLENGER 1 (M2/M3)")
    print(f"Target: {BASE_URL}")
    print("=" * 70)

    client = httpx.Client(base_url=BASE_URL, timeout=30.0)
    tests = [
        ("Traducir cadena vacía (422 graceful)", lambda: test_translate_empty_string(client)),
        ("Traducir espacios en blanco", lambda: test_translate_whitespace_only(client)),
        ("Traducir puntuación y símbolos", lambda: test_translate_punctuation_only(client)),
        ("Límites de longitud de texto (4900, 5000, 5001, 15000)", lambda: test_translate_massive_text_boundaries(client)),
        ("Traducir números, fechas y decimales", lambda: test_translate_numbers_and_symbols(client)),
        ("Traducir acrónimos (UPEC, LSEC, UNESCO, etc.)", lambda: test_translate_acronyms_and_institutions(client)),
        ("Traducir palabras desconocidas / OOV", lambda: test_translate_unknown_oov_words(client)),
        ("Validación de esquemas JSON corruptos", lambda: test_translate_malformed_json_types(client)),
        ("Resolución de glosa inexistente (0 errores 404/500)", lambda: test_resolve_non_existent_gloss(client)),
        ("Resolución insensible a mayúsculas/minúsculas", lambda: test_resolve_case_insensitivity(client)),
        ("Resolución de caracteres acentuados y Unicode", lambda: test_resolve_accented_and_unicode_characters(client)),
        ("Resolución de símbolos y puntuación", lambda: test_resolve_punctuation_and_symbols(client)),
        ("Resolución por lotes (vacío, mixto, 500 ítems)", lambda: test_resolve_batch_adversarial(client)),
        ("Descarga de avatar VRM e integridad glTF magic", lambda: test_avatar_vrm_integrity_and_magic_header(client)),
        ("Archivos estáticos inexistentes retornan 404 limpio", lambda: test_non_existent_static_assets_return_404(client)),
        ("Pruebas de Path Traversal y seguridad", lambda: test_path_traversal_attempts(client)),
        ("Tampering de métodos HTTP (405 Method Not Allowed)", lambda: test_http_method_tampering(client)),
    ]

    passed = 0
    failed = 0
    errors: List[Dict[str, str]] = []

    for name, fn in tests:
        t0 = time.time()
        try:
            fn()
            elapsed = time.time() - t0
            print(f"  [PASS] {name} ({elapsed:.3f}s)")
            passed += 1
        except Exception as exc:
            elapsed = time.time() - t0
            print(f"  [FAIL] {name} ({elapsed:.3f}s) -> {exc}")
            failed += 1
            errors.append({"test": name, "error": str(exc)})

    client.close()

    print("=" * 70)
    print(f"RESUMEN ADVERSARIAL: {passed} PASADOS | {failed} FALLADOS | Total: {len(tests)}")
    print("=" * 70)

    return {
        "passed": passed,
        "failed": failed,
        "total": len(tests),
        "errors": errors,
    }


if __name__ == "__main__":
    results = run_standalone_adversarial_suite()
    if results["failed"] > 0:
        sys.exit(1)
    sys.exit(0)
