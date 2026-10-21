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


def test_negacion_incorporada_multiple_en_clausula(svc):
    g1 = _glosses(svc, "Yo no sé la respuesta, no puedo asistir y no quiero mentir")
    assert "NO-SABER" in g1
    assert "NO-PODER" in g1
    assert "NO-QUERER" in g1
    assert "QUERER" not in g1

    g2 = _glosses(svc, "No me gusta el ruido y no hay suficiente tiempo")
    assert "NO-GUSTAR" in g2
    assert "NO-HABER" in g2
    assert "GUSTAR" not in g2


def test_verbos_direccionales_encliticos(svc):
    g_ayudame = _glosses(svc, "Ayúdame con este trámite urgente, por favor")
    assert "AYUDAR[2->1]" in g_ayudame
    assert "AYÚDAME" not in g_ayudame

    g_compleja = _glosses(
        svc,
        "Primero, cuando llegues a la oficina (si el director ya está presente), entrégale el documento; después, avísame por teléfono porque necesitamos confirmar el presupuesto antes del viernes.",
    )
    assert "ENTREGAR[2->3]" in g_compleja
    assert "AVISAR[2->1]" in g_compleja


def test_duplicacion_intensidad_verbal_mucho(svc):
    g = _glosses(svc, "En invierno llueve mucho y el río crece muchísimo")
    assert "LLOVER++" in g
    assert "CRECER++" in g
    assert "MUCHO" not in g


def test_pure_unit_derive_ar_infinitive():
    from app.services.semantic_parser import SpanishVerbLexicon

    assert SpanishVerbLexicon.derive_ar_infinitive("dejaste") == "dejar"
    assert SpanishVerbLexicon.derive_ar_infinitive("llevaron") == "llevar"
    assert SpanishVerbLexicon.derive_ar_infinitive("caminamos") == "caminar"
    assert SpanishVerbLexicon.derive_ar_infinitive("vamos") == "ir"
    assert SpanishVerbLexicon.derive_ar_infinitive("cuando") is None
    assert SpanishVerbLexicon.derive_ar_infinitive("bando") is None
    assert SpanishVerbLexicon.derive_ar_infinitive("dibujo") is None


def test_pure_unit_split_enclitic():
    from app.services.semantic_parser import SpanishVerbLexicon

    assert SpanishVerbLexicon.split_enclitic("verlo") == ("ver", "lo")
    assert SpanishVerbLexicon.split_enclitic("avísame") == ("avisar", "me")
    assert SpanishVerbLexicon.split_enclitic("ayúdame") == ("ayudar", "me")
    assert SpanishVerbLexicon.split_enclitic("entrégalo") == ("entregar", "lo")
    assert SpanishVerbLexicon.split_enclitic("inscríbete") == ("inscribir", "te")
    assert SpanishVerbLexicon.split_enclitic("comunícate") == ("comunicar", "te")
    assert SpanishVerbLexicon.split_enclitic("dímelo") == ("decir", "me")
    assert SpanishVerbLexicon.split_enclitic("entréganoslo") == ("entregar", "nos")
    assert SpanishVerbLexicon.split_enclitic("explícaselo") == ("explicar", "se")
    for non_enc in ("película", "trámite", "trámites", "límite", "límites", "escándalo", "escándalos"):
        assert SpanishVerbLexicon.split_enclitic(non_enc) == (non_enc, None)
    assert SpanishVerbLexicon.split_enclitic("este", pos="DET") == ("este", None)


def test_pure_unit_contains_negation():
    from app.services.text_normalizer import contains_negation

    for pos_txt in (
        "Dame pasando el cuaderno",
        "Mi número de teléfono es 0991234567",
        "El arte moderno inspira paz",
        "En invierno llueve mucho",
        "Cuando llegues a la oficina",
        "Sin embargo aprobaré el examen",
        "Sino también los docentes colaboran",
    ):
        assert not contains_negation(pos_txt), f"Falso positivo de negación en: {pos_txt}"

    for neg_txt in (
        "Yo no sé la respuesta",
        "Nunca llega tarde",
        "Jamás miente",
        "Nadie vino hoy",
        "Tampoco quiero salir",
    ):
        assert contains_negation(neg_txt), f"Falso negativo de negación en: {neg_txt}"


def test_pure_unit_apply_incorporated_negation_mock_doc():
    from types import SimpleNamespace
    from app.core.schemas import GlossItem, GlossType
    from app.services.fenasec_rules import apply_incorporated_negation

    t_saber = SimpleNamespace(text="sé", i=2, head=SimpleNamespace(i=2), dep_="ROOT")
    t_no1 = SimpleNamespace(text="no", i=1, head=t_saber, dep_="advmod")
    t_poder = SimpleNamespace(text="puedo", i=5, head=t_saber, dep_="conj")
    t_no2 = SimpleNamespace(text="no", i=4, head=t_poder, dep_="advmod")
    t_querer = SimpleNamespace(text="quiero", i=8, head=t_saber, dep_="conj")
    t_no3 = SimpleNamespace(text="no", i=7, head=t_querer, dep_="advmod")
    mock_doc = [t_no1, t_saber, t_no2, t_poder, t_no3, t_querer]

    items = [
        GlossItem(gloss="SABER", gloss_type=GlossType.SIGN, order=0, source_word="sé"),
        GlossItem(gloss="PODER", gloss_type=GlossType.SIGN, order=1, source_word="puedo"),
        GlossItem(gloss="QUERER", gloss_type=GlossType.SIGN, order=2, source_word="quiero"),
        GlossItem(gloss="NO", gloss_type=GlossType.SIGN, order=3, source_word="no"),
        GlossItem(gloss="NO", gloss_type=GlossType.SIGN, order=4, source_word="no"),
        GlossItem(gloss="NO", gloss_type=GlossType.SIGN, order=5, source_word="no"),
    ]
    apply_incorporated_negation(items, mock_doc)
    assert [it.gloss for it in items] == ["NO-SABER", "NO-PODER", "NO-QUERER"]


def test_f24_possible_conjugated_gloss_warning():
    from app.core.schemas import DictionarySignMetadata, GlossItem, GlossType, ValidationSeverity
    from app.services.validator import StructuralValidator

    validator = StructuralValidator()
    bad_gloss = GlossItem(
        gloss="DEJASTAR",
        gloss_type=GlossType.SIGN,
        order=0,
        source_word="dejaste",
        normalized_word="dejastar",
    )
    ok_gloss = GlossItem(
        gloss="CAMINAR",
        gloss_type=GlossType.SIGN,
        order=1,
        source_word="caminamos",
        normalized_word="caminar",
        dictionary_metadata=DictionarySignMetadata(
            verified_in_conadis=True,
            status="VERIFICADO_CONADIS",
        ),
    )
    errs = validator._validate_lsec_211_invariants(
        original_text="dejaste",
        normalized_text="dejaste",
        propositions=[],
        glosses=[bad_gloss, ok_gloss],
        blocks=[],
        plans=[],
        timing_plan=None,
        validation_metadata=None,
    )
    conj_warns = [e for e in errs if e.code == "POSSIBLE_CONJUGATED_GLOSS"]
    assert len(conj_warns) == 1
    assert conj_warns[0].severity == ValidationSeverity.WARNING
    assert conj_warns[0].blocking is False
    assert str(bad_gloss.id) in conj_warns[0].affected_ids


def test_double_enclitics_and_multiword_proper_nouns(svc):
    assert "DAR[2->1]" in _glosses(svc, "Dámelo ahora")
    assert "ENSEÑAR[2->3]" in _glosses(svc, "Enséñaselo al estudiante")
    assert "ENTREGAR[2->1-PL]" in _glosses(svc, "Entréganoslo mañana")
    assert any(x.startswith("DECIR") for x in _glosses(svc, "Dímelo ahora"))
    assert any(x.startswith("EXPLICAR") for x in _glosses(svc, "Explícaselo al estudiante"))

    g_propn = _glosses(svc, "Juan Carlos compra pan")
    # Multi-word proper noun stays contiguous before object/verb
    idx_juan = next(i for i, x in enumerate(g_propn) if "J-U-A-N" in x or x == "JUAN")
    idx_carlos = next(i for i, x in enumerate(g_propn) if "C-A-R-L-O-S" in x or x == "CARLOS")
    assert idx_carlos == idx_juan + 1
    assert g_propn[-2:] == ["PAN", "COMPRAR"]


