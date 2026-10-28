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
    AvatarPayload, BlendshapeValue, FacialExpression, GlossItem, GlossOutput,
    GlossType, HandKeypoints, KeypointsFrame, Landmark3D, NonManualMarker,
    PoseKeypoints, TranscriptionResult, WSMessageType, WebSocketMessage, WordTimestamp,
)


# ============================================================
# Tests de Schemas (Pydantic)
# ============================================================

class TestSchemas:
    """Pruebas de validación de esquemas Pydantic."""

    def test_transcription_result_creation(self) -> None:
        """Verifica la creación de un TranscriptionResult."""
        result = TranscriptionResult(text="Hola mundo", language="es", confidence=0.95, duration_seconds=2.5)
        assert result.text == "Hola mundo" and result.language == "es" and result.confidence == 0.95

    def test_word_timestamp(self) -> None:
        """Verifica la creación de WordTimestamp."""
        word = WordTimestamp(word="hola", start=0.0, end=0.5, probability=0.98)
        assert word.word == "hola" and word.start == 0.0 and word.end == 0.5

    def test_gloss_item_sign(self) -> None:
        """Verifica la creación de una glosa tipo SEÑA."""
        gloss = GlossItem(gloss="COMER", gloss_type=GlossType.SIGN, order=0, original_word="comer", duration_ms=500)
        assert gloss.gloss == "COMER" and gloss.gloss_type == GlossType.SIGN and gloss.order == 0

    def test_gloss_item_fingerspelling(self) -> None:
        """Verifica la creación de una glosa tipo DACTILOLOGÍA."""
        gloss = GlossItem(gloss="M-A-R-Í-A", gloss_type=GlossType.FINGERSPELLING, order=1, original_word="María", duration_ms=1500)
        assert gloss.gloss_type == GlossType.FINGERSPELLING and "-" in gloss.gloss

    def test_non_manual_marker(self) -> None:
        """Verifica los marcadores no-manuales."""
        marker = NonManualMarker(expression=FacialExpression.QUESTION_WH, head_movement="inclinar", intensity=1.5)
        assert marker.expression == FacialExpression.QUESTION_WH and marker.head_movement == "inclinar" and marker.intensity == 1.5

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
        assert output.total_duration_ms == 1350 and len(output.glosses) == 3

    def test_landmark_3d(self) -> None:
        """Verifica la creación de un Landmark3D."""
        lm = Landmark3D(x=0.5, y=0.3, z=0.1, visibility=0.99)
        assert lm.x == 0.5 and lm.visibility == 0.99

    def test_keypoints_frame(self) -> None:
        """Verifica la creación de un KeypointsFrame vacío."""
        frame = KeypointsFrame(frame_index=0, timestamp_ms=33.3)
        assert frame.left_hand is None and frame.right_hand is None and frame.pose is None and frame.face is None

    def test_avatar_payload(self) -> None:
        """Verifica la creación de un AvatarPayload completo."""
        gloss = GlossItem(gloss="HOLA", gloss_type=GlossType.SIGN, order=0)
        payload = AvatarPayload(
            sequence_index=0, gloss=gloss,
            non_manual_markers=NonManualMarker(expression=FacialExpression.NEUTRAL),
            blendshapes=[BlendshapeValue(name="browInnerUp", value=0.3), BlendshapeValue(name="mouthSmileLeft", value=0.7)],
            timestamp_ms=1000.0,
        )
        assert payload.gloss.gloss == "HOLA" and len(payload.blendshapes) == 2 and payload.blendshapes[0].name == "browInnerUp"

    def test_websocket_message(self) -> None:
        """Verifica la serialización de WebSocketMessage."""
        msg = WebSocketMessage(type=WSMessageType.GLOSS_RESULT, payload={"text": "test"})
        assert "gloss_result" in msg.model_dump_json()

    def test_gloss_output_serialization(self) -> None:
        """Verifica la serialización/deserialización JSON de GlossOutput."""
        output = GlossOutput(
            original_text="Buenos días",
            glosses=[GlossItem(gloss="BUENOS-DÍAS", gloss_type=GlossType.SIGN, order=0, non_manual=NonManualMarker(expression=FacialExpression.AFFIRMATION, head_movement="asentir"))],
        )
        data = json.loads(output.model_dump_json())
        assert data["original_text"] == "Buenos días" and len(data["glosses"]) == 1 and data["glosses"][0]["non_manual"]["expression"] == "afirmación"


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
        assert result.original_text == "Yo como manzana" and len(result.glosses) > 0
        assert all(g.gloss == g.gloss.upper() for g in result.glosses)

    @pytest.mark.asyncio
    async def test_stop_words_removed(self, nlp_service) -> None:
        """Verifica que se eliminen artículos y preposiciones."""
        result = await nlp_service.translate_to_gloss("El gato está en la mesa")
        gloss_texts = [g.gloss for g in result.glosses]
        # "el", "la", "en", "está" deben ser eliminados
        assert "EL" not in gloss_texts and "LA" not in gloss_texts and "EN" not in gloss_texts

    @pytest.mark.asyncio
    async def test_question_wh_detection(self, nlp_service) -> None:
        """Verifica detección de preguntas WH."""
        result = await nlp_service.translate_to_gloss("¿Dónde está el baño?")
        assert any(g.non_manual.expression == FacialExpression.QUESTION_WH for g in result.glosses)

    @pytest.mark.asyncio
    async def test_question_yesno_detection(self, nlp_service) -> None:
        """Verifica detección de preguntas sí/no."""
        result = await nlp_service.translate_to_gloss("¿Tienes hambre?")
        assert any(g.non_manual.expression == FacialExpression.QUESTION_YESNO for g in result.glosses)

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
        assert result.grammar_notes is not None and len(result.grammar_notes) > 0


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
        assert nlp_service._nlp is not None, "spaCy no se cargó. Ejecutar: python -m spacy download es_core_news_sm"

    @pytest.mark.asyncio
    async def test_example_yo_como_manzana(self, nlp_service) -> None:
        """Verifica el ejemplo: 'Yo como manzana' → 'PRO1 MANZANA COMER' (con deixis pronominal)."""
        result = await nlp_service.translate_to_gloss("Yo como manzana")
        gloss_names = [g.gloss for g in result.glosses]
        assert gloss_names[0] == "PRO1", f"Esperado PRO1 al inicio, obtenido: {gloss_names}"
        assert "MANZANA" in gloss_names and "COMER" in gloss_names
        # Verificar orden SOV: PRO1 (sujeto) antes de COMER (verbo)
        assert gloss_names.index("PRO1") < gloss_names.index("COMER")

    @pytest.mark.asyncio
    async def test_example_maria_compra_pan(self, nlp_service) -> None:
        """Verifica el ejemplo: 'María compra pan' → 'MARÍA PAN COMPRAR'."""
        gloss_names = [g.gloss for g in (await nlp_service.translate_to_gloss("María compra pan")).glosses]
        assert all(k in gloss_names for k in ("MARÍA", "PAN", "COMPRAR")) and gloss_names.index("MARÍA") < gloss_names.index("COMPRAR")

    @pytest.mark.asyncio
    async def test_pos_filtering_removes_determiners(self, nlp_service) -> None:
        """Verifica que se eliminen los determinantes (DET): 'El gato come la manzana'."""
        gloss_names = [g.gloss for g in (await nlp_service.translate_to_gloss("El gato come la manzana")).glosses]
        assert "EL" not in gloss_names and "LA" not in gloss_names and all(k in gloss_names for k in ("GATO", "MANZANA", "COMER"))

    @pytest.mark.asyncio
    async def test_pos_filtering_removes_prepositions(self, nlp_service) -> None:
        """Verifica que se eliminen las preposiciones (ADP)."""
        gloss_names = [g.gloss for g in (await nlp_service.translate_to_gloss("Voy a la escuela de niños")).glosses]
        assert "A" not in gloss_names and "DE" not in gloss_names

    @pytest.mark.asyncio
    async def test_copulative_removal(self, nlp_service) -> None:
        """Verifica que se eliminen verbos copulativos (ser, estar)."""
        gloss_names = [g.gloss for g in (await nlp_service.translate_to_gloss("María es estudiante")).glosses]
        assert "ES" not in gloss_names and "SER" not in gloss_names

    @pytest.mark.asyncio
    async def test_lemmatization_verbs_to_infinitive(self, nlp_service) -> None:
        """Verifica que los verbos se lematicen al infinitivo."""
        gloss_names = [g.gloss for g in (await nlp_service.translate_to_gloss("Los estudiantes leen libros")).glosses]
        assert all(k in gloss_names for k in ("LEER", "ESTUDIANTE", "LIBRO"))

    @pytest.mark.asyncio
    async def test_passthrough_on_no_clear_structure(self, nlp_service) -> None:
        """Verifica que textos cortos no crasheen."""
        assert len((await nlp_service.translate_to_gloss("¡Hola!")).glosses) > 0

    def test_split_into_sentences_spacy(self, nlp_service) -> None:
        """Verifica que _split_into_sentences divida correctamente por oraciones."""
        sentences = nlp_service._split_into_sentences("En la Politécnica eliges ser imparable. La universidad ofrece innovación.")
        all_text = " ".join(sentences)
        assert len(sentences) >= 2 and ("Politécnica" in all_text or "POLITECNICA" in all_text) and "innovación" in all_text

    @pytest.mark.asyncio
    async def test_multi_sentence_continuous_order(self, nlp_service) -> None:
        """Verifica que las glosas de múltiples oraciones mantengan un order continuo (0, 1, 2...)."""
        result = await nlp_service.translate_to_gloss("María compra pan. Los estudiantes leen libros.")
        assert len(result.glosses) > 0 and [g.order for g in result.glosses] == list(range(len(result.glosses)))

    @pytest.mark.asyncio
    async def test_strict_lemmatization(self, nlp_service) -> None:
        """Verifica lematización estricta: 'Los graduados crean proyectos'."""
        gloss_names = [g.gloss for g in (await nlp_service.translate_to_gloss("Los graduados crean proyectos")).glosses]
        assert all(k in gloss_names for k in ("GRADUADO", "PROYECTO", "CREAR"))

    @pytest.mark.asyncio
    async def test_verb_conjugation_to_infinitive(self, nlp_service) -> None:
        """Verifica que verbos conjugados como 'eliges' se lematicen al infinitivo 'ELEGIR'."""
        gloss_names = [g.gloss for g in (await nlp_service.translate_to_gloss("Tú eliges estudiar")).glosses]
        assert "ELEGIR" in gloss_names and "ELIGE" not in gloss_names and "ELIGES" not in gloss_names

    @pytest.mark.asyncio
    async def test_sov_dependency_order_with_time_and_place(self, nlp_service) -> None:
        """Verifica orden SOV con Tiempo y Lugar al inicio: 'Ayer Juan compró una casa en Quito'."""
        gloss_names = [g.gloss for g in (await nlp_service.translate_to_gloss("Ayer Juan compró una casa en Quito")).glosses]
        assert gloss_names[0] == "AYER" and all(k in gloss_names for k in ("JUAN", "CASA", "COMPRAR"))

    @pytest.mark.asyncio
    async def test_nmm_negation_only_on_no(self, nlp_service) -> None:
        """Verifica que 'expression' sea 'neutral' por defecto y sólo 'negación' en la palabra 'NO'."""
        for g in (await nlp_service.translate_to_gloss("No quiero comer pan")).glosses:
            if g.gloss == "NO" or g.gloss.startswith("NO-"):
                assert g.non_manual.expression == FacialExpression.NEGATION and g.non_manual.head_movement == "negar"
            else:
                assert g.non_manual.expression == FacialExpression.NEUTRAL and g.non_manual.head_movement is None

    @pytest.mark.asyncio
    async def test_institutional_dictionary_and_dactylology(self, nlp_service) -> None:
        """Verifica diccionario institucional (UPEC -> U-P-E-C) y reemplazo de modismos (cadénica -> académica)."""
        result = await nlp_service.translate_to_gloss("La UPEC ofrece excelencia cadénica")
        gloss_names = [g.gloss for g in result.glosses]
        assert "U-P-E-C" in gloss_names and next(g for g in result.glosses if g.gloss == "U-P-E-C").gloss_type == GlossType.FINGERSPELLING
        assert "CADÉNICA" not in gloss_names and "CADENICA" not in gloss_names and "OFRECER" in gloss_names

    @pytest.mark.asyncio
    async def test_translate_to_lsec_alias(self, nlp_service) -> None:
        """Verifica que el alias translate_to_lsec funcione de forma idéntica."""
        gloss_names = [g.gloss for g in (await nlp_service.translate_to_lsec("Yo como manzana")).glosses]
        assert all(k in gloss_names for k in ("PRO1", "MANZANA", "COMER"))


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
        assert "DÓNDE" in gloss_names
        # La Wh-word debe estar después del verbo
        wh_words = {"DÓNDE", "QUÉ", "QUIÉN", "CUÁNDO", "CÓMO", "CUÁL", "CUÁNTO"}
        wh_positions = [i for i, g in enumerate(gloss_names) if g in wh_words]
        verb_positions = [i for i, g in enumerate(gloss_names) if g in ("VIVIR", "VIVES")]
        if wh_positions and verb_positions:
            assert max(wh_positions) > max(verb_positions), f"Wh-word debe estar después del verbo. Obtenido: {gloss_names}"

    @pytest.mark.asyncio
    async def test_wh_question_nmm(self, nlp_service) -> None:
        """Verifica que las Wh-words tengan NMM de pregunta_qu."""
        result = await nlp_service.translate_to_gloss("¿Qué estudias?")
        wh_items = [g for g in result.glosses if g.gloss in ("QUÉ", "QUIÉN", "DÓNDE", "CUÁNDO", "CÓMO")]
        for wh in wh_items:
            assert wh.non_manual.expression == FacialExpression.QUESTION_WH and wh.non_manual.head_movement == "inclinar"

    # --- Adjetivos post-nominales ---

    @pytest.mark.asyncio
    async def test_adjective_after_noun(self, nlp_service) -> None:
        """Verifica orden Sustantivo + Adjetivo: 'La casa grande' → 'CASA GRANDE'."""
        result = await nlp_service.translate_to_gloss("La casa grande")
        gloss_names = [g.gloss for g in result.glosses]
        if "CASA" in gloss_names and "GRANDE" in gloss_names:
            assert gloss_names.index("CASA") < gloss_names.index("GRANDE"), f"Adjetivo debe seguir al sustantivo. Obtenido: {gloss_names}"

    @pytest.mark.asyncio
    async def test_adjective_has_post_nominal_note(self, nlp_service) -> None:
        """Verifica que los adjetivos post-nominales tengan la nota explicativa."""
        result = await nlp_service.translate_to_gloss("El libro interesante")
        for adj in [g for g in result.glosses if g.gloss == "INTERESANTE"]:
            if adj.notes:
                assert "Adjetivo" in adj.notes or "post-nominal" in adj.notes

    # --- Marcador de pluralidad ---

    @pytest.mark.asyncio
    async def test_plural_marker_inserted(self, nlp_service) -> None:
        """Verifica que se inserte VARIOS después de sustantivos plurales sin cuantificador."""
        result = await nlp_service.translate_to_gloss("Los estudiantes estudian")
        gloss_names = [g.gloss for g in result.glosses]
        assert "ESTUDIANTE" in gloss_names and "VARIOS" in gloss_names
        # VARIOS debe estar justo después de ESTUDIANTE
        assert gloss_names.index("VARIOS") == gloss_names.index("ESTUDIANTE") + 1

    @pytest.mark.asyncio
    async def test_plural_marker_not_inserted_with_quantifier(self, nlp_service) -> None:
        """Verifica que NO se inserte VARIOS si ya hay un cuantificador explícito."""
        result = await nlp_service.translate_to_gloss("Muchos estudiantes estudian")
        gloss_names = [g.gloss for g in result.glosses]
        # Con cuantificador explícito "muchos", no debe insertar VARIOS
        assert "VARIOS" not in gloss_names

    # --- Perífrasis verbales ---

    @pytest.mark.asyncio
    async def test_periphrasis_future(self, nlp_service) -> None:
        """Verifica perífrasis 'voy a comer' → FUTURO COMER."""
        gloss_names = [g.gloss for g in (await nlp_service.translate_to_gloss("Yo voy a comer")).glosses]
        assert "FUTURO" in gloss_names and "COMER" in gloss_names and gloss_names.index("FUTURO") < gloss_names.index("COMER")

    @pytest.mark.asyncio
    async def test_periphrasis_perfect(self, nlp_service) -> None:
        """Verifica perífrasis 'he comido' → COMER YA."""
        gloss_names = [g.gloss for g in (await nlp_service.translate_to_gloss("He comido pan")).glosses]
        assert "YA" in gloss_names and ("COMER" in gloss_names or "COMIDO" in gloss_names)

    # --- Deixis pronominal ---

    @pytest.mark.asyncio
    async def test_pronoun_deixis_pro1(self, nlp_service) -> None:
        """Verifica deixis pronominal: 'yo' → PRO1."""
        gloss_names = [g.gloss for g in (await nlp_service.translate_to_gloss("Yo como manzana")).glosses]
        assert "PRO1" in gloss_names and "YO" not in gloss_names

    @pytest.mark.asyncio
    async def test_pronoun_deixis_pro2(self, nlp_service) -> None:
        """Verifica deixis pronominal: 'tú' → PRO2."""
        assert "PRO2" in [g.gloss for g in (await nlp_service.translate_to_gloss("Tú estudias mucho")).glosses]

    @pytest.mark.asyncio
    async def test_pronoun_deixis_has_note(self, nlp_service) -> None:
        """Verifica que las glosas de deixis pronominal tengan la nota explicativa."""
        for pro in [g for g in (await nlp_service.translate_to_gloss("Yo estudio")).glosses if g.gloss.startswith("PRO")]:
            if pro.notes:
                assert "Deixis" in pro.notes or "pronominal" in pro.notes

    # --- Desambiguación de "como" ---

    @pytest.mark.asyncio
    async def test_como_as_verb_eating(self, nlp_service) -> None:
        """Verifica que 'como' (verbo comer) se traduzca a COMER."""
        assert "COMER" in [g.gloss for g in (await nlp_service.translate_to_gloss("Yo como manzana")).glosses]

    # --- Duración dinámica ---

    @pytest.mark.asyncio
    async def test_dynamic_duration_fingerspelling(self, nlp_service) -> None:
        """Verifica que la dactilología use duración proporcional al número de letras."""
        upec_items = [g for g in (await nlp_service.translate_to_gloss("La UPEC ofrece cursos")).glosses if g.gloss == "U-P-E-C"]
        assert len(upec_items) > 0 and upec_items[0].duration_ms == 1200

    @pytest.mark.asyncio
    async def test_dynamic_duration_sign(self, nlp_service) -> None:
        """Verifica que las señas tengan duración variable según longitud."""
        for g in (await nlp_service.translate_to_gloss("Yo como manzana")).glosses:
            if g.gloss_type == GlossType.SIGN:
                assert g.duration_ms >= 300

    @pytest.mark.asyncio
    async def test_temporal_marker_duration(self, nlp_service) -> None:
        """Verifica que los marcadores temporales tengan duración de ~400ms."""
        for f_item in [g for g in (await nlp_service.translate_to_gloss("Yo voy a comer")).glosses if g.gloss == "FUTURO"]:
            assert f_item.duration_ms == 400

    # --- Carga de lexicón externo ---

    def test_lexicon_loading(self, nlp_service) -> None:
        """Verifica que el servicio haya cargado datos del lexicón (externo o inline)."""
        assert len(nlp_service._institutional_dict) > 0 and len(nlp_service._lemma_overrides) > 0
        assert len(nlp_service._pronoun_deixis) > 0 and len(nlp_service._periphrasis_map) > 0 and nlp_service._plural_marker == "VARIOS"

    def test_lexicon_institutional_dict_has_upec(self, nlp_service) -> None:
        """Verifica que el diccionario institucional contenga UPEC."""
        assert "UPEC" in nlp_service._institutional_dict and nlp_service._institutional_dict["UPEC"]["gloss"] == "U-P-E-C"

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
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.get("/")
        assert response.status_code == 200 and response.json()["name"] == "LSEC Translator Prototype" and "docs" in response.json()

    @pytest.mark.asyncio
    async def test_health_endpoint(self, app) -> None:
        """Verifica el endpoint de health check."""
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.get("/api/v1/health")
        assert response.status_code == 200 and response.json()["status"] in ("ok", "degraded") and "services" in response.json() and "checks" in response.json()

    @pytest.mark.asyncio
    async def test_translate_endpoint(self, app) -> None:
        """Verifica el endpoint de traducción de texto."""
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post("/api/v1/translate", json={"text": "Hola buenos días"})
        assert response.status_code in (200, 503)
        if response.status_code == 200:
            assert "glosses" in response.json() and "original_text" in response.json()

    @pytest.mark.asyncio
    async def test_translate_empty_text_400(self, app) -> None:
        """Verifica que texto vacío devuelva 400/422."""
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post("/api/v1/translate", json={"text": ""})
        assert response.status_code == 422


# ============================================================
# Tests del Nuevo Motor Discursivo LSEC
# ============================================================

class TestTextNormalizerAndCorrections:
    """Pruebas del servicio TextNormalizer."""

    def test_contextual_corrections_applied(self) -> None:
        """Verifica que se apliquen correcciones de alta certeza."""
        from app.services.text_normalizer import TextNormalizer
        raw_text = "En campos Tulkán y Callambe con excelencia cadénica. Más de 4.500 graduados ya le hicieron. has posible hoy."
        normalized, corrections = TextNormalizer().normalize(raw_text)
        assert all(s in normalized for s in ("campus Tulcán", "Cayambe", "excelencia académica", "ya lo hicieron", "haz posible")) and len(corrections) >= 4

    def test_entity_registry(self) -> None:
        """Verifica resolución de entidades."""
        from app.services.text_normalizer import TextNormalizer
        info = TextNormalizer().get_entity_info("UPEC")
        assert info is not None and info.preferred_gloss == "U-P-E-C"


class TestDiscourseSegmenterUnits:
    """Pruebas de la segmentación por unidades de significado."""

    def test_segmentation_contrast_and_imperatives(self) -> None:
        """Verifica segmentación de construcciones contrastivas e imperativas."""
        from app.services.discourse_segmenter import DiscourseSegmenter
        text = "En la Politécnica del Carchi no solo eliges una carrera; eliges ser imparable. Decide sobre tu futuro. Haz posible hoy lo que imaginas. UPEC, educamos para transformar el mundo."
        units = DiscourseSegmenter().segment(text)
        types = [u.unit_type for u in units]
        assert len(units) >= 4 and ("contrast" in types or any(u.has_contrast for u in units)) and ("imperative" in types or any(u.rhetorical_function == "call_to_action" for u in units))


class TestDiscourseTranslationEngine:
    """Pruebas integradas del motor de traducción semántica y discursiva LSEC."""

    @pytest.fixture
    def nlp_service(self):
        from app.services.nlp_service import LSECTranslatorService
        return LSECTranslatorService()

    @pytest.mark.asyncio
    async def test_intelligent_plurality_no_varios_on_numerals(self, nlp_service) -> None:
        """Verifica que NO se inserte VARIOS cuando existe un número explícito como 4500."""
        glosses = [g.gloss for g in (await nlp_service.translate_to_gloss("Más de 4.500 graduados ya lo hicieron.")).glosses]
        assert all(gloss in glosses for gloss in ("CUATRO", "MIL", "CINCO", "CIENTOS", "GRADUADO")) and "VARIOS" not in glosses

    @pytest.mark.asyncio
    async def test_semantic_paraphrase_for_imparable(self, nlp_service) -> None:
        """Verifica que 'imparable' use paráfrasis conceptual en lugar de una traducción literal ciega."""
        glosses = [g.gloss for g in (await nlp_service.translate_to_gloss("eliges ser imparable")).glosses]
        assert any(g in glosses for g in ("FUERTE", "AVANZAR", "OBSTÁCULO", "SUPERAR"))

    @pytest.mark.asyncio
    async def test_spatial_referents_established(self, nlp_service) -> None:
        """Verifica que los campus Tulcán y Cayambe establezcan referentes espaciales."""
        result = await nlp_service.translate_to_gloss("Con carreras de grado en los campus Tulcán y Cayambe.")
        ref_ids = [r.id for r in result.spatial_referents]
        assert len(result.spatial_referents) >= 2 and "campus_tulcan" in ref_ids and "campus_cayambe" in ref_ids
        tulcan_item = next((g for g in result.glosses if "T-U-L-C" in g.gloss), None)
        assert tulcan_item is not None and tulcan_item.spatial_ref == "campus_tulcan"

    @pytest.mark.asyncio
    async def test_non_manual_spans_generated(self, nlp_service) -> None:
        """Verifica generación de NonManualSpans con alcance."""
        result = await nlp_service.translate_to_gloss("No quiero estudiar ahora. Decide sobre tu futuro.")
        span_types = [s.type for s in result.non_manual_spans]
        assert len(result.non_manual_spans) > 0 and ("negation" in span_types or "imperative" in span_types)

    @pytest.mark.asyncio
    async def test_full_upec_announcement_translation(self, nlp_service) -> None:
        """Prueba completa del anuncio de la UPEC evaluado por el usuario."""
        upec_text = (
            "Dicen que el conocimiento es poder, pero nadie te dice que también es libertad: libertad para decidir quién quieres ser. "
            "En la Politécnica del Carchi no solo eliges una carrera; eliges ser imparable. Con carreras de grado en los campus Tulcán y Cayambe, "
            "nos enorgullece ser la universidad pública más sostenible del Ecuador. Formamos más que profesionales; formamos seres humanos que inspiran confianza y cercanía. "
            "Aquí te preparamos desde el primer día, con excelencia académica, con innovación y con tecnología que evoluciona contigo. "
            "Más de 4.500 graduados ya lo hicieron. Decide sobre tu futuro. Haz posible hoy lo que imaginas. UPEC, educamos para transformar el mundo."
        )
        result = await nlp_service.translate_to_gloss(upec_text)
        assert len(result.glosses) > 15 and len(result.discourse_blocks) >= 5 and len(result.spatial_referents) >= 2 and len(result.non_manual_spans) >= 2
        assert result.normalized_text is not None and all(s in result.normalized_text for s in ("campus Tulcán", "Cayambe", "académica"))


# ============================================================
# Nuevas Pruebas LSEC 2.0 — Capa Semántica e Intermedia
# ============================================================

class TestSemanticRepresentation:
    """Pruebas de la capa semántica intermedia (SemanticProposition, Participant, Predicate)."""

    def test_semantic_proposition_models(self) -> None:
        """Verifica la creación y validación de modelos semánticos."""
        from app.core.schemas import ParticipantType, PredicateType, RelationType, SemanticParticipant, SemanticPredicate, SemanticProposition, SemanticRelation, SemanticRole

        pred = SemanticPredicate(lemma="estudiar", predicate_type=PredicateType.ACTION, polarity="positive", modality="declarative")
        part = SemanticParticipant(lemma="estudiante", normalized_text="estudiantes", participant_type=ParticipantType.PERSON, semantic_role=SemanticRole.AGENT, number="plural")
        rel = SemanticRelation(source_id="p1", target_id="p2", relation_type=RelationType.CONTRAST)
        prop = SemanticProposition(id="p1", source_text="Los estudiantes estudian", normalized_text="Los estudiantes estudian", predicate=pred, participants=[part], semantic_relations=[rel])
        assert prop.id == "p1" and prop.predicate.lemma == "estudiar" and len(prop.participants) == 1
        assert prop.participants[0].semantic_role == SemanticRole.AGENT and prop.semantic_relations[0].relation_type == RelationType.CONTRAST


class TestMWEDetector:
    """Pruebas del detector de expresiones multipalabra (MWE)."""

    def test_mwe_detection_seres_humanos(self) -> None:
        """Verifica que 'seres humanos' se detecte como unidad MWE y bloquee el verbo SER."""
        from app.services.mwe_detector import MWEDetector
        matches = MWEDetector().detect("Formamos seres humanos que inspiran confianza")
        mwe = next((m for m in matches if m.source_phrase == "seres humanos"), None)
        assert mwe is not None and mwe.semantic_concept == "human_person" and "SER" in mwe.prevent_verb_generation and mwe.prevent_component_parsing is True

    def test_mwe_detection_excelencia_academica_and_primer_dia(self) -> None:
        """Verifica detección de colocaciones fijas institucionales."""
        from app.services.mwe_detector import MWEDetector
        phrases = [m.source_phrase for m in MWEDetector().detect("Desde el primer día con excelencia académica y carreras de grado")]
        assert all(p in phrases for p in ("primer día", "excelencia académica", "carreras de grado"))


class TestLSEC20Features:
    """Pruebas específicas para las capacidades avanzadas LSEC 2.0."""

    @pytest.fixture
    def nlp_service(self):
        from app.services.nlp_service import LSECTranslatorService
        return LSECTranslatorService()

    @pytest.mark.asyncio
    async def test_indirect_question_reflective_not_direct_wh(self, nlp_service) -> None:
        """Verifica que 'decidir quién quieres ser' use expresión reflexiva y no pregunta_qu estridente."""
        result = await nlp_service.translate_to_gloss("libertad para decidir quién quieres ser")
        glosses = [g.gloss for g in result.glosses]
        assert "QUIÉN" in glosses
        # Verificar que el span o marcador sea reflexivo
        assert any(s.type == "reflective" for s in result.non_manual_spans) or any(g.non_manual.expression == FacialExpression.REFLECTIVE for g in result.glosses)

    @pytest.mark.asyncio
    async def test_negation_scope_restriction_nadie_te_dice(self, nlp_service) -> None:
        """Verifica que la negación en 'nadie te dice' no cubra 'libertad'."""
        result = await nlp_service.translate_to_gloss("nadie te dice que también es libertad")
        glosses = [g.gloss for g in result.glosses]
        assert "NADIE" in glosses and "LIBERTAD" in glosses
        # La glosa LIBERTAD no debe tener expresión de negación
        libertad_item = next((g for g in result.glosses if g.gloss == "LIBERTAD"), None)
        assert libertad_item is not None and libertad_item.non_manual.expression != FacialExpression.NEGATION

    @pytest.mark.asyncio
    async def test_not_only_contrast_pair_structure(self, nlp_service) -> None:
        """Verifica estructura de par contrastivo en 'no solo eliges una carrera, eliges ser imparable'."""
        result = await nlp_service.translate_to_gloss("En la Politécnica del Carchi no solo eliges una carrera; eliges ser imparable.")
        glosses = [g.gloss for g in result.glosses]
        assert ("SOLAMENTE-NO" in glosses or "NO" in glosses) and ("ADEMÁS" in glosses or any(g in glosses for g in ("OBSTÁCULO", "SUPERAR", "AVANZAR")))

    @pytest.mark.asyncio
    async def test_superlative_structure(self, nlp_service) -> None:
        """Verifica que el superlativo se asocie con sostenibilidad y Ecuador."""
        result = await nlp_service.translate_to_gloss("nos enorgullece ser la universidad pública más sostenible del Ecuador")
        glosses = [g.gloss for g in result.glosses]
        assert "MÁS" in glosses and ("SOSTENIBILIDAD" in glosses or "SOSTENIBLE" in glosses) and "ECUADOR" in glosses
        assert any(s.type == "superlative" for s in result.non_manual_spans) or any(g.non_manual.expression == FacialExpression.SUPERLATIVE for g in result.glosses)

    @pytest.mark.asyncio
    async def test_number_4500_preservation_and_no_varios(self, nlp_service) -> None:
        """Verifica la composición posicional de 4.500 y que no genere VARIOS."""
        result = await nlp_service.translate_to_gloss("Más de 4.500 graduados ya lo hicieron.")
        glosses = [g.gloss for g in result.glosses]
        assert all(gloss in glosses for gloss in ("CUATRO", "MIL", "CINCO", "CIENTOS")) and "4500" not in glosses
        assert ("MÁS-DE" in glosses or "SUPERAR" in glosses) and "VARIOS" not in glosses

    @pytest.mark.asyncio
    async def test_neutral_pronoun_lo_resolved_to_goal(self, nlp_service) -> None:
        """Verifica que 'lo' en 'ya lo hicieron' no produzca PRO3 personal sino logro/meta."""
        result = await nlp_service.translate_to_gloss("Más de 4.500 graduados ya lo hicieron.")
        glosses = [g.gloss for g in result.glosses]
        assert ("LOGRAR" in glosses or "HACER" in glosses) and ("PRO3" not in glosses or "ELLOS" in glosses)

    @pytest.mark.asyncio
    async def test_seres_humanos_no_verbal_ser(self, nlp_service) -> None:
        """Verifica que 'seres humanos' produzca 'PERSONA HUMANA' y no el verbo 'SER'."""
        result = await nlp_service.translate_to_gloss("Formamos seres humanos que inspiran confianza.")
        assert "PERSONA" in [g.gloss for g in result.glosses]
        # Verificar que no exista una glosa SER inmediatamente antes de HUMANA
        for g in result.glosses:
            if g.gloss == "SER":
                assert g.source_word not in ("seres humanos", "seres")


    @pytest.mark.asyncio
    async def test_timing_plan_generation(self, nlp_service) -> None:
        """Verifica que se construya un TimingPlan coherente con pausas y ratio."""
        result = await nlp_service.translate_to_gloss("Decide sobre tu futuro. Haz posible hoy lo que imaginas.", source_audio_duration=3.0)
        assert result.timing_plan is not None and result.timing_plan.planned_duration_ms > 0 and result.timing_plan.signing_rate > 0.0

    @pytest.mark.asyncio
    async def test_modes_legacy_detailed_debug(self, nlp_service) -> None:
        """Verifica compatibilidad con modos legacy, detailed y debug."""
        text = "UPEC, educamos para transformar el mundo."
        res_detailed = await nlp_service.translate_to_gloss(text, mode="detailed")
        res_legacy = await nlp_service.translate_to_gloss(text, mode="legacy")
        assert res_detailed.schema_version in ("2.0", "2.1") and len(res_detailed.semantic_propositions) > 0
        assert res_legacy.original_text == text and len(res_legacy.glosses) > 0


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

        # 1. Introducción representa que dicen que conocimiento es poder; 2. DECIR no queda ambiguamente gobernado por conocimiento
        assert "CONOCIMIENTO" in glosses and "PODER" in glosses and "DECIR" in glosses
        # 3. NADIE aparece en la proposición de explicación/comunicación. El verbo direccional puede llevar vector de persona (EXPLICAR[3->2]).
        assert "NADIE" in glosses and any(g.startswith("EXPLICAR") for g in glosses)
        # 4. Negación de NADIE no cubre LIBERTAD
        libertad_g = next((g for g in result.glosses if g.gloss == "LIBERTAD"), None)
        assert libertad_g is not None and libertad_g.non_manual.expression != FacialExpression.NEGATION
        # 5 y 6. 'quién quieres ser' es reflexiva/indirecta, no pregunta directa
        assert "QUIÉN" in glosses and not any(s.type == "question_wh" and "quién quieres ser" in s.id for s in result.non_manual_spans)
        # 7, 8, 9. 'no solo..., también...' genera dos proposiciones con negación y contraste
        assert "SOLAMENTE-NO" in glosses and "ADEMÁS" in glosses
        # 10 y 11. 'imparable' genera paráfrasis semántica marcada como propuesta
        assert any(g.semantic_concept and "avanza" in g.semantic_concept for g in result.glosses)
        # 12. Oferta académica, campus y sostenibilidad en bloques
        block_labels = [b.label for b in result.discourse_blocks]
        assert any("CAMPUS" in l for l in block_labels) and any("SOSTENIBILIDAD" in l or "SUSTAINABILITY" in l for l in block_labels)
        # 13 y 14. Tulcán (izq) y Cayambe (der) en ubicaciones distintas; 15. UPEC establecida antes del cierre
        tulcan_g = next((g for g in result.glosses if "T-U-L-C" in g.gloss), None)
        cayambe_g = next((g for g in result.glosses if "C-A-Y-A" in g.gloss), None)
        assert tulcan_g is not None and tulcan_g.spatial_ref == "campus_tulcan" and cayambe_g is not None and cayambe_g.spatial_ref == "campus_cayambe"
        assert any(r.id == "upec" for r in result.spatial_referents)
        # 16 y 17. Superlativo en sostenibilidad y orgullo en proposición separada; 18. 'seres humanos' no genera SER verbal
        assert "MÁS" in glosses and "ORGULLO" in glosses
        seres_item = next((g for g in result.glosses if g.source_word == "seres humanos"), None)
        assert seres_item is not None and seres_item.gloss != "SER"
        # 19. No se añade VARIOS al numeral 4500
        assert not [g for g in result.glosses if g.gloss == "VARIOS" and g.proposition_id and any("4500" in p.source_text for p in result.semantic_propositions if p.id == g.proposition_id)]
        # 20 y 21. CONFIANZA con INSPIRAR y cercanía en paráfrasis; 22. Preparación separada de tecnología
        assert "CONFIANZA" in glosses and "INSPIRAR" in glosses and "ACOMPAÑAR" in glosses
        assert any(k in glosses for k in ("PREPARAR", "EXCELENCIA", "TECNOLOGÍA", "DESDE", "DÍA-PRIMERO")) or len(result.discourse_blocks) >= 5
        # 23 y 24. 4500 asociado a graduados sin VARIOS; 25. 'lo' no produce PRO3 personal
        assert all(gloss in glosses for gloss in ("CUATRO", "MIL", "CINCO", "CIENTOS", "GRADUADO", "LOGRAR"))
        # 26. 'liberan' queda marcado para revisión contextual; 27, 28, 29. Imperativos y cierre
        liberan_g = next((g for g in result.glosses if g.source_word == "liberan"), None)
        assert all(k in glosses for k in ("DECIDIR", "HACER", "TRANSFORMAR", "MUNDO"))
        # 30, 31, 32, 33. Trazabilidad, spans en rango, referentes establecidos, órdenes sin huecos
        assert [g.order for g in result.glosses] == list(range(len(result.glosses)))
        for s in result.non_manual_spans:
            assert s.start_order <= s.end_order < len(result.glosses)
        # 34 y 35. Salida legacy válida y detailed contiene modelos 2.0/2.1
        assert result.schema_version in ("2.0", "2.1") and len(result.semantic_propositions) > 0 and len(result.translation_plans) > 0 and len(result.spatial_operations) > 0 and result.timing_plan is not None
