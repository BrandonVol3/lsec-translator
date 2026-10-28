"""Suite de regresión completa para la auditoría LSEC (F-01 a F-24) y batería QA de 42 oraciones."""
import asyncio
import pytest

from app.core.schemas import GlossType
from app.services.nlp_service import LSECTranslatorService


QA_BATTERY_42 = [
    ("N1-01", "Hola, buenos días"),
    ("N1-02", "El niño come una manzana en la escuela"),
    ("N1-03", "La profesora es muy amable y está feliz"),
    ("N1-04", "Nosotros caminamos por el parque y unos perros corren"),
    ("N1-05", "Te invitamos al evento cultural de la universidad"),
    ("N1-06", "Ellos escriben cartas y viven en Quito"),
    ("N1-07", "Los estudiantes leyeron los libros nuevos"),
    ("N2-01", "Eh... este... o sea, yo yo quiero aprender lengua de señas, ¿sí?"),
    ("N2-02", "Nosotros queremos ir, nosotros queremos aprender más más rápido y muy muy bien"),
    ("N2-03", "Dame pasando el cuaderno y deme haciendo el favor"),
    ("N2-04", "Ñaño, el guagua tiene frío, achachay, y el pana se quemó, arrarray"),
    ("N2-05", "En Tulkán y Callambe visitamos el campos universitario"),
    ("N2-06", "La UPEC organiza un congreso con el CONADIS en Ecuador"),
    ("N2-07", "Mi número de teléfono es 0991234567 y tengo 25 años"),
    ("N2-08", "Mandarás el informe mañana, darás avisando al director"),
    ("N3-01", "Todos los seres humanos tienen derechos fundamentales"),
    ("N3-02", "Por favor, muchas gracias y buenas tardes a todos"),
    ("N3-03", "Ayer estudié bastante, pero hoy todavía tengo dudas; sin embargo, aprobaré el examen"),
    ("N3-04", "No solo los estudiantes participan, sino también los docentes colaboran"),
    ("N3-05", "Me pregunto cuándo llegará el intérprete y dónde será la reunión"),
    ("N3-06", "Antes trabajaba en Guayaquil y mañana viajaré a Cuenca"),
    ("N3-07", "A pesar de la lluvia, llevaremos a cabo la asamblea estudiantil"),
    ("N4-01", "Trabajo en el hospital y ayudas a los pacientes mientras estudiamos medicina"),
    ("N4-02", "Ayer llovió fuerte en la sierra y hay neblina en la carretera"),
    ("N4-03", "El dibujo técnico, el taller de cerámica, el arte moderno y la música clásica inspiran paz"),
    ("N4-04", "Caminamos desde la plaza con mi familia hacia el museo para aprender historia"),
    ("N4-05", "Mañana el médico ya habrá revisado a varios pacientes ahora"),
    ("N4-06", "Mi casa grande está cerca de tu colegio nuevo"),
    ("N4-07", "Los tres niños leen libros interesantes en la biblioteca"),
    ("N5-01", "Ayúdame con este trámite urgente, por favor"),
    ("N5-02", "Yo no sé la respuesta, no puedo asistir y no quiero mentir"),
    ("N5-03", "No me gusta el ruido y no hay suficiente tiempo"),
    ("N5-04", "El estudiante no entregó la tarea ayer"),
    ("N5-05", "Yo te aviso mañana y tú me enseñas el camino"),
    ("N5-06", "En invierno llueve mucho y el río crece muchísimo"),
    ("N5-07", "¿Vas a venir mañana a la clase o qué necesitas comprar?"),
    ("N6-01", "La familia ecuatoriana celebra con alegría en la escuela"),
    ("N6-02", "El algoritmo de criptografía cuántica optimiza el microprocesador"),
    ("N6-03", "El doctor Brando Narváez vive en Chone"),
    (
        "N6-04",
        "Primero, cuando llegues a la oficina (si el director ya está presente), entrégale el documento; después, avísame por teléfono porque necesitamos confirmar el presupuesto antes del viernes.",
    ),
    ("N6-05", "¿Dónde dejaste las llaves que te di ayer?"),
    ("N6-06", "¡Qué alegría verte de nuevo, hermano!"),
]

CORRUPTED_VERB_GLOSSES = {
    "LLEVARER",
    "DEJASTAR",
    "ENTRÉGALIR",
    "AVÍSAME",
    "AYÚDAME",
    "VERTER",
    "CAMINAMOS",
    "LLEGUES",
    "MANDARÁS",
    "DARÁS",
}


@pytest.fixture(scope="module")
def svc():
    return LSECTranslatorService()


def _run(svc, text: str):
    return asyncio.run(svc.translate_to_gloss(text))


def test_qa_battery_42_zero_blocked_and_zero_corrupted_glosses(svc):
    """Verifica que ninguna de las 42 oraciones de la batería QA emita glosas corruptas."""
    for cid, text in QA_BATTERY_42:
        out = _run(svc, text)
        gloss_list = [g.gloss for g in out.glosses]
        assert gloss_list, f"{cid} no generó glosas"
        for bad in CORRUPTED_VERB_GLOSSES:
            assert bad not in gloss_list, f"{cid} emitió glosa corrupta '{bad}' en {gloss_list}"
        for i in range(len(gloss_list) - 1):
            assert (gloss_list[i], gloss_list[i + 1]) not in (
                ("AYUDA", "VARIOS"),
                ("NECESITA", "VARIOS"),
            ), f"{cid} trató verbo 2SG como sustantivo plural en {gloss_list}"


def test_f01_zero_polarity_inversions_n5_02_and_n5_03(svc):
    """F-01 / F-21: Preservación de polaridad negativa en cláusulas coordinadas."""
    out_n502 = _run(svc, "Yo no sé la respuesta, no puedo asistir y no quiero mentir")
    g_n502 = [g.gloss for g in out_n502.glosses]
    assert "NO-SABER" in g_n502
    assert "NO-PODER" in g_n502
    assert "NO-QUERER" in g_n502
    assert "QUERER" not in g_n502

    out_n503 = _run(svc, "No me gusta el ruido y no hay suficiente tiempo")
    g_n503 = [g.gloss for g in out_n503.glosses]
    assert "NO-GUSTAR" in g_n503
    assert "NO-HABER" in g_n503
    assert "GUSTAR" not in g_n503


@pytest.mark.parametrize(
    "cid,text",
    [
        ("N2-03", "Dame pasando el cuaderno y deme haciendo el favor"),
        ("N2-07", "Mi número de teléfono es 0991234567 y tengo 25 años"),
        ("N4-03", "El dibujo técnico, el taller de cerámica, el arte moderno y la música clásica inspiran paz"),
        ("N5-06", "En invierno llueve mucho y el río crece muchísimo"),
        (
            "N6-04",
            "Primero, cuando llegues a la oficina (si el director ya está presente), entrégale el documento; después, avísame por teléfono porque necesitamos confirmar el presupuesto antes del viernes.",
        ),
    ],
)
def test_f06_zero_false_negative_polarity_from_no_substring(svc, cid, text):
    """F-06: Ninguna palabra con subcadena 'no' ('cuaderno', 'teléfono', 'moderno', 'invierno', 'oficina') activa negación."""
    out = _run(svc, text)
    for prop in out.semantic_propositions:
        assert prop.polarity == "positive", f"{cid} tuvo polaridad falsa '{prop.polarity}' en '{prop.source_text}'"
        assert not any(
            op.get("type") == "NEGATION" or op.get("operator_type") == "NEGATION" for op in prop.operators
        ), f"{cid} generó operador NEGATION espurio en '{prop.source_text}'"


def test_f02_and_f03_muletillas_y_modismos_ecuatorianos(svc):
    """F-02 / F-03 / F-04: Muletillas fáticas, reduplicaciones, tag question y futuro sintético de cortesía andina."""
    from app.core.schemas import FacialExpression

    out_n201 = _run(svc, "Eh... este... o sea, yo yo quiero aprender lengua de señas, ¿sí?")
    g_n201 = [g.gloss for g in out_n201.glosses]
    assert g_n201 == ["PRO1", "LENGUA-DE-SEÑAS", "QUERER", "APRENDER"]
    assert any(
        s.type == "question_yn" and s.expression == FacialExpression.QUESTION_YESNO
        for s in out_n201.non_manual_spans
    )
    assert all(
        c.get("original") is not None and c.get("corrected") is not None and c.get("type") is not None
        for c in out_n201.corrections_applied
    )

    out_n202 = _run(svc, "Nosotros queremos ir, nosotros queremos aprender más más rápido y muy muy bien")
    g_n202 = [g.gloss for g in out_n202.glosses]
    assert "FUTURO" not in g_n202
    assert "IR" in g_n202

    out_n208 = _run(svc, "Mandarás el informe mañana, darás avisando al director")
    g_n208 = [g.gloss for g in out_n208.glosses]
    assert "MANDAR" in g_n208
    assert "POR-FAVOR" in g_n208
    assert "AVISAR" in g_n208


def test_f08_to_f13_verb_lemmatization_and_2sg_disambiguation(svc):
    """F-08 a F-13: Lematización morfológica verbal, enclíticos y desambiguación de 2SG."""
    out_n303 = _run(svc, "Ayer estudié bastante, pero hoy todavía tengo dudas; sin embargo, aprobaré el examen")
    assert out_n303.glosses

    out_n307 = _run(svc, "A pesar de la lluvia, llevaremos a cabo la asamblea estudiantil")
    g_n307 = [g.gloss for g in out_n307.glosses]
    assert g_n307 == ["AUNQUE", "LLUVIA", "PRO1-PL", "ASAMBLEA", "ESTUDIANTIL", "REALIZAR"]

    g_n401 = [g.gloss for g in _run(svc, "Trabajo en el hospital y ayudas a los pacientes mientras estudiamos medicina").glosses]
    assert g_n401 == ["PRO1", "HOSPITAL", "TRABAJAR", "PRO2", "PACIENTE", "VARIOS", "AYUDAR", "PRO1-PL", "MIENTRAS", "MEDICINA", "ESTUDIAR"]

    g_n507 = [g.gloss for g in _run(svc, "¿Vas a venir mañana a la clase o qué necesitas comprar?").glosses]
    assert g_n507 == ["PRO2", "MAÑANA", "CLASE", "VENIR", "NECESITAR", "COMPRAR", "QUÉ"]

    g_n605 = [g.gloss for g in _run(svc, "¿Dónde dejaste las llaves que te di ayer?").glosses]
    assert g_n605 == ["PRO2", "AYER", "LLAVE", "VARIOS", "DEJAR", "DAR[1->2]", "DÓNDE"]

    g_n606 = [g.gloss for g in _run(svc, "¡Qué alegría verte de nuevo, hermano!").glosses]
    assert g_n606 == ["ALEGRÍA", "HERMANO", "OTRA-VEZ", "VER"]


def test_f14_to_f19_proper_nouns_quantifiers_and_pronouns(svc):
    """F-14 a F-19 y F-22: Dactilología OOV, cuantificadores, clíticos, cortesía y aislamiento UPEC."""
    out_n603 = _run(svc, "El doctor Brando Narváez vive en Chone")
    g_n603 = [g.gloss for g in out_n603.glosses]
    assert g_n603 == ["DOCTOR", "B-R-A-N-D-O", "N-A-R-V-Á-E-Z", "CH-O-N-E", "VIVIR"]
    propn_items = [g for g in out_n603.glosses if g.gloss in ("B-R-A-N-D-O", "N-A-R-V-Á-E-Z", "CH-O-N-E")]
    assert all(g.gloss_type == GlossType.FINGERSPELLING for g in propn_items)

    g_n105 = [g.gloss for g in _run(svc, "Te invitamos al evento cultural de la universidad").glosses]
    assert "PRO2" in g_n105
    assert "PRO1-PL" in g_n105

    g_n207 = [g.gloss for g in _run(svc, "Mi número de teléfono es 0991234567 y tengo 25 años").glosses]
    assert all(tok in g_n207 for tok in ("PRO1", "NÚMERO", "DE-TELÉFONO", "CERO", "NUEVE", "AÑO", "25", "TENER"))

    g_n301 = [g.gloss for g in _run(svc, "Todos los seres humanos tienen derechos fundamentales").glosses]
    assert g_n301 == ["PERSONA", "TODO", "DERECHO", "FUNDAMENTAL", "VARIOS", "TENER"]

    g_n302 = [g.gloss for g in _run(svc, "Por favor, muchas gracias y buenas tardes a todos").glosses]
    assert g_n302 == ["POR-FAVOR", "GRACIA", "MUCHO", "BUENAS-TARDES", "TODO"]

    g_n501 = [g.gloss for g in _run(svc, "Ayúdame con este trámite urgente, por favor").glosses]
    assert g_n501[0] == "POR-FAVOR"
    assert "AYUDAR[2->1]" in g_n501

    g_campus_gen = [g.gloss for g in _run(svc, "Caminamos por el campus universitario").glosses]
    assert "TULCÁN" not in g_campus_gen and "CAYAMBE" not in g_campus_gen
    assert "CAMINAR" in g_campus_gen

