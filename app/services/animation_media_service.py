"""
Servicio de Medios, Validación de Integridad de Bitstream y Exportación MP4 Determinista.

Gestiona la verificación de integridad de contenedores MP4/WebM/MKV (_is_video_stream_healthy),
la resolución con fallback de videos Ultra HD e ilustraciones del Diccionario LSEC,
el enriquecimiento de animation.json al vuelo y el remuxeado/codificación a 30.0 FPS constantes.
"""

from __future__ import annotations

import io
import json
import logging
import re
import struct
import unicodedata
from fractions import Fraction
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from fastapi import HTTPException
from fastapi.responses import FileResponse, JSONResponse, Response

from app.services.animation_catalog_service import (
    CANDIDATE_PATHS,
    SENAS_CANDIDATE_PATHS,
    UHD_CANDIDATE_PATHS,
    _get_norm_dir_map,
    ensure_sign_animation_stabilized,
    get_animations_dir,
    get_available_signs,
    get_senas_dir,
    get_sign_metadata,
    get_sign_stroke_entry,
    get_uhd_dir,
    get_v25_dir,
    get_v26_dir,
    get_v27_dir,
    lsec_cnm,
    normalize_text,
)
from app.services.animation_fingerspelling_service import (
    get_baked_fingerspelling_folder,
    resolve_explicit_fingerspelling_grapheme,
)
from app.services.animation_lexical_resolver import resolve_gloss_to_sign

logger = logging.getLogger(__name__)

_video_health_cache: Dict[Tuple[str, float, int], bool] = {}


def _is_video_stream_healthy(video_path: Path) -> bool:
    """
    Verifica rápidamente que un archivo de video local sea íntegro y reproducible
    (cajas ISO-BMFF íntegras en MP4, primer cuadro decodificable, demuxeado completo
    desde el paquete #0 sin truncamiento y paquetes NAL H.264 íntegros).
    Cachea el resultado por (ruta, mtime, tamaño).
    """
    try:
        if not video_path or not video_path.is_file():
            return False
        st = video_path.stat()
        file_size = st.st_size
        if file_size < 1024:
            return False
        cache_key = (str(video_path), st.st_mtime, file_size)
        if cache_key in _video_health_cache:
            return _video_health_cache[cache_key]
    except Exception:
        return False

    healthy = True
    try:
        if video_path.suffix.lower() == ".mp4":
            with video_path.open("rb") as f:
                head = f.read(min(file_size, 65536))
                if b"moov" not in head and file_size <= 65536:
                    healthy = False
                elif b"moof" not in head:
                    if head.count(b"moov") > 1:
                        healthy = False
                    else:
                        pos = 0
                        moov_count = 0
                        mdat_count = 0
                        while pos + 8 <= file_size:
                            f.seek(pos)
                            hdr = f.read(16)
                            if len(hdr) < 8:
                                break
                            bsz, btype = struct.unpack(">I4s", hdr[:8])
                            if bsz == 1 and len(hdr) >= 16:
                                bsz = struct.unpack(">Q", hdr[8:16])[0]
                            elif bsz == 0:
                                bsz = file_size - pos
                            if bsz < 8 or pos + bsz > file_size:
                                healthy = False
                                break
                            if btype == b"moov":
                                moov_count += 1
                            elif btype == b"mdat":
                                mdat_count += 1
                            pos += bsz
                        if moov_count != 1 or mdat_count < 1:
                            healthy = False

        if healthy:
            import av
            codec = ""
            expected_frames = 0
            expected_duration_sec = 0.0
            with av.open(str(video_path), mode="r", timeout=3.0) as container:
                if not container.streams.video:
                    healthy = False
                else:
                    vs = container.streams.video[0]
                    codec = vs.codec_context.name or ""
                    expected_frames = vs.frames or 0
                    if vs.duration is not None and vs.time_base is not None:
                        expected_duration_sec = float(vs.duration * vs.time_base)
                    elif container.duration is not None:
                        expected_duration_sec = float(container.duration) / 1_000_000.0
                    first_frame = next(container.decode(video=0), None)
                    if first_frame is None:
                        healthy = False

            if healthy:
                with av.open(str(video_path), mode="r", timeout=3.0) as c2:
                    vs2 = c2.streams.video[0]
                    tb2 = float(vs2.time_base) if vs2.time_base is not None else 0.0
                    total_pkts = 0
                    max_pts_sec = 0.0
                    for pkt in c2.demux(video=0):
                        if pkt.dts is None and pkt.pts is None:
                            continue
                        total_pkts += 1
                        pts_val = pkt.pts if pkt.pts is not None else pkt.dts
                        if pts_val is not None and tb2 > 0:
                            end_t = float(pts_val + (pkt.duration or 0)) * tb2
                            if end_t > max_pts_sec:
                                max_pts_sec = end_t
                        b = bytes(pkt)
                        n = len(b)
                        if n == 0:
                            healthy = False
                            break
                        if codec == "h264" and b[:4] != b"\x00\x00\x00\x01" and b[:3] != b"\x00\x00\x01":
                            pos = 0
                            while pos < n:
                                if pos + 4 > n:
                                    healthy = False
                                    break
                                nal_sz = struct.unpack(">I", b[pos : pos + 4])[0]
                                if nal_sz <= 0 or pos + 4 + nal_sz > n:
                                    healthy = False
                                    break
                                pos += 4 + nal_sz
                            if not healthy:
                                break
                    if healthy:
                        if total_pkts == 0:
                            healthy = False
                        elif expected_frames > 0 and total_pkts < expected_frames:
                            healthy = False
                        elif expected_duration_sec > 0.5 and max_pts_sec > 0 and max_pts_sec < expected_duration_sec * 0.75:
                            healthy = False
    except ImportError:
        healthy = True
    except Exception:
        healthy = False

    _video_health_cache[cache_key] = healthy
    return healthy


def resolve_sign_animation_response(sign_name: str, version: Optional[str] = None):
    """Localiza, enriquece y sirve el archivo animation.json para una seña específica."""
    clean_name = sign_name.strip()
    v27_dir = get_v27_dir()
    v26_dir = get_v26_dir()
    v25_dir = get_v25_dir()

    if version == "2.5":
        search_dirs = [v25_dir]
    elif version == "2.6":
        search_dirs = [d for d in (v26_dir, v25_dir) if d]
    else:
        search_dirs = [d for d in (v27_dir, v26_dir, v25_dir) if d]

    anim_file: Optional[Path] = None
    resolved_name: str = clean_name
    if version == "2.5":
        version_served = "2.5"
    elif version == "2.6":
        version_served = "2.6" if v26_dir else "2.5"
    else:
        version_served = "2.7" if v27_dir else ("2.6" if v26_dir else "2.5")
    match_type: str = "exact"
    status_label: str = "EXACT"
    needs_review: bool = False
    warning_msg: Optional[str] = None

    name_variants = list(dict.fromkeys([
        clean_name,
        unicodedata.normalize("NFC", clean_name),
        unicodedata.normalize("NFD", clean_name),
    ]))

    for bdir in search_dirs:
        if not bdir or not bdir.is_dir():
            continue
        for variant in name_variants:
            cand = bdir / variant / "animation.json"
            if cand.is_file():
                anim_file = cand
                resolved_name = unicodedata.normalize("NFC", variant)
                if v27_dir and bdir == v27_dir:
                    version_served = "2.7"
                elif v26_dir and bdir == v26_dir:
                    version_served = "2.6"
                else:
                    version_served = "2.5"
                break
        if anim_file:
            break

    res = resolve_gloss_to_sign(clean_name, version=version or "2.7", include_animation=False)
    if res.get("found") and res.get("anim_path"):
        if not anim_file:
            anim_file = Path(res["anim_path"])
            resolved_name = res.get("resolved_gloss") or resolved_name
            version_served = res.get("version_served") or version_served
            match_type = res.get("match_type") or match_type
            status_label = res.get("status") or status_label
            needs_review = bool(res.get("needs_review", False))
            warning_msg = res.get("warning")
        elif res.get("match_type") == "exact":
            resolved_name = res.get("resolved_gloss") or resolved_name
            status_label = res.get("status") or status_label
            needs_review = bool(res.get("needs_review", False))
            warning_msg = res.get("warning")

    if not anim_file or not anim_file.is_file():
        fs_folder = get_baked_fingerspelling_folder(clean_name)
        if fs_folder and (fs_folder / "animation.json").is_file():
            anim_file = fs_folder / "animation.json"
            resolved_name = fs_folder.name
            version_served = "2.7"
            match_type = "fingerspelling_baked_v27"
            status_label = "EXACT"

    if not anim_file or not anim_file.is_file():
        raise HTTPException(
            status_code=404,
            detail=f"Animación no encontrada para la seña '{sign_name}'. Verifique /api/v1/animations/list.",
        )

    safe_name = re.sub(r"[^a-zA-Z0-9_\-]", "_", resolved_name)
    headers = {
        "Cache-Control": "no-cache",
        "X-Sign-Resolved": unicodedata.normalize("NFKD", resolved_name).encode("ascii", "ignore").decode("ascii"),
        "X-Sign-Version": str(version_served),
        "X-Sign-Status": str(status_label),
        "X-Sign-Match-Type": str(match_type),
        "X-Sign-Needs-Review": "true" if needs_review else "false",
    }
    if warning_msg:
        headers["X-Sign-Warning"] = unicodedata.normalize("NFKD", warning_msg).encode("ascii", "ignore").decode("ascii")

    try:
        raw_data = json.loads(anim_file.read_text(encoding="utf-8"))
        if isinstance(raw_data, dict):
            cat_meta = get_sign_metadata(resolved_name)
            cnm_ver = getattr(lsec_cnm, "CNM_STANDARD_VERSION", "1.1")
            if lsec_cnm is not None and raw_data.get("metadata", {}).get("nonManualStandard", {}).get("version") != cnm_ver:
                lsec_cnm.standardize_animation_dict(raw_data, sign_name=resolved_name, catalog_entry=cat_meta)
            meta = raw_data.setdefault("metadata", {})
            meta["version_served"] = version_served
            meta["resolved_sign"] = resolved_name
            meta["requested_gloss"] = clean_name
            meta["match_type"] = match_type
            meta["status_label"] = status_label
            meta["needs_review"] = needs_review
            meta["warning"] = warning_msg
            if version_served == "2.7":
                meta["pipelineVersion"] = "2.7_Estandarizado"
                stroke_entry = get_sign_stroke_entry(resolved_name)
                if stroke_entry:
                    existing_stroke = meta.get("stroke") if isinstance(meta.get("stroke"), dict) else {}
                    merged_stroke = dict(stroke_entry)
                    merged_stroke.update(existing_stroke)
                    meta["stroke"] = merged_stroke
                if cat_meta and isinstance(cat_meta.get("hand_standardization"), dict):
                    h_std = dict(cat_meta["hand_standardization"])
                    if isinstance(meta.get("handStandardization"), dict):
                        h_std.update(meta["handStandardization"])
                    if "distance_reduction_pct" in h_std and "reduction_pct" not in h_std:
                        h_std["reduction_pct"] = h_std["distance_reduction_pct"]
                    meta["handStandardization"] = h_std
                ensure_sign_animation_stabilized(
                    raw_data,
                    sign_name=resolved_name,
                    anim_file=anim_file,
                    cat_meta=cat_meta,
                    persist_to_disk=True,
                )
                if isinstance(meta.get("stroke"), dict):
                    s_cur = meta["stroke"]
                    headers["X-Sign-Stroke-Window"] = f"{s_cur.get('strokeStart', 0.0)}-{s_cur.get('strokeEnd', 0.0)}"
            cnm_std = meta.get("nonManualStandard", {})
            headers["X-Sign-Facial-Archetype"] = str(cnm_std.get("archetype", "neutral"))
            headers["X-Sign-Explicit-Expression"] = "true" if cnm_std.get("hasExplicitFacialExpression") else "false"
            hand_std = meta.get("handStandardization", {})
            if isinstance(hand_std, dict) and hand_std:
                headers["X-Sign-Hand-Standardization"] = str(hand_std.get("status", ""))
                headers["X-Sign-Hand-Template"] = str(hand_std.get("template_id") or (cat_meta.get("hand_variant") if cat_meta else "") or "")
            if isinstance(meta.get("kinematicStabilizer"), dict):
                headers["X-Sign-Stabilizer-Version"] = str(meta["kinematicStabilizer"].get("version", ""))
            return JSONResponse(content=raw_data, headers=headers)
    except Exception as exc:
        logger.warning("Aviso normalizando metadata al vuelo para %s: %s", resolved_name, exc)

    return FileResponse(
        path=str(anim_file),
        media_type="application/json",
        filename=f"{safe_name}_animation.json",
        headers=headers,
    )


def resolve_sign_qa_response(sign_name: str, version: Optional[str] = None):
    """Obtiene el archivo qa.json o la metadata QA en memoria para una seña."""
    clean_name = sign_name.strip()
    v27_dir = get_v27_dir()
    v26_dir = get_v26_dir()
    v25_dir = get_v25_dir()

    if version == "2.5":
        search_dirs = [v25_dir]
    elif version == "2.6":
        search_dirs = [d for d in (v26_dir, v25_dir) if d]
    else:
        search_dirs = [d for d in (v27_dir, v26_dir, v25_dir) if d]

    qa_file: Optional[Path] = None
    name_variants = list(dict.fromkeys([
        clean_name,
        unicodedata.normalize("NFC", clean_name),
        unicodedata.normalize("NFD", clean_name),
    ]))

    for bdir in search_dirs:
        if not bdir or not bdir.is_dir():
            continue
        for variant in name_variants:
            cand = bdir / variant / "qa.json"
            if cand.is_file():
                qa_file = cand
                break
        if qa_file:
            break

    if not qa_file:
        norm_target = normalize_text(clean_name)
        for candidate in get_available_signs():
            if normalize_text(candidate) == norm_target:
                for bdir in search_dirs:
                    if not bdir or not bdir.is_dir():
                        continue
                    for variant in (candidate, unicodedata.normalize("NFD", candidate)):
                        cand = bdir / variant / "qa.json"
                        if cand.is_file():
                            qa_file = cand
                            break
                    if qa_file:
                        break
                if qa_file:
                    break

    if not qa_file or not qa_file.is_file():
        meta = get_sign_metadata(clean_name)
        if meta and meta.get("qa"):
            return JSONResponse(content=meta["qa"])
        raise HTTPException(status_code=404, detail=f"Métricas QA no encontradas para '{sign_name}'.")

    return FileResponse(path=str(qa_file), media_type="application/json")


def resolve_sign_info_response(sign_name: str):
    """Obtiene la ficha lingüística info.json o la metadata enriquecida en caché."""
    clean_name = sign_name.strip()
    meta = get_sign_metadata(clean_name)

    if meta:
        return JSONResponse(content=meta)

    for base_dir in [d for d in (get_v27_dir(), get_v26_dir(), get_v25_dir()) if d]:
        for variant in (clean_name, unicodedata.normalize("NFC", clean_name), unicodedata.normalize("NFD", clean_name)):
            info_file = base_dir / variant / "info.json"
            if info_file.is_file():
                return FileResponse(path=str(info_file), media_type="application/json")

    fs_folder = get_baked_fingerspelling_folder(clean_name)
    if fs_folder and (fs_folder / "info.json").is_file():
        return FileResponse(path=str(fs_folder / "info.json"), media_type="application/json")

    raise HTTPException(status_code=404, detail=f"Ficha lingüística no encontrada para '{sign_name}'.")


def resolve_sign_video_response(sign_name: str):
    """Busca y sirve en streaming el video MP4/WebM/MKV original Ultra HD o de respaldo."""
    clean_name = sign_name.strip()
    meta = get_sign_metadata(clean_name)

    candidates: List[str] = [clean_name]
    if meta:
        for k in ("sign", "palabra", "slug"):
            val = meta.get(k)
            if val and val not in candidates:
                candidates.append(val)

    res = resolve_gloss_to_sign(clean_name, include_animation=False)
    if res.get("found") and res.get("resolved_gloss"):
        rg = res["resolved_gloss"]
        if rg not in candidates:
            candidates.append(rg)
        rg_base = re.sub(r"__\d+$", "", rg).strip()
        if rg_base and rg_base not in candidates:
            candidates.append(rg_base)

    uhd_dirs = [p for p in [get_uhd_dir()] if p is not None]
    fallback_dirs = [p for p in [get_senas_dir()] if p is not None]

    def _find_healthy_video_in_dirs(dirs: List[Path], filenames: Tuple[str, ...]) -> Optional[Path]:
        expanded_cands: List[str] = []
        for c in candidates:
            if not c:
                continue
            for v in (c, unicodedata.normalize("NFC", c), unicodedata.normalize("NFD", c)):
                if v not in expanded_cands:
                    expanded_cands.append(v)
        norm_candidates = [normalize_text(c) for c in candidates if c and normalize_text(c)]
        for s_dir in dirs:
            if not s_dir.is_dir():
                continue

            checked_paths: set[str] = set()

            for cand in expanded_cands:
                for fname in filenames:
                    v_path = s_dir / cand / fname
                    if v_path.is_file():
                        checked_paths.add(str(v_path.resolve()))
                        if _is_video_stream_healthy(v_path):
                            return v_path
                        logger.warning("Video dañado detectado en %s; buscando respaldo sano.", v_path)

            norm_map = _get_norm_dir_map(s_dir)
            for nc in norm_candidates:
                for sub in norm_map.get(nc, ()):
                    for fname in filenames:
                        v_path = sub / fname
                        if v_path.is_file():
                            rp = str(v_path.resolve())
                            if rp in checked_paths:
                                continue
                            checked_paths.add(rp)
                            if _is_video_stream_healthy(v_path):
                                return v_path
                            logger.warning("Video dañado detectado en %s; buscando respaldo sano.", v_path)
        return None

    target_video: Optional[Path] = _find_healthy_video_in_dirs(uhd_dirs, ("video.mp4",))
    source_tier = "ultra_hd"

    if target_video is None:
        target_video = _find_healthy_video_in_dirs(fallback_dirs, ("video.mp4", "video.webm", "video.mkv"))
        if target_video is not None:
            source_tier = "fallback_senas"

    if target_video and target_video.is_file():
        safe_name = re.sub(r"[^a-zA-Z0-9_\-]", "_", clean_name)
        ext = target_video.suffix.lower()
        media_type = "video/mp4"
        if ext == ".webm":
            media_type = "video/webm"
        elif ext == ".mkv":
            media_type = "video/x-matroska"

        return FileResponse(
            path=str(target_video),
            media_type=media_type,
            filename=f"{safe_name}_original_uhd{ext or '.mp4'}",
            headers={
                "Accept-Ranges": "bytes",
                "Cache-Control": "public, max-age=7200",
                "X-Video-Source": source_tier,
            },
        )

    yt_url = meta.get("video_url") if meta else None
    yt_id = meta.get("video_id") if meta else None

    raise HTTPException(
        status_code=404,
        detail={
            "message": f"Video MP4 local no encontrado para '{sign_name}'.",
            "youtube_url": yt_url,
            "video_id": yt_id,
            "has_remote": bool(yt_url or yt_id),
        },
    )


def resolve_sign_illustration_response(sign_name: str):
    """Busca y sirve la imagen de ilustración oficial (PNG/JPG/WebP) de la seña desde el disco local."""
    clean_name = sign_name.strip()
    meta = get_sign_metadata(clean_name)

    base_candidates = [clean_name]
    if meta:
        for k in ("sign", "palabra", "slug"):
            val = meta.get(k)
            if val and val not in base_candidates:
                base_candidates.append(val)

    candidates: List[str] = []
    for c in base_candidates:
        if not c:
            continue
        for v in (c, unicodedata.normalize("NFC", c), unicodedata.normalize("NFD", c)):
            if v not in candidates:
                candidates.append(v)

    raw_search_dirs: List[Optional[Path]] = [
        get_animations_dir(),
        get_v27_dir(),
        get_uhd_dir(),
        get_senas_dir(),
        get_v26_dir(),
        *CANDIDATE_PATHS,
        *UHD_CANDIDATE_PATHS,
        *SENAS_CANDIDATE_PATHS,
    ]
    search_dirs: List[Path] = []
    for p in raw_search_dirs:
        if p is not None and p not in search_dirs:
            search_dirs.append(p)

    target_img: Optional[Path] = None
    norm_candidates = [normalize_text(c) for c in base_candidates if c and normalize_text(c)]

    for s_dir in search_dirs:
        if not s_dir.is_dir():
            continue

        for cand in candidates:
            for ext in ("ilustracion.png", "ilustracion.jpg", "ilustracion.jpeg", "ilustracion.webp"):
                p = s_dir / cand / ext
                if p.is_file():
                    target_img = p
                    break
            if target_img:
                break
        if target_img:
            break

        norm_map = _get_norm_dir_map(s_dir)
        for nc in norm_candidates:
            for sub in norm_map.get(nc, ()):
                for ext in ("ilustracion.png", "ilustracion.jpg", "ilustracion.jpeg", "ilustracion.webp"):
                    p = sub / ext
                    if p.is_file():
                        target_img = p
                        break
                if target_img:
                    break
            if target_img:
                break
        if target_img:
            break

    if target_img and target_img.is_file():
        safe_name = re.sub(r"[^a-zA-Z0-9_\-]", "_", clean_name)
        media_type = "image/png"
        if target_img.suffix.lower() in [".jpg", ".jpeg"]:
            media_type = "image/jpeg"
        elif target_img.suffix.lower() == ".webp":
            media_type = "image/webp"

        return FileResponse(
            path=str(target_img),
            media_type=media_type,
            filename=f"{safe_name}_ilustracion{target_img.suffix}",
            headers={"Cache-Control": "public, max-age=86400"},
        )

    remote_url = meta.get("imagen_url") if meta else None
    raise HTTPException(
        status_code=404,
        detail={
            "message": f"Ilustración local no encontrada para '{sign_name}'.",
            "remote_url": remote_url,
            "has_remote": bool(remote_url),
        },
    )


def encode_deterministic_mp4_response(
    video_bytes: bytes,
    audio_bytes: Optional[bytes] = None,
    target_fps: int = 30,
) -> Response:
    """Codifica un flujo de video (y audio opcional) a MP4 H.264 + AAC con FPS constante."""
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
    out_vstream.options = {"preset": "ultrafast", "crf": "20"}

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
        rgb = frame.to_ndarray(format="rgb24")
        if rgb.shape[1] != width or rgb.shape[0] != height:
            rgb = rgb[:height, :width, :]
        new_vf = av.VideoFrame.from_ndarray(rgb, format="rgb24")
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
    return Response(
        content=mp4_data,
        media_type="video/mp4",
        headers={
            "X-Export-FPS": str(target_fps),
            "X-Export-Frames": str(frame_idx),
            "Cache-Control": "no-store",
        },
    )
