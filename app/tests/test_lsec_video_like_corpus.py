"""
Regresiones del corpus LSEC de generalización (textos tipo UPEC/institucional).

Cubre los fallos detectados al traducir textos nuevos similares a las
transcripciones de los videos 1, 2 y 3: homógrafos verbales, lemas nominales
truncados, conectores con contenido semántico, cobertura de conceptos,
predicados elípticos y dactilología espuria.
"""

from __future__ import annotations

import asyncio

import pytest

from app.core.schemas import GlossType, SemanticRole
from app.services.nlp_service import LSECTranslatorService


@pytest.fixture
def svc() -> LSECTranslatorService:
    return LSECTranslatorService()


def _run(svc: LSECTranslatorService, text: str):
    return asyncio.run(
        svc.translate_to_gloss(text, mode="detailed", paraphrase_budget="compact")
    )


def _glosses(out) -> list[str]:
    return [g.gloss for g in out.glosses]


def _codes(out) -> list[str]:
    return [w.code for w in out.warnings]


class TestVideoLikeCorpus:
    def test_ven_is_venir_not_ver(self, svc):
        out = _run(svc, "Ven al campus de Tulcán.")
        assert "VENIR" in _glosses(out)
        assert "VER" not in _glosses(out)
        assert out.semantic_propositions[0].predicate.lemma == "venir"
        assert "SOURCE_CONTENT_DROPPED" not in _codes(out)

    def test_come_manzana_keeps_verb_lemma(self, svc):
        out = _run(svc, "¿Tú comes manzana?")
        glosses = _glosses(out)
        assert "COMER" in glosses
        assert "MANZANA" in glosses
        assert "COMES" not in glosses

    def test_wh_question_does_not_pluralize_verb(self, svc):
        out = _run(svc, "¿Qué comes?")
        glosses = _glosses(out)
        assert "COMER" in glosses
        assert "VARIOS" not in glosses
        assert "QUÉ" in glosses

    def test_donde_estudias_is_verb(self, svc):
        out = _run(svc, "¿Dónde estudias?")
        glosses = _glosses(out)
        assert "ESTUDIAR" in glosses
        assert "VARIOS" not in glosses
        loc = next(p for p in out.semantic_propositions[0].participants if p.semantic_role == SemanticRole.LOCATION)
        assert loc.lemma == "dónde"

    def test_possessive_plural_has_no_spurious_pro2(self, svc):
        out = _run(svc, "Nuestros docentes investigan nuevas formas de enseñar.")
        glosses = _glosses(out)
        assert "PRO1-PL" in glosses
        assert "PRO2" not in glosses
        assert glosses.count("VARIOS") == 2  # docentes y formas
        assert "FORMA" in glosses and "NUEVO" in glosses

    def test_from_the_start_coverage(self, svc):
        out = _run(svc, "La matrícula se realiza en línea desde el primer día.")
        assert "SOURCE_CONTENT_DROPPED" not in _codes(out)
        glosses = _glosses(out)
        assert "DESDE" in glosses and "PRIMERO" in glosses

    def test_passive_auxiliary_is_not_glossed(self, svc):
        out = _run(svc, "La universidad, que fue fundada hace varias décadas, mantiene su compromiso con la excelencia.")
        glosses = _glosses(out)
        assert "SER" not in glosses
        assert "FUNDAR" in glosses and "MANTENER" in glosses

    def test_elliptical_fragment_does_not_fabricate_afirmar(self, svc):
        out = _run(svc, "No solo formamos profesionales competentes, también ciudadanos responsables y solidarios.")
        assert len(out.semantic_propositions) == 2
        assert out.semantic_propositions[0].predicate.lemma == "formar"
        assert out.semantic_propositions[1].predicate is None
        assert "AFIRMAR" not in _glosses(out)

    def test_more_than_quantifier_coverage(self, svc):
        out = _run(svc, "Más de cinco mil graduados ejercen su profesión en todo el país.")
        assert "SOURCE_CONTENT_DROPPED" not in _codes(out)
        glosses = _glosses(out)
        assert "MÁS-DE" in glosses and "CINCO-MIL" in glosses

    def test_por_que_is_one_unit(self, svc):
        out = _run(svc, "¿Por qué elegir la UPEC?")
        glosses = _glosses(out)
        assert "POR-QUÉ" in glosses
        assert "POR" not in glosses

    def test_por_favor_is_not_split(self, svc):
        out = _run(svc, "Por favor, muchas gracias y buenas tardes a todos")
        glosses = _glosses(out)
        assert "POR-FAVOR" in glosses
        assert "POR" not in glosses

    def test_estatal_is_a_sign_not_fingerspelling(self, svc):
        out = _run(svc, "La Universidad Politécnica Estatal del Carchi promueve la inclusión y la diversidad.")
        estatal = next(g for g in out.glosses if g.source_word and g.source_word.lower() == "estatal")
        assert estatal.gloss == "ESTATAL"
        assert estatal.gloss_type != GlossType.FINGERSPELLING

    def test_nominal_lemmas_are_not_truncated(self, svc):
        out_modern = _run(svc, "El campus de Cayambe cuenta con laboratorios modernos.")
        assert "MODERNO" in _glosses(out_modern)
        out_pre = _run(svc, "Las prácticas preprofesionales se desarrollan en empresas públicas y privadas.")
        assert "PREPROFESIONAL" in _glosses(out_pre)

    def test_semantic_connectors_are_preserved(self, svc):
        for text, connector in (
            ("Aunque la lluvia cayó durante toda la mañana, los estudiantes continuaron con la jornada académica.", "AUNQUE"),
            ("Si apruebas el examen de admisión, podrás matricularte en la carrera que elegiste.", "SI"),
            ("Cuando termines la carrera, podrás trabajar en hospitales, clínicas o centros de investigación.", "CUANDO"),
            ("Los estudiantes no asistieron a clases por la emergencia.", "POR"),
        ):
            glosses = _glosses(_run(svc, text))
            assert connector in glosses, (text, connector, glosses)

    def test_prepositions_with_content_are_preserved(self, svc):
        sin = _glosses(_run(svc, "No se permite el ingreso sin identificación."))
        assert "SIN" in sin
        sobre = _glosses(_run(svc, "Los investigadores publicaron un estudio sobre la calidad del agua en las comunidades rurales."))
        assert "SOBRE" in sobre
        hasta = _glosses(_run(svc, "La biblioteca permanece abierta hasta las diez de la noche."))
        assert "HASTA" in hasta
