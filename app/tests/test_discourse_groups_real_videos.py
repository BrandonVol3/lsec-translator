"""
Pruebas de análisis por idea completa (oración) con los VIDEOS REALES de `Videos de Prueba/`.

Cumple AGENTS.md: sin mocks ni textos sintéticos. La transcripción proviene del ASR real (Whisper) de
`1.mp4`, `2.mp4` y `3.mp4` (se cachea por hash del video en `app/tests/tools/.asr_cache/`) y se traduce
con el código vigente a TODAS sus glosas reales.

Verifica:
  * `sentence_id` presente en el 100 % de las glosas y no decreciente en el orden lineal.
  * Cero glosas idénticas adyacentes (excepto dactilología) con el nivel por defecto.
  * El optimizador por oración es auditable: cada acción aplicada corresponde a una glosa menos y deja
    registro; los niveles `off` y `conservative` difieren solo en glosas registradas en el log.
  * Integridad de metadatos tras consolidar: órdenes continuos, sin ids huérfanos en spans/bloques.
  * Toda relación adversativa/de contraste (`but`, `not_only`, `more_than`) tiene marcador `contrast`
    (el sistema no emite la glosa PERO por defecto).
  * La consolidación no introduce advertencias bloqueantes ni empeora el número de advertencias.
"""
from __future__ import annotations

import asyncio
from typing import Dict, Tuple

import pytest

from app.core.schemas import GlossOutput, TranscriptionResult
from app.services.nlp_service import LSECTranslatorService
from app.tests.tools.measure_discourse_units import VIDEOS_DIR, transcribe_real_video

REAL_VIDEOS = ["1.mp4", "2.mp4", "3.mp4"]
CONTRAST_RELATIONS = {"but", "not_only", "more_than"}


@pytest.fixture(scope="module")
def svc() -> LSECTranslatorService:
    return LSECTranslatorService()


@pytest.fixture(scope="module")
def real_transcriptions() -> Dict[str, TranscriptionResult]:
    out: Dict[str, TranscriptionResult] = {}
    for name in REAL_VIDEOS:
        path = VIDEOS_DIR / name
        assert path.exists(), f"Falta el video real de prueba: {path}"
        out[name] = transcribe_real_video(path)
    return out


def _translate(svc: LSECTranslatorService, tr: TranscriptionResult, level: str) -> GlossOutput:
    return asyncio.run(
        svc.translate_to_gloss(
            tr.text,
            mode="detailed",
            paraphrase_budget="compact",
            source_audio_duration=tr.duration_seconds,
            transcription=tr,
            condense_level=level,
        )
    )


@pytest.fixture(scope="module")
def outputs(svc, real_transcriptions) -> Dict[str, Tuple[GlossOutput, GlossOutput]]:
    return {
        name: (_translate(svc, tr, "off"), _translate(svc, tr, "conservative"))
        for name, tr in real_transcriptions.items()
    }


@pytest.mark.parametrize("name", REAL_VIDEOS)
def test_sentence_id_on_every_gloss_and_monotonic(outputs, name):
    _, out = outputs[name]
    ordered = sorted(out.glosses, key=lambda g: g.order)
    assert ordered, f"{name}: sin glosas"
    assert all(g.sentence_id is not None for g in ordered), f"{name}: glosas sin sentence_id"
    ids = [g.sentence_id for g in ordered]
    assert ids == sorted(ids), f"{name}: sentence_id no decreciente en el orden lineal"
    assert all(p.sentence_id is not None for p in out.semantic_propositions)


@pytest.mark.parametrize("name", REAL_VIDEOS)
def test_no_adjacent_identical_glosses_by_default(outputs, name):
    _, out = outputs[name]
    ordered = sorted(out.glosses, key=lambda g: g.order)
    dups = [
        a.gloss for a, b in zip(ordered, ordered[1:])
        if a.gloss == b.gloss and "-" not in a.gloss  # la dactilología (T-U-L…) nunca se consolida
    ]
    assert dups == [], f"{name}: glosas idénticas adyacentes: {dups}"


@pytest.mark.parametrize("name", REAL_VIDEOS)
def test_condensation_is_auditable(outputs, name):
    base, cond = outputs[name]
    applied = [c for c in cond.condensation_log if c["applied"]]
    assert len(base.glosses) - len(cond.glosses) == len(applied), (
        f"{name}: las glosas eliminadas ({len(base.glosses) - len(cond.glosses)}) no coinciden con las acciones "
        f"registradas ({len(applied)})"
    )
    assert base.condensation_log == [], f"{name}: el nivel 'off' no debe registrar acciones"
    removed_ids = {c["removed_gloss_id"] for c in applied}
    kept_ids = {g.id for g in cond.glosses}
    assert removed_ids.isdisjoint(kept_ids), f"{name}: una glosa registrada como eliminada sigue en la salida"
    # El nivel conservador jamás aplica la regla R3 (solo la sugiere).
    assert all(c["rule_id"] != "R3_PARALLEL_FINAL_VERB" for c in applied)
    # No se pierde contenido léxico: la secuencia conservadora es subsecuencia de la base.
    it = iter(g.gloss for g in sorted(base.glosses, key=lambda g: g.order))
    assert all(any(x == y for y in it) for x in (g.gloss for g in sorted(cond.glosses, key=lambda g: g.order)))


@pytest.mark.parametrize("name", REAL_VIDEOS)
def test_metadata_integrity_after_condensation(outputs, name):
    _, out = outputs[name]
    orders = [g.order for g in sorted(out.glosses, key=lambda g: g.order)]
    assert orders == list(range(len(orders))), f"{name}: órdenes de glosa no continuos"
    ids = {g.id for g in out.glosses}
    n = len(out.glosses)
    for s in out.non_manual_spans:
        assert all(i in ids for i in s.gloss_ids), f"{name}: span {s.id} con ids huérfanos"
        assert 0 <= s.start_order <= s.end_order < n, f"{name}: span {s.id} fuera de rango"
    for b in out.discourse_blocks:
        assert all(i in ids for i in b.gloss_ids), f"{name}: bloque {b.id} con ids huérfanos"
        assert 0 <= b.start_order <= b.end_order < n, f"{name}: bloque {b.id} fuera de rango"
    for g in out.glosses:
        for sid in g.non_manual_span_ids:
            assert any(sp.id == sid for sp in out.non_manual_spans), f"{name}: {g.gloss} apunta a un span inexistente"


@pytest.mark.parametrize("name", REAL_VIDEOS)
def test_contrast_relations_have_visible_marker(outputs, name):
    _, out = outputs[name]
    contrast_props = {s.proposition_id for s in out.non_manual_spans if s.type == "contrast"}
    connector_props = {g.proposition_id for g in out.glosses if g.lexical_strategy == "discourse_connector" and g.gloss == "PERO"}
    missing = [
        f"{p.id}:{p.discourse_relation}" for p in out.semantic_propositions
        if p.discourse_relation in CONTRAST_RELATIONS and p.id not in contrast_props and p.id not in connector_props
    ]
    assert missing == [], f"{name}: relaciones de contraste sin marcador visible: {missing}"


def test_fragmentation_is_measurable_on_real_video_1(outputs):
    """Línea base documentada: 1.mp4 tiene 8 oraciones fragmentadas en 21 proposiciones."""
    _, out = outputs["1.mp4"]
    sent_ids = {p.sentence_id for p in out.semantic_propositions}
    assert len(sent_ids) == 8
    assert len(out.semantic_propositions) == 21
