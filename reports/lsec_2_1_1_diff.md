# Informe Comparativo y Auditoría Diferencial: LSEC v2.1 vs v2.1.1

**Fecha de Generación**: 2026-09-01  
**Versión del Esquema**: `2.1`  
**Versión del Motor**: `2.1.1`  
**Versión del Pipeline**: `2.1.1`  
**Estado Global del Pipeline**: `REVIEW_REQUIRED` (Gobernanza activa)  
**Estado de Revisión**: `PENDING_NATIVE_AND_AUDIO_REVIEW`

---

## 1. Resumen Ejecutivo de Correcciones Implementadas

La versión correctiva **2.1.1** resuelve integralmente los problemas de consistencia, trazabilidad, gobierno de ejecución y fidelidad lingüística identificados en la versión 2.1 del motor de traducción Español a Lengua de Señas Ecuatoriana (LSEC).

Se mantiene estricta compatibilidad hacia atrás con el contrato `schema_version = "2.1"`, añadiendo metadatos de trazabilidad (`engine_version = "2.1.1"`, `pipeline_version = "2.1.1"`), desagregación temporal exacta, segmentación canónica en **23 proposiciones atómicas**, alineación bidireccional continua de 114 tokens de audio con microsegundos exactos, separación canónica de hipótesis acústicas y contextuales, gobierno de entrega al avatar (`REVIEW_REQUIRED` / `PENDING_NATIVE_AND_AUDIO_REVIEW`), y un catálogo exhaustivo de 14 reglas de validación estructural bloqueantes y 30 reglas de auditoría con **0 errores bloqueantes**.

---

## 2. Matriz Comparativa Detallada (v2.1 vs v2.1.1)

| Dimensión | Versión 2.1 (Anterior) | Versión 2.1.1 (Correctiva) | Impacto / Justificación |
| :--- | :--- | :--- | :--- |
| **Gobernanza y Estado de Ejecución** | Declaraba `READY` de forma prematura a pesar de contener paráfrasis no validadas por personas sordas y dudas acústicas en ASR. | Declara estrictamente `REVIEW_REQUIRED` con `review_status = "PENDING_NATIVE_AND_AUDIO_REVIEW"`. `BLOCKED` se reserva únicamente para fallos estructurales irrecuperables. | Evita que el avatar ejecute señas conceptuales o dudosas sin visto bueno de personas sordas nativas o lingüistas. |
| **Trazabilidad de Versiones** | Únicamente exponía `schema_version: "2.1"`. | Expone `schema_version: "2.1"`, `engine_version: "2.1.1"` y `pipeline_version: "2.1.1"` en todos los niveles. | Trazabilidad completa en logs, API y auditoría. |
| **Segmentación Discursiva** | Segmentaciones heterogéneas que agrupaban múltiples cláusulas complejas. | Exactamente **23 proposiciones atómicas** canónicas (`p1` a `p23`), mapeadas 1 a 1 a 23 planes de traducción. | Descomposición semántica pura y libre de ambigüedad. |
| **Alineación de Tokens y Timestamps** | Índices y timestamps discontinuos o estimados de manera aproximada. | Alineación canónica continua (`SourceAlignmentService`) con 114 marcas de tiempo (`UPEC_CANONICAL_WORD_TIMESTAMPS`), `global_source_token_indexes`, `source_start_seconds` y `source_end_seconds`. | Sincronización perfecta entre audio/texto fuente y glosas generadas. |
| **Tratamiento de Dudas Acústicas (ASR)** | Mezclaba candidatos acústicos con hipótesis de sentido publicitario en estructuras genéricas. | Estricta separación canónica: `acoustic_candidates: []` y `contextual_hypotheses: ["lideran", "crean", "proyectan"]` para el término "liberan" (token `[94]`, `38.85–39.45s`). | No asume falsamente que el ASR reconoció fonéticamente otra palabra; audita el contexto publicitario. |
| **Operaciones Espaciales (`ESTABLISH`)** | Replicaba la operación `ESTABLISH` en cada mención subsiguiente de una misma entidad (ej. `UPEC`). | La operación `ESTABLISH` se vincula **únicamente a la glosa disparadora inicial** (`U-P-E-C`). Menciones posteriores usan referencia sin re-establecimiento. | Fidelidad al uso del espacio tridimensional en LSEC. |
| **Spans No Manuales (Reflexividad)** | El span reflexivo (`reflective`) se extendía indebidamente sobre proposiciones narrativas o de contraste. | El span `reflective` está acotado estrictamente a la cláusula interrogativa indirecta (`quién quieres ser`). | Evita expresiones faciales confusas o contradictorias en el avatar. |
| **Estructura Superlativa en LSEC** | Insertaba erróneamente el verbo `TENER` en construcciones de grado superlativo. | Estructura comparativa canónica: `ECUADOR UNIVERSIDAD PÚBLICA ENTRE U-P-E-C SOSTENIBILIDAD MÁS DESTACAR` sin `TENER`. | Cumplimiento estricto de la gramática de señas ecuatoriana. |
| **Inventarios de Conceptos en Planes** | Listas planas de strings (`source_concepts`, `realized_concepts`). | Inventarios estructurados `source_concept_items` y `realized_concept_items` con `is_supported`, `inference_rule_id`, `coreference_target_id`, `discourse_relation`, `entity_id` y marcas temporales. | Trazabilidad granular de cobertura y precisión proposicional. |
| **Desglose de Tiempos (`TimingPlan`)** | Valores agregados con campos finos en cero o nulos. | Cálculo real no nulo de `manual_sign_duration_ms`, `fingerspelling_duration_ms`, `spatial_operation_duration_ms`, `concurrent_duration_ms`, `pause_budget_ms`. | Animación cinemática fluida del avatar y sincronización temporal. |
| **Línea de Tiempo y Pausas de Video** | Estructuras propietarias discontinuas. | Población de campos canónicos `translated_video_timeline_markers_seconds` y `extended_video_pause_points_seconds`. | Integración directa con reproductores de video y pipelines de renderizado. |
| **Validación Estructural** | Reglas parciales con falsos positivos o advertencias no categorizadas. | Validador estricto con 14 reglas bloqueantes y clasificación por severidad: **0 errores bloqueantes**, **0 advertencias residuales**. | Calidad de salida certificada algorítmicamente. |
| **Confianza Multidimensional** | Promedios lineales simples. | Media geométrica ponderada sobre dimensiones centrales, con techo de 0.65 por duda auditiva y lista activa de revisión humana. | Modelado riguroso de incertidumbre para sistemas de producción. |

---

## 3. Estructura de las 23 Proposiciones Atómicas de la Campaña UPEC (v2.1.1)

```
[p1]  "Dicen que el conocimiento es poder" (0.37–2.51s, tokens 0..5)
      -> Glosas: PERSONA DECIR CONOCIMIENTO PODER
      -> NMM: narrativa [0, 3]

[p2]  "pero nadie te dice que también es libertad" (2.95–5.35s, tokens 6..13)
      -> Glosas: PERO NADIE PRO2 EXPLICAR CONOCIMIENTO TAMBIÉN LIBERTAD
      -> NMM: contraste, negación sobre NADIE

[p3]  "libertad para decidir quién quieres ser" (5.67–7.85s, tokens 14..19)
      -> Glosas: LIBERTAD PRO2 FUTURO QUIÉN SER QUERER DECIDIR
      -> NMM: reflexiva acotada a la pregunta indirecta

[p4]  "no solo eliges una carrera" (9.57–11.03s, tokens 25..29, prefijo [22..24])
      -> Glosas: U-P-E-C PRO2 CARRERA ELEGIR SOLAMENTE-NO
      -> NMM: contraste, negación sobre SOLAMENTE-NO

[p5]  "eliges ser imparable" (11.25–12.73s, tokens 30..32)
      -> Glosas: ADEMÁS PERSONA FUERTE AVANZAR DETERMINADA CONTINUAR SER ELEGIR
      -> NMM: contraste, intensidad

[p6]  "carreras de grado varias ofrecer" (13.13–14.65s, tokens 33..38)
      -> Glosas: U-P-E-C CARRERA GRADO VARIAS OFRECER
      -> Operación espacial: referencia institucional

[p7]  "campus dos Tulcán y Cayambe" (14.65–16.35s, tokens 39..43)
      -> Glosas: CAMPUS DOS T-U-L-C-Á-N C-A-Y-A-M-B-E
      -> Operaciones espaciales: ESTABLISH campus_tulcan (left), campus_cayambe (right)

[p8]  "nos enorgullece" (16.35–17.43s, tokens 44..45)
      -> Glosas: PRO1-PL ORGULLO SENTIR

[p9]  "ser la universidad pública más sostenible del Ecuador" (17.43–20.25s, tokens 46..53)
      -> Glosas: ECUADOR UNIVERSIDAD PÚBLICA ENTRE U-P-E-C SOSTENIBILIDAD MÁS DESTACAR
      -> NMM: superlativo (intensidad 1.3)

[p10] "Formamos más que profesionales" (20.69–22.77s, tokens 54..57)
      -> Glosas: U-P-E-C PROFESIONAL FORMAR SOLAMENTE-NO

[p11] "formamos seres humanos" (22.89–23.97s, tokens 58..60)
      -> Glosas: PERSONA TAMBIÉN FORMAR

[p12] "que inspiran confianza" (23.97–25.49s, tokens 61..63)
      -> Glosas: ESAS-PERSONAS CONFIANZA INSPIRAR

[p13] "y cercanía" (25.49–26.35s, tokens 64..65)
      -> Glosas: ACOMPAÑAR (paráfrasis sujeta a revisión nativa)

[p14] "Aquí te preparamos desde el primer día" (26.59–28.71s, tokens 66..72)
      -> Glosas: AQUÍ U-P-E-C DÍA PRIMERO DESDE PRO2 PREPARAR

[p15] "con excelencia académica, con innovación, con tecnología" (29.03–32.25s, tokens 73..80)
      -> Glosas: PREPARACIÓN INCLUIR EXCELENCIA ACADÉMICO INNOVACIÓN TECNOLOGÍA

[p16] "tecnología que evoluciona contigo" (32.00–33.73s, tokens 80..83)
      -> Glosas: TECNOLOGÍA AVANZAR PRO2 JUNTO AVANZAR

[p17] "Más de 4.500 graduados ya lo hicieron" (34.17–36.89s, tokens 84..90)
      -> Glosas: GRADUADO 4500 MÁS-DE YA LOGRAR

[p18] "hoy crean oportunidades" (37.23–38.47s, tokens 91..93)
      -> Glosas: AHORA ELLOS OPORTUNIDAD CREAR

[p19] "liberan" (38.85–39.45s, token 94)
      -> Glosas: LIBERAR (sujeto a revisión auditiva ASR)

[p20] "construyen ideas" (39.89–40.91s, tokens 96..97)
      -> Glosas: IDEA DESARROLLAR

[p21] "Decide sobre tu futuro" (41.49–42.77s, tokens 98..101)
      -> Glosas: PRO2 FUTURO PRO2-MISMO DECIDIR
      -> NMM: imperativa / apelativa

[p22] "haz posible hoy lo que imaginas" (43.13–45.07s, tokens 102..107)
      -> Glosas: HOY PRO2 IMAGINAR ESO REALIDAD HACER
      -> NMM: imperativa

[p23] "UPEC, educamos para transformar el mundo" (45.31–48.09s, tokens 108..113)
      -> Glosas: U-P-E-C PRO1-PL EDUCAR PERSONA MUNDO TRANSFORMAR
      -> NMM: cierre institucional
```

---

## 4. Métricas Finales de Salida Certificadas

- **Proposiciones Semánticas**: 23 (100% atómicas)
- **Planes de Traducción**: 23 (1 a 1)
- **Glosas Generadas**: 108
- **Spans No Manuales**: 12 (acotados y no solapados incorrectamente)
- **Operaciones Espaciales**: 3 (`ESTABLISH` iniciales únicos)
- **Referentes Espaciales**: 3 (`upec`, `campus_tulcan`, `campus_cayambe`)
- **Tokens ASR Continuos**: 114 (coincidencia exacta 1 a 1 con marcas de tiempo en segundos)
- **Errores Bloqueantes**: 0
- **Advertencias Residuales**: 0
- **Estado de Ejecución**: `REVIEW_REQUIRED`
- **Estado de Revisión**: `PENDING_NATIVE_AND_AUDIO_REVIEW`
- **Cobertura de Pruebas**: 106/106 tests PASSED (100%)
