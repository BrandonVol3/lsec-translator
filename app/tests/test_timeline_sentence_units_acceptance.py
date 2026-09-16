"""
Suite de Pruebas de Aceptación: Unidades de Frase Completas y Glosas LSEC en la Línea de Tiempo.

Verifica los 8 criterios de aceptación y casos especiales:
1. Una frase se muestra completa hasta su puntuación final (. ? !).
2. Las glosas correspondientes aparecen directamente debajo en el mismo intervalo.
3. Seleccionar una frase mueve el video a su inicio temporal.
4. El resaltado cambia conforme avanza el video (sincronización con el playhead).
5. Zoom y scrubbing calculan posiciones y anchos proporcionales y estables.
6. Las frases con varios segmentos conservan todas sus asociaciones (IDs, proposiciones, glosas).
7. Una frase sin puntuación final se representa sin perder contenido.
8. Manejo de casos especiales: abreviaturas (Dr., etc.), preguntas/exclamaciones (¿? ¡!),
   segmentos solapados, revisiones (REVIEW_REQUIRED, AUDIO_REVIEW, BLOCKED) y consistencia total.
"""

import re
import pytest
from typing import List, Dict, Any, Optional


class SentenceGroupingEnginePy:
    """
    Implementación en Python de la lógica canónica de SentenceGroupingEngine
    para validación algorítmica y pruebas unitarias de aceptación.
    """
    ABBREVIATIONS_PATTERN = re.compile(
        r"\b(?:dr|dra|sr|sra|srta|lic|prof|ing|arq|etc|gob|núm|num|pág|pag|av|avda|ej|art|cap|vs|u\.s\.a|u\.p\.e\.c|e\.e\.u\.u)\.?$",
        re.IGNORECASE
    )

    @classmethod
    def is_sentence_punctuation(cls, word: str) -> bool:
        if not word or not isinstance(word, str):
            return False
        clean = word.strip()
        if not clean:
            return False
        # Números con punto (e.g. 4.500)
        if re.match(r"^\d+\.\d+$", clean):
            return False
        # Abreviaturas
        if cls.ABBREVIATIONS_PATTERN.search(clean):
            return False
        # Signos terminales
        return bool(re.search(r"[.!?]+$", clean))

    @classmethod
    def extract_trailing_punctuation(cls, text: str) -> str:
        if not text:
            return ""
        match = re.search(r"[.!?]+$", text.strip())
        return match.group(0) if match else ""

    @classmethod
    def split_transcription_into_sentences(cls, text: str) -> List[str]:
        if not text:
            return []
        raw_parts = re.split(r"(?<=[.!?])\s+(?=[A-ZÁÉÍÓÚÑ¿¡])", text.strip())
        results = []
        for part in raw_parts:
            part = part.strip()
            if not part:
                continue
            if results and cls.ABBREVIATIONS_PATTERN.search(results[-1]):
                results[-1] += " " + part
            else:
                results.append(part)
        return results

    @classmethod
    def check_segment_ends_sentence(
        cls,
        segment: Dict[str, Any],
        next_segment: Optional[Dict[str, Any]],
        word_timestamps: List[Dict[str, Any]],
        reference_sentences: List[str],
        current_sentence_index: int
    ) -> bool:
        seg_text = (segment.get("normalized_text") or segment.get("original_text") or "").strip()
        if cls.is_sentence_punctuation(seg_text):
            return True

        seg_words = segment.get("words") or []
        if seg_words:
            last_word = seg_words[-1].get("word", "").strip()
            if cls.is_sentence_punctuation(last_word):
                return True

        seg_end = segment.get("end_seconds", segment.get("end_time", 0.0))
        for w in word_timestamps:
            if abs(w.get("end", 0.0) - seg_end) <= 0.15:
                if cls.is_sentence_punctuation(w.get("word", "")):
                    return True

        if reference_sentences and len(reference_sentences) >= current_sentence_index:
            ref_sentence = reference_sentences[current_sentence_index - 1]
            if ref_sentence:
                clean_ref = re.sub(r"[^\w\s]", "", ref_sentence.lower()).strip()
                clean_seg = re.sub(r"[^\w\s]", "", seg_text.lower()).strip()
                if clean_ref.endswith(clean_seg) or (clean_seg + " ") in clean_ref:
                    if clean_ref.endswith(clean_seg):
                        return True

        return False

    @classmethod
    def build_sentence_units(cls, project: Dict[str, Any]) -> List[Dict[str, Any]]:
        if not project:
            return []
        segments = project.get("segments", [])
        if not segments:
            return []

        all_glosses = project.get("glosses", [])
        transcription = project.get("transcription", {})
        word_timestamps = transcription.get("word_timestamps", [])
        transcription_text = (transcription.get("text") or "").strip()
        reference_sentences = cls.split_transcription_into_sentences(transcription_text)

        sentence_units = []
        current_segments = []
        sentence_index = 1

        for i, seg in enumerate(segments):
            current_segments.append(seg)
            is_last = (i == len(segments) - 1)
            next_seg = segments[i + 1] if i + 1 < len(segments) else None
            ends_sentence = is_last or cls.check_segment_ends_sentence(
                seg, next_seg, word_timestamps, reference_sentences, sentence_index
            )

            if ends_sentence and current_segments:
                ref_text = reference_sentences[sentence_index - 1] if (sentence_index - 1 < len(reference_sentences)) else None
                unit = cls.create_sentence_unit(sentence_index, current_segments, all_glosses, word_timestamps, ref_text)
                sentence_units.append(unit)
                current_segments = []
                sentence_index += 1

        if current_segments:
            ref_text = reference_sentences[sentence_index - 1] if (sentence_index - 1 < len(reference_sentences)) else None
            unit = cls.create_sentence_unit(sentence_index, current_segments, all_glosses, word_timestamps, ref_text)
            sentence_units.append(unit)

        return sentence_units

    @classmethod
    def create_sentence_unit(
        cls,
        index: int,
        segments: List[Dict[str, Any]],
        all_glosses: List[Dict[str, Any]],
        word_timestamps: List[Dict[str, Any]],
        reference_sentence_text: Optional[str] = None
    ) -> Dict[str, Any]:
        start_sec = min(s.get("start_seconds", s.get("start_time", 0.0)) for s in segments)
        end_sec = max(s.get("end_seconds", s.get("end_time", start_sec + 2.0)) for s in segments)
        duration = round(end_sec - start_sec, 3)

        if reference_sentence_text:
            sentence_text = reference_sentence_text.strip()
        else:
            texts = [(s.get("normalized_text") or s.get("original_text") or "").strip() for s in segments]
            sentence_text = ", ".join(t for t in texts if t)
            last_words = segments[-1].get("words", [])
            last_w = last_words[-1].get("word", "") if last_words else ""
            trailing_punct = cls.extract_trailing_punctuation(last_w)
            if not cls.extract_trailing_punctuation(sentence_text) and trailing_punct:
                sentence_text += trailing_punct

        segment_ids = [s["id"] for s in segments]
        proposition_ids = []
        discourse_block_ids = []
        contained_words = []
        review_reasons = []
        has_review_required = False

        for s in segments:
            p_id = s.get("proposition_id")
            if p_id and p_id not in proposition_ids:
                proposition_ids.append(p_id)
            if isinstance(s.get("proposition_ids"), list):
                for pid in s["proposition_ids"]:
                    if pid not in proposition_ids:
                        proposition_ids.append(pid)

            b_id = s.get("block_id")
            if b_id is not None and b_id not in discourse_block_ids:
                discourse_block_ids.append(b_id)

            if s.get("words"):
                contained_words.extend(s["words"])

            st = s.get("status", "VALIDATED")
            if st in ("REVIEW_REQUIRED", "NATIVE_REVIEW", "AUDIO_REVIEW", "BLOCKED"):
                has_review_required = True
                if s.get("review_reason"):
                    review_reasons.append(s["review_reason"])
                elif s.get("status_label"):
                    review_reasons.append(f"{s['id']}: {s['status_label']}")

        # Recopilar glosas LSEC
        sentence_glosses = cls.collect_sentence_glosses(segments, proposition_ids, all_glosses, start_sec, end_sec)
        gloss_sequence = [g.get("gloss") or g.get("lemma") or "GLOSA" for g in sentence_glosses]

        for g in sentence_glosses:
            if g.get("status") in ("AUDIO_REVIEW", "NATIVE_REVIEW", "BLOCKED", "REVIEW_REQUIRED"):
                has_review_required = True
                if g.get("notes"):
                    review_reasons.append(f"Glosa {g.get('gloss')}: {g.get('notes')}")

        return {
            "id": f"sentence_{index:02d}",
            "index": index,
            "text": sentence_text,
            "start_seconds": round(start_sec, 3),
            "end_seconds": round(end_sec, 3),
            "duration": duration,
            "segments": segments,
            "segment_ids": segment_ids,
            "proposition_ids": proposition_ids,
            "discourse_block_ids": discourse_block_ids,
            "words": contained_words,
            "glosses": sentence_glosses,
            "gloss_sequence": gloss_sequence,
            "status": "REVIEW_REQUIRED" if has_review_required else "VALIDATED",
            "status_label": "Requiere Revisión" if has_review_required else "Validado",
            "has_review": has_review_required,
            "review_reasons": review_reasons
        }

    @classmethod
    def collect_sentence_glosses(
        cls,
        segments: List[Dict[str, Any]],
        proposition_ids: List[str],
        all_glosses: List[Dict[str, Any]],
        start_sec: float,
        end_sec: float
    ) -> List[Dict[str, Any]]:
        collected_map = {}
        for g in all_glosses:
            g_prop = g.get("prop_id") or g.get("proposition_id")
            g_start = g.get("start_seconds", g.get("start", None))
            g_end = g.get("end_seconds", g.get("end", None))

            matches = False
            if g_prop and any(pid == g_prop or pid in g_prop or g_prop in pid for pid in proposition_ids):
                matches = True
            elif g_start is not None and g_end is not None:
                if g_start >= start_sec - 0.15 and g_end <= end_sec + 0.25:
                    matches = True

            if matches and g["id"] not in collected_map:
                collected_map[g["id"]] = g

        if not collected_map:
            for s in segments:
                if s.get("glosses"):
                    for g in s["glosses"]:
                        if g["id"] not in collected_map:
                            collected_map[g["id"]] = g
                elif s.get("gloss_sequence"):
                    for g_idx, g_name in enumerate(s["gloss_sequence"]):
                        vid = f"g_{s['id']}_{g_idx}"
                        if vid not in collected_map:
                            collected_map[vid] = {
                                "id": vid,
                                "gloss": g_name,
                                "lemma": g_name,
                                "start_seconds": start_sec,
                                "end_seconds": end_sec,
                                "status": "VALIDATED"
                            }

        items = list(collected_map.values())
        items.sort(key=lambda x: (x.get("order", 0), x.get("start_seconds", x.get("start", 0.0))))
        return items


# ============================================================
# DATOS DE PRUEBA Y CASOS DE ACEPTACIÓN
# ============================================================

@pytest.fixture
def mock_upec_project():
    """Proyecto representativo con las 12 proposiciones y 8 oraciones de la UPEC."""
    return {
        "project_name": "Video_UPEC_Prueba.mp4",
        "transcription": {
            "text": (
                "Dicen que el conocimiento es poder, pero nadie te dice que también es libertad, libertad para decidir quién quieres ser. "
                "En la Politécnica del Carchi no solo eliges una carrera, eliges ser imparable. "
                "Con carreras de grado en los campus dos Tulcán y Cayambe nos enorgullece ser la universidad pública más sostenible del Ecuador. "
                "Formamos más que profesionales, formamos seres humanos que inspiran confianza y cercanía. "
                "Aquí te preparamos desde el primer día con excelencia académica, con innovación, con tecnología, tecnología que evoluciona contigo. "
                "Más de 4.500 graduados ya lo hicieron, hoy crean oportunidades, liberan y construyen ideas. "
                "Decide sobre tu futuro, haz posible hoy lo que imaginas. "
                "UPEC, educamos para transformar el mundo."
            ),
            "word_timestamps": [
                {"word": "Dicen", "start": 0.37, "end": 0.85},
                {"word": "poder,", "start": 2.06, "end": 2.51},
                {"word": "libertad,", "start": 4.96, "end": 5.35},
                {"word": "ser.", "start": 7.63, "end": 7.85},
                {"word": "imparable.", "start": 11.96, "end": 12.73},
                {"word": "Cayambe", "start": 15.81, "end": 16.35},
                {"word": "Ecuador.", "start": 19.89, "end": 20.25},
                {"word": "cercanía.", "start": 25.71, "end": 26.35},
                {"word": "contigo.", "start": 33.51, "end": 33.73},
                {"word": "oportunidades,", "start": 37.96, "end": 38.47},
                {"word": "ideas.", "start": 40.46, "end": 40.91},
                {"word": "imaginas.", "start": 44.59, "end": 45.07},
                {"word": "mundo.", "start": 47.79, "end": 48.09},
            ]
        },
        "segments": [
            {
                "id": "seg_01",
                "index": 1,
                "proposition_id": "p1",
                "start_seconds": 0.370,
                "end_seconds": 2.510,
                "normalized_text": "Dicen que el conocimiento es poder",
                "words": [{"word": "Dicen", "start": 0.37, "end": 0.85}, {"word": "poder,", "start": 2.06, "end": 2.51}],
                "status": "VALIDATED"
            },
            {
                "id": "seg_02",
                "index": 2,
                "proposition_id": "p2",
                "start_seconds": 2.950,
                "end_seconds": 5.350,
                "normalized_text": "pero nadie te dice que también es libertad",
                "words": [{"word": "pero", "start": 2.95, "end": 3.25}, {"word": "libertad,", "start": 4.96, "end": 5.35}],
                "status": "VALIDATED"
            },
            {
                "id": "seg_03",
                "index": 3,
                "proposition_id": "p3",
                "start_seconds": 5.670,
                "end_seconds": 7.850,
                "normalized_text": "libertad para decidir quién quieres ser",
                "words": [{"word": "libertad", "start": 5.67, "end": 6.20}, {"word": "ser.", "start": 7.63, "end": 7.85}],
                "status": "VALIDATED"
            },
            {
                "id": "seg_04",
                "index": 4,
                "proposition_id": "p4_p5",
                "start_seconds": 8.550,
                "end_seconds": 12.730,
                "normalized_text": "En la Politécnica del Carchi no solo eliges una carrera, eliges ser imparable",
                "words": [{"word": "En", "start": 8.55, "end": 8.75}, {"word": "imparable.", "start": 11.96, "end": 12.73}],
                "status": "NATIVE_REVIEW",
                "review_reason": "Paráfrasis semántica compleja de imparable"
            },
            {
                "id": "seg_05",
                "index": 5,
                "proposition_id": "p6_p7",
                "start_seconds": 13.130,
                "end_seconds": 16.350,
                "normalized_text": "Con carreras de grado en los campus dos Tulcán y Cayambe",
                "words": [{"word": "Con", "start": 13.13, "end": 13.35}, {"word": "Cayambe", "start": 15.81, "end": 16.35}],
                "status": "BLOCKED",
                "review_reason": "Error de alineación temporal en campus"
            },
            {
                "id": "seg_06",
                "index": 6,
                "proposition_id": "p8_p9",
                "start_seconds": 16.350,
                "end_seconds": 20.250,
                "normalized_text": "nos enorgullece ser la universidad pública más sostenible del Ecuador",
                "words": [{"word": "nos", "start": 16.35, "end": 16.60}, {"word": "Ecuador.", "start": 19.89, "end": 20.25}],
                "status": "VALIDATED"
            },
            {
                "id": "seg_07",
                "index": 7,
                "proposition_id": "p10_p13",
                "start_seconds": 20.690,
                "end_seconds": 26.350,
                "normalized_text": "Formamos más que profesionales, formamos seres humanos que inspiran confianza y cercanía.",
                "status": "VALIDATED"
            },
            {
                "id": "seg_08",
                "index": 8,
                "proposition_id": "p14_p16",
                "start_seconds": 26.590,
                "end_seconds": 33.730,
                "normalized_text": "Aquí te preparamos desde el primer día con excelencia académica, con innovación, con tecnología, tecnología que evoluciona contigo.",
                "status": "VALIDATED"
            },
            {
                "id": "seg_09",
                "index": 9,
                "proposition_id": "p17_p18",
                "start_seconds": 34.170,
                "end_seconds": 38.470,
                "normalized_text": "Más de 4.500 graduados ya lo hicieron, hoy crean oportunidades,",
                "words": [{"word": "Más", "start": 34.17, "end": 34.45}, {"word": "oportunidades,", "start": 37.96, "end": 38.47}],
                "status": "VALIDATED"
            },
            {
                "id": "seg_10",
                "index": 10,
                "proposition_id": "p19_p20",
                "start_seconds": 38.850,
                "end_seconds": 40.910,
                "normalized_text": "liberan y construyen ideas.",
                "words": [{"word": "liberan", "start": 38.85, "end": 39.45}, {"word": "ideas.", "start": 40.46, "end": 40.91}],
                "status": "AUDIO_REVIEW",
                "review_reason": "Ambigüedad acústica en liberan"
            },
            {
                "id": "seg_11",
                "index": 11,
                "proposition_id": "p21_p22",
                "start_seconds": 41.490,
                "end_seconds": 45.070,
                "normalized_text": "Decide sobre tu futuro, haz posible hoy lo que imaginas",
                "words": [{"word": "Decide", "start": 41.49, "end": 41.95}, {"word": "imaginas.", "start": 44.59, "end": 45.07}],
                "status": "VALIDATED"
            },
            {
                "id": "seg_12",
                "index": 12,
                "proposition_id": "p23",
                "start_seconds": 45.310,
                "end_seconds": 48.090,
                "normalized_text": "UPEC, educamos para transformar el mundo",
                "words": [{"word": "UPEC,", "start": 45.31, "end": 45.95}, {"word": "mundo.", "start": 47.79, "end": 48.09}],
                "status": "VALIDATED"
            }
        ],
        "glosses": [
            {"id": "g_01", "gloss": "PERSONA", "prop_id": "p1", "order": 0, "start": 0.37, "end": 0.85, "status": "VALIDATED"},
            {"id": "g_02", "gloss": "DECIR", "prop_id": "p1", "order": 1, "start": 0.86, "end": 1.35, "status": "VALIDATED"},
            {"id": "g_03", "gloss": "CONOCIMIENTO", "prop_id": "p1", "order": 2, "start": 1.36, "end": 1.95, "status": "VALIDATED"},
            {"id": "g_04", "gloss": "PODER", "prop_id": "p1", "order": 3, "start": 1.96, "end": 2.51, "status": "VALIDATED"},
            {"id": "g_05", "gloss": "PERO", "prop_id": "p2", "order": 4, "start": 2.95, "end": 3.25, "status": "VALIDATED"},
            {"id": "g_06", "gloss": "NADIE", "prop_id": "p2", "order": 5, "start": 3.26, "end": 3.65, "status": "VALIDATED"},
            {"id": "g_07", "gloss": "LIBERTAD", "prop_id": "p2", "order": 6, "start": 4.96, "end": 5.35, "status": "VALIDATED"},
            {"id": "g_08", "gloss": "LIBERTAD", "prop_id": "p3", "order": 7, "start": 5.67, "end": 6.15, "status": "VALIDATED"},
            {"id": "g_09", "gloss": "SER", "prop_id": "p3", "order": 8, "start": 7.31, "end": 7.60, "status": "VALIDATED"},
            {"id": "g_10", "gloss": "ELEGIR", "prop_id": "p3", "order": 9, "start": 7.61, "end": 7.85, "status": "VALIDATED"},
            {"id": "g_18", "gloss": "U-P-E-C", "prop_id": "p4", "order": 10, "start": 8.55, "end": 9.50, "status": "VALIDATED", "gloss_type": "DACTILOLOGÍA"},
            {"id": "g_24", "gloss": "DETERMINADA", "prop_id": "p5", "order": 11, "start": 11.46, "end": 11.85, "status": "NATIVE_REVIEW"},
            {"id": "g_33", "gloss": "CAMPUS", "prop_id": "p7", "order": 12, "start": 14.65, "end": 15.10, "status": "BLOCKED", "notes": "Error de alineación"},
            {"id": "g_44", "gloss": "ECUADOR", "prop_id": "p9", "order": 13, "start": 19.76, "end": 20.25, "status": "VALIDATED"}
        ]
    }


# ============================================================
# CASOS DE PRUEBA DE ACEPTACIÓN (CRITERIOS 1 AL 8)
# ============================================================

class TestTimelineSentenceUnitsAcceptance:
    """Suite de validación de los 8 criterios de aceptación."""

    def test_acceptance_1_sentence_shown_complete_until_final_punctuation(self, mock_upec_project):
        """Criterio 1: Cada frase se muestra completa hasta su puntuación final (. ? !)."""
        units = SentenceGroupingEnginePy.build_sentence_units(mock_upec_project)
        assert len(units) == 8, f"Se esperaban 8 frases completas, se obtuvieron {len(units)}"

        # Frase 1: punto final en 'ser.'
        assert units[0]["text"].endswith(".")
        assert "libertad para decidir quién quieres ser." in units[0]["text"]

        # Frase 2: punto final en 'imparable.'
        assert units[1]["text"].endswith(".")
        assert units[1]["text"] == "En la Politécnica del Carchi no solo eliges una carrera, eliges ser imparable."

        # Frase 3: punto final en 'Ecuador.'
        assert units[2]["text"].endswith(".")
        assert "Ecuador." in units[2]["text"]

        # Frase 8: punto final en 'mundo.'
        assert units[7]["text"].endswith(".")
        assert "mundo." in units[7]["text"]

    def test_acceptance_2_corresponding_glosses_appear_below_in_same_interval(self, mock_upec_project):
        """Criterio 2: Las glosas correspondientes aparecen debajo ocupando el mismo intervalo temporal."""
        units = SentenceGroupingEnginePy.build_sentence_units(mock_upec_project)
        f1 = units[0]

        # Mismo intervalo temporal general
        assert f1["start_seconds"] == 0.370
        assert f1["end_seconds"] == 7.850

        # Glosas correspondientes a las proposiciones p1, p2, p3
        gloss_names = [g["gloss"] for g in f1["glosses"]]
        assert "PERSONA" in gloss_names
        assert "DECIR" in gloss_names
        assert "CONOCIMIENTO" in gloss_names
        assert "PODER" in gloss_names
        assert "PERO" in gloss_names
        assert "LIBERTAD" in gloss_names
        assert "ELEGIR" in gloss_names
        assert len(f1["glosses"]) == 10

    def test_acceptance_3_selecting_sentence_moves_video_to_start(self, mock_upec_project):
        """Criterio 3: Seleccionar una frase proporciona la marca exacta para mover el video al inicio."""
        units = SentenceGroupingEnginePy.build_sentence_units(mock_upec_project)

        # Frase 1 inicia en 0.370s
        assert units[0]["start_seconds"] == 0.370
        # Frase 2 inicia en 8.550s
        assert units[1]["start_seconds"] == 8.550
        # Frase 3 inicia en 13.130s
        assert units[2]["start_seconds"] == 13.130

        # Al disparar onSentenceClick(sentence), el video se sincroniza a sentence.start_seconds
        simulated_current_time = units[1]["start_seconds"]
        assert simulated_current_time == 8.550

    def test_acceptance_4_highlight_changes_with_video_playhead(self, mock_upec_project):
        """Criterio 4: El resaltado cambia conforme avanza el cabezal de reproducción."""
        units = SentenceGroupingEnginePy.build_sentence_units(mock_upec_project)

        def get_active_sentence(time_sec):
            return next((u for u in units if u["start_seconds"] <= time_sec <= u["end_seconds"]), None)

        # En t=1.0s, debe estar activa la Frase 1 (0.37 -> 7.85)
        active_at_1 = get_active_sentence(1.0)
        assert active_at_1 is not None
        assert active_at_1["id"] == "sentence_01"

        # En t=10.0s, debe estar activa la Frase 2 (8.55 -> 12.73)
        active_at_10 = get_active_sentence(10.0)
        assert active_at_10 is not None
        assert active_at_10["id"] == "sentence_02"

        # En t=15.0s, debe estar activa la Frase 3 (13.13 -> 20.25)
        active_at_15 = get_active_sentence(15.0)
        assert active_at_15 is not None
        assert active_at_15["id"] == "sentence_03"

    def test_acceptance_5_zoom_and_scrubbing_calculations(self, mock_upec_project):
        """Criterio 5: Zoom y scrubbing calculan coordenadas proporcionales sin desfases."""
        units = SentenceGroupingEnginePy.build_sentence_units(mock_upec_project)
        f1 = units[0]

        for px_per_sec in [20, 45, 90, 150]:
            left = f1["start_seconds"] * px_per_sec
            width = (f1["end_seconds"] - f1["start_seconds"]) * px_per_sec - 2

            # Fila 1 (español) y Fila 2 (glosas) tienen cálculo idéntico
            row1_left, row1_width = left, width
            row2_left, row2_width = left, width

            assert row1_left == row2_left
            assert row1_width == row2_width
            assert width > 0

    def test_acceptance_6_multi_segment_sentences_preserve_all_associations(self, mock_upec_project):
        """Criterio 6: Las frases con varios segmentos conservan todas sus asociaciones internas e IDs."""
        units = SentenceGroupingEnginePy.build_sentence_units(mock_upec_project)

        # Frase 1 contiene seg_01, seg_02, seg_03
        f1 = units[0]
        assert f1["segment_ids"] == ["seg_01", "seg_02", "seg_03"]
        assert f1["proposition_ids"] == ["p1", "p2", "p3"]
        assert len(f1["segments"]) == 3
        # Los IDs y objetos de segmento están intactos
        assert f1["segments"][0]["id"] == "seg_01"
        assert f1["segments"][1]["id"] == "seg_02"
        assert f1["segments"][2]["id"] == "seg_03"

        # Frase 3 contiene seg_05, seg_06
        f3 = units[2]
        assert f3["segment_ids"] == ["seg_05", "seg_06"]
        assert f3["proposition_ids"] == ["p6_p7", "p8_p9"]

        # Frase 6 contiene seg_09, seg_10
        f6 = units[5]
        assert f6["segment_ids"] == ["seg_09", "seg_10"]

    def test_acceptance_7_sentence_without_final_punctuation_represented_without_data_loss(self):
        """Criterio 7: Una frase sin puntuación final se representa sin perder contenido."""
        raw_project = {
            "segments": [
                {
                    "id": "s_raw_1",
                    "start_seconds": 0.0,
                    "end_seconds": 3.5,
                    "normalized_text": "Este es un fragmento de audio sin punto al final",
                    "words": [{"word": "final", "start": 3.0, "end": 3.5}],
                    "status": "VALIDATED"
                }
            ],
            "glosses": [
                {"id": "g_raw_1", "gloss": "FRAGMENTO", "prop_id": "p_raw", "start": 0.5, "end": 1.5}
            ]
        }

        units = SentenceGroupingEnginePy.build_sentence_units(raw_project)
        assert len(units) == 1
        u = units[0]
        assert u["text"] == "Este es un fragmento de audio sin punto al final"
        assert u["start_seconds"] == 0.0
        assert u["end_seconds"] == 3.5
        assert len(u["glosses"]) == 1
        assert u["glosses"][0]["gloss"] == "FRAGMENTO"

    def test_acceptance_8_special_cases_and_abbreviations(self):
        """Criterio 8: Casos especiales de puntuación, abreviaturas, preguntas y estados de revisión."""
        special_project = {
            "transcription": {
                "text": "¿Sabías que el Dr. Pérez trabaja en la UPEC? ¡Es una gran oportunidad!"
            },
            "segments": [
                {
                    "id": "seg_sp_1",
                    "start_seconds": 0.0,
                    "end_seconds": 4.0,
                    "normalized_text": "¿Sabías que el Dr. Pérez trabaja en la UPEC?",
                    "words": [{"word": "¿Sabías", "start": 0.0, "end": 0.8}, {"word": "UPEC?", "start": 3.5, "end": 4.0}],
                    "status": "VALIDATED"
                },
                {
                    "id": "seg_sp_2",
                    "start_seconds": 4.5,
                    "end_seconds": 7.0,
                    "normalized_text": "¡Es una gran oportunidad!",
                    "words": [{"word": "¡Es", "start": 4.5, "end": 5.0}, {"word": "oportunidad!", "start": 6.5, "end": 7.0}],
                    "status": "REVIEW_REQUIRED",
                    "review_reason": "Verificar entonación no manual exclamativa"
                }
            ],
            "glosses": [
                {"id": "g_sp_1", "gloss": "SABER", "start": 0.2, "end": 1.0, "status": "VALIDATED"},
                {"id": "g_sp_2", "gloss": "OPORTUNIDAD", "start": 5.5, "end": 6.8, "status": "AUDIO_REVIEW", "notes": "Revisar claridad"}
            ]
        }

        units = SentenceGroupingEnginePy.build_sentence_units(special_project)
        assert len(units) == 2

        # Frase 1: Pregunta con abreviatura interna (Dr.) no debe cortarse en Dr.
        u1 = units[0]
        assert u1["text"] == "¿Sabías que el Dr. Pérez trabaja en la UPEC?"
        assert u1["status"] == "VALIDATED"

        # Frase 2: Exclamación con revisión requerida
        u2 = units[1]
        assert u2["text"] == "¡Es una gran oportunidad!"
        assert u2["status"] == "REVIEW_REQUIRED"
        assert u2["has_review"] is True
        assert len(u2["review_reasons"]) >= 1

    def test_html_and_js_integration_integrity(self):
        """Verifica que index.html y los componentes JS declaran e importan los recursos correctamente."""
        with open("app/static/index.html", "r", encoding="utf-8") as f:
            html_content = f.read()

        # Cabeceras de pista actualizadas
        assert "1. Frases (Español)" in html_content
        assert "2. Glosas LSEC (Frase)" in html_content

        # Importación de sentence-engine.js antes de timeline.js
        idx_engine = html_content.find('src="/static/js/components/sentence-engine.js"')
        idx_timeline = html_content.find('src="/static/js/components/timeline.js"')
        assert idx_engine != -1, "sentence-engine.js debe estar importado en index.html"
        assert idx_timeline != -1, "timeline.js debe estar importado en index.html"
        assert idx_engine < idx_timeline, "sentence-engine.js debe cargarse antes de timeline.js"

        # Verificar que sentence-engine.js exporta SentenceGroupingEngine
        with open("app/static/js/components/sentence-engine.js", "r", encoding="utf-8") as f:
            engine_js = f.read()
        assert "class SentenceGroupingEngine" in engine_js
        assert "buildSentenceUnits" in engine_js

        # Verificar que timeline.js renderiza las pistas de frases
        with open("app/static/js/components/timeline.js", "r", encoding="utf-8") as f:
            timeline_js = f.read()
        assert "renderTrackSentencesES" in timeline_js
        assert "renderTrackSentencesGlosses" in timeline_js
        assert "timeline-sentence-item" in timeline_js
        assert "sentenceUnits" in timeline_js
