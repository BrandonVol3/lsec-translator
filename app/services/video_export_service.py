"""
Servicio de Gestión de Carpeta de Exportación y Codificación MP4 Determinista para LSEC Studio.

Garantiza que:
1. Exista por defecto una carpeta en el Escritorio (`Videos Exportados LSEC Studio`).
2. Si la carpeta por defecto o la ruta personalizada no existe al momento de exportar un video,
   se cree automáticamente (`mkdir(parents=True, exist_ok=True)`).
3. El usuario pueda consultar, escribir o seleccionar mediante diálogo nativo cualquier otra
   ruta personalizada para guardar los videos exportados.
"""

from __future__ import annotations

import io
import json
import logging
import os
import re
import subprocess
import sys
import urllib.parse
from fractions import Fraction
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

from fastapi import HTTPException
from fastapi.responses import Response

from app.config import PROJECT_ROOT, WORKSPACE_ROOT

logger = logging.getLogger(__name__)

DEFAULT_EXPORT_FOLDER_NAME = "Videos Exportados LSEC Studio"
_PREFS_FILE = PROJECT_ROOT / "data" / "export_preferences.json"
_active_custom_export_dir: Optional[str] = None


def _resolve_desktop_root() -> Path:
    """Localiza el Escritorio del usuario actual de forma robusta en Windows."""
    candidates = []
    # 1. Si el workspace está directamente dentro del Escritorio (ej. C:\Users\brana\Desktop\TIC Software)
    if WORKSPACE_ROOT.parent and WORKSPACE_ROOT.parent.exists():
        parent_name = WORKSPACE_ROOT.parent.name.lower()
        if parent_name in ("desktop", "escritorio"):
            candidates.append(WORKSPACE_ROOT.parent)

    # 2. Variable de perfil de usuario estándar
    home = Path.home()
    candidates.append(home / "Desktop")
    candidates.append(home / "Escritorio")

    userprofile = os.environ.get("USERPROFILE")
    if userprofile:
        up = Path(userprofile)
        candidates.append(up / "Desktop")
        candidates.append(up / "Escritorio")

    for cand in candidates:
        try:
            if cand.exists() and cand.is_dir():
                return cand.resolve()
        except OSError:
            continue

    return WORKSPACE_ROOT.parent if WORKSPACE_ROOT.parent.exists() else WORKSPACE_ROOT


def get_default_export_directory(ensure_exists: bool = True) -> Path:
    """
    Devuelve la ruta de la carpeta por defecto en el Escritorio para guardar videos exportados.
    Si `ensure_exists` es True y la carpeta no existe, la crea automáticamente.
    """
    desktop_root = _resolve_desktop_root()
    default_dir = desktop_root / DEFAULT_EXPORT_FOLDER_NAME
    if ensure_exists:
        try:
            default_dir.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            logger.warning("No se pudo crear la carpeta en Escritorio (%s): %s", default_dir, exc)
            fallback = WORKSPACE_ROOT / DEFAULT_EXPORT_FOLDER_NAME
            fallback.mkdir(parents=True, exist_ok=True)
            return fallback.resolve()
    return default_dir.resolve()


def _load_persisted_custom_dir() -> Optional[str]:
    """Carga la ruta personalizada guardada en disco si existe."""
    global _active_custom_export_dir
    if _active_custom_export_dir is not None:
        return _active_custom_export_dir or None
    try:
        if _PREFS_FILE.is_file():
            data = json.loads(_PREFS_FILE.read_text(encoding="utf-8"))
            custom = (data.get("custom_export_directory") or "").strip()
            _active_custom_export_dir = custom
            return custom or None
    except Exception as exc:
        logger.debug("No se pudo leer preferencia de exportación: %s", exc)
    _active_custom_export_dir = ""
    return None


def _save_persisted_custom_dir(custom_dir: Optional[str]) -> None:
    """Guarda la ruta personalizada en `data/export_preferences.json`."""
    global _active_custom_export_dir
    clean = (custom_dir or "").strip()
    _active_custom_export_dir = clean
    try:
        _PREFS_FILE.parent.mkdir(parents=True, exist_ok=True)
        _PREFS_FILE.write_text(
            json.dumps({"custom_export_directory": clean}, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
    except Exception as exc:
        logger.warning("No se pudo persistir preferencia de carpeta de exportación: %s", exc)


def resolve_export_target_directory(custom_dir: Optional[str] = None, ensure_exists: bool = True) -> Path:
    """
    Resuelve la carpeta destino donde se guardará el video exportado.
    Si no existe la carpeta (sea la del Escritorio por defecto o una ruta personalizada),
    la crea automáticamente.
    """
    default_dir = get_default_export_directory(ensure_exists=ensure_exists)
    candidate_raw = (custom_dir or "").strip()
    if not candidate_raw:
        candidate_raw = _load_persisted_custom_dir() or ""

    if not candidate_raw:
        return default_dir

    try:
        cleaned = candidate_raw.strip().strip('"').strip("'")
        target = Path(cleaned).expanduser()
        if not target.is_absolute():
            # Si el usuario ingresó solo un nombre de carpeta o ruta relativa, la ubicamos en el Escritorio
            target = _resolve_desktop_root() / target
        if ensure_exists:
            target.mkdir(parents=True, exist_ok=True)
        return target.resolve()
    except Exception as exc:
        logger.warning(
            "Ruta personalizada inválida o inaccesible ('%s'): %s. Usando carpeta por defecto en Escritorio.",
            candidate_raw,
            exc,
        )
        if ensure_exists:
            default_dir.mkdir(parents=True, exist_ok=True)
        return default_dir


def get_export_directory_status() -> Dict[str, Any]:
    """Devuelve el estado actual de la carpeta por defecto y la carpeta activa de exportación."""
    default_dir = get_default_export_directory(ensure_exists=True)
    custom_raw = _load_persisted_custom_dir()
    active_dir = resolve_export_target_directory(custom_raw, ensure_exists=True)
    is_custom = active_dir.resolve() != default_dir.resolve()
    return {
        "default_directory": str(default_dir),
        "current_directory": str(active_dir),
        "is_custom": is_custom,
        "exists": active_dir.is_dir(),
    }


def set_export_directory_preference(directory: Optional[str] = None, reset_to_default: bool = False) -> Dict[str, Any]:
    """
    Configura una ruta personalizada para guardar los videos exportados o restaura la carpeta por defecto.
    Crea la carpeta inmediatamente para validar que la ruta sea válida y escribible.
    """
    default_dir = get_default_export_directory(ensure_exists=True)
    if reset_to_default or not (directory or "").strip():
        _save_persisted_custom_dir("")
        return {
            "default_directory": str(default_dir),
            "current_directory": str(default_dir),
            "is_custom": False,
            "exists": default_dir.is_dir(),
        }

    raw = (directory or "").strip().strip('"').strip("'")
    try:
        target = Path(raw).expanduser()
        if not target.is_absolute():
            target = _resolve_desktop_root() / target
        target.mkdir(parents=True, exist_ok=True)
        resolved = target.resolve()
    except Exception as exc:
        raise HTTPException(
            status_code=400,
            detail=f"No se pudo crear o acceder a la carpeta indicada ('{raw}'): {exc}",
        ) from exc

    is_custom = resolved != default_dir.resolve()
    _save_persisted_custom_dir(str(resolved) if is_custom else "")
    return {
        "default_directory": str(default_dir),
        "current_directory": str(resolved),
        "is_custom": is_custom,
        "exists": resolved.is_dir(),
    }


def select_export_directory_native_dialog(initial_dir: Optional[str] = None) -> Dict[str, Any]:
    """
    Abre un cuadro de diálogo nativo del sistema operativo para que el usuario elija
    visualmente cualquier carpeta donde guardar los videos exportados.
    """
    status_info = get_export_directory_status()
    start_dir = (initial_dir or status_info["current_directory"] or status_info["default_directory"]).strip()
    if not Path(start_dir).is_dir():
        start_dir = status_info["default_directory"]

    selected_path = ""
    if sys.platform == "win32":
        # Intentar primero mediante Tkinter en subproceso aislado (con ventana topmost)
        tk_script = (
            "import sys, tkinter as tk; from tkinter import filedialog; "
            "root = tk.Tk(); root.withdraw(); root.attributes('-topmost', True); "
            "folder = filedialog.askdirectory(initialdir=sys.argv[1], title='Seleccionar carpeta para guardar videos exportados de LSEC Studio'); "
            "root.destroy(); "
            "sys.stdout.buffer.write((folder or '').encode('utf-8'))"
        )
        try:
            proc = subprocess.run(
                [sys.executable, "-c", tk_script, start_dir],
                capture_output=True,
                timeout=120,
                check=False,
            )
            if proc.returncode == 0:
                selected_path = proc.stdout.decode("utf-8", errors="replace").strip()
        except Exception as exc:
            logger.debug("Aviso abriendo selector Tkinter: %s", exc)

    if not selected_path:
        return {
            "cancelled": True,
            **status_info,
        }

    norm_path = str(Path(selected_path).resolve())
    updated = set_export_directory_preference(directory=norm_path, reset_to_default=False)
    return {
        "cancelled": False,
        "selected_directory": updated["current_directory"],
        **updated,
    }


def open_export_directory_in_os(directory: Optional[str] = None, filename: Optional[str] = None) -> Dict[str, Any]:
    """Abre la carpeta de exportación en el Explorador de Archivos de Windows."""
    target_dir = resolve_export_target_directory(directory, ensure_exists=True)
    target_file = (target_dir / filename).resolve() if filename else None

    try:
        if sys.platform == "win32":
            if target_file and target_file.is_file():
                subprocess.Popen(["explorer.exe", f"/select,{str(target_file)}"])
            else:
                os.startfile(str(target_dir))  # type: ignore[attr-defined]
        return {
            "opened": True,
            "directory": str(target_dir),
            "file": str(target_file) if (target_file and target_file.is_file()) else None,
        }
    except Exception as exc:
        logger.warning("No se pudo abrir el explorador de archivos en %s: %s", target_dir, exc)
        return {
            "opened": False,
            "directory": str(target_dir),
            "error": str(exc),
        }


def sanitize_export_filename(filename: Optional[str], default_ext: str = ".mp4") -> str:
    """Limpia el nombre de archivo de salida asegurando extensión válida y caracteres seguros."""
    raw = (filename or "").strip()
    if not raw:
        raw = f"video_lsec_con_interprete_y_glosas{default_ext}"
    # Eliminar rutas o barras
    raw = Path(raw).name
    stem = Path(raw).stem
    ext = Path(raw).suffix.lower() or default_ext
    if not ext.startswith("."):
        ext = "." + ext
    safe_stem = re.sub(r'[<>:"/\\|?*\x00-\x1f]+', "_", stem).strip(" ._")
    if not safe_stem:
        safe_stem = "video_lsec_con_interprete_y_glosas"
    return f"{safe_stem}{ext}"


def save_video_bytes_to_export_dir(
    video_bytes: bytes,
    output_dir: Optional[str] = None,
    output_filename: Optional[str] = None,
    default_ext: str = ".mp4",
) -> Tuple[Path, Path, str]:
    """
    Guarda los bytes del video exportado en la carpeta destino (creándola automáticamente
    si no existe) y devuelve `(saved_file_path, target_dir, safe_filename)`.
    """
    target_dir = resolve_export_target_directory(output_dir, ensure_exists=True)
    # Garantizar creación automática incluso si fue borrada justo antes de exportar
    target_dir.mkdir(parents=True, exist_ok=True)

    safe_filename = sanitize_export_filename(output_filename, default_ext=default_ext)
    saved_path = (target_dir / safe_filename).resolve()

    try:
        saved_path.write_bytes(video_bytes)
        logger.info("✓ Video exportado guardado en disco: %s (%d bytes)", saved_path, len(video_bytes))
    except OSError as exc:
        logger.warning("Error escribiendo en '%s' (%s). Guardando en carpeta por defecto del Escritorio.", saved_path, exc)
        fallback_dir = get_default_export_directory(ensure_exists=True)
        fallback_dir.mkdir(parents=True, exist_ok=True)
        saved_path = (fallback_dir / safe_filename).resolve()
        saved_path.write_bytes(video_bytes)
        target_dir = fallback_dir

    return saved_path, target_dir, safe_filename


def encode_deterministic_mp4_response(
    video_bytes: bytes,
    audio_bytes: Optional[bytes] = None,
    target_fps: int = 30,
    output_dir: Optional[str] = None,
    output_filename: Optional[str] = None,
    save_to_disk: bool = True,
) -> Response:
    """
    Codifica un flujo de video (y audio opcional) a MP4 H.264 + AAC con FPS constante
    y guarda automáticamente el resultado en la carpeta de exportación (por defecto en el
    Escritorio o en la ruta personalizada elegida por el usuario).
    """
    if target_fps <= 0:
        target_fps = 30

    try:
        import av
    except ImportError as exc:
        raise HTTPException(status_code=500, detail=f"PyAV no disponible: {exc}")

    in_vid = av.open(io.BytesIO(video_bytes), mode="r")
    if not in_vid.streams.video:
        in_vid.close()
        raise HTTPException(status_code=400, detail="El archivo de video recibido no contiene pista de video.")

    in_vstream = in_vid.streams.video[0]
    width = in_vstream.width or 1280
    height = in_vstream.height or 720
    width = width - (width % 2)
    height = height - (height % 2)

    out_buf = io.BytesIO()
    out_container = av.open(out_buf, mode="w", format="mp4")
    out_vstream = out_container.add_stream("libx264", rate=target_fps)
    out_vstream.width = width
    out_vstream.height = height
    out_vstream.pix_fmt = "yuv420p"
    out_vstream.options = {"preset": "ultrafast", "crf": "20", "threads": "0"}

    in_aud = None
    out_astream = None
    audio_resampler = None
    aud_source_bytes = audio_bytes if audio_bytes else video_bytes
    try:
        cand_aud = av.open(io.BytesIO(aud_source_bytes), mode="r")
        if cand_aud.streams.audio:
            in_aud = cand_aud
            out_astream = out_container.add_stream("aac", rate=48000)
            out_astream.layout = "stereo"
            audio_resampler = av.AudioResampler(format="fltp", layout="stereo", rate=48000)
        else:
            cand_aud.close()
    except Exception:
        pass

    tb = Fraction(1, target_fps)
    frame_idx = 0
    for frame in in_vid.decode(video=0):
        new_vf = frame.reformat(width=width, height=height, format="yuv420p")
        new_vf.pts = frame_idx
        new_vf.time_base = tb
        for packet in out_vstream.encode(new_vf):
            out_container.mux(packet)
        frame_idx += 1

    for packet in out_vstream.encode(None):
        out_container.mux(packet)

    max_duration_sec = frame_idx / float(target_fps) if frame_idx > 0 else 0.0

    if in_aud and out_astream and audio_resampler:
        try:
            audio_pts = 0
            max_samples = int(max_duration_sec * 48000) + 2048 if max_duration_sec > 0 else 0
            for aframe in in_aud.decode(audio=0):
                aframe.pts = None
                resampled_frames = audio_resampler.resample(aframe)
                for rf in resampled_frames:
                    if max_samples > 0 and audio_pts >= max_samples:
                        break
                    rf.pts = audio_pts
                    rf.time_base = Fraction(1, 48000)
                    audio_pts += rf.samples
                    for packet in out_astream.encode(rf):
                        out_container.mux(packet)
                if max_samples > 0 and audio_pts >= max_samples:
                    break
            for packet in out_astream.encode(None):
                out_container.mux(packet)
        except Exception as exc:
            logger.warning("Aviso codificando pista de audio AAC: %s", exc)
        finally:
            in_aud.close()

    in_vid.close()
    out_container.close()

    mp4_data = out_buf.getvalue()
    headers = {
        "X-Export-FPS": str(target_fps),
        "X-Export-Frames": str(frame_idx),
        "Cache-Control": "no-store",
    }

    if save_to_disk and mp4_data:
        try:
            saved_path, target_dir, safe_filename = save_video_bytes_to_export_dir(
                video_bytes=mp4_data,
                output_dir=output_dir,
                output_filename=output_filename,
                default_ext=".mp4",
            )
            headers["X-Export-Saved-Path"] = urllib.parse.quote(str(saved_path))
            headers["X-Export-Saved-Dir"] = urllib.parse.quote(str(target_dir))
            headers["X-Export-Saved-Filename"] = urllib.parse.quote(safe_filename)
        except Exception as exc:
            logger.error("No se pudo guardar automáticamente el MP4 exportado en disco: %s", exc)

    return Response(
        content=mp4_data,
        media_type="video/mp4",
        headers=headers,
    )
