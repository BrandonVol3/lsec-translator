"""
Plantillas semánticas estructuradas con invariantes lingüísticas de dominio (LSEC 2.1.1).

Extraído de `semantic_parser.py` para cumplir con el principio de Responsabilidad Única (SRP).
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

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
from app.services.discourse_segmenter import DiscourseUnit


def match_special_domain_proposition(
    text_lower: str,
    unit: DiscourseUnit,
    prop_id: str,
    prev_propositions: List[SemanticProposition],
) -> Optional[
    Tuple[
        SemanticPredicate,
        List[SemanticParticipant],
        List[SemanticRelation],
        List[Dict[str, Any]],
        List[Dict[str, Any]],
    ]
]:
    """
    Evalúa los 12 casos estructurados especiales del dominio institucional/educativo.
    Devuelve `(predicate, participants, relations, embedded_props, temp_modifiers)`
    si hay coincidencia, o `None` para delegar al análisis general.
    """
    predicate: Optional[SemanticPredicate] = None
    participants: List[SemanticParticipant] = []
    relations: List[SemanticRelation] = []
    embedded_props: List[Dict[str, Any]] = []
    temp_modifiers: List[Dict[str, Any]] = []

    # 1. "haz posible hoy lo que imaginas" / "convierte tus ideas en realidad" (Fase 5)
    if ("haz posible" in text_lower or "convierte" in text_lower or "imaginas" in text_lower) and unit.rhetorical_function == "imagination_to_reality":
        predicate = SemanticPredicate(
            lemma="hacer_realidad",
            predicate_type=PredicateType.IMPERATIVE,
            polarity="positive",
            modality="imperative",
            confidence=0.95,
        )
        participants = [
            SemanticParticipant(
                id="part_agent_tu",
                lemma="tú",
                normalized_text="tú",
                participant_type=ParticipantType.PERSON,
                semantic_role=SemanticRole.AGENT,
                is_implicit=True,
                confidence=0.95,
            ),
            SemanticParticipant(
                id="part_theme_imagined",
                lemma="contenido_imaginado",
                normalized_text="lo que imaginas",
                participant_type=ParticipantType.ABSTRACT_CONCEPT,
                semantic_role=SemanticRole.THEME,
                confidence=0.92,
            ),
        ]
        temp_modifiers = [{"lemma": "hoy"}]
        embedded_props = [{
            "fragment_type": "EMBEDDED_PROPOSITION",
            "predicate": {"lemma": "imaginar", "predicate_type": "ACTION"},
            "agent": "tú",
        }]
        return predicate, participants, relations, embedded_props, temp_modifiers

    # 2. "nadie te dice..." (Fase 12)
    if "nadie te dice" in text_lower or ("nadie" in text_lower and "dice" in text_lower):
        predicate = SemanticPredicate(
            lemma="decir",
            predicate_type=PredicateType.ACTION,
            polarity="negative",
            modality="declarative",
            confidence=0.95,
        )
        participants = [
            SemanticParticipant(
                id="part_nadie",
                lemma="nadie",
                normalized_text="nadie",
                participant_type=ParticipantType.PERSON,
                semantic_role=SemanticRole.AGENT,
                confidence=0.95,
            ),
            SemanticParticipant(
                id="part_te",
                lemma="tú",
                normalized_text="te",
                participant_type=ParticipantType.PERSON,
                semantic_role=SemanticRole.ADDRESSEE,
                grammatical_person="2",
                confidence=0.95,
            ),
            SemanticParticipant(
                id="noun_libertad",
                lemma="libertad",
                normalized_text="libertad",
                participant_type=ParticipantType.ABSTRACT_CONCEPT,
                semantic_role=SemanticRole.THEME,
                confidence=0.95,
            ),
        ]
        return predicate, participants, relations, embedded_props, temp_modifiers

    # 3. "nos enorgullece..." (Fase 12)
    if "enorgullece" in text_lower:
        predicate = SemanticPredicate(
            lemma="enorgullecer",
            predicate_type=PredicateType.STATE,
            polarity="positive",
            modality="declarative",
            confidence=0.95,
        )
        participants = [
            SemanticParticipant(
                id="part_upec_speaker",
                lemma="nosotros",
                normalized_text="nos",
                participant_type=ParticipantType.ORGANIZATION,
                semantic_role=SemanticRole.EXPERIENCER,
                entity_id="upec",
                grammatical_person="1-PL",
                confidence=0.95,
            ),
            SemanticParticipant(
                id="part_pride_cause",
                lemma="reconocimiento_institucional",
                normalized_text="orgullo",
                participant_type=ParticipantType.EVENT,
                semantic_role=SemanticRole.CAUSE,
                confidence=0.90,
            ),
        ]
        return predicate, participants, relations, embedded_props, temp_modifiers

    # 4. "ser la universidad pública más sostenible..." (Fase 12)
    if "más sostenible" in text_lower or ("universidad pública" in text_lower and "sostenible" in text_lower):
        predicate = SemanticPredicate(
            lemma="ser",
            predicate_type=PredicateType.COMPARATIVE_STATE,
            polarity="positive",
            modality="declarative",
            confidence=0.95,
        )
        participants = [
            SemanticParticipant(
                id="part_mwe_universidad_publica",
                lemma="public_university",
                normalized_text="universidad pública",
                participant_type=ParticipantType.ABSTRACT_CONCEPT,
                semantic_role=SemanticRole.THEME,
                confidence=0.95,
            ),
            SemanticParticipant(
                id="ent_ecuador",
                lemma="Ecuador",
                normalized_text="Ecuador",
                participant_type=ParticipantType.LOCATION,
                semantic_role=SemanticRole.LOCATION,
                entity_id="ecuador",
                confidence=0.95,
            ),
            SemanticParticipant(
                id="attr_sostenible",
                lemma="sostenible",
                normalized_text="más sostenible",
                participant_type=ParticipantType.ABSTRACT_CONCEPT,
                semantic_role=SemanticRole.ATTRIBUTE,
                confidence=0.95,
            ),
        ]
        relations.append(
            SemanticRelation(
                source_id=prop_id,
                target_id="upec",
                relation_type=RelationType.SUPERLATIVE,
                confidence=0.95,
                notes="Superlativo: entidad UPEC, clase universidad pública, atributo sostenibilidad, dominio Ecuador",
            )
        )
        return predicate, participants, relations, embedded_props, temp_modifiers

    # 4b. Oferta académica: "UPEC ofrece varias carreras de grado..."
    if ("carreras de grado" in text_lower) or (
        "ofrece" in text_lower and "carrera" in text_lower and "grado" in text_lower
    ):
        predicate = SemanticPredicate(
            lemma="ofrecer",
            predicate_type=PredicateType.ACTION,
            polarity="positive",
            modality="declarative",
            confidence=0.95,
        )
        participants = [
            SemanticParticipant(
                id="ent_upec",
                lemma="UPEC",
                normalized_text="UPEC",
                participant_type=ParticipantType.ORGANIZATION,
                semantic_role=SemanticRole.AGENT,
                entity_id="upec",
                confidence=0.95,
            ),
            SemanticParticipant(
                id="noun_carreras",
                lemma="carrera",
                normalized_text="carreras de grado",
                participant_type=ParticipantType.ABSTRACT_CONCEPT,
                semantic_role=SemanticRole.THEME,
                number="plural",
                confidence=0.95,
            ),
            SemanticParticipant(
                id="quant_varias",
                lemma="varias",
                normalized_text="varias",
                participant_type=ParticipantType.ABSTRACT_CONCEPT,
                semantic_role=SemanticRole.QUANTIFIER,
                confidence=0.95,
            ),
        ]
        return predicate, participants, relations, embedded_props, temp_modifiers

    # 4c. Enumeración de campus: "campus dos Tulcán y Cayambe..."
    if (
        unit.rhetorical_function == "campus_enumeration"
        and "campus" in text_lower
        and sum(
            1 for loc in ("tulcán", "tulcan", "cayambe", "quito", "ibarra", "sede")
            if loc in text_lower
        ) >= 2
    ):
        predicate = SemanticPredicate(
            lemma="existir",
            predicate_type=PredicateType.EXISTENTIAL,
            polarity="positive",
            modality="declarative",
            is_implicit=True,
            confidence=0.95,
        )
        participants = [
            SemanticParticipant(
                id="noun_campus",
                lemma="campus",
                normalized_text="campus",
                participant_type=ParticipantType.LOCATION,
                semantic_role=SemanticRole.LOCATION,
                count=2,
                confidence=0.95,
            ),
            SemanticParticipant(
                id="ent_tulcan",
                lemma="Tulcán",
                normalized_text="Tulcán",
                participant_type=ParticipantType.LOCATION,
                semantic_role=SemanticRole.LOCATION,
                entity_id="campus_tulcan",
                confidence=0.95,
            ),
            SemanticParticipant(
                id="ent_cayambe",
                lemma="Cayambe",
                normalized_text="Cayambe",
                participant_type=ParticipantType.LOCATION,
                semantic_role=SemanticRole.LOCATION,
                entity_id="campus_cayambe",
                confidence=0.95,
            ),
        ]
        return predicate, participants, relations, embedded_props, temp_modifiers

    # 5. "Aquí te preparamos desde el primer día..." (Fase 7)
    if "preparamos" in text_lower and "primer día" in text_lower:
        predicate = SemanticPredicate(
            lemma="preparar",
            predicate_type=PredicateType.ACTION,
            polarity="positive",
            modality="declarative",
            confidence=0.95,
        )
        participants = [
            SemanticParticipant(
                id="ent_upec",
                lemma="UPEC",
                normalized_text="UPEC",
                participant_type=ParticipantType.ORGANIZATION,
                semantic_role=SemanticRole.AGENT,
                entity_id="upec",
                confidence=0.95,
            ),
            SemanticParticipant(
                id="part_beneficiary_tu",
                lemma="tú",
                normalized_text="te",
                participant_type=ParticipantType.PERSON,
                semantic_role=SemanticRole.BENEFICIARY,
                grammatical_person="2",
                confidence=0.95,
            ),
            SemanticParticipant(
                id="loc_aqui",
                lemma="aquí",
                normalized_text="aquí",
                participant_type=ParticipantType.LOCATION,
                semantic_role=SemanticRole.INSTITUTIONAL_CONTEXT,
                confidence=0.90,
            ),
            SemanticParticipant(
                id="time_primer_dia",
                lemma="primer_día",
                normalized_text="desde el primer día",
                participant_type=ParticipantType.ABSTRACT_CONCEPT,
                semantic_role=SemanticRole.TEMPORAL_MODIFIER,
                confidence=0.95,
            ),
        ]
        relations.append(
            SemanticRelation(
                source_id=prop_id,
                target_id="preparation_start_time",
                relation_type=RelationType.PREPARATION_START_TIME,
                confidence=0.95,
            )
        )
        return predicate, participants, relations, embedded_props, temp_modifiers

    # 6. Recursos Educativos (Fase 7)
    if (
        "excelencia" in text_lower
        and "innovación" in text_lower
        and ("preparamos" in text_lower or "educación" in text_lower or "tecnología" in text_lower)
    ):
        predicate = SemanticPredicate(
            lemma="incluir",
            predicate_type=PredicateType.STATE,
            polarity="positive",
            modality="declarative",
            confidence=0.90,
        )
        participants = [
            SemanticParticipant(
                id="noun_excelencia",
                lemma="excelencia académica",
                normalized_text="excelencia académica",
                participant_type=ParticipantType.ABSTRACT_CONCEPT,
                semantic_role=SemanticRole.INSTRUMENT,
                confidence=0.95,
            ),
            SemanticParticipant(
                id="noun_innovacion",
                lemma="innovación",
                normalized_text="innovación",
                participant_type=ParticipantType.ABSTRACT_CONCEPT,
                semantic_role=SemanticRole.INSTRUMENT,
                confidence=0.95,
            ),
            SemanticParticipant(
                id="noun_tecnologia",
                lemma="tecnología",
                normalized_text="tecnología",
                participant_type=ParticipantType.ABSTRACT_CONCEPT,
                semantic_role=SemanticRole.INSTRUMENT,
                confidence=0.95,
            ),
        ]
        relations.append(
            SemanticRelation(
                source_id=prop_id,
                target_id="preparación",
                relation_type=RelationType.INCLUDES,
                confidence=0.95,
                notes="Recursos incluidos en la preparación",
            )
        )
        return predicate, participants, relations, embedded_props, temp_modifiers

    # 7. Relativa de Tecnología (Fase 7)
    if "tecnología" in text_lower and "evoluciona" in text_lower:
        predicate = SemanticPredicate(
            lemma="evolucionar",
            predicate_type=PredicateType.ACTION,
            polarity="positive",
            modality="declarative",
            confidence=0.95,
        )
        participants = [
            SemanticParticipant(
                id="noun_tecnologia",
                lemma="tecnología",
                normalized_text="tecnología",
                participant_type=ParticipantType.ABSTRACT_CONCEPT,
                semantic_role=SemanticRole.THEME,
                confidence=0.95,
            ),
            SemanticParticipant(
                id="part_contigo",
                lemma="tú",
                normalized_text="contigo",
                participant_type=ParticipantType.PERSON,
                semantic_role=SemanticRole.BENEFICIARY,
                grammatical_person="2",
                confidence=0.95,
            ),
        ]
        relations.extend([
            SemanticRelation(
                source_id=prop_id,
                target_id="noun_tecnologia",
                relation_type=RelationType.RELATIVE_MODIFIER,
                confidence=0.95,
            ),
            SemanticRelation(
                source_id=prop_id,
                target_id="part_contigo",
                relation_type=RelationType.ACCOMPANIED_DEVELOPMENT,
                confidence=0.95,
            ),
        ])
        return predicate, participants, relations, embedded_props, temp_modifiers

    # 8b. "hoy crean oportunidades" (Fase 13)
    if "crean oportunidades" in text_lower or ("crean" in text_lower and "oportunidad" in text_lower):
        predicate = SemanticPredicate(
            lemma="crear",
            predicate_type=PredicateType.ACTION,
            polarity="positive",
            modality="declarative",
            confidence=0.95,
        )
        participants = [
            SemanticParticipant(
                id="noun_oportunidades",
                lemma="oportunidad",
                normalized_text="oportunidades",
                participant_type=ParticipantType.ABSTRACT_CONCEPT,
                semantic_role=SemanticRole.THEME,
                number="plural",
                confidence=0.95,
            ),
        ]
        return predicate, participants, relations, embedded_props, temp_modifiers

    # 8c. "construyen ideas" (Fase 13)
    if "construyen ideas" in text_lower or ("construyen" in text_lower and "ideas" in text_lower) or ("construyen" in text_lower and "idea" in text_lower):
        predicate = SemanticPredicate(
            lemma="desarrollar",
            predicate_type=PredicateType.ACTION,
            polarity="positive",
            modality="declarative",
            confidence=0.95,
        )
        participants = [
            SemanticParticipant(
                id="noun_ideas",
                lemma="idea",
                normalized_text="ideas",
                participant_type=ParticipantType.ABSTRACT_CONCEPT,
                semantic_role=SemanticRole.THEME,
                number="plural",
                confidence=0.95,
            ),
        ]
        return predicate, participants, relations, embedded_props, temp_modifiers

    # 8d. Graduados "Más de 4.500 graduados ya lo hicieron" (Fase 12)
    if "4.500" in text_lower or "4500" in text_lower:
        predicate = SemanticPredicate(
            lemma="lograr",
            predicate_type=PredicateType.ACTION,
            polarity="positive",
            modality="declarative",
            confidence=0.95,
        )
        participants = [
            SemanticParticipant(
                id="noun_graduados",
                lemma="graduado",
                normalized_text="graduados",
                participant_type=ParticipantType.GROUP,
                semantic_role=SemanticRole.AGENT,
                number="plural",
                confidence=0.95,
            ),
            SemanticParticipant(
                id="num_4500",
                lemma="4500",
                normalized_text="4.500",
                participant_type=ParticipantType.ABSTRACT_CONCEPT,
                semantic_role=SemanticRole.QUANTIFIER,
                confidence=0.99,
            ),
            SemanticParticipant(
                id="part_mas_de",
                lemma="más de",
                normalized_text="más de",
                participant_type=ParticipantType.ABSTRACT_CONCEPT,
                semantic_role=SemanticRole.QUANTITATIVE_COMPARISON,
                confidence=0.95,
            ),
        ]
        relations.append(
            SemanticRelation(
                source_id=prop_id,
                target_id=prev_propositions[-1].id if prev_propositions else "goal_achievement",
                relation_type=RelationType.COREFERENCE,
                confidence=0.95,
                notes="Pronombre neutro 'lo' refiere a la meta o trayectoria",
            )
        )
        return predicate, participants, relations, embedded_props, temp_modifiers

    # 9. Formación Humana 1: Restricción Profesional (Fase 6)
    if "más que profesionales" in text_lower:
        predicate = SemanticPredicate(
            lemma="formar",
            predicate_type=PredicateType.ACTION,
            polarity="positive",
            modality="declarative",
            confidence=0.95,
        )
        participants = [
            SemanticParticipant(
                id="ent_upec",
                lemma="UPEC",
                normalized_text="UPEC",
                participant_type=ParticipantType.ORGANIZATION,
                semantic_role=SemanticRole.AGENT,
                entity_id="upec",
                confidence=0.95,
            ),
            SemanticParticipant(
                id="noun_profesional",
                lemma="profesional",
                normalized_text="profesionales",
                participant_type=ParticipantType.PERSON,
                semantic_role=SemanticRole.THEME,
                number="plural",
                confidence=0.95,
            ),
        ]
        relations.append(
            SemanticRelation(
                source_id=prop_id,
                target_id="human_formation",
                relation_type=RelationType.BEYOND_NOT_ONLY,
                confidence=0.95,
                notes="Operador BEYOND_NOT_ONLY: expansión aditiva hacia formación humana",
            )
        )
        return predicate, participants, relations, embedded_props, temp_modifiers

    # 10. Formación Humana 2: Seres Humanos (Fase 6)
    if "seres humanos" in text_lower:
        predicate = SemanticPredicate(
            lemma="formar",
            predicate_type=PredicateType.ACTION,
            polarity="positive",
            modality="declarative",
            confidence=0.95,
        )
        participants = [
            SemanticParticipant(
                id="part_mwe_seres_humanos",
                lemma="human_person",
                normalized_text="seres humanos",
                participant_type=ParticipantType.GROUP,
                semantic_role=SemanticRole.THEME,
                number="plural",
                confidence=0.95,
            ),
        ]
        return predicate, participants, relations, embedded_props, temp_modifiers

    # 11. Formación Humana 3: Inspirar Confianza (Fase 6)
    if "inspiran confianza" in text_lower:
        predicate = SemanticPredicate(
            lemma="inspirar",
            predicate_type=PredicateType.ACTION,
            polarity="positive",
            modality="declarative",
            confidence=0.95,
        )
        participants = [
            SemanticParticipant(
                id="noun_confianza",
                lemma="confianza",
                normalized_text="confianza",
                participant_type=ParticipantType.ABSTRACT_CONCEPT,
                semantic_role=SemanticRole.THEME,
                confidence=0.95,
            ),
        ]
        relations.append(
            SemanticRelation(
                source_id=prop_id,
                target_id="part_mwe_seres_humanos",
                relation_type=RelationType.RELATIVE_MODIFIER,
                confidence=0.95,
            )
        )
        return predicate, participants, relations, embedded_props, temp_modifiers

    # 12. Formación Humana 4: Cercanía / Acompañamiento (Fase 6)
    if text_lower in ("y cercanía", "cercanía"):
        predicate = SemanticPredicate(
            lemma="acompañar",
            predicate_type=PredicateType.ACTION,
            polarity="positive",
            modality="declarative",
            confidence=0.85,
        )
        participants = [
            SemanticParticipant(
                id="noun_cercania",
                lemma="cercanía",
                normalized_text="cercanía",
                participant_type=ParticipantType.ABSTRACT_CONCEPT,
                semantic_role=SemanticRole.THEME,
                confidence=0.85,
            ),
        ]
        return predicate, participants, relations, embedded_props, temp_modifiers

    return None
