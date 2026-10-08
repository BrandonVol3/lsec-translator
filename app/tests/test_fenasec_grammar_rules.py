"""Pruebas de las reglas FENASEC/CONADIS, limpieza de muletillas y modismos ecuatorianos."""
import asyncio

import pytest

from app.core.schemas import FacialExpression
from app.services.nlp_service import LSECTranslatorService
from app.services.spoken_text_cleaner import SpokenTextCleaner


@pytest.fixture(scope="module")
def svc():
    return LSECTranslatorService()


def _run(svc, text):
    return asyncio.run(svc.translate_to_gloss(text))


def _glosses(svc, text):
    return [g.gloss for g in _run(svc, text).glosses]


# --- Regla 1: cópula nula -------------------------------------------------
@pytest.mark.parametrize("text,expected", [
    ("La flor es amarilla", ["FLOR", "AMARILLO"]),
    ("María es doctora", ["MARÍA", "DOCTORA"]),
    ("Yo estoy en la fiesta", ["PRO1", "FIESTA"]),
])
def test_copula_nula(svc, text, expected):
    assert _glosses(svc, text) == expected


# --- Regla 2: negación ----------------------------------------------------
def test_negacion_final_simple(svc):
    g = _glosses(svc, "Él no come carne")
    assert g[-1] == "NO"


@pytest.mark.parametrize("text,incorporated", [
    ("Yo no sé nada", "NO-SABER"),
    ("No quiero salir", "NO-QUERER"),
])
def test_negacion_incorporada(svc, text, incorporated):
    g = _glosses(svc, text)
    assert incorporated in g
    assert "NO" not in g


# --- Regla 3: seriación verbal --------------------------------------------
def test_seriacion_verbal_sujeto_una_vez(svc):
    g = _glosses(svc, "Yo entré a la escuela, estudié, jugué y aprendí")
    assert g.count("PRO1") == 1
    assert g[-4:] == ["ENTRAR", "ESTUDIAR", "JUGAR", "APRENDER"]
    assert "HACIA" not in g


# --- Regla 4: verbos direccionales ----------------------------------------
def test_verbo_direccional_1_a_2(svc):
    g = _glosses(svc, "Yo te aviso mañana")
    assert "AVISAR[1->2]" in g
    assert "PRO1" not in g and "PRO2" not in g


def test_verbo_direccional_3_a_1_pl(svc):
    g = _glosses(svc, "El profesor nos enseña LSEC")
    assert "ENSEÑAR[3->1-PL]" in g
    assert "PROFESOR" in g
    assert "PRO1-PL" not in g


# --- Regla 5: duplicación de intensidad -----------------------------------
@pytest.mark.parametrize("text,expected", [
    ("Está lloviendo fuertísimo", ["LLOVER++"]),
    ("Estudió muchísimo", ["ESTUDIAR++"]),
])
def test_duplicacion_intensidad(svc, text, expected):
    out = _run(svc, text)
    assert [g.gloss for g in out.glosses] == expected
    assert not [w for w in out.warnings if w.blocking]


# --- Regla 6: preguntas retóricas -----------------------------------------
def test_pregunta_retorica(svc):
    out = _run(svc, "¿Por qué estudiamos? Para progresar")
    g = [x.gloss for x in out.glosses]
    assert "POR-QUÉ" in g
    assert not [w for w in out.warnings if w.blocking]
    porque = next(x for x in out.glosses if x.gloss == "POR-QUÉ")
    assert porque.non_manual.expression == FacialExpression.RHETORICAL


def test_pregunta_directa_no_es_retorica(svc):
    out = _run(svc, "¿Dónde trabajas tú?")
    g = [x.gloss for x in out.glosses]
    assert g[-1] == "DÓNDE"
    donde = out.glosses[-1]
    assert donde.non_manual.expression == FacialExpression.QUESTION_WH


# --- Muletillas -----------------------------------------------------------
@pytest.mark.parametrize("text,expected", [
    ("eh este yo quiero comer pan", ["PRO1", "PAN", "QUERER", "COMER"]),
    ("yo yo quiero un café caliente", ["PRO1", "CAFÉ", "CALIENTE", "QUERER"]),
])
def test_muletillas_no_filtran(svc, text, expected):
    assert _glosses(svc, text) == expected


def test_cleaner_no_toca_texto_legitimo():
    cleaner = SpokenTextCleaner()
    for txt in ("este libro es bueno", "esta casa es muy muy grande"):
        spans = []
        pos = 0
        for w in txt.split():
            start = txt.index(w, pos)
            spans.append((start, start + len(w)))
            pos = start + len(w)
        res = cleaner.clean(txt, spans)
        assert res.text == txt


# --- Modismos ecuatorianos ------------------------------------------------
def test_modismos(svc):
    assert _glosses(svc, "mi ñaño tiene dos guaguas") == ["PRO1", "HERMANO", "NIÑO", "DOS", "TENER"]
    assert _glosses(svc, "dame pasando la sal")[0] == "POR-FAVOR"
