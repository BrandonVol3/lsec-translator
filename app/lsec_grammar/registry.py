"""
Registro central de reglas gramaticales LSEC.

Almacena, indexa y consulta reglas por ámbito, estado de validación y prioridad.
Migra las reglas dispersas existentes en el código a entradas centralizadas.
"""

from __future__ import annotations

import logging
from typing import Dict, List, Optional, Set

from app.lsec_grammar.schema import (
    GrammarRule,
    RuleAction,
    RuleCondition,
    RuleScope,
    RuleValidationStatus,
)

logger = logging.getLogger(__name__)


class RuleRegistry:
    """
    Registro singleton de reglas gramaticales LSEC.

    Las reglas se registran una vez y se consultan por ámbito o prioridad.
    """

    def __init__(self) -> None:
        self._rules: Dict[str, GrammarRule] = {}
        self._by_scope: Dict[RuleScope, List[str]] = {}
        self._aliases: Dict[str, str] = {}
        self._load_baseline_rules()

    # ── API pública ────────────────────────────────────────────

    def register(self, rule: GrammarRule) -> None:
        """Registra una regla. Reemplaza si el ``rule_id`` ya existe."""
        self._rules[rule.rule_id] = rule
        self._by_scope.setdefault(rule.scope, [])
        if rule.rule_id not in self._by_scope[rule.scope]:
            self._by_scope[rule.scope].append(rule.rule_id)

    def get(self, rule_id: str) -> Optional[GrammarRule]:
        if rule_id in self._rules:
            return self._rules[rule_id]
        if rule_id in self._aliases:
            return self._rules.get(self._aliases[rule_id])
        return None

    def get_by_scope(self, scope: RuleScope) -> List[GrammarRule]:
        """Retorna reglas de un ámbito, ordenadas por prioridad (menor = mayor prioridad)."""
        ids = self._by_scope.get(scope, [])
        rules = [self._rules[rid] for rid in ids if rid in self._rules]
        rules.sort(key=lambda r: r.priority)
        return rules

    def get_executable(self, scope: Optional[RuleScope] = None) -> List[GrammarRule]:
        """Retorna solo reglas que pueden ejecutarse (no DRAFT ni REJECTED)."""
        if scope:
            return [r for r in self.get_by_scope(scope) if r.is_executable]
        return [r for r in self._rules.values() if r.is_executable]

    def all_rules(self) -> List[GrammarRule]:
        return list(self._rules.values())

    @property
    def count(self) -> int:
        return len(self._rules)

    # ── Reglas BASELINE_LEGACY ─────────────────────────────────

    def _load_baseline_rules(self) -> None:
        """
        Carga las reglas baseline lingüísticas auditadas con estado PROVISIONAL.
        
        Aplica los 12 principios de auditoría LSEC:
          1. Diferenciación formal de adjetivos atributivos y predicativos.
          2. Cópula tipificada (atributiva, identificacional, locativa, existencial, temporal).
          3. Transferencia funcional de determinantes y preposiciones.
          4. Separación de tiempo y aspecto (sin conversión ciega a AHORA/YA).
          5. Pro-drop tipificado (PRO1, PRO2, anafórico, locus, genérico, impersonal, ambiguo).
          6. Clasificador condicionado a candidato (CLASSIFIER_CANDIDATE con revisión humana).
          7. Patrones de orden condicionados con evidencia y excepciones.
          8. Estado PROVISIONAL en todas las reglas baseline con revisión en decisiones críticas.
        """
        baseline = [
            # 1. Orden tópico-comentario
            GrammarRule(
                rule_id="LSEC_TOPIC_COMMENT_ORDER",
                name="Orden tópico-comentario LSEC",
                description="LSEC antepone el tópico prominente al comentario de la proposición.",
                grammar_version="0.2.0",
                priority=30,
                scope=RuleScope.WORD_ORDER,
                conditions=[
                    RuleCondition(field="sentence_type", operator="in", value=["declarative", "exclamative"]),
                    RuleCondition(field="topic", operator="exists", value=True),
                ],
                actions=[
                    RuleAction(action_type="reorder", parameters={"pattern": "topic_first"}, description="Colocar tópico antes del comentario"),
                ],
                exclusions=["LSEC_IMPERATIVE_VERB_FIRST"],
                required_evidence=["discourse_topic:explicit", "sentence_type:declarative|exclamative"],
                validation_status=RuleValidationStatus.PROVISIONAL,
                confidence_weight=0.85,
                examples=[{"input": "La universidad ofrece carreras", "expected_order": "UNIVERSIDAD CARRERA OFRECER"}],
                counterexamples=[{"input": "Hay una fiesta", "reason": "Oración presentacional/existencial sin tópico prominente"}],
            ),
            # 2. Orden SOV en proposiciones transitivas
            GrammarRule(
                rule_id="LSEC_SOV_ORDER",
                name="Orden SOV en proposiciones transitivas",
                description="Proposiciones transitivas de acción o causativas siguen orden Sujeto-Objeto-Verbo.",
                grammar_version="0.2.0",
                priority=30,
                scope=RuleScope.WORD_ORDER,
                conditions=[
                    RuleCondition(field="predicate_type", operator="in", value=["ACTION", "CAUSATIVE"]),
                    RuleCondition(field="has_patient_or_theme", operator="eq", value=True),
                    RuleCondition(field="is_copulative", operator="eq", value=False),
                ],
                actions=[
                    RuleAction(action_type="reorder", parameters={"pattern": "SOV"}, description="Sujeto, Objeto, Verbo"),
                ],
                exclusions=["LSEC_IMPERATIVE_VERB_FIRST", "LSEC_SV_INTRANSITIVE"],
                required_evidence=["spacy_dep:obj", "participant_role:THEME|PATIENT", "predicate_type:ACTION|CAUSATIVE"],
                validation_status=RuleValidationStatus.PROVISIONAL,
                confidence_weight=0.80,
                examples=[{"input": "Juan come manzanas", "expected_order": "JUAN MANZANA COMER"}],
                counterexamples=[{"input": "¡Come manzanas!", "reason": "Imperativo directivo prioriza verbo al inicio"}],
            ),
            # 3. Marcador temporal al inicio
            GrammarRule(
                rule_id="LSEC_TIME_INITIAL",
                name="Marcador temporal al inicio",
                description="El marco temporal de la cláusula se establece en posición inicial.",
                grammar_version="0.2.0",
                priority=20,
                scope=RuleScope.TEMPORALITY,
                conditions=[
                    RuleCondition(field="has_temporal_reference", operator="eq", value=True),
                ],
                actions=[
                    RuleAction(action_type="reorder", parameters={"pattern": "time_first"}, description="Tiempo al inicio"),
                ],
                required_evidence=["has_temporal_reference:true"],
                validation_status=RuleValidationStatus.PROVISIONAL,
                confidence_weight=0.85,
                examples=[{"input": "Ayer estudiamos", "expected_order": "AYER PRO1-PL ESTUDIAR"}],
                counterexamples=[{"input": "Estudió hasta las 5", "reason": "Límite temporal final o subordinada de término"}],
            ),
            # 4. Negación postverbal / final con CNM
            GrammarRule(
                rule_id="LSEC_NEGATION_POSTVERBAL",
                name="Negación clausal final o postverbal",
                description="La negación clausal se ubica al final con movimiento cefálico de negación.",
                grammar_version="0.2.0",
                priority=25,
                scope=RuleScope.NEGATION,
                conditions=[
                    RuleCondition(field="polarity", operator="eq", value="negative"),
                    RuleCondition(field="negation_scope", operator="neq", value="constituent"),
                ],
                actions=[
                    RuleAction(action_type="reorder", parameters={"pattern": "negation_final"}, description="Negación al final"),
                    RuleAction(action_type="set_non_manual", parameters={
                        "marker_type": "negation",
                        "expression": "negación",
                        "head_movement": "negar",
                    }),
                ],
                required_evidence=["polarity:negative", "negation_scope:clausal"],
                validation_status=RuleValidationStatus.PROVISIONAL,
                confidence_weight=0.85,
                examples=[{"input": "No entiendo", "expected_order": "PRO1 ENTENDER NO"}],
                counterexamples=[{"input": "Compró no muchas casas", "reason": "Negación de constituyente cuantificador"}],
            ),
            # 5. Interrogativo Wh al final
            GrammarRule(
                rule_id="LSEC_WH_FINAL",
                name="Interrogativo Wh al final",
                description="En interrogativas parciales, el elemento Wh se ubica al final con cejas fruncidas/inclinación.",
                grammar_version="0.2.0",
                priority=25,
                scope=RuleScope.INTERROGATION,
                conditions=[
                    RuleCondition(field="sentence_type", operator="eq", value="interrogative_wh"),
                ],
                actions=[
                    RuleAction(action_type="reorder", parameters={"pattern": "wh_final"}),
                    RuleAction(action_type="set_non_manual", parameters={
                        "marker_type": "question_wh",
                        "expression": "pregunta_qu",
                        "head_movement": "inclinar",
                    }),
                ],
                exclusions=["LSEC_IMPERATIVE_VERB_FIRST"],
                required_evidence=["sentence_type:interrogative_wh"],
                validation_status=RuleValidationStatus.PROVISIONAL,
                confidence_weight=0.85,
                examples=[{"input": "¿Dónde estudias?", "expected_order": "PRO2 ESTUDIAR DÓNDE"}],
                counterexamples=[{"input": "No sé dónde vives", "reason": "Interrogativa indirecta / cláusula subordinada"}],
            ),
            # 6. Preguntas sí/no con cejas levantadas
            GrammarRule(
                rule_id="LSEC_YN_QUESTION",
                name="Pregunta sí/no con cejas levantadas",
                description="Preguntas totales con cejas levantadas sobre la cláusula.",
                grammar_version="0.2.0",
                priority=25,
                scope=RuleScope.INTERROGATION,
                conditions=[
                    RuleCondition(field="sentence_type", operator="eq", value="interrogative_yn"),
                ],
                actions=[
                    RuleAction(action_type="set_non_manual", parameters={
                        "marker_type": "question_yn",
                        "expression": "pregunta_sn",
                    }),
                ],
                required_evidence=["sentence_type:interrogative_yn"],
                validation_status=RuleValidationStatus.PROVISIONAL,
                confidence_weight=0.85,
            ),
            # 7. Resolución de pro-drop tipificado
            GrammarRule(
                rule_id="LSEC_PRODROP_RESOLVE",
                name="Resolución de sujeto tácito tipificado",
                description="Resuelve pro-drop distinguiendo 1ra/2da persona, anáfora y casos ambiguos.",
                grammar_version="0.2.0",
                priority=35,
                scope=RuleScope.PRODROP,
                conditions=[
                    RuleCondition(field="explicit_subject", operator="eq", value=False),
                    RuleCondition(field="prodrop_type", operator="in", value=["pro1", "pro2", "anaphoric"]),
                ],
                actions=[
                    RuleAction(action_type="resolve_prodrop", parameters={"strategy": "morphological_contextual"}),
                ],
                required_evidence=["morph_person:1|2", "discourse_antecedent"],
                validation_status=RuleValidationStatus.PROVISIONAL,
                confidence_weight=0.75,
                counterexamples=[{"input": "Llueve mucho", "reason": "Sujeto impersonal no admite resolución pronominal"}],
            ),
            # 8. Perífrasis prospectiva ir+a+infinitivo → FUTURO
            GrammarRule(
                rule_id="LSEC_PERIPHRASIS_FUTURE",
                name="Perífrasis prospectiva ir+a+infinitivo → FUTURO",
                description="La perífrasis prospectiva se realiza como marcador temporal/aspectual FUTURO antes del verbo.",
                grammar_version="0.2.0",
                priority=20,
                scope=RuleScope.ASPECT,
                conditions=[
                    RuleCondition(field="grammatical_aspect", operator="eq", value="prospective"),
                ],
                actions=[
                    RuleAction(action_type="insert_gloss", parameters={"gloss": "FUTURO", "position": "before_predicate"}),
                ],
                required_evidence=["aspect:prospective"],
                validation_status=RuleValidationStatus.PROVISIONAL,
                confidence_weight=0.85,
            ),
            # 9. Aspecto progresivo condicionado (no AHORA en pasado)
            GrammarRule(
                rule_id="LSEC_ASPECT_PROGRESSIVE",
                name="Aspecto progresivo presente → AHORA",
                description="La perífrasis progresiva estar+gerundio en presente se realiza como AHORA; en pasado se modula aspectualmente.",
                grammar_version="0.2.0",
                priority=20,
                scope=RuleScope.ASPECT,
                conditions=[
                    RuleCondition(field="grammatical_aspect", operator="eq", value="progressive"),
                    RuleCondition(field="has_past_reference", operator="eq", value=False),
                ],
                actions=[
                    RuleAction(action_type="insert_gloss", parameters={"gloss": "AHORA", "position": "after_predicate"}, description="Marcador progresivo presente"),
                ],
                required_evidence=["aspect:progressive", "has_past_reference:false"],
                validation_status=RuleValidationStatus.PROVISIONAL,
                confidence_weight=0.85,
                examples=[{"input": "Estamos construyendo", "expected": "PRO1-PL CONSTRUIR AHORA"}],
                counterexamples=[{"input": "Ayer estábamos construyendo", "reason": "Referencia temporal pasada bloquea inserción de AHORA"}],
            ),
            # 10. Aspecto perfectivo completivo (separado de tiempo)
            GrammarRule(
                rule_id="LSEC_ASPECT_PERFECTIVE",
                name="Aspecto perfectivo completivo → YA",
                description="El aspecto perfectivo completivo se realiza como YA tras el verbo, separando referencia temporal.",
                grammar_version="0.2.0",
                priority=20,
                scope=RuleScope.ASPECT,
                conditions=[
                    RuleCondition(field="grammatical_aspect", operator="eq", value="perfect"),
                    RuleCondition(field="has_past_reference", operator="eq", value=False),
                ],
                actions=[
                    RuleAction(action_type="insert_gloss", parameters={"gloss": "YA", "position": "after_predicate"}, description="Marcador perfectivo completivo"),
                ],
                required_evidence=["aspect:perfect", "has_past_reference:false"],
                validation_status=RuleValidationStatus.PROVISIONAL,
                confidence_weight=0.85,
                examples=[{"input": "Han terminado", "expected": "TERMINAR YA"}],
                counterexamples=[{"input": "El año pasado han estudiado", "reason": "Pasado histórico no debe confundirse con aspecto completivo inmediato"}],
            ),
            # 11. Topicalización con CNM
            GrammarRule(
                rule_id="LSEC_TOPICALIZATION",
                name="Topicalización con cejas levantadas",
                description="El elemento topicalizado se señala con cejas levantadas y micro-pausa.",
                grammar_version="0.2.0",
                priority=30,
                scope=RuleScope.INFORMATION_STRUCTURE,
                conditions=[
                    RuleCondition(field="topic", operator="exists", value=True),
                ],
                actions=[
                    RuleAction(action_type="set_non_manual", parameters={
                        "marker_type": "topicalization",
                        "over_topic": True,
                    }),
                ],
                required_evidence=["topic:explicit"],
                validation_status=RuleValidationStatus.PROVISIONAL,
                confidence_weight=0.75,
            ),
            # 12. Perífrasis tener+que+infinitivo → DEBER
            GrammarRule(
                rule_id="LSEC_PERIPHRASIS_OBLIGATION",
                name="Perífrasis deóntica tener+que → DEBER",
                description="Modalidad deóntica de obligación se realiza como DEBER antes del predicado.",
                grammar_version="0.2.0",
                priority=20,
                scope=RuleScope.MODALITY,
                conditions=[
                    RuleCondition(field="modality", operator="eq", value="deontic"),
                ],
                actions=[
                    RuleAction(action_type="insert_gloss", parameters={"gloss": "DEBER", "position": "before_predicate"}),
                ],
                required_evidence=["modality:deontic"],
                validation_status=RuleValidationStatus.PROVISIONAL,
                confidence_weight=0.80,
            ),
            # 13. Pro-drop: sujeto tácito con deixis diferenciada
            GrammarRule(
                rule_id="LSEC_PRODROP_EXPLICIT",
                name="Pro-drop → deixis diferenciada PRO1/PRO2",
                description="Sujetos tácitos de 1ra y 2da persona reciben deixis explícita. Impersonales y ambiguos no generan deixis ciega.",
                grammar_version="0.2.0",
                priority=25,
                scope=RuleScope.COREFERENCE,
                conditions=[
                    RuleCondition(field="explicit_subject", operator="eq", value=False),
                    RuleCondition(field="prodrop_type", operator="in", value=["pro1", "pro2"]),
                ],
                actions=[
                    RuleAction(action_type="insert_gloss", parameters={"gloss": "PRO{agent_person}", "position": "before_predicate"}, description="Insertar deixis pronominal 1ra/2da"),
                ],
                required_evidence=["explicit_subject:false", "prodrop_type:pro1|pro2"],
                validation_status=RuleValidationStatus.PROVISIONAL,
                confidence_weight=0.80,
                examples=[{"input": "Ofrecemos carreras", "expected": "PRO1-PL CARRERA OFRECER"}],
                counterexamples=[{"input": "Se vive bien en Quito", "reason": "Sujeto genérico/impersonal sin deixis pronominal"}],
            ),
            # 14. Clasificador candidato con requisito de respaldo / revisión
            GrammarRule(
                rule_id="LSEC_CLASSIFIER_MOVEMENT",
                name="Candidato a clasificador en movimiento/ubicación",
                description="Genera CLASSIFIER_CANDIDATE y exige respaldo léxico o revisión humana antes de emisión.",
                grammar_version="0.2.0",
                priority=40,
                scope=RuleScope.CLASSIFIER,
                conditions=[
                    RuleCondition(field="predicate_type", operator="in", value=["MOVEMENT", "LOCATION"]),
                    RuleCondition(field="patient", operator="exists", value=True),
                ],
                actions=[
                    RuleAction(action_type="set_classifier", parameters={"status": "CLASSIFIER_CANDIDATE", "requires_lexical_support": True, "requires_review": True}),
                    RuleAction(action_type="mark_review", parameters={"reason": "Clasificador candidato requiere respaldo léxico o revisión humana"}),
                ],
                required_evidence=["predicate_type:MOVEMENT|LOCATION", "patient:exists"],
                validation_status=RuleValidationStatus.PROVISIONAL,
                confidence_weight=0.60,
                counterexamples=[{"input": "Pensamos en el auto", "reason": "Verbo cognitivo sin movimiento ni disposición física"}],
            ),
            # 15. Modo imperativo: predicado al inicio
            GrammarRule(
                rule_id="LSEC_IMPERATIVE_VERB_FIRST",
                name="Imperativo directivo simple: verbo primero",
                description="En oraciones imperativas directivas simples (sin cláusula subordinada), el verbo se coloca al inicio con CNM directiva.",
                grammar_version="0.2.0",
                priority=15,
                scope=RuleScope.WORD_ORDER,
                conditions=[
                    RuleCondition(field="sentence_type", operator="eq", value="imperative"),
                    RuleCondition(field="has_subordinate", operator="eq", value=False),
                    RuleCondition(field="is_embedded", operator="eq", value=False),
                ],
                actions=[
                    RuleAction(action_type="reorder", parameters={"pattern": "verb_first"}, description="Verbo al inicio"),
                    RuleAction(action_type="set_non_manual", parameters={"expression": "directiva", "type": "cejas_bajas_contacto_visual"}),
                ],
                exclusions=["LSEC_SOV_ORDER", "LSEC_TOPIC_COMMENT_ORDER"],
                required_evidence=["sentence_type:imperative", "has_subordinate:false", "is_embedded:false"],
                validation_status=RuleValidationStatus.PROVISIONAL,
                confidence_weight=0.80,
                examples=[{"input": "¡Estudia ingeniería!", "expected": "ESTUDIAR INGENIERÍA"}],
                counterexamples=[
                    {"input": "Haz posible hoy lo que imaginas", "reason": "Imperativo complejo con subordinada/tópico relativo preverbal"},
                    {"input": "Mañana estudia", "reason": "Tiempo inicial prevalece sobre orden directivo"},
                ],
            ),
            # 16. Cópula atributiva / identificacional: omisión de cópula enlace
            GrammarRule(
                rule_id="LSEC_COPULA_OMISSION",
                name="Omisión de cópula enlace atributiva/identificacional",
                description="Las cópulas 'ser' y 'estar' como meros enlaces atributivos, identificacionales o temporales se omiten.",
                grammar_version="0.2.0",
                priority=10,
                scope=RuleScope.WORD_ORDER,
                conditions=[
                    RuleCondition(field="is_copulative", operator="eq", value=True),
                    RuleCondition(field="copula_type", operator="in", value=["attributive", "identificational", "temporal"]),
                ],
                actions=[
                    RuleAction(action_type="omit_predicate", parameters={"reason": "copula_enlace_vacio"}, description="Omitir cópula vacía"),
                ],
                required_evidence=["copula_type:attributive|identificational|temporal"],
                validation_status=RuleValidationStatus.PROVISIONAL,
                confidence_weight=0.90,
                examples=[{"input": "La universidad es grande", "expected": "UNIVERSIDAD GRANDE"}],
                counterexamples=[{"input": "Hay estudiantes", "reason": "Cópula existencial debe realizarse como HABER/EXISTIR"}],
            ),
            # 17. Cópula existencial: retención y selección léxica HABER/EXISTIR
            GrammarRule(
                rule_id="LSEC_COPULA_EXISTENTIAL",
                name="Cópula existencial → HABER",
                description="La cópula existencial ('haber' impersonal) NO se omite: se realiza como HABER o EXISTIR.",
                grammar_version="0.2.0",
                priority=10,
                scope=RuleScope.LEXICAL_SELECTION,
                conditions=[
                    RuleCondition(field="copula_type", operator="eq", value="existencial"),
                ],
                actions=[
                    RuleAction(action_type="replace_gloss", parameters={"gloss": "HABER", "reason": "existential_copula"}),
                ],
                required_evidence=["copula_type:existencial"],
                validation_status=RuleValidationStatus.PROVISIONAL,
                confidence_weight=0.90,
                examples=[{"input": "Hay carreras", "expected": "CARRERA HABER"}],
            ),
            # 18. Cópula locativa: anclaje espacial
            GrammarRule(
                rule_id="LSEC_COPULA_LOCATIVE",
                name="Cópula locativa → asignación espacial",
                description="La cópula locativa ('estar en') se transfiere a un anclaje o locus espacial.",
                grammar_version="0.2.0",
                priority=12,
                scope=RuleScope.SPATIAL,
                conditions=[
                    RuleCondition(field="copula_type", operator="eq", value="locativa"),
                ],
                actions=[
                    RuleAction(action_type="assign_locus", parameters={"target": "location"}),
                ],
                required_evidence=["copula_type:locativa", "location:exists"],
                validation_status=RuleValidationStatus.PROVISIONAL,
                confidence_weight=0.85,
                examples=[{"input": "La sede está en Tulcán", "expected": "SEDE TULCÁN [locus:izq]"}],
            ),
            # 19. Orden S-V en proposiciones intransitivas
            GrammarRule(
                rule_id="LSEC_SV_INTRANSITIVE",
                name="Orden S-V en intransitivos",
                description="Proposiciones intransitivas usan orden Sujeto-Verbo.",
                grammar_version="0.2.0",
                priority=35,
                scope=RuleScope.WORD_ORDER,
                conditions=[
                    RuleCondition(field="sentence_type", operator="in", value=["declarative", "exclamative"]),
                    RuleCondition(field="has_patient_or_theme", operator="eq", value=False),
                    RuleCondition(field="explicit_subject", operator="eq", value=True),
                    RuleCondition(field="is_copulative", operator="eq", value=False),
                ],
                actions=[
                    RuleAction(action_type="reorder", parameters={"pattern": "SV"}, description="Orden Sujeto-Verbo"),
                ],
                exclusions=["LSEC_SOV_ORDER", "LSEC_IMPERATIVE_VERB_FIRST"],
                required_evidence=["has_patient_or_theme:false", "explicit_subject:true"],
                validation_status=RuleValidationStatus.PROVISIONAL,
                confidence_weight=0.85,
                examples=[{"input": "Los estudiantes estudian", "expected": "ESTUDIANTE VARIOS ESTUDIAR"}],
            ),
            # 20. Adjetivo atributivo posnominal (unificado y formalmente diferenciado)
            GrammarRule(
                rule_id="LSEC_ADJ_POSTNOMINAL",
                name="Adjetivo atributivo posnominal",
                description="Los adjetivos atributivos dentro del sintagma nominal se colocan después del sustantivo.",
                grammar_version="0.2.0",
                priority=45,
                scope=RuleScope.WORD_ORDER,
                conditions=[
                    RuleCondition(field="has_attributive_adjective", operator="eq", value=True),
                ],
                actions=[
                    RuleAction(action_type="reorder", parameters={"pattern": "noun_adj"}, description="Adjetivo después del sustantivo"),
                ],
                required_evidence=["spacy_dep:amod"],
                validation_status=RuleValidationStatus.PROVISIONAL,
                confidence_weight=0.90,
                examples=[{"input": "la universidad grande", "expected": "UNIVERSIDAD GRANDE"}],
                counterexamples=[{"input": "La casa es grande", "reason": "Adjetivo predicativo en cláusula copulativa"}],
            ),
            # 21. Adjetivo predicativo (diferenciado de atributivo)
            GrammarRule(
                rule_id="LSEC_ADJ_PREDICATIVE",
                name="Adjetivo predicativo en cláusula de estado",
                description="El adjetivo predicativo ocupa la posición de predicado principal tras el sujeto.",
                grammar_version="0.2.0",
                priority=25,
                scope=RuleScope.WORD_ORDER,
                conditions=[
                    RuleCondition(field="has_adjectival_predicate", operator="eq", value=True),
                    RuleCondition(field="copula_type", operator="eq", value="attributive"),
                ],
                actions=[
                    RuleAction(action_type="reorder", parameters={"pattern": "subject_predicate_adj"}),
                ],
                required_evidence=["has_adjectival_predicate:true", "copula_type:attributive"],
                validation_status=RuleValidationStatus.PROVISIONAL,
                confidence_weight=0.85,
                examples=[{"input": "El campus es hermoso", "expected": "CAMPUS HERMOSO"}],
            ),
            # 22. Transferencia funcional de determinantes y preposiciones
            GrammarRule(
                rule_id="LSEC_FUNCTIONAL_TRANSFER_DET_ADP",
                name="Transferencia funcional de DET y ADP",
                description="Analiza definitud, deixis, posesión, origen, destino, ubicación, instrumento, beneficiario antes de omitir formas del español.",
                grammar_version="0.2.0",
                priority=15,
                scope=RuleScope.LEXICAL_SELECTION,
                conditions=[
                    RuleCondition(field="functional_transfers", operator="exists", value=True),
                ],
                actions=[
                    RuleAction(action_type="apply_functional_transfer", parameters={"strategy": "functional_analysis"}),
                ],
                required_evidence=["spacy_pos:DET|ADP"],
                validation_status=RuleValidationStatus.PROVISIONAL,
                confidence_weight=0.80,
                examples=[{"input": "Vengo de Tulcán", "expected": "PRO1 TULCÁN DESDE VENIR"}],
            ),
        ]

        # Aliases de compatibilidad para evitar roturas
        self._aliases = {
            "LSEC_ADJ_AFTER_NOUN": "LSEC_ADJ_POSTNOMINAL",
            "LSEC_COPULA_CONTEXT": "LSEC_COPULA_OMISSION",
            "LSEC_OMIT_DET_ADP": "LSEC_FUNCTIONAL_TRANSFER_DET_ADP",
            "LSEC_PERIPHRASIS_PROGRESSIVE": "LSEC_ASPECT_PROGRESSIVE",
            "LSEC_PERIPHRASIS_PERFECT": "LSEC_ASPECT_PERFECTIVE",
        }

        for rule in baseline:
            self.register(rule)

        logger.info("RuleRegistry: %d reglas PROVISIONAL cargadas con éxito.", len(baseline))


# Singleton global
_global_registry: Optional[RuleRegistry] = None


def get_rule_registry() -> RuleRegistry:
    """Retorna el registro global de reglas (singleton)."""
    global _global_registry
    if _global_registry is None:
        _global_registry = RuleRegistry()
    return _global_registry
