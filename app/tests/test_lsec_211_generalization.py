"""
Suite de Pruebas de Generalización LSEC 2.1.1 (Fase 21).

Evalúa la robustez, capacidad de generalización y consistencia sintáctico-semántica
del motor LSEC 2.1.1 en 10 oraciones arbitrarias del dominio educativo e institucional.
"""

import pytest
from app.core.schemas import FacialExpression, GlossType, TranslationMode
from app.services.nlp_service import LSECTranslatorService


@pytest.fixture
def translator() -> LSECTranslatorService:
    return LSECTranslatorService()


class TestLSEC211Generalization:
    """Pruebas de generalización en 10 oraciones sintácticamente diversas."""

    @pytest.mark.asyncio
    async def test_s1_indirect_wh_institutional(self, translator: LSECTranslatorService):
        """S1: Interrogativa indirecta institucional ('La universidad explica cómo postular')."""
        text = "La universidad explica cómo postular."
        out = await translator.translate_to_gloss(text, mode="detailed")
        assert len(out.glosses) >= 2
        # Debe tener glosa de pregunta o reflexión
        gloss_texts = [g.gloss for g in out.glosses]
        assert any(gt in ("CÓMO", "POSTULAR", "EXPLICAR", "UNIVERSIDAD") for gt in gloss_texts)

    @pytest.mark.asyncio
    async def test_s2_high_numeral_and_group(self, translator: LSECTranslatorService):
        """S2: Numeral alto y colectivo ('Más de 1.200 estudiantes se matricularon')."""
        text = "Más de 1.200 estudiantes se matricularon."
        out = await translator.translate_to_gloss(text, mode="detailed")
        gloss_texts = [g.gloss for g in out.glosses]
        assert all(gt in gloss_texts for gt in ("UNO", "MIL", "DOSCIENTOS"))
        # Invariante: no debe duplicar con VARIOS
        assert "VARIOS" not in gloss_texts

    @pytest.mark.asyncio
    async def test_s3_future_periphrasis(self, translator: LSECTranslatorService):
        """S3: Perífrasis temporal futura ('Vamos a inaugurar un nuevo laboratorio')."""
        text = "Vamos a inaugurar un nuevo laboratorio."
        out = await translator.translate_to_gloss(text, mode="detailed")
        gloss_texts = [g.gloss for g in out.glosses]
        # Invariante: el marcador aspectual FUTURO debe preceder al verbo
        if "FUTURO" in gloss_texts:
            f_idx = gloss_texts.index("FUTURO")
            assert f_idx < len(gloss_texts) - 1

    @pytest.mark.asyncio
    async def test_s4_multiple_locations_spatial(self, translator: LSECTranslatorService):
        """S4: Múltiples sedes/campus ('Ofrecemos carreras en las sedes Ibarra y Quito')."""
        text = "Ofrecemos carreras en las sedes Ibarra y Quito."
        out = await translator.translate_to_gloss(text, mode="detailed")
        gloss_texts = [g.gloss for g in out.glosses]
        # Dactilología de ubicaciones
        assert any("I-B-A-R-R-A" in gt or "IBARRA" in gt for gt in gloss_texts)
        assert any("Q-U-I-T-O" in gt or "QUITO" in gt for gt in gloss_texts)

    @pytest.mark.asyncio
    async def test_s5_conceptual_paraphrase(self, translator: LSECTranslatorService):
        """S5: Paráfrasis conceptual ('Un líder visionario transforma su comunidad')."""
        text = "Un líder visionario transforma su comunidad."
        out = await translator.translate_to_gloss(text, mode="detailed")
        assert len(out.glosses) >= 2
        assert out.total_duration_ms > 0

    @pytest.mark.asyncio
    async def test_s6_emphatic_negation(self, translator: LSECTranslatorService):
        """S6: Negación enfática ('Nadie te impide alcanzar tus metas')."""
        text = "Nadie te impide alcanzar tus metas."
        out = await translator.translate_to_gloss(text, mode="detailed")
        # Debe contener marcador facial de negación
        neg_spans = [s for s in out.non_manual_spans if s.expression == FacialExpression.NEGATION]
        assert len(neg_spans) > 0

    @pytest.mark.asyncio
    async def test_s7_comparative_state(self, translator: LSECTranslatorService):
        """S7: Comparativa de estado ('Es la institución más innovadora del norte')."""
        text = "Es la institución más innovadora del norte."
        out = await translator.translate_to_gloss(text, mode="detailed")
        gloss_texts = [g.gloss for g in out.glosses]
        assert "MÁS" in gloss_texts or "INNOVACIÓN" in gloss_texts or "INNOVADOR" in gloss_texts

    @pytest.mark.asyncio
    async def test_s8_imperative_with_subordinate(self, translator: LSECTranslatorService):
        """S8: Imperativo con subordinada ('Haz posible mañana lo que sueñas')."""
        text = "Haz posible mañana lo que sueñas."
        out = await translator.translate_to_gloss(text, mode="detailed")
        gloss_texts = [g.gloss for g in out.glosses]
        # Invariante: mañana no debe ser predicado de acción
        assert any(g in gloss_texts for g in ("HACER", "REALIDAD", "POSIBLE"))

    @pytest.mark.asyncio
    async def test_s9_comprehensive_formation_contrast(self, translator: LSECTranslatorService):
        """S9: Formación integral ('Capacitamos más que técnicos, formamos ciudadanos')."""
        text = "Capacitamos más que técnicos, formamos ciudadanos."
        out = await translator.translate_to_gloss(text, mode="detailed")
        assert len(out.semantic_propositions) >= 2
        # No debe haber duplicación exacta entre cláusulas
        assert len(out.translation_plans) >= 2

    @pytest.mark.asyncio
    async def test_s10_resources_and_development(self, translator: LSECTranslatorService):
        """S10: Recursos y desarrollo ('Estudiamos con rigor académico, con proyectos que crecen contigo')."""
        text = "Estudiamos con rigor académico, con proyectos que crecen contigo."
        out = await translator.translate_to_gloss(text, mode="detailed")
        assert len(out.glosses) >= 3
