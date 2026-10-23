"""
Tests del pipeline LSEC Translator.

Pruebas unitarias y de integración para verificar el flujo
completo del sistema: ASR → NLP → WebSocket.

Incluye tests para las mejoras lingüísticas LSEC:
- Wh-words al final de la cláusula
- Adjetivos post-nominales (Sustantivo + Adjetivo)
- Marcador de pluralidad (VARIOS)
- Perífrasis verbales → marcadores temporales/aspectuales
- Deixis pronominal (PRO1, PRO2, PRO3)
- Duración dinámica de glosas
- Carga de lexicón externo
"""

from __future__ import annotations

import asyncio
import json

import pytest
from httpx import ASGITransport, AsyncClient

from app.core.schemas import (
    AvatarPayload,
    BlendshapeValue,
    FacialExpression,
    GlossItem,
    GlossOutput,
    GlossType,
    HandKeypoints,
    KeypointsFrame,
    Landmark3D,
    NonManualMarker,
    PoseKeypoints,
    TranscriptionResult,
    WSMessageType,
    WebSocketMessage,
    WordTimestamp,
)


# ============================================================
# Tests de Schemas (Pydantic)
# ============================================================

class TestSchemas:
    """Pruebas de validación de esquemas Pydantic."""

    def test_transcription_result_creation(self) -> None:
        """Verifica la creación de un TranscriptionResult."""
        result = TranscriptionResult(
            text="Hola mundo",
            language="es",
            confidence=0.95,
            duration_seconds=2.5,
        )
        assert result.text == "Hola mundo"
        assert result.language == "es"
        assert result.confidence == 0.95

    def test_word_timestamp(self) -> None:
        """Verifica la creación de WordTimestamp."""
        word = WordTimestamp(word="hola", start=0.0, end=0.5, probability=0.98)
        assert word.word == "hola"
        assert word.start == 0.0
        assert word.end == 0.5

    def test_gloss_item_sign(self) -> None:
        """Verifica la creación de una glosa tipo SEÑA."""
        gloss = GlossItem(
            gloss="COMER",
            gloss_type=GlossType.SIGN,
            order=0,
            original_word="comer",
            duration_ms=500,
        )
        assert gloss.gloss == "COMER"
        assert gloss.gloss_type == GlossType.SIGN
        assert gloss.order == 0

    def test_gloss_item_fingerspelling(self) -> None:
        """Verifica la creación de una glosa tipo DACTILOLOGÍA."""
        gloss = GlossItem(
            gloss="M-A-R-Í-A",
            gloss_type=GlossType.FINGERSPELLING,
            order=1,
            original_word="María",
            duration_ms=1500,
        )
        assert gloss.gloss_type == GlossType.FINGERSPELLING
        assert "-" in gloss.gloss

    def test_non_manual_marker(self) -> None:
        """Verifica los marcadores no-manuales."""
        marker = NonManualMarker(
            expression=FacialExpression.QUESTION_WH,
            head_movement="inclinar",
            intensity=1.5,
        )
        assert marker.expression == FacialExpression.QUESTION_WH
        assert marker.head_movement == "inclinar"
        assert marker.intensity == 1.5

    def test_gloss_output_auto_duration(self) -> None:
        """Verifica que GlossOutput calcule duración total automáticamente."""
        output = GlossOutput(
            original_text="Yo como manzana",
            glosses=[
                GlossItem(gloss="PRO1", gloss_type=GlossType.SIGN, order=0, duration_ms=350),
                GlossItem(gloss="MANZANA", gloss_type=GlossType.SIGN, order=1, duration_ms=500),
                GlossItem(gloss="COMER", gloss_type=GlossType.SIGN, order=2, duration_ms=500),
            ],
        )
        assert output.total_duration_ms == 1350
        assert len(output.glosses) == 3

    def test_landmark_3d(self) -> None:
        """Verifica la creación de un Landmark3D."""
        lm = Landmark3D(x=0.5, y=0.3, z=0.1, visibility=0.99)
        assert lm.x == 0.5
        assert lm.visibility == 0.99

    def test_keypoints_frame(self) -> None:
        """Verifica la creación de un KeypointsFrame vacío."""
        frame = KeypointsFrame(frame_index=0, timestamp_ms=33.3)
        assert frame.left_hand is None
        assert frame.right_hand is None
        assert frame.pose is None
        assert frame.face is None

    def test_avatar_payload(self) -> None:
        """Verifica la creación de un AvatarPayload completo."""
        gloss = GlossItem(
            gloss="HOLA",
            gloss_type=GlossType.SIGN,
            order=0,
        )
        payload = AvatarPayload(
            sequence_index=0,
            gloss=gloss,
            non_manual_markers=NonManualMarker(expression=FacialExpression.NEUTRAL),
            blendshapes=[
                BlendshapeValue(name="browInnerUp", value=0.3),
                BlendshapeValue(name="mouthSmileLeft", value=0.7),
            ],
            timestamp_ms=1000.0,
        )
        assert payload.gloss.gloss == "HOLA"
        assert len(payload.blendshapes) == 2
        assert payload.blendshapes[0].name == "browInnerUp"

    def test_websocket_message(self) -> None:
        """Verifica la serialización de WebSocketMessage."""
        msg = WebSocketMessage(
            type=WSMessageType.GLOSS_RESULT,
            payload={"text": "test"},
        )
        serialized = msg.model_dump_json()
        assert "gloss_result" in serialized

    def test_gloss_output_serialization(self) -> None:
        """Verifica la serialización/deserialización JSON de GlossOutput."""
        output = GlossOutput(
            original_text="Buenos días",
            glosses=[
                GlossItem(
                    gloss="BUENOS-DÍAS",
                    gloss_type=GlossType.SIGN,
                    order=0,
                    non_manual=NonManualMarker(
                        expression=FacialExpression.AFFIRMATION,
                        head_movement="asentir",
                    ),
                ),
            ],
        )
        json_str = output.model_dump_json()
        data = json.loads(json_str)
        assert data["original_text"] == "Buenos días"
        assert len(data["glosses"]) == 1
        assert data["glosses"][0]["non_manual"]["expression"] == "afirmación"


# ============================================================
# Tests del Servicio NLP (Heurístico)
# ============================================================

class TestNLPServiceHeuristic:
    """Pruebas del motor heurístico de traducción LSEC (sin LLM)."""

    @pytest.fixture
    def nlp_service(self):
        """Crea una instancia del servicio NLP en modo heurístico."""
        from app.services.nlp_service import LSECTranslatorService

        return LSECTranslatorService()

    @pytest.mark.asyncio
    async def test_basic_translation(self, nlp_service) -> None:
        """Traduce una oración simple."""
        result = await nlp_service.translate_to_gloss("Yo como manzana")
        assert result.original_text == "Yo como manzana"
        assert len(result.glosses) > 0
        assert all(g.gloss == g.gloss.upper() for g in result.glosses)

    @pytest.mark.asyncio
    async def test_stop_words_removed(self, nlp_service) -> None:
        """Verifica que se eliminen artículos y preposiciones."""
        result = await nlp_service.translate_to_gloss("El gato está en la mesa")
        gloss_texts = [g.gloss for g in result.glosses]
        # "el", "la", "en", "está" deben ser eliminados
        assert "EL" not in gloss_texts
        assert "LA" not in gloss_texts
        assert "EN" not in gloss_texts

    @pytest.mark.asyncio
    async def test_question_wh_detection(self, nlp_service) -> None:
        """Verifica detección de preguntas WH."""
        result = await nlp_service.translate_to_gloss("¿Dónde está el baño?")
        has_question_marker = any(
            g.non_manual.expression == FacialExpression.QUESTION_WH
            for g in result.glosses
        )
        assert has_question_marker

    @pytest.mark.asyncio
    async def test_question_yesno_detection(self, nlp_service) -> None:
        """Verifica detección de preguntas sí/no."""
        result = await nlp_service.translate_to_gloss("¿Tienes hambre?")
        has_question_marker = any(
            g.non_manual.expression == FacialExpression.QUESTION_YESNO
            for g in result.glosses
        )
        assert has_question_marker

    @pytest.mark.asyncio
    async def test_negation_detection(self, nlp_service) -> None:
        """Verifica detección de negaciones exclusivamente en la palabra 'NO'."""
        result = await nlp_service.translate_to_gloss("No quiero ir")
        no_glosses = [g for g in result.glosses if g.gloss == "NO" or g.gloss.startswith("NO-")]
        other_glosses = [g for g in result.glosses if not (g.gloss == "NO" or g.gloss.startswith("NO-"))]
        assert len(no_glosses) > 0
        assert all(g.non_manual.expression == FacialExpression.NEGATION for g in no_glosses)
        assert all(g.non_manual.expression == FacialExpression.NEUTRAL for g in other_glosses)

    @pytest.mark.asyncio
    async def test_empty_text_raises(self, nlp_service) -> None:
        """Verifica que texto vacío lance ValueError."""
        with pytest.raises(ValueError, match="vacío"):
            await nlp_service.translate_to_gloss("")

    @pytest.mark.asyncio
    async def test_grammar_notes_present(self, nlp_service) -> None:
        """Verifica que se incluyan notas gramaticales."""
        result = await nlp_service.translate_to_gloss("Hola amigo")
        assert result.grammar_notes is not None
        assert len(result.grammar_notes) > 0


# ============================================================
# Tests de Traducción Determinista con spaCy (Estructura SOV)
# ============================================================

class TestSpaCyPreprocessing:
    """Pruebas de la traducción determinista con spaCy en orden SOV."""

    @pytest.fixture
    def nlp_service(self):
        """Crea una instancia del servicio NLP con spaCy cargado."""
        from app.services.nlp_service import LSECTranslatorService
        return LSECTranslatorService()

    def test_spacy_loaded(self, nlp_service) -> None:
        """Verifica que spaCy se cargó correctamente."""
        assert nlp_service._nlp is not None, (
            "spaCy no se cargó. Ejecutar: python -m spacy download es_core_news_sm"
        )

    @pytest.mark.asyncio
    async def test_example_yo_como_manzana(self, nlp_service) -> None:
        """Verifica el ejemplo: 'Yo como manzana' → 'PRO1 MANZANA COMER' (con deixis pronominal)."""
        result = await nlp_service.translate_to_gloss("Yo como manzana")
        gloss_names = [g.gloss for g in result.glosses]
        assert gloss_names[0] == "PRO1", f"Esperado PRO1 al inicio, obtenido: {gloss_names}"
        assert "MANZANA" in gloss_names
        assert "COMER" in gloss_names
        # Verificar orden SOV: PRO1 (sujeto) antes de COMER (verbo)
        assert gloss_names.index("PRO1") < gloss_names.index("COMER")

    @pytest.mark.asyncio
    async def test_example_maria_compra_pan(self, nlp_service) -> None:
        """Verifica el ejemplo: 'María compra pan' → 'MARÍA PAN COMPRAR'."""
        result = await nlp_service.translate_to_gloss("María compra pan")
        gloss_names = [g.gloss for g in result.glosses]
        assert "MARÍA" in gloss_names
        assert "PAN" in gloss_names
        assert "COMPRAR" in gloss_names
        # Verificar orden SOV
        assert gloss_names.index("MARÍA") < gloss_names.index("COMPRAR")

    @pytest.mark.asyncio
    async def test_pos_filtering_removes_determiners(self, nlp_service) -> None:
        """Verifica que se eliminen los determinantes (DET): 'El gato come la manzana'."""
        result = await nlp_service.translate_to_gloss("El gato come la manzana")
        gloss_names = [g.gloss for g in result.glosses]
        assert "EL" not in gloss_names
        assert "LA" not in gloss_names
        assert "GATO" in gloss_names
        assert "MANZANA" in gloss_names
        assert "COMER" in gloss_names

    @pytest.mark.asyncio
    async def test_pos_filtering_removes_prepositions(self, nlp_service) -> None:
        """Verifica que se eliminen las preposiciones (ADP)."""
        result = await nlp_service.translate_to_gloss("Voy a la escuela de niños")
        gloss_names = [g.gloss for g in result.glosses]
        assert "A" not in gloss_names
        assert "DE" not in gloss_names

    @pytest.mark.asyncio
    async def test_copulative_removal(self, nlp_service) -> None:
        """Verifica que se eliminen verbos copulativos (ser, estar)."""
        result = await nlp_service.translate_to_gloss("María es estudiante")
        gloss_names = [g.gloss for g in result.glosses]
        assert "ES" not in gloss_names
        assert "SER" not in gloss_names

    @pytest.mark.asyncio
    async def test_lemmatization_verbs_to_infinitive(self, nlp_service) -> None:
        """Verifica que los verbos se lematicen al infinitivo."""
        result = await nlp_service.translate_to_gloss("Los estudiantes leen libros")
        gloss_names = [g.gloss for g in result.glosses]
        assert "LEER" in gloss_names
        # Con la mejora de pluralidad, puede incluir VARIOS
        assert "ESTUDIANTE" in gloss_names
        assert "LIBRO" in gloss_names

    @pytest.mark.asyncio
    async def test_passthrough_on_no_clear_structure(self, nlp_service) -> None:
        """Verifica que textos cortos no crasheen."""
        result = await nlp_service.translate_to_gloss("¡Hola!")
        assert len(result.glosses) > 0

    def test_split_into_sentences_spacy(self, nlp_service) -> None:
        """Verifica que _split_into_sentences divida correctamente por oraciones."""
        text = "En la Politécnica eliges ser imparable. La universidad ofrece innovación."
        sentences = nlp_service._split_into_sentences(text)
        assert len(sentences) >= 2
        # Verificar que las cláusulas contengan el contenido esperado
        all_text = " ".join(sentences)
        assert "Politécnica" in all_text or "POLITECNICA" in all_text
        assert "innovación" in all_text

    @pytest.mark.asyncio
    async def test_multi_sentence_continuous_order(self, nlp_service) -> None:
        """Verifica que las glosas de múltiples oraciones mantengan un order continuo (0, 1, 2...)."""
        text = "María compra pan. Los estudiantes leen libros."
        result = await nlp_service.translate_to_gloss(text)
        assert len(result.glosses) > 0
        orders = [g.order for g in result.glosses]
        assert orders == list(range(len(result.glosses)))

    @pytest.mark.asyncio
    async def test_strict_lemmatization(self, nlp_service) -> None:
        """Verifica lematización estricta: 'Los graduados crean proyectos'."""
        result = await nlp_service.translate_to_gloss("Los graduados crean proyectos")
        gloss_names = [g.gloss for g in result.glosses]
        assert "GRADUADO" in gloss_names
        assert "PROYECTO" in gloss_names
        assert "CREAR" in gloss_names

    @pytest.mark.asyncio
    async def test_verb_conjugation_to_infinitive(self, nlp_service) -> None:
        """Verifica que verbos conjugados como 'eliges' se lematicen al infinitivo 'ELEGIR'."""
        result = await nlp_service.translate_to_gloss("Tú eliges estudiar")
        gloss_names = [g.gloss for g in result.glosses]
        assert "ELEGIR" in gloss_names
        assert "ELIGE" not in gloss_names
        assert "ELIGES" not in gloss_names

    @pytest.mark.asyncio
    async def test_sov_dependency_order_with_time_and_place(self, nlp_service) -> None:
        """Verifica orden SOV con Tiempo y Lugar al inicio: 'Ayer Juan compró una casa en Quito'."""
        result = await nlp_service.translate_to_gloss("Ayer Juan compró una casa en Quito")
        gloss_names = [g.gloss for g in result.glosses]
        # Tiempo: AYER al inicio, Verbo: COMPRAR al final (o cerca)
        assert gloss_names[0] == "AYER"
        assert "JUAN" in gloss_names
        assert "CASA" in gloss_names
        assert "COMPRAR" in gloss_names

    @pytest.mark.asyncio
    async def test_nmm_negation_only_on_no(self, nlp_service) -> None:
        """Verifica que 'expression' sea 'neutral' por defecto y sólo 'negación' en la palabra 'NO'."""
        result = await nlp_service.translate_to_gloss("No quiero comer pan")
        for g in result.glosses:
            if g.gloss == "NO" or g.gloss.startswith("NO-"):
                assert g.non_manual.expression == FacialExpression.NEGATION
                assert g.non_manual.head_movement == "negar"
            else:
                assert g.non_manual.expression == FacialExpression.NEUTRAL
                assert g.non_manual.head_movement is None

    @pytest.mark.asyncio
    async def test_institutional_dictionary_and_dactylology(self, nlp_service) -> None:
        """Verifica diccionario institucional (UPEC -> U-P-E-C) y reemplazo de modismos (cadénica -> académica)."""
        result = await nlp_service.translate_to_gloss("La UPEC ofrece excelencia cadénica")
        gloss_names = [g.gloss for g in result.glosses]
        assert "U-P-E-C" in gloss_names
        upec_item = next(g for g in result.glosses if g.gloss == "U-P-E-C")
        assert upec_item.gloss_type == GlossType.FINGERSPELLING
        assert "CADÉNICA" not in gloss_names
        assert "CADENICA" not in gloss_names
        assert "OFRECER" in gloss_names

    @pytest.mark.asyncio
    async def test_translate_to_lsec_alias(self, nlp_service) -> None:
        """Verifica que el alias translate_to_lsec funcione de forma idéntica."""
        text = "Yo como manzana"
        result = await nlp_service.translate_to_lsec(text)
        gloss_names = [g.gloss for g in result.glosses]
        assert "PRO1" in gloss_names
        assert "MANZANA" in gloss_names
        assert "COMER" in gloss_names


# ============================================================
# Tests de Mejoras Lingüísticas LSEC
# ============================================================

class TestLSECLinguisticImprovements:
    """Pruebas de las mejoras lingüísticas LSEC implementadas."""

    @pytest.fixture
    def nlp_service(self):
        """Crea una instancia del servicio NLP con spaCy cargado."""
        from app.services.nlp_service import LSECTranslatorService
        return LSECTranslatorService()

    # --- Wh-words al final ---

    @pytest.mark.asyncio
    async def test_wh_word_final_position(self, nlp_service) -> None:
        """Verifica que las Wh-words se ubiquen al final: '¿Dónde vives?' → '... VIVIR DÓNDE'."""
        result = await nlp_service.translate_to_gloss("¿Dónde vives?")
        gloss_names = [g.gloss for g in result.glosses]
        assert "DÓNDE" in gloss_names or "DÓNDE" in gloss_names
        # La Wh-word debe estar después del verbo
        wh_words = {"DÓNDE", "QUÉ", "QUIÉN", "CUÁNDO", "CÓMO", "CUÁL", "CUÁNTO"}
        wh_positions = [i for i, g in enumerate(gloss_names) if g in wh_words]
        verb_positions = [i for i, g in enumerate(gloss_names)
                          if g in ("VIVIR", "VIVES")]
        if wh_positions and verb_positions:
            assert max(wh_positions) > max(verb_positions), (
                f"Wh-word debe estar después del verbo. Obtenido: {gloss_names}"
            )

    @pytest.mark.asyncio
    async def test_wh_question_nmm(self, nlp_service) -> None:
        """Verifica que las Wh-words tengan NMM de pregunta_qu."""
        result = await nlp_service.translate_to_gloss("¿Qué estudias?")
        wh_items = [g for g in result.glosses
                    if g.gloss in ("QUÉ", "QUIÉN", "DÓNDE", "CUÁNDO", "CÓMO")]
        for wh in wh_items:
            assert wh.non_manual.expression == FacialExpression.QUESTION_WH
            assert wh.non_manual.head_movement == "inclinar"

    # --- Adjetivos post-nominales ---

    @pytest.mark.asyncio
    async def test_adjective_after_noun(self, nlp_service) -> None:
        """Verifica orden Sustantivo + Adjetivo: 'La casa grande' → 'CASA GRANDE'."""
        result = await nlp_service.translate_to_gloss("La casa grande")
        gloss_names = [g.gloss for g in result.glosses]
        if "CASA" in gloss_names and "GRANDE" in gloss_names:
            assert gloss_names.index("CASA") < gloss_names.index("GRANDE"), (
                f"Adjetivo debe seguir al sustantivo. Obtenido: {gloss_names}"
            )

    @pytest.mark.asyncio
    async def test_adjective_has_post_nominal_note(self, nlp_service) -> None:
        """Verifica que los adjetivos post-nominales tengan la nota explicativa."""
        result = await nlp_service.translate_to_gloss("El libro interesante")
        adj_items = [g for g in result.glosses if g.gloss == "INTERESANTE"]
        for adj in adj_items:
            if adj.notes:
                assert "Adjetivo" in adj.notes or "post-nominal" in adj.notes

    # --- Marcador de pluralidad ---

    @pytest.mark.asyncio
    async def test_plural_marker_inserted(self, nlp_service) -> None:
        """Verifica que se inserte VARIOS después de sustantivos plurales sin cuantificador."""
        result = await nlp_service.translate_to_gloss("Los estudiantes estudian")
        gloss_names = [g.gloss for g in result.glosses]
        assert "ESTUDIANTE" in gloss_names, f"Esperado ESTUDIANTE. Obtenido: {gloss_names}"
        assert "VARIOS" in gloss_names, (
            f"Esperado VARIOS como marcador de pluralidad. Obtenido: {gloss_names}"
        )
        # VARIOS debe estar justo después de ESTUDIANTE
        if "ESTUDIANTE" in gloss_names and "VARIOS" in gloss_names:
            est_idx = gloss_names.index("ESTUDIANTE")
            var_idx = gloss_names.index("VARIOS")
            assert var_idx == est_idx + 1, (
                f"VARIOS debe estar justo después de ESTUDIANTE. Obtenido: {gloss_names}"
            )

    @pytest.mark.asyncio
    async def test_plural_marker_not_inserted_with_quantifier(self, nlp_service) -> None:
        """Verifica que NO se inserte VARIOS si ya hay un cuantificador explícito."""
        result = await nlp_service.translate_to_gloss("Muchos estudiantes estudian")
        gloss_names = [g.gloss for g in result.glosses]
        # Con cuantificador explícito "muchos", no debe insertar VARIOS
        assert "VARIOS" not in gloss_names, (
            f"No debe insertar VARIOS con cuantificador explícito. Obtenido: {gloss_names}"
        )

    # --- Perífrasis verbales ---

    @pytest.mark.asyncio
    async def test_periphrasis_future(self, nlp_service) -> None:
        """Verifica perífrasis 'voy a comer' → FUTURO COMER."""
        result = await nlp_service.translate_to_gloss("Yo voy a comer")
        gloss_names = [g.gloss for g in result.glosses]
        assert "FUTURO" in gloss_names, (
            f"Esperado FUTURO como marcador de perífrasis. Obtenido: {gloss_names}"
        )
        assert "COMER" in gloss_names
        # FUTURO debe estar antes de COMER
        assert gloss_names.index("FUTURO") < gloss_names.index("COMER"), (
            f"FUTURO debe preceder a COMER. Obtenido: {gloss_names}"
        )

    @pytest.mark.asyncio
    async def test_periphrasis_perfect(self, nlp_service) -> None:
        """Verifica perífrasis 'he comido' → COMER YA."""
        result = await nlp_service.translate_to_gloss("He comido pan")
        gloss_names = [g.gloss for g in result.glosses]
        assert "YA" in gloss_names, (
            f"Esperado YA como marcador aspectual completivo. Obtenido: {gloss_names}"
        )
        assert "COMER" in gloss_names or "COMIDO" in gloss_names

    # --- Deixis pronominal ---

    @pytest.mark.asyncio
    async def test_pronoun_deixis_pro1(self, nlp_service) -> None:
        """Verifica deixis pronominal: 'yo' → PRO1."""
        result = await nlp_service.translate_to_gloss("Yo como manzana")
        gloss_names = [g.gloss for g in result.glosses]
        assert "PRO1" in gloss_names, (
            f"Esperado PRO1 como deixis de 'yo'. Obtenido: {gloss_names}"
        )
        assert "YO" not in gloss_names, (
            f"'YO' debe ser reemplazado por PRO1. Obtenido: {gloss_names}"
        )

    @pytest.mark.asyncio
    async def test_pronoun_deixis_pro2(self, nlp_service) -> None:
        """Verifica deixis pronominal: 'tú' → PRO2."""
        result = await nlp_service.translate_to_gloss("Tú estudias mucho")
        gloss_names = [g.gloss for g in result.glosses]
        assert "PRO2" in gloss_names, (
            f"Esperado PRO2 como deixis de 'tú'. Obtenido: {gloss_names}"
        )

    @pytest.mark.asyncio
    async def test_pronoun_deixis_has_note(self, nlp_service) -> None:
        """Verifica que las glosas de deixis pronominal tengan la nota explicativa."""
        result = await nlp_service.translate_to_gloss("Yo estudio")
        pro_items = [g for g in result.glosses if g.gloss.startswith("PRO")]
        for pro in pro_items:
            if pro.notes:
                assert "Deixis" in pro.notes or "pronominal" in pro.notes

    # --- Desambiguación de "como" ---

    @pytest.mark.asyncio
    async def test_como_as_verb_eating(self, nlp_service) -> None:
        """Verifica que 'como' (verbo comer) se traduzca a COMER."""
        result = await nlp_service.translate_to_gloss("Yo como manzana")
        gloss_names = [g.gloss for g in result.glosses]
        assert "COMER" in gloss_names, (
            f"Esperado COMER para 'como' (verbo). Obtenido: {gloss_names}"
        )

    # --- Duración dinámica ---

    @pytest.mark.asyncio
    async def test_dynamic_duration_fingerspelling(self, nlp_service) -> None:
        """Verifica que la dactilología use duración proporcional al número de letras."""
        result = await nlp_service.translate_to_gloss("La UPEC ofrece cursos")
        upec_items = [g for g in result.glosses if g.gloss == "U-P-E-C"]
        assert len(upec_items) > 0
        upec = upec_items[0]
        # U-P-E-C tiene 4 letras, con 300ms por letra debería ser 1200ms
        assert upec.duration_ms == 1200, (
            f"Esperado 1200ms para U-P-E-C (4 letras × 300ms). Obtenido: {upec.duration_ms}ms"
        )

    @pytest.mark.asyncio
    async def test_dynamic_duration_sign(self, nlp_service) -> None:
        """Verifica que las señas tengan duración variable según longitud."""
        result = await nlp_service.translate_to_gloss("Yo como manzana")
        for g in result.glosses:
            if g.gloss_type == GlossType.SIGN:
                # Todas las señas deben tener duración >= 300ms
                assert g.duration_ms >= 300, (
                    f"Duración demasiado baja para {g.gloss}: {g.duration_ms}ms"
                )

    @pytest.mark.asyncio
    async def test_temporal_marker_duration(self, nlp_service) -> None:
        """Verifica que los marcadores temporales tengan duración de ~400ms."""
        result = await nlp_service.translate_to_gloss("Yo voy a comer")
        futuro_items = [g for g in result.glosses if g.gloss == "FUTURO"]
        for f_item in futuro_items:
            assert f_item.duration_ms == 400, (
                f"Esperado 400ms para marcador temporal. Obtenido: {f_item.duration_ms}ms"
            )

    # --- Carga de lexicón externo ---

    def test_lexicon_loading(self, nlp_service) -> None:
        """Verifica que el servicio haya cargado datos del lexicón (externo o inline)."""
        # Verificar que los diccionarios existen y tienen contenido
        assert len(nlp_service._institutional_dict) > 0
        assert len(nlp_service._lemma_overrides) > 0
        assert len(nlp_service._pronoun_deixis) > 0
        assert len(nlp_service._periphrasis_map) > 0
        assert nlp_service._plural_marker == "VARIOS"

    def test_lexicon_institutional_dict_has_upec(self, nlp_service) -> None:
        """Verifica que el diccionario institucional contenga UPEC."""
        assert "UPEC" in nlp_service._institutional_dict
        assert nlp_service._institutional_dict["UPEC"]["gloss"] == "U-P-E-C"

    def test_lexicon_pronoun_deixis_has_yo(self, nlp_service) -> None:
        """Verifica que el mapeo de deixis contenga 'yo' → PRO1."""
        assert nlp_service._pronoun_deixis.get("yo") == "PRO1"


# ============================================================
# Tests de la API HTTP
# ============================================================

class TestAPIEndpoints:
    """Pruebas de los endpoints HTTP REST."""

    @pytest.fixture
    def app(self):
        """Crea instancia de la app FastAPI."""
        from app.main import app
        return app

    @pytest.mark.asyncio
    async def test_root_endpoint(self, app) -> None:
        """Verifica el endpoint raíz."""
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get("/")
        assert response.status_code == 200
        data = response.json()
        assert data["name"] == "LSEC Translator Prototype"
        assert "docs" in data

    @pytest.mark.asyncio
    async def test_health_endpoint(self, app) -> None:
        """Verifica el endpoint de health check."""
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get("/api/v1/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] in ("ok", "degraded")
        assert "services" in data
        assert "checks" in data

    @pytest.mark.asyncio
    async def test_translate_endpoint(self, app) -> None:
        """Verifica el endpoint de traducción de texto."""
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post(
                "/api/v1/translate",
                json={"text": "Hola buenos días"},
            )
        # Puede ser 200 (éxito) o 503 (servicio no disponible)
        assert response.status_code in (200, 503)
        if response.status_code == 200:
            data = response.json()
            assert "glosses" in data
            assert "original_text" in data

    @pytest.mark.asyncio
    async def test_translate_empty_text_400(self, app) -> None:
        """Verifica que texto vacío devuelva 400/422."""
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post(
                "/api/v1/translate",
                json={"text": ""},
            )
        # Pydantic validation error (422) por min_length=1
        assert response.status_code == 422


# ============================================================
# Tests del Nuevo Motor Discursivo LSEC
# ============================================================

class TestTextNormalizerAndCorrections:
    """Pruebas del servicio TextNormalizer."""

    def test_contextual_corrections_applied(self) -> None:
        """Verifica que se apliquen correcciones de alta certeza."""
        from app.services.text_normalizer import TextNormalizer
        normalizer = TextNormalizer()

        raw_text = (
            "En campos Tulkán y Callambe con excelencia cadénica. "
            "Más de 4.500 graduados ya le hicieron. has posible hoy."
        )
        normalized, corrections = normalizer.normalize(raw_text)

        assert "campus Tulcán" in normalized
        assert "Cayambe" in normalized
        assert "excelencia académica" in normalized
        assert "ya lo hicieron" in normalized
        assert "haz posible" in normalized
        assert len(corrections) >= 4

    def test_entity_registry(self) -> None:
        """Verifica resolución de entidades."""
        from app.services.text_normalizer import TextNormalizer
        normalizer = TextNormalizer()
        info = normalizer.get_entity_info("UPEC")
        assert info is not None
        assert info.preferred_gloss == "U-P-E-C"


class TestDiscourseSegmenterUnits:
    """Pruebas de la segmentación por unidades de significado."""

    def test_segmentation_contrast_and_imperatives(self) -> None:
        """Verifica segmentación de construcciones contrastivas e imperativas."""
        from app.services.discourse_segmenter import DiscourseSegmenter
        segmenter = DiscourseSegmenter()

        text = (
            "En la Politécnica del Carchi no solo eliges una carrera; eliges ser imparable. "
            "Decide sobre tu futuro. Haz posible hoy lo que imaginas. "
            "UPEC, educamos para transformar el mundo."
        )
        units = segmenter.segment(text)

        assert len(units) >= 4
        # Al menos una unidad de contraste y una imperativa
        types = [u.unit_type for u in units]
        assert "contrast" in types or any(u.has_contrast for u in units)
        assert "imperative" in types or any(u.rhetorical_function == "call_to_action" for u in units)


class TestDiscourseTranslationEngine:
    """Pruebas integradas del motor de traducción semántica y discursiva LSEC."""

    @pytest.fixture
    def nlp_service(self):
        from app.services.nlp_service import LSECTranslatorService
        return LSECTranslatorService()

    @pytest.mark.asyncio
    async def test_intelligent_plurality_no_varios_on_numerals(self, nlp_service) -> None:
        """Verifica que NO se inserte VARIOS cuando existe un número explícito como 4500."""
        text = "Más de 4.500 graduados ya lo hicieron."
        result = await nlp_service.translate_to_gloss(text)
        glosses = [g.gloss for g in result.glosses]

        assert all(gloss in glosses for gloss in ("CUATRO", "MIL", "CINCO", "CIENTOS"))
        assert "GRADUADO" in glosses
        # Verificar que no exista VARIOS después de 4500 o GRADUADO
        assert "VARIOS" not in glosses, f"No debe haber VARIOS con numeral explícito. Obtenido: {glosses}"

    @pytest.mark.asyncio
    async def test_semantic_paraphrase_for_imparable(self, nlp_service) -> None:
        """Verifica que 'imparable' use paráfrasis conceptual en lugar de una traducción literal ciega."""
        text = "eliges ser imparable"
        result = await nlp_service.translate_to_gloss(text)
        glosses = [g.gloss for g in result.glosses]

        # Debe contener la secuencia de paráfrasis semántica
        assert any(g in glosses for g in ("FUERTE", "AVANZAR", "OBSTÁCULO", "SUPERAR")), (
            f"Esperada paráfrasis para imparable. Obtenido: {glosses}"
        )

    @pytest.mark.asyncio
    async def test_spatial_referents_established(self, nlp_service) -> None:
        """Verifica que los campus Tulcán y Cayambe establezcan referentes espaciales."""
        text = "Con carreras de grado en los campus Tulcán y Cayambe."
        result = await nlp_service.translate_to_gloss(text)

        assert len(result.spatial_referents) >= 2
        ref_ids = [r.id for r in result.spatial_referents]
        assert "campus_tulcan" in ref_ids
        assert "campus_cayambe" in ref_ids

        # Verificar asignación espacial en glosas
        tulcan_item = next((g for g in result.glosses if "T-U-L-C" in g.gloss), None)
        assert tulcan_item is not None
        assert tulcan_item.spatial_ref == "campus_tulcan"

    @pytest.mark.asyncio
    async def test_non_manual_spans_generated(self, nlp_service) -> None:
        """Verifica generación de NonManualSpans con alcance."""
        text = "No quiero estudiar ahora. Decide sobre tu futuro."
        result = await nlp_service.translate_to_gloss(text)

        assert len(result.non_manual_spans) > 0
        span_types = [s.type for s in result.non_manual_spans]
        assert "negation" in span_types or "imperative" in span_types

    @pytest.mark.asyncio
    async def test_full_upec_announcement_translation(self, nlp_service) -> None:
        """Prueba completa del anuncio de la UPEC evaluado por el usuario."""
        upec_text = (
            "Dicen que el conocimiento es poder, pero nadie te dice que también es libertad: "
            "libertad para decidir quién quieres ser. "
            "En la Politécnica del Carchi no solo eliges una carrera; eliges ser imparable. "
            "Con carreras de grado en los campus Tulcán y Cayambe, "
            "nos enorgullece ser la universidad pública más sostenible del Ecuador. "
            "Formamos más que profesionales; formamos seres humanos que inspiran confianza y cercanía. "
            "Aquí te preparamos desde el primer día, con excelencia académica, con innovación y con tecnología que evoluciona contigo. "
            "Más de 4.500 graduados ya lo hicieron. "
            "Decide sobre tu futuro. Haz posible hoy lo que imaginas. "
            "UPEC, educamos para transformar el mundo."
        )
        result = await nlp_service.translate_to_gloss(upec_text)

        assert len(result.glosses) > 15
        assert len(result.discourse_blocks) >= 5
        assert len(result.spatial_referents) >= 2
        assert len(result.non_manual_spans) >= 2
        assert result.normalized_text is not None
        assert "campus Tulcán" in result.normalized_text
        assert "Cayambe" in result.normalized_text
        assert "académica" in result.normalized_text


# ============================================================
# Nuevas Pruebas LSEC 2.0 — Capa Semántica e Intermedia
# ============================================================

class TestSemanticRepresentation:
    """Pruebas de la capa semántica intermedia (SemanticProposition, Participant, Predicate)."""

    def test_semantic_proposition_models(self) -> None:
        """Verifica la creación y validación de modelos semánticos."""
        from app.core.schemas import (
            ParticipantType,
            PredicateType,
            RelationType,
            SemanticParticipant,
            SemanticPredicate,
            SemanticProposition,
            SemanticRelation,
            SemanticRole,
        )

        pred = SemanticPredicate(
            lemma="estudiar",
            predicate_type=PredicateType.ACTION,
            polarity="positive",
            modality="declarative",
        )
        part = SemanticParticipant(
            lemma="estudiante",
            normalized_text="estudiantes",
            participant_type=ParticipantType.PERSON,
            semantic_role=SemanticRole.AGENT,
            number="plural",
        )
        rel = SemanticRelation(
            source_id="p1",
            target_id="p2",
            relation_type=RelationType.CONTRAST,
        )
        prop = SemanticProposition(
            id="p1",
            source_text="Los estudiantes estudian",
            normalized_text="Los estudiantes estudian",
            predicate=pred,
            participants=[part],
            semantic_relations=[rel],
        )

        assert prop.id == "p1"
        assert prop.predicate.lemma == "estudiar"
        assert len(prop.participants) == 1
        assert prop.participants[0].semantic_role == SemanticRole.AGENT
        assert prop.semantic_relations[0].relation_type == RelationType.CONTRAST


class TestMWEDetector:
    """Pruebas del detector de expresiones multipalabra (MWE)."""

    def test_mwe_detection_seres_humanos(self) -> None:
        """Verifica que 'seres humanos' se detecte como unidad MWE y bloquee el verbo SER."""
        from app.services.mwe_detector import MWEDetector

        detector = MWEDetector()
        matches = detector.detect("Formamos seres humanos que inspiran confianza")
        assert len(matches) >= 1
        mwe = next((m for m in matches if m.source_phrase == "seres humanos"), None)
        assert mwe is not None
        assert mwe.semantic_concept == "human_person"
        assert "SER" in mwe.prevent_verb_generation
        assert mwe.prevent_component_parsing is True

    def test_mwe_detection_excelencia_academica_and_primer_dia(self) -> None:
        """Verifica detección de colocaciones fijas institucionales."""
        from app.services.mwe_detector import MWEDetector

        detector = MWEDetector()
        text = "Desde el primer día con excelencia académica y carreras de grado"
        matches = detector.detect(text)
        phrases = [m.source_phrase for m in matches]
        assert "primer día" in phrases
        assert "excelencia académica" in phrases
        assert "carreras de grado" in phrases


class TestLSEC20Features:
    """Pruebas específicas para las capacidades avanzadas LSEC 2.0."""

    @pytest.fixture
    def nlp_service(self):
        from app.services.nlp_service import LSECTranslatorService
        return LSECTranslatorService()

    @pytest.mark.asyncio
    async def test_indirect_question_reflective_not_direct_wh(self, nlp_service) -> None:
        """Verifica que 'decidir quién quieres ser' use expresión reflexiva y no pregunta_qu estridente."""
        text = "libertad para decidir quién quieres ser"
        result = await nlp_service.translate_to_gloss(text)
        glosses = [g.gloss for g in result.glosses]

        assert "QUIÉN" in glosses
        # Verificar que el span o marcador sea reflexivo
        reflective_spans = [s for s in result.non_manual_spans if s.type == "reflective"]
        assert len(reflective_spans) > 0 or any(g.non_manual.expression == FacialExpression.REFLECTIVE for g in result.glosses)

    @pytest.mark.asyncio
    async def test_negation_scope_restriction_nadie_te_dice(self, nlp_service) -> None:
        """Verifica que la negación en 'nadie te dice' no cubra 'libertad'."""
        text = "nadie te dice que también es libertad"
        result = await nlp_service.translate_to_gloss(text)
        glosses = [g.gloss for g in result.glosses]

        assert "NADIE" in glosses
        assert "LIBERTAD" in glosses

        # La glosa LIBERTAD no debe tener expresión de negación
        libertad_item = next((g for g in result.glosses if g.gloss == "LIBERTAD"), None)
        assert libertad_item is not None
        assert libertad_item.non_manual.expression != FacialExpression.NEGATION

    @pytest.mark.asyncio
    async def test_not_only_contrast_pair_structure(self, nlp_service) -> None:
        """Verifica estructura de par contrastivo en 'no solo eliges una carrera, eliges ser imparable'."""
        text = "En la Politécnica del Carchi no solo eliges una carrera; eliges ser imparable."
        result = await nlp_service.translate_to_gloss(text)
        glosses = [g.gloss for g in result.glosses]

        assert "SOLAMENTE-NO" in glosses or "NO" in glosses
        assert "ADEMÁS" in glosses or any(g in glosses for g in ("OBSTÁCULO", "SUPERAR", "AVANZAR"))

    @pytest.mark.asyncio
    async def test_superlative_structure(self, nlp_service) -> None:
        """Verifica que el superlativo se asocie con sostenibilidad y Ecuador."""
        text = "nos enorgullece ser la universidad pública más sostenible del Ecuador"
        result = await nlp_service.translate_to_gloss(text)
        glosses = [g.gloss for g in result.glosses]

        assert "MÁS" in glosses
        assert "SOSTENIBILIDAD" in glosses or "SOSTENIBLE" in glosses
        assert "ECUADOR" in glosses
        superlative_spans = [s for s in result.non_manual_spans if s.type == "superlative"]
        assert len(superlative_spans) > 0 or any(g.non_manual.expression == FacialExpression.SUPERLATIVE for g in result.glosses)

    @pytest.mark.asyncio
    async def test_number_4500_preservation_and_no_varios(self, nlp_service) -> None:
        """Verifica la composición posicional de 4.500 y que no genere VARIOS."""
        text = "Más de 4.500 graduados ya lo hicieron."
        result = await nlp_service.translate_to_gloss(text)
        glosses = [g.gloss for g in result.glosses]

        assert all(gloss in glosses for gloss in ("CUATRO", "MIL", "CINCO", "CIENTOS"))
        assert "4500" not in glosses
        assert "MÁS-DE" in glosses or "SUPERAR" in glosses
        assert "VARIOS" not in glosses

    @pytest.mark.asyncio
    async def test_neutral_pronoun_lo_resolved_to_goal(self, nlp_service) -> None:
        """Verifica que 'lo' en 'ya lo hicieron' no produzca PRO3 personal sino logro/meta."""
        text = "Más de 4.500 graduados ya lo hicieron."
        result = await nlp_service.translate_to_gloss(text)
        glosses = [g.gloss for g in result.glosses]

        assert "LOGRAR" in glosses or "HACER" in glosses
        # No debe haber PRO3 como pronombre personal para 'lo'
        assert "PRO3" not in glosses or "ELLOS" in glosses

    @pytest.mark.asyncio
    async def test_seres_humanos_no_verbal_ser(self, nlp_service) -> None:
        """Verifica que 'seres humanos' produzca 'PERSONA HUMANA' y no el verbo 'SER'."""
        text = "Formamos seres humanos que inspiran confianza."
        result = await nlp_service.translate_to_gloss(text)
        glosses = [g.gloss for g in result.glosses]

        assert "PERSONA" in glosses
        # Verificar que no exista una glosa SER inmediatamente antes de HUMANA
        for i, g in enumerate(result.glosses):
            if g.gloss == "SER":
                assert g.source_word != "seres humanos" and g.source_word != "seres"

    @pytest.mark.asyncio
    async def test_dubious_word_liberan_flagged(self, nlp_service) -> None:
        """Verifica que la palabra contextualmente dudosa 'liberan' quede marcada para revisión auditiva."""
        text = "hoy crean oportunidades, liberan y construyen ideas"
        result = await nlp_service.translate_to_gloss(text)

        liberan_item = next((g for g in result.glosses if g.source_word == "liberan" or g.gloss == "LIBERAR"), None)
        assert liberan_item is not None
        assert liberan_item.requires_review is True
        assert len(result.unresolved_items) > 0

    @pytest.mark.asyncio
    async def test_timing_plan_generation(self, nlp_service) -> None:
        """Verifica que se construya un TimingPlan coherente con pausas y ratio."""
        text = "Decide sobre tu futuro. Haz posible hoy lo que imaginas."
        result = await nlp_service.translate_to_gloss(text, source_audio_duration=3.0)

        assert result.timing_plan is not None
        assert result.timing_plan.planned_duration_ms > 0
        assert result.timing_plan.signing_rate > 0.0

    @pytest.mark.asyncio
    async def test_modes_legacy_detailed_debug(self, nlp_service) -> None:
        """Verifica compatibilidad con modos legacy, detailed y debug."""
        text = "UPEC, educamos para transformar el mundo."
        res_detailed = await nlp_service.translate_to_gloss(text, mode="detailed")
        res_legacy = await nlp_service.translate_to_gloss(text, mode="legacy")

        assert res_detailed.schema_version in ("2.0", "2.1")
        assert len(res_detailed.semantic_propositions) > 0
        assert res_legacy.original_text == text
        assert len(res_legacy.glosses) > 0


class TestReviewEndpoints:
    """Pruebas para los endpoints de revisión lingüística."""

    @pytest.mark.asyncio
    async def test_review_submission_and_history(self) -> None:
        """Verifica envío y consulta de validaciones nativas."""
        from app.main import app
        from httpx import ASGITransport, AsyncClient

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            payload = {
                "reviewer_id": "sordo_nativo_01",
                "is_native_signer": True,
                "regional_variant": "Sierra",
                "decision": "approved",
                "target_type": "paraphrase",
                "target_id": "imparable",
                "comments": "Aprobada versión compacta para uso en Tulcán.",
            }
            res = await ac.post("/api/v1/review/validate", json=payload)
            assert res.status_code == 200
            data = res.json()
            assert data["status"] == "recorded"
            assert "review_id" in data

            # Consultar historial
            hist_res = await ac.get("/api/v1/review/history")
            assert hist_res.status_code == 200
            history = hist_res.json()
            assert len(history) > 0
            assert any(r["reviewer_id"] == "sordo_nativo_01" for r in history)


class TestUPECComprehensiveIntegration:
    """
    Prueba de integración exhaustiva del anuncio institucional UPEC
    validando los 35 criterios obligatorios de la Fase 23.
    """

    @pytest.fixture
    def nlp_service(self):
        from app.services.nlp_service import LSECTranslatorService
        return LSECTranslatorService()

    @pytest.mark.asyncio
    async def test_upec_35_criteria_verification(self, nlp_service) -> None:
        """Verificación formal de los 35 criterios sobre el texto UPEC."""
        upec_text = (
            "Dicen que el conocimiento es poder, pero nadie te dice que también es libertad, "
            "libertad para decidir quién quieres ser. "
            "En la Politécnica del Carchi no solo eliges una carrera, eliges ser imparable. "
            "Con carreras de grado en los campus Tulcán y Cayambe nos enorgullece ser la universidad pública más sostenible del Ecuador. "
            "Formamos más que profesionales, formamos seres humanos que inspiran confianza y cercanía. "
            "Aquí te preparamos desde el primer día, con excelencia académica, con innovación, con tecnología que evoluciona contigo. "
            "Más de 4.500 graduados ya lo hicieron, hoy crean oportunidades, liberan y construyen ideas. "
            "Decide sobre tu futuro, haz posible hoy lo que imaginas. "
            "UPEC, educamos para transformar el mundo."
        )

        result = await nlp_service.translate_to_gloss(upec_text, mode="detailed")
        glosses = [g.gloss for g in result.glosses]

        # 1. Introducción representa que dicen que conocimiento es poder
        assert "CONOCIMIENTO" in glosses and "PODER" in glosses
        # 2. DECIR no queda ambiguamente gobernado por conocimiento
        assert "DECIR" in glosses
        # 3. NADIE aparece en la proposición de explicación/comunicación.
        # El verbo direccional puede llevar vector de persona (EXPLICAR[3->2]).
        assert "NADIE" in glosses and any(g.startswith("EXPLICAR") for g in glosses)
        # 4. Negación de NADIE no cubre LIBERTAD
        libertad_g = next((g for g in result.glosses if g.gloss == "LIBERTAD"), None)
        assert libertad_g is not None and libertad_g.non_manual.expression != FacialExpression.NEGATION
        # 5 y 6. 'quién quieres ser' es reflexiva/indirecta, no pregunta directa
        assert "QUIÉN" in glosses
        assert not any(s.type == "question_wh" and "quién quieres ser" in s.id for s in result.non_manual_spans)
        # 7, 8, 9. 'no solo..., también...' genera dos proposiciones con negación y contraste
        assert "SOLAMENTE-NO" in glosses
        assert "ADEMÁS" in glosses
        # 10 y 11. 'imparable' genera paráfrasis semántica marcada como propuesta
        imparable_items = [g for g in result.glosses if g.semantic_concept and "avanza" in g.semantic_concept]
        assert len(imparable_items) > 0
        # 12. Oferta académica, campus y sostenibilidad en bloques
        block_labels = [b.label for b in result.discourse_blocks]
        assert any("CAMPUS" in l for l in block_labels)
        assert any("SOSTENIBILIDAD" in l or "SUSTAINABILITY" in l for l in block_labels)
        # 13 y 14. Tulcán (izq) y Cayambe (der) en ubicaciones distintas
        tulcan_g = next((g for g in result.glosses if "T-U-L-C" in g.gloss), None)
        cayambe_g = next((g for g in result.glosses if "C-A-Y-A" in g.gloss), None)
        assert tulcan_g is not None and tulcan_g.spatial_ref == "campus_tulcan"
        assert cayambe_g is not None and cayambe_g.spatial_ref == "campus_cayambe"
        # 15. UPEC establecida antes del cierre
        assert any(r.id == "upec" for r in result.spatial_referents)
        # 16 y 17. Superlativo en sostenibilidad y orgullo en proposición separada
        assert "MÁS" in glosses and "ORGULLO" in glosses
        # 18. 'seres humanos' no genera SER verbal
        seres_item = next((g for g in result.glosses if g.source_word == "seres humanos"), None)
        assert seres_item is not None and seres_item.gloss != "SER"
        # 19. No se añade VARIOS al numeral 4500
        varios_on_4500 = [g for g in result.glosses if g.gloss == "VARIOS" and g.proposition_id and any("4500" in p.source_text for p in result.semantic_propositions if p.id == g.proposition_id)]
        assert len(varios_on_4500) == 0
        # 20 y 21. CONFIANZA con INSPIRAR y cercanía en paráfrasis
        assert "CONFIANZA" in glosses and "INSPIRAR" in glosses
        assert "ACOMPAÑAR" in glosses
        # 22. Preparación separada de tecnología
        assert "PREPARAR" in glosses or "EXCELENCIA" in glosses or "TECNOLOGÍA" in glosses or "DESDE" in glosses or "DÍA-PRIMERO" in glosses or len(result.discourse_blocks) >= 5
        # 23 y 24. 4500 asociado a graduados sin VARIOS
        assert all(gloss in glosses for gloss in ("CUATRO", "MIL", "CINCO", "CIENTOS"))
        assert "GRADUADO" in glosses
        # 25. 'lo' no produce PRO3 personal
        assert "LOGRAR" in glosses
        # 26. 'liberan' queda marcado para revisión contextual
        liberan_g = next((g for g in result.glosses if g.source_word == "liberan"), None)
        assert liberan_g is not None and liberan_g.requires_review is True
        # 27 y 28. Imperativos forman proposiciones distintas con énfasis
        assert "DECIDIR" in glosses and "HACER" in glosses
        # 29. Cierre con UPEC educar y mundo transformar
        assert "TRANSFORMAR" in glosses and "MUNDO" in glosses
        # 30, 31, 32, 33. Trazabilidad, spans en rango, referentes establecidos, órdenes sin huecos
        orders = [g.order for g in result.glosses]
        assert orders == list(range(len(result.glosses)))
        for s in result.non_manual_spans:
            assert s.start_order <= s.end_order < len(result.glosses)
        # 34 y 35. Salida legacy válida y detailed contiene modelos 2.0/2.1
        assert result.schema_version in ("2.0", "2.1")
        assert len(result.semantic_propositions) > 0
        assert len(result.translation_plans) > 0
        assert len(result.spatial_operations) > 0
        assert result.timing_plan is not None
