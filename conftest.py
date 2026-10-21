"""Clasificación estable de la suite pytest por tipo de ejecución."""

from __future__ import annotations

import importlib.util

import pytest


_E2E_FILES = {
    "test_adversarial_browser_stress.py",
    "test_avatar_3d_playwright.py",
    "test_playwright_e2e.py",
    "test_lsec_avatar_vrm_validation.py",
    "test_studio_avatar_connection.py",
    "test_studio_export_e2e.py",
    "test_studio_audit_fixes_acceptance.py",
    "test_trailing_signal_browser.py",
}
_ASSET_FILES = {
    "test_avatar_3d_unit.py",
    "test_avatar_v26_resolution_and_export.py",
    "test_avatar_v27_standardized.py",
    "test_dictionary_service_and_gloss_enrichment.py",
    "test_lsec_video_like_corpus.py",
    "test_universal_video_and_remediation.py",
}
_INTEGRATION_FILES = {
    "test_annotation_endpoints.py",
    "test_pipeline.py",
    "test_root_and_avatar_endpoints.py",
    "test_active_learning_and_mlops.py",
}
_LIVE_SERVER_FILES = {
    "test_adversarial_backend.py",
    "test_adversarial_browser_stress.py",
}


def pytest_ignore_collect(collection_path, config: pytest.Config) -> bool:
    """Evita importar pruebas E2E al ejecutar perfiles sin Playwright."""
    if collection_path.name not in _E2E_FILES:
        return False
    if "unit" not in config.getoption("-m", default=""):
        return False
    return importlib.util.find_spec("playwright") is None


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    """Añade marcadores por archivo sin cambiar la ubicación de las pruebas."""
    for item in items:
        filename = item.path.name
        if filename in _E2E_FILES:
            item.add_marker("e2e")
        if filename in _ASSET_FILES:
            item.add_marker("assets")
        if filename in _INTEGRATION_FILES:
            item.add_marker("integration")
        if filename in _LIVE_SERVER_FILES:
            item.add_marker("live_server")
        if (
            filename not in _E2E_FILES
            and filename not in _INTEGRATION_FILES
            and filename not in _LIVE_SERVER_FILES
            and filename not in _ASSET_FILES
        ):
            item.add_marker("unit")
