"""
Herramienta de medición de unidades de discurso (Fase 1 del plan de análisis por idea completa).

Procesa EXCLUSIVAMENTE los videos reales de `Videos de Prueba/` (AGENTS.md: sin mocks):
  1. ASR real (Whisper vía /api/v1/transcribe del servidor en 127.0.0.1:8000); la transcripción se
     cachea por hash SHA-1 del archivo en `app/tests/tools/.asr_cache/` y se regenera sola si el
     video cambia.
  2. Traducción en proceso con el código actual (`LSECTranslatorService`), de modo que refleja cambios
     del backend sin reiniciar el servidor.

Uso:
    python -m app.tests.tools.measure_discourse_units [--out ruta.json] [1.mp4 2.mp4 3.mp4]
"""
from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, List

from app.core.schemas import TranscriptionResult
from app.services.nlp_service import LSECTranslatorService

ROOT = Path(__file__).resolve().parents[4]
VIDEOS_DIR = ROOT / "Videos de Prueba"
CACHE_DIR = Path(__file__).resolve().parent / ".asr_cache"
SERVER = "http://127.0.0.1:8000"

CONTRAST_RELATIONS = {"but", "because", "not_only", "more_than", "also"}


def _sha1(path: Path) -> str:
    h = hashlib.sha1()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def transcribe_real_video(video: Path) -> TranscriptionResult:
    """ASR real del video (con caché por hash del contenido)."""
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    cache = CACHE_DIR / f"{video.stem}_{_sha1(video)[:12]}.json"
    if cache.exists():
        return TranscriptionResult.model_validate_json(cache.read_text(encoding="utf-8"))
    proc = subprocess.run(
        ["curl.exe", "-s", "-X", "POST", "-F", f"file=@{video}", f"{SERVER}/api/v1/transcribe"],
        capture_output=True, timeout=600,
    )
    if proc.returncode != 0 or not proc.stdout:
        raise RuntimeError(f"ASR real falló para {video.name}: {proc.stderr.decode('utf-8', 'replace')}")
    data = json.loads(proc.stdout.decode("utf-8"))
    tr = TranscriptionResult.model_validate(data)
    cache.write_text(tr.model_dump_json(), encoding="utf-8")
    return tr


def compute_metrics(svc: LSECTranslatorService, video: Path, tr: TranscriptionResult) -> Dict[str, Any]:
    out = asyncio.run(
        svc.translate_to_gloss(
            tr.text, mode="detailed", paraphrase_budget="compact",
            source_audio_duration=tr.duration_seconds, transcription=tr,
        )
    )
    glosses = sorted(out.glosses, key=lambda g: g.order)
    props = list(out.semantic_propositions or [])
    spans = list(out.non_manual_spans or [])
    sentences = svc._segmenter._split_sentences(out.normalized_text or tr.text)

    adjacent_dups: List[str] = []
    for a, b in zip(glosses, glosses[1:]):
        if a.gloss == b.gloss:
            adjacent_dups.append(a.gloss)

    glosses_by_prop: Dict[str, List[Any]] = {}
    for g in glosses:
        glosses_by_prop.setdefault(g.proposition_id, []).append(g)
    single_gloss_props = [p.id for p in props if len(glosses_by_prop.get(p.id, [])) <= 1]

    contrast_span_props = {s.proposition_id for s in spans if s.proposition_id and s.type == "contrast"}
    rel_without_connector = []
    rel_without_any_marker = []
    for p in props:
        if p.discourse_relation in CONTRAST_RELATIONS:
            has_connector = any(
                (g.lexical_strategy == "discourse_connector") for g in glosses_by_prop.get(p.id, [])
            )
            has_span = p.id in contrast_span_props
            if not has_connector:
                rel_without_connector.append(f"{p.id}:{p.discourse_relation}")
            if not has_connector and not has_span:
                rel_without_any_marker.append(f"{p.id}:{p.discourse_relation}")

    dur = max(0.1, tr.duration_seconds or 0.1)
    return {
        "video": video.name,
        "duration_sec": round(dur, 2),
        "sentences": len(sentences),
        "propositions": len(props),
        "propositions_per_sentence": round(len(props) / max(1, len(sentences)), 2),
        "glosses": len(glosses),
        "glosses_per_sec": round(len(glosses) / dur, 2),
        "adjacent_identical_glosses": len(adjacent_dups),
        "adjacent_identical_list": adjacent_dups,
        "single_gloss_propositions": len(single_gloss_props),
        "relations_without_connector": rel_without_connector,
        "relations_without_any_marker": rel_without_any_marker,
        "sentence_id_coverage": sum(1 for g in glosses if getattr(g, "sentence_id", None) is not None),
        "condensation_actions": len(getattr(out, "condensation_log", []) or []),
        "condensation_applied": sum(1 for c in (getattr(out, "condensation_log", []) or []) if c.get("applied")),
        "condensation_rules": sorted({c.get("rule_id") for c in (getattr(out, "condensation_log", []) or [])}),
        "gloss_sequence": [g.gloss for g in glosses],
    }


def main(argv: List[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("videos", nargs="*", default=["1.mp4", "2.mp4", "3.mp4"])
    ap.add_argument("--out", default=None)
    args = ap.parse_args(argv)

    svc = LSECTranslatorService()
    results = []
    for name in args.videos:
        vp = VIDEOS_DIR / name
        if not vp.exists():
            print(f"[WARN] No existe {vp}", file=sys.stderr)
            continue
        tr = transcribe_real_video(vp)
        m = compute_metrics(svc, vp, tr)
        results.append(m)
        brief = {k: v for k, v in m.items() if k not in ("gloss_sequence", "adjacent_identical_list")}
        print(json.dumps(brief, ensure_ascii=False))
        if m["adjacent_identical_list"]:
            print("   duplicados adyacentes:", m["adjacent_identical_list"])
    if args.out:
        Path(args.out).write_text(json.dumps(results, ensure_ascii=False, indent=1), encoding="utf-8")
        print("Informe:", args.out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
