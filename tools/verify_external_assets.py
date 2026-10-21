"""Verifica perfiles de assets externos sin escanear el contenido multimedia."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.config import PROJECT_ROOT, external_path, settings


def _asset_entry(name: str, path: Path, required: bool) -> dict[str, Any]:
    return {
        "name": name,
        "path": str(path),
        "available": path.is_dir() or path.is_file(),
        "required_for_complete_profile": required,
    }


def build_report() -> dict[str, Any]:
    assets = [
        _asset_entry("avatar", external_path(settings.lsec_avatar_dir, "Avatar"), True),
        _asset_entry("dictionary", external_path(settings.lsec_dictionary_root, "Diccionario LSEC"), True),
        _asset_entry(
            "animations_v27",
            external_path(settings.lsec_animations_v27_dir, "Diccionario LSEC/senas_vrm_standardized_v2.7"),
            True,
        ),
        _asset_entry(
            "animations_v26",
            external_path(settings.lsec_animations_v26_dir, "Diccionario LSEC/senas_vrm_direct_v2.6"),
            False,
        ),
        _asset_entry("uhd_videos", external_path(settings.lsec_uhd_dir, "Diccionario LSEC/senas_ultra_hd"), False),
        _asset_entry("whisper_model", PROJECT_ROOT / settings.whisper_model_path, False),
    ]
    complete = all(item["available"] for item in assets if item["required_for_complete_profile"])
    asr_ready = next(item for item in assets if item["name"] == "whisper_model")["available"]
    return {
        "profiles": {
            "minimal": True,
            "asr_offline": asr_ready,
            "complete_av": complete,
        },
        "assets": assets,
        "policy": "Assets externos permanecen fuera de Git; esta comprobación no calcula hashes ni recorre catálogos.",
    }


if __name__ == "__main__":
    print(json.dumps(build_report(), ensure_ascii=False, indent=2))
