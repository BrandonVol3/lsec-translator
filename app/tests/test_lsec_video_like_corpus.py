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
    def test_videos_4_to_10_preserve_unicode_glosses(self, svc):
        out = _run(
            svc,
            "La evaluación de admisión en la mañana incluye música, diseño y tecnología.",
        )
        glosses = _glosses(out)
        assert "EVALUACIÓN" in glosses
        assert "ADMISIÓN" in glosses
        assert any("MAÑANA" in value for value in glosses)
        assert "MÚSICA" in glosses
        assert "DISEÑO" in glosses
        assert "TECNOLOGÍA" in glosses
        assert not any(
            value in glosses
            for value in ("EVALUACIN", "ADMISIN", "MAANA", "MSICA", "DISEO", "TECNOLOGA")
        )

    def test_video_7_written_4500_and_3000_are_positional(self, svc):
        out = _run(
            svc,
            "Invitamos a los cuatro mil quinientos graduados y a los tres mil aspirantes.",
        )
        glosses = _glosses(out)
        assert glosses.count("CUATRO") == 1
        assert glosses.count("MIL") == 2
        assert glosses[glosses.index("CUATRO"):glosses.index("CUATRO") + 4] == [
            "CUATRO", "MIL", "CINCO", "CIENTOS"
        ]
        assert "TRES-MIL" not in glosses
        assert "TRES" in glosses

    def test_videos_4_to_10_do_not_inject_direction_or_now(self, svc):
        out = _run(
            svc,
            "Hoy los aspirantes revisan la oferta en los campos de Tulcán y Cayambe.",
        )
        glosses = _glosses(out)
        assert "HACIA" not in glosses
        assert "HOY" in glosses
        assert "AHORA" not in glosses

    def test_video_8_keeps_ecuadorian_courtesy_and_weather_content(self, svc):
        out = _run(
            svc,
            "Aunque hace frío y calor, mi ñaño y mi pana revisan el formulario de inscripción.",
        )
        glosses = _glosses(out)
        assert "AUNQUE" in glosses
        assert "FRÍO" in glosses
        assert "CALOR" in glosses
        assert "HERMANO" in glosses
        assert "AMIGO" in glosses
        assert "FORMULARIO" in glosses
        assert "INSCRIPCIÓN" in glosses
        assert "SOURCE_CONTENT_DROPPED" not in _codes(out)

    def test_video_9_preserves_condition_and_negation(self, svc):
        out = _run(
            svc,
            "Si mañana no llueve, realizaremos la jornada de integración.",
        )
        glosses = _glosses(out)
        assert "SI" in glosses
        assert "MAÑANA" in glosses
        assert "NO" in glosses
        assert "LLUVIA" in glosses or "LLOVER" in glosses
        assert "INTEGRACIÓN" in glosses

    def test_video_10_preserves_modalities(self, svc):
        out = _run(
            svc,
            "Los programas presenciales y semipresenciales promueven el desarrollo sostenible.",
        )
        glosses = _glosses(out)
        assert "PRESENCIAL" in glosses
        assert "SEMIPRESENCIAL" in glosses
        assert "DESARROLLO" in glosses
        assert "SOSTENIBLE" in glosses or "SOSTENIBILIDAD" in glosses

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

    def test_video_1_4500_is_positional(self, svc):
        out = _run(svc, "Más de 4.500 graduados ya lo hicieron.")
        glosses = _glosses(out)
        assert all(g in glosses for g in ("CUATRO", "MIL", "CINCO", "CIENTOS"))
        assert "4500" not in glosses
        assert "VARIOS" not in glosses

    def test_video_1_comparative_is_not_plural_negation(self, svc):
        out = _run(svc, "Formamos más que profesionales.")
        glosses = _glosses(out)
        assert "PROFESIONAL" in glosses
        assert "MÁS-DE" in glosses
        assert "VARIOS" not in glosses
        assert "SOLAMENTE-NO" not in glosses

    def test_video_3_approximation_and_progressive_are_not_directional(self, svc):
        out = _run(
            svc,
            "Al momento la UPEC registra alrededor de 3.000 aspirantes "
            "que están opcionando para un cupo.",
        )
        glosses = _glosses(out)
        assert "ALREDEDOR" in glosses
        assert "HACIA" not in glosses
        assert "AHORA" not in glosses

    def test_video_3_time_expression_keeps_numeric_order(self, svc):
        out = _run(svc, "A partir de las 8 y cuarto.")
        glosses = _glosses(out)
        hour = "8" if "8" in glosses else "OCHO"
        assert hour in glosses
        assert glosses.index(hour) < glosses.index("QUINCE")

    @pytest.mark.parametrize(
        ("text", "expected"),
        (
            (
                "Más de 3.200 estudiantes participan en cursos académicos.",
                ("TRES", "MIL", "DOSCIENTOS"),
            ),
            (
                "La UPEC registra alrededor de 2.800 aspirantes.",
                ("DOS", "MIL", "OCHOCIENTOS"),
            ),
        ),
    )
    def test_positional_numeric_composition_is_reusable(self, svc, text, expected):
        glosses = _glosses(_run(svc, text))
        assert all(item in glosses for item in expected)

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


VIDEO_TEXTS_11_20 = {
    "11": (
        "En el año 2026 la beca estudiantil cubre el cien por ciento de la matrícula "
        "para quinientos veinte estudiantes y el ochenta y cinco por ciento para "
        "ciento cincuenta becarios nuevos. El primer grupo entregará los requisitos "
        "el 15 de mayo desde las 14:15 hasta las 16:30, mientras que el segundo, "
        "tercer y quinto grupo asistirán el 22 de mayo. Para aprobar necesitas un "
        "promedio mínimo de nueve punto cinco sobre diez."
    ),
    "12": (
        "En la secretaría de la facultad se revisaron las carpetas y se entregaron "
        "los certificados a quienes se inscribieron a tiempo. Si el comprobante está "
        "listo, pídeselo al coordinador o dímelo hoy para enviártelo por correo "
        "electrónico. En la UPEC nos apoyamos mutuamente, nos comunicamos con respeto "
        "y nos preparamos para graduarnos juntos."
    ),
    "13": (
        "Los aspirantes que han completado el registro tienen que presentar el "
        "formulario firmado y la cédula actualizada. Mañana vamos a construir nuevos "
        "espacios de investigación porque debemos seguir fortaleciendo el proyecto "
        "aprobado por el consejo universitario. Si vuelves a intentar la prueba, "
        "podrás alcanzar el puntaje requerido sin dificultad."
    ),
    "14": (
        "Antes nosotros no sabíamos cómo usar la plataforma, no podíamos subir las "
        "tareas y no nos gustaba estudiar en línea. Sin embargo, hoy nadie se queda "
        "atrás: no tenemos ningún problema ni ninguna duda porque el sistema nunca "
        "falla. Si mañana no hay internet en tu casa y no quieres perder la clase, "
        "tampoco te preocupes, porque ningún docente te pondrá falta."
    ),
    "15": (
        "Yo estudio en la biblioteca porque el estudio constante mejora mi "
        "rendimiento, y luego trabajo en el laboratorio donde presento mi trabajo "
        "final. Cuando el profesor pregunta sobre la práctica profesional, cada "
        "estudiante presente muestra su informe y practica la exposición frente a la "
        "muestra científica. Solicita ayuda en bienestar estudiantil si necesitas que "
        "alguien te ayude hoy."
    ),
    "16": (
        "Estudiamos desde temprano con entusiasmo para transformar nuestra provincia "
        "y trabajamos por el bienestar de la comunidad sin descanso. Durante el "
        "semestre debatimos sobre inteligencia artificial entre compañeros según el "
        "cronograma académico. Hasta el viernes puedes postular para la beca de "
        "movilidad hacia universidades extranjeras."
    ),
    "17": (
        "¿Con quién debemos hablar para legalizar la matrícula y en dónde queda la "
        "oficina de admisión? ¿Desde cuándo están abiertas las inscripciones para "
        "nivelación y hasta qué hora atienden hoy? ¿Cuál de las carreras de la UPEC "
        "prefieres estudiar, cómo piensas financiar tus estudios y por qué elegiste "
        "esta universidad?"
    ),
    "18": (
        "Eh... o sea, en la en la universidad nos pidieron llegar tempranito, así que "
        "ven ahorita mismo rapidito. ¡Atatai, qué sucio está ese piso por la lluvia!, "
        "y ¡ayayay, me duele la cabeza!, pero de ley mi ñaño y mi guagua entran hoy a "
        "clases. Por favor, dame viendo si ya abrieron el aula y deme avisando al "
        "WhatsApp tres cero cinco veinte dieciocho o al correo bienestar arroba upec "
        "punto edu punto ec."
    ),
    "19": (
        "El rector se reunió ayer con la directora de carrera en el edificio central; "
        "él le solicitó a ella el informe de evaluación y ella se lo entregó antes del "
        "mediodía. Después, ambos conversaron con los docentes y les explicaron que "
        "este semestre recibirán equipamiento nuevo en sus laboratorios."
    ),
    "20": (
        "La educación intercultural bilingüe y la investigación lingüística tienen "
        "gran antigüedad y prestigio en nuestra frontera norte. En coordinación con "
        "la SENESCYT, el CES y el CONADIS, la UPEC ofrece carreras como Ingeniería en "
        "Computación, Comercio Exterior, Administración de Empresas, Enfermería, "
        "Turismo, Agropecuaria y Educación Inicial. ¡Inscríbete hoy: \"Tu esfuerzo "
        "construye el mañana\"!"
    ),
}


class TestVideos11To20Regressions:
    @pytest.mark.parametrize("video", sorted(VIDEO_TEXTS_11_20))
    def test_no_source_content_dropped(self, svc, video):
        out = _run(svc, VIDEO_TEXTS_11_20[video])
        dropped = [
            warning.message
            for warning in out.warnings
            if warning.code == "SOURCE_CONTENT_DROPPED"
        ]
        assert not dropped, (video, dropped)

    def test_video_11_numbers_dates_and_percentages(self, svc):
        out = _run(svc, VIDEO_TEXTS_11_20["11"])
        glosses = _glosses(out)
        assert "2026" not in glosses
        assert "520" not in glosses and "150" not in glosses
        assert self._is_contiguous(glosses, ["DOS", "MIL", "VEINTE", "SEIS"])
        assert self._is_contiguous(glosses, ["CINCO", "CIENTOS", "VEINTE"])
        assert self._is_contiguous(glosses, ["CIEN", "PORCENTAJE"])
        assert self._is_contiguous(glosses, ["OCHENTA", "CINCO", "PORCENTAJE"])
        assert self._is_contiguous(glosses, ["CIEN", "CINCUENTA"])
        assert self._is_contiguous(glosses, ["HORA", "CATORCE", "QUINCE"])
        assert self._is_contiguous(glosses, ["DIECISÉIS", "TREINTA"])
        assert "PIDER" not in glosses

    def test_video_12_clitics_are_lemmatized(self, svc):
        out = _run(svc, VIDEO_TEXTS_11_20["12"])
        glosses = _glosses(out)
        assert "PEDIR" in glosses
        assert "GRADUAR" in glosses
        assert "GRADUARNO" not in glosses
        assert "GRADUARNOS" not in glosses
        assert "CORREO-ELECTRÓNICO" in glosses
        assert not any(
            left == "POR" and right == "CORREO-ELECTRÓNICO"
            for left, right in zip(glosses, glosses[1:])
        )

    def test_video_15_homographs_and_relative_donde(self, svc):
        out = _run(svc, VIDEO_TEXTS_11_20["15"])
        glosses = _glosses(out)
        assert "CADA" in glosses
        assert "PRESENTE" in glosses
        assert "MUESTRA" in glosses
        assert "MOSTRAR" in glosses
        assert "LUGAR" in glosses
        assert "DÓNDE" not in glosses
        assert "SOURCE_CONTENT_DROPPED" not in _codes(out)

    def test_video_17_preferir_and_question_shape(self, svc):
        out = _run(svc, VIDEO_TEXTS_11_20["17"])
        glosses = _glosses(out)
        assert "PREFERIR" in glosses
        assert "PREFIER" not in glosses
        assert "POR" not in glosses or "POR-QUÉ" not in glosses
        assert not any(
            left == "POR" and right == "POR-QUÉ"
            for left, right in zip(glosses, glosses[1:])
        )
        question_props = [
            prop for prop in out.semantic_propositions
            if prop.modality in ("interrogative_wh", "interrogative_yn")
        ]
        assert question_props
        first_question_glosses = [
            gloss.gloss
            for gloss in out.glosses
            if gloss.proposition_id == question_props[0].id
        ]
        assert "PROPÓSITO" not in first_question_glosses

    def test_video_18_ecuadorianisms_and_courtesy(self, svc):
        out = _run(svc, VIDEO_TEXTS_11_20["18"])
        glosses = _glosses(out)
        assert "VENIR" in glosses
        assert "ASCO" in glosses
        assert "DOLOR" in glosses
        assert "SEGURO" in glosses
        assert "TEMPRANO" in glosses
        assert "AHORA" in glosses
        assert "RÁPIDO" in glosses
        assert "AYAYAY" not in glosses
        assert not any(value.startswith("A-T-A-T-A-I") for value in glosses)
        assert not any(value.startswith("DAR[") for value in glosses)
        assert "POR-FAVOR" in glosses
        assert "VER" in glosses or "REVISAR" in glosses
        assert "AVISAR" in glosses or "REVISAR" in glosses

    def test_video_19_coreference_has_no_spurious_loci(self, svc):
        out = _run(svc, VIDEO_TEXTS_11_20["19"])
        glosses = _glosses(out)
        assert "PRO3" in glosses
        assert not any("[" in value and "->" in value for value in glosses)
        assert "SOURCE_CONTENT_DROPPED" not in _codes(out)

    def test_video_20_careers_are_signs_not_fingerspelling(self, svc):
        out = _run(svc, VIDEO_TEXTS_11_20["20"])
        glosses = _glosses(out)
        for term in (
            "INGENIERÍA",
            "COMPUTACIÓN",
            "COMERCIO",
            "EXTERIOR",
            "ENFERMERÍA",
            "AGROPECUARIA",
            "INICIAL",
        ):
            assert term in glosses, term
        career_items = [
            item
            for item in out.glosses
            if (item.source_word or "").lower()
            in {"ingeniería", "computación", "comercio", "exterior", "enfermería", "agropecuaria", "inicial"}
        ]
        assert career_items
        assert all(item.gloss_type != GlossType.FINGERSPELLING for item in career_items)
        assert "COMERCIAR" not in glosses

    @staticmethod
    def _is_contiguous(glosses, sequence):
        size = len(sequence)
        return any(
            glosses[index:index + size] == sequence
            for index in range(len(glosses) - size + 1)
        )

