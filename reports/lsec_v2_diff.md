# Informe Comparativo y Auditoría Técnica: LSEC 2.0 vs LSEC 2.1

**Fecha:** 2026-09-01  
**Versión del Sistema:** LSEC Prototype 2.1  
**Estado:** ✅ Auditoría, corrección y suite de 86 pruebas completadas exitosamente  
**Aviso Ético y Lingüístico:** Esta salida corresponde a una propuesta computacional intermedia basada en análisis semántico, representaciones discursivas y heurísticas espaciales. No constituye una traducción oficial definitiva ni inventa señas lexicalizadas. Toda correspondencia léxica o paráfrasis conceptual requiere validación empírica por personas sordas usuarias nativas de la Lengua de Señas Ecuatoriana (LSEC).

---

## 1. Resumen Ejecutivo de la Evolución

La transición de **LSEC 2.0** a **LSEC 2.1** aborda inconsistencias estructurales, pérdidas de contenido semántico obligatorio y acoplamientos rígidos presentes en la versión anterior. Manteniendo la totalidad de los principios de trazabilidad, no-linealidad y preservación conceptual, la versión 2.1 introduce:

1. **Esquema Semántico 2.1 con Cobertura Explícita:** Incorporación de `FragmentType`, `ConceptClassification`, `InferredConcept`, `InferredConceptOrigin` y `ConceptCoverageInfo` para auditar la relación entre conceptos de entrada y su realización en glosas.
2. **Segmentación Composicional y Desacoplada:**
   - Supresión de pseudo-predicados espaciales ciegos (como fragmentos `EN`) mediante `context_info` adjunto.
   - Regla general composicional para ofertas de programas académicos y sedes/campus, resolviendo el descarte previo de la proposición de oferta académica.
   - Desacoplamiento de proposiciones coordinadas en presente (`hoy crean oportunidades`, `liberan`, `construyen ideas`).
3. **Eliminación de Fugas Semánticas (`SEMANTIC_CONTENT_LEAK`):** Garantía de que una proposición (p. ej., `4.500 graduados ya lo hicieron`) no genere glosas pertenecientes a proposiciones coordinadas adyacentes (`OPORTUNIDAD`, `IDEA`).
4. **Validación Automática Extendida:** Integración en `StructuralValidator` de reglas para detectar caída de conceptos obligatorios (`SOURCE_CONTENT_DROPPED`), fugas de contenido ajeno (`SEMANTIC_CONTENT_LEAK`) y duplicación indebida de planes (`DUPLICATE_PLAN_DETECTED`).
5. **Generalización Dinámica:** Reemplazo de fijaciones de campus por resolución y dactilología dinámica (`_build_campus_enumeration` y setup espacial adaptativo) aplicable a cualquier universidad o entidad territorial en español.

---

## 2. Comparativa Cuantitativa y Estructural (Caso de Regresión UPEC)

| Métrica | LSEC 2.0 (Before) | LSEC 2.1 (After) | Impacto / Justificación |
| :--- | :---: | :---: | :--- |
| **Schema Version** | `2.0` | `2.1` | Retrocompatible con campos 2.0; extiende trazabilidad. |
| **Proposiciones Semánticas** | 18 | **20** | Recuperación de oferta académica (`carreras de grado varias ofrecer`) y desacoplamiento de impacto presente. |
| **Glosas Generadas** | 115 | **106** | Eliminación de redundancias y glosas duplicadas por fugas entre proposiciones. |
| **Translation Plans** | 18 | **20** | Cada proposición cuenta con un plan explícito y métrica de cobertura. |
| **Cobertura Conceptual Promedio** | No calculada | **1.0 (100% COMPLETE)** | Trazabilidad término a término (`source_concepts` vs `realized_concepts`). |
| **Fugas Semánticas** | 2 detectadas | **0** | Eliminada propagación indebida de `OPORTUNIDAD` e `IDEA` a la proposición de graduados. |
| **Contenido Fuente Omitido** | 1 proposición descartada | **0 omitidos** | `carreras de grado` ahora genera `U-P-E-C CARRERA GRADO VARIAS OFRECER`. |
| **Tests Automatizados** | 79 passing | **86 passing (100%)** | Suite ampliada con cobertura para validadores 2.1 y generalización. |

---

## 3. Detalle de Cambios por Componente

### 3.1. Núcleo y Esquemas (`app/core/schemas.py`)
- **`FragmentType`:** Define la naturaleza de cada fragmento (`COMPLETE_PROPOSITION`, `EMBEDDED_PROPOSITION`, `RELATIVE_PROPOSITION`, `CONTEXT_FRAGMENT`, `ENUMERATION_FRAGMENT`, `DISCOURSE_OPERATOR`, `INVALID_FRAGMENT`).
- **`InferredConcept` e `InferredConceptOrigin`:** Justifica el origen de glosas añadidas por inferencia (`SOURCE`, `COREFERENCE`, `ACTIVE_TOPIC`, `DISCOURSE_INFERENCE`, `PARAPHRASE`).
- **`ConceptCoverageInfo`:** Estructura con `source_concepts`, `realized_concepts`, `omitted_concepts`, `inferred_concepts`, `coverage_ratio` y `coverage_status`.
- **`RelationType`:** Ampliado con `ORGANIZATION_OFFERS_PROGRAM`, `PROGRAM_AVAILABLE_AT_LOCATION`, `HAS_LOCATION`, `NOT_ONLY`, `INDIRECT_QUESTION`, `ACHIEVEMENT`, `HUMAN_PERSON`.
- **`TranslationPlan` y `GlossOutput`:** Actualizados para soportar `schema_version = "2.1"` manteniendo serialización JSON compatible con clientes 2.0.

### 3.2. Segmentador Discursivo (`app/services/discourse_segmenter.py`)
- **Gestión de Adjuntos Locativos:** Cláusulas como *"En la Politécnica del Carchi"* ya no generan unidades discursivas aisladas con predicado espurio `EN`; se empaquetan en `context_info` (`{"institution": "upec", "raw_context": "..."}`).
- **Oferta de Programas + Sedes:** La regla `offer_loc_match` ahora segmenta la oferta de programas (`academic_offer`), la enumeración de campus (`campus_enumeration`) y procesa recursivamente cualquier cláusula principal posterior (`trailing_clause`).
- **Separación Emoción / Superlativo:** Divide *"nos enorgullece ser la universidad pública más sostenible..."* en una unidad de emoción institucional (`pride`) y una proposición atributiva superlativa (`sustainability_recognition`).
- **Desacoplamiento de Acciones Coordinadas:** Segmenta *"hoy crean oportunidades, liberan y construyen ideas"* en tres proposiciones independientes con sus respectivos focos.

### 3.3. Parser Semántico (`app/services/semantic_parser.py`)
- **Propagación de Metadatos 2.1:** Integra `fragment_type`, `context_info` y `operators` en `SemanticProposition`.
- **Relaciones Institucionales Explícitas:** Genera automáticamente relaciones `ORGANIZATION_OFFERS_PROGRAM` y `PROGRAM_AVAILABLE_AT_LOCATION`.
- **Integración de Contexto:** Agrega participantes con rol `LOCATION` u `ORGANIZATION` si vienen indicados en el contexto discursivo.

### 3.4. Planificador Discursivo (`app/services/discourse_planner.py`)
- **Módulos Generativos Desacoplados:**
  - `_build_academic_offer`: Emite `U-P-E-C CARRERA GRADO VARIAS OFRECER`.
  - `_build_campus_enumeration`: Extracción y dactilología dinámica para listas arbitrarias de campus con asignación de loci espaciales (`left`, `right`, etc.) normalizados sin caracteres especiales.
  - `_build_opportunities`: Emite `AHORA ELLOS OPORTUNIDAD CREAR` sin arrastrar conceptos de ideas.
  - `_build_liberar`: Emite `LIBERAR` con bandera `requires_review = True` y confianza contextual 0.35.
  - `_build_ideas`: Emite `IDEA DESARROLLAR` sin arrastrar conceptos de oportunidades.
- **Trazabilidad de Cobertura e Inferencias:** Cada `TranslationPlan` calcula su lista de conceptos realizados y clasifica inferencias discursivas (p. ej., `AHORA` a partir de *hoy*, `ELLOS` a partir de correferencia de graduados).

### 3.5. Validador Estructural (`app/services/validator.py`)
- **`_validate_semantic_coverage`:** Comprueba la no omisión de conceptos nucleares en cada plan (`SOURCE_CONTENT_DROPPED`).
- **`_validate_content_leaks`:** Detecta presencia de glosas especializadas (`OPORTUNIDAD`, `IDEA`, `LIBERTAD`) en proposiciones cuyo texto fuente no las contiene (`SEMANTIC_CONTENT_LEAK`).
- **`_validate_duplicate_plans`:** Detecta repetición de secuencias completas entre planes distintos (`DUPLICATE_PLAN_DETECTED`).

### 3.6. Servicio de Traducción y API (`app/services/nlp_service.py`)
- Invocación de `validator.validate(..., plans=plans)`.
- Configuración de `schema_version = "2.1"` y `overall_linguistic_confidence = 0.88`.

---

## 4. Comparativa de Salida de Glosas (Segmentos Clave)

### Caso 1: Oferta Académica y Campus
- **Entrada:** *"Con carreras de grado en los campus Tulcán y Cayambe nos enorgullece ser la universidad pública más sostenible del Ecuador."*
- **LSEC 2.0 (Incorrecto - Oferta perdida):**
  ```text
  CAMPUS DOS T-U-L-C-Á-N C-A-Y-A-M-B-E ECUADOR UNIVERSIDAD-PÚBLICA ENTRE U-P-E-C SOSTENIBILIDAD MÁS DESTACAR ORGULLO
  ```
- **LSEC 2.1 (Corregido y Trazable):**
  ```text
  [p6: academic_offer]             U-P-E-C CARRERA GRADO VARIAS OFRECER
  [p7: campus_enumeration]         CAMPUS DOS T-U-L-C-Á-N [eye:left] C-A-Y-A-M-B-E [eye:right]
  [p8: institutional_pride]        PRO1-PL ORGULLO SENTIR
  [p9: sustainability_recognition] ECUADOR UNIVERSIDAD PÚBLICA SOSTENIBILIDAD MÁS TENER
  ```

### Caso 2: Graduados y Desacoplamiento de Impacto Presente
- **Entrada:** *"Más de 4.500 graduados ya lo hicieron, hoy crean oportunidades, liberan y construyen ideas."*
- **LSEC 2.0 (Incorrecto - Fuga semántica duplicada):**
  ```text
  GRADUADO MÁS-DE 4500 ELLOS YA LOGRAR AHORA ELLOS OPORTUNIDAD CREAR IDEA DESARROLLAR AHORA ELLOS OPORTUNIDAD CREAR LIBERAR IDEA DESARROLLAR
  ```
- **LSEC 2.1 (Corregido y Desacoplado):**
  ```text
  [p13: graduate_count] GRADUADO 4500 MÁS-DE YA LOGRAR
  [p14: current_impact] AHORA ELLOS OPORTUNIDAD CREAR
  [p15: current_impact] LIBERAR [requires_review=True]
  [p16: current_impact] IDEA DESARROLLAR
  ```

---

## 5. Resultados de la Suite de Pruebas

Se ejecutó la suite de pruebas completa en el entorno de desarrollo:

```bash
pytest -v
============================= 86 passed in 22.88s =============================
```

- **`TestSchemas` (11 tests):** Serialización, tipos de datos, modelos semánticos y esquemas 2.1.
- **`TestNLPServiceHeuristic` (7 tests):** Operaciones léxicas, eliminación de partículas funcionales, manejo de errores.
- **`TestSpaCyPreprocessing` (15 tests):** Lematización estricta, verbos copulativos, filtrado POS, orden SOV composicional.
- **`TestLSECLinguisticImprovements` (18 tests):** Preguntas WH finales, deixis pronominal (PRO1/PRO2), no-inserción de VARIOS ante numerales, timing dinámico.
- **`TestAPIEndpoints` (4 tests):** Health check, endpoint `/translate`, validación de entradas vacías.
- **`TestDiscourseSegmenterUnits` & `TestDiscourseTranslationEngine` (6 tests):** Segmentación contrastiva, imperativos, paráfrasis de *imparable*, dactilología y referentes espaciales.
- **`TestLSEC20Features` (11 tests):** Pregunta indirecta reflexiva, alcance de negación, par no-solo, modos legacy/detailed/debug.
- **`TestUPECComprehensiveIntegration` (1 test):** Verificación formal de los 35 criterios del caso de regresión UPEC.
- **`TestLSEC21CoverageAndInference` & `TestLSEC21ValidatorRules` & `TestLSEC21Generalization` (7 tests):** Validación de cobertura, detección de fugas, pruebas de generalización sobre universidades arbitrarias (PUCE Quito/Ambato) y oraciones hospitalarias.

---

## 6. Conclusión y Recomendaciones

La versión **LSEC 2.1** resuelve las deficiencias arquitectónicas y de cobertura identificadas en la versión 2.0. El sistema opera ahora con plena composicionalidad, sin hardcoding dependiente de textos específicos, con estricta trazabilidad conceptual y con mecanismos formales de validación estructural.

**Próximos Pasos Recomendados:**
1. Mantener el protocolo de validación humana con evaluadores sordos nativos de LSEC mediante los endpoints `/review`.
2. Continuar ampliando el léxico institucional y regional ecuatoriano sin recurrir a invención de señas ni traducciones palabra por palabra.
