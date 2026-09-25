"""
Tests unitarios para el motor de gramática LSEC centralizado.

Cubre:
  - Esquema de reglas (GrammarRule, RuleCondition, RuleAction)
  - Registro (RuleRegistry)
  - Motor de ejecución (RuleEngine)
  - Resolución de conflictos (ConflictResolver)
  - Confianza multidimensional (ConfidenceCalculator)
  - SemanticFrame (construcción y evaluación)
"""

from __future__ import annotations

import pytest

from app.lsec_grammar.schema import (
    GrammarRule,
    RuleAction,
    RuleCondition,
    RuleScope,
    RuleValidationStatus,
)
from app.lsec_grammar.registry import RuleRegistry
from app.lsec_grammar.rule_engine import RuleEngine, RuleApplication
from app.lsec_grammar.conflict_resolver import ConflictResolver, ConflictRecord
from app.lsec_grammar.confidence import ConfidenceCalculator, ConfidenceVector


# ============================================================
# Tests de Esquema (GrammarRule)
# ============================================================

class TestGrammarRuleSchema:
    """Pruebas del esquema tipado de reglas."""

    def test_rule_creation_minimal(self) -> None:
        rule = GrammarRule(
            rule_id="TEST_RULE_01",
            name="Regla de prueba mínima",
        )
        assert rule.rule_id == "TEST_RULE_01"
        assert rule.priority == 50
        assert rule.scope == RuleScope.WORD_ORDER
        assert rule.validation_status == RuleValidationStatus.PROVISIONAL
        assert rule.is_executable is True

    def test_rule_draft_not_executable(self) -> None:
        rule = GrammarRule(
            rule_id="DRAFT_RULE",
            name="Borrador",
            validation_status=RuleValidationStatus.DRAFT,
        )
        assert rule.is_executable is False

    def test_rule_rejected_not_executable(self) -> None:
        rule = GrammarRule(
            rule_id="REJECTED_RULE",
            name="Rechazada",
            validation_status=RuleValidationStatus.REJECTED,
        )
        assert rule.is_executable is False

    def test_rule_provisional_reduces_confidence(self) -> None:
        rule = GrammarRule(
            rule_id="PROV_RULE",
            name="Provisional",
            validation_status=RuleValidationStatus.PROVISIONAL,
        )
        assert rule.reduces_confidence is True
        assert rule.requires_review is True

    def test_rule_validated_does_not_reduce_confidence(self) -> None:
        rule = GrammarRule(
            rule_id="VAL_RULE",
            name="Validada",
            validation_status=RuleValidationStatus.COMMUNITY_VALIDATED,
        )
        assert rule.reduces_confidence is False
        assert rule.requires_review is False

    def test_rule_with_conditions_and_actions(self) -> None:
        rule = GrammarRule(
            rule_id="FULL_RULE",
            name="Regla completa",
            conditions=[
                RuleCondition(field="polarity", operator="eq", value="negative"),
                RuleCondition(field="sentence_type", operator="neq", value="interrogative_wh"),
            ],
            actions=[
                RuleAction(action_type="reorder", parameters={"pattern": "negation_final"}),
                RuleAction(action_type="set_non_manual", parameters={"expression": "negación"}),
            ],
        )
        assert len(rule.conditions) == 2
        assert len(rule.actions) == 2
        assert rule.conditions[0].field == "polarity"
        assert rule.actions[0].action_type == "reorder"


# ============================================================
# Tests del Registro (RuleRegistry)
# ============================================================

class TestRuleRegistry:
    """Pruebas del registro central de reglas."""

    def test_baseline_rules_loaded(self) -> None:
        registry = RuleRegistry()
        assert registry.count >= 20
        assert registry.get("LSEC_NEGATION_POSTVERBAL") is not None
        assert registry.get("LSEC_WH_FINAL") is not None
        assert registry.get("LSEC_SOV_ORDER") is not None

    def test_get_by_scope(self) -> None:
        registry = RuleRegistry()
        neg_rules = registry.get_by_scope(RuleScope.NEGATION)
        assert len(neg_rules) >= 1
        assert all(r.scope == RuleScope.NEGATION for r in neg_rules)

    def test_get_executable_filters_drafts(self) -> None:
        registry = RuleRegistry()
        registry.register(GrammarRule(
            rule_id="DRAFT_TEST",
            name="Borrador test",
            validation_status=RuleValidationStatus.DRAFT,
        ))
        executable = registry.get_executable()
        assert all(r.rule_id != "DRAFT_TEST" for r in executable)

    def test_register_replaces_existing(self) -> None:
        registry = RuleRegistry()
        rule = GrammarRule(
            rule_id="LSEC_NEGATION_POSTVERBAL",
            name="Negación v2",
            description="Versión actualizada",
            grammar_version="0.2.0",
        )
        registry.register(rule)
        retrieved = registry.get("LSEC_NEGATION_POSTVERBAL")
        assert retrieved.description == "Versión actualizada"

    def test_priority_ordering_in_scope(self) -> None:
        registry = RuleRegistry()
        rules = registry.get_by_scope(RuleScope.WORD_ORDER)
        if len(rules) >= 2:
            for i in range(len(rules) - 1):
                assert rules[i].priority <= rules[i + 1].priority


# ============================================================
# Tests del Motor de Ejecución (RuleEngine)
# ============================================================

class TestRuleEngine:
    """Pruebas del motor de evaluación de reglas."""

    def test_eval_eq(self) -> None:
        engine = RuleEngine()
        cond = RuleCondition(field="polarity", operator="eq", value="negative")
        assert engine.evaluate_conditions([cond], {"polarity": "negative"}) is True
        assert engine.evaluate_conditions([cond], {"polarity": "positive"}) is False

    def test_eval_neq(self) -> None:
        engine = RuleEngine()
        cond = RuleCondition(field="sentence_type", operator="neq", value="imperative")
        assert engine.evaluate_conditions([cond], {"sentence_type": "declarative"}) is True
        assert engine.evaluate_conditions([cond], {"sentence_type": "imperative"}) is False

    def test_eval_in(self) -> None:
        engine = RuleEngine()
        cond = RuleCondition(field="sentence_type", operator="in", value=["declarative", "exclamative"])
        assert engine.evaluate_conditions([cond], {"sentence_type": "declarative"}) is True
        assert engine.evaluate_conditions([cond], {"sentence_type": "imperative"}) is False

    def test_eval_contains(self) -> None:
        engine = RuleEngine()
        cond = RuleCondition(field="source_text", operator="contains", value="universidad")
        assert engine.evaluate_conditions([cond], {"source_text": "la universidad ofrece"}) is True
        assert engine.evaluate_conditions([cond], {"source_text": "hoy es martes"}) is False

    def test_eval_exists(self) -> None:
        engine = RuleEngine()
        cond = RuleCondition(field="topic", operator="exists", value=True)
        assert engine.evaluate_conditions([cond], {"topic": "UPEC"}) is True
        assert engine.evaluate_conditions([cond], {"topic": None}) is False
        assert engine.evaluate_conditions([cond], {"topic": ""}) is False

    def test_eval_not_exists(self) -> None:
        engine = RuleEngine()
        cond = RuleCondition(field="topic", operator="exists", value=False)
        assert engine.evaluate_conditions([cond], {"topic": None}) is True
        assert engine.evaluate_conditions([cond], {"topic": "algo"}) is False

    def test_eval_conjunction(self) -> None:
        engine = RuleEngine()
        conds = [
            RuleCondition(field="polarity", operator="eq", value="negative"),
            RuleCondition(field="sentence_type", operator="eq", value="declarative"),
        ]
        assert engine.evaluate_conditions(conds, {"polarity": "negative", "sentence_type": "declarative"}) is True
        assert engine.evaluate_conditions(conds, {"polarity": "negative", "sentence_type": "imperative"}) is False

    def test_eval_deep_key(self) -> None:
        engine = RuleEngine()
        cond = RuleCondition(field="predicate.type", operator="eq", value="ACTION")
        assert engine.evaluate_conditions([cond], {"predicate": {"type": "ACTION"}}) is True

    def test_apply_rules_basic(self) -> None:
        engine = RuleEngine()
        rules = [
            GrammarRule(
                rule_id="R1",
                name="Regla 1",
                conditions=[RuleCondition(field="polarity", operator="eq", value="negative")],
                actions=[RuleAction(action_type="set_non_manual", parameters={"expression": "negación"})],
            ),
            GrammarRule(
                rule_id="R2",
                name="Regla 2",
                conditions=[RuleCondition(field="polarity", operator="eq", value="positive")],
                actions=[RuleAction(action_type="reorder", parameters={"pattern": "SOV"})],
            ),
        ]
        frame = {"polarity": "negative", "sentence_type": "declarative"}
        apps = engine.apply_rules(rules, frame)
        assert len(apps) == 1
        assert apps[0].rule_id == "R1"

    def test_apply_rules_exclusions(self) -> None:
        engine = RuleEngine()
        rules = [
            GrammarRule(
                rule_id="R_A",
                name="Regla A",
                conditions=[RuleCondition(field="polarity", operator="eq", value="negative")],
                actions=[RuleAction(action_type="reorder", parameters={})],
                exclusions=["R_B"],
            ),
            GrammarRule(
                rule_id="R_B",
                name="Regla B",
                conditions=[RuleCondition(field="polarity", operator="eq", value="negative")],
                actions=[RuleAction(action_type="reorder", parameters={})],
            ),
        ]
        frame = {"polarity": "negative"}
        apps = engine.apply_rules(rules, frame)
        assert len(apps) == 1
        assert apps[0].rule_id == "R_A"


# ============================================================
# Tests del Resolutor de Conflictos
# ============================================================

class TestConflictResolver:
    """Pruebas de resolución de conflictos entre reglas."""

    def test_no_conflict(self) -> None:
        rules = [
            GrammarRule(rule_id="R1", name="R1", priority=10),
            GrammarRule(rule_id="R2", name="R2", priority=20),
        ]
        winners, conflicts = ConflictResolver.resolve(rules)
        assert len(winners) == 2
        assert len(conflicts) == 0

    def test_resolve_by_priority(self) -> None:
        rules = [
            GrammarRule(rule_id="R_HIGH", name="Alta prioridad", priority=10, exclusions=["R_LOW"]),
            GrammarRule(rule_id="R_LOW", name="Baja prioridad", priority=50, exclusions=["R_HIGH"]),
        ]
        winners, conflicts = ConflictResolver.resolve(rules)
        # R_HIGH wins by priority and excludes R_LOW preemptively
        assert len(winners) == 1
        assert winners[0].rule_id == "R_HIGH"

    def test_single_rule_no_conflict(self) -> None:
        rules = [GrammarRule(rule_id="SOLO", name="Única")]
        winners, conflicts = ConflictResolver.resolve(rules)
        assert len(winners) == 1
        assert len(conflicts) == 0


# ============================================================
# Tests de Confianza Multidimensional
# ============================================================

class TestConfidenceCalculator:
    """Pruebas de cálculo de confianza multidimensional."""

    def test_no_applications(self) -> None:
        vec = ConfidenceCalculator.from_rule_applications([])
        assert vec.linguistic == 0.65  # Sin reglas = heurístico
        assert vec.overall > 0.0

    def test_with_applications(self) -> None:
        apps = [
            RuleApplication(rule_id="R1", rule_name="R1", scope=RuleScope.WORD_ORDER),
        ]
        vec = ConfidenceCalculator.from_rule_applications(apps)
        assert vec.linguistic >= 0.80
        assert vec.overall > 0.0

    def test_unresolved_reduces_production(self) -> None:
        vec_ok = ConfidenceCalculator.from_rule_applications([], has_unresolved=False)
        vec_bad = ConfidenceCalculator.from_rule_applications([], has_unresolved=True)
        assert vec_ok.production > vec_bad.production

    def test_lexicon_coverage_affects_lexical(self) -> None:
        vec_full = ConfidenceCalculator.from_rule_applications([], lexicon_hit_ratio=1.0)
        vec_partial = ConfidenceCalculator.from_rule_applications([], lexicon_hit_ratio=0.5)
        assert vec_full.lexical > vec_partial.lexical

    def test_to_dict(self) -> None:
        vec = ConfidenceCalculator.from_rule_applications([])
        d = vec.to_dict()
        assert "linguistic" in d
        assert "lexical" in d
        assert "semantic" in d
        assert "production" in d
        assert "overall" in d


# ============================================================
# Tests de SemanticFrame
# ============================================================

class TestSemanticFrame:
    """Pruebas de construcción de SemanticFrame."""

    def test_frame_from_proposition_basic(self) -> None:
        from app.core.schemas import SemanticProposition, SemanticFrame
        prop = SemanticProposition(
            id="p1",
            source_text="La universidad ofrece carreras.",
            normalized_text="la universidad ofrece carreras",
            polarity="positive",
            modality="declarative",
        )
        frame = SemanticFrame.from_proposition(prop)
        assert frame.frame_id == "frame_p1"
        assert frame.proposition_id == "p1"
        assert frame.sentence_type == "declarative"
        assert frame.polarity == "positive"

    def test_frame_from_negative_proposition(self) -> None:
        from app.core.schemas import SemanticProposition, SemanticFrame
        prop = SemanticProposition(
            id="p2",
            source_text="No ofrecemos eso.",
            normalized_text="no ofrecemos eso",
            polarity="negative",
            modality="declarative",
        )
        frame = SemanticFrame.from_proposition(prop)
        assert frame.polarity == "negative"
        assert frame.negation_scope == "clausal"

    def test_frame_interrogative_wh(self) -> None:
        from app.core.schemas import SemanticProposition, SemanticFrame
        prop = SemanticProposition(
            id="p3",
            source_text="¿Qué carrera ofrece la UPEC?",
            normalized_text="qué carrera ofrece la upec",
            modality="declarative",
        )
        frame = SemanticFrame.from_proposition(prop)
        assert frame.sentence_type == "interrogative_wh"

    def test_frame_interrogative_yn(self) -> None:
        from app.core.schemas import SemanticProposition, SemanticFrame
        prop = SemanticProposition(
            id="p4",
            source_text="¿Ofrecen carreras de grado?",
            normalized_text="ofrecen carreras de grado",
            modality="declarative",
        )
        frame = SemanticFrame.from_proposition(prop)
        assert frame.sentence_type == "interrogative_yn"

    def test_frame_to_eval_dict(self) -> None:
        from app.core.schemas import SemanticProposition, SemanticFrame
        prop = SemanticProposition(
            id="p5",
            source_text="UPEC educa.",
            normalized_text="upec educa",
        )
        frame = SemanticFrame.from_proposition(prop)
        d = frame.to_eval_dict()
        assert isinstance(d, dict)
        assert "sentence_type" in d
        assert "polarity" in d

    def test_frame_with_participants(self) -> None:
        from app.core.schemas import (
            SemanticProposition,
            SemanticFrame,
            SemanticPredicate,
            SemanticParticipant,
            PredicateType,
            ParticipantType,
            SemanticRole,
        )
        prop = SemanticProposition(
            id="p6",
            source_text="Los estudiantes estudian ingeniería.",
            normalized_text="los estudiantes estudian ingeniería",
            predicate=SemanticPredicate(lemma="estudiar", predicate_type=PredicateType.ACTION),
            participants=[
                SemanticParticipant(
                    lemma="estudiante",
                    normalized_text="estudiantes",
                    participant_type=ParticipantType.PERSON,
                    semantic_role=SemanticRole.AGENT,
                ),
                SemanticParticipant(
                    lemma="ingeniería",
                    normalized_text="ingeniería",
                    participant_type=ParticipantType.PERSON,
                    semantic_role=SemanticRole.THEME,
                ),
            ],
        )
        frame = SemanticFrame.from_proposition(prop)
        assert frame.predicate_lemma == "estudiar"
        assert frame.predicate_type == "ACTION"
        assert frame.has_patient_or_theme is True
        assert frame.agent == "estudiante"
        assert frame.patient == "ingeniería"
        assert frame.explicit_subject is True
        assert len(frame.participants) == 2


# ============================================================
# Tests de Integración: Registro + Motor + Frame
# ============================================================

class TestGrammarIntegration:
    """Pruebas de integración del flujo completo de reglas."""

    def test_negation_rule_activates_on_negative_frame(self) -> None:
        registry = RuleRegistry()
        engine = RuleEngine()

        frame = {
            "polarity": "negative",
            "sentence_type": "declarative",
        }

        neg_rules = registry.get_executable(RuleScope.NEGATION)
        apps = engine.apply_rules(neg_rules, frame)
        assert len(apps) >= 1
        assert any(a.rule_id == "LSEC_NEGATION_POSTVERBAL" for a in apps)

    def test_wh_rule_activates_on_interrogative(self) -> None:
        registry = RuleRegistry()
        engine = RuleEngine()

        frame = {
            "sentence_type": "interrogative_wh",
        }

        q_rules = registry.get_executable(RuleScope.INTERROGATION)
        apps = engine.apply_rules(q_rules, frame)
        assert any(a.rule_id == "LSEC_WH_FINAL" for a in apps)

    def test_temporal_rule_activates(self) -> None:
        registry = RuleRegistry()
        engine = RuleEngine()

        frame = {
            "has_temporal_reference": True,
        }

        temp_rules = registry.get_executable(RuleScope.TEMPORALITY)
        apps = engine.apply_rules(temp_rules, frame)
        assert any(a.rule_id == "LSEC_TIME_INITIAL" for a in apps)

    def test_full_frame_evaluation(self) -> None:
        """Evalúa todas las reglas contra un frame completo."""
        registry = RuleRegistry()
        engine = RuleEngine()

        frame = {
            "sentence_type": "declarative",
            "polarity": "positive",
            "has_temporal_reference": True,
            "topic": "UPEC",
            "predicate_type": "ACTION",
            "has_patient_or_theme": True,
            "explicit_subject": True,
        }

        all_rules = registry.get_executable()
        apps = engine.apply_rules(all_rules, frame)
        assert len(apps) >= 2  # Al menos temporal y orden SOV
        rule_ids = [a.rule_id for a in apps]
        assert "LSEC_TIME_INITIAL" in rule_ids
        assert "LSEC_SOV_ORDER" in rule_ids


# ============================================================
# Punto 9: Pruebas Positivas, Negativas, Ambiguas, Contraejemplos y Conflictos
# ============================================================

class TestRuleCoveragePositiveNegativeAmbiguousCounterexamplesConflicts:
    """
    Pruebas sistemáticas para cada regla auditada cubriendo:
      - Caso positivo (condiciones cumplidas)
      - Caso negativo (condiciones no cumplidas)
      - Caso ambiguo / contraejemplo documentado
      - Resolución de conflictos e incompatibilidades mutuas
    """

    @pytest.fixture
    def setup_engine(self):
        registry = RuleRegistry()
        engine = RuleEngine()
        resolver = ConflictResolver()
        return registry, engine, resolver

    # 1. LSEC_TOPIC_COMMENT_ORDER
    def test_topic_comment_positive_negative_conflict(self, setup_engine) -> None:
        registry, engine, resolver = setup_engine
        rules = registry.get_executable(RuleScope.WORD_ORDER)

        # Positivo: declarativa con tópico explícito
        pos_frame = {"sentence_type": "declarative", "topic": "UNIVERSIDAD"}
        pos_apps = engine.apply_rules(rules, pos_frame)
        assert any(a.rule_id == "LSEC_TOPIC_COMMENT_ORDER" for a in pos_apps)

        # Negativo: declarativa sin tópico
        neg_frame = {"sentence_type": "declarative", "topic": None}
        neg_apps = engine.apply_rules(rules, neg_frame)
        assert not any(a.rule_id == "LSEC_TOPIC_COMMENT_ORDER" for a in neg_apps)

        # Conflicto / Exclusión: imperativo directivo excluye tópico-comentario
        imp_frame = {"sentence_type": "imperative", "modality": "imperative", "topic": "CARRERA"}
        imp_apps = engine.apply_rules(rules, imp_frame)
        imp_rule_ids = {a.rule_id for a in imp_apps}
        # Imperativo tiene prioridad y exclusión sobre tópico-comentario
        assert "LSEC_IMPERATIVE_VERB_FIRST" in imp_rule_ids or "LSEC_TOPIC_COMMENT_ORDER" not in imp_rule_ids

    # 2. LSEC_SOV_ORDER
    def test_sov_order_positive_negative_conflict(self, setup_engine) -> None:
        registry, engine, resolver = setup_engine
        rules = registry.get_executable(RuleScope.WORD_ORDER)

        # Positivo: transitiva de acción con paciente/tema
        pos_frame = {
            "predicate_type": "ACTION",
            "has_patient_or_theme": True,
            "is_copulative": False,
        }
        pos_apps = engine.apply_rules(rules, pos_frame)
        assert any(a.rule_id == "LSEC_SOV_ORDER" for a in pos_apps)

        # Negativo: intransitiva sin paciente/tema
        neg_frame = {
            "predicate_type": "ACTION",
            "has_patient_or_theme": False,
            "explicit_subject": True,
            "sentence_type": "declarative",
            "is_copulative": False,
        }
        neg_apps = engine.apply_rules(rules, neg_frame)
        assert not any(a.rule_id == "LSEC_SOV_ORDER" for a in neg_apps)
        assert any(a.rule_id == "LSEC_SV_INTRANSITIVE" for a in neg_apps)

        # Contraejemplo: cópula de estado no aplica SOV
        cop_frame = {
            "predicate_type": "STATE",
            "is_copulative": True,
            "has_patient_or_theme": True,
        }
        cop_apps = engine.apply_rules(rules, cop_frame)
        assert not any(a.rule_id == "LSEC_SOV_ORDER" for a in cop_apps)

    # 3. LSEC_TIME_INITIAL
    def test_time_initial_positive_negative(self, setup_engine) -> None:
        registry, engine, _ = setup_engine
        rules = registry.get_executable(RuleScope.TEMPORALITY)

        # Positivo: marco temporal activo
        pos_apps = engine.apply_rules(rules, {"has_temporal_reference": True})
        assert any(a.rule_id == "LSEC_TIME_INITIAL" for a in pos_apps)

        # Negativo: sin referencia temporal
        neg_apps = engine.apply_rules(rules, {"has_temporal_reference": False})
        assert not any(a.rule_id == "LSEC_TIME_INITIAL" for a in neg_apps)

    # 4. LSEC_WH_FINAL
    def test_wh_final_positive_negative_conflict(self, setup_engine) -> None:
        registry, engine, resolver = setup_engine
        rules = registry.get_executable(RuleScope.INTERROGATION)

        # Positivo: pregunta QU directa
        pos_apps = engine.apply_rules(rules, {"sentence_type": "interrogative_wh"})
        assert any(a.rule_id == "LSEC_WH_FINAL" for a in pos_apps)

        # Negativo: declarativa
        neg_apps = engine.apply_rules(rules, {"sentence_type": "declarative"})
        assert not any(a.rule_id == "LSEC_WH_FINAL" for a in neg_apps)

        # Conflicto / Exclusión: imperativo excluye WH_FINAL y contraejemplo documentado
        wh_rule = registry.get("LSEC_WH_FINAL")
        assert wh_rule is not None
        assert "LSEC_IMPERATIVE_VERB_FIRST" in wh_rule.exclusions
        assert len(wh_rule.counterexamples) > 0
        assert any("subordinada" in c["reason"].lower() or "indirecta" in c["reason"].lower() for c in wh_rule.counterexamples)

    # 5. LSEC_NEGATION_POSTVERBAL
    def test_negation_postverbal_positive_negative(self, setup_engine) -> None:
        registry, engine, _ = setup_engine
        rules = registry.get_executable(RuleScope.NEGATION)

        # Positivo: polaridad negativa
        pos_apps = engine.apply_rules(rules, {"polarity": "negative"})
        assert any(a.rule_id == "LSEC_NEGATION_POSTVERBAL" for a in pos_apps)

        # Negativo: polaridad positiva
        neg_apps = engine.apply_rules(rules, {"polarity": "positive"})
        assert not any(a.rule_id == "LSEC_NEGATION_POSTVERBAL" for a in neg_apps)

    # 6. Tipología de Cópulas: Atributiva vs. Existencial vs. Locativa
    def test_copula_omission_vs_existential_vs_locative(self, setup_engine) -> None:
        registry, engine, _ = setup_engine
        all_rules = registry.get_executable()

        # Cópula atributiva / identificacional -> LSEC_COPULA_OMISSION
        attr_frame = {"copula_type": "attributive", "is_copulative": True}
        attr_apps = engine.apply_rules(all_rules, attr_frame)
        attr_ids = {a.rule_id for a in attr_apps}
        assert "LSEC_COPULA_OMISSION" in attr_ids
        assert "LSEC_COPULA_EXISTENTIAL" not in attr_ids

        # Cópula existencial ('hay') -> LSEC_COPULA_EXISTENTIAL (HABER)
        exist_frame = {"copula_type": "existencial", "is_copulative": True}
        exist_apps = engine.apply_rules(all_rules, exist_frame)
        exist_ids = {a.rule_id for a in exist_apps}
        assert "LSEC_COPULA_EXISTENTIAL" in exist_ids
        assert "LSEC_COPULA_OMISSION" not in exist_ids

        # Cópula locativa ('está en') -> LSEC_COPULA_LOCATIVE (locus)
        loc_frame = {"copula_type": "locativa", "is_copulative": True}
        loc_apps = engine.apply_rules(all_rules, loc_frame)
        loc_ids = {a.rule_id for a in loc_apps}
        assert "LSEC_COPULA_LOCATIVE" in loc_ids
        assert "LSEC_COPULA_OMISSION" not in loc_ids

    # 7. Adjetivo Posnominal vs. Predicativo
    def test_adjective_postnominal_vs_predicative(self, setup_engine) -> None:
        registry, engine, _ = setup_engine
        all_rules = registry.get_executable()

        # Adjetivo atributivo posnominal
        attr_frame = {"has_attributive_adjective": True, "sentence_type": "declarative"}
        attr_apps = engine.apply_rules(all_rules, attr_frame)
        assert any(a.rule_id == "LSEC_ADJ_POSTNOMINAL" for a in attr_apps)

        # Sin adjetivo atributivo -> no activa LSEC_ADJ_POSTNOMINAL
        no_adj_frame = {"has_attributive_adjective": False, "sentence_type": "declarative"}
        no_adj_apps = engine.apply_rules(all_rules, no_adj_frame)
        assert not any(a.rule_id == "LSEC_ADJ_POSTNOMINAL" for a in no_adj_apps)

        # Adjetivo predicativo en cláusula copulativa
        pred_frame = {"has_adjectival_predicate": True, "copula_type": "attributive"}
        pred_apps = engine.apply_rules(all_rules, pred_frame)
        assert any(a.rule_id == "LSEC_ADJ_PREDICATIVE" for a in pred_apps)

    # 8. Sujeto Tácito: PRO1/PRO2 vs. Impersonal / Genérico
    def test_prodrop_explicit_vs_impersonal_generic(self, setup_engine) -> None:
        registry, engine, _ = setup_engine
        all_rules = registry.get_executable()

        # Positivo: pro-drop 1ra persona -> genera deixis
        pro1_frame = {"explicit_subject": False, "prodrop_type": "pro1", "agent_person": "1"}
        pro1_apps = engine.apply_rules(all_rules, pro1_frame)
        assert any(a.rule_id == "LSEC_PRODROP_EXPLICIT" for a in pro1_apps)

        # Negativo: sujeto explícito -> no genera deixis ciega
        exp_frame = {"explicit_subject": True, "prodrop_type": None}
        exp_apps = engine.apply_rules(all_rules, exp_frame)
        assert not any(a.rule_id == "LSEC_PRODROP_EXPLICIT" for a in exp_apps)

        # Contraejemplo: impersonal / genérico -> NO genera deixis ciega
        imp_frame = {"explicit_subject": False, "prodrop_type": "impersonal"}
        imp_apps = engine.apply_rules(all_rules, imp_frame)
        assert not any(a.rule_id == "LSEC_PRODROP_EXPLICIT" for a in imp_apps)

    # 9. Clasificador candidato con requisito de revisión
    def test_classifier_candidate_requires_review(self, setup_engine) -> None:
        registry, engine, _ = setup_engine
        all_rules = registry.get_executable()

        # Positivo: verbo de movimiento con paciente -> CLASSIFIER_CANDIDATE
        mov_frame = {"predicate_type": "MOVEMENT", "patient": "auto"}
        mov_apps = engine.apply_rules(all_rules, mov_frame)
        cl_app = next((a for a in mov_apps if a.rule_id == "LSEC_CLASSIFIER_MOVEMENT"), None)
        assert cl_app is not None
        assert cl_app.requires_review is True

        # Negativo: verbo cognitivo sin disposición física
        cog_frame = {"predicate_type": "COGNITIVE", "patient": "idea"}
        cog_apps = engine.apply_rules(all_rules, cog_frame)
        assert not any(a.rule_id == "LSEC_CLASSIFIER_MOVEMENT" for a in cog_apps)

    # 10. Transferencia funcional de DET y ADP
    def test_functional_transfer_det_adp_positive_negative(self, setup_engine) -> None:
        registry, engine, _ = setup_engine
        all_rules = registry.get_executable()

        # Positivo: transferencias funcionales detectadas
        pos_frame = {"functional_transfers": [{"function_type": "possession", "target_gloss": "PRO1"}]}
        pos_apps = engine.apply_rules(all_rules, pos_frame)
        assert any(a.rule_id == "LSEC_FUNCTIONAL_TRANSFER_DET_ADP" for a in pos_apps)

        # Negativo: sin transferencias
        neg_frame = {"functional_transfers": None}
        neg_apps = engine.apply_rules(all_rules, neg_frame)
        assert not any(a.rule_id == "LSEC_FUNCTIONAL_TRANSFER_DET_ADP" for a in neg_apps)


# ============================================================
# Punto 10: Prueba de Desactivación Individual de Reglas
# ============================================================

class TestIndividualRuleDeactivation:
    """
    Verifica que al desactivar individualmente cada regla del motor,
    solamente cambia el comportamiento lingüístico correspondiente
    y el resto de la estructura oracional se conserva intacto.
    """

    @pytest.fixture
    def nlp_service(self):
        from app.services.nlp_service import get_nlp_service
        return get_nlp_service()

    @pytest.mark.asyncio
    async def test_deactivate_wh_final_only_changes_wh_position(self, nlp_service) -> None:
        """Al desactivar LSEC_WH_FINAL, la palabra interrogativa no se traslada al final."""
        text = "¿Qué estudias?"
        res_baseline = await nlp_service.translate_to_gloss(text)
        res_deactivated = await nlp_service.translate_to_gloss(text, exclude_rule_ids={"LSEC_WH_FINAL"})

        base_glosses = [g.gloss for g in res_baseline.glosses]
        deact_glosses = [g.gloss for g in res_deactivated.glosses]

        # En baseline, QUÉ está al final
        assert base_glosses[-1] == "QUÉ"
        # Al desactivar, QUÉ no está al final y precede al verbo
        assert deact_glosses[-1] != "QUÉ"
        assert deact_glosses.index("QUÉ") < deact_glosses.index("ESTUDIAR")
        # El predicado 'ESTUDIAR' se mantiene idéntico en ambos
        assert "ESTUDIAR" in base_glosses and "ESTUDIAR" in deact_glosses

    @pytest.mark.asyncio
    async def test_deactivate_negation_postverbal_only_changes_negation(self, nlp_service) -> None:
        """Al desactivar LSEC_NEGATION_POSTVERBAL, la negación se conserva preverbal."""
        text = "Juan no come pan"
        res_baseline = await nlp_service.translate_to_gloss(text)
        res_deactivated = await nlp_service.translate_to_gloss(text, exclude_rule_ids={"LSEC_NEGATION_POSTVERBAL"})

        base_glosses = [g.gloss for g in res_baseline.glosses]
        deact_glosses = [g.gloss for g in res_deactivated.glosses]

        # En baseline, NO está posverbal (al final)
        assert base_glosses[-1] == "NO"
        # Al desactivar, NO precede al verbo
        no_idx = deact_glosses.index("NO")
        comer_idx = deact_glosses.index("COMER")
        assert no_idx < comer_idx
        # El resto de constituyentes (JUAN, PAN) están presentes
        assert "JUAN" in deact_glosses and "PAN" in deact_glosses

    @pytest.mark.asyncio
    async def test_deactivate_time_initial_only_changes_time(self, nlp_service) -> None:
        """Al desactivar LSEC_TIME_INITIAL, el adverbio temporal no se fuerza al inicio."""
        text = "Juan come pan ayer"
        res_baseline = await nlp_service.translate_to_gloss(text)
        res_deactivated = await nlp_service.translate_to_gloss(text, exclude_rule_ids={"LSEC_TIME_INITIAL"})

        base_glosses = [g.gloss for g in res_baseline.glosses]
        deact_glosses = [g.gloss for g in res_deactivated.glosses]

        # En baseline, AYER está al inicio
        assert base_glosses[0] == "AYER"
        # Al desactivar, AYER no está al inicio
        assert deact_glosses[0] != "AYER"
        assert "AYER" in deact_glosses

    @pytest.mark.asyncio
    async def test_deactivate_copula_omission_retains_copula(self, nlp_service) -> None:
        """Al desactivar LSEC_COPULA_OMISSION, la cópula no se omite y se conserva en las glosas."""
        text = "Juan es profesor"
        res_baseline = await nlp_service.translate_to_gloss(text)
        res_deactivated = await nlp_service.translate_to_gloss(text, exclude_rule_ids={"LSEC_COPULA_OMISSION"})

        base_glosses = [g.gloss for g in res_baseline.glosses]
        deact_glosses = [g.gloss for g in res_deactivated.glosses]

        # En baseline, la cópula 'es' fue omitida
        assert "SER" not in base_glosses and "ES" not in base_glosses
        # Al desactivar la regla, la cópula se conserva
        assert "ES" in deact_glosses or "SER" in deact_glosses
        assert "JUAN" in deact_glosses and "PROFESOR" in deact_glosses

    @pytest.mark.asyncio
    async def test_deactivate_sov_retains_svo_order(self, nlp_service) -> None:
        """Al desactivar LSEC_SOV_ORDER, la proposición transitiva conserva orden SVO."""
        text = "Juan come manzana"
        res_baseline = await nlp_service.translate_to_gloss(text)
        res_deactivated = await nlp_service.translate_to_gloss(text, exclude_rule_ids={"LSEC_SOV_ORDER"})

        base_glosses = [g.gloss for g in res_baseline.glosses]
        deact_glosses = [g.gloss for g in res_deactivated.glosses]

        # En baseline SOV: MANZANA (objeto) precede a COMER (verbo)
        assert base_glosses.index("MANZANA") < base_glosses.index("COMER")
        # Al desactivar SOV: COMER (verbo) precede a MANZANA (objeto) -> SVO
        assert deact_glosses.index("COMER") < deact_glosses.index("MANZANA")


# ============================================================
# Puntos 4, 5, 11: Aspecto, Pro-drop y Bloqueo de Adiciones Semánticas
# ============================================================

class TestSemanticAdditionBlockingAndAspectTypology:
    """
    Pruebas para los puntos 4, 5 y 11:
      - Separación de aspecto gramatical y referencia temporal (sin AHORA en pasado)
      - Tipología de pro-drop (sin deixis ciega en impersonal o genérico)
      - Bloqueo de conceptos no respaldados
    """

    @pytest.fixture
    def nlp_service(self):
        from app.services.nlp_service import get_nlp_service
        return get_nlp_service()

    @pytest.mark.asyncio
    async def test_progressive_aspect_does_not_convert_to_ahora_in_past(self, nlp_service) -> None:
        """Verifica que el aspecto progresivo en pasado ('estaba comiendo') NO inserte AHORA."""
        text = "Ayer Juan estaba comiendo pan"
        result = await nlp_service.translate_to_gloss(text)
        gloss_names = [g.gloss for g in result.glosses]

        # AHORA es deíctico de presente; NO debe generarse en contexto pasado
        assert "AHORA" not in gloss_names
        assert "AYER" in gloss_names
        assert "COMER" in gloss_names

    @pytest.mark.asyncio
    async def test_prodrop_impersonal_does_not_create_deictic_participant(self, nlp_service) -> None:
        """Verifica que oraciones impersonales ('se vive bien') no creen participante deíctico PRO1/PRO2."""
        text = "Aquí se vive bien"
        result = await nlp_service.translate_to_gloss(text)
        gloss_names = [g.gloss for g in result.glosses]

        assert "PRO1" not in gloss_names
        assert "PRO2" not in gloss_names

    def test_unsupported_concept_blocked_from_output(self) -> None:
        """Verifica que un concepto sin respaldo explícito ni inferencial sea bloqueado (Punto 11)."""
        from app.services.discourse_planner import DiscoursePlanner
        from app.core.schemas import (
            SemanticProposition, SemanticPredicate, PredicateType, GlossItem, GlossType, AlignmentType
        )

        planner = DiscoursePlanner()
        prop = SemanticProposition(
            id="p_test_block",
            source_text="El profesor habla",
            normalized_text="el profesor habla",
            predicate=SemanticPredicate(lemma="hablar", predicate_type=PredicateType.ACTION),
        )

        plans, blocks = [], []
        glosses, plans, blocks, _, _, _ = planner.plan_and_generate([prop])
        gloss_names = {g.gloss for g in glosses}

        # Comprobar que no existan conceptos no respaldados en las glosas finales
        plan = plans[0]
        for blocked_c in plan.unsupported_realized_concepts:
            assert blocked_c not in gloss_names

