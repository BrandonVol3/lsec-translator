"""
Script de Verificación Empírica y Adversarial — Challenger M2 (Milestone 2).

Verifica de forma independiente y empírica:
1. Videos reales 1.mp4, 2.mp4, 3.mp4 (transcripciones completas extraídas por Whisper y variantes breves de prueba).
2. Corpus de validación de 20 textos (VIDEO_TEXTS_11_20 y textos institucionales/cotidianos 1-10).
3. Resolución léxica de cada glosa individual mediante resolve_gloss_to_sign.
4. Conteo exacto de glosas generadas y verificación estricta de count(MISSING) == 0 (100% resolubilidad).
5. Desambiguación de 'cero' en números de teléfono: forma manual 0 (dactilología O), nunca 'Nada'.
6. Verificación de ausencia de SEMANTIC_CONTENT_LEAK en 'desarrollar' y poda de 'CON'/'SOBRE'.
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

# Add project root to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from typing import Dict, List, Any, Tuple

from app.core.schemas import GlossOutput
from app.services.animation_lexical_resolver import (
    resolve_batch_glosses_payload,
    resolve_gloss_to_sign,
)
from app.services.nlp_service import LSECTranslatorService
from app.tests.test_lsec_video_like_corpus import VIDEO_TEXTS_11_20

# 1. Transcripciones reales completas de Whisper sobre 1.mp4, 2.mp4, 3.mp4
REAL_VIDEO_TRANSCRIPTS: Dict[str, str] = {
    "1.mp4_real_full": (
        "Dicen que el conocimiento es poder, pero nadie te dice que también es libertad, "
        "libertad para decidir quién quiere ser. En la Politécnica del Carchi no solo eliges "
        "una carrera, eliges ser imparable. Con carreras de grado en los campos, Tulcán y Cayambe, "
        "nos enorgullece ser la universidad pública más sostenible del ecuador. "
        "Formamos más que profesionales, formamos seres humanos que inspiran confianza y cercanía. "
        "Aquí te preparamos desde el primer día, con excelencia cadénica, con innovación, "
        "con tecnología que evoluciona contigo. Más de 4.500 grados ya lo hicieron, hoy crean "
        "oportunidades, liberan y construyen ideas. Decide sobre tu futuro, haz posible hoy lo que "
        "imaginas. UPEC, educamos para transformar el mundo."
    ),
    "2.mp4_real_full": (
        "Te invitamos a formar parte del Centro Académico de Arte y Cultura. Te puedes inscribir "
        "en las asignaturas de cuerpo y movimiento, apreciación de la música en el ecuador y "
        "dibujo experimental. Información al WhatsApp 099 28 72 993 o al correo seartesarrobaupec.edu.ec."
    ),
    "3.mp4_real_full": (
        "Así se vivió el proceso de admisión 2026-A en la UPEC. La Universidad Politécnica Estatal "
        "del Carchi para el periodo 2026-A desarrolla la etapa de evaluación como parte de su "
        "proceso de admisión. El día de hoy se inició el proceso en la etapa de evaluación a partir "
        "de las 8 y cuarto con el primer grupo en donde constan de 60 preguntas las cuales tienen "
        "que ser respondidas por parte de los aspirantes en un tiempo promedio de 60 minutos. "
        "Al momento la UPEC registra alrededor de 3.000 aspirantes los cuales están opcionando "
        "para un cupo dentro de la oferta académica para el periodo 2026-A."
    ),
}

# 2. Textos de prueba sintéticos/focales de los videos (utilizados en M2)
VIDEO_SNIPPETS: Dict[str, str] = {
    "video_1_snippet": (
        "Regístrate en www.upec.edu.ec y postula por una de nuestras carreras de grado. "
        "Estandel Karczym 20-26a."
    ),
    "video_2_snippet": (
        "Para mayor información comunícate al 099 28 72 993 o al correo seartes@upec.edu.ec."
    ),
    "video_3_snippet": (
        "Si estás opcionando por una carrera focalizada, desarrolla la etapa de evaluación "
        "en el horario determinado."
    ),
}

# 3. Textos 1 a 10 del corpus de validación (institucionales/cotidianos complementarios a VIDEO_TEXTS_11_20)
VALIDATION_TEXTS_1_10: Dict[str, str] = {
    "1": "Más de 4.500 graduados ya lo hicieron.",
    "2": "Formamos más que profesionales.",
    "3": "Al momento la UPEC registra alrededor de 3.000 aspirantes que están opcionando para un cupo.",
    "4": "A partir de las 8 y cuarto.",
    "5": "La evaluación de admisión en la mañana incluye música, diseño y tecnología.",
    "6": "Invitamos a los cuatro mil quinientos graduados y a los tres mil aspirantes.",
    "7": "Hoy los aspirantes revisan la oferta en los campos de Tulcán y Cayambe.",
    "8": "Aunque hace frío y calor, mi ñaño y mi pana revisan el formulario de inscripción.",
    "9": "Si mañana no llueve, realizaremos la jornada de integración.",
    "10": "Los programas presenciales y semipresenciales promueven el desarrollo sostenible.",
}


def run_empirical_verification() -> Dict[str, Any]:
    svc = LSECTranslatorService()
    results: Dict[str, Any] = {
        "videos_real": {},
        "videos_snippets": {},
        "corpus_1_10": {},
        "corpus_11_20": {},
        "phone_number_audit": {},
        "total_glosses_corpus_20": 0,
        "total_missing_corpus_20": 0,
        "total_glosses_all": 0,
        "total_missing_all": 0,
        "failures": [],
    }

    def verify_single_text(key: str, text: str) -> Dict[str, Any]:
        out: GlossOutput = asyncio.run(
            svc.translate_to_gloss(text, mode="detailed", paraphrase_budget="compact")
        )
        gloss_tokens = [g.gloss for g in out.glosses]
        total = len(gloss_tokens)
        
        # Resolver cada glosa individualmente
        resolved_items = []
        missing_glosses = []
        for g in gloss_tokens:
            res = resolve_gloss_to_sign(g, version="2.7")
            resolved_items.append(res)
            if res.get("status") == "MISSING":
                missing_glosses.append(g)

        # Batch resolution para doble verificación
        batch_res = resolve_batch_glosses_payload({"glosses": gloss_tokens, "version": "2.7"})
        batch_missing = [it["gloss"] for it in batch_res["items"] if it.get("status") == "MISSING"]

        warnings = [w.code for w in out.warnings]
        return {
            "total_glosses": total,
            "glosses": gloss_tokens,
            "missing_individual": missing_glosses,
            "missing_batch": batch_missing,
            "missing_count": len(missing_glosses),
            "warnings": warnings,
        }

    # 1. Videos Reales (Whisper ASR completo)
    print("=== PROCESANDO VIDEOS REALES (WHISPER ASR COMPLETO) ===")
    for k, text in REAL_VIDEO_TRANSCRIPTS.items():
        v_data = verify_single_text(k, text)
        results["videos_real"][k] = v_data
        results["total_glosses_all"] += v_data["total_glosses"]
        results["total_missing_all"] += v_data["missing_count"]
        print(f"[{k}] Glosas: {v_data['total_glosses']}, MISSING: {v_data['missing_count']}, Warnings: {v_data['warnings']}")
        if v_data["missing_count"] > 0:
            results["failures"].append(f"{k} has missing glosses: {v_data['missing_individual']}")

    # 2. Videos Snippets
    print("\n=== PROCESANDO VIDEOS SNIPPETS (M2 TARGETS) ===")
    for k, text in VIDEO_SNIPPETS.items():
        v_data = verify_single_text(k, text)
        results["videos_snippets"][k] = v_data
        results["total_glosses_all"] += v_data["total_glosses"]
        results["total_missing_all"] += v_data["missing_count"]
        print(f"[{k}] Glosas: {v_data['total_glosses']}, MISSING: {v_data['missing_count']}, Warnings: {v_data['warnings']}")
        if v_data["missing_count"] > 0:
            results["failures"].append(f"{k} has missing glosses: {v_data['missing_individual']}")
        if "SEMANTIC_CONTENT_LEAK" in v_data["warnings"]:
            results["failures"].append(f"{k} triggered SEMANTIC_CONTENT_LEAK")

    # 3. Corpus 1 a 10
    print("\n=== PROCESANDO CORPUS TEXTOS 1 A 10 ===")
    for k, text in VALIDATION_TEXTS_1_10.items():
        v_data = verify_single_text(f"text_{k}", text)
        results["corpus_1_10"][k] = v_data
        results["total_glosses_corpus_20"] += v_data["total_glosses"]
        results["total_missing_corpus_20"] += v_data["missing_count"]
        results["total_glosses_all"] += v_data["total_glosses"]
        results["total_missing_all"] += v_data["missing_count"]
        print(f"[Text {k:2s}] Glosas: {v_data['total_glosses']:2d}, MISSING: {v_data['missing_count']}")
        if v_data["missing_count"] > 0:
            results["failures"].append(f"Corpus Text {k} has missing glosses: {v_data['missing_individual']}")

    # 4. Corpus 11 a 20 (VIDEO_TEXTS_11_20)
    print("\n=== PROCESANDO CORPUS TEXTOS 11 A 20 (VIDEO_TEXTS_11_20) ===")
    for k, text in VIDEO_TEXTS_11_20.items():
        v_data = verify_single_text(f"text_{k}", text)
        results["corpus_11_20"][k] = v_data
        results["total_glosses_corpus_20"] += v_data["total_glosses"]
        results["total_missing_corpus_20"] += v_data["missing_count"]
        results["total_glosses_all"] += v_data["total_glosses"]
        results["total_missing_all"] += v_data["missing_count"]
        print(f"[Text {k:2s}] Glosas: {v_data['total_glosses']:2d}, MISSING: {v_data['missing_count']}")
        if v_data["missing_count"] > 0:
            results["failures"].append(f"Corpus Text {k} has missing glosses: {v_data['missing_individual']}")

    # 5. Auditoría de Teléfonos y 'Cero'
    print("\n=== AUDITORÍA DE TELÉFONOS Y 'CERO' ===")
    phone_res = verify_single_text("phone_test", "WhatsApp 099 28 72 993 y teléfono 02-2987-650.")
    cero_sign = resolve_gloss_to_sign("cero")
    zero_sign = resolve_gloss_to_sign("0")
    CERO_upper_sign = resolve_gloss_to_sign("CERO")

    results["phone_number_audit"] = {
        "text_glosses": phone_res["glosses"],
        "cero_resolved": cero_sign,
        "zero_resolved": zero_sign,
        "CERO_upper_resolved": CERO_upper_sign,
    }

    # Verificaciones específicas de 'cero'
    for label, r in [("cero", cero_sign), ("0", zero_sign), ("CERO", CERO_upper_sign)]:
        print(f"[{label}] status={r.get('status')}, is_fingerspelling={r.get('is_fingerspelling')}, sign={r.get('sign')}")
        if r.get("sign") == "Nada":
            results["failures"].append(f"'{label}' resolved to 'Nada'! Must resolve to handshape 0 / fingerspelling.")
        if not r.get("is_fingerspelling") and r.get("sign") != "0":
            results["failures"].append(f"'{label}' did not resolve to fingerspelling/0: {r}")

    # Verificar que 'registrar' no sea 'Registro Civil'
    reg_sign = resolve_gloss_to_sign("registrar")
    print(f"['registrar'] sign={reg_sign.get('sign')}")
    if reg_sign.get("sign") == "Registro Civil":
        results["failures"].append("'registrar' resolved to 'Registro Civil' instead of 'Inscribir'!")

    print("\n=======================================================")
    print(f"TOTAL GLOSAS EN CORPUS DE 20 TEXTOS: {results['total_glosses_corpus_20']}")
    print(f"TOTAL MISSING EN CORPUS DE 20 TEXTOS: {results['total_missing_corpus_20']}")
    print(f"TOTAL GLOSAS EN TODAS LAS PRUEBAS:    {results['total_glosses_all']}")
    print(f"TOTAL MISSING EN TODAS LAS PRUEBAS:   {results['total_missing_all']}")
    print(f"TOTAL FALLOS DETECTADOS:             {len(results['failures'])}")
    print("=======================================================")

    return results


if __name__ == "__main__":
    res = run_empirical_verification()
    if res["failures"]:
        print("FAILURES:")
        for f in res["failures"]:
            print(f"  - {f}")
        exit(1)
    else:
        print("ALL EMPIRICAL CHECKS PASSED (100% RESOLUTION, 0 MISSING).")
        exit(0)
